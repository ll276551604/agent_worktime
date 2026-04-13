# -*- coding: utf-8 -*-
"""
业务知识库工具函数（独立模块，避免循环引用）
"""


def match_business_context(req: dict, business_docs: list) -> str:
    """根据需求文本匹配业务知识库，返回注入 prompt 的上下文字符串。"""
    if not business_docs:
        return ""

    req_text = " ".join([
        req.get("module", ""), req.get("feature", ""),
        req.get("detail", ""), req.get("extra", ""),
    ]).lower()

    matched = []
    for doc in business_docs:
        if any(term in req_text for term in doc.get("match_terms", []) if len(term) >= 2):
            matched.append(doc)

    if not matched:
        return ""

    parts = []
    for doc in matched[:2]:   # 最多注入2个文档
        parts.append(f"\n=== 业务知识库：{doc['domain']} / {doc['subdomain']} ===")
        if doc.get("recall_when"):
            parts.append(f"适用场景：{doc['recall_when']}")
        if doc.get("digest"):
            parts.append(f"章节摘要：{doc['digest'][:600]}")
        if doc.get("body"):
            parts.append(f"关键内容：\n{doc['body'][:800]}")

    return "\n".join(parts)
