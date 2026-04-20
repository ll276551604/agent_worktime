# -*- coding: utf-8 -*-
"""
技能管理器 - 管理评估技能（可切换的评估体系）

每个 Skill 定义一套独立的：
  - 需求拆解策略（page_feature / user_story）
  - 工时估算方式（role_based / story_points）
  - 输出角色配置（产品/前端/后端/测试 等）

Skill 可从 knowledge/skills/*.json 加载，也有内置默认值。
支持运行时切换；历史案例与代码知识库按 skill_id 隔离。
"""
import glob
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

# ============================================================
# 内置技能（当 JSON 文件不存在时作为 fallback）
# ============================================================
_BUILTIN_SKILLS: Dict[str, dict] = {
    "standard": {
        "id": "standard",
        "name": "标准产品评估",
        "description": "按页面×功能点拆解，按角色（产品/设计、前端、后端、测试）分别估算工时",
        "version": "1.0",
        "roles": ["产品/设计", "前端开发", "后端开发", "测试"],
        "decomposition": {
            "strategy": "page_feature",
            "max_pages": 8,
            "max_features_per_page": 10,
            "focus": "从产品经理视角，按页面维度拆解功能点，区分新增/调整",
        },
        "estimation": {
            "strategy": "role_based",
            "base_rates": {
                "新增页面-简单": {"产品/设计": 0.25, "前端开发": 0.5,  "后端开发": 0.3, "测试": 0.3},
                "新增页面-中等": {"产品/设计": 0.5,  "前端开发": 1.0,  "后端开发": 0.8, "测试": 0.5},
                "新增页面-复杂": {"产品/设计": 1.0,  "前端开发": 1.5,  "后端开发": 1.5, "测试": 1.0},
                "调整页面-简单": {"产品/设计": 0.1,  "前端开发": 0.2,  "后端开发": 0.1, "测试": 0.2},
                "调整页面-中等": {"产品/设计": 0.2,  "前端开发": 0.4,  "后端开发": 0.3, "测试": 0.3},
                "调整页面-复杂": {"产品/设计": 0.5,  "前端开发": 0.8,  "后端开发": 0.8, "测试": 0.5},
            },
            "complexity_bonuses": {
                "审批流": 0.3, "外部接口": 0.3, "批量操作": 0.2,
                "复杂计算": 0.3, "多角色": 0.2, "实时数据": 0.2,
            },
        },
    },
    "agile": {
        "id": "agile",
        "name": "敏捷故事点评估",
        "description": "按用户故事拆解，用斐波那契故事点（1/2/3/5/8/13）估算，适合敏捷团队",
        "version": "1.0",
        "roles": ["前端开发", "后端开发", "测试"],
        "decomposition": {
            "strategy": "user_story",
            "story_format": "作为[角色]，我希望[做什么]，以便[获得价值]",
            "max_stories": 10,
            "focus": "从用户价值视角拆解，每个故事独立可交付，符合 INVEST 原则",
        },
        "estimation": {
            "strategy": "story_points",
            "point_scale": [1, 2, 3, 5, 8, 13],
            "days_per_point": 0.8,
            "role_ratios": {"前端开发": 0.4, "后端开发": 0.4, "测试": 0.2},
        },
    },
}

# ============================================================
# 全局状态
# ============================================================
_current_skill_id: str = "b_end_fulfillment"
_skills_cache: Dict[str, dict] = {}


# ============================================================
# 公开 API
# ============================================================

def list_skills() -> List[dict]:
    """列出所有可用技能（文件系统 + 内置）"""
    skills: List[dict] = []
    seen: set = set()

    # 文件系统技能优先
    if os.path.exists(SKILLS_DIR):
        for fpath in sorted(glob.glob(os.path.join(SKILLS_DIR, "*.json"))):
            try:
                with open(fpath, encoding="utf-8") as f:
                    s = json.load(f)
                sid = s.get("id") or os.path.splitext(os.path.basename(fpath))[0]
                skills.append({
                    "id": sid,
                    "name": s.get("name", sid),
                    "description": s.get("description", ""),
                    "version": s.get("version", "1.0"),
                    "source": "file",
                })
                seen.add(sid)
            except Exception as e:
                logger.warning(f"加载技能文件失败: {fpath} - {e}")

    # 补充内置技能
    for sid, s in _BUILTIN_SKILLS.items():
        if sid not in seen:
            skills.append({
                "id": sid,
                "name": s["name"],
                "description": s.get("description", ""),
                "version": s.get("version", "1.0"),
                "source": "builtin",
            })

    return skills


def get_skill(skill_id: Optional[str] = None) -> dict:
    """获取技能完整配置，优先从文件加载，其次使用内置"""
    sid = skill_id or _current_skill_id

    if sid in _skills_cache:
        return _skills_cache[sid]

    # 尝试文件加载
    if os.path.exists(SKILLS_DIR):
        fpath = os.path.join(SKILLS_DIR, f"{sid}.json")
        if os.path.exists(fpath):
            try:
                with open(fpath, encoding="utf-8") as f:
                    skill = json.load(f)
                _skills_cache[sid] = skill
                return skill
            except Exception as e:
                logger.warning(f"加载技能 {sid} 失败: {e}")

    # fallback 到内置
    skill = _BUILTIN_SKILLS.get(sid, _BUILTIN_SKILLS["standard"])
    _skills_cache[sid] = skill
    return skill


def get_current_skill_id() -> str:
    return _current_skill_id


def set_current_skill(skill_id: str) -> bool:
    """切换当前全局技能，返回是否成功"""
    global _current_skill_id
    available = {s["id"] for s in list_skills()}
    if skill_id not in available:
        logger.warning(f"技能不存在: {skill_id}，可用: {available}")
        return False
    _current_skill_id = skill_id
    logger.info(f"技能已切换: {skill_id}")
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
    从代码知识库检索相关片段（关键词相关性匹配）。
    存储位置：knowledge/code_knowledge/*.md / *.txt / *.json
    用于向 LLM 注入已有代码结构 / 接口 / 数据模型信息。
    """
    if not os.path.exists(CODE_KB_DIR):
        return ""

    query_terms = [t.lower() for t in query.split() if len(t) >= 2][:10]
    candidates: List[tuple] = []

    for fname in os.listdir(CODE_KB_DIR):
        fpath = os.path.join(CODE_KB_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        if not any(fname.endswith(ext) for ext in (".md", ".txt", ".json")):
            continue
        try:
            with open(fpath, encoding="utf-8") as f:
                content = f.read()
            score = sum(1 for t in query_terms if t in content.lower()) if query_terms else 0
            candidates.append((score, fname, content))
        except Exception as e:
            logger.warning(f"读取代码知识库失败: {fname} - {e}")

    candidates.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, fname, content in candidates[:limit]:
        if score > 0 or not query_terms:
            results.append(f"### {fname}\n{content[:800]}")

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
