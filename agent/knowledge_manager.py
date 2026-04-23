# -*- coding: utf-8 -*-
"""
增强的知识库管理器
- 支持本地知识库读取
- 支持代码知识库读取
- 智能需求识别（新增vs调整）
- 产品需求初步拆解
"""
import os
import json
import re
import time
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class KnowledgeManager:
    """知识库管理器"""
    
    def __init__(self):
        self.kb_cache = {}
        self.code_kb_cache = {}
        self._load_time = 0
        self._cache_ttl = 3600  # 缓存有效期 1 小时
    
    def load_all_knowledge(self, force_reload=False) -> Dict[str, Any]:
        """加载所有知识库（带缓存）"""
        now = time.time()
        
        # 如果缓存有效且不强制刷新，直接返回缓存
        if self.kb_cache and not force_reload and (now - self._load_time) < self._cache_ttl:
            return self.kb_cache
        
        # 重新加载
        self.kb_cache = {
            "system_caps": self._load_system_caps(),
            "feature_rules": self._load_feature_rules(),
            "worktime_rules": self._load_worktime_rules(),
            "business_docs": self._load_business_docs(),
            "code_knowledge": self._load_code_knowledge(),
        }
        self._load_time = now
        
        logger.info("知识库加载完成")
        return self.kb_cache
    
    def _load_system_caps(self) -> Dict:
        """加载系统能力（已有模块和功能）"""
        from config import KB_SYSTEM_CAPS
        return self._load_json_file(KB_SYSTEM_CAPS)
    
    def _load_feature_rules(self) -> Dict:
        """加载功能拆解规则"""
        from config import KB_FEATURE_RULES
        return self._load_json_file(KB_FEATURE_RULES)
    
    def _load_worktime_rules(self) -> Dict:
        """加载工时评估规则"""
        from config import KB_WORKTIME_RULES
        return self._load_json_file(KB_WORKTIME_RULES)
    
    def _load_business_docs(self) -> List[Dict]:
        """加载业务文档知识库（支持多个目录，Markdown / JSON / TXT）"""
        from config import BUSINESS_KB_DIRS
        docs = []
        for kb_dir in BUSINESS_KB_DIRS:
            if not os.path.exists(kb_dir):
                logger.warning(f"业务知识库目录不存在: {kb_dir}")
                continue
            for fname in sorted(os.listdir(kb_dir)):
                fpath = os.path.join(kb_dir, fname)
                if not os.path.isfile(fpath):
                    continue
                if not any(fname.endswith(ext) for ext in (".md", ".txt", ".json")):
                    continue
                try:
                    with open(fpath, encoding="utf-8") as f:
                        content = f.read()
                    docs.append(self._parse_business_doc(fname, content))
                    logger.debug(f"加载业务文档: {fname} ({kb_dir})")
                except Exception as e:
                    logger.error(f"加载业务文档失败 {fname}: {e}")
        return docs

    def _parse_business_doc(self, fname: str, content: str) -> Dict:
        """将 Markdown/TXT 文件解析为 match_business_context 所需的结构化格式"""
        domain = re.sub(r'\.[^.]+$', '', fname)  # 去掉扩展名作为领域名

        # 从 H1/H2 标题提取 subdomain
        heading_match = re.search(r'^#{1,2}\s+(.+)', content, re.MULTILINE)
        subdomain = heading_match.group(1).strip() if heading_match else domain

        # 第一段非标题文本作为 digest
        lines = [l for l in content.splitlines() if l.strip() and not l.startswith('#')]
        digest = lines[0][:200] if lines else ""

        # 提取匹配关键词：标题词 + 内容高频词
        match_terms = list(set(self._extract_terms(content)))

        return {
            "domain":      domain,
            "subdomain":   subdomain,
            "recall_when": "",
            "digest":      digest,
            "body":        content,
            "match_terms": match_terms,
        }
    
    def _load_code_knowledge(self) -> Dict:
        """加载代码知识库（扫描项目结构）"""
        from config import BASE_DIR
        
        if "code_knowledge" in self.code_kb_cache:
            return self.code_kb_cache["code_knowledge"]
        
        code_kb = {
            "modules": [],
            "controllers": [],
            "models": [],
            "apis": [],
            "components": [],
        }
        
        # 扫描项目目录结构
        for root, dirs, files in os.walk(BASE_DIR):
            # 跳过隐藏目录和依赖目录
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'venv', 'node_modules']]
            
            for fname in files:
                fpath = os.path.join(root, fname)
                rel_path = os.path.relpath(fpath, BASE_DIR)
                
                if fname.endswith('.py'):
                    module_info = self._parse_python_file(fpath, rel_path)
                    if module_info:
                        code_kb["modules"].append(module_info)
                        if 'controller' in rel_path.lower() or 'api' in rel_path.lower():
                            code_kb["controllers"].append(module_info)
                        if 'model' in rel_path.lower():
                            code_kb["models"].append(module_info)
                
                elif fname.endswith('.json') and 'schema' in rel_path.lower():
                    schema_info = self._parse_schema_file(fpath, rel_path)
                    if schema_info:
                        code_kb["apis"].append(schema_info)
                
                elif fname.endswith('.js') or fname.endswith('.ts') or fname.endswith('.vue') or fname.endswith('.jsx'):
                    comp_info = self._parse_frontend_file(fpath, rel_path)
                    if comp_info:
                        code_kb["components"].append(comp_info)
        
        self.code_kb_cache["code_knowledge"] = code_kb
        logger.info(f"代码知识库加载完成: {len(code_kb['modules'])} 个模块")
        return code_kb
    
    def _parse_python_file(self, fpath: str, rel_path: str) -> Dict:
        """解析Python文件，提取类和函数"""
        try:
            with open(fpath, encoding="utf-8") as f:
                content = f.read()
            
            classes = re.findall(r'class\s+(\w+)\s*(?:\(.*?\))?\s*:', content)
            functions = re.findall(r'def\s+(\w+)\s*\(', content)
            imports = re.findall(r'from\s+(\S+)\s+import|import\s+(\S+)', content)
            
            return {
                "path": rel_path,
                "type": "python",
                "classes": classes,
                "functions": functions,
                "imports": [item for sublist in imports for item in sublist if item],
            }
        except Exception:
            return None
    
    def _parse_schema_file(self, fpath: str, rel_path: str) -> Dict:
        """解析JSON Schema文件"""
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
            return {
                "path": rel_path,
                "type": "schema",
                "properties": list(data.get('properties', {}).keys()),
                "required": data.get('required', []),
            }
        except Exception:
            return None
    
    def _parse_frontend_file(self, fpath: str, rel_path: str) -> Dict:
        """解析前端文件"""
        try:
            with open(fpath, encoding="utf-8") as f:
                content = f.read()
            
            # 提取组件名和props
            component_name = re.search(r'(?:export\s+(?:default\s+)?class|function)\s+(\w+)', content)
            props = re.findall(r'props\s*[=:]\s*\{([^}]+)\}', content)
            
            return {
                "path": rel_path,
                "type": "component",
                "name": component_name.group(1) if component_name else None,
                "props": props[0] if props else "",
            }
        except Exception:
            return None
    
    def _extract_terms(self, content: str) -> List[str]:
        """从文本中提取关键词"""
        terms = set()
        # 提取中文词
        chinese_pattern = re.findall(r'[\u4e00-\u9fa5]{2,}', content)
        for term in chinese_pattern:
            if len(term) >= 2:
                terms.add(term)
        # 提取英文词
        english_pattern = re.findall(r'[A-Za-z][a-zA-Z0-9_]{2,}', content)
        terms.update(english_pattern)
        return list(terms)
    
    def _load_json_file(self, path: str) -> Dict:
        """加载JSON文件"""
        if not os.path.exists(path):
            logger.warning(f"配置文件不存在: {path}")
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载JSON文件失败 {path}: {e}")
            return {}
    
    def analyze_requirement(self, requirement: Dict) -> Dict:
        """
        智能分析需求：
        - 判断是新增还是调整
        - 识别相关模块
        - 提供拆解建议
        """
        feature = requirement.get("feature", "")
        detail = requirement.get("detail", "")
        module = requirement.get("module", "")
        
        all_kb = self.load_all_knowledge()
        system_caps = all_kb["system_caps"]
        
        analysis = {
            "judgment": "新增",  # 新增 / 调整
            "confidence": 0.5,
            "related_modules": [],
            "existing_features": [],
            "suggestions": [],
        }
        
        # 检查是否匹配现有模块
        for module_name, caps in system_caps.items():
            if module_name == "_说明" or module_name == "_更新方式" or module_name == "_格式说明" or module_name == "_示例":
                continue
            
            # 检查模块名匹配
            module_match = module_name in feature or feature in module_name or module_name in detail
            
            if module_match:
                analysis["related_modules"].append(module_name)
                
                # 检查是否有相似功能
                existing_features = caps.get("features", [])
                for feat in existing_features:
                    if feat in feature or feature in feat or feat in detail:
                        analysis["existing_features"].append(feat)
                        analysis["judgment"] = "调整"
                        analysis["confidence"] = min(0.9, analysis["confidence"] + 0.3)
        
        # 如果没有找到匹配，检查代码知识库
        if not analysis["related_modules"]:
            code_kb = all_kb["code_knowledge"]
            for mod in code_kb["modules"]:
                mod_name = os.path.splitext(mod["path"])[0].replace(os.sep, "_")
                if mod_name.lower() in feature.lower() or feature.lower() in mod_name.lower():
                    analysis["related_modules"].append(mod_name)
                    analysis["judgment"] = "调整"
                    analysis["confidence"] = 0.6
        
        # 关键词分析
        keywords = ["新增", "新建", "添加", "创建", "开发", "实现"]
        for kw in keywords:
            if kw in feature or kw in detail:
                analysis["judgment"] = "新增"
                analysis["confidence"] = min(0.9, analysis["confidence"] + 0.2)
        
        keywords_adjust = ["修改", "调整", "优化", "改进", "修复", "更新"]
        for kw in keywords_adjust:
            if kw in feature or kw in detail:
                analysis["judgment"] = "调整"
                analysis["confidence"] = min(0.9, analysis["confidence"] + 0.2)
        
        # 生成建议
        if analysis["judgment"] == "调整":
            if analysis["existing_features"]:
                analysis["suggestions"].append(
                    f"检测到相似功能: {', '.join(analysis['existing_features'])}，建议参考现有实现"
                )
            if analysis["related_modules"]:
                analysis["suggestions"].append(
                    f"涉及模块: {', '.join(analysis['related_modules'])}，建议检查相关代码"
                )
        else:
            analysis["suggestions"].append("这是一个新增需求，需要完整实现")
            if analysis["related_modules"]:
                analysis["suggestions"].append(
                    f"建议参考相似模块: {', '.join(analysis['related_modules'])}"
                )
        
        return analysis
    
    def suggest_decomposition(self, requirement: Dict) -> List[Dict]:
        """
        建议需求拆解方案
        返回初步拆解的功能点列表
        """
        feature = requirement.get("feature", "")
        detail = requirement.get("detail", "")
        
        all_kb = self.load_all_knowledge()
        feature_rules = all_kb["feature_rules"]
        
        suggestions = []
        
        # 根据页面类型规则匹配
        for page_type, default_features in feature_rules.get("页面类型规则", {}).items():
            if page_type in feature or feature in page_type:
                suggestions.append({
                    "type": "页面",
                    "name": page_type,
                    "features": default_features.copy(),
                })
        
        # 根据功能类型规则匹配
        for func_type, default_features in feature_rules.get("功能类型规则", {}).items():
            if func_type in feature or feature in func_type or func_type in detail:
                suggestions.append({
                    "type": "功能",
                    "name": func_type,
                    "features": default_features.copy(),
                })
        
        # 如果没有匹配规则，使用通用拆解
        if not suggestions:
            suggestions = self._generate_default_decomposition(feature, detail)
        
        return suggestions
    
    def _generate_default_decomposition(self, feature: str, detail: str) -> List[Dict]:
        """生成默认拆解方案"""
        parts = []
        
        # 通用功能点
        if "列表" in feature or "查询" in feature or "搜索" in feature:
            parts.append({
                "type": "页面",
                "name": "列表页",
                "features": ["查询条件", "结果列表", "分页", "排序", "导出"],
            })
        
        if "新增" in feature or "创建" in feature or "添加" in feature:
            parts.append({
                "type": "页面",
                "name": "表单页",
                "features": ["表单字段", "必填校验", "格式校验", "提交保存"],
            })
        
        if "详情" in feature or "查看" in feature:
            parts.append({
                "type": "页面",
                "name": "详情页",
                "features": ["信息展示", "关联数据", "操作按钮"],
            })
        
        if "编辑" in feature or "修改" in feature:
            parts.append({
                "type": "功能",
                "name": "编辑功能",
                "features": ["数据回显", "编辑表单", "保存更新"],
            })
        
        if "导入" in feature:
            parts.append({
                "type": "功能",
                "name": "导入功能",
                "features": ["模板下载", "文件上传", "数据校验", "结果反馈"],
            })
        
        if "导出" in feature:
            parts.append({
                "type": "功能",
                "name": "导出功能",
                "features": ["筛选条件", "字段选择", "文件生成"],
            })
        
        # 如果没有匹配，使用通用模板
        if not parts:
            parts = [
                {
                    "type": "页面",
                    "name": "主页面",
                    "features": ["页面布局", "基础交互", "数据展示"],
                },
                {
                    "type": "功能",
                    "name": "核心功能",
                    "features": ["业务逻辑", "接口对接", "异常处理"],
                },
            ]
        
        return parts


# 单例
_knowledge_manager = None

def get_knowledge_manager() -> KnowledgeManager:
    """获取知识库管理器单例"""
    global _knowledge_manager
    if _knowledge_manager is None:
        _knowledge_manager = KnowledgeManager()
    return _knowledge_manager
