"""
SKILL.md → 结构化快照（snap）。

与 OpenClaw 一致：SKILL.md **不是**单独的 .yaml 文件；文件开头用 Markdown 惯例的
`---` … `---` 包住一段 **YAML frontmatter**，其后才是 Markdown 正文。
解析策略对齐 `openclaw/src/markdown/frontmatter.ts`：
  - 先抽取 `---` 块；
  - 用 YAML 1.2（PyYAML `safe_load`）解析为 dict，标量/结构化值统一落成字符串；
  - 若整段 YAML 解析失败，则回退为逐行 `key: value` 解析（与 OpenClaw 的 line parser 同思路）。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

import yaml

# OpenClaw: extractFrontmatterBlock — 第一段 --- 到下一个 \n--- 之间为 frontmatter 原文
def _extract_frontmatter_block(content: str) -> str | None:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.startswith("---"):
        return None
    end_index = normalized.find("\n---", 3)
    if end_index == -1:
        return None
    return normalized[4:end_index]


def _body_after_frontmatter(content: str) -> str:
    """正文：第二个 --- 之后的部分（OpenClaw 只解析 frontmatter，正文由 Markdown 消费）。"""
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.startswith("---"):
        return normalized
    end_index = normalized.find("\n---", 3)
    if end_index == -1:
        return normalized
    tail = normalized[end_index + len("\n---") :]
    return tail.lstrip("\n")


def _coerce_frontmatter_value(value: object) -> str | None:
    """对齐 openclaw coerceYamlFrontmatterValue → 最终存入 Record<string, string>。"""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            return None
    return None


def _parse_yaml_frontmatter_block(block: str) -> dict[str, str] | None:
    """
    对齐 openclaw parseYamlFrontmatter：YAML.parse 得到对象后再逐键 coerce。
    返回 None 表示应完全退化为行解析。
    """
    try:
        parsed = yaml.safe_load(block)
    except yaml.YAMLError:
        return None
    if parsed is None:
        return {}
    if not isinstance(parsed, dict) or isinstance(parsed, bool):
        return None
    out: dict[str, str] = {}
    for raw_key, value in parsed.items():
        key = str(raw_key).strip()
        if not key:
            continue
        coerced = _coerce_frontmatter_value(value)
        if coerced is not None:
            out[key] = coerced
    return out


_LINE_KEY = re.compile(r"^([\w-]+):\s*(.*)$")


def _extract_multiline_value(lines: list[str], start_index: int) -> tuple[str, int]:
    """对齐 openclaw extractMultiLineValue：下一行起缩进行合并。"""
    value_lines: list[str] = []
    i = start_index + 1
    while i < len(lines):
        line = lines[i]
        if len(line) > 0 and not line.startswith((" ", "\t")):
            break
        value_lines.append(line)
        i += 1
    combined = "\n".join(value_lines).strip()
    return combined, i - start_index


def _parse_line_frontmatter(block: str) -> dict[str, str]:
    """对齐 openclaw parseLineFrontmatter → lineFrontmatterToPlain（仅 string 值）。"""
    result: dict[str, str] = {}
    lines = block.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _LINE_KEY.match(line)
        if not m:
            i += 1
            continue
        key = m.group(1)
        inline = m.group(2).strip()
        if not key:
            i += 1
            continue

        if not inline and i + 1 < len(lines):
            nxt = lines[i + 1]
            if nxt.startswith((" ", "\t")):
                value, consumed = _extract_multiline_value(lines, i)
                if value:
                    result[key] = value
                i += consumed
                continue

        if inline:
            if (inline.startswith('"') and inline.endswith('"')) or (
                inline.startswith("'") and inline.endswith("'")
            ):
                inline = inline[1:-1]
            result[key] = inline
        i += 1
    return result


def parse_frontmatter_block(content: str) -> dict[str, str]:
    """
    对齐 openclaw parseFrontmatterBlock：YAML 优先，失败则纯行解析；
    YAML 成功时合并「仅在行解析中出现且 YAML 未给出」的键。
    """
    block = _extract_frontmatter_block(content)
    if block is None:
        return {}

    line_parsed = _parse_line_frontmatter(block)
    yaml_parsed = _parse_yaml_frontmatter_block(block)

    if yaml_parsed is None:
        return line_parsed

    merged: dict[str, str] = dict(yaml_parsed)
    for key, value in line_parsed.items():
        if key not in merged:
            merged[key] = value
    return merged


@dataclass
class SkillSnap:
    """内存中的 skill 快照，用于多轮对话注入 system 后缀。"""

    snap_id: str
    skill_key: str
    name: str
    description: str
    body: str
    source_path: str
    raw_frontmatter: dict[str, str] = field(default_factory=dict)


def parse_skill_markdown(raw: str, source_path: str, skill_key: str) -> SkillSnap:
    """将 SKILL.md 全文解析为 SkillSnap（frontmatter + 正文）。"""
    fm = parse_frontmatter_block(raw)
    body = _body_after_frontmatter(raw)

    name = fm.get("name") or ""
    desc = fm.get("description") or ""
    if not name:
        for line in body.splitlines():
            if line.startswith("#"):
                name = line.lstrip("#").strip()
                break
    if not name:
        name = skill_key

    digest = hashlib.sha256(f"{source_path}\n{body}".encode()).hexdigest()[:16]
    snap_id = f"snap_{digest}"

    return SkillSnap(
        snap_id=snap_id,
        skill_key=skill_key,
        name=name,
        description=desc,
        body=body.strip(),
        source_path=source_path,
        raw_frontmatter=fm,
    )


def snap_to_tool_json(snap: SkillSnap, *, body_max_chars: int) -> dict:
    """返回给模型 tool 消息的 JSON 摘要（正文过长则截断，完整正文由下一轮 system 注入）。"""
    body = snap.body
    truncated = False
    if len(body) > body_max_chars:
        body = body[:body_max_chars] + f"\n…[正文已截断至 {body_max_chars} 字符，完整内容已加载到会话快照]"
        truncated = True
    return {
        "ok": True,
        "snap_id": snap.snap_id,
        "skill_key": snap.skill_key,
        "name": snap.name,
        "description": snap.description,
        "source_path": snap.source_path,
        "body_injected_next_turn": True,
        "truncated_in_tool_msg": truncated,
        "body_preview": body,
    }
