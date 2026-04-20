# -*- coding: utf-8 -*-
import json
import re
import time
import logging
import os
import ssl
import certifi
import httpx
from openai import OpenAI
from config import AVAILABLE_MODELS, API_KEYS, DEFAULT_MODEL, MAX_RETRIES

# 禁用代理，避免连接问题
for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
    os.environ.pop(key, None)

# 设置SSL证书路径
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

logger = logging.getLogger(__name__)


def _get_model_config(model_id: str) -> dict:
    for m in AVAILABLE_MODELS:
        if m["id"] == model_id:
            return m
    raise ValueError(f"未知模型：{model_id}，可选：{[m['id'] for m in AVAILABLE_MODELS]}")


def call_llm(prompt, model_id: str = None) -> str:
    """调用 LLM，根据 model_id 自动选择 provider 和 API Key，含指数退避重试。"""
    model_id = model_id or DEFAULT_MODEL
    cfg = _get_model_config(model_id)

    api_key = API_KEYS.get(cfg["provider"], "")
    if not api_key:
        raise Exception(f"未配置 {cfg['provider']} API Key")

    # 创建httpx客户端，强制禁用代理
    http_client = httpx.Client(
        timeout=60.0,
        proxy=None,  # 强制禁用代理
        trust_env=False,  # 不信任环境变量中的代理设置
        follow_redirects=True
    )
    
    client = OpenAI(
        api_key=api_key,
        base_url=cfg["base_url"],
        timeout=60,  # 60秒超时
        max_retries=0,  # 由外层处理重试
        http_client=http_client
    )
    last_exc = None

    if isinstance(prompt, list):
        messages = prompt
        prompt_length = len(json.dumps(prompt, ensure_ascii=False))
    else:
        messages = [{"role": "user", "content": prompt}]
        prompt_length = len(prompt)

    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"LLM 请求: model={model_id}, attempt={attempt+1}/{MAX_RETRIES}, prompt_length={prompt_length}")
            response = client.chat.completions.create(
                model=model_id,
                messages=messages,
                temperature=0.3,
                max_tokens=2048,
                timeout=60,
            )
            content = response.choices[0].message.content
            logger.debug(f"LLM 响应: length={len(content)}")
            return content
        except Exception as e:
            last_exc = e
            logger.warning(f"LLM 调用失败 attempt={attempt+1}: {e}")
            if attempt < MAX_RETRIES - 1:
                wait_time = 2 ** attempt
                logger.info(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)

    raise Exception(f"LLM调用失败: {last_exc}")


def _simulate_llm(prompt: str, model_id: str = None) -> str:
    """在无法调用模型时，提供简单的本地模拟结果。"""
    if '功能拆解规则' in prompt and '页面与功能点拆解结果' in prompt:
        return _simulate_page_feature_response(prompt)
    if 'role_breakdown' in prompt and 'total_days' in prompt and 'g_text' in prompt:
        return _simulate_worktime_response(prompt)
    if 'work_breakdown' in prompt and 'days' in prompt:
        return _simulate_work_breakdown_response(prompt)
    return _simulate_work_breakdown_response(prompt)


def _extract_requirement_info(prompt: str) -> dict:
    info = {}
    patterns = {
        'module': r'- 功能模块：([^\n]*)',
        'feature': r'- 需求名称：([^\n]*)',
        'detail': r'- 需求描述：([^\n]*)',
        'extra': r'- 补充说明：([^\n]*)',
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, prompt)
        info[key] = match.group(1).strip() if match else ''
    return info


def _normalize_text(text: str) -> str:
    return text.replace('“', '"').replace('”', '"').strip()


def _build_basic_features(feature: str, detail: str) -> list:
    page = feature or detail.split('。')[0][:10] or '需求页面'
    page_name = page.strip() or '需求页面'
    points = ['分析需求背景', '设计实现方案', '实施开发与测试']

    if any(k in detail for k in ['登录', '注册', '帐号', '账户', '认证']):
        points = ['设计登录流程', '实现认证逻辑', '前端页面交互', '测试登录流程']
    elif any(k in detail for k in ['订单', '支付', '退款', '发货']):
        points = ['设计订单流程', '实现订单交互', '接口对接', '测试订单流程']
    elif any(k in detail for k in ['导出', 'Excel', '文件']):
        points = ['设计导出格式', '实现导出功能', '生成文件并下载', '测试导出结果']
    elif any(k in detail for k in ['接口', 'API', '对接']):
        points = ['设计接口规范', '实现接口开发', '联调测试', '编写文档']

    return [{
        '页面': page_name,
        '类型': '调整' if any(k in detail for k in ['修复', '错误', '异常', '问题', '优化']) else '新增',
        '功能点': points,
    }]


def _simulate_page_feature_response(prompt: str) -> str:
    info = _extract_requirement_info(prompt)
    features = _build_basic_features(info.get('feature', ''), info.get('detail', ''))
    return json.dumps(features, ensure_ascii=False)


def _simulate_worktime_response(prompt: str) -> str:
    req_info = _extract_requirement_info(prompt)
    pages = re.search(r'\[.*\]', prompt, re.DOTALL)
    try:
        pages_data = json.loads(pages.group()) if pages else []
    except Exception:
        pages_data = []

    if not isinstance(pages_data, list):
        pages_data = []

    total_points = 0
    total_pages = len(pages_data)
    for p in pages_data:
        total_points += len(p.get('功能点', [])) if isinstance(p.get('功能点', []), list) else 0
    total_points = max(total_points, 3)
    total_days = _round_half(0.5 + total_pages * 0.7 + total_points * 0.15)
    if total_days < 0.5:
        total_days = 0.5

    roles = ['产品/设计', '前端开发', '后端开发', '测试']
    per_role = _round_half(total_days / len(roles))
    role_breakdown = {r: per_role for r in roles}
    g_lines = []
    for p in pages_data:
        page = p.get('页面', '需求页面')
        ptype = p.get('类型', '新增')
        fps = '、'.join(p.get('功能点', [])) if isinstance(p.get('功能点', []), list) else ''
        g_lines.append(f"【{page}-{ptype}】{fps}")
    g_text = '\n'.join(g_lines)
    g_text += f"\n\n各角色工时：{' '.join([f'{r}{v}天' for r,v in role_breakdown.items()])}\n合计工时：{total_days}天"

    return json.dumps({
        'role_breakdown': role_breakdown,
        'total_days': total_days,
        'g_text': g_text,
    }, ensure_ascii=False)


def _simulate_work_breakdown_response(prompt: str) -> str:
    info = _extract_requirement_info(prompt)
    feature = info.get('feature') or '需求'
    detail = info.get('detail') or ''
    if '修复' in detail or 'bug' in detail.lower() or '异常' in detail:
        days = 1.0
    else:
        days = 1.5 if len(detail) > 80 else 1.0
    days = _round_half(days)
    breakdown = [
        f'分析需求：理解「{feature}」的业务场景',
        '设计实现方案',
        '开发实现与验证',
    ]
    if len(detail) > 80:
        breakdown.append('补充详细测试与验收')
    work_breakdown = '\n'.join(f'{i+1}. {line}' for i, line in enumerate(breakdown))
    return json.dumps({
        'work_breakdown': work_breakdown,
        'days': days,
        'reason': '本地规则估算，输入长度和关键词决定工作量',
    }, ensure_ascii=False)


def _round_half(x: float) -> float:
    return round(x * 2) / 2
    logger.warning(f"LLM 调用最终失败，启用本地降级模拟结果: {last_exc}")
    return _simulate_llm(prompt, model_id)


def _simulate_llm(prompt: str, model_id: str = None) -> str:
    """在无法调用模型时，提供简单的本地模拟结果。"""
    if '功能拆解规则' in prompt and '页面与功能点拆解结果' in prompt:
        return _simulate_page_feature_response(prompt)
    if 'role_breakdown' in prompt and 'total_days' in prompt and 'g_text' in prompt:
        return _simulate_worktime_response(prompt)
    if 'work_breakdown' in prompt and 'days' in prompt:
        return _simulate_work_breakdown_response(prompt)
    return _simulate_work_breakdown_response(prompt)


def _extract_requirement_info(prompt: str) -> dict:
    info = {}
    patterns = {
        'module': r'- 功能模块：([^\n]*)',
        'feature': r'- 需求名称：([^\n]*)',
        'detail': r'- 需求描述：([^\n]*)',
        'extra': r'- 补充说明：([^\n]*)',
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, prompt)
        info[key] = match.group(1).strip() if match else ''
    return info


def _normalize_text(text: str) -> str:
    return text.replace('“', '"').replace('”', '"').strip()


def _build_basic_features(feature: str, detail: str) -> list:
    page = feature or detail.split('。')[0][:10] or '需求页面'
    page_name = page.strip() or '需求页面'
    points = ['分析需求背景', '设计实现方案', '实施开发与测试']

    if any(k in detail for k in ['登录', '注册', '帐号', '账户', '认证']):
        points = ['设计登录流程', '实现认证逻辑', '前端页面交互', '测试登录流程']
    elif any(k in detail for k in ['订单', '支付', '退款', '发货']):
        points = ['设计订单流程', '实现订单交互', '接口对接', '测试订单流程']
    elif any(k in detail for k in ['导出', 'Excel', '文件']):
        points = ['设计导出格式', '实现导出功能', '生成文件并下载', '测试导出结果']
    elif any(k in detail for k in ['接口', 'API', '对接']):
        points = ['设计接口规范', '实现接口开发', '联调测试', '编写文档']

    return [{
        '页面': page_name,
        '类型': '调整' if any(k in detail for k in ['修复', '错误', '异常', '问题', '优化']) else '新增',
        '功能点': points,
    }]


def _simulate_page_feature_response(prompt: str) -> str:
    info = _extract_requirement_info(prompt)
    features = _build_basic_features(info.get('feature', ''), info.get('detail', ''))
    return json.dumps(features, ensure_ascii=False)


def _simulate_worktime_response(prompt: str) -> str:
    req_info = _extract_requirement_info(prompt)
    pages = re.search(r'\[.*\]', prompt, re.DOTALL)
    try:
        pages_data = json.loads(pages.group()) if pages else []
    except Exception:
        pages_data = []

    if not isinstance(pages_data, list):
        pages_data = []

    total_points = 0
    total_pages = len(pages_data)
    for p in pages_data:
        total_points += len(p.get('功能点', [])) if isinstance(p.get('功能点', []), list) else 0
    total_points = max(total_points, 3)
    total_days = _round_half(0.5 + total_pages * 0.7 + total_points * 0.15)
    if total_days < 0.5:
        total_days = 0.5

    roles = ['产品/设计', '前端开发', '后端开发', '测试']
    per_role = _round_half(total_days / len(roles))
    role_breakdown = {r: per_role for r in roles}
    g_lines = []
    for p in pages_data:
        page = p.get('页面', '需求页面')
        ptype = p.get('类型', '新增')
        fps = '、'.join(p.get('功能点', [])) if isinstance(p.get('功能点', []), list) else ''
        g_lines.append(f"【{page}-{ptype}】{fps}")
    g_text = '\n'.join(g_lines)
    g_text += f"\n\n各角色工时：{' '.join([f'{r}{v}天' for r,v in role_breakdown.items()])}\n合计工时：{total_days}天"

    return json.dumps({
        'role_breakdown': role_breakdown,
        'total_days': total_days,
        'g_text': g_text,
    }, ensure_ascii=False)


def _simulate_work_breakdown_response(prompt: str) -> str:
    info = _extract_requirement_info(prompt)
    feature = info.get('feature') or '需求'
    detail = info.get('detail') or ''
    if '修复' in detail or 'bug' in detail.lower() or '异常' in detail:
        days = 1.0
    else:
        days = 1.5 if len(detail) > 80 else 1.0
    days = _round_half(days)
    breakdown = [
        f'分析需求：理解「{feature}」的业务场景',
        '设计实现方案',
        '开发实现与验证',
    ]
    if len(detail) > 80:
        breakdown.append('补充详细测试与验收')
    work_breakdown = '\n'.join(f'{i+1}. {line}' for i, line in enumerate(breakdown))
    return json.dumps({
        'work_breakdown': work_breakdown,
        'days': days,
        'reason': '本地规则估算，输入长度和关键词决定工作量',
    }, ensure_ascii=False)


def _round_half(x: float) -> float:
    return round(x * 2) / 2


# 保持旧接口兼容（worktime_agent 调用的是 call_gemini）
def call_gemini(prompt: str, api_key: str = None, model_id: str = None) -> str:
    return call_llm(prompt, model_id=model_id)


def build_prompt(row: dict) -> str:
    module  = row.get("module", "") or ""
    feature = row.get("feature", "") or ""
    detail  = row.get("detail", "") or ""
    extra   = row.get("extra", "") or ""

    return f"""你是一位有10年经验的IT项目经理，擅长将业务需求拆解为可落地的研发工作项并估算工时。

## 当前需求信息
- 功能模块/阶段：{module}
- 需求名称：{feature}
- 需求描述：{detail}
- 补充说明：{extra}

## 任务
1. 将该需求拆解为3-6个具体工作步骤（产品/技术/测试视角均可覆盖）
2. 评估该需求的总工时天数（1天=8小时，单位精确到0.5天）

## 输出格式（严格 JSON，不要加任何代码块标记或多余文字）
{{"work_breakdown": "1. 步骤一描述\\n2. 步骤二描述\\n3. 步骤三描述", "days": 2.0, "reason": "一句话说明工时评估依据"}}

## 约束规则
- work_breakdown 每步骤不超过80字，聚焦可执行动作
- days 范围：0.5 到 10，超出请拆分或合并需求
- 若需求信息不足，基于通用研发经验给出合理估算
- 不要输出任何 JSON 以外的内容

## 参考样例
输入：顺丰快捷登录接入 - 前端引入SDK，获取授权码，后端换取token，绑定账号
输出：{{"work_breakdown": "1. 前端引入顺丰微服务SDK并配置授权范围\\n2. 实现获取临时授权码逻辑（静默+主动两套）\\n3. 后端实现token换取接口及RSA解密用户信息\\n4. 实现顺丰openId与本地账号绑定逻辑\\n5. 产品输出登录流程原型图（新用户/老用户两场景）", "days": 2.0, "reason": "标准OAuth接入复杂度，含两套授权流程，估2天"}}"""


def parse_response(raw_text: str) -> dict:
    text = re.sub(r'```(?:json)?\s*', '', raw_text).replace('```', '').strip()

    try:
        data = json.loads(text)
        return {
            "work_breakdown": str(data.get("work_breakdown", "")).replace("\\n", "\n"),
            "days": float(data.get("days", 1.0)),
        }
    except (json.JSONDecodeError, ValueError):
        pass

    days_match = re.search(r'"days"\s*:\s*([\d.]+)', text)
    breakdown_match = re.search(r'"work_breakdown"\s*:\s*"((?:[^"\\]|\\.)*)"', text)

    breakdown = breakdown_match.group(1).replace("\\n", "\n") if breakdown_match else raw_text.strip()
    days = float(days_match.group(1)) if days_match else 1.0

    return {"work_breakdown": breakdown, "days": days}
