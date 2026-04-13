# -*- coding: utf-8 -*-
import time
import sys
import os
import logging
import hashlib
from typing import List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

from excel import reader, writer
from agent.graph import build_graph, KnowledgeLoader
from agent.knowledge_manager import get_knowledge_manager
from agent.evaluation_models import evaluate_requirement
from config import REQUEST_DELAY, AppConfig

# 评估结果缓存（简单的内存缓存）
_evaluation_cache = {}
_CACHE_MAX_SIZE = AppConfig.EVALUATION_CACHE_MAX_SIZE


def _generate_cache_key(req: Dict) -> str:
    """生成需求的唯一缓存键"""
    content = f"{req.get('module','')}|{req.get('feature','')}|{req.get('detail','')}"
    return hashlib.md5(content.encode()).hexdigest()


def _get_cached_result(req: Dict) -> Dict:
    """获取缓存的评估结果"""
    key = _generate_cache_key(req)
    return _evaluation_cache.get(key)


def _set_cached_result(req: Dict, result: Dict):
    """设置评估结果到缓存"""
    key = _generate_cache_key(req)
    
    # 淘汰策略：超过最大缓存数时删除最早的记录
    if len(_evaluation_cache) >= _CACHE_MAX_SIZE:
        oldest_key = next(iter(_evaluation_cache))
        del _evaluation_cache[oldest_key]
    
    _evaluation_cache[key] = result


def run_agent(filepath: str, skip_filled: bool, api_key: str = None,
              model_id: str = None, progress_callback=None) -> str:
    """
    完整工时拆解流程：读取 → 智能评估 → 回填 Excel（G列+N列）

    progress_callback: fn(current, total, row_num, status, preview, page_count)
    """
    rows = reader.read_requirements(filepath)
    if not rows:
        raise ValueError("未找到任何需求行，请检查 Excel 格式和工作表名称")

    kb = KnowledgeLoader().load()
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
            # 使用智能评估模型处理
            requirement = {
                "module": row_data.get("module", ""),
                "feature": row_data.get("feature", ""),
                "detail": row_data.get("detail", "")
            }
            
            # 检查缓存
            cached_result = _get_cached_result(requirement)
            if cached_result:
                logger.info(f"[Agent] 命中缓存: 行 {row_num}")
                eval_result = cached_result
            else:
                eval_result = evaluate_requirement(requirement, "composite")
                _set_cached_result(requirement, eval_result)
            
            g_text = format_eval_result_for_g_column(eval_result)
            total_days = eval_result["evaluation"]["effort_days"]
            page_count = len(eval_result["decomposition"])

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


def format_eval_result_for_g_column(eval_result: dict) -> str:
    """将智能评估结果格式化为 G 列文本"""
    result = []
    
    # 需求分析
    analysis = eval_result.get("analysis", {})
    result.append(f"【需求分析】")
    result.append(f"类型: {analysis.get('judgment', '未知')}（置信度: {analysis.get('confidence', 0)}%）")
    
    # 初步拆解
    decomposition = eval_result.get("decomposition", [])
    if decomposition:
        result.append("")
        result.append("【初步拆解】")
        for part in decomposition:
            result.append(f"【{part.get('type')}】{part.get('name')}")
            for feat in part.get('features', []):
                result.append(f"  - {feat}")
    
    # 工时评估
    evaluation = eval_result.get("evaluation", {})
    result.append("")
    result.append("【工时评估】")
    result.append(f"模型: {evaluation.get('model', '综合评估')}")
    result.append(f"预估工时: {evaluation.get('effort_days', 0)} 天")
    
    # 建议
    suggestions = analysis.get("suggestions", [])
    if suggestions:
        result.append("")
        result.append("【建议】")
        for suggestion in suggestions:
            result.append(f"• {suggestion}")
    
    return "\n".join(result)


def run_text(text: str, model_id: str = None, progress_callback=None) -> dict:
    """
    处理单条文本需求（不写 Excel）。
    progress_callback: fn(current, total, row_num, status, preview, page_count)
    返回: {"g_text": str, "total_days": float, "page_count": int}
    """
    return run_chat(text, model_id=model_id, progress_callback=progress_callback, context="")


def run_chat(text: str, model_id: str = None, progress_callback=None, context: str = "") -> dict:
    """
    处理聊天消息（支持上下文）。
    context: 历史对话上下文
    返回: {"g_text": str, "total_days": float, "page_count": int, "is_question": bool}
    """
    text = text.strip()
    if not text:
        raise ValueError("消息内容为空")

    # 判断是否是追问（非需求拆解请求）
    is_question = _is_question(text)
    
    if is_question and context:
        # 追问模式：直接调用 LLM 回答
        logger.info(f"[Agent-Chat] 追问模式: {text[:40]}")
        response = _answer_question(text, context, model_id)
        return {
            "g_text": response,
            "total_days": 0.0,
            "page_count": 0,
            "is_question": True,
        }

    # 需求拆解模式
    lines = text.split('\n')
    feature = lines[0].strip()[:80]
    detail_lines = [l for l in lines[1:] if l.strip()]
    detail = '\n'.join(detail_lines) if detail_lines else text

    # 如果有上下文，追加到详情中
    if context:
        detail = f"【历史对话】\n{context}\n\n【当前需求】\n{detail}"

    req = {
        "row":        1,
        "module":     "",
        "feature":    feature,
        "detail":     detail,
        "extra":      "",
        "existing_g": None,
        "existing_n": None,
    }

    kb    = KnowledgeLoader().load()
    graph = build_graph()

    logger.info(f"[Agent-Chat] 处理需求: {feature[:40]}, context_length={len(context)}")

    state = graph.invoke({
        "raw_requirement":  req,
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

    if progress_callback:
        preview = g_text.split("\n")[0][:60] if g_text else ""
        progress_callback(1, 1, 1, "done", preview, page_count)

        return {"g_text": g_text, "total_days": total_days, "page_count": page_count, "is_question": False}


def _is_question(text: str) -> bool:
    """判断是否是追问/问题（非需求拆解请求）"""
    question_patterns = [
        r'^[你您][觉认]得.*',
        r'^为什么.*',
        r'^什么.*',
        r'^怎么.*',
        r'^如何.*',
        r'^能不能.*',
        r'^可以.*吗\??$',
        r'^是否.*',
        r'^应该.*',
        r'^如果.*',
        r'.*怎么样\??$',
        r'.*好不好\??$',
        r'.*对吗\??$',
        r'.*是吗\??$',
        r'.*呢\??$',
        r'.*吧\??$',
        r'^再.*',
        r'^继续.*',
        r'^更多.*',
        r'^详细.*',
        r'^解释.*',
        r'^说明.*',
        r'^分析.*',
        r'^比较.*',
        r'^评估.*',
    ]
    
    import re
    text = text.strip()
    for pattern in question_patterns:
        if re.match(pattern, text):
            return True
    return False


def _answer_question(question: str, context: str, model_id: str = None) -> str:
    """回答追问问题"""
    from agent import gemini_client
    
    prompt = f"""你是一位有10年经验的IT项目经理和产品专家。

## 对话历史
{context}

## 当前问题
{question}

## 任务
基于对话历史，回答用户的问题。
如果是关于工时评估的问题，请给出专业建议；
如果是一般性问题，请友好解答。

## 输出要求
- 回答要简明扼要
- 使用自然语言
- 保持专业但友好的语气"""
    
    try:
        response = gemini_client.call_llm(prompt, model_id=model_id)
        return response.strip()
    except Exception as e:
        logger.error(f"回答问题失败: {e}")
        return f"抱歉，我暂时无法回答这个问题。错误: {str(e)}"


def analyze_and_evaluate_requirements(requirements: List[Dict]) -> Dict[str, Any]:
    """
    分析和评估多个需求
    :param requirements: 需求列表，每个需求包含 feature, detail, module
    :return: 评估结果
    """
    kb_manager = get_knowledge_manager()
    
    results = []
    total_days = 0.0
    
    for req in requirements:
        # 使用新的评估模型
        eval_result = evaluate_requirement(req)
        
        results.append({
            "original_requirement": req,
            "analysis": eval_result["analysis"],
            "decomposition": eval_result["decomposition"],
            "evaluation": eval_result["evaluation"],
        })
        
        total_days += eval_result["evaluation"].get("effort_days", 0.0)
    
    return {
        "results": results,
        "total_days": round(total_days, 2),
        "requirement_count": len(requirements),
    }


def export_to_excel(results: Dict[str, Any], output_path: str = None) -> str:
    """
    导出评估结果到Excel
    :param results: 评估结果
    :param output_path: 输出路径，不传则自动生成
    :return: 生成的文件路径
    """
    import openpyxl
    from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
    from openpyxl.utils import get_column_letter
    
    if output_path is None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_path = f"evaluation_result_{timestamp}.xlsx"
    
    # 创建工作簿
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "需求拆解评估"
    
    # 表头样式
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin_border = Border(left=Side(style='thin'), right=Side(style='thin'),
                         top=Side(style='thin'), bottom=Side(style='thin'))
    
    # 表头
    headers = ["序号", "原始需求", "需求类型", "已拆解需求", "产品工时(天)", "评估模型", "备注"]
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = alignment
        cell.border = thin_border
    
    # 填充数据
    row_num = 2
    for i, result in enumerate(results["results"], 1):
        req = result["original_requirement"]
        analysis = result["analysis"]
        evaluation = result["evaluation"]
        
        # 序号
        ws.cell(row=row_num, column=1, value=i).border = thin_border
        
        # 原始需求
        original_req = f"{req.get('module', '')} - {req.get('feature', '')}\n{req.get('detail', '')}"
        ws.cell(row=row_num, column=2, value=original_req).border = thin_border
        
        # 需求类型（新增/调整）
        ws.cell(row=row_num, column=3, value=analysis.get("judgment", "未知")).border = thin_border
        
        # 已拆解需求
        decomposition = result["decomposition"]
        decomposed_text = ""
        for part in decomposition:
            decomposed_text += f"【{part.get('type')}】{part.get('name')}\n"
            for feat in part.get('features', []):
                decomposed_text += f"  - {feat}\n"
        ws.cell(row=row_num, column=4, value=decomposed_text.strip()).border = thin_border
        
        # 产品工时
        ws.cell(row=row_num, column=5, value=evaluation.get("effort_days", 0)).border = thin_border
        
        # 评估模型
        ws.cell(row=row_num, column=6, value=evaluation.get("model", "综合评估")).border = thin_border
        
        # 备注
        related_modules = analysis.get("related_modules", [])
        suggestions = analysis.get("suggestions", [])
        remark = ""
        if related_modules:
            remark += f"相关模块: {', '.join(related_modules)}\n"
        if suggestions:
            remark += "\n".join(suggestions)
        ws.cell(row=row_num, column=7, value=remark.strip()).border = thin_border
        
        row_num += 1
    
    # 添加合计行
    total_row = row_num
    ws.cell(row=total_row, column=1, value="合计").font = Font(bold=True)
    ws.cell(row=total_row, column=1, value="合计").border = thin_border
    ws.cell(row=total_row, column=5, value=results["total_days"]).font = Font(bold=True)
    ws.cell(row=total_row, column=5, value=results["total_days"]).border = thin_border
    
    # 调整列宽
    ws.column_dimensions['A'].width = 8
    ws.column_dimensions['B'].width = 30
    ws.column_dimensions['C'].width = 12
    ws.column_dimensions['D'].width = 40
    ws.column_dimensions['E'].width = 15
    ws.column_dimensions['F'].width = 15
    ws.column_dimensions['G'].width = 30
    
    # 设置行高
    for row in range(1, total_row + 1):
        ws.row_dimensions[row].height = 15
    
    # 保存文件
    wb.save(output_path)
    logger.info(f"评估结果已导出到: {output_path}")
    
    return output_path


def evaluate_text_requirement(text: str, model_name: str = "composite") -> Dict[str, Any]:
    """
    评估文本需求（单条）
    :param text: 需求文本
    :param model_name: 评估模型名称
    :return: 评估结果
    """
    lines = text.split('\n')
    feature = lines[0].strip()[:80]
    detail_lines = [l for l in lines[1:] if l.strip()]
    detail = '\n'.join(detail_lines) if detail_lines else text
    
    req = {
        "module": "",
        "feature": feature,
        "detail": detail,
    }
    
    return evaluate_requirement(req, model_name)


def format_evaluation_result(eval_result: Dict[str, Any]) -> str:
    """
    格式化评估结果为可读文本
    """
    analysis = eval_result["analysis"]
    decomposition = eval_result["decomposition"]
    evaluation = eval_result["evaluation"]
    
    result_text = f"""【需求分析】
类型: {analysis.get('judgment', '未知')}（置信度: {int(analysis.get('confidence', 0)*100)}%）

{'' if not analysis.get('related_modules') else f'相关模块: {", ".join(analysis["related_modules"])}'}
{'' if not analysis.get('existing_features') else f'相似功能: {", ".join(analysis["existing_features"])}'}

【初步拆解】
"""
    
    for part in decomposition:
        result_text += f"【{part.get('type')}】{part.get('name')}\n"
        for feat in part.get('features', []):
            result_text += f"  - {feat}\n"
    
    result_text += f"""
【工时评估】
模型: {evaluation.get('model', '综合评估')}
预估工时: {evaluation.get('effort_days', 0)} 天

{'' if not analysis.get('suggestions') else '【建议】\n' + '\n'.join(analysis['suggestions'])}
"""
    
    return result_text
