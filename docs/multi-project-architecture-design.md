# 多项目多知识库架构设计文档

## 1. 设计背景

为支持未来多个项目使用不同知识库和评估模型的需求，需要设计一套灵活、可扩展的架构方案。

## 2. 核心设计原则

| 原则 | 说明 |
|------|------|
| **项目隔离** | 每个项目拥有独立的配置和知识库 |
| **模型可插拔** | 评估模型采用插件化设计，支持动态加载 |
| **配置驱动** | 通过配置文件而非硬编码来管理项目差异 |
| **分层解耦** | 知识库层、评估层、业务层相互独立 |

## 3. 目录结构设计

```
agent_worktime/
├── projects/                    # 项目配置目录（新增）
│   ├── project_a/              # 项目 A
│   │   ├── config.yaml         # 项目配置
│   │   └── knowledge/          # 项目专属知识库
│   │       ├── system_caps.json
│   │       ├── feature_rules.json
│   │       └── worktime_rules.json
│   └── project_b/              # 项目 B
│       ├── config.yaml
│       └── knowledge/
├── agent/                      # 核心引擎（与项目无关）
│   ├── knowledge_manager.py    # 知识库加载器
│   ├── evaluation_models.py    # 评估模型框架
│   ├── worktime_agent.py       # 业务逻辑
│   └── models/                 # 可插拔模型（新增目录）
│       ├── fpa.py              # FPA 模型
│       ├── cocomo.py           # COCOMO 模型
│       ├── storypoint.py       # 故事点模型
│       └── composite.py        # 综合模型
├── templates/
└── app.py
```

## 4. 项目配置文件 (`config.yaml`)

```yaml
# 项目基本信息
project:
  id: "project_a"
  name: "电商后台管理系统"
  description: "电商平台的后台管理系统"

# 支持的评估模型（可按需启用/禁用）
enabled_models:
  - fpa              # 功能点分析法
  - cocomo           # COCOMO II 模型
  - storypoint       # 敏捷故事点
  - composite        # 综合评估（默认）

# 模型权重配置（仅对综合评估生效）
model_weights:
  fpa: 0.35
  cocomo: 0.25
  storypoint: 0.20
  rule_based: 0.20

# 知识库路径配置
knowledge:
  system_caps: "knowledge/system_caps.json"
  feature_rules: "knowledge/feature_rules.json"
  worktime_rules: "knowledge/worktime_rules.json"
  custom_rules: "knowledge/custom_rules.json"

# 业务规则配置
rules:
  skip_filled_rows: true        # 是否跳过已填写的行
  max_retry_count: 3            # 最大重试次数
  confidence_threshold: 0.7     # 置信度阈值

# 输出配置
output:
  columns:
    - "序号"
    - "原始需求"
    - "需求类型"
    - "已拆解需求"
    - "产品工时"
    - "评估模型"
    - "备注"
```

## 5. 评估模型插件化设计

### 5.1 模型基类

```python
# agent/models/base.py
from abc import ABC, abstractmethod

class EvaluationModel(ABC):
    @property
    @abstractmethod
    def model_id(self) -> str:
        pass
    
    @property
    @abstractmethod
    def model_name(self) -> str:
        pass
    
    @abstractmethod
    def evaluate(self, requirement: dict, decomposition: list, config: dict) -> dict:
        pass
    
    def get_config_schema(self) -> dict:
        return {}
```

### 5.2 模型管理器

```python
# agent/model_manager.py
import importlib
import os

class ModelManager:
    def __init__(self):
        self.models = {}
        self._load_models()
    
    def _load_models(self):
        models_dir = os.path.join(os.path.dirname(__file__), "models")
        for filename in os.listdir(models_dir):
            if filename.endswith(".py") and filename != "__init__.py" and filename != "base.py":
                module_name = f"agent.models.{filename[:-3]}"
                module = importlib.import_module(module_name)
                for attr in dir(module):
                    obj = getattr(module, attr)
                    if isinstance(obj, type) and issubclass(obj, EvaluationModel) and obj != EvaluationModel:
                        instance = obj()
                        self.models[instance.model_id] = instance
    
    def get_model(self, model_id: str) -> EvaluationModel:
        return self.models.get(model_id)
    
    def get_enabled_models(self, config: dict) -> list:
        enabled = config.get("enabled_models", [])
        return [self.models[m] for m in enabled if m in self.models]
```

## 6. 知识库管理器

```python
# agent/knowledge_manager.py
import json
import os
import yaml

class KnowledgeManager:
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.knowledge = {}
        self.config = {}
        self._load_knowledge()
    
    def _load_knowledge(self):
        project_dir = os.path.join("projects", self.project_id)
        config_path = os.path.join(project_dir, "config.yaml")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        knowledge_config = self.config.get("knowledge", {})
        for key, relative_path in knowledge_config.items():
            full_path = os.path.join(project_dir, relative_path)
            if os.path.exists(full_path):
                with open(full_path, 'r', encoding='utf-8') as f:
                    self.knowledge[key] = json.load(f)
    
    def analyze_requirement(self, requirement: dict) -> dict:
        return {
            "judgment": "新增",
            "confidence": 0.85,
            "related_modules": [],
            "existing_features": []
        }
```

## 7. API 接口设计

| 接口 | 方法 | 功能 |
|------|------|------|
| `/api/projects` | GET | 获取所有项目列表 |
| `/api/projects/{project_id}/config` | GET | 获取项目配置 |
| `/api/evaluate` | POST | 评估需求（支持 project_id 参数） |

## 8. 扩展建议

| 扩展场景 | 实现方案 |
|---------|---------|
| **新增项目** | 复制项目模板目录，修改配置文件 |
| **新增评估模型** | 在 `agent/models/` 创建新文件，继承 `EvaluationModel` |
| **自定义规则** | 在项目知识库中添加规则文件 |
| **模型权重调整** | 修改项目 `config.yaml` 中的权重配置 |

## 9. 实现优先级

```
高优先级：
1. 创建 projects 目录结构
2. 实现模型基类和模型管理器
3. 实现项目配置加载

中优先级：
4. 添加项目管理 API
5. 修改评估接口支持 project_id 参数
6. 前端添加项目选择器

低优先级：
7. 配置热加载
8. 日志和监控
```

---

**文档版本**: v1.0  
**创建日期**: 2026-04-14  
**状态**: 待实现