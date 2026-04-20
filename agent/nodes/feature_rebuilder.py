# -*- coding: utf-8 -*-
"""
节点1：需求拆解为「页面 × 功能点」或「用户故事」结构
- 策略由 skill_config.decomposition.strategy 决定：
    page_feature  — 标准模式，按页面拆功能点（默认）
    user_story    — 敏捷模式，拆解为用户故事列表
- 注入历史案例（few-shot）学习团队评估习惯
- 注入代码知识库了解现有实现
- 注入业务知识库补充领域背景
- 对比 system_caps 判断新增/调整
"""
import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from agent import gemini_client
from agent.kb_utils import match_business_context


def rebuild_features(state: dict) -> dict:
    req             = state["raw_requirement"]
    kb_feature_rules = state.get("kb_feature_rules", {})
    kb_system_caps   = state.get("kb_system_caps", {})
    retry_count      = state.get("retry_count", 0)
    model_id         = state.get("model_id")
    skill_config     = state.get("skill_config", {})
    examples         = state.get("skill_examples", [])
    code_context     = state.get("code_context", "")

    # Step 1: 知识库案例检索（B端履约中台技能时启用）
    kb_cases = state.get("kb_cases", [])
    skill_id = (skill_config or {}).get("id", "standard")
    if skill_id == "b_end_fulfillment" and not kb_cases:
        try:
            from agent import skill_manager as sm
            query = f"{req.get('feature', '')} {req.get('detail', '')[:60]}"
            kb_cases = sm.search_kb_cases(query=query, skill_id=skill_id, limit=3)
            if kb_cases:
                print(f"[节点1] 知识库检索命中 {len(kb_cases)} 条参照案例: {[c['id'] for c in kb_cases]}", flush=True)
            else:
                print("[节点1] 知识库未命中相似案例，将使用规则推算", flush=True)
        except Exception as e:
            print(f"[节点1] 知识库检索失败: {e}", flush=True)

    business_context = match_business_context(req, state.get("kb_business_docs", []))
    if business_context:
        print(f"[节点1] 命中业务知识库，注入上下文", flush=True)

    strategy = (skill_config.get("decomposition") or {}).get("strategy", "page_feature")
    print(f"[节点1] 拆解策略={strategy} skill={skill_id} retry={retry_count} feature={req.get('feature','')[:30]}", flush=True)

    prompt = _build_prompt(req, kb_feature_rules, kb_system_caps,
                           business_context, skill_config, examples, code_context, kb_cases)

    try:
        raw = gemini_client.call_llm(prompt, model_id=model_id)
        print(f"[节点1] LLM 返回 {len(raw)} 字符", flush=True)
        pages_features = _parse(raw, strategy)
    except Exception as e:
        errors = state.get("errors", [])
        errors.append(f"节点1异常: {e}")
        return {**state, "pages_features": [], "errors": errors, "retry_count": retry_count + 1}

    if not pages_features:
        return {**state, "pages_features": [], "kb_cases": kb_cases, "retry_count": retry_count + 1}

    print(f"[节点1] 输出 {len(pages_features)} 个页面/故事", flush=True)
    return {**state, "pages_features": pages_features, "kb_cases": kb_cases, "retry_count": retry_count}


# ============================================================
# Prompt 构建
# ============================================================

def _build_prompt(req: dict, feature_rules: dict, system_caps: dict,
                  business_context: str = "", skill_config: dict = None,
                  examples: list = None, code_context: str = "", kb_cases: list = None) -> str:
    module  = req.get("module", "") or ""
    feature = req.get("feature", "") or ""
    detail  = req.get("detail", "") or ""
    extra   = req.get("extra", "") or ""

    skill   = skill_config or {}
    decomp  = skill.get("decomposition", {})
    strategy     = decomp.get("strategy", "page_feature")
    max_pages    = decomp.get("max_pages", 8)
    max_features = decomp.get("max_features_per_page", 10)
    focus        = decomp.get("focus", "")
    skill_name   = skill.get("name", "标准产品评估")
    skill_id     = skill.get("id", "standard")

    rules_text = json.dumps(feature_rules, ensure_ascii=False, indent=2) if feature_rules else "（无）"
    caps_text  = json.dumps(system_caps,   ensure_ascii=False, indent=2) if system_caps else "（无）"

    # ── 各可选 section ──────────────────────────────────────
    kb_section   = f"\n## 业务领域知识（优先参考）\n{business_context}\n" if business_context else ""
    code_section = f"\n## 代码/技术知识库（了解现有实现）\n{code_context}\n" if code_context else ""
    examples_section = _build_examples_section(examples, strategy)
    kb_cases_section = _build_kb_cases_section(kb_cases or [])

    if strategy == "user_story":
        return _build_user_story_prompt(
            module, feature, detail, extra,
            decomp, skill_name,
            kb_section, code_section, examples_section,
            caps_text
        )
    elif skill_id == "b_end_fulfillment":
        return _build_b_end_decomp_prompt(
            module, feature, detail, extra,
            max_pages, max_features, skill_name,
            caps_text, kb_section, code_section, examples_section, kb_cases_section
        )
    else:
        return _build_page_feature_prompt(
            module, feature, detail, extra,
            max_pages, max_features, focus, skill_name,
            rules_text, caps_text,
            kb_section, code_section, examples_section
        )


def _build_examples_section(examples: list, strategy: str) -> str:
    if not examples:
        return ""
    parts = ["## 历史评估参考案例（学习拆解风格）"]
    for i, ex in enumerate(examples[:3], 1):
        req_info = ex.get("requirement", {})
        pages    = ex.get("pages_features", [])
        if not req_info or not pages:
            continue
        feat   = req_info.get("feature", "")
        detail = req_info.get("detail", "")[:120]
        parts.append(f"\n### 案例{i}：{feat}")
        parts.append(f"需求描述：{detail}")
        if strategy == "user_story":
            parts.append(f"拆解结果：\n{json.dumps(pages, ensure_ascii=False)}")
        else:
            for p in pages:
                fps = "、".join(p.get("功能点", []))
                parts.append(f"  - 【{p.get('页面','')}（{p.get('类型','')}）】{fps}")
    return "\n".join(parts) if len(parts) > 1 else ""


def _build_kb_cases_section(kb_cases: list) -> str:
    if not kb_cases:
        return ""
    lines = ["\n## 🔍 知识库参照案例（拆解时参考相似案例的功能点粒度）"]
    for case in kb_cases:
        h = case.get("hours", {})
        lines.append(
            f"- [{case.get('id','')}] {case.get('scenario','')} ({case.get('dev_type','')}) | "
            f"特征：{case.get('feature','')[:80]} | "
            f"合计{h.get('total','?')}天"
        )
    return "\n".join(lines) + "\n"


def _build_b_end_decomp_prompt(module, feature, detail, extra,
                                max_pages, max_features, skill_name,
                                caps_text, kb_section, code_section,
                                examples_section, kb_cases_section) -> str:
    """B端履约中台专属拆解 prompt：支持开发类型分类"""
    return f"""你是资深B端履约中台产品经理，使用「{skill_name}」评估体系进行需求功能点拆解。
{kb_cases_section}{kb_section}{code_section}{examples_section}

## 当前需求
- 功能模块：{module or '履约中台'}
- 需求名称：{feature}
- 需求描述：{detail}
- 补充说明：{extra}

## 系统已有能力（据此判断新增/调整）
{caps_text}

## 拆解规则
- 一组 CRUD 接口算 1 个功能点，不逐接口拆行
- 每个独立页面算 1 个功能点
- 纯接口改造（字段追加）与新建页面分开拆
- 若某功能明确"复用已有"或"无改造"，单独列出并注明
- 开发类型：完全新增=全新页面/模块；适应性改造=已有功能上修改；新增=已有模块内追加功能；业务联调=需对接第三方系统

## 输出格式（严格 JSON 数组，禁止代码块）
[
  {{
    "页面": "功能点名称（简明）",
    "类型": "新增",
    "dev_type": "完全新增",
    "功能点": ["功能描述1（简明，不超过30字）", "功能描述2"],
    "complexity_reason": "复杂度判断依据（字段数、接口数、是否含业务逻辑等）"
  }}
]

## 约束
- 功能点数量：1~{max_pages} 个
- 每个功能点的子功能：2~{max_features} 条，每条不超过 30 字
- 类型只能是「新增」或「调整」
- dev_type 只能是「完全新增」「适应性改造」「新增」「业务联调」之一，可多个用逗号分隔
- 只输出 JSON 数组，不要任何其他内容"""


def _build_page_feature_prompt(module, feature, detail, extra,
                                max_pages, max_features, focus, skill_name,
                                rules_text, caps_text,
                                kb_section, code_section, examples_section) -> str:
    focus_line = f"\n评估视角：{focus}" if focus else ""
    return f"""你是一位有 10 年经验的 IT 产品经理，当前使用「{skill_name}」评估体系。{focus_line}
{kb_section}{code_section}{examples_section}

## 当前需求
- 功能模块：{module}
- 需求名称：{feature}
- 需求描述：{detail}
- 补充说明：{extra}

## 系统已有能力（据此判断新增/调整）
{caps_text}

## 功能拆解规则（补全遗漏功能点时参考）
{rules_text}

## 任务
1. 先整体理解需求范围，确定核心页面、关键按钮/操作和主要业务流程
2. 仅拆解到页面/按钮/业务动作层面，不写技术实现、数据库字段或接口细节
3. 对比「系统已有能力」判断每个页面是「新增」还是「调整」
4. 参考「功能拆解规则」补全遗漏的必要功能点（如列表页默认含查询/分页）
5. 先在脑海中推理整体范围，再输出最终 JSON

## 输出格式（严格 JSON 数组，禁止代码块）
[
  {{
    "页面": "页面名称",
    "类型": "新增",
    "功能点": ["功能点1（简明描述）", "功能点2"]
  }}
]

## 约束
- 页面数量：1~{max_pages} 个（按实际范围，不强制凑数）
- 每个页面功能点：2~{max_features} 个，每条不超过 30 字
- 类型只能是「新增」或「调整」
- 只输出 JSON 数组，不要任何其他内容"""


def _build_user_story_prompt(module, feature, detail, extra,
                              decomp, skill_name,
                              kb_section, code_section, examples_section,
                              caps_text) -> str:
    story_format  = decomp.get("story_format", "作为[角色]，我希望[做什么]，以便[获得价值]")
    max_stories   = decomp.get("max_stories", 10)
    focus         = decomp.get("focus", "")
    ac_note       = decomp.get("acceptance_criteria", "")

    focus_line = f"\n评估视角：{focus}" if focus else ""
    ac_line    = f"\n- 每个故事附上 1~2 条验收标准（acceptance_criteria）" if ac_note else ""
    return f"""你是一位资深敏捷教练，当前使用「{skill_name}」评估体系。{focus_line}
{kb_section}{code_section}{examples_section}

## 当前需求
- 功能模块：{module}
- 需求名称：{feature}
- 需求描述：{detail}
- 补充说明：{extra}

## 系统已有能力
{caps_text}

## 任务
将需求拆解为用户故事列表，每个故事格式：{story_format}
要求：
- 每个故事独立可交付，符合 INVEST 原则
- 区分「新增」或「调整」
{ac_line}

## 输出格式（严格 JSON 数组，禁止代码块）
[
  {{
    "故事": "作为[角色]，我希望[功能]，以便[价值]",
    "类型": "新增",
    "验收标准": ["标准1", "标准2"]
  }}
]

## 约束
- 故事数量：1~{max_stories} 个
- 类型只能是「新增」或「调整」
- 只输出 JSON 数组，不要任何其他内容"""


# ============================================================
# 解析
# ============================================================

def _parse(raw_text: str, strategy: str = "page_feature") -> list:
    text = re.sub(r'```(?:json)?\s*', '', raw_text).replace('```', '').strip()
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group())
        if not isinstance(data, list):
            return []

        if strategy == "user_story":
            return _parse_user_stories(data)
        return _parse_page_features(data)
    except (json.JSONDecodeError, ValueError):
        return []


def _parse_page_features(data: list) -> list:
    result = []
    for item in data:
        if not isinstance(item, dict):
            continue
        page  = str(item.get("页面", "")).strip()
        ptype = item.get("类型", "新增")
        fps   = item.get("功能点", [])
        if not page or not isinstance(fps, list):
            continue
        result.append({
            "页面":   page,
            "类型":   ptype if ptype in ("新增", "调整") else "新增",
            "功能点": [str(f).strip() for f in fps if str(f).strip()],
        })
    return result


def _parse_user_stories(data: list) -> list:
    """将用户故事格式统一适配为 pages_features 的 schema（页面→故事，功能点→验收标准）"""
    result = []
    for item in data:
        if not isinstance(item, dict):
            continue
        story = str(item.get("故事", "")).strip()
        ptype = item.get("类型", "新增")
        ac    = item.get("验收标准", [])
        if not story:
            continue
        result.append({
            "页面":   story,          # 复用 pages schema，页面字段存故事描述
            "类型":   ptype if ptype in ("新增", "调整") else "新增",
            "功能点": [str(a).strip() for a in ac if str(a).strip()] or ["完成上述用户故事"],
        })
    return result
