# -*- coding: utf-8 -*-
"""
节点2：工时估算
- 输入：节点1的 pages_features（功能点列表，含开发类型）+ 知识库参照案例
- B端履约中台专属：S/M/L/XL/XXL 五档 + 测试公式（后端×0.35）
- 输出：
    role_breakdown  — 各角色工时 dict
    total_days      — 合计天数
    g_column_text   — G 列标准格式文本（3张表+风险提示）
"""
import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from agent import gemini_client


def estimate_worktime(state: dict) -> dict:
    pages_features = state.get("pages_features", [])
    req            = state["raw_requirement"]
    model_id       = state.get("model_id")
    skill_config   = state.get("skill_config", {})
    examples       = state.get("skill_examples", [])
    kb_cases       = state.get("kb_cases", [])  # 知识库检索结果（Step 1）

    if not pages_features:
        return _fallback_estimate(state)

    skill_id = skill_config.get("id", "standard")
    print(f"[节点2] 工时估算 技能={skill_id} 功能点数={len(pages_features)}", flush=True)

    prompt = _build_prompt(req, pages_features, skill_config, examples, kb_cases)

    try:
        raw = gemini_client.call_llm(prompt, model_id=model_id)
        print(f"[节点2] LLM 返回 {len(raw)} 字符", flush=True)
        g_text, total_days, role_breakdown = _parse(raw, pages_features, skill_config, kb_cases)
    except Exception as e:
        errors = state.get("errors", [])
        errors.append(f"节点2异常: {e}")
        g_text, total_days, role_breakdown = _fallback_format(pages_features, skill_config, kb_cases)
        return {**state, "g_column_text": g_text, "total_days": total_days,
                "role_breakdown": role_breakdown, "errors": errors}

    return {**state, "g_column_text": g_text, "total_days": total_days, "role_breakdown": role_breakdown}


# ============================================================
# Prompt 构建
# ============================================================

def _build_prompt(req: dict, pages_features: list, skill_config: dict,
                  examples: list, kb_cases: list) -> str:
    module  = req.get("module", "") or ""
    feature = req.get("feature", "") or ""
    detail  = (req.get("detail", "") or "")[:300]

    skill      = skill_config or {}
    skill_id   = skill.get("id", "standard")
    skill_name = skill.get("name", "标准产品评估")
    roles      = skill.get("roles", ["产品/设计", "前端开发", "后端开发", "测试"])
    est        = skill.get("estimation", {})
    strategy   = est.get("strategy", "role_based")

    pages_text = json.dumps(pages_features, ensure_ascii=False, indent=2)

    if strategy == "story_points":
        rules_section = _build_story_point_rules(est, roles)
    elif skill_id == "b_end_fulfillment":
        rules_section = _build_b_end_rules(est, roles)
    else:
        rules_section = _build_role_based_rules(est, roles)

    examples_section = _build_examples_section(examples, roles)
    kb_section = _build_kb_section(kb_cases)

    roles_example = {r: 0.5 for r in roles}
    roles_example_str = json.dumps(roles_example, ensure_ascii=False)

    if skill_id == "b_end_fulfillment":
        return _build_b_end_prompt(
            module, feature, detail, pages_text, pages_features,
            rules_section, examples_section, kb_section, roles, roles_example_str
        )

    return f"""你是 IT 产品经理，当前使用「{skill_name}」评估体系，根据页面/功能点拆解结果，估算各角色工时。
{examples_section}
## 需求背景
- 功能模块：{module}
- 需求名称：{feature}
- 需求描述：{detail or '无'}

## 页面与功能点拆解结果
{pages_text}

{rules_section}

## 输出角色
{"、".join(roles)}

## 输出格式（严格 JSON，禁止代码块）
{{
  "role_breakdown": {roles_example_str},
  "total_days": 2.0,
  "g_text": "【页面名-新增】功能点1、功能点2\\n【页面名2-调整】功能点3\\n\\n各角色工时：产品/设计0.5天 前端1.0天 后端1.0天 测试0.5天\\n合计工时：2.0天",
  "reason": "一句话说明估算依据"
}}

## G 列文本格式规则
- 每页面/故事一行：【名称-新增/调整】功能点1、功能点2、...
- 末尾空一行后：各角色工时：角色1 X天 角色2 X天 ...
- 最后一行：合计工时：X天（X 精确到 0.5）
- 换行用 \\n，不要其他格式
- 只输出 JSON，不要任何其他内容"""


def _build_b_end_prompt(module, feature, detail, pages_text, pages_features,
                         rules_section, examples_section, kb_section, roles, roles_example_str) -> str:
    """B端履约中台专属 prompt：输出3张表 + 风险提示"""
    role_names = "、".join(roles)
    zero_patterns = "复用现有功能/链路 | 已有功能无改造 | 标品支持不涉及定制"
    return f"""你是资深B端履约中台产品经理，基于功能点拆解结果，完成三步评估输出。
{kb_section}{examples_section}
## 需求背景
- 功能模块：{module or '履约中台'}
- 需求名称：{feature}
- 需求描述：{detail or '无'}

## 已拆解功能点
{pages_text}

{rules_section}

## 不计工时的情形（工时全部为0）
若功能点描述含以下关键词：{zero_patterns}，该行四端工时均填 0。

## 输出格式（严格 JSON，禁止代码块）
{{
  "role_breakdown": {roles_example_str},
  "total_days": 6.0,
  "g_text": "参照案例表\\n功能点拆解表\\n工时评估表\\n风险提示",
  "feature_rows": [
    {{
      "id": 1,
      "name": "功能点名称",
      "dev_type": "完全新增",
      "complexity_reason": "复杂度判断依据",
      "产品": 1.0,
      "前端": 1.0,
      "后端": 3.0,
      "测试": 1.0,
      "subtotal": 6.0,
      "ref": "参照案例ID或推算依据",
      "confidence": "normal"
    }}
  ],
  "reason": "一句话说明整体估算逻辑"
}}

## G列文本格式（g_text字段内容）
按以下格式拼接，用\\n换行：

1) 参照案例行（若有）：
【参照案例】案例ID | 场景 | 开发类型 | 产品X天 前端X天 后端X天 测试X天 合计X天

2) 功能点拆解表：
【功能点拆解】
序号. 功能点名称 | 开发类型 | 复杂度判断依据

3) 工时评估表：
【工时评估】
序号. 功能点 | 产品X | 前端X | 后端X | 测试X | 小计X | 评估依据（⚠️建议评审确认 或 ❓建议需求评审后重新估算）

4) 合计行：
合计 | 产品X天 | 前端X天 | 后端X天 | 测试X天 | 总计X天

5) 风险提示：
⚠️评估说明：本评估基于历史项目数据推算，建议±20%浮动区间。业务联调工时已折算在各端内。涉及第三方接口对接，建议接口文档确认后由研发复核后端工时。最终报价建议由产研主导完成工时对齐会。

## 注意事项
- total_days = sum(feature_rows的subtotal)，精确到0.5
- 测试工时 ≈ 后端工时 × 0.35，参照：后端≤2天→测试0.5天；2.5-3.5天→1天；4-4.5天→1.5天；5-6天→2天；7-8天→3天
- confidence字段：有直接参照案例填"normal"，类似场景推算填"review"，全新领域填"uncertain"
- 只输出 JSON，不要任何其他内容"""


# ============================================================
# 规则构建
# ============================================================

def _build_b_end_rules(est: dict, roles: list) -> str:
    tier_rules = est.get("tier_rules", {})
    bonuses    = est.get("complexity_bonuses", {})

    lines = ["## B端履约中台工时估算规则"]

    lines.append("\n### 产品工时等级")
    lines.append("| 等级 | 工时 | 触发条件 |")
    lines.append("|------|------|---------|")
    lines.append("| S | 0.5天 | 单接口说明/单配置项追加/字段扩展说明 |")
    lines.append("| M | 1天 | 标准增删改查配置表（字段10-15）/接口+单页面 |")
    lines.append("| L | 1.5-2天 | 2-3个页面/含导出+导入/含数据同步逻辑 |")
    lines.append("| XL | 3天 | 含业务规则执行+通知/跨系统联动/完整业务流程 |")
    lines.append("| XXL | 4-5天 | 全新子系统（5+页面）/可视化规则配置器/复杂报表2个+ |")

    lines.append("\n### 后端工时等级")
    lines.append("| 等级 | 工时 | 触发条件 |")
    lines.append("|------|------|---------|")
    lines.append("| S | 0.5-1.5天 | 单接口字段改造/简单查询接口（字段<10） |")
    lines.append("| M | 2-3天 | 1-2个标准CRUD接口组（含表设计+权限+日志） |")
    lines.append("| L | 4-6天 | 3-5个接口+业务逻辑/含数据同步链路 |")
    lines.append("| XL | 7-9天 | 完整功能模块（配置+执行+通知）/含规则引擎 |")
    lines.append("| XXL | 10-16天 | 跨系统全链路/含状态机+异步+重试+多系统联调 |")

    lines.append("\n### 前端工时等级")
    lines.append("| 等级 | 工时 | 触发条件 |")
    lines.append("|------|------|---------|")
    lines.append("| 0天 | 0天 | 纯后端接口，无页面 |")
    lines.append("| S | 0.5天 | 纯展示只读页/已有页面追加字段或按钮 |")
    lines.append("| M | 1天 | 标准CRUD单页（字段10-15，含弹窗表单） |")
    lines.append("| L | 1.5天 | 复杂查询列表（查询条件10+）/2个标准页面 |")
    lines.append("| XL | 2-3天 | 3-4个页面含联动/含图表报表 |")
    lines.append("| XXL | 4-5天 | 5+页面/可视化规则配置器/含移动端独立体系 |")

    lines.append("\n### 测试工时公式：后端工时 × 0.35，向上取整到0.5天粒度")

    lines.append("\n### 后端加分项（叠加）")
    lines.append("- 跨系统对接（每个外部系统如ERP/WMS/云商/京东）：+2-3天")
    lines.append("- 含异步处理/消息队列/定时任务：+1-2天")
    lines.append("- 含业务规则匹配逻辑（命中→执行→通知）：+2-3天")
    lines.append("- 含报表数据加工（字段计算/多表关联）：+2天/报表")
    lines.append("- 含幂等/分布式一致性处理：+0.5-1天")
    lines.append("- 含大批量导出（10W+行）：+1天")

    return "\n".join(lines)


def _build_role_based_rules(est: dict, roles: list) -> str:
    base_rates = est.get("base_rates", {})
    bonuses    = est.get("complexity_bonuses", {})

    lines = ["## 工时估算规则（按角色）"]
    if base_rates:
        lines.append("### 基础工时参考（天/页面）")
        for level, rates in base_rates.items():
            r_str = " ".join(f"{role}={v}天" for role, v in rates.items() if role in roles)
            lines.append(f"- {level}：{r_str}")
    else:
        lines.append("- 新增页面（简单）：前端 0.5天，后端 0.3天，测试 0.3天")
        lines.append("- 新增页面（中等）：前端 1.0天，后端 0.8天，测试 0.5天")
        lines.append("- 新增页面（复杂）：前端 1.5天，后端 1.5天，测试 1.0天")
        lines.append("- 调整页面：约为新增页面的 30%~50%")

    if bonuses:
        lines.append("### 复杂度加成（各角色均加）")
        for name, info in bonuses.items():
            if isinstance(info, dict):
                lines.append(f"- {name}：+{info.get('加成天数', 0.2)}天（{info.get('说明', '')}）")
            else:
                lines.append(f"- {name}：+{info}天")

    lines.append("### 估算原则")
    lines.append("- total_days 精确到 0.5，范围 0.5~20 天")
    lines.append("- total_days = sum(role_breakdown.values())")
    lines.append("- 先判断页面复杂度（简单/中等/复杂），再套用基础工时+加成")
    return "\n".join(lines)


def _build_story_point_rules(est: dict, roles: list) -> str:
    point_scale    = est.get("point_scale", [1, 2, 3, 5, 8, 13])
    days_per_point = est.get("days_per_point", 0.8)
    role_ratios    = est.get("role_ratios", {})
    guidance       = est.get("point_guidance", {})

    lines = ["## 工时估算规则（故事点）"]
    lines.append(f"- 故事点范围：{point_scale}")
    lines.append(f"- 每故事点 = {days_per_point} 天")
    if guidance:
        lines.append("### 故事点参考")
        for pt, desc in guidance.items():
            lines.append(f"  - {pt}点：{desc}")
    if role_ratios:
        lines.append("### 角色工时分配比例")
        for role, ratio in role_ratios.items():
            if role in roles:
                lines.append(f"  - {role}：{int(ratio*100)}%")
    lines.append("- total_days = sum(所有故事点) × days_per_point，精确到 0.5")
    return "\n".join(lines)


def _build_examples_section(examples: list, roles: list) -> str:
    if not examples:
        return ""
    parts = ["## 历史工时参考案例"]
    for i, ex in enumerate(examples[:2], 1):
        req_info = ex.get("requirement", {})
        worktime = ex.get("worktime", {})
        if not worktime or not req_info:
            continue
        rb    = worktime.get("role_breakdown", {})
        total = worktime.get("total_days", "?")
        note  = worktime.get("note", "")
        rb_str = " ".join(f"{r}={rb.get(r,'?')}天" for r in roles if r in rb)
        parts.append(f"\n案例{i}：{req_info.get('feature','')} — {rb_str} 合计{total}天" +
                     (f"（实际{worktime.get('actual_days','?')}天，{note}）" if note else ""))
    return "\n".join(parts) if len(parts) > 1 else ""


def _build_kb_section(kb_cases: list) -> str:
    """将知识库检索结果格式化为 prompt section"""
    if not kb_cases:
        return "⚠️ 未找到直接参照案例，以下工时基于评估规则推算\n\n"
    lines = ["## 🔍 知识库参照案例（优先参考）"]
    for case in kb_cases:
        h = case.get("hours", {})
        prod = h.get("product", "?")
        fe   = h.get("frontend", "?")
        be   = h.get("backend", "?")
        test = h.get("test", "?")
        total = h.get("total", "?")
        lines.append(
            f"- [{case.get('id','')}] {case.get('scenario','')} | {case.get('dev_type','')} | "
            f"产品{prod}天 前端{fe}天 后端{be}天 测试{test}天 合计{total}天"
        )
    return "\n".join(lines) + "\n\n"


# ============================================================
# 解析
# ============================================================

def _parse(raw_text: str, pages_features: list, skill_config: dict, kb_cases: list):
    """返回 (g_text, total_days, role_breakdown)"""
    text = re.sub(r'```(?:json)?\s*', '', raw_text).replace('```', '').strip()
    skill_id = (skill_config or {}).get("id", "standard")
    try:
        data = json.loads(text)

        rb = data.get("role_breakdown", {})
        role_breakdown = {k: float(v) for k, v in rb.items() if isinstance(v, (int, float, str))}

        total_days = float(data.get("total_days", sum(role_breakdown.values()) or 1.0))
        total_days = _round_half(total_days)
        total_days = max(0.5, min(total_days, 50.0))

        g_text = str(data.get("g_text", "")).replace("\\n", "\n").strip()
        if not g_text:
            feature_rows = data.get("feature_rows", [])
            if skill_id == "b_end_fulfillment" and feature_rows:
                g_text = _format_b_end(feature_rows, role_breakdown, total_days, kb_cases)
            else:
                g_text = _format_fallback(pages_features, role_breakdown, total_days, skill_config)

        return g_text, total_days, role_breakdown
    except (json.JSONDecodeError, ValueError, KeyError):
        g_text, total_days, role_breakdown = _fallback_format(pages_features, skill_config, kb_cases)
        return g_text, total_days, role_breakdown


def _format_b_end(feature_rows: list, role_breakdown: dict, total_days: float, kb_cases: list) -> str:
    """从 feature_rows 生成 B端3表格式文本"""
    lines = []

    # 参照案例表
    if kb_cases:
        lines.append("【参照案例】")
        for case in kb_cases:
            h = case.get("hours", {})
            lines.append(
                f"{case.get('id','')} | {case.get('scenario','')} | {case.get('dev_type','')} | "
                f"产品{h.get('product','?')}天 前端{h.get('frontend','?')}天 "
                f"后端{h.get('backend','?')}天 测试{h.get('test','?')}天 "
                f"合计{h.get('total','?')}天"
            )
        lines.append("")

    # 功能点拆解表
    lines.append("【功能点拆解】")
    for row in feature_rows:
        lines.append(f"{row.get('id','')}.  {row.get('name','')} | {row.get('dev_type','')} | {row.get('complexity_reason','')}")
    lines.append("")

    # 工时评估表
    lines.append("【工时评估】")
    confidence_map = {"review": "⚠️建议评审确认", "uncertain": "❓建议需求评审后重新估算"}
    for row in feature_rows:
        conf_tag = confidence_map.get(row.get("confidence", ""), "")
        ref = row.get("ref", "")
        note = f"{ref} {conf_tag}".strip()
        lines.append(
            f"{row.get('id','')}.  {row.get('name','')} | "
            f"产品{row.get('产品',0)} | 前端{row.get('前端',0)} | "
            f"后端{row.get('后端',0)} | 测试{row.get('测试',0)} | "
            f"小计{row.get('subtotal',0)} | {note}"
        )

    # 合计行
    rb_str = " ".join(f"{r}{v}天" for r, v in role_breakdown.items())
    lines.append(f"合计 | {rb_str} | 总计{total_days}天")
    lines.append("")

    # 风险提示
    lines.append("⚠️评估说明：本评估基于历史项目数据推算，建议±20%浮动区间。"
                 "业务联调工时已折算在各端内。涉及第三方接口对接，建议接口文档确认后由研发复核后端工时。"
                 "最终报价建议由产研主导完成工时对齐会。")
    return "\n".join(lines)


def _round_half(x: float) -> float:
    return round(x * 2) / 2


def _format_fallback(pages_features: list, role_breakdown: dict, total_days: float, skill_config: dict) -> str:
    lines = []
    for p in pages_features:
        page  = p.get("页面", "")
        ptype = p.get("类型", "新增")
        fps   = "、".join(p.get("功能点", []))
        lines.append(f"【{page}-{ptype}】{fps}")

    if role_breakdown:
        lines.append("")
        rb_str = " ".join(f"{r} {v}天" for r, v in role_breakdown.items())
        lines.append(f"各角色工时：{rb_str}")
    lines.append(f"合计工时：{total_days}天")
    return "\n".join(lines)


def _fallback_format(pages_features: list, skill_config: dict, kb_cases: list = None):
    roles = (skill_config or {}).get("roles", ["产品/设计", "前端开发", "后端开发", "测试"])
    total_days = max(0.5, len(pages_features) * 1.0)
    total_days = _round_half(total_days)

    role_breakdown = {r: _round_half(total_days / len(roles)) for r in roles}
    g_text = _format_fallback(pages_features, role_breakdown, total_days, skill_config)
    return g_text, total_days, role_breakdown


# ============================================================
# 降级：pages_features 为空时走原始单次估算
# ============================================================

def _fallback_estimate(state: dict) -> dict:
    req      = state["raw_requirement"]
    model_id = state.get("model_id")
    prompt   = gemini_client.build_prompt(req)
    skill_config = state.get("skill_config", {})
    roles = skill_config.get("roles", ["产品/设计", "前端开发", "后端开发", "测试"])

    try:
        raw    = gemini_client.call_llm(prompt, model_id=model_id)
        parsed = gemini_client.parse_response(raw)
        total  = _round_half(parsed["days"])
        role_breakdown = {r: _round_half(total / len(roles)) for r in roles}
        rb_str = " ".join(f"{r} {v}天" for r, v in role_breakdown.items())
        g_text = parsed["work_breakdown"] + f"\n\n各角色工时：{rb_str}\n合计工时：{total}天"
        return {**state, "g_column_text": g_text, "total_days": total, "role_breakdown": role_breakdown}
    except Exception as e:
        errors = state.get("errors", [])
        errors.append(f"降级估算失败: {e}")
        return {**state, "g_column_text": "工时评估失败", "total_days": 1.0,
                "role_breakdown": {}, "errors": errors}
