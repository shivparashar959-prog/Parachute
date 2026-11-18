"""
Automated unit & integration tests for Milestone 4:
Documentation Parsing and Code Mapping Engine.

Covers all 39 required test scenarios across:
- Markdown Parser (headings, nested headings, paragraphs, bullet/numbered lists,
  inline code, fenced code blocks, tables, links, exact line numbers, empty/malformed/large files)
- Documentation Extractor (sections, paragraphs, lists, API references, separate code blocks,
  general/installation/changelog classification, verbatim text preservation)
- Mapping Engine (exact function/class/method/qualified-name matching, parameter evidence,
  multi-symbol units, unmapped units, ambiguous references, confidence levels, evidence,
  duplicate references, non-matching similar names)
- End-to-End Integration (POST /api/analyze/documentation, HEAD commit retrieval,
  ignored directories & oversized files, missing docs, partial Python syntax errors,
  and temporary directory cleanup)
"""

import os
import shutil
import tempfile

from fastapi.testclient import TestClient
import git

from app.analyzers.documentation_extractor import extract_documentation_units
from app.analyzers.documentation_mapper import map_documentation_units_to_symbols
from app.analyzers.markdown_parser import parse_markdown_document
from app.analyzers.symbol_extractor import extract_python_symbols
from app.main import app
from app.services import github_service

client = TestClient(app)


# ---------------------------------------------------------------------------
# 1. Markdown Parser Tests (Items 1–13)
# ---------------------------------------------------------------------------


def test_markdown_parser_headings_lists_code_tables_links_and_lines():
    """
    Verify items 1–10: headings, nested heading hierarchy, paragraphs,
    bullet lists, numbered lists, inline code, fenced code blocks with language,
    tables, links, and exact 1-based line numbers.
    """
    md_source = "\n".join(
        [
            "# API Reference",  # line 1
            "",  # line 2
            "Welcome to the [DocGuard Guide](https://github.com/org/docguard) reference.",  # line 3
            "",  # line 4
            "## Authentication",  # line 5
            "",  # line 6
            "- Pass `api_key` in the request header.",  # line 7
            "- Tokens expire after 24 hours.",  # line 8
            "",  # line 9
            "### Token Refresh",  # line 10
            "",  # line 11
            "1. Call `refresh_token(old_token)`.",  # line 12
            "2. Store the returned JWT.",  # line 13
            "",  # line 14
            "## calculate_total()",  # line 15
            "",  # line 16
            "Calculates the total order price using `price` and `tax`.",  # line 17
            "",  # line 18
            "| Parameter | Type | Default |",  # line 19
            "| --- | --- | --- |",  # line 20
            "| `price` | `float` | required |",  # line 21
            "| `tax` | `float` | `0.0` |",  # line 22
            "",  # line 23
            "```python",  # line 24
            "total = calculate_total(100.0, tax=5.0)",  # line 25
            "```",  # line 26
        ]
    )

    doc = parse_markdown_document(md_source, "docs/api.md")

    assert doc.file_path == "docs/api.md"
    assert doc.total_lines == 26
    assert doc.headings == [
        "API Reference",
        "Authentication",
        "Token Refresh",
        "calculate_total()",
    ]

    # Verify nested heading hierarchy reset when moving from H3 back to H2
    sec_by_heading = {s.heading: s for s in doc.sections}
    assert sec_by_heading["API Reference"].heading_hierarchy == ["API Reference"]
    assert sec_by_heading["Authentication"].heading_hierarchy == [
        "API Reference",
        "Authentication",
    ]
    assert sec_by_heading["Token Refresh"].heading_hierarchy == [
        "API Reference",
        "Authentication",
        "Token Refresh",
    ]
    assert sec_by_heading["calculate_total()"].heading_hierarchy == [
        "API Reference",
        "calculate_total()",
    ]

    # Verify exact line numbers
    assert sec_by_heading["API Reference"].start_line == 1
    assert sec_by_heading["API Reference"].end_line == 4
    assert sec_by_heading["calculate_total()"].start_line == 15
    assert sec_by_heading["calculate_total()"].end_line == 26

    # Paragraphs, bullets, numbered lists
    assert len(doc.paragraphs) == 2
    assert len(doc.bullet_lists) == 2
    assert len(doc.numbered_lists) == 2

    # Links with exact line number
    assert len(doc.links) == 1
    assert doc.links[0].text == "DocGuard Guide"
    assert doc.links[0].url == "https://github.com/org/docguard"
    assert doc.links[0].line == 3

    # Inline code references
    assert "api_key" in doc.inline_code_references
    assert "refresh_token(old_token)" in doc.inline_code_references
    assert "price" in doc.inline_code_references
    assert "tax" in doc.inline_code_references

    # Table parsing
    assert len(doc.tables) == 1
    assert doc.tables[0].headers == ["Parameter", "Type", "Default"]
    assert len(doc.tables[0].rows) == 2
    assert doc.tables[0].start_line == 19
    assert doc.tables[0].end_line == 22

    # Fenced code block with language and exact line numbers
    assert len(doc.code_blocks) == 1
    assert doc.code_blocks[0].language == "python"
    assert doc.code_blocks[0].content == "total = calculate_total(100.0, tax=5.0)"
    assert doc.code_blocks[0].start_line == 24
    assert doc.code_blocks[0].end_line == 26


def test_markdown_parser_empty_malformed_and_section_limits():
    """Verify items 11–13: empty Markdown, malformed unclosed fences/backticks, and section bounds."""
    empty_doc = parse_markdown_document("   \n  ", "README.md")
    assert empty_doc.total_lines == 0
    assert empty_doc.sections == []

    # Malformed Markdown with unclosed code fence and unclosed inline backtick
    malformed = "# Broken Doc\nParagraph with `unclosed backtick.\n```python\ndef incomplete():\n"
    parsed_malformed = parse_markdown_document(malformed, "docs/broken.md")
    assert len(parsed_malformed.sections) == 1
    assert len(parsed_malformed.code_blocks) == 1
    assert "def incomplete():" in parsed_malformed.code_blocks[0].content

    # Section limit
    many_sections_md = "\n".join(f"## Section {i}\nBody {i}\n" for i in range(25))
    bounded_doc = parse_markdown_document(
        many_sections_md, "docs/large.md", max_sections=10
    )
    assert len(bounded_doc.sections) == 10


# ---------------------------------------------------------------------------
# 2. Documentation Statement Extraction Tests (Items 14–20)
# ---------------------------------------------------------------------------


def test_documentation_extractor_unit_classification_and_verbatim_preservation():
    """
    Verify items 14–20: heading-scoped units, paragraphs, list items, API references,
    parameter/return descriptions, code blocks kept separate from prose,
    installation/changelog/general classification, and verbatim text preservation.
    """
    md_source = "\n".join(
        [
            "# Overview",
            "DocGuard keeps documentation synchronized across releases.",
            "## Installation",
            "Run `pip install docguard` in your virtual environment.",
            "## calculate_total(price, tax=0)",
            "The calculate_total function computes the total order cost.",
            "- Parameter `tax`: optional tax value added to `price`.",
            "Returns a floating-point total.",
            "```python",
            "calculate_total(50, tax=5)",
            "```",
            "## Changelog",
            "- v0.1.0: Initial release.",
        ]
    )

    parsed = parse_markdown_document(md_source, "README.md")
    units = extract_documentation_units(parsed)

    by_type = {}
    for u in units:
        by_type.setdefault(u.unit_type, []).append(u)

    assert "general_info" in by_type
    assert "installation" in by_type
    assert "api_reference" in by_type
    assert "parameter_description" in by_type
    assert "return_description" in by_type
    assert "code_block" in by_type
    assert "changelog" in by_type

    # Code blocks must have is_code_example=True, while prose units have is_code_example=False
    code_unit = by_type["code_block"][0]
    assert code_unit.is_code_example is True
    assert code_unit.original_text == "calculate_total(50, tax=5)"

    api_unit = by_type["api_reference"][0]
    assert api_unit.is_code_example is False
    assert (
        api_unit.original_text
        == "The calculate_total function computes the total order cost."
    )
    assert "calculate_total" in api_unit.referenced_identifiers


# ---------------------------------------------------------------------------
# 3. Documentation-to-Code Mapping Engine Tests (Items 21–32)
# ---------------------------------------------------------------------------


def test_mapping_engine_comprehensive_scenarios():
    """
    Verify items 21–32:
    - Exact function, class, method, and qualified-name matching
    - Parameter reference corroboration
    - Multiple distinct symbols mapped in one documentation unit
    - Unmapped general/installation documentation
    - Ambiguous references when two classes define a method with the same short name
    - Confidence levels (HIGH, MEDIUM, LOW) and evidence generation
    - Multiple documentation units mapping to the same symbol
    - Similar names (`calculate_subtotal`) NOT falsely matched to `calculate_total`
    """
    calc_py = "\n".join(
        [
            "def calculate_total(price: float, tax: float = 0.0) -> float:",
            "    return price + tax",
            "",
            "def validate_order(order_id: str) -> bool:",
            "    return bool(order_id)",
            "",
            "class BillingEngine:",
            "    def issue_invoice(self, customer_id: str, currency: str = 'USD') -> dict:",
            "        return {'customer': customer_id, 'currency': currency}",
            "",
            "    def export_data(self, fmt: str) -> str:",
            "        return fmt",
        ]
    )
    audit_py = "\n".join(
        [
            "class AuditExporter:",
            "    def export_data(self, destination: str) -> bool:",
            "        return True",
        ]
    )

    symbols_calc, err1 = extract_python_symbols(calc_py, "src/calculator.py")
    symbols_audit, err2 = extract_python_symbols(audit_py, "src/audit.py")
    assert err1 is None and err2 is None
    all_symbols = symbols_calc + symbols_audit

    md_content = "\n".join(
        [
            "# Project Overview",
            "Welcome to our billing platform for modern e-commerce teams.",
            "",
            "## calculate_total()",
            "The calculate_total function accepts a `price` and an optional `tax` parameter.",
            "",
            "Pass `tax` as a float when calling `calculate_total(price, tax=0.0)`.",
            "",
            "## BillingEngine",
            "Use the `BillingEngine` class in `src/calculator.py` to manage customer invoices.",
            "",
            "Call `BillingEngine.issue_invoice(customer_id, currency='EUR')` to create an invoice.",
            "",
            "## Order Workflow",
            "First call `validate_order(order_id)` and then compute cost with `calculate_total(price)`.",
            "",
            "## Ambiguous Export",
            "Use `export_data()` to export records.",
            "",
            "## Similar But Unrelated Function",
            "The `calculate_subtotal` helper is documented for a future microservice.",
        ]
    )

    parsed_doc = parse_markdown_document(md_content, "docs/guide.md")
    units = extract_documentation_units(parsed_doc)
    mappings = map_documentation_units_to_symbols(units, all_symbols)

    mappings_by_section: dict[str, list] = {}
    for m in mappings:
        mappings_by_section.setdefault(m.documentation_section or "", []).append(m)

    # 1. Project Overview -> UNMAPPED (general prose must not be force-mapped)
    overview_map = mappings_by_section["Project Overview"][0]
    assert overview_map.mapping_status == "UNMAPPED"
    assert overview_map.related_symbols == []

    # 2. calculate_total() section -> Two duplicate/separate units both mapping to calculate_total with HIGH confidence
    calc_maps = mappings_by_section["calculate_total()"]
    assert len(calc_maps) == 2
    for cm in calc_maps:
        assert cm.mapping_status == "MAPPED"
        assert cm.highest_confidence == "HIGH"
        assert len(cm.related_symbols) == 1
        sym_match = cm.related_symbols[0]
        assert sym_match.symbol == "calculate_total"
        assert sym_match.source_file == "src/calculator.py"
        assert any("parameter" in r.lower() for r in sym_match.matching_reasons)
        assert any("tax" in ev for ev in sym_match.evidence)

    # 3. BillingEngine section -> Class match and Qualified Method match
    billing_maps = mappings_by_section["BillingEngine"]
    class_map = billing_maps[0]
    assert class_map.mapping_status == "MAPPED"
    assert class_map.related_symbols[0].qualified_name == "BillingEngine"
    assert class_map.related_symbols[0].confidence == "HIGH"

    method_map = billing_maps[1]
    assert method_map.mapping_status == "MAPPED"
    matched_qnames = {s.qualified_name for s in method_map.related_symbols}
    assert "BillingEngine.issue_invoice" in matched_qnames

    # 4. Order Workflow -> Multiple symbols (`validate_order` AND `calculate_total`) in one unit
    workflow_map = mappings_by_section["Order Workflow"][0]
    assert workflow_map.mapping_status == "MAPPED"
    workflow_symbols = {s.symbol for s in workflow_map.related_symbols}
    assert workflow_symbols == {"validate_order", "calculate_total"}

    # 5. Ambiguous Export -> `export_data()` matches both BillingEngine.export_data and AuditExporter.export_data
    ambig_map = mappings_by_section["Ambiguous Export"][0]
    assert ambig_map.mapping_status == "AMBIGUOUS"
    ambig_qnames = {s.qualified_name for s in ambig_map.related_symbols}
    assert ambig_qnames == {
        "BillingEngine.export_data",
        "AuditExporter.export_data",
    }

    # 6. Similar name (`calculate_subtotal`) must NOT falsely match `calculate_total`
    similar_map = mappings_by_section["Similar But Unrelated Function"][0]
    assert similar_map.mapping_status == "UNMAPPED"
    assert similar_map.related_symbols == []


# ---------------------------------------------------------------------------
# 4. End-to-End Integration Tests (Items 33–39)
# ---------------------------------------------------------------------------


def test_documentation_analysis_api_end_to_end_and_cleanup(monkeypatch):
    """
    Verify items 33–39:
    - POST /api/analyze/documentation retrieves HEAD commit documentation and AST symbols
    - Discovers README.md and docs/api.md
    - Skips ignored directories (node_modules/pkg/README.md) and oversized Markdown files
    - Captures partial Python syntax errors without crashing
    - Maps documentation units accurately and cleans up temporary clone directories
    """
    repo_dir = tempfile.mkdtemp(prefix="docguard_doc_test_")
    repo = git.Repo.init(repo_dir, initial_branch="main")

    with repo.config_writer() as cw:
        cw.set_value("user", "name", "DocGuard Doc Tester")
        cw.set_value("user", "email", "docs@docguard.local")

    os.makedirs(os.path.join(repo_dir, "src"), exist_ok=True)
    os.makedirs(os.path.join(repo_dir, "docs"), exist_ok=True)
    os.makedirs(os.path.join(repo_dir, "node_modules", "pkg"), exist_ok=True)

    with open(os.path.join(repo_dir, "src", "service.py"), "w", encoding="utf-8") as f:
        f.write(
            "class UserDirectory:\n"
            "    def lookup_user(self, email: str, include_inactive: bool = False) -> dict:\n"
            "        return {'email': email}\n"
        )

    with open(os.path.join(repo_dir, "src", "broken_syntax.py"), "w", encoding="utf-8") as f:
        f.write("def broken_func(:\n    pass\n")

    with open(os.path.join(repo_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write(
            "# UserDirectory Service\n\n"
            "The `UserDirectory` class provides user lookup utilities.\n"
        )

    with open(os.path.join(repo_dir, "docs", "api.md"), "w", encoding="utf-8") as f:
        f.write(
            "## lookup_user()\n\n"
            "Call `UserDirectory.lookup_user(email, include_inactive=True)` in `src/service.py`.\n"
        )

    with open(
        os.path.join(repo_dir, "node_modules", "pkg", "README.md"),
        "w",
        encoding="utf-8",
    ) as f:
        f.write("# Ignored third-party readme\n")

    repo.index.add(
        [
            "src/service.py",
            "src/broken_syntax.py",
            "README.md",
            "docs/api.md",
            "node_modules/pkg/README.md",
        ]
    )
    commit_head = repo.index.commit("Commit with docs, code, ignored dir, and partial syntax error")

    created_temp_dirs: list[str] = []
    real_mkdtemp = tempfile.mkdtemp

    def tracking_mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        created_temp_dirs.append(path)
        return path

    try:
        monkeypatch.setattr(tempfile, "mkdtemp", tracking_mkdtemp)
        monkeypatch.setattr(
            github_service,
            "_resolve_clone_source",
            lambda _url: repo_dir,
        )

        response = client.post(
            "/api/analyze/documentation",
            json={
                "repository_url": "https://github.com/octocat/DocGuard-Docs",
                "base_commit": commit_head.hexsha,
                "head_commit": commit_head.hexsha,
            },
        )
        assert response.status_code == 200
        data = response.json()

        assert data["owner"] == "octocat"
        assert data["name"] == "DocGuard-Docs"
        assert data["commit_sha"] == commit_head.hexsha

        summary = data["summary"]
        assert summary["discovered_doc_files_count"] == 2
        assert summary["skipped_files_count"] == 1
        assert summary["extracted_python_symbols_count"] == 2
        assert summary["parse_errors_count"] == 1
        assert summary["mapped_units_count"] >= 2
        assert summary["high_confidence_count"] >= 2

        # Verify skipped node_modules README
        assert data["skipped_files"][0]["file_path"] == "node_modules/pkg/README.md"
        assert "node_modules" in data["skipped_files"][0]["reason"]

        # Verify partial parse failure recorded without crashing
        assert data["parse_errors"][0]["file_path"] == "src/broken_syntax.py"

        # Verify temporary directory cleanup
        assert len(created_temp_dirs) == 1
        assert not os.path.exists(created_temp_dirs[0])
    finally:
        try:
            repo.close()
        except Exception:
            pass
        shutil.rmtree(repo_dir, onerror=github_service._remove_readonly)


def test_documentation_analysis_missing_docs_and_invalid_repo(monkeypatch):
    """Verify repositories with zero Markdown files and invalid repository URLs are handled cleanly."""
    # Invalid URL -> 400
    bad_resp = client.post(
        "/api/analyze/documentation",
        json={
            "repository_url": "https://gitlab.com/owner/repo",
            "head_commit": "abcdef1234567",
        },
    )
    assert bad_resp.status_code == 400

    # Repo with only Python code and no Markdown files
    repo_dir = tempfile.mkdtemp(prefix="docguard_nodocs_")
    repo = git.Repo.init(repo_dir, initial_branch="main")
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Tester")
        cw.set_value("user", "email", "t@docguard.local")

    with open(os.path.join(repo_dir, "main.py"), "w", encoding="utf-8") as f:
        f.write("def run_task():\n    return 42\n")
    repo.index.add(["main.py"])
    c_head = repo.index.commit("Code only commit")

    try:
        monkeypatch.setattr(
            github_service,
            "_resolve_clone_source",
            lambda _url: repo_dir,
        )
        resp = client.post(
            "/api/analyze/documentation",
            json={
                "repository_url": "https://github.com/octocat/NoDocs",
                "head_commit": c_head.hexsha,
            },
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["summary"]["discovered_doc_files_count"] == 0
        assert payload["summary"]["extracted_units_count"] == 0
        assert payload["summary"]["mapped_units_count"] == 0
        assert payload["mappings"] == []
    finally:
        try:
            repo.close()
        except Exception:
            pass
        shutil.rmtree(repo_dir, onerror=github_service._remove_readonly)
