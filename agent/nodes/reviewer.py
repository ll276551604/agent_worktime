# -*- coding: utf-8 -*-
"""
节点3：需求评审
- 完整性检查
- 歧义识别
- 风险标注
"""
import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from agent import gemini_client


def review_requirement(state: dict) -> dict:
    req = state["raw_requirement"]
    feature_points = state.get("feature_points", [])
    worktime_breakdown = state.get("worktime_breakdown", [])
    total_days = state.get("total_days", 0)
    model_id = state.get("model_id")

    prompt = _build_prompt(req, feature_points, worktime_breakdown, total_days)
    print(f"[节点3] 评审", flush=True)

    try:
        raw = gemini_client.call_llm(prompt, model_id=model_id)
        print(f"[节点3] LLM 返回 {len(raw)} 字符", flush=True)
        review = _parse_review(raw)
    except Exception as e:
        errors = state.get("errors", [])
        errors.append(f"节点3(评审)异常: {e}")
        review = {"完整性": "未知", "问题点": [], "风险": [], "建议": []}
        return {**state, "review": review, "errors": errors}

    return {**state, "review": review}


def _build_prompt(req: dict, feature_points: list, worktime_breakdown: list, total_days: float) -> str:
    module  = req.get("module", "") or ""
    feature = req.get("feature", "") or ""
    detail  = req.get("detail", "") or ""
    extra   = req.get("extra", "") or ""

    fp_text = json.dumps(feature_points, ensure_ascii=False, indent=2)
    wt_text = f"总工时 {total_days} 天"

    return f"""你是一位有10年经验的IT产品经理，擅长评审需求文档质量。

## 原始需求
- 功能模块：{module}
- 需求名称：{feature}
- 需求描述：{detail}
- 补充说明：{extra}

## 已拆解功能点
{fp_text}

## 工时评估结果
{wt_text}

## 任务
对该需求进行评审，输出评审结论。

## 输出格式（严格JSON，不要加任何代码块标记）
{{
  "完整性": "高",
  "问题点": [
    "需求描述中未说明XXX的处理逻辑"
  ],
  "风险": [
    "依赖第三方接口，需提前确认接口文档"
  ],
  "建议": [
    "建议补充边界条件说明"
  ]
}}

## 评审维度说明
- 完整性：高/中/低，判断需求是否足够清晰可实现
- 问题点：需求描述中存在的歧义、缺失、矛盾
- 风险：可能影响排期或质量的因素（技术风险/依赖风险/业务风险）
- 建议：可选的优化建议

## 约束
- 完整性只能是"高"、"中"、"低"之一
- 问题点和风险各最多3条，无则返回空数组
- 只输出JSON，不要任何其他内容"""


def _parse_review(raw_text: str) -> dict:
    text = re.sub(r'```(?:json)?\s*', '', raw_text).replace('```', '').strip()

    try:
        data = json.loads(text)
        completeness = data.get("完整性", "中")
        if completeness not in ("高", "中", "低"):
            completeness = "中"
        return {
            "完整性": completeness,
            "问题点": [str(p) for p in data.get("问题点", [])],
            "风险":   [str(r) for r in data.get("风险", [])],
            "建议":   [str(s) for s in data.get("建议", [])],
        }
    except (json.JSONDecodeError, ValueError):
        return {"完整性": "中", "问题点": [], "风险": [], "建议": []}
