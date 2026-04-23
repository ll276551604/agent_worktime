# AI 工时评估助手

## 项目概览

基于大语言模型的 B 端履约中台工时评估工具。通过对话描述需求，自动完成知识库检索、功能点拆解、四端工时估算，输出可直接用于项目报价的评估结果。

**核心能力：**

- **知识库驱动**：内置 57 条历史案例，自动召回相似案例作为参照
- **多源知识检索**：业务知识库 + 代码知识库 + Java 源码扫描
- **智能拆解 & 估算**：LangGraph 流程，页面 × 功能点 → S/M/L/XL/XXL 四端工时
- **四端分角色输出**：产品 / 前端 / 后端 / 测试，测试工时 = 后端 × 0.35
- **Excel 批量处理**：上传需求清单，批量评估并回填结果
- **多模型 & 会话管理**：6 种 LLM 可切换，多轮对话上下文记忆

## 项目结构

```
agent_worktime/
├── agent/                          # 核心评估引擎
│   ├── nodes/
│   │   ├── feature_rebuilder.py    #   图节点1：需求拆解为页面 × 功能点
│   │   ├── worktime_estimator.py   #   图节点2：S/M/L/XL/XXL 四端工时估算
│   │   └── reviewer.py             #   需求质量审核（已实现，暂未接入图）
│   ├── dialog_manager.py           #   意图识别、需求提取、智能追问
│   ├── evaluation_models.py        #   5种评估模型：FPA / COCOMO / 故事点 / 规则 / 综合
│   ├── gemini_client.py            #   LLM 调用封装（DashScope + Gemini）
│   ├── graph.py                    #   LangGraph StateGraph 定义
│   ├── java_scanner.py             #   Java 源码扫描（Controller/Entity/Service）
│   ├── kb_utils.py                 #   业务知识上下文匹配
│   ├── knowledge_manager.py        #   知识库加载与需求分析
│   ├── session_manager.py          #   会话管理（自动过期清理）
│   ├── skill_manager.py            #   技能加载、案例检索、代码知识
│   └── worktime_agent.py           #   主评估入口：对话评估 / 批量处理 / Excel导出
├── excel/
│   ├── reader.py                   # Excel 需求读取（支持多种表名/合并单元格）
│   └── writer.py                   # Excel 结果回填（G列文本 + N列数字）
├── knowledge/                      # 知识库
│   ├── b_end_fulfillment/
│   │   └── kb_cases.json           #   57 条历史案例（8大类别）
│   ├── business/                   #   业务知识库目录
│   ├── code_knowledge/             #   代码知识库目录
│   ├── examples/                   #   技能 few-shot 案例
│   ├── rules/                      #   功能点拆解 & 工时评估规则
│   ├── skills/                     #   技能配置（角色/分级/加分项）
│   └── system_caps.json            #   系统已有能力描述
├── prompts/
│   └── guiding_prompt.txt          # 引导对话 prompt
├── templates/
│   └── index.html                  # 前端页面（暗色模式/会话管理/SSE流式）
├── docs/                           # 架构设计与产品路线图
├── tests/                          # 单元测试
├── app.py                          # Flask 应用入口（API 路由）
├── config.py                       # 配置（模型/路径/评估参数）
├── start.sh                        # 一键启动脚本
└── requirements.txt
```

## 快速开始

### 环境要求

- Python 3.8+

### 安装与启动

```bash
# 克隆项目后进入目录
cd agent_worktime

# 一键启动（自动创建虚拟环境、安装依赖、启动服务）
bash start.sh
```

首次运行会生成 `.env` 文件，填入 API Key 后重新执行：

```
GEMINI_API_KEY=your_gemini_key
DASHSCOPE_API_KEY=your_dashscope_key
```

服务默认启动在 http://localhost:5001（端口被占用时自动切换至 5002）。

## 使用方式

### 对话评估

在输入框直接描述需求，系统会自动进入评估流程。

**输入示例：**
> 新增经销商账期预警功能：当应收账款超过账期时自动触发预警，支持预警规则可配置（阈值、触发条件）；向销售员发送企业微信消息；提供预警记录查询页面，支持导出。

**评估输出示例：**
```
【参照案例】
通知-09 | 经销商余额不足短信预警 | 新增 | 产品0.5天 前端0天 后端2天 测试0.5天 合计3天
规则-05 | 订单管控策略执行+通知 | 完全新增 | 产品3天 前端1天 后端9天 测试3天 合计16天

【功能点拆解】
1. 账期预警规则配置 | 完全新增 | 标准配置表，字段10+，含启用禁用
2. 预警触发逻辑 | 完全新增 | 含定时任务+规则匹配+通知调用，无页面
3. 企业微信消息接口 | 新增, 业务联调 | 调用企微接口，单发场景
4. 预警记录查询页 | 完全新增 | 1页查询+导出

【工时评估】
1. 账期预警规则配置 | 产品1 | 前端1 | 后端3 | 测试1 | 小计6 | 参照配置-04
2. 预警触发逻辑 | 产品1 | 前端0 | 后端4 | 测试1.5 | 小计6.5 | ⚠️建议评审确认
3. 企业微信消息接口 | 产品0.5 | 前端0 | 后端2 | 测试0.5 | 小计3 | 参照通知-09
4. 预警记录查询页 | 产品1 | 前端1 | 后端3 | 测试1 | 小计6 | 参照列表-01简化版
合计 | 产品3.5天 | 前端2天 | 后端12天 | 测试4天 | 总计21.5天

⚠️评估说明：本评估基于历史项目数据推算，建议±20%浮动区间...
```

### Excel 批量处理

1. 准备 `.xlsx` 文件，支持多种工作表名称
2. 点击上传按钮选择文件
3. 系统自动检测已填写内容并询问是否覆盖
4. 等待批量评估完成，下载回填结果

**支持的工作表名称：**
- 需求清单、需求拆解评估、工时评估表AI版本
- 工时评估表、需求列表、需求、Sheet1

## 工时评估规则

### 产品工时
| 等级 | 工时 | 典型场景 |
|------|------|---------|
| S | 0.5天 | 单接口说明 / 单配置项追加 |
| M | 1天 | 标准增删改查配置表 / 接口+单页面 |
| L | 1.5~2天 | 2~3个页面 / 含导出+导入 |
| XL | 3天 | 含业务规则执行+通知 / 跨系统联动 |
| XXL | 4~5天 | 全新子系统（5+页面）/ 复杂报表2个+ |

### 后端工时
| 等级 | 工时 | 典型场景 |
|------|------|---------|
| S | 0.5~1.5天 | 单接口字段改造 / 简单查询接口 |
| M | 2~3天 | 1~2个标准 CRUD 接口组 |
| L | 4~6天 | 3~5个接口+业务逻辑 / 含数据同步链路 |
| XL | 7~9天 | 完整功能模块 / 含规则引擎 |
| XXL | 10~16天 | 跨系统全链路 / 含状态机+异步+重试 |

后端加分项：跨系统对接每个 +2~3天；异步/消息队列 +1~2天；业务规则匹配 +2~3天；大批量导出 10W+ +1天。

### 前端工时
| 等级 | 工时 | 典型场景 |
|------|------|---------|
| 0天 | 0天 | 纯后端接口，无页面 |
| S | 0.5天 | 纯展示只读页 / 已有页面追加字段 |
| M | 1天 | 标准 CRUD 单页（字段10~15） |
| L | 1.5天 | 复杂查询列表（查询条件10+） |
| XL | 2~3天 | 3~4个页面含联动 / 含图表报表 |
| XXL | 4~5天 | 5+页面 / 可视化规则配置器 |

### 测试工时
**公式：后端工时 × 0.35，向上取整到 0.5 天粒度**

| 后端工时 | 测试工时 |
|---------|---------|
| ≤2天 | 0.5天 |
| 2.5~3.5天 | 1天 |
| 4~4.5天 | 1.5天 |
| 5~6天 | 2天 |
| 7~8天 | 3天 |
| 12~16天 | 4~6天 |

## API 接口

### 对话评估

**标准接口**
```
POST /chat
Body: { "message": "需求描述", "session_id": "xxx", "skill_id": "b_end_fulfillment" }
Response: {
  "success": true,
  "output": {
    "type": "text|evaluation|thinking|error",
    "content": "..."
  },
  "meta": {
    "intent": "chat|new_task|revise_task",
    "stage": "chat|collecting|assessment|reassessment"
  }
}
```

**流式接口（SSE，推荐）**
```
POST /chat/stream
Body: { "message": "需求描述", "session_id": "xxx" }
Response: Server-Sent Events
  - type: intent    # 意图识别结果
  - type: thinking  # 思考状态（逐步加载）
  - type: complete  # 完成结果
  - type: error     # 错误信息
```

### 模型列表
```
GET /models
Response: 返回可用的 6 种 LLM 模型列表
```

### Excel 批量评估
```
POST /upload                # 上传 Excel 文件，返回 task_id
POST /process               # 处理已上传文件
GET  /progress/<task_id>    # SSE 实时进度流
GET  /download/<filename>   # 下载评估结果
POST /evaluate_batch        # 批量评估
POST /export_evaluation     # 导出评估结果为 Excel
```

### 会话管理
```
POST /session/create        # 创建新会话
GET  /session/<id>/history  # 获取会话历史消息
DELETE /session/<id>/delete # 删除会话
```

### 技能管理
```
GET  /skills                    # 列出所有技能
GET  /skills/current            # 获取当前使用的技能
POST /skills/switch             # 切换技能 { "skill_id": "xxx" }
GET  /skills/<id>               # 获取技能详情
POST /skills/reload             # 重新加载技能配置
GET  /skills/<id>/examples      # 获取历史案例列表
POST /skills/<id>/examples      # 新增历史案例（积累团队经验）
```

### 知识管理
```
GET  /knowledge/code            # 获取代码知识
POST /knowledge/reload          # 重新加载知识库
POST /knowledge/analyze         # 分析需求类型（新增/调整）
```

### 直接评估
```
POST /evaluate        # 直接评估需求（跳过对话引导）
```

## 技能体系

当前内置技能：

| 技能 ID | 名称 | 说明 |
|---------|------|------|
| `b_end_fulfillment` | B端履约中台评估 | 标品定制化项目评估，含 57 条历史案例（默认） |

技能配置包含：角色定义、S/M/L/XL/XXL 分级规则、复杂度加分项、零工时场景等。可通过 `POST /skills/reload` 热重载配置。

## 评估模型

系统内置 5 种评估模型（`evaluation_models.py`）：

| 模型 | 方法 | 说明 |
|------|------|------|
| FunctionPoint | Albrecht FPA | 基于 EI/EO/EQ/ILF/EIF 的功能点分析 |
| COCOMO | COCOMO II | 基于规模的参数化估算 Effort = A × Size^B × EAF |
| StoryPoint | 斐波那契数列 | 敏捷团队故事点（1/2/3/5/8/13） |
| RuleBased | 规则匹配 | 基于知识库预定义规则 |
| Composite | 加权综合 | FPA(0.35) + COCOMO(0.25) + StoryPoint(0.20) + RuleBased(0.20) |

## 注意事项

- 评估结果基于历史案例数据推算，建议以 **±20%** 作为浮动区间
- 涉及第三方系统对接时，建议接口文档确认后由研发复核后端工时
- 可通过 `POST /skills/b_end_fulfillment/examples` 持续积累团队历史案例，提升评估准确性
- 使用前需在 `.env` 中配置有效的 API Key
- `reviewer.py`（需求质量审核节点）已实现但暂未接入 LangGraph 流程
