# -*- coding: utf-8 -*-
import os
import sys
import uuid
import json
import queue
import threading

from flask import Flask, request, jsonify, Response, send_file, render_template
from werkzeug.utils import secure_filename

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import UPLOAD_FOLDER, OUTPUT_FOLDER, MAX_UPLOAD_SIZE, AVAILABLE_MODELS, DEFAULT_MODEL
from excel import reader
from agent import worktime_agent

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# 存储上传文件信息和任务进度队列
uploaded_files = {}   # file_id -> filepath
task_queues   = {}    # task_id -> Queue


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


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "未收到文件"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "文件名为空"}), 400
    if not allowed_file(f.filename):
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
    except Exception as e:
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
        return jsonify({"error": "无效的 file_id，请重新上传"}), 400

    filepath = uploaded_files[file_id]
    task_id  = str(uuid.uuid4())
    q        = queue.Queue()
    task_queues[task_id] = q

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
                filepath, skip_filled, model_id=model_id, progress_callback=progress_cb
            )
            q.put({"done": True, "filename": os.path.basename(output_path)})
        except Exception as e:
            q.put({"error": str(e)})

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"task_id": task_id})


@app.route("/progress/<task_id>")
def progress(task_id):
    q = task_queues.get(task_id)
    if not q:
        return jsonify({"error": "任务不存在"}), 404

    def generate():
        while True:
            msg = q.get()
            yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
            if msg.get("done") or msg.get("error"):
                task_queues.pop(task_id, None)
                break

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/download/<path:filename>")
def download(filename):
    filepath = os.path.join(OUTPUT_FOLDER, filename)
    if not os.path.exists(filepath):
        return jsonify({"error": "文件不存在"}), 404
    return send_file(filepath, as_attachment=True, download_name=filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
