# -*- coding: utf-8 -*-
"""
节点1：需求拆解为「页面 × 功能点」结构
- 按页面维度组织功能点
- 参考 system_caps 判断新增/调整
- 参考 feature_rules 补全遗漏的标准功能点
- 命中业务知识库时注入领域上下文
"""
import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from agent import gemini_client
from agent.kb_utils import match_business_context


def rebuild_features(state: dict) -> dict:
    req = state["raw_requirement"]
    kb_feature_rules = state.get("kb_feature_rules", {})
    kb_system_caps   = state.get("kb_system_caps", {})
    retry_count      = state.get("retry_count", 0)
    model_id         = state.get("model_id")

    business_context = match_business_context(req, state.get("kb_business_docs", []))
    if business_context:
        print(f"[节点1] 命中业务知识库，注入上下文", flush=True)

    prompt = _build_prompt(req, kb_feature_rules, kb_system_caps, business_context)
    print(f"[节点1] 拆解页面×功能点 retry={retry_count} feature={req.get('feature','')[:30]}", flush=True)

    try:
        raw = gemini_client.call_llm(prompt, model_id=model_id)
        print(f"[节点1] LLM 返回 {len(raw)} 字符", flush=True)
        pages_features = _parse(raw)
    except Exception as e:
        errors = state.get("errors", [])
        errors.append(f"节点1异常: {e}")
        return {**state, "pages_features": [], "errors": errors, "retry_count": retry_count + 1}

    if not pages_features:
        return {**state, "pages_features": [], "retry_count": retry_count + 1}

    print(f"[节点1] 输出 {len(pages_features)} 个页面", flush=True)
    return {**state, "pages_features": pages_features, "retry_count": retry_count}


def _build_prompt(req: dict, feature_rules: dict, system_caps: dict, business_context: str = "") -> str:
    module  = req.get("module", "") or ""
    feature = req.get("feature", "") or ""
    detail  = req.get("detail", "") or ""
    extra   = req.get("extra", "") or ""

    rules_text = json.dumps(feature_rules, ensure_ascii=False, indent=2)
    caps_text  = json.dumps(system_caps,   ensure_ascii=False, indent=2)

    kb_section = f"\n## 业务领域知识（优先参考）\n{business_context}\n" if business_context else ""

    return f"""你是一位有10年经验的IT产品经理，负责将业务需求拆解为页面和功能点。{kb_section}

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
1. 将该需求拆解为涉及的所有页面，每个页面列出具体功能点
2. 对比「系统已有能力」判断每个页面是「新增」还是「调整」
3. 参考「功能拆解规则」，补全用户描述中遗漏的必要功能点（如列表页默认含查询/分页）

## 输出格式（严格JSON数组，禁止代码块）
[
  {{
    "页面": "页面名称",
    "类型": "新增",
    "功能点": ["功能点1（简明描述）", "功能点2", "功能点3"]
  }}
]

## 约束
- 页面数量：1~5个
- 每个页面功能点：2~8个，每条不超过30字
- 类型只能是「新增」或「调整」
- 只输出JSON数组，不要任何其他内容"""


def _parse(raw_text: str) -> list:
    text = re.sub(r'```(?:json)?\s*', '', raw_text).replace('```', '').strip()
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group())
        if not isinstance(data, list):
            return []
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
                "页面": page,
                "类型": ptype if ptype in ("新增", "调整") else "新增",
                "功能点": [str(f).strip() for f in fps if str(f).strip()],
            })
        return result
    except (json.JSONDecodeError, ValueError):
        return []
