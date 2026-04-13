# AI 工时评估助手

基于大语言模型的智能需求分析与工时评估工具，帮助产品经理快速估算项目开发工作量。

## ✨ 功能特点

- **智能需求分析**：自动识别需求类型（新增/调整），识别相关模块和相似功能
- **需求自动拆解**：按页面类型和功能类型自动拆分需求为功能点
- **多模型评估**：支持多种业内标准评估模型
  - 综合评估模型（加权平均）
  - 功能点分析法 (FPA)
  - COCOMO II 模型
  - 敏捷故事点估算
- **知识库驱动**：强制读取本地知识库和代码知识库，提升评估准确性
- **Excel 导出**：支持导出评估结果，包含原始需求、拆解需求、产品工时等

## 🚀 快速开始

### 环境要求

- Python 3.8+
- Flask 2.0+
- 依赖库：`pip install -r requirements.txt`

### 配置

1. 复制 `.env.example` 为 `.env`
2. 配置 API Key：
   ```
   DASHSCOPE_API_KEY=your_dashscope_key
   GEMINI_API_KEY=your_gemini_key
   ```

### 启动服务

```bash
cd agent_worktime
pip install -r requirements.txt
python app.py
```

服务启动后访问：http://localhost:5000

## 📖 使用说明

### 方式一：直接输入需求

在输入框中输入需求描述，例如：
```
用户管理模块 - 新增用户功能
```

### 方式二：上传 Excel 文件

1. 点击上传按钮选择 `.xlsx` 文件
2. 支持拖拽上传
3. 文件格式要求：
   - Sheet 名称为 `需求清单`
   - 列：模块、功能点、需求描述、已有功能点、预估工时

### 输出结果

评估完成后可导出 Excel，包含以下列：
- 序号
- 原始需求
- 需求类型（新增/调整）
- 已拆解需求（功能点明细）
- 产品工时（天）
- 评估模型
- 备注（相关模块、建议）

## 📁 项目结构

```
agent_worktime/
├── agent/                 # 核心业务逻辑
│   ├── knowledge_manager.py    # 知识库管理
│   ├── evaluation_models.py    # 评估模型
│   ├── worktime_agent.py       # 主代理逻辑
│   ├── session_manager.py      # 会话管理
│   ├── reader.py               # Excel 读取
│   └── writer.py               # Excel 写入
├── knowledge/             # 知识库文件
│   ├── system_caps.json        # 系统能力
│   ├── feature_rules.json      # 功能规则
│   └── worktime_rules.json     # 工时规则
├── templates/             # 前端模板
│   └── index.html              # 主页面
├── app.py                 # Flask 应用入口
├── config.py              # 配置文件
└── requirements.txt       # 依赖列表
```

## 🧠 评估模型说明

### 功能点分析法 (FPA)
基于 Albrecht 方法，计算 EI（外部输入）、EO（外部输出）、EQ（外部查询）、ILF（内部逻辑文件）、EIF（外部接口文件）的功能点。

### COCOMO II 模型
面向对象开发成本估算模型，使用公式：
```
Effort = A * Size^B * EAF
```

### 敏捷故事点估算
使用斐波那契数列（1, 2, 3, 5, 8, 13）估算故事点，再转换为人天。

### 综合评估模型
加权平均多个模型结果：
- FPA: 35%
- COCOMO: 25%
- 故事点: 20%
- 规则引擎: 20%

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

---

**注意**：使用前请确保已配置有效的 API Key，否则无法进行 AI 评估。