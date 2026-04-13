# -*- coding: utf-8 -*-
"""
节点2：工时估算
- 输入：节点1的 pages_features（完整，不裁剪字段）
- 输出：G列标准格式文本 + N列工时天数
- G列格式：【页面-类型】功能点1、功能点2\n产品工时X天
"""
import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from agent import gemini_client


def estimate_worktime(state: dict) -> dict:
    pages_features = state.get("pages_features", [])
    req    = state["raw_requirement"]
    model_id = state.get("model_id")

    if not pages_features:
        return _fallback_estimate(state)

    print(f"[节点2] 工时估算 页面数={len(pages_features)}", flush=True)

    prompt = _build_prompt(req, pages_features)

    try:
        raw = gemini_client.call_llm(prompt, model_id=model_id)
        print(f"[节点2] LLM 返回 {len(raw)} 字符", flush=True)
        g_text, total_days = _parse(raw, pages_features)
    except Exception as e:
        errors = state.get("errors", [])
        errors.append(f"节点2异常: {e}")
        g_text     = _format_fallback(pages_features)
        total_days = 1.0
        return {**state, "g_column_text": g_text, "total_days": total_days, "errors": errors}

    return {**state, "g_column_text": g_text, "total_days": total_days}


def _build_prompt(req: dict, pages_features: list) -> str:
    module  = req.get("module", "") or ""
    feature = req.get("feature", "") or ""
    detail  = req.get("detail", "") or ""

    pages_text = json.dumps(pages_features, ensure_ascii=False, indent=2)

    return f"""你是IT产品经理，根据页面和功能点拆解结果，估算产品工时并生成标准格式输出。

## 需求背景
- 功能模块：{module}
- 需求名称：{feature}
- 需求描述：{detail[:200] if detail else '无'}

## 页面与功能点拆解结果
{pages_text}

## 工时估算规则
- 新增页面：0.5~1天；调整页面：0.2~0.5天
- 简单功能（单一逻辑）：0.1~0.3天；复杂功能（多状态/外部接口）：0.5~1天
- 审批流加0.3天，外部接口加0.3天，批量操作加0.2天
- 总工时精确到0.5天，范围0.5~10天

## 输出格式（严格JSON，禁止代码块）
{{
  "g_text": "【调拨单创建页-新增】创建表单（调出仓/调入仓/SKU/数量）、必填校验、提交确认\\n【调拨单列表页-调整】新增状态筛选、批量导出\\n产品工时2天",
  "total_days": 2.0
}}

## G列文本格式规则
- 每页面一行：【页面名-新增/调整】功能点1、功能点2、...
- 最后一行：产品工时X天（X为合计，精确到0.5）
- 换行用\\n，不要其他格式
- 只输出JSON，不要任何其他内容"""


def _parse(raw_text: str, pages_features: list):
    text = re.sub(r'```(?:json)?\s*', '', raw_text).replace('```', '').strip()
    try:
        data = json.loads(text)
        g_text     = str(data.get("g_text", "")).replace("\\n", "\n").strip()
        total_days = float(data.get("total_days", 1.0))
        total_days = round(total_days * 2) / 2
        total_days = max(0.5, min(total_days, 10.0))

        # 兜底：若 g_text 为空则用格式化降级
        if not g_text:
            g_text = _format_fallback(pages_features, total_days)
        return g_text, total_days
    except (json.JSONDecodeError, ValueError, KeyError):
        return _format_fallback(pages_features), 1.0


def _format_fallback(pages_features: list, total_days: float = 1.0) -> str:
    """LLM 解析失败时的降级格式化"""
    lines = []
    for p in pages_features:
        page  = p.get("页面", "")
        ptype = p.get("类型", "新增")
        fps   = "、".join(p.get("功能点", []))
        lines.append(f"【{page}-{ptype}】{fps}")
    lines.append(f"产品工时{total_days}天")
    return "\n".join(lines)


def _fallback_estimate(state: dict) -> dict:
    """pages_features 为空时降级为原始单次估算"""
    req      = state["raw_requirement"]
    model_id = state.get("model_id")
    prompt   = gemini_client.build_prompt(req)
    try:
        raw    = gemini_client.call_llm(prompt, model_id=model_id)
        parsed = gemini_client.parse_response(raw)
        g_text = parsed["work_breakdown"] + f"\n产品工时{parsed['days']}天"
        return {**state, "g_column_text": g_text, "total_days": parsed["days"]}
    except Exception as e:
        errors = state.get("errors", [])
        errors.append(f"降级估算失败: {e}")
        return {**state, "g_column_text": "工时评估失败", "total_days": 1.0, "errors": errors}
