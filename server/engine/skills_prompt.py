"""
Skills 注入 system prompt — 合并 actone-ai「索引表 + 规则」与 OpenClaw 式 `<available_skills>`：

- 索引：`skills_index.load_skills_index_markdown()`（对齐 actone `_load_skills_index`）
- 路径列表：`format_available_skills_xml_from_catalog()` 与 `read_file` 工具配合

不单独暴露「读 skill」为 LLM tool；使用 **read_file** + 表中的 File 列即可。
"""

from __future__ import annotations

from server.engine.skills_index import (
    format_available_skills_xml_from_catalog,
    load_skills_index_markdown,
    scan_skills_catalog,
)


def build_openclaw_skills_section() -> str:
    """actone 渐进披露表 + `<available_skills>` + 使用说明。"""
    table = load_skills_index_markdown()
    rows = scan_skills_catalog()
    xml = format_available_skills_xml_from_catalog(rows)

    if not rows:
        return (
            "## Skills\n"
            "（当前工作区 `skills/` 下未发现一层目录内的 SKILL.md 或平铺 .md；"
            "仍可用 **read_file** 读任意路径下的文件。）\n"
        )

    return (
        "## Skills（mandatory）\n"
        "以下为 **actone-ai 风格**渐进披露：表格仅 name / description / File；"
        "完整流程请用 **read_file**，`path` 填「File」列（与 `<available_skills>` 中 `<path>` 一致）。\n"
        "探索 Skill 目录下的脚本等请用 **list_files**。\n\n"
        f"{table}\n"
        f"{xml}\n"
    )
