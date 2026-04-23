# -*- coding: utf-8 -*-
"""
技能管理器 - B端履约中台评估体系

定义一套固定的评估标准：
  - 需求拆解策略：按页面×功能点拆解
  - 工时估算方式：S/M/L/XL/XXL 五档工时 + 测试公式（后端×0.35）
  - 输出角色配置：产品 / 前端 / 后端 / 测试

历史案例与代码知识库按当前评估体系隔离。
"""
import json
import logging
import os
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR        = os.path.join(_BASE_DIR, "knowledge", "skills")
EXAMPLES_BASE_DIR = os.path.join(_BASE_DIR, "knowledge", "examples")
CODE_KB_DIR       = os.path.join(_BASE_DIR, "knowledge", "code_knowledge")

# 固定技能 ID — 只保留 B端履约中台
SKILL_ID = "b_end_fulfillment"

# ============================================================
# 全局状态
# ============================================================
_skills_cache: Dict[str, dict] = {}


# ============================================================
# 公开 API
# ============================================================

def list_skills() -> List[dict]:
    """返回唯一可用技能"""
    skills: List[dict] = []
    if os.path.exists(SKILLS_DIR):
        fpath = os.path.join(SKILLS_DIR, f"{SKILL_ID}.json")
        if os.path.exists(fpath):
            try:
                with open(fpath, encoding="utf-8") as f:
                    s = json.load(f)
                skills.append({
                    "id": s.get("id", SKILL_ID),
                    "name": s.get("name", SKILL_ID),
                    "description": s.get("description", ""),
                    "version": s.get("version", "1.0"),
                    "source": "file",
                })
            except Exception as e:
                logger.warning(f"加载技能文件失败: {fpath} - {e}")
    return skills


def get_skill(skill_id: Optional[str] = None) -> dict:
    """获取技能完整配置，仅支持 b_end_fulfillment"""
    if skill_id and skill_id != SKILL_ID:
        logger.warning(f"仅支持 {SKILL_ID} 技能，忽略传入的 skill_id={skill_id}")
    sid = SKILL_ID

    if sid in _skills_cache:
        return _skills_cache[sid]

    fpath = os.path.join(SKILLS_DIR, f"{sid}.json")
    if os.path.exists(fpath):
        try:
            with open(fpath, encoding="utf-8") as f:
                skill = json.load(f)
            _skills_cache[sid] = skill
            return skill
        except Exception as e:
            logger.error(f"加载技能 {sid} 失败: {e}")

    # 文件不存在时返回空配置（由节点内建的 prompt 兜底）
    skill = {"id": sid, "name": "B端履约中台评估", "roles": ["产品", "前端开发", "后端开发", "测试"]}
    _skills_cache[sid] = skill
    return skill


def get_current_skill_id() -> str:
    return SKILL_ID


def set_current_skill(skill_id: str) -> bool:
    """始终返回 True，仅保留 b_end_fulfillment"""
    if skill_id != SKILL_ID:
        logger.warning(f"仅支持 {SKILL_ID} 技能，忽略切换请求")
        return False
    return True


def reload_skill(skill_id: str):
    """清除缓存，强制从文件重新加载指定技能"""
    _skills_cache.pop(skill_id, None)


def load_examples(skill_id: Optional[str] = None, limit: int = 5) -> List[dict]:
    """
    加载历史评估案例作为 few-shot 示例。
    存储位置：knowledge/examples/<skill_id>/*.json
    每个文件为一次历史评估，包含 requirement / pages_features / worktime 三段。
    """
    sid = skill_id or _current_skill_id
    examples_dir = os.path.join(EXAMPLES_BASE_DIR, sid)

    if not os.path.exists(examples_dir):
        return []

    examples: List[dict] = []
    fnames = sorted(f for f in os.listdir(examples_dir) if f.endswith(".json"))
    for fname in fnames[-limit:]:
        try:
            with open(os.path.join(examples_dir, fname), encoding="utf-8") as f:
                ex = json.load(f)
            examples.append(ex)
        except Exception as e:
            logger.warning(f"加载历史案例失败: {fname} - {e}")

    logger.info(f"[SkillManager] 加载 {len(examples)} 个历史案例 (skill={sid})")
    return examples


def search_kb_cases(query: str = "", skill_id: Optional[str] = None, limit: int = 3) -> List[dict]:
    """
    从领域知识库案例（kb_cases.json）中按 tag/场景关键词检索相似历史案例。
    返回最多 limit 条，格式与 load_examples 兼容。
    """
    sid = skill_id or _current_skill_id
    kb_path = os.path.join(_BASE_DIR, "knowledge", sid, "kb_cases.json")
    if not os.path.exists(kb_path):
        return []

    try:
        with open(kb_path, encoding="utf-8") as f:
            cases = json.load(f)
    except Exception as e:
        logger.warning(f"加载 kb_cases.json 失败: {e}")
        return []

    # 先按空格/标点分词，再对中文片段做 2-char bigram 扩展提高召回率
    raw_terms = [t for t in re.split(r'[\s,，、/+（）()]+', query) if len(t) >= 2]
    query_terms = set()
    for t in raw_terms:
        query_terms.add(t.lower())
        if len(t) >= 4:
            for i in range(len(t) - 1):
                query_terms.add(t[i:i+2].lower())
    query_terms = list(query_terms)

    scored = []
    for case in cases:
        tags = [t.lower() for t in case.get("tags", [])]
        scenario = case.get("scenario", "").lower()
        feature = case.get("feature", "").lower()
        text = " ".join(tags) + " " + scenario + " " + feature
        score = sum(1 for t in query_terms if t in text)
        if score > 0:
            scored.append((score, case))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for _, case in scored[:limit]:
        h = case.get("hours", {})
        results.append({
            "id": case.get("id", ""),
            "scenario": case.get("scenario", ""),
            "dev_type": case.get("dev_type", ""),
            "feature": case.get("feature", ""),
            "hours": h,
            "complexity": case.get("complexity", ""),
            "tags": case.get("tags", []),
        })
    return results


def load_code_knowledge(query: str = "", limit: int = 3) -> str:
    """
    从代码知识库检索相关片段，来源优先级：
      1. 内置代码知识库（knowledge/code_knowledge/）
      2. 外部代码知识库（.env CODE_KB_DIR，Markdown/TXT/JSON）
      3. Java 源码自动扫描（.env JAVA_SOURCE_DIR，提取接口+实体+服务）
    返回拼接的 Markdown 文本，注入 LLM prompt。
    """
    from config import AppConfig

    query_terms = [t.lower() for t in query.split() if len(t) >= 2][:10]
    candidates: List[tuple] = []

    # ── 1 & 2：扫描 Markdown/TXT/JSON 知识库文件 ─────────────────────
    scan_dirs = [CODE_KB_DIR] + [d for d in AppConfig.CODE_KB_EXT_DIRS
                                 if d and os.path.isdir(d) and d != CODE_KB_DIR]

    for kb_dir in scan_dirs:
        if not os.path.isdir(kb_dir):
            continue
        for fname in os.listdir(kb_dir):
            fpath = os.path.join(kb_dir, fname)
            if not os.path.isfile(fpath):
                continue
            if not any(fname.endswith(ext) for ext in (".md", ".txt", ".json")):
                continue
            try:
                with open(fpath, encoding="utf-8") as f:
                    content = f.read()
                score = sum(1 for t in query_terms if t in content.lower()) if query_terms else 0
                candidates.append((score, fname, content[:1200]))
            except Exception as e:
                logger.warning(f"读取代码知识库失败: {fname} - {e}")

    candidates.sort(key=lambda x: x[0], reverse=True)
    results = []
    for score, fname, content in candidates[:limit]:
        if score > 0 or not query_terms:
            results.append(f"### {fname}\n{content}")

    # ── 3：Java 源码自动扫描（支持多个目录）──────────────────────────
    java_dirs = AppConfig.JAVA_SOURCE_DIRS or []
    for java_dir in java_dirs:
        if java_dir and os.path.isdir(java_dir):
            try:
                from agent.java_scanner import scan_java_source
                java_summary = scan_java_source(java_dir)
                if java_summary:
                    results.append(java_summary)
            except Exception as e:
                logger.warning(f"Java 源码扫描失败 ({java_dir}): {e}")

    return "\n\n".join(results)


def add_example(example: dict, skill_id: Optional[str] = None) -> str:
    """
    保存一个历史评估案例到文件系统。
    example 格式：
    {
      "requirement": {"module": "", "feature": "", "detail": ""},
      "pages_features": [...],
      "worktime": {"role_breakdown": {...}, "total_days": 0, "actual_days": 0, "note": ""}
    }
    """
    import time as _time
    sid = skill_id or _current_skill_id
    examples_dir = os.path.join(EXAMPLES_BASE_DIR, sid)
    os.makedirs(examples_dir, exist_ok=True)

    fname = f"example_{int(_time.time() * 1000)}.json"
    fpath = os.path.join(examples_dir, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(example, f, ensure_ascii=False, indent=2)

    logger.info(f"[SkillManager] 保存历史案例: {fpath}")
    return fpath
