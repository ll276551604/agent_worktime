# -*- coding: utf-8 -*-
"""
基础单元测试
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.worktime_agent import _generate_cache_key, _get_cached_result, _set_cached_result


class TestCacheFunctions:
    """缓存功能测试"""

    def test_generate_cache_key(self):
        """测试缓存键生成"""
        req1 = {"module": "用户管理", "feature": "登录", "detail": "实现登录功能"}
        req2 = {"module": "用户管理", "feature": "登录", "detail": "实现登录功能"}
        req3 = {"module": "订单管理", "feature": "下单", "detail": "实现下单功能"}

        key1 = _generate_cache_key(req1)
        key2 = _generate_cache_key(req2)
        key3 = _generate_cache_key(req3)

        # 相同需求应该生成相同的键
        assert key1 == key2
        # 不同需求应该生成不同的键
        assert key1 != key3
        # 键应该是有效的 MD5 哈希值（32位十六进制）
        assert len(key1) == 32

    def test_cache_set_and_get(self):
        """测试缓存设置和获取"""
        req = {"module": "测试", "feature": "测试功能", "detail": "测试详情"}
        result = {"analysis": {}, "decomposition": [], "evaluation": {"effort_days": 2.0}}

        # 设置缓存
        _set_cached_result(req, result)

        # 获取缓存
        cached = _get_cached_result(req)

        assert cached is not None
        assert cached["evaluation"]["effort_days"] == 2.0


class TestConfig:
    """配置测试"""
    
    def test_config_import(self):
        """测试配置模块导入"""
        from config import APIConfig, AppConfig
        
        # 验证配置类存在
        assert hasattr(APIConfig, 'get_dashscope_key')
        assert hasattr(APIConfig, 'get_gemini_key')
        assert hasattr(AppConfig, 'init_folders')
        assert hasattr(AppConfig, 'BASE_DIR')
        
        # 验证目录初始化方法
        AppConfig.init_folders()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
