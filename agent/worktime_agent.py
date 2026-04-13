# -*- coding: utf-8 -*-
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from excel import reader, writer
from agent.graph import build_graph, KnowledgeLoader
from config import REQUEST_DELAY


def run_agent(filepath: str, skip_filled: bool, api_key: str = None,
              model_id: str = None, progress_callback=None) -> str:
    """
    完整工时拆解流程：读取 → LangGraph → 回填 Excel（G列+N列）

    progress_callback: fn(current, total, row_num, status, preview, page_count)
    """
    rows = reader.read_requirements(filepath)
    if not rows:
        raise ValueError("未找到任何需求行，请检查 Excel 格式和工作表名称")

    kb    = KnowledgeLoader().load()
    graph = build_graph()

    total   = len(rows)
    results = []

    for i, row_data in enumerate(rows):
        row_num = row_data["row"]

        # 跳过已填写的行
        if skip_filled and row_data.get("existing_g"):
            results.append({
                "row":          row_num,
                "g_column_text": row_data["existing_g"],
                "days":         row_data["existing_n"],
                "skipped":      True,
            })
            if progress_callback:
                progress_callback(i + 1, total, row_num, "skipped", "（已有内容，跳过）", 0)
            continue

        print(f"[Agent] 开始处理行 {row_num} ({i+1}/{total})", flush=True)
        try:
            state = graph.invoke({
                "raw_requirement":  row_data,
                "model_id":         model_id,
                "kb_feature_rules": kb["kb_feature_rules"],
                "kb_system_caps":   kb["kb_system_caps"],
                "kb_business_docs": kb["kb_business_docs"],
                "pages_features":   [],
                "g_column_text":    "",
                "total_days":       0.0,
                "retry_count":      0,
                "errors":           [],
            })

            g_text     = state.get("g_column_text", "")
            total_days = state.get("total_days", 1.0)
            page_count = len(state.get("pages_features", []))

            results.append({
                "row":           row_num,
                "g_column_text": g_text,
                "days":          total_days,
                "skipped":       False,
            })

            preview = g_text.split("\n")[0][:60] if g_text else ""
            if progress_callback:
                progress_callback(i + 1, total, row_num, "done", preview, page_count)

        except Exception as e:
            results.append({
                "row":           row_num,
                "g_column_text": f"[处理失败] {str(e)}",
                "days":          None,
                "skipped":       False,
            })
            if progress_callback:
                progress_callback(i + 1, total, row_num, "error", str(e), 0)

        if i < total - 1:
            time.sleep(REQUEST_DELAY)

    return writer.write_results(filepath, results)
