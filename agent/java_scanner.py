# -*- coding: utf-8 -*-
"""
Java 源码扫描器
扫描 Spring Boot 项目，提取 REST 接口 + 实体类 + 服务接口，
生成供 LLM 判断「新增 vs 调整」的结构化摘要文本。

扫描对象：
  @RestController / @Controller  → 已有 REST 接口路径
  @Entity / @Table               → 已有数据模型（表结构）
  @Service / @FeignClient        → 已有服务层能力
"""
import logging
import os
import re
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

# 单次扫描最多读取的 Java 文件数（防止超大项目卡住）
_MAX_FILES = 300
# 每个文件读取的最大字节（防止巨型文件）
_MAX_FILE_BYTES = 60_000
# 扫描结果缓存（dir → summary），重启前不会失效
_scan_cache: Dict[str, str] = {}

# 跳过的无意义目录
_SKIP_DIRS = {
    "target", "build", ".git", ".idea", "node_modules",
    "test", "tests", "src/test",
}


def scan_java_source(source_dir: str, force: bool = False) -> str:
    """
    扫描 Java 源码目录，返回 Markdown 格式的结构摘要。
    结果会在进程内缓存，force=True 时强制重新扫描。
    """
    if not source_dir or not os.path.isdir(source_dir):
        return ""

    if not force and source_dir in _scan_cache:
        return _scan_cache[source_dir]

    controllers: List[Dict] = []
    entities: List[Dict] = []
    services: List[Dict] = []
    scanned = 0

    for root, dirs, files in os.walk(source_dir):
        # 跳过无关目录
        rel_root = os.path.relpath(root, source_dir)
        dirs[:] = [
            d for d in dirs
            if d not in _SKIP_DIRS
            and not any(skip in os.path.join(rel_root, d) for skip in _SKIP_DIRS)
        ]

        for fname in files:
            if not fname.endswith(".java"):
                continue
            if scanned >= _MAX_FILES:
                logger.info(f"[JavaScanner] 已达扫描上限 {_MAX_FILES} 个文件，停止")
                break

            fpath = os.path.join(root, fname)
            try:
                with open(fpath, encoding="utf-8", errors="ignore") as f:
                    content = f.read(_MAX_FILE_BYTES)
            except Exception:
                continue

            scanned += 1

            if _has_annotation(content, r"@(Rest)?Controller"):
                info = _parse_controller(content, fname)
                if info:
                    controllers.append(info)
            elif _has_annotation(content, r"@(Entity|Table|Document)\b"):
                info = _parse_entity(content, fname)
                if info:
                    entities.append(info)
            elif _has_annotation(content, r"@(Service|FeignClient)\b"):
                info = _parse_service(content, fname)
                if info:
                    services.append(info)

    summary = _format_summary(controllers, entities, services, scanned)
    _scan_cache[source_dir] = summary
    logger.info(f"[JavaScanner] 扫描完成: {scanned} 文件 | "
                f"{len(controllers)} Controller | {len(entities)} Entity | {len(services)} Service")
    return summary


# ─────────────────────────────────────────────
# 内部工具
# ─────────────────────────────────────────────

def _has_annotation(content: str, pattern: str) -> bool:
    return bool(re.search(pattern, content))


def _parse_controller(content: str, fname: str) -> Dict:
    class_name = _extract_class_name(content) or fname.replace(".java", "")

    # 类级别的 @RequestMapping 基础路径
    base_path = ""
    m = re.search(
        r'@RequestMapping\s*\(\s*(?:value\s*=\s*)?["\{]([^"\}]+)["\}]',
        content,
    )
    if m:
        base_path = m.group(1).rstrip("/")

    # 收集所有方法级别的路由
    endpoints: List[str] = []
    ep_pattern = re.compile(
        r'@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)'
        r'(?:\s*\(\s*(?:value\s*=\s*)?["\{]([^"\}]*)["\}])?',
    )
    for m in ep_pattern.finditer(content):
        verb = m.group(1).replace("Mapping", "").upper()
        if verb == "REQUEST":
            verb = "ANY"
        sub_path = m.group(2) or ""
        full = (base_path + "/" + sub_path.lstrip("/")).rstrip("/") or base_path or "/"
        endpoints.append(f"{verb} {full}")

    if not endpoints and not base_path:
        return None

    return {"class": class_name, "base_path": base_path, "endpoints": endpoints[:20]}


def _parse_entity(content: str, fname: str) -> Dict:
    class_name = _extract_class_name(content) or fname.replace(".java", "")

    table_m = re.search(r'@Table\s*\(\s*name\s*=\s*["\']([^"\']+)["\']', content)
    table_name = table_m.group(1) if table_m else ""

    # 提取私有字段名（排除常量和序列化字段）
    fields = [
        f for f in re.findall(r'private\s+\S+\s+(\w+)\s*;', content)
        if f not in ("serialVersionUID", "log", "logger")
        and not f.startswith("_")
    ]

    return {"class": class_name, "table": table_name, "fields": fields[:30]}


def _parse_service(content: str, fname: str) -> Dict:
    class_name = _extract_class_name(content) or fname.replace(".java", "")

    methods = [
        m for m in re.findall(r'(?:public|protected)\s+\S+\s+(\w+)\s*\(', content)
        if m not in ("toString", "hashCode", "equals", "getClass")
    ]

    return {"class": class_name, "methods": methods[:15]}


def _extract_class_name(content: str) -> str:
    m = re.search(r'(?:public\s+)?(?:class|interface|enum)\s+(\w+)', content)
    return m.group(1) if m else ""


def _format_summary(
    controllers: List[Dict],
    entities: List[Dict],
    services: List[Dict],
    scanned: int,
) -> str:
    if not controllers and not entities and not services:
        return ""

    parts = [f"### Java 源码扫描摘要（共扫描 {scanned} 个文件）\n"]

    if controllers:
        parts.append("#### 已有 REST 接口（判断接口是否已存在）")
        for c in controllers[:40]:
            parts.append(f"\n**{c['class']}**  基础路径: `{c['base_path'] or '/'}`")
            for ep in c["endpoints"][:12]:
                parts.append(f"  - {ep}")

    if entities:
        parts.append("\n#### 已有数据实体（判断数据模型是否已存在）")
        for e in entities[:40]:
            table_info = f" → 表 `{e['table']}`" if e["table"] else ""
            fields_str = "、".join(e["fields"][:20]) if e["fields"] else "（无字段）"
            parts.append(f"- **{e['class']}**{table_info}: {fields_str}")

    if services:
        parts.append("\n#### 已有服务层（判断业务能力是否已存在）")
        for s in services[:30]:
            methods_str = "、".join(s["methods"][:8]) if s["methods"] else "（无公开方法）"
            parts.append(f"- **{s['class']}**: {methods_str}")

    return "\n".join(parts)
