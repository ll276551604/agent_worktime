# -*- coding: utf-8 -*-
import os
import sys
import uuid
import json
import queue
import threading
import time
import logging
from logging.handlers import RotatingFileHandler

from flask import Flask, request, jsonify, Response, send_file, render_template
from werkzeug.utils import secure_filename

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import UPLOAD_FOLDER, OUTPUT_FOLDER, MAX_UPLOAD_SIZE, AVAILABLE_MODELS, DEFAULT_MODEL, AppConfig


def setup_logging():
    """配置日志系统"""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # 避免重复添加处理器
    if logger.handlers:
        logger.handlers.clear()
    
    # 格式设置
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 控制台输出
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 文件输出（自动轮转，保留最近5个文件，每个最大10MB）
    file_handler = RotatingFileHandler(
        'app.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


# 初始化日志
setup_logging()
logger = logging.getLogger(__name__)

# 初始化目录
AppConfig.init_folders()

from excel import reader
from agent import worktime_agent

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE
app.config['TIMEOUT'] = 300  # 5分钟超时


# ============================================================
# 全局异常处理
# ============================================================
@app.errorhandler(Exception)
def handle_exception(e):
    """全局异常处理器"""
    logger.error(f"未处理的异常: {str(e)}", exc_info=True)
    return jsonify({
        "success": False,
        "error": "服务器内部错误，请稍后重试"
    }), 500


@app.errorhandler(400)
def handle_bad_request(e):
    """处理请求参数错误"""
    return jsonify({
        "success": False,
        "error": str(e)
    }), 400


@app.errorhandler(403)
def handle_forbidden(e):
    """处理禁止访问"""
    return jsonify({
        "success": False,
        "error": "访问被拒绝"
    }), 403


@app.errorhandler(404)
def handle_not_found(e):
    """处理资源未找到"""
    return jsonify({
        "success": False,
        "error": "资源未找到"
    }), 404


@app.errorhandler(413)
def handle_request_too_large(e):
    """处理文件过大"""
    return jsonify({
        "success": False,
        "error": f"上传文件大小超过限制（最大 {MAX_UPLOAD_SIZE//1024//1024}MB）"
    }), 413

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
    """聊天接口 — LangGraph 智能拆解 + 可切换技能 + 按角色工时输出"""
    from agent.session_manager import SessionManager
    from agent.dialog_manager import DialogManager
    from agent import skill_manager as sm

    session_mgr = SessionManager()
    dm          = DialogManager()
    data        = request.get_json()

    session_id = data.get("session_id")
    message    = (data.get("message") or "").strip()
    model_id   = data.get("model_id", DEFAULT_MODEL)
    skill_id   = data.get("skill_id") or sm.get_current_skill_id()

    if not message:
        return jsonify({"error": "消息内容为空"}), 400

    # ── 获取/创建会话 ────────────────────────────────────────
    if session_id:
        session = session_mgr.get_session(session_id)
    if not session_id or not session:
        session = session_mgr.create_session()
        session_id = session.session_id

    session.add_message("user", message)
    conversation_history = session.get_messages()
    logger.info(f"聊天请求: session={session_id} skill={skill_id} msg_len={len(message)}")

    intent = dm.analyze_intent(message)
    process_log = [f"意图分析：{intent}"]

    # ── 提取需求信息（模块/类型自动识别） ───────────────────
    info           = dm.extract_requirement_info(conversation_history)
    is_complete    = dm.check_info_complete(info)
    auto_detected  = {
        "module_detected": bool(info.get("auto_detected", {}).get("module")),
        "type_detected":   bool(info.get("auto_detected", {}).get("type")),
    }

    if not is_complete:
        if not info.get('requirement'):
            process_log.append("未识别到有效需求描述，进入引导输入")
        else:
            process_log.append("检测到需求信息不完整，准备追问补充")
            if not info.get('module'):
                process_log.append("模块未识别")
            if not info.get('type'):
                process_log.append("需求类型未识别")

        reply = dm.get_next_question(info) or "请继续描述您的需求内容，我会帮您补全模块和类型。"
        session.add_message("assistant", reply)
        return jsonify({"success": True, "session_id": session_id,
                        "stage": "collecting", "message": reply,
                        "collected_info": info, "auto_detected": auto_detected,
                        "process": process_log})

    # ── 拼装完整需求文本（含模块+类型上下文） ───────────────
    full_text = f"【模块】{info['module']} 【类型】{info['type']} 【描述】{info['requirement']}"
    process_log.append(f"提取到需求：{info['requirement'][:80]}")
    if info.get('module'):
        process_log.append(f"模块识别：{info['module']} ({'自动' if auto_detected['module_detected'] else '默认'})")
    else:
        process_log.append("模块未识别，使用默认模块")
    if info.get('type'):
        process_log.append(f"需求类型识别：{info['type']} ({'自动' if auto_detected['type_detected'] else '默认'})")
    else:
        process_log.append("需求类型未识别，默认视为新增功能")
    process_log.append("开始执行需求拆解与工时评估")

    # ── 获取历史对话上下文（最近 3 轮）──────────────────────
    history_ctx = ""
    msgs = conversation_history[:-1]  # 排除刚加入的本条
    if msgs:
        recent = msgs[-6:]
        history_ctx = "\n".join(f"{m['role']}: {m['content'][:200]}" for m in recent)

    try:
        result = worktime_agent.run_chat(
            text=full_text,
            model_id=model_id,
            context=history_ctx,
            skill_id=skill_id,
        )
    except Exception as e:
        logger.error(f"LangGraph 评估失败: {e}", exc_info=True)
        return jsonify({"error": f"评估失败: {str(e)}"}), 500

    # ── 需要澄清：需求描述过于简短 ──────────────────────────
    if result.get("needs_clarification"):
        process_log.append("评估结果认为需求描述过短，需要补充信息")
        question = result["clarification_question"]
        session.add_message("assistant", question)
        return jsonify({"success": True, "session_id": session_id,
                        "stage": "clarifying", "message": question,
                        "collected_info": info, "auto_detected": auto_detected,
                        "process": process_log})

    # ── 追问模式（已有上下文，用户在追问） ──────────────────
    if result.get("is_question"):
        process_log.append("检测到用户追问，直接生成回答")
        session.add_message("assistant", result["g_text"])
        return jsonify({"success": True, "session_id": session_id,
                        "stage": "answering", "formatted_result": result["g_text"],
                        "collected_info": info, "process": process_log})

    # ── 正常评估结果 ─────────────────────────────────────────
    pages_features = result.get("pages_features", [])
    role_breakdown = result.get("role_breakdown", {})
    formatted_result = result["g_text"]

    # 智能识别提示头
    note_parts = []
    if auto_detected["module_detected"]:
        note_parts.append(f"模块：{info['module']}")
    if auto_detected["type_detected"]:
        note_parts.append(f"类型：{info['type']}")
    if note_parts:
        formatted_result = f"【智能识别】{'、'.join(note_parts)}\n\n" + formatted_result

    process_log.append("评估完成，生成最终拆解与工时结果")
    session.add_message("assistant", formatted_result)
    logger.info(f"评估完成: session={session_id} skill={skill_id} "
                f"pages={len(pages_features)} days={result['total_days']}")

    return jsonify({
        "success": True,
        "session_id": session_id,
        "stage": "assessment",
        "skill_id": skill_id,
        # 主要输出
        "g_text":        result["g_text"],
        "total_days":    result["total_days"],
        "role_breakdown": role_breakdown,
        "pages_features": pages_features,
        # 向下兼容字段
        "decomposition": [
            {"type": p["类型"], "name": p["页面"], "features": p["功能点"]}
            for p in pages_features
        ],
        "evaluation": {
            "model": f"skill:{skill_id}",
            "effort_days": result["total_days"],
            "role_breakdown": role_breakdown,
        },
        "formatted_result": formatted_result,
        "collected_info":   info,
        "auto_detected":    auto_detected,
        "process":          process_log,
    })


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
    # 1. 安全过滤文件名（移除路径字符）
    safe_filename = secure_filename(filename)
    
    # 2. 构建完整路径
    filepath = os.path.join(OUTPUT_FOLDER, safe_filename)
    
    # 3. 强制校验：确保路径在允许范围内
    abs_output_folder = os.path.abspath(OUTPUT_FOLDER)
    abs_filepath = os.path.abspath(filepath)
    
    if not abs_filepath.startswith(abs_output_folder):
        logger.warning(f"非法路径访问尝试: {filename}")
        return jsonify({"error": "无效的文件请求"}), 403
    
    # 4. 检查文件是否存在
    if not os.path.exists(filepath):
        logger.warning(f"下载文件不存在: {filename}")
        return jsonify({"error": "文件不存在"}), 404
    
    logger.info(f"文件下载: {safe_filename}")
    return send_file(filepath, as_attachment=True, download_name=safe_filename)


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


# ============================================================
# 技能管理接口
# ============================================================

@app.route("/skills", methods=["GET"])
def list_skills():
    """列出所有可用技能"""
    from agent import skill_manager as sm
    skills = sm.list_skills()
    current = sm.get_current_skill_id()
    return jsonify({"skills": skills, "current": current})


@app.route("/skills/current", methods=["GET"])
def get_current_skill():
    """获取当前技能详情"""
    from agent import skill_manager as sm
    sid   = sm.get_current_skill_id()
    skill = sm.get_skill(sid)
    return jsonify({"skill_id": sid, "skill": skill})


@app.route("/skills/switch", methods=["POST"])
def switch_skill():
    """切换当前全局技能"""
    from agent import skill_manager as sm
    data     = request.get_json()
    skill_id = (data.get("skill_id") or "").strip()
    if not skill_id:
        return jsonify({"error": "skill_id 不能为空"}), 400
    ok = sm.set_current_skill(skill_id)
    if not ok:
        available = [s["id"] for s in sm.list_skills()]
        return jsonify({"error": f"技能不存在: {skill_id}", "available": available}), 404
    logger.info(f"技能切换: {skill_id}")
    return jsonify({"success": True, "current": skill_id})


@app.route("/skills/<skill_id>", methods=["GET"])
def get_skill(skill_id):
    """获取指定技能的完整配置"""
    from agent import skill_manager as sm
    skill = sm.get_skill(skill_id)
    return jsonify({"skill_id": skill_id, "skill": skill})


@app.route("/skills/reload", methods=["POST"])
def reload_skill():
    """清除技能缓存，强制从文件重新加载（修改 JSON 后调用）"""
    from agent import skill_manager as sm
    data     = request.get_json() or {}
    skill_id = data.get("skill_id")
    if skill_id:
        sm.reload_skill(skill_id)
        logger.info(f"技能缓存已清除: {skill_id}")
        return jsonify({"success": True, "reloaded": skill_id})
    # 清除所有缓存
    sm._skills_cache.clear()
    logger.info("所有技能缓存已清除")
    return jsonify({"success": True, "reloaded": "all"})


@app.route("/skills/<skill_id>/examples", methods=["GET"])
def get_skill_examples(skill_id):
    """获取指定技能的历史评估案例"""
    from agent import skill_manager as sm
    limit    = int(request.args.get("limit", 20))
    examples = sm.load_examples(skill_id, limit=limit)
    return jsonify({"skill_id": skill_id, "count": len(examples), "examples": examples})


@app.route("/skills/<skill_id>/examples", methods=["POST"])
def add_skill_example(skill_id):
    """
    添加一条历史评估案例（用于学习）
    Body: {
      "requirement": {"module": "", "feature": "", "detail": ""},
      "pages_features": [...],
      "worktime": {"role_breakdown": {...}, "total_days": 0, "actual_days": 0, "note": ""}
    }
    """
    from agent import skill_manager as sm
    example = request.get_json()
    if not example or not example.get("requirement"):
        return jsonify({"error": "缺少 requirement 字段"}), 400
    fpath = sm.add_example(example, skill_id=skill_id)
    logger.info(f"新增历史案例: skill={skill_id} file={fpath}")
    return jsonify({"success": True, "file": os.path.basename(fpath)})


@app.route("/knowledge/code", methods=["GET"])
def list_code_knowledge():
    """列出代码知识库中的文件"""
    from agent import skill_manager as sm
    code_dir = sm.CODE_KB_DIR
    if not os.path.exists(code_dir):
        return jsonify({"files": [], "hint": "目录不存在，请创建 knowledge/code_knowledge/ 并放入文档"})
    files = [
        {"name": f, "size": os.path.getsize(os.path.join(code_dir, f))}
        for f in sorted(os.listdir(code_dir))
        if os.path.isfile(os.path.join(code_dir, f)) and not f.startswith(".")
    ]
    return jsonify({"files": files, "directory": code_dir})


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
    app.run(host="0.0.0.0", port=5001, debug=True)
