# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# 后台 API Key 配置（用户不可见，在此处填写）
# ============================================================
API_KEYS = {
    "dashscope": os.environ.get("DASHSCOPE_API_KEY", "sk-f448e9a456f849b984fac86018b92e48"),
    "gemini":    os.environ.get("GEMINI_API_KEY",    "AIzaSyAWTJZRLWhfoKqnSOQXkDttnN3u6HsEQn0"),
}

# ============================================================
# 可选模型列表（前端下拉展示）
# provider 对应 API_KEYS 的 key
# ============================================================
AVAILABLE_MODELS = [
    {
        "id":       "qwen-flash-character-2026-02-26",
        "label":    "Qwen Flash Character（阿里云，极速）",
        "provider": "dashscope",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    },
    {
        "id":       "qwen3.5-122b-a10b",
        "label":    "Qwen3.5 122B（阿里云）",
        "provider": "dashscope",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    },
    {
        "id":       "qwen-turbo",
        "label":    "Qwen Turbo（阿里云，快速）",
        "provider": "dashscope",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    },
    {
        "id":       "gemini-1.5-flash",
        "label":    "Gemini 1.5 Flash（Google）",
        "provider": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
    },
    {
        "id":       "gemini-2.0-flash",
        "label":    "Gemini 2.0 Flash（Google）",
        "provider": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
    },
]

# 默认模型 id
DEFAULT_MODEL = "qwen-flash-character-2026-02-26"

# Excel 默认配置
SHEET_NAME = "2.需求&工时清单"
DATA_START_ROW = 4

INPUT_COLS = {
    "module":  1,
    "feature": 2,
    "detail":  3,
    "extra":   4,
}

OUTPUT_COL_G = 7
OUTPUT_COL_N = 14

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "outputs")
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB

MAX_RETRIES = 3
REQUEST_DELAY = 0.5

# ============================================================
# 知识库路径配置
# ============================================================
KNOWLEDGE_DIR = os.path.join(BASE_DIR, "knowledge")
BUSINESS_KB_DIR = os.path.join(os.path.dirname(BASE_DIR), "业务知识库")
KB_FEATURE_RULES  = os.path.join(KNOWLEDGE_DIR, "rules", "feature_rules.json")
KB_WORKTIME_RULES = os.path.join(KNOWLEDGE_DIR, "rules", "worktime_rules.json")
KB_SYSTEM_CAPS    = os.path.join(KNOWLEDGE_DIR, "system_caps.json")

