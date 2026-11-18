"""
Documentation Statement & Unit Extractor for DocGuard (Milestone 4).

Extracts meaningful documentation units (headings with descriptions, paragraphs,
bullet items, numbered items, API reference entries, parameter descriptions,
return descriptions, tables, and code blocks) from a ParsedMarkdownDocument.
Preserves exact original text and 1-based start/end line numbers.
"""

import re
from typing import Optional

from app.schemas.documentation import (
    DocumentationUnit,
    DocumentationUnitType,
    MarkdownBlockElement,
    MarkdownSection,
    ParsedMarkdownDocument,
)

_CALL_IDENTIFIER_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_.]*)\s*\(")
_DOTTED_IDENTIFIER_RE = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+)\b"
)
_SNAKE_CASE_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*_[A-Za-z0-9_]+)\b")
_CAMEL_CASE_RE = re.compile(r"\b([A-Z][a-z0-9]+(?:[A-Z][A-Za-z0-9]*)+)\b")
_PY_FILE_PATH_RE = re.compile(r"\b([A-Za-z0-9_./-]+\.py)\b")
_CONTEXT_SYMBOL_RE = re.compile(
    r"\b(?:function|method|class|def|parameter|argument|param|arg|module)\s+`?([A-Za-z_][A-Za-z0-9_.]*)`?\b",
    re.IGNORECASE,
)
_REVERSE_CONTEXT_SYMBOL_RE = re.compile(
    r"`?([A-Za-z_][A-Za-z0-9_.]*)`?\s+(?:function|method|class|parameter|argument|module)\b",
    re.IGNORECASE,
)
_API_HEADING_SIGNATURE_RE = re.compile(
    r"^(?:`?(?:async\s+)?(?:def|class)\s+)?`?([A-Za-z_][A-Za-z0-9_.]*)\s*(?:\([^)]*\))?`?$"
)

_STOPWORD_TOKENS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "true",
    "false",
    "none",
    "null",
    "self",
    "cls",
    "http",
    "https",
    "github",
    "com",
    "org",
    "net",
    "pip",
    "npm",
    "git",
    "bash",
    "json",
    "yaml",
    "html",
    "text",
    "code",
    "file",
    "note",
    "todo",
}

_CHANGELOG_HEADINGS = {"changelog", "changes", "release notes", "version history", "history"}
_CONTRIBUTION_HEADINGS = {
    "contributing",
    "contribution",
    "contributions",
    "code of conduct",
    "pull requests",
    "development setup",
}
_INSTALLATION_HEADINGS = {
    "installation",
    "install",
    "installing",
    "prerequisites",
    "requirements",
    "setup",
}
_GENERAL_INFO_HEADINGS = {
    "overview",
    "project overview",
    "about",
    "introduction",
    "summary",
    "license",
    "licence",
    "authors",
    "credits",
    "acknowledgments",
    "acknowledgements",
    "support",
    "community",
    "sponsors",
    "badges",
}


def extract_code_identifiers(
    text: str,
    inline_code_spans: Optional[list[str]] = None,
    heading: Optional[str] = None,
) -> list[str]:
    """
    Extract candidate Python code identifiers, qualified names, and `.py` file paths
    from a documentation text fragment, its inline code spans, and its section heading.
    """
    candidates: list[str] = []
    seen: set[str] = set()

    def _add_token(raw_token: str) -> None:
        cleaned = raw_token.strip().strip("`'\".,:;!?()[]{}")
        if not cleaned or len(cleaned) < 2:
            return
        if cleaned.lower() in _STOPWORD_TOKENS:
            return
        if cleaned not in seen:
            seen.add(cleaned)
            candidates.append(cleaned)

    # 1. Extract from inline code spans (`...`)
    for span in inline_code_spans or []:
        _add_token(span)
        for m in _CALL_IDENTIFIER_RE.finditer(span):
            _add_token(m.group(1))
        for m in _DOTTED_IDENTIFIER_RE.finditer(span):
            _add_token(m.group(1))
        for m in _PY_FILE_PATH_RE.finditer(span):
            _add_token(m.group(1))
        # Extract bare identifier words inside inline code (e.g. `calculate_total(price, tax=0)`)
        for ident in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", span):
            if ident not in {"def", "class", "async", "await", "return", "import", "from"}:
                _add_token(ident)

    # 2. Extract from heading if heading looks like a code reference
    if heading:
        h_clean = heading.strip()
        h_lower = h_clean.lower()
        is_prose_heading = (
            h_lower in _GENERAL_INFO_HEADINGS
            or h_lower in _INSTALLATION_HEADINGS
            or h_lower in _CHANGELOG_HEADINGS
            or h_lower in _CONTRIBUTION_HEADINGS
        )
        if not is_prose_heading:
            for h_span in re.findall(r"`([^`]+)`", h_clean):
                _add_token(h_span)
            for m in _CALL_IDENTIFIER_RE.finditer(h_clean):
                _add_token(m.group(1))
            for m in _SNAKE_CASE_RE.finditer(h_clean):
                _add_token(m.group(1))
            for m in _CAMEL_CASE_RE.finditer(h_clean):
                _add_token(m.group(1))

    # 3. Extract explicit call patterns, file paths, snake_case, CamelCase, and contextual symbols from prose
    if text:
        for m in _PY_FILE_PATH_RE.finditer(text):
            _add_token(m.group(1))
        for m in _CALL_IDENTIFIER_RE.finditer(text):
            _add_token(m.group(1))
        for m in _DOTTED_IDENTIFIER_RE.finditer(text):
            token = m.group(1)
            if not token.lower().endswith((".md", ".rst", ".txt", ".json", ".com", ".org", ".io")):
                _add_token(token)
        for m in _SNAKE_CASE_RE.finditer(text):
            _add_token(m.group(1))
        for m in _CAMEL_CASE_RE.finditer(text):
            _add_token(m.group(1))
        for m in _CONTEXT_SYMBOL_RE.finditer(text):
            _add_token(m.group(1))
        for m in _REVERSE_CONTEXT_SYMBOL_RE.finditer(text):
            _add_token(m.group(1))

    return candidates


def _is_api_heading(heading: Optional[str], hierarchy: list[str]) -> bool:
    """Return True if the section heading represents an API reference or code symbol."""
    if not heading:
        return False
    stripped = heading.strip()
    if "`" in stripped or "(" in stripped and ")" in stripped:
        return True
    if _SNAKE_CASE_RE.search(stripped) or _CAMEL_CASE_RE.search(stripped):
        return True
    if stripped.startswith(("def ", "async def ", "class ")):
        return True
    hierarchy_lower = " ".join(hierarchy).lower()
    if any(k in hierarchy_lower for k in ("api", "reference", "functions", "methods", "classes")):
        return True
    return False


def _classify_prose_unit_type(
    file_path: str,
    section: MarkdownSection,
    block: MarkdownBlockElement,
    identifiers: list[str],
) -> DocumentationUnitType:
    """Classify a documentation block into a specific DocumentationUnitType."""
    if block.block_type == "code_block":
        return "code_block"
    if block.block_type == "table":
        return "table"

    basename_lower = file_path.replace("\\", "/").split("/")[-1].lower()
    heading_lower = (section.heading or "").strip().lower()
    hierarchy_lower = " ".join(section.heading_hierarchy).lower()
    text_lower = block.text.strip().lower()

    # 1. File-level or heading-level non-API categories
    if "changelog" in basename_lower or "history" in basename_lower or any(
        h in hierarchy_lower for h in _CHANGELOG_HEADINGS
    ):
        return "changelog"

    if "contributing" in basename_lower or any(
        h in hierarchy_lower for h in _CONTRIBUTION_HEADINGS
    ):
        return "contribution"

    if any(h in heading_lower for h in _INSTALLATION_HEADINGS) or re.search(
        r"\b(?:pip\s+install|npm\s+install|poetry\s+add|uv\s+pip|git\s+clone)\b",
        text_lower,
    ):
        return "installation"

    if any(h == heading_lower for h in _GENERAL_INFO_HEADINGS):
        return "general_info"

    # 2. Parameter or Return descriptions
    if re.search(
        r"(?:^:param\b|^parameters?\b|\bparameter\b|\bargument\b|\boptional\s+[a-z0-9_`]+\s+value\b|\baccepts\s+a\b)",
        text_lower,
    ):
        return "parameter_description"

    if re.search(
        r"(?:^:returns?\b|^:rtype\b|^returns?\s*:|\breturn\s+value\b|\breturns\s+(?:a|an|the)\b)",
        text_lower,
    ):
        return "return_description"

    # 3. API Reference entry
    if _is_api_heading(section.heading, section.heading_hierarchy):
        return "api_reference"

    # 4. Block-specific or general prose classification
    if block.block_type == "bullet_item":
        return "bullet_item"
    if block.block_type == "numbered_item":
        return "numbered_item"

    if not identifiers and (
        heading_lower in {"overview", "about", "introduction", "summary", "docguard"}
        or not section.heading
    ):
        return "general_info"

    return "paragraph"


def extract_documentation_units(
    parsed_doc: ParsedMarkdownDocument,
    max_units: int = 400,
) -> list[DocumentationUnit]:
    """
    Extract meaningful DocumentationUnit items from a ParsedMarkdownDocument.
    Preserves original text, exact line ranges, heading hierarchy, and keeps
    code blocks distinct (`is_code_example=True`).
    """
    units: list[DocumentationUnit] = []
    counter = 0

    for section in parsed_doc.sections:
        if len(units) >= max_units:
            break

        # If a section has an explicit heading but zero body blocks, emit a heading_section unit
        if section.heading and not section.blocks:
            counter += 1
            identifiers = extract_code_identifiers(
                text=section.heading,
                inline_code_spans=section.inline_code,
                heading=section.heading,
            )
            u_type: DocumentationUnitType = (
                "api_reference"
                if _is_api_heading(section.heading, section.heading_hierarchy)
                else "heading_section"
            )
            units.append(
                DocumentationUnit(
                    unit_id=f"{parsed_doc.file_path}::unit-{counter}",
                    documentation_file=parsed_doc.file_path,
                    section_heading=section.heading,
                    heading_hierarchy=list(section.heading_hierarchy),
                    start_line=section.start_line,
                    end_line=section.end_line,
                    original_text=section.heading,
                    unit_type=u_type,
                    referenced_identifiers=identifiers,
                    inline_code=list(section.inline_code),
                    is_code_example=False,
                )
            )
            continue

        heading_inline = (
            re.findall(r"(?<!`)`([^`\n]+)`(?!`)", section.heading)
            if section.heading
            else []
        )

        for block in section.blocks:
            if len(units) >= max_units:
                break

            combined_inline = list(dict.fromkeys(heading_inline + block.inline_code))
            identifiers = extract_code_identifiers(
                text=block.text,
                inline_code_spans=combined_inline,
                heading=section.heading,
            )
            unit_type = _classify_prose_unit_type(
                file_path=parsed_doc.file_path,
                section=section,
                block=block,
                identifiers=identifiers,
            )

            counter += 1
            units.append(
                DocumentationUnit(
                    unit_id=f"{parsed_doc.file_path}::unit-{counter}",
                    documentation_file=parsed_doc.file_path,
                    section_heading=section.heading,
                    heading_hierarchy=list(section.heading_hierarchy),
                    start_line=block.start_line,
                    end_line=block.end_line,
                    original_text=block.text,
                    unit_type=unit_type,
                    referenced_identifiers=identifiers,
                    inline_code=combined_inline,
                    is_code_example=(block.block_type == "code_block"),
                )
            )

    return units
