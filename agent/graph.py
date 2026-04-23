# -*- coding: utf-8 -*-
"""
LangGraph StateGraph 定义
图流程：rebuild_features → estimate_worktime
条件边：pages_features 为空且 retry_count < 2 时回到 rebuild_features
"""
import json
import os
import re
import sys
from typing import TypedDict, List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langgraph.graph import StateGraph, END

from agent.nodes.feature_rebuilder import rebuild_features
from agent.nodes.worktime_estimator import estimate_worktime
from agent.kb_utils import match_business_context  # noqa: F401
from config import KB_FEATURE_RULES, KB_SYSTEM_CAPS, BUSINESS_KB_DIRS


# ============================================================
# State 定义
# ============================================================
class RequirementState(TypedDict):
    # ── 输入 ──────────────────────────────────────────────────
    raw_requirement:  dict
    kb_feature_rules: dict
    kb_system_caps:   dict
    kb_business_docs: List[dict]
    model_id:         str

    # ── 技能系统（可切换的评估体系）──────────────────────────
    skill_id:       str           # 当前使用的技能 ID
    skill_config:   dict          # 技能完整配置（从 skill_manager 获取）
    skill_examples: List[dict]    # 历史评估案例（few-shot）
    code_context:   str           # 代码知识库相关片段

    # ── 节点1 输出：页面 × 功能点结构 ────────────────────────
    pages_features: List[dict]    # [{页面, 类型, 功能点:[str]}]
    kb_cases:       List[dict]    # 知识库检索结果（B端履约中台技能）

    # ── 节点2 输出：工时估算 ──────────────────────────────────
    g_column_text:  str           # G列最终文本
    total_days:     float         # N列数字（合计天数）
    role_breakdown: Dict[str, float]  # 各角色工时 {"前端开发": 1.5, ...}

    # ── 控制 ──────────────────────────────────────────────────
    retry_count: int
    errors:      List[str]


# ============================================================
# 条件路由：pages_features 为空时重试，最多2次
# ============================================================
def _route_after_rebuild(state: RequirementState) -> str:
    if not state.get("pages_features") and state.get("retry_count", 0) < 2:
        return "rebuild_features"
    return "estimate_worktime"


# ============================================================
# 图组装
# ============================================================
def build_graph():
    graph = StateGraph(RequirementState)

    graph.add_node("rebuild_features",  rebuild_features)
    graph.add_node("estimate_worktime", estimate_worktime)

    graph.set_entry_point("rebuild_features")
    graph.add_conditional_edges(
        "rebuild_features",
        _route_after_rebuild,
        {"rebuild_features": "rebuild_features", "estimate_worktime": "estimate_worktime"},
    )
    graph.add_edge("estimate_worktime", END)

    return graph.compile()


# ============================================================
# 知识库加载（供 worktime_agent 调用）
# ============================================================
class KnowledgeLoader:
    def load(self) -> dict:
        return {
            "kb_feature_rules": self._load_json(KB_FEATURE_RULES),
            "kb_system_caps":   self._load_json(KB_SYSTEM_CAPS),
            "kb_business_docs": self._load_business_docs(),
        }

    def _load_json(self, path: str) -> dict:
        if not os.path.exists(path):
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _load_business_docs(self) -> list:
        docs = []
        for kb_dir in BUSINESS_KB_DIRS:
            if not os.path.exists(kb_dir):
                continue
            for fname in os.listdir(kb_dir):
                fpath = os.path.join(kb_dir, fname)
                if not os.path.isfile(fpath):
                    continue
                try:
                    with open(fpath, encoding="utf-8") as f:
                        content = f.read()
                    lines     = content.split('\n')
                    meta      = lines[0] if lines else ""
                    domain    = self._extract(meta, r'domain:\s*(\S+)') or fname
                    subdomain = self._extract(meta, r'subdomain:\s*([^\s]+(?:\s+[^\s:]+)*?)(?=\s+\w+:)')
                    recall    = self._extract(meta, r'recall_when:\s*"([^"]+)"')
                    digest    = self._extract(meta, r'chapter_digest:\s*(.+?)(?=related_docs:|$)')
                    body      = '\n'.join(l for l in lines[5:65] if l.strip())

                    terms = set()
                    for t in [fname, domain, subdomain or "", recall or ""]:
                        for w in re.split(r'[\s/·，。、]+', t):
                            if len(w) >= 2:
                                terms.add(w.lower())

                    docs.append({
                        "name": fname, "domain": domain,
                        "subdomain": subdomain or "", "recall_when": recall or "",
                        "digest": digest or "", "body": body,
                        "match_terms": list(terms),
                    })
                    print(f"[KB] 加载业务文档：{fname}", flush=True)
                except Exception as e:
                    print(f"[KB] 加载失败：{fname} - {e}", flush=True)
        return docs

    def _extract(self, text: str, pattern: str) -> str:
        m = re.search(pattern, text)
        return m.group(1).strip() if m else ""
