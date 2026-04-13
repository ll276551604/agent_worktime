# -*- coding: utf-8 -*-
import os
import sys
import uuid
import json
import queue
import threading
import time
import logging

from flask import Flask, request, jsonify, Response, send_file, render_template
from werkzeug.utils import secure_filename

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import UPLOAD_FOLDER, OUTPUT_FOLDER, MAX_UPLOAD_SIZE, AVAILABLE_MODELS, DEFAULT_MODEL

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

from excel import reader
from agent import worktime_agent

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE
app.config['TIMEOUT'] = 300  # 5分钟超时

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# 存储上传文件信息和任务进度队列
uploaded_files = {}   # file_id -> filepath
task_queues   = {}    # task_id -> Queue
task_timestamps = {}  # task_id -> 创建时间戳，用于清理超时任务

# 定期清理超时任务（每30秒检查一次）
def cleanup_expired_tasks():
    while True:
        try:
            now = time.time()
            expired_tasks = [tid for tid, ts in task_timestamps.items() if now - ts > 3600]  # 1小时超时
            for tid in expired_tasks:
                task_queues.pop(tid, None)
                task_timestamps.pop(tid, None)
                logger.info(f"清理超时任务: {tid}")
        except Exception as e:
            logger.error(f"清理任务时出错: {e}")
        time.sleep(30)

# 启动清理线程
cleanup_thread = threading.Thread(target=cleanup_expired_tasks, daemon=True)
cleanup_thread.start()


def allowed_file(filename: str) -> bool:
    return filename.lower().endswith(".xlsx")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/models")
def models():
    return jsonify({
        "models":  [{"id": m["id"], "label": m["label"]} for m in AVAILABLE_MODELS],
        "default": DEFAULT_MODEL,
    })


# ============================================================
# 会话管理接口
# ============================================================
@app.route("/session/create", methods=["POST"])
def create_session():
    """创建新会话"""
    from agent.session_manager import SessionManager
    sm = SessionManager()
    session = sm.create_session()
    logger.info(f"创建会话: {session.session_id}")
    return jsonify({
        "session_id": session.session_id,
        "message": "会话创建成功",
    })


@app.route("/session/<session_id>/history")
def get_session_history(session_id):
    """获取会话历史"""
    from agent.session_manager import SessionManager
    sm = SessionManager()
    session = sm.get_session(session_id)
    if not session:
        return jsonify({"error": "会话不存在"}), 404
    return jsonify({
        "session_id": session_id,
        "history": session.get_history(),
    })


@app.route("/session/<session_id>/delete", methods=["POST"])
def delete_session(session_id):
    """删除会话"""
    from agent.session_manager import SessionManager
    sm = SessionManager()
    sm.delete_session(session_id)
    return jsonify({"message": "会话已删除"})


@app.route("/chat", methods=["POST"])
def chat():
    """聊天接口（支持多轮对话和智能评估）"""
    from agent.session_manager import SessionManager, ChatSession
    
    sm = SessionManager()
    data = request.get_json()
    
    session_id = data.get("session_id")
    message    = (data.get("message") or "").strip()
    model_id   = data.get("model_id", DEFAULT_MODEL)

    if not message:
        return jsonify({"error": "消息内容为空"}), 400

    # 获取或创建会话
    if session_id:
        session = sm.get_session(session_id)
    else:
        session = sm.create_session()
        session_id = session.session_id

    if not session:
        session = sm.create_session()
        session_id = session.session_id

    # 添加用户消息到会话
    session.add_message("user", message)
    
    # 获取上下文（最近5条消息）
    context = session.get_context_prompt(5)
    
    logger.info(f"聊天请求: session={session_id}, message_length={len(message)}")

    # 使用智能评估模型处理需求
    try:
        eval_result = worktime_agent.evaluate_text_requirement(message, "composite")
        session.add_message("assistant", eval_result.get("formatted_result", ""))
        
        return jsonify({
            "success": True,
            "session_id": session_id,
            "analysis": eval_result["analysis"],
            "decomposition": eval_result["decomposition"],
            "evaluation": eval_result["evaluation"],
        })
    except Exception as e:
        logger.error(f"智能评估失败: {e}")
        # 如果智能评估失败，回退到传统流程
        task_id = str(uuid.uuid4())
    q = queue.Queue()
    task_queues[task_id] = q
    task_timestamps[task_id] = time.time()

    def run():
        def progress_cb(current, total, row_num, status, preview, page_count=0):
            q.put({
                "current":    current,
                "total":      total,
                "row":        row_num,
                "status":     status,
                "preview":    preview,
                "page_count": page_count,
            })

        try:
            result = worktime_agent.run_chat(
                message, 
                model_id=model_id, 
                progress_callback=progress_cb,
                context=context
            )
            
            # 添加助手回复到会话
            session.add_message("assistant", result["g_text"])
            
            q.put({
                "done":        True,
                "session_id":  session_id,
                "g_text":      result["g_text"],
                "total_days":  result["total_days"],
                "page_count":  result["page_count"],
                "is_question": result.get("is_question", False),
            })
            logger.info(f"聊天完成: session={session_id}, days={result['total_days']}")
        except Exception as e:
            logger.error(f"聊天失败: session={session_id}, error={e}")
            q.put({"error": str(e)})

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"task_id": task_id, "session_id": session_id})


@app.route("/upload", methods=["POST"])
def upload():
    logger.info("收到文件上传请求")
    if "file" not in request.files:
        logger.warning("上传请求中未包含文件")
        return jsonify({"error": "未收到文件"}), 400

    f = request.files["file"]
    if not f.filename:
        logger.warning("上传文件名为空")
        return jsonify({"error": "文件名为空"}), 400
    if not allowed_file(f.filename):
        logger.warning(f"不支持的文件格式: {f.filename}")
        return jsonify({"error": "仅支持 .xlsx 格式"}), 400

    # 保存到独立目录，避免文件名冲突
    file_id = str(uuid.uuid4())
    save_dir = os.path.join(UPLOAD_FOLDER, file_id)
    os.makedirs(save_dir, exist_ok=True)
    filename = secure_filename(f.filename)
    filepath = os.path.join(save_dir, filename)
    f.save(filepath)
    uploaded_files[file_id] = filepath

    # 解析需求行供前端预览
    try:
        rows = reader.read_requirements(filepath)
        logger.info(f"成功解析 Excel 文件: {filename}, 共 {len(rows)} 行需求")
    except Exception as e:
        logger.error(f"解析 Excel 失败: {e}")
        return jsonify({"error": f"解析 Excel 失败：{e}"}), 400

    preview_rows = [
        {
            "row":        r["row"],
            "module":     r["module"],
            "feature":    r["feature"],
            "detail":     r["detail"][:60] + ("..." if len(r["detail"]) > 60 else ""),
            "has_g":      bool(r["existing_g"]),
            "has_n":      r["existing_n"] is not None,
        }
        for r in rows
    ]

    return jsonify({
        "file_id":  file_id,
        "filename": filename,
        "total":    len(rows),
        "rows":     preview_rows,
    })


@app.route("/process", methods=["POST"])
def process():
    data = request.get_json()
    file_id     = data.get("file_id")
    model_id    = data.get("model_id", DEFAULT_MODEL)
    skip_filled = data.get("skip_filled", True)

    if not file_id or file_id not in uploaded_files:
        logger.warning(f"无效的 file_id: {file_id}")
        return jsonify({"error": "无效的 file_id，请重新上传"}), 400

    filepath = uploaded_files[file_id]
    task_id  = str(uuid.uuid4())
    q        = queue.Queue()
    task_queues[task_id] = q
    task_timestamps[task_id] = time.time()

    logger.info(f"开始处理文件任务: task_id={task_id}, file={os.path.basename(filepath)}, model={model_id}")

    def run():
        def progress_cb(current, total, row_num, status, preview, page_count=0):
            q.put({
                "current":    current,
                "total":      total,
                "row":        row_num,
                "status":     status,
                "preview":    preview,
                "page_count": page_count,
            })

        try:
            output_path = worktime_agent.run_agent(
                filepath, skip_filled, model_id=model_id, 
                progress_callback=progress_cb
            )
            q.put({"done": True, "filename": os.path.basename(output_path)})
            logger.info(f"文件任务完成: task_id={task_id}, output={os.path.basename(output_path)}")
        except Exception as e:
            logger.error(f"文件任务失败: task_id={task_id}, error={e}")
            q.put({"error": str(e)})

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"task_id": task_id})


@app.route("/progress/<task_id>")
def progress(task_id):
    q = task_queues.get(task_id)
    if not q:
        logger.warning(f"查询进度时任务不存在: {task_id}")
        return jsonify({"error": "任务不存在"}), 404

    def generate():
        while True:
            msg = q.get()
            yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
            if msg.get("done") or msg.get("error"):
                task_queues.pop(task_id, None)
                task_timestamps.pop(task_id, None)
                break

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/process_text", methods=["POST"])
def process_text():
    data     = request.get_json()
    text     = (data.get("text") or "").strip()
    model_id = data.get("model_id", DEFAULT_MODEL)

    if not text:
        logger.warning("文本处理请求内容为空")
        return jsonify({"error": "请输入需求内容"}), 400

    task_id = str(uuid.uuid4())
    q       = queue.Queue()
    task_queues[task_id] = q
    task_timestamps[task_id] = time.time()

    logger.info(f"开始处理文本任务: task_id={task_id}, model={model_id}, text_length={len(text)}")

    def run():
        def progress_cb(current, total, row_num, status, preview, page_count=0):
            q.put({
                "current":    current,
                "total":      total,
                "row":        row_num,
                "status":     status,
                "preview":    preview,
                "page_count": page_count,
            })

        try:
            result = worktime_agent.run_text(text, model_id=model_id, progress_callback=progress_cb)
            q.put({
                "done":       True,
                "g_text":     result["g_text"],
                "total_days": result["total_days"],
                "page_count": result["page_count"],
            })
            logger.info(f"文本任务完成: task_id={task_id}, days={result['total_days']}, pages={result['page_count']}")
        except Exception as e:
            logger.error(f"文本任务失败: task_id={task_id}, error={e}")
            q.put({"error": str(e)})

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"task_id": task_id})


@app.route("/download/<path:filename>")
def download(filename):
    filepath = os.path.join(OUTPUT_FOLDER, filename)
    if not os.path.exists(filepath):
        logger.warning(f"下载文件不存在: {filename}")
        return jsonify({"error": "文件不存在"}), 404
    logger.info(f"文件下载: {filename}")
    return send_file(filepath, as_attachment=True, download_name=filename)


# ============================================================
# 增强评估接口（支持新的评估模型）
# ============================================================
@app.route("/evaluate", methods=["POST"])
def evaluate():
    """
    评估需求（使用新的评估模型）
    :param text: 需求文本
    :param model_name: 评估模型名称 (fpa/cocomo/storypoint/rule/composite)
    :return: 评估结果
    """
    data = request.get_json()
    text = (data.get("text") or "").strip()
    model_name = data.get("model_name", "composite")
    
    if not text:
        return jsonify({"error": "需求内容为空"}), 400
    
    logger.info(f"评估请求: model={model_name}, text_length={len(text)}")
    
    try:
        eval_result = worktime_agent.evaluate_text_requirement(text, model_name)
        formatted_result = worktime_agent.format_evaluation_result(eval_result)
        
        return jsonify({
            "success": True,
            "analysis": eval_result["analysis"],
            "decomposition": eval_result["decomposition"],
            "evaluation": eval_result["evaluation"],
            "formatted_result": formatted_result,
        })
    except Exception as e:
        logger.error(f"评估失败: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/evaluate_batch", methods=["POST"])
def evaluate_batch():
    """
    批量评估需求
    :param requirements: 需求列表，每个需求包含 feature, detail, module
    :param model_name: 评估模型名称
    :return: 批量评估结果
    """
    data = request.get_json()
    requirements = data.get("requirements", [])
    model_name = data.get("model_name", "composite")
    
    if not requirements:
        return jsonify({"error": "需求列表为空"}), 400
    
    logger.info(f"批量评估请求: model={model_name}, count={len(requirements)}")
    
    try:
        # 转换需求格式
        req_list = []
        for req in requirements:
            req_list.append({
                "module": req.get("module", ""),
                "feature": req.get("feature", ""),
                "detail": req.get("detail", ""),
            })
        
        results = worktime_agent.analyze_and_evaluate_requirements(req_list)
        return jsonify({
            "success": True,
            "results": results["results"],
            "total_days": results["total_days"],
            "requirement_count": results["requirement_count"],
        })
    except Exception as e:
        logger.error(f"批量评估失败: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/export_evaluation", methods=["POST"])
def export_evaluation():
    """
    导出评估结果到Excel
    :param results: 评估结果数据
    :return: 文件下载路径
    """
    data = request.get_json()
    results = data.get("results")
    
    if not results:
        return jsonify({"error": "评估结果为空"}), 400
    
    logger.info(f"导出请求: count={len(results.get('results', []))}")
    
    try:
        # 生成导出文件路径
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_filename = f"evaluation_result_{timestamp}.xlsx"
        output_path = os.path.join(OUTPUT_FOLDER, output_filename)
        
        worktime_agent.export_to_excel(results, output_path)
        
        return jsonify({
            "success": True,
            "filename": output_filename,
            "download_url": f"/download/{output_filename}",
            "total_days": results.get("total_days", 0),
        })
    except Exception as e:
        logger.error(f"导出失败: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/knowledge/reload", methods=["POST"])
def reload_knowledge():
    """重新加载知识库（热更新）"""
    from agent.knowledge_manager import get_knowledge_manager
    
    kb_manager = get_knowledge_manager()
    kb_manager.kb_cache = {}
    kb_manager.code_kb_cache = {}
    
    try:
        all_kb = kb_manager.load_all_knowledge()
        logger.info("知识库重新加载成功")
        return jsonify({
            "success": True,
            "message": "知识库重新加载成功",
            "system_caps_count": len(all_kb.get("system_caps", {})),
            "business_docs_count": len(all_kb.get("business_docs", [])),
            "code_modules_count": len(all_kb.get("code_knowledge", {}).get("modules", [])),
        })
    except Exception as e:
        logger.error(f"知识库加载失败: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/knowledge/analyze", methods=["POST"])
def analyze_requirement():
    """
    分析需求（判断新增/调整，识别相关模块）
    :param text: 需求文本
    :return: 分析结果
    """
    data = request.get_json()
    text = (data.get("text") or "").strip()
    
    if not text:
        return jsonify({"error": "需求内容为空"}), 400
    
    logger.info(f"需求分析请求: text_length={len(text)}")
    
    try:
        from agent.knowledge_manager import get_knowledge_manager
        
        kb_manager = get_knowledge_manager()
        
        lines = text.split('\n')
        feature = lines[0].strip()[:80]
        detail_lines = [l for l in lines[1:] if l.strip()]
        detail = '\n'.join(detail_lines) if detail_lines else text
        
        req = {
            "module": "",
            "feature": feature,
            "detail": detail,
        }
        
        analysis = kb_manager.analyze_requirement(req)
        decomposition = kb_manager.suggest_decomposition(req)
        
        return jsonify({
            "success": True,
            "analysis": analysis,
            "decomposition": decomposition,
        })
    except Exception as e:
        logger.error(f"需求分析失败: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    logger.info("启动 AI 工时评估助手服务")
    app.run(host="0.0.0.0", port=5000, debug=True)
