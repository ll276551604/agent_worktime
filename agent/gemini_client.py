# -*- coding: utf-8 -*-
import json
import re
import time
import logging
from openai import OpenAI
from config import AVAILABLE_MODELS, API_KEYS, DEFAULT_MODEL, MAX_RETRIES

logger = logging.getLogger(__name__)


def _get_model_config(model_id: str) -> dict:
    for m in AVAILABLE_MODELS:
        if m["id"] == model_id:
            return m
    raise ValueError(f"未知模型：{model_id}，可选：{[m['id'] for m in AVAILABLE_MODELS]}")


def call_llm(prompt: str, model_id: str = None) -> str:
    """调用 LLM，根据 model_id 自动选择 provider 和 API Key，含指数退避重试。"""
    model_id = model_id or DEFAULT_MODEL
    cfg = _get_model_config(model_id)

    api_key = API_KEYS.get(cfg["provider"], "")
    if not api_key:
        raise RuntimeError(f"未配置 {cfg['provider']} 的 API Key，请在 .env 文件中设置")

    client = OpenAI(
        api_key=api_key,
        base_url=cfg["base_url"],
        timeout=60,  # 60秒超时
        max_retries=0  # 由外层处理重试
    )
    last_exc = None

    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"LLM 请求: model={model_id}, attempt={attempt+1}/{MAX_RETRIES}, prompt_length={len(prompt)}")
            response = client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": prompt}],
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

    raise RuntimeError(f"LLM 调用失败（重试 {MAX_RETRIES} 次）：{last_exc}")


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
