"""
Skill 索引（load skills index）— 对齐 actone-ai `app/services/agent_context.py`：

- 在 `skills/` 下只做**一层**扫描（与 actone `_load_skills_index` 一致）：
  - 目录：`skills/<folder>/SKILL.md` 或 `skill.md`
  - 平铺：`skills/<name>.md`
- 渐进披露：system 里只放 name + description + **File** 列（相对工作区根的 path），
  完整内容由模型调用 **read_file** 读取该 path。

另提供 `scan_skills_catalog()` 供 `list_skills_tool` / XML 与表格共用数据源。
"""

from __future__ import annotations

from pathlib import Path

from server.config import settings


def _workspace_root() -> Path:
    return Path(settings.WORKSPACE_ROOT).resolve()


def _primary_skills_dir() -> Path:
    root = _workspace_root()
    sd = Path(settings.SKILLS_DIR)
    return sd if sd.is_absolute() else (root / sd)


def _extra_skill_roots() -> list[Path]:
    root = _workspace_root()
    alt = root / ".cursor" / "skills"
    return [alt] if alt.is_dir() else []


def parse_skill_frontmatter_actone(content: str, filename: str) -> tuple[str, str]:
    """Port of actone `_parse_skill_frontmatter` — (name, description)."""
    name = filename.replace("_", " ").replace("-", " ")
    description = ""

    stripped = content.strip()
    if stripped.startswith("---"):
        end = stripped.find("---", 3)
        if end != -1:
            frontmatter = stripped[3:end].strip()
            for line in frontmatter.split("\n"):
                line = line.strip()
                if line.lower().startswith("name:"):
                    val = line[5:].strip().strip('"').strip("'")
                    if val:
                        name = val
                elif line.lower().startswith("description:"):
                    val = line[12:].strip().strip('"').strip("'")
                    if val:
                        description = val[:200]
            if description:
                return name, description

    for line in stripped.split("\n"):
        line = line.strip()
        if line in ("---",) or line.startswith("name:") or line.startswith("description:"):
            continue
        if line and not line.startswith("#"):
            description = line[:200]
            break
    if not description:
        lines = stripped.split("\n")
        if lines:
            description = lines[0].strip().lstrip("# ")[:200]

    return name, description


def _scan_one_skills_root(skills_dir: Path, root: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not skills_dir.exists() or not skills_dir.is_dir():
        return rows

    for entry in sorted(skills_dir.iterdir()):
        if entry.name.startswith("."):
            continue

        if entry.is_dir():
            skill_md = entry / "SKILL.md"
            if not skill_md.exists():
                skill_md = entry / "skill.md"
            if skill_md.exists():
                try:
                    content = skill_md.read_text(encoding="utf-8", errors="replace").strip()
                    name, desc = parse_skill_frontmatter_actone(content, entry.name)
                    rel = str(skill_md.relative_to(root))
                    rows.append({"name": name, "description": desc, "path": rel})
                except OSError:
                    rel = str(skill_md.relative_to(root))
                    rows.append({"name": entry.name, "description": "", "path": rel})

        elif entry.suffix == ".md" and entry.is_file():
            try:
                content = entry.read_text(encoding="utf-8", errors="replace").strip()
                name, desc = parse_skill_frontmatter_actone(content, entry.stem)
                rel = str(entry.relative_to(root))
                rows.append({"name": name, "description": desc, "path": rel})
            except OSError:
                rel = str(entry.relative_to(root))
                rows.append({"name": entry.stem, "description": "", "path": rel})

    return rows


def scan_skills_catalog() -> list[dict[str, str]]:
    """合并主 `SKILLS_DIR` 与 `.cursor/skills` 的一层扫描结果，按 name 去重（先出现的保留）。"""
    root = _workspace_root()
    all_rows: list[dict[str, str]] = []
    for base in [_primary_skills_dir(), *_extra_skill_roots()]:
        all_rows.extend(_scan_one_skills_root(base, root))

    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for row in all_rows:
        key = row["name"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    unique.sort(key=lambda r: r["path"])
    return unique


def load_skills_index_markdown() -> str:
    """
    actone `_load_skills_index` 的 Markdown 表格 + 使用规则（中文语境）。
    空目录时返回空串。
    """
    unique = scan_skills_catalog()
    if not unique:
        return ""

    lines = [
        "你可使用以下 Skill（仅摘要）。完整流程写在对应文件中。",
        "",
        "| Skill | Description | File |",
        "|-------|-------------|------|",
    ]
    for row in unique:
        name = row["name"].replace("|", "\\|")
        desc = (row.get("description") or "").replace("|", "\\|")
        fp = row["path"].replace("|", "\\|")
        lines.append(f"| {name} | {desc} | {fp} |")

    lines.extend([
        "",
        "⚠️ SKILL 使用规则（与 actone-ai 一致）：",
        "1. 当用户需求匹配某 Skill 时，**先**用工具 **read_file**，`path` 填上表 **File** 列的路径，加载全文再执行。",
        "2. 按加载后的说明完成任务。",
        "3. 不要猜测 Skill 内容——必须先 read_file。",
        "4. 目录型 Skill 下可能有 `scripts/`、`references/` 等；可用 **list_files** 在对应目录下探索。",
        "",
    ])
    return "\n".join(lines)


def format_available_skills_xml_from_catalog(rows: list[dict[str, str]]) -> str:
    """从同一目录数据生成 OpenClaw 式 XML（可选，与表格并存）。"""
    if not rows:
        return "<available_skills>\n</available_skills>"
    lines = ["<available_skills>"]
    for row in rows:
        p = row["path"].replace("&", "&amp;").replace("<", "&lt;")
        n = row["name"].replace("&", "&amp;").replace("<", "&lt;")
        d = (row.get("description") or "").replace("&", "&amp;").replace("<", "&lt;")
        lines.append(f'  <skill><path>{p}</path><name>{n}</name><description>{d}</description></skill>')
    lines.append("</available_skills>")
    return "\n".join(lines)
