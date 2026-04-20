# -*- coding: utf-8 -*-
import os
import time
from dotenv import load_dotenv

load_dotenv()


class APIConfig:
    """API 密钥配置（只在后台使用，永远不在前端暴露）"""
    
    @staticmethod
    def get_dashscope_key() -> str:
        """获取阿里云 DashScope 密钥"""
        key = os.environ.get("DASHSCOPE_API_KEY", "")
        if not key:
            raise RuntimeError("请配置 DASHSCOPE_API_KEY 环境变量（在 .env 文件中设置）")
        return key
    
    @staticmethod
    def get_gemini_key() -> str:
        """获取 Google Gemini 密钥"""
        key = os.environ.get("GEMINI_API_KEY", "")
        if not key:
            raise RuntimeError("请配置 GEMINI_API_KEY 环境变量（在 .env 文件中设置）")
        return key
    
    @staticmethod
    def get_provider_key(provider: str) -> str:
        """根据提供商获取密钥"""
        provider = provider.lower()
        if provider == "dashscope":
            return APIConfig.get_dashscope_key()
        elif provider == "gemini":
            return APIConfig.get_gemini_key()
        else:
            raise ValueError(f"不支持的提供商: {provider}")


class AppConfig:
    """应用配置"""
    
    # 路径配置
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    OUTPUT_FOLDER = os.path.join(BASE_DIR, "outputs")
    KNOWLEDGE_DIR = os.path.join(BASE_DIR, "knowledge")
    BUSINESS_KB_DIR = os.path.join(os.path.dirname(BASE_DIR), "业务知识库")
    
    # 文件限制
    MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB
    
    # 评估参数
    EVALUATION_PARAMS = {
        "fpa_conversion_factor": 0.3,      # 功能点转人天系数
        "story_point_days": 0.8,           # 故事点转人天系数
        "min_days": 0.5,                   # 最小工时
        "max_days": 10.0,                  # 最大工时
    }
    
    # 会话配置
    SESSION_TIMEOUT_HOURS = 2
    SESSION_CLEANUP_INTERVAL = 30  # 清理间隔（秒）
    
    # 缓存配置
    KB_CACHE_TTL = 3600  # 知识库缓存有效期（秒）
    EVALUATION_CACHE_MAX_SIZE = 100  # 评估结果缓存最大数量
    
    # 默认模型
    DEFAULT_MODEL = "qwen-flash-character-2026-02-26"
    
    @classmethod
    def init_folders(cls):
        """初始化必要的目录"""
        os.makedirs(cls.UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(cls.OUTPUT_FOLDER, exist_ok=True)


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
        "id":       "qwen3.5-27b",
        "label":    "Qwen3.5 27B（阿里云）",
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
        "id":       "gemini/gemini-1.5-flash",
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

# ============================================================
# 旧版配置（保持兼容，供其他模块使用）
# ============================================================
API_KEYS = {
    "dashscope": os.environ.get("DASHSCOPE_API_KEY", ""),
    "gemini":    os.environ.get("GEMINI_API_KEY",    ""),
}

DEFAULT_MODEL = AppConfig.DEFAULT_MODEL

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

BASE_DIR = AppConfig.BASE_DIR
UPLOAD_FOLDER = AppConfig.UPLOAD_FOLDER
OUTPUT_FOLDER = AppConfig.OUTPUT_FOLDER
MAX_UPLOAD_SIZE = AppConfig.MAX_UPLOAD_SIZE

MAX_RETRIES = 3
REQUEST_DELAY = 0.5

KNOWLEDGE_DIR = AppConfig.KNOWLEDGE_DIR
BUSINESS_KB_DIR = AppConfig.BUSINESS_KB_DIR
KB_FEATURE_RULES  = os.path.join(AppConfig.KNOWLEDGE_DIR, "rules", "feature_rules.json")
KB_WORKTIME_RULES = os.path.join(AppConfig.KNOWLEDGE_DIR, "rules", "worktime_rules.json")
KB_SYSTEM_CAPS    = os.path.join(AppConfig.KNOWLEDGE_DIR, "system_caps.json")

# 技能系统路径
SKILLS_DIR         = os.path.join(AppConfig.KNOWLEDGE_DIR, "skills")
EXAMPLES_BASE_DIR  = os.path.join(AppConfig.KNOWLEDGE_DIR, "examples")
CODE_KB_DIR        = os.path.join(AppConfig.KNOWLEDGE_DIR, "code_knowledge")
