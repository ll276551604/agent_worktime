# AI 工时评估助手 - 产品方向调整改造计划

**更新日期**：2026-04-25  
**状态**：待执行  
**优先级**：高

---

## 核心方向调整总结

### 删除功能
- ❌ Excel 批量导入
- ❌ 多项目隔离
- ❌ 多评估模型（FPA、COCOMO、故事点、综合）
- ❌ 批量处理接口

### 改造功能
- 🔄 对话输出格式（文字 → 表格）
- 🔄 改造点描述（技术视角 → 业务视角）
- 🔄 Excel 导出格式（新增接口列）
- 🔄 Session 管理（支持临时知识库）

### 新增功能
- ✅ 用户文档上传（PDF、Excel、Word、图片）
- ✅ 接口自动识别和提取
- ✅ 会话级临时知识库存储

---

## 改造点详细描述规范

改造点描述必须包含四个要素：

```
改造点名称：[简洁的功能名称]
描述：[新增/调整] [页面名称]，包含：[UI功能列表]。
业务规则：[简单的业务逻辑说明]。
接口：[具体接口名] 或 [新增N个接口]
```

### 示例

**例1：新增页面**
```
改造点名称：预警规则配置页面
描述：新增配置页面，包含：启用/禁用开关、参数输入(5+字段)、优先级设置、导出配置清单。
业务规则：支持灵活配置预警触发条件。
接口：getRule、saveRule、deleteRule
```

**例2：调整已有页面**
```
改造点名称：订单列表页搜索功能调整
描述：在订单列表页新增时间范围搜索，包含：开始日期、结束日期输入框。
业务规则：支持按下单时间段筛选订单。
接口：新增1个接口（searchByDateRange）
```

**例3：后台处理**
```
改造点名称：预警触发与通知
描述：自动化触发机制，当规则条件满足时自动发送预警，无需前端页面。
业务规则：后台自动判断，实时推送预警消息给销售员。
接口：新增2个接口（checkCondition、sendMessage）
```

---

## 改造执行清单

### 第一阶段：代码删除（第1-3步）

#### 步骤1：删除 evaluation_models.py

**文件**：`agent/evaluation_models.py`  
**操作**：完全删除此文件  
**影响范围**：
- 删除 5 种评估模型类（FunctionPoint、COCOMO、StoryPoint、RuleBased、Composite）
- 所有模型逻辑都被移除

**检查点**：
- [ ] 删除文件
- [ ] 搜索 `import evaluation_models` 并删除所有导入
- [ ] 搜索 `from agent.evaluation_models` 并删除所有导入

---

#### 步骤2：删除 excel/reader.py

**文件**：`excel/reader.py`  
**操作**：完全删除此文件  
**功能**：
- Excel 文件读取和解析

**检查点**：
- [ ] 删除文件
- [ ] 搜索 `from excel import reader` 并删除所有导入
- [ ] 搜索 `reader.read_requirements` 并删除所有调用

---

#### 步骤3：删除 app.py 中的批量处理路由

**文件**：`app.py`  
**操作**：删除以下内容

**删除的路由**：
```python
@app.route("/upload", methods=["POST"])           # 约 799-852 行
@app.route("/process", methods=["POST"])          # 约 855-897 行
@app.route("/progress/<task_id>")                 # 约 900-917 行
@app.route("/process_text", methods=["POST"])     # 约 920-962 行
@app.route("/evaluate", methods=["POST"])         # 约 993-1023 行
@app.route("/evaluate_batch", methods=["POST"])   # 约 1026-1062 行
```

**删除的全局变量**：
```python
uploaded_files = {}      # 约 197 行
task_queues = {}         # 约 198 行
task_timestamps = {}     # 约 199 行
```

**删除的函数**：
```python
def cleanup_expired_tasks():        # 约 202-213 行
cleanup_thread = threading.Thread(...) # 约 215-217 行
def allowed_file(filename):         # 约 220-221 行
```

**检查点**：
- [ ] 删除上述所有路由
- [ ] 删除相关的全局变量
- [ ] 删除清理线程相关代码
- [ ] 搜索 `@app.route("/download/` 确认导出路由需要改造（不删除）

---

### 第二阶段：核心文件改造（第4-11步）

#### 步骤4：改造 agent/session_manager.py - 支持临时知识库

**文件**：`agent/session_manager.py`  
**操作**：修改 Session 类

**添加到 Session.__init__() 中**：
```python
# 用户上传的临时文档（仅内存存储，不持久化）
self.temp_documents = []           # 存储文档信息
self.temp_knowledge_context = ""   # 文档提取的文本内容
```

**添加新方法**：
```python
def add_temp_document(self, doc_info):
    """
    添加临时文档到当前会话
    doc_info: {
        "filename": str,
        "content": str,
        "interfaces": list,
        "upload_time": str
    }
    """
    self.temp_documents.append(doc_info)
    self.update_knowledge_context()

def update_knowledge_context(self):
    """更新知识库上下文文本"""
    context_parts = []
    for doc in self.temp_documents:
        context_parts.append(f"【{doc['filename']}】\n{doc['content']}")
    self.temp_knowledge_context = "\n".join(context_parts)

def get_temp_knowledge_context(self):
    """获取临时知识库上下文"""
    return self.temp_knowledge_context

def clear_temp_documents(self):
    """清理临时文档（会话结束时调用）"""
    self.temp_documents = []
    self.temp_knowledge_context = ""
```

**改造 _cleanup_expired_sessions() 方法**：
```python
# 在清理过期会话时，调用 session.clear_temp_documents()
session.clear_temp_documents()
```

**检查点**：
- [ ] 添加了 temp_documents 和 temp_knowledge_context
- [ ] 实现了 4 个新方法
- [ ] 清理函数中调用了 clear_temp_documents()

---

#### 步骤5：改造 app.py - 新增 /upload_knowledge 接口

**文件**：`app.py`  
**操作**：新增路由

**在 app.py 中添加导入**：
```python
from werkzeug.utils import secure_filename
# 已有，确认存在
```

**新增函数**（在 /chat 路由之前）：
```python
@app.route("/upload_knowledge", methods=["POST"])
def upload_knowledge():
    """
    用户上传知识库文档（用于当前对话的上下文）
    支持：PDF、Excel、Word、图片、文本
    文档仅存储在内存，会话结束自动清理
    """
    if "file" not in request.files:
        return jsonify({"error": "未收到文件"}), 400
    
    session_id = request.form.get("session_id")
    if not session_id:
        return jsonify({"error": "session_id 为空"}), 400
    
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "文件名为空"}), 400
    
    try:
        filename = secure_filename(f.filename)
        file_bytes = f.read()
        
        # 解析文档内容
        ext = os.path.splitext(filename)[1].lower()
        doc_content = _parse_document(file_bytes, ext, filename)
        
        if not doc_content:
            return jsonify({"error": "无法解析该文件格式"}), 400
        
        # 限制内容长度（防止过大的上下文）
        max_content_length = 10000
        if len(doc_content) > max_content_length:
            doc_content = doc_content[:max_content_length] + "\n... [文档过长，已截断]"
        
        # 提取接口信息
        interfaces = _extract_interfaces(doc_content)
        
        # 添加到会话的临时文档
        from agent.session_manager import SessionManager
        session_mgr = SessionManager()
        session = session_mgr.get_session(session_id)
        if not session:
            return jsonify({"error": "会话不存在"}), 404
        
        session.add_temp_document({
            "filename": filename,
            "content": doc_content,
            "interfaces": interfaces,
            "upload_time": datetime.now().isoformat()
        })
        
        logger.info(f"临时文档上传: session={session_id}, file={filename}, size={len(file_bytes)}bytes")
        
        return jsonify({
            "success": True,
            "filename": filename,
            "document_count": len(session.temp_documents),
            "extracted_interfaces": interfaces[:10],  # 只返回前10个
            "message": f"已上传 {filename}，提取到 {len(interfaces)} 个接口"
        })
    
    except Exception as e:
        logger.error(f"文档上传失败: {e}")
        return jsonify({"error": f"处理失败: {str(e)}"}), 500


def _parse_document(file_bytes, ext, filename):
    """
    解析不同格式的文档
    支持：PDF、Excel、Word、图片、文本
    """
    try:
        if ext == ".pdf":
            return _parse_pdf(file_bytes)
        elif ext == ".xlsx":
            return _parse_excel(file_bytes)
        elif ext == ".docx":
            return _parse_docx(file_bytes)
        elif ext in [".jpg", ".jpeg", ".png", ".gif", ".bmp"]:
            return _parse_image(file_bytes, ext)
        elif ext in [".txt", ".md", ".log"]:
            return file_bytes.decode('utf-8', errors='ignore')
        else:
            return None
    except Exception as e:
        logger.error(f"文档解析失败 ({filename}): {e}")
        return None


def _parse_pdf(file_bytes):
    """解析PDF文件"""
    try:
        import PyPDF2
        from io import BytesIO
        
        pdf_file = BytesIO(file_bytes)
        reader = PyPDF2.PdfReader(pdf_file)
        text_parts = []
        
        for page in reader.pages:
            text_parts.append(page.extract_text())
        
        return "\n".join(text_parts)
    except Exception as e:
        logger.error(f"PDF解析失败: {e}")
        return None


def _parse_excel(file_bytes):
    """解析Excel文件"""
    try:
        from openpyxl import load_workbook
        from io import BytesIO
        
        excel_file = BytesIO(file_bytes)
        wb = load_workbook(excel_file)
        text_parts = []
        
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            text_parts.append(f"\n=== {sheet_name} ===\n")
            
            # 读取前100行
            for idx, row in enumerate(ws.iter_rows(values_only=True)):
                if idx > 100:
                    text_parts.append("... [表格过长，已截断]")
                    break
                row_text = " | ".join(str(cell) if cell is not None else "" for cell in row)
                text_parts.append(row_text)
        
        return "\n".join(text_parts)
    except Exception as e:
        logger.error(f"Excel解析失败: {e}")
        return None


def _parse_docx(file_bytes):
    """解析Word文件"""
    try:
        from docx import Document
        from io import BytesIO
        
        docx_file = BytesIO(file_bytes)
        doc = Document(docx_file)
        text_parts = []
        
        # 读取段落
        for para in doc.paragraphs:
            text_parts.append(para.text)
        
        # 读取表格
        for table in doc.tables:
            text_parts.append("\n[表格]\n")
            for row in table.rows:
                row_text = " | ".join(cell.text for cell in row.cells)
                text_parts.append(row_text)
        
        return "\n".join(text_parts)
    except Exception as e:
        logger.error(f"Word解析失败: {e}")
        return None


def _parse_image(file_bytes, ext):
    """解析图片文件"""
    try:
        from PIL import Image
        from io import BytesIO
        
        img = Image.open(BytesIO(file_bytes))
        
        # 尝试使用OCR（可选）
        try:
            import pytesseract
            text = pytesseract.image_to_string(img, lang='chi_sim+eng')
            if text.strip():
                return text
        except:
            pass
        
        # OCR失败时返回图片信息
        return f"[图片文件: {ext}]\n尺寸: {img.size}\n模式: {img.mode}"
    
    except Exception as e:
        logger.error(f"图片解析失败: {e}")
        return f"[无法解析的图片文件]\n错误: {str(e)}"


def _extract_interfaces(doc_content):
    """
    从文档内容中提取接口名称
    支持多种格式
    """
    import re
    
    interfaces = set()
    
    # 接口名称识别模式
    patterns = [
        r'(?:接口|API|api|endpoint)[\s：:]*([a-zA-Z0-9_\.\-/]+)',
        r'(?:方法|Method)[\s：:]*(?:GET|POST|PUT|DELETE)\s+(/[a-zA-Z0-9_/\-]*)',
        r'def\s+([a-zA-Z0-9_]+)\s*\(',
        r'function\s+([a-zA-Z0-9_]+)\s*\(',
        r'public\s+(?:void|String|int|boolean)\s+([a-zA-Z0-9_]+)\s*\(',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, doc_content)
        interfaces.update(matches)
    
    return list(interfaces)[:20]  # 最多返回20个
```

**检查点**：
- [ ] 添加了 /upload_knowledge 路由
- [ ] 实现了 6 个文档解析函数
- [ ] 实现了接口提取函数
- [ ] 正确处理了文件大小限制
- [ ] 会话不存在时返回404

---

#### 步骤6：改造 /chat 接口 - 支持临时知识库和表格输出

**文件**：`app.py` 的 `/chat` 路由  
**操作**：修改现有路由

**在评估前获取临时知识库**：
```python
# 在调用 worktime_agent.run_chat() 之前添加
session_knowledge = session.get_temp_knowledge_context()
```

**改造调用 worktime_agent.run_chat()**：
```python
# 改造前
result = worktime_agent.run_chat(
    text=full_text,
    model_id=model_id,
    context=history_ctx,
    skill_id=skill_id,
    last_evaluation=last_evaluation,
)

# 改造后
result = worktime_agent.run_chat(
    text=full_text,
    model_id=model_id,
    context=history_ctx,
    skill_id=skill_id,
    last_evaluation=last_evaluation,
    session_knowledge=session_knowledge  # 新增参数
)
```

**改造输出格式**：
```python
# 将评估结果格式化为表格
from agent.worktime_agent import format_evaluation_as_table
formatted_result = format_evaluation_as_table(result)

# 用表格格式替代原来的 formatted_result
```

**检查点**：
- [ ] 添加了获取临时知识库的代码
- [ ] 传递了 session_knowledge 参数
- [ ] 使用了表格格式化函数

---

#### 步骤7：改造 /chat/stream 接口 - 支持表格输出

**文件**：`app.py` 的 `/chat/stream` 路由  
**操作**：同步改造 /chat 接口

**改造内容**：
- 获取临时知识库
- 传递给 worktime_agent.run_chat()
- 使用表格格式的思路步骤输出
- 最终结果用表格格式

**检查点**：
- [ ] 获取临时知识库
- [ ] 传递参数
- [ ] 表格格式输出

---

#### 步骤8：改造 agent/worktime_agent.py - 核心改造

**文件**：`agent/worktime_agent.py`  
**操作**：重大改造

**改造 run_chat() 函数签名**：
```python
# 改造前
def run_chat(text, model_id, context, skill_id, last_evaluation):

# 改造后
def run_chat(text, model_id, context, skill_id, last_evaluation, session_knowledge=None):
    # 如果有临时知识库，将其插入到上下文开头
    if session_knowledge:
        context = f"""【用户上传的参考文档】
{session_knowledge}

【历史对话】
{context}"""
```

**改造分解结果数据结构**：
```python
# 每个改造点应该包含
{
    "id": 1,
    "title": "改造点名称",
    "description": "业务视角的描述（包含页面、UI功能、业务规则）",
    "interfaces": ["interface1", "interface2"],  # 新增字段
    "effort": {
        "product": 1.0,
        "frontend": 1.0,
        "backend": 3.0,
        "test": 1.0,
        "total": 6.0
    }
}
```

**新增函数 - 表格格式化**：
```python
def format_evaluation_as_table(evaluation_result):
    """
    将评估结果格式化为表格格式
    用于对话展示和导出
    """
    # 实现表格生成逻辑
    # 返回格式化的表格字符串
```

**新增函数 - 接口提取**：
```python
def extract_interfaces_from_decomposition(item, user_knowledge=None):
    """
    从改造点描述中识别接口信息
    """

def search_interfaces_in_docs(decomposition_title, user_knowledge):
    """
    在用户上传的文档中搜索相关接口
    """
```

**改造 - 移除多模型逻辑**：
- 删除所有模型选择代码
- 删除所有模型权重计算
- 只保留基于"中台标准"的评估

**检查点**：
- [ ] 修改了 run_chat() 签名
- [ ] 处理了临时知识库的上下文拼装
- [ ] 改造了分解结果数据结构
- [ ] 实现了表格格式化函数
- [ ] 删除了所有多模型相关代码

---

#### 步骤9：改造 agent/nodes/feature_rebuilder.py - 业务视角描述

**文件**：`agent/nodes/feature_rebuilder.py`  
**操作**：改造改造点生成逻辑

**改造改造点描述生成**：
```
确保改造点描述包含：
1. 页面操作：新增/调整 [页面名称]
2. UI功能：包含的具体功能（查询条件、导入导出等）
3. 业务规则：业务意义和逻辑说明
4. 接口信息：具体接口名或接口数量

格式：
[新增/调整] [页面名称]，包含：[UI功能列表]。
业务规则：[业务逻辑]。

示例：
新增配置页面，包含：启用/禁用开关、参数输入(5+字段)、优先级设置、导出。
业务规则：支持灵活配置预警触发条件。
```

**检查点**：
- [ ] 改造点名称是业务语言（不是技术术语）
- [ ] 描述包含4个要素
- [ ] 没有技术细节（后台任务、规则引擎等）
- [ ] 改造点能清晰表达业务价值

---

#### 步骤10：改造 agent/nodes/worktime_estimator.py - 移除多模型

**文件**：`agent/nodes/worktime_estimator.py`  
**操作**：简化评估逻辑

**删除**：
- 所有模型选择逻辑
- 所有模型权重计算
- 所有模型对比逻辑

**保留**：
- 中台标准评估规则
- 四端工时计算逻辑
- 基础的规则匹配

**检查点**：
- [ ] 删除了所有多模型代码
- [ ] 保留了中台标准评估
- [ ] 工时计算逻辑正确

---

#### 步骤11：改造 excel/writer.py - 新增接口列

**文件**：`excel/writer.py`  
**操作**：修改 write_evaluation_to_excel() 函数

**新增列**：
```
表头：序号 | 原始需求 | 改造点 | 改造点描述 | 接口列表 | 产品(天) | 前端(天) | 后端(天) | 测试(天) | 合计(天)

数据行：
| 1 | [需求] | [改造点名] | [描述] | [接口] | 1.0 | 1.0 | 3.0 | 1.0 | 6.0 |
```

**处理方式**：
- 一个需求对应多个改造点，需求列重复显示
- 接口列显示提取的接口名称或"新增N个接口"
- 合计行显示四端工时总和

**检查点**：
- [ ] 添加了接口列
- [ ] 正确处理了一对多关系
- [ ] 合计行计算正确

---

### 第三阶段：测试和验证（第12-13步）

#### 步骤12：功能测试

**测试场景1：对话评估**
```
输入：新增经销商账期预警功能...
预期输出：表格格式（不是文字格式）
验证：
  ☑ 表格包含序号、改造点名、描述、接口、工时列
  ☑ 改造点描述是业务语言
  ☑ 接口列显示具体接口或接口数量
```

**测试场景2：上传文档**
```
上传：接口文档.pdf
预期：
  ☑ 文件成功解析
  ☑ 提取到接口列表
  ☑ 返回提取的接口信息
验证：
  ☑ 文档仅存内存（查看日志）
  ☑ 会话结束自动清理
```

**测试场景3：带文档的对话**
```
先上传文档，再对话
预期：改造点描述中包含上传文档中的接口名
验证：
  ☑ 接口列显示具体名称（来自上传文档）
  ☑ 不显示通用的"新增N个接口"
```

**测试场景4：Excel 导出**
```
对话后导出
预期：Excel包含新的表格格式
验证：
  ☑ 包含接口列
  ☑ 一个需求对应多行（每行一个改造点）
  ☑ 合计行正确
```

**检查点清单**：
- [ ] 对话输出为表格格式
- [ ] 改造点描述符合业务视角规范
- [ ] 文档上传解析成功
- [ ] 接口提取正确
- [ ] Excel 导出格式正确
- [ ] 会话临时文档正确清理

---

#### 步骤13：回归测试和清理

**验证未受影响的功能**：
```
☑ 会话管理（创建、历史、删除）
☑ LLM 模型切换
☑ 技能切换和加载
☑ 知识库加载
☑ 评估规则应用
```

**代码检查**：
```
☑ 没有死代码
☑ 没有孤立的 import 语句
☑ 日志记录清晰
☑ 错误处理完整
```

**文档更新**：
```
☑ README.md - 更新功能说明
☑ API 文档 - 添加 /upload_knowledge，删除 /upload 等
☑ 代码注释 - 确认清晰
```

---

## 执行进度追踪

| 步骤 | 任务 | 状态 | 完成日期 |
|------|------|------|---------|
| 1 | 删除 evaluation_models.py | ⏳ 待执行 | |
| 2 | 删除 excel/reader.py | ⏳ 待执行 | |
| 3 | 删除 app.py 批量处理路由 | ⏳ 待执行 | |
| 4 | 改造 session_manager.py | ⏳ 待执行 | |
| 5 | 新增 /upload_knowledge 接口 | ⏳ 待执行 | |
| 6 | 改造 /chat 接口 | ⏳ 待执行 | |
| 7 | 改造 /chat/stream 接口 | ⏳ 待执行 | |
| 8 | 改造 worktime_agent.py | ⏳ 待执行 | |
| 9 | 改造 feature_rebuilder.py | ⏳ 待执行 | |
| 10 | 改造 worktime_estimator.py | ⏳ 待执行 | |
| 11 | 改造 excel/writer.py | ⏳ 待执行 | |
| 12 | 功能测试 | ⏳ 待执行 | |
| 13 | 回归测试和清理 | ⏳ 待执行 | |

---

## 注意事项

1. **备份代码**：执行前确保已备份当前代码
2. **逐步提交**：每个步骤完成后提交一次 git commit
3. **充分测试**：每个步骤完成后进行对应的测试
4. **保持通信**：如果遇到问题，及时反馈和讨论
5. **文档同步**：更新代码的同时更新相关文档

---

**创建者**：Claude Code  
**创建时间**：2026-04-25  
**计划完成时间**：待定
