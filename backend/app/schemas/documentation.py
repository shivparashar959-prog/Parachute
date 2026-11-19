"""
Pydantic schemas for Milestone 4: Documentation Parsing and Code Mapping Engine.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field

from app.schemas.code_analysis import ParseErrorItem, SkippedFileItem, SymbolType

MappingConfidence = Literal["HIGH", "MEDIUM", "LOW"]
MappingStatus = Literal["MAPPED", "UNMAPPED", "AMBIGUOUS"]

DocumentationUnitType = Literal[
    "heading_section",
    "paragraph",
    "bullet_item",
    "numbered_item",
    "api_reference",
    "parameter_description",
    "return_description",
    "code_block",
    "table",
    "installation",
    "changelog",
    "contribution",
    "general_info",
]


class MarkdownLink(BaseModel):
    """A link `[text](url)` extracted from Markdown content."""

    text: str
    url: str
    line: int


class MarkdownCodeBlock(BaseModel):
    """A fenced code block extracted from a Markdown document."""

    language: str = ""
    content: str
    start_line: int
    end_line: int
    heading: Optional[str] = None
    heading_hierarchy: list[str] = Field(default_factory=list)


class MarkdownTable(BaseModel):
    """A pipe-delimited Markdown table with exact line numbers."""

    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    raw_text: str
    start_line: int
    end_line: int
    heading: Optional[str] = None
    heading_hierarchy: list[str] = Field(default_factory=list)


class MarkdownBlockElement(BaseModel):
    """An atomic structural block inside a Markdown section."""

    block_type: Literal[
        "paragraph", "bullet_item", "numbered_item", "code_block", "table"
    ]
    text: str
    start_line: int
    end_line: int
    inline_code: list[str] = Field(default_factory=list)
    links: list[MarkdownLink] = Field(default_factory=list)
    language: Optional[str] = None


class MarkdownSection(BaseModel):
    """A heading-delimited section within a Markdown document."""

    heading: Optional[str] = None
    level: int = 0
    heading_hierarchy: list[str] = Field(default_factory=list)
    start_line: int
    end_line: int
    blocks: list[MarkdownBlockElement] = Field(default_factory=list)
    inline_code: list[str] = Field(default_factory=list)
    links: list[MarkdownLink] = Field(default_factory=list)


class ParsedMarkdownDocument(BaseModel):
    """Complete structured AST representation of a parsed Markdown file."""

    file_path: str
    total_lines: int
    sections: list[MarkdownSection] = Field(default_factory=list)
    headings: list[str] = Field(default_factory=list)
    paragraphs: list[str] = Field(default_factory=list)
    bullet_lists: list[str] = Field(default_factory=list)
    numbered_lists: list[str] = Field(default_factory=list)
    code_blocks: list[MarkdownCodeBlock] = Field(default_factory=list)
    inline_code_references: list[str] = Field(default_factory=list)
    links: list[MarkdownLink] = Field(default_factory=list)
    tables: list[MarkdownTable] = Field(default_factory=list)


class DocumentationUnit(BaseModel):
    """A meaningful documentation statement or section unit extracted from Markdown."""

    unit_id: str
    documentation_file: str
    section_heading: Optional[str] = None
    heading_hierarchy: list[str] = Field(default_factory=list)
    start_line: int
    end_line: int
    original_text: str
    unit_type: DocumentationUnitType
    referenced_identifiers: list[str] = Field(default_factory=list)
    inline_code: list[str] = Field(default_factory=list)
    is_code_example: bool = False


class RelatedSymbolMatch(BaseModel):
    """A matched Python AST symbol linked to a documentation unit with evidence."""

    symbol: str
    qualified_name: str
    source_file: str
    symbol_type: SymbolType
    signature: str
    line_start: int
    line_end: int
    confidence: MappingConfidence
    matching_reasons: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class DocumentationMapping(BaseModel):
    """A mapping record linking an extracted documentation unit to zero, one, or multiple code symbols."""

    mapping_id: str
    unit_id: str
    documentation_file: str
    documentation_section: Optional[str] = None
    heading_hierarchy: list[str] = Field(default_factory=list)
    unit_type: DocumentationUnitType
    start_line: int
    end_line: int
    documentation_text: str
    referenced_identifiers: list[str] = Field(default_factory=list)
    related_symbols: list[RelatedSymbolMatch] = Field(default_factory=list)
    mapping_status: MappingStatus
    highest_confidence: Optional[MappingConfidence] = None


class DiscoveredDocFile(BaseModel):
    """Metadata for a discovered and parsed Markdown documentation file."""

    file_path: str
    size_bytes: int
    sections_count: int
    extracted_units_count: int
    mapped_units_count: int


class DocumentationAnalysisSummary(BaseModel):
    """High-level summary statistics for a documentation parsing and code mapping run."""

    discovered_doc_files_count: int
    skipped_files_count: int
    extracted_python_symbols_count: int
    extracted_units_count: int
    mapped_units_count: int
    unmapped_units_count: int
    ambiguous_units_count: int
    high_confidence_count: int
    medium_confidence_count: int
    low_confidence_count: int
    parse_errors_count: int


class DocumentationAnalysisRequest(BaseModel):
    """Request payload for POST /api/analyze/documentation."""

    github_repository_id: int = Field(
        ...,
        gt=0,
        description="Stable numeric GitHub repository ID from the authorized catalog",
    )
    base_commit: Optional[str] = Field(
        default=None,
        description="Optional base commit SHA for context",
    )
    head_commit: str = Field(
        ...,
        description="Head commit SHA from which documentation and Python symbols are analyzed",
    )


class DocumentationAnalysisResponse(BaseModel):
    """Response payload for POST /api/analyze/documentation."""

    repository_url: str
    owner: str
    name: str
    commit_sha: str
    base_commit: Optional[str] = None
    head_commit: str
    summary: DocumentationAnalysisSummary
    documentation_files: list[DiscoveredDocFile]
    skipped_files: list[SkippedFileItem]
    mappings: list[DocumentationMapping]
    parse_errors: list[ParseErrorItem]
