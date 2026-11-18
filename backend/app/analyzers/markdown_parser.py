"""
Line-accurate Static Markdown Parser for DocGuard (Milestone 4).

Parses Markdown documentation into heading-scoped sections, paragraphs,
bullet lists, numbered lists, fenced code blocks (with language metadata),
inline code spans, links, and tables while preserving exact 1-based line numbers.
Never executes any embedded code blocks or external links.
"""

import re
from typing import List, Optional, Tuple

from app.schemas.documentation import (
    MarkdownBlockElement,
    MarkdownCodeBlock,
    MarkdownLink,
    MarkdownSection,
    MarkdownTable,
    ParsedMarkdownDocument,
)

DEFAULT_MAX_SECTIONS = 300

_ATX_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)(?:\s+#+\s*)?$")
_FENCE_OPEN_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})\s*([A-Za-z0-9_+.-]*)\s*$")
_BULLET_ITEM_RE = re.compile(r"^\s*[-*+]\s+(.+)$")
_NUMBERED_ITEM_RE = re.compile(r"^\s*\d+[.)]\s+(.+)$")
_INLINE_CODE_RE = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
_MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?(?:\s*:?-{2,}:?\s*\|)+\s*:?-{2,}:?\s*\|?\s*$")


def extract_inline_code_spans(text: str) -> list[str]:
    """Extract all inline code spans (`...`) from a Markdown text fragment."""
    if not text or "`" not in text:
        return []
    spans: list[str] = []
    for match in _INLINE_CODE_RE.finditer(text):
        val = match.group(1).strip()
        if val:
            spans.append(val)
    return spans


def extract_markdown_links(text: str, base_line: int) -> list[MarkdownLink]:
    """Extract all Markdown links `[label](url)` from a text fragment with 1-based line numbers."""
    if not text or "[" not in text:
        return []
    links: list[MarkdownLink] = []
    for offset, line_text in enumerate(text.split("\n")):
        for match in _MARKDOWN_LINK_RE.finditer(line_text):
            label = match.group(1).strip()
            url = match.group(2).strip()
            if label and url:
                links.append(
                    MarkdownLink(
                        text=label,
                        url=url,
                        line=base_line + offset,
                    )
                )
    return links


def _is_table_row(line: str) -> bool:
    """Return True if a line looks like a pipe-delimited Markdown table row."""
    stripped = line.strip()
    return "|" in stripped and not stripped.startswith((">", "```", "~~~"))


def _split_table_cells(line: str) -> list[str]:
    """Split a Markdown table row into trimmed cell values."""
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def parse_markdown_document(
    content: str,
    file_path: str,
    max_sections: int = DEFAULT_MAX_SECTIONS,
) -> ParsedMarkdownDocument:
    """
    Parse a Markdown string into a structured `ParsedMarkdownDocument` with exact
    1-based start and end line numbers for every section and block element.
    """
    if not content or not content.strip():
        return ParsedMarkdownDocument(
            file_path=file_path,
            total_lines=0,
        )

    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    total_lines = len(lines)

    sections: list[MarkdownSection] = []
    all_headings: list[str] = []
    all_paragraphs: list[str] = []
    all_bullets: list[str] = []
    all_numbered: list[str] = []
    all_code_blocks: list[MarkdownCodeBlock] = []
    all_inline_code: list[str] = []
    all_links: list[MarkdownLink] = []
    all_tables: list[MarkdownTable] = []

    # Stack of (heading_level, heading_text) to compute nested heading_hierarchy
    heading_stack: List[Tuple[int, str]] = []

    current_section = MarkdownSection(
        heading=None,
        level=0,
        heading_hierarchy=[],
        start_line=1,
        end_line=total_lines,
        blocks=[],
        inline_code=[],
        links=[],
    )

    def _finalize_current_section(end_line_num: int) -> None:
        if current_section.heading is not None or current_section.blocks:
            current_section.end_line = max(current_section.start_line, end_line_num)
            if len(sections) < max_sections:
                sections.append(current_section)

    idx = 0
    while idx < total_lines:
        line_num = idx + 1
        line = lines[idx]

        # 1. Check for Fenced Code Block (` ``` ` or ` ~~~ `)
        fence_match = _FENCE_OPEN_RE.match(line)
        if fence_match:
            fence_marker = fence_match.group(1)
            fence_char = fence_marker[0]
            fence_len = len(fence_marker)
            language = (fence_match.group(2) or "").strip()
            block_start = line_num
            code_lines: list[str] = []
            idx += 1

            while idx < total_lines:
                candidate = lines[idx].strip()
                if (
                    candidate.startswith(fence_char * fence_len)
                    and candidate.strip(fence_char) == ""
                ):
                    idx += 1
                    break
                code_lines.append(lines[idx])
                idx += 1

            block_end = idx
            code_text = "\n".join(code_lines)

            code_block_obj = MarkdownCodeBlock(
                language=language,
                content=code_text,
                start_line=block_start,
                end_line=block_end,
                heading=current_section.heading,
                heading_hierarchy=list(current_section.heading_hierarchy),
            )
            all_code_blocks.append(code_block_obj)

            current_section.blocks.append(
                MarkdownBlockElement(
                    block_type="code_block",
                    text=code_text,
                    start_line=block_start,
                    end_line=block_end,
                    inline_code=[],
                    links=[],
                    language=language,
                )
            )
            continue

        # 2. Check for ATX Heading (`# Heading`)
        heading_match = _ATX_HEADING_RE.match(line)
        if heading_match:
            _finalize_current_section(line_num - 1)

            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()
            all_headings.append(heading_text)

            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, heading_text))
            hierarchy = [h_text for _lvl, h_text in heading_stack]

            h_inline = extract_inline_code_spans(heading_text)
            h_links = extract_markdown_links(heading_text, line_num)
            all_inline_code.extend(h_inline)
            all_links.extend(h_links)

            current_section = MarkdownSection(
                heading=heading_text,
                level=level,
                heading_hierarchy=hierarchy,
                start_line=line_num,
                end_line=total_lines,
                blocks=[],
                inline_code=list(h_inline),
                links=list(h_links),
            )
            idx += 1
            continue

        # 3. Skip blank lines
        if not line.strip():
            idx += 1
            continue

        # 4. Check for Markdown Table (header row + separator row `| --- | --- |`)
        if (
            idx + 1 < total_lines
            and _is_table_row(line)
            and _TABLE_SEPARATOR_RE.match(lines[idx + 1])
        ):
            table_start = line_num
            headers = _split_table_cells(line)
            raw_table_lines = [line, lines[idx + 1]]
            rows: list[list[str]] = []
            idx += 2

            while idx < total_lines and _is_table_row(lines[idx]) and lines[idx].strip():
                raw_table_lines.append(lines[idx])
                rows.append(_split_table_cells(lines[idx]))
                idx += 1

            table_end = idx
            raw_table_text = "\n".join(raw_table_lines)
            t_inline = extract_inline_code_spans(raw_table_text)
            t_links = extract_markdown_links(raw_table_text, table_start)
            all_inline_code.extend(t_inline)
            all_links.extend(t_links)
            current_section.inline_code.extend(t_inline)
            current_section.links.extend(t_links)

            table_obj = MarkdownTable(
                headers=headers,
                rows=rows,
                raw_text=raw_table_text,
                start_line=table_start,
                end_line=table_end,
                heading=current_section.heading,
                heading_hierarchy=list(current_section.heading_hierarchy),
            )
            all_tables.append(table_obj)

            current_section.blocks.append(
                MarkdownBlockElement(
                    block_type="table",
                    text=raw_table_text,
                    start_line=table_start,
                    end_line=table_end,
                    inline_code=t_inline,
                    links=t_links,
                )
            )
            continue

        # 5. Check for Bullet List Item (`- `, `* `, `+ `)
        bullet_match = _BULLET_ITEM_RE.match(line)
        if bullet_match:
            item_start = line_num
            item_lines = [bullet_match.group(1).strip()]
            idx += 1

            while idx < total_lines:
                next_line = lines[idx]
                if (
                    not next_line.strip()
                    or _ATX_HEADING_RE.match(next_line)
                    or _FENCE_OPEN_RE.match(next_line)
                    or _BULLET_ITEM_RE.match(next_line)
                    or _NUMBERED_ITEM_RE.match(next_line)
                ):
                    break
                if next_line.startswith(("  ", "\t")):
                    item_lines.append(next_line.strip())
                    idx += 1
                else:
                    break

            item_end = idx
            item_text = " ".join(item_lines)
            all_bullets.append(item_text)

            b_inline = extract_inline_code_spans(item_text)
            b_links = extract_markdown_links(item_text, item_start)
            all_inline_code.extend(b_inline)
            all_links.extend(b_links)
            current_section.inline_code.extend(b_inline)
            current_section.links.extend(b_links)

            current_section.blocks.append(
                MarkdownBlockElement(
                    block_type="bullet_item",
                    text=item_text,
                    start_line=item_start,
                    end_line=item_end,
                    inline_code=b_inline,
                    links=b_links,
                )
            )
            continue

        # 6. Check for Numbered List Item (`1. `, `2) `)
        numbered_match = _NUMBERED_ITEM_RE.match(line)
        if numbered_match:
            item_start = line_num
            item_lines = [numbered_match.group(1).strip()]
            idx += 1

            while idx < total_lines:
                next_line = lines[idx]
                if (
                    not next_line.strip()
                    or _ATX_HEADING_RE.match(next_line)
                    or _FENCE_OPEN_RE.match(next_line)
                    or _BULLET_ITEM_RE.match(next_line)
                    or _NUMBERED_ITEM_RE.match(next_line)
                ):
                    break
                if next_line.startswith(("  ", "\t")):
                    item_lines.append(next_line.strip())
                    idx += 1
                else:
                    break

            item_end = idx
            item_text = " ".join(item_lines)
            all_numbered.append(item_text)

            n_inline = extract_inline_code_spans(item_text)
            n_links = extract_markdown_links(item_text, item_start)
            all_inline_code.extend(n_inline)
            all_links.extend(n_links)
            current_section.inline_code.extend(n_inline)
            current_section.links.extend(n_links)

            current_section.blocks.append(
                MarkdownBlockElement(
                    block_type="numbered_item",
                    text=item_text,
                    start_line=item_start,
                    end_line=item_end,
                    inline_code=n_inline,
                    links=n_links,
                )
            )
            continue

        # 7. Paragraph block (accumulate contiguous non-blank prose lines)
        para_start = line_num
        para_lines = [line.strip()]
        idx += 1

        while idx < total_lines:
            next_line = lines[idx]
            if (
                not next_line.strip()
                or _ATX_HEADING_RE.match(next_line)
                or _FENCE_OPEN_RE.match(next_line)
                or _BULLET_ITEM_RE.match(next_line)
                or _NUMBERED_ITEM_RE.match(next_line)
                or (
                    idx + 1 < total_lines
                    and _is_table_row(next_line)
                    and _TABLE_SEPARATOR_RE.match(lines[idx + 1])
                )
            ):
                break
            para_lines.append(next_line.strip())
            idx += 1

        para_end = idx
        para_text = "\n".join(para_lines)
        all_paragraphs.append(para_text)

        p_inline = extract_inline_code_spans(para_text)
        p_links = extract_markdown_links(para_text, para_start)
        all_inline_code.extend(p_inline)
        all_links.extend(p_links)
        current_section.inline_code.extend(p_inline)
        current_section.links.extend(p_links)

        current_section.blocks.append(
            MarkdownBlockElement(
                block_type="paragraph",
                text=para_text,
                start_line=para_start,
                end_line=para_end,
                inline_code=p_inline,
                links=p_links,
            )
        )

    _finalize_current_section(total_lines)

    return ParsedMarkdownDocument(
        file_path=file_path,
        total_lines=total_lines,
        sections=sections,
        headings=all_headings,
        paragraphs=all_paragraphs,
        bullet_lists=all_bullets,
        numbered_lists=all_numbered,
        code_blocks=all_code_blocks,
        inline_code_references=all_inline_code,
        links=all_links,
        tables=all_tables,
    )
