"""
Automated unit & integration tests for Milestone 3: Python AST Code Change Analysis.
Covers all 17 change types, all 5 Python parameter kinds, nested functions,
class/static methods, syntax errors, skipped non-Python files, multi-file Git
repository analysis, and static-only security guarantees.
"""

import os
import shutil
import tempfile

from fastapi.testclient import TestClient
import git
import pytest

from app.analyzers.python_ast_analyzer import analyze_python_file_change
from app.analyzers.symbol_extractor import extract_python_symbols
from app.main import app
from app.services import github_service

client = TestClient(app)


# ---------------------------------------------------------------------------
# 1. Function Added, Removed, Body Modified, and Conservatively Renamed
# ---------------------------------------------------------------------------


def test_function_added_and_removed():
    """Verify FUNCTION_ADDED and FUNCTION_REMOVED are detected accurately."""
    base_code = """
def old_helper(x):
    return x + 1
"""
    head_code = """
def new_helper(y, z):
    return y * z
"""
    report, changes, errors = analyze_python_file_change(
        file_path="src/helpers.py",
        file_change_type="modified",
        base_source=base_code,
        head_source=head_code,
    )
    assert not errors
    assert report.changes_count == 2
    by_type = {c.change_type: c for c in changes}
    assert "FUNCTION_REMOVED" in by_type
    assert by_type["FUNCTION_REMOVED"].symbol == "old_helper"
    assert "FUNCTION_ADDED" in by_type
    assert by_type["FUNCTION_ADDED"].symbol == "new_helper"


def test_function_body_modified():
    """Verify FUNCTION_MODIFIED is emitted when a function's implementation changes."""
    base_code = """
def compute_discount(price: float) -> float:
    return price * 0.9
"""
    head_code = """
def compute_discount(price: float) -> float:
    if price > 100:
        return price * 0.8
    return price * 0.95
"""
    _report, changes, errors = analyze_python_file_change(
        file_path="src/pricing.py",
        file_change_type="modified",
        base_source=base_code,
        head_source=head_code,
    )
    assert not errors
    assert len(changes) == 1
    assert changes[0].change_type == "FUNCTION_MODIFIED"
    assert changes[0].symbol == "compute_discount"
    assert changes[0].details["implementation_changed"] is True


def test_function_renamed_confident_and_conservative():
    """
    Verify FUNCTION_RENAMED is detected when body/signature match confidently,
    and NOT falsely reported when two functions have completely unrelated bodies.
    """
    base_code = """
def calculate_invoice_subtotal(items, tax_rate=0.05):
    subtotal = sum(item.price * item.qty for item in items)
    tax = subtotal * tax_rate
    return round(subtotal + tax, 2)
"""
    head_code = """
def compute_invoice_total(items, tax_rate=0.05):
    subtotal = sum(item.price * item.qty for item in items)
    tax = subtotal * tax_rate
    return round(subtotal + tax, 2)
"""
    _report, changes, errors = analyze_python_file_change(
        file_path="src/billing.py",
        file_change_type="modified",
        base_source=base_code,
        head_source=head_code,
    )
    assert not errors
    assert len(changes) == 1
    assert changes[0].change_type == "FUNCTION_RENAMED"
    assert changes[0].details["old_name"] == "calculate_invoice_subtotal"
    assert changes[0].details["new_name"] == "compute_invoice_total"

    # Unrelated functions with different bodies must report FUNCTION_REMOVED + FUNCTION_ADDED
    unrelated_base = """
def fetch_user(item_id: int) -> dict:
    db = connect_database()
    row = db.query("SELECT * FROM users WHERE id = ?", item_id)
    return {"user": row}
"""
    unrelated_head = """
def delete_order(item_id: int) -> dict:
    cache.evict_all()
    logger.warning("Order purged: %s", item_id)
    raise ValueError("Deprecated order endpoint")
"""
    _rep2, changes2, _err2 = analyze_python_file_change(
        file_path="src/orders.py",
        file_change_type="modified",
        base_source=unrelated_base,
        head_source=unrelated_head,
    )
    change_types = {c.change_type for c in changes2}
    assert "FUNCTION_RENAMED" not in change_types
    assert change_types == {"FUNCTION_REMOVED", "FUNCTION_ADDED"}


# ---------------------------------------------------------------------------
# 2. Parameter Added, Removed, Renamed, Reordered, Defaults & Annotations
# ---------------------------------------------------------------------------


def test_parameter_added_and_removed():
    """Verify PARAMETER_ADDED and PARAMETER_REMOVED on functions and methods."""
    base_code = """
def send_notification(user_id, message, legacy_flag):
    return True
"""
    head_code = """
def send_notification(user_id, message, priority="high"):
    return True
"""
    _report, changes, errors = analyze_python_file_change(
        file_path="src/notify.py",
        file_change_type="modified",
        base_source=base_code,
        head_source=head_code,
    )
    assert not errors
    by_type = {c.change_type: c for c in changes}
    assert "PARAMETER_REMOVED" in by_type
    assert by_type["PARAMETER_REMOVED"].details["parameter"] == "legacy_flag"
    assert "PARAMETER_ADDED" in by_type
    assert by_type["PARAMETER_ADDED"].details["parameter"] == "priority"
    assert by_type["PARAMETER_ADDED"].details["default"] == "'high'"


def test_parameter_renamed():
    """Verify PARAMETER_RENAMED when a single parameter slot changes name in place."""
    base_code = """
def connect_client(host_address: str, port: int = 8080):
    return (host_address, port)
"""
    head_code = """
def connect_client(hostname: str, port: int = 8080):
    return (host_address, port)
"""
    _report, changes, errors = analyze_python_file_change(
        file_path="src/client.py",
        file_change_type="modified",
        base_source=base_code,
        head_source=head_code,
    )
    assert not errors
    rename_changes = [c for c in changes if c.change_type == "PARAMETER_RENAMED"]
    assert len(rename_changes) == 1
    assert rename_changes[0].details["old_parameter"] == "host_address"
    assert rename_changes[0].details["new_parameter"] == "hostname"


def test_parameter_reordered():
    """Verify PARAMETER_REORDERED when existing parameters change relative order."""
    base_code = """
def format_range(start, end, step):
    return (start, end, step)
"""
    head_code = """
def format_range(end, start, step):
    return (start, end, step)
"""
    _report, changes, errors = analyze_python_file_change(
        file_path="src/ranges.py",
        file_change_type="modified",
        base_source=base_code,
        head_source=head_code,
    )
    assert not errors
    assert len(changes) == 1
    assert changes[0].change_type == "PARAMETER_REORDERED"
    assert changes[0].details["old_order"] == ["start", "end", "step"]
    assert changes[0].details["new_order"] == ["end", "start", "step"]


def test_default_value_and_annotations_changed():
    """Verify DEFAULT_VALUE_CHANGED, PARAMETER_ANNOTATION_CHANGED, and RETURN_ANNOTATION_CHANGED."""
    base_code = """
def paginate(page: int = 1, limit: int = 20) -> list:
    return []
"""
    head_code = """
def paginate(page: int = 1, limit: float = 50) -> tuple[list, int]:
    return []
"""
    _report, changes, errors = analyze_python_file_change(
        file_path="src/pagination.py",
        file_change_type="modified",
        base_source=base_code,
        head_source=head_code,
    )
    assert not errors
    by_type = {c.change_type: c for c in changes}
    assert "DEFAULT_VALUE_CHANGED" in by_type
    assert by_type["DEFAULT_VALUE_CHANGED"].details == {
        "parameter": "limit",
        "old_default": "20",
        "new_default": "50",
    }
    assert "PARAMETER_ANNOTATION_CHANGED" in by_type
    assert by_type["PARAMETER_ANNOTATION_CHANGED"].details == {
        "parameter": "limit",
        "old_annotation": "int",
        "new_annotation": "float",
    }
    assert "RETURN_ANNOTATION_CHANGED" in by_type
    assert by_type["RETURN_ANNOTATION_CHANGED"].details == {
        "old_return_annotation": "list",
        "new_return_annotation": "tuple[list, int]",
    }


# ---------------------------------------------------------------------------
# 3. Async Status Changes (Regular <-> Async)
# ---------------------------------------------------------------------------


def test_async_status_changed_both_directions():
    """Verify ASYNC_STATUS_CHANGED when switching sync -> async and async -> sync."""
    base_code = """
def sync_to_async(url: str):
    return url

async def async_to_sync(data: bytes):
    return len(data)
"""
    head_code = """
async def sync_to_async(url: str):
    return url

def async_to_sync(data: bytes):
    return len(data)
"""
    _report, changes, errors = analyze_python_file_change(
        file_path="src/workers.py",
        file_change_type="modified",
        base_source=base_code,
        head_source=head_code,
    )
    assert not errors
    async_changes = {
        c.symbol: c for c in changes if c.change_type == "ASYNC_STATUS_CHANGED"
    }
    assert len(async_changes) == 2
    assert async_changes["sync_to_async"].details == {
        "was_async": False,
        "is_async": True,
    }
    assert async_changes["async_to_sync"].details == {
        "was_async": True,
        "is_async": False,
    }


# ---------------------------------------------------------------------------
# 4. Classes, Class Methods, Static Methods, and Nested Functions
# ---------------------------------------------------------------------------


def test_class_and_method_added_removed_modified():
    """Verify CLASS_ADDED, CLASS_REMOVED, METHOD_ADDED, METHOD_REMOVED, METHOD_MODIFIED."""
    base_code = """
class LegacyAdapter:
    pass

class PaymentProcessor:
    def charge(self, amount: int) -> bool:
        return amount > 0

    def obsolete_method(self):
        return False
"""
    head_code = """
class AuditLogger:
    pass

class PaymentProcessor:
    def charge(self, amount: int) -> bool:
        return amount >= 10

    @classmethod
    def from_config(cls, cfg: dict):
        return cls()
"""
    _report, changes, errors = analyze_python_file_change(
        file_path="src/payments.py",
        file_change_type="modified",
        base_source=base_code,
        head_source=head_code,
    )
    assert not errors
    types_by_qname = {(c.qualified_name, c.change_type) for c in changes}
    assert ("LegacyAdapter", "CLASS_REMOVED") in types_by_qname
    assert ("AuditLogger", "CLASS_ADDED") in types_by_qname
    assert ("PaymentProcessor.charge", "METHOD_MODIFIED") in types_by_qname
    assert ("PaymentProcessor.obsolete_method", "METHOD_REMOVED") in types_by_qname
    assert ("PaymentProcessor.from_config", "METHOD_ADDED") in types_by_qname


def test_nested_functions_and_special_parameter_kinds():
    """
    Verify extraction of nested functions, positional-only (/), keyword-only (*),
    *args, **kwargs, @classmethod, and @staticmethod.
    """
    source = """
class MathEngine:
    @staticmethod
    def clamp(val: float, low: float = 0.0, /, high: float = 1.0, *extras: float, strict: bool = False, **meta) -> float:
        def inner_validate(target: float) -> bool:
            return low <= target <= high
        return val if inner_validate(val) else low
"""
    symbols, err = extract_python_symbols(source, "src/math_engine.py")
    assert err is None
    by_qname = {s.qualified_name: s for s in symbols}
    assert "MathEngine" in by_qname
    assert "MathEngine.clamp" in by_qname
    assert "MathEngine.clamp.inner_validate" in by_qname

    clamp_sym = by_qname["MathEngine.clamp"]
    assert clamp_sym.symbol_type == "method"
    assert clamp_sym.method_kind == "staticmethod"
    param_kinds = [(p.name, p.kind, p.default) for p in clamp_sym.parameters]
    assert param_kinds == [
        ("val", "positional_only", None),
        ("low", "positional_only", "0.0"),
        ("high", "positional_or_keyword", "1.0"),
        ("extras", "var_positional", None),
        ("strict", "keyword_only", "False"),
        ("meta", "var_keyword", None),
    ]
    assert "/" in clamp_sym.signature
    assert "*extras" in clamp_sym.signature
    assert "**meta" in clamp_sym.signature


# ---------------------------------------------------------------------------
# 5. Added File, Deleted File, Syntax Error, Unchanged Code, Security Check
# ---------------------------------------------------------------------------


def test_added_and_deleted_python_files():
    """Verify added files report all symbols added and deleted files report all symbols removed."""
    added_code = """
class TokenService:
    def issue(self, user: str) -> str:
        return user
"""
    rep_add, changes_add, err_add = analyze_python_file_change(
        file_path="src/tokens.py",
        file_change_type="added",
        base_source=None,
        head_source=added_code,
    )
    assert not err_add
    assert rep_add.base_symbol_count == 0
    assert rep_add.head_symbol_count == 2
    assert {c.change_type for c in changes_add} == {"CLASS_ADDED", "METHOD_ADDED"}

    rep_del, changes_del, err_del = analyze_python_file_change(
        file_path="src/tokens.py",
        file_change_type="deleted",
        base_source=added_code,
        head_source=None,
    )
    assert not err_del
    assert rep_del.base_symbol_count == 2
    assert rep_del.head_symbol_count == 0
    assert {c.change_type for c in changes_del} == {"CLASS_REMOVED", "METHOD_REMOVED"}


def test_invalid_python_syntax_returns_structured_parse_error():
    """Verify syntax errors do not crash analysis and produce structured ParseErrorItem."""
    valid_base = "def ok():\n    return 1\n"
    broken_head = "def broken(a, b:\n    return a + b\n"

    report, changes, errors = analyze_python_file_change(
        file_path="src/broken.py",
        file_change_type="modified",
        base_source=valid_base,
        head_source=broken_head,
    )
    assert report.has_parse_error is True
    assert len(errors) == 1
    assert errors[0].file_path == "src/broken.py"
    assert errors[0].version == "head"
    assert errors[0].line == 1
    assert errors[0].error_type == "SyntaxError"
    assert changes == []


def test_unchanged_source_and_never_executes_code():
    """
    Verify comments/whitespace changes produce 0 symbol changes, and top-level
    or default-argument payloads are NEVER executed or evaluated.
    """
    dangerous_base = """
import os
raise RuntimeError("THIS CODE MUST NEVER BE EXECUTED")

def dangerous_fn(cmd: str = os.system("echo PWNED")):
    # Initial comment
    return cmd
"""
    dangerous_head = """
import os
raise RuntimeError("THIS CODE MUST NEVER BE EXECUTED")

def dangerous_fn(cmd: str = os.system("echo PWNED")):
    # Updated comment and whitespace only

    return cmd
"""
    report, changes, errors = analyze_python_file_change(
        file_path="src/safe.py",
        file_change_type="modified",
        base_source=dangerous_base,
        head_source=dangerous_head,
    )
    assert not errors
    assert report.changes_count == 0
    assert changes == []


# ---------------------------------------------------------------------------
# 6. End-to-End API Integration Test on Local Temporary Git Repository
# ---------------------------------------------------------------------------


def test_analyze_code_api_endpoint_multi_file_git_repo(monkeypatch):
    """
    Test POST /api/analyze/code against a temporary local Git repository containing:
    - Modified Python file with parameter + return annotation changes
    - Newly added Python file
    - Deleted Python file
    - Python file with a syntax error (partial analysis resilience)
    - Non-Python file (README.md) that must be skipped
    """
    repo_dir = tempfile.mkdtemp(prefix="docguard_ast_test_")
    repo = git.Repo.init(repo_dir, initial_branch="main")

    with repo.config_writer() as cw:
        cw.set_value("user", "name", "DocGuard AST Tester")
        cw.set_value("user", "email", "ast@docguard.local")

    os.makedirs(os.path.join(repo_dir, "src"), exist_ok=True)

    # Commit 1
    with open(os.path.join(repo_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write("# Docs v1\n")
    with open(os.path.join(repo_dir, "src", "calculator.py"), "w", encoding="utf-8") as f:
        f.write(
            "class Calculator:\n"
            "    def calculate_total(self, price):\n"
            "        return price\n"
        )
    with open(os.path.join(repo_dir, "src", "deprecated.py"), "w", encoding="utf-8") as f:
        f.write("def old_api():\n    return 'v1'\n")
    with open(os.path.join(repo_dir, "src", "malformed.py"), "w", encoding="utf-8") as f:
        f.write("def valid_before():\n    return True\n")

    repo.index.add(
        ["README.md", "src/calculator.py", "src/deprecated.py", "src/malformed.py"]
    )
    c1 = repo.index.commit("Base commit for AST analysis")

    # Commit 2
    with open(os.path.join(repo_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write("# Docs v2\nUpdated markdown.\n")
    with open(os.path.join(repo_dir, "src", "calculator.py"), "w", encoding="utf-8") as f:
        f.write(
            "class Calculator:\n"
            "    def calculate_total(self, price, tax=0) -> float:\n"
            "        return float(price + tax)\n"
        )
    with open(os.path.join(repo_dir, "src", "new_service.py"), "w", encoding="utf-8") as f:
        f.write("async def fetch_rates(currency: str = 'USD') -> dict:\n    return {}\n")
    repo.index.remove(["src/deprecated.py"], working_tree=True)
    with open(os.path.join(repo_dir, "src", "malformed.py"), "w", encoding="utf-8") as f:
        f.write("def syntax_err(:\n    pass\n")

    repo.index.add(
        ["README.md", "src/calculator.py", "src/new_service.py", "src/malformed.py"]
    )
    c2 = repo.index.commit("Head commit with multi-file Python AST changes")

    try:
        monkeypatch.setattr(
            github_service,
            "_resolve_clone_source",
            lambda _url: repo_dir,
        )

        response = client.post(
            "/api/analyze/code",
            json={
                "repository_url": "https://github.com/octocat/DocGuard-Sample",
                "base_commit": c1.hexsha,
                "head_commit": c2.hexsha,
            },
        )
        assert response.status_code == 200
        data = response.json()

        assert data["owner"] == "octocat"
        assert data["name"] == "DocGuard-Sample"
        assert data["base_commit"] == c1.hexsha
        assert data["head_commit"] == c2.hexsha

        summary = data["summary"]
        assert summary["total_changed_files_in_diff"] == 5
        assert summary["analyzed_python_files_count"] == 4
        assert summary["skipped_files_count"] == 1
        assert summary["parse_errors_count"] == 1
        assert summary["total_symbol_changes"] >= 5

        # Non-Python file skipped
        assert data["skipped_files"] == [
            {"file_path": "README.md", "reason": "Non-Python file"}
        ]

        # Syntax error captured without crashing
        assert len(data["parse_errors"]) == 1
        assert data["parse_errors"][0]["file_path"] == "src/malformed.py"

        # Symbol changes across calculator.py, new_service.py, deprecated.py
        changes = data["changed_symbols"]
        change_keys = {(c["file_path"], c["qualified_name"], c["change_type"]) for c in changes}
        assert ("src/calculator.py", "Calculator.calculate_total", "PARAMETER_ADDED") in change_keys
        assert ("src/calculator.py", "Calculator.calculate_total", "RETURN_ANNOTATION_CHANGED") in change_keys
        assert ("src/calculator.py", "Calculator.calculate_total", "METHOD_MODIFIED") in change_keys
        assert ("src/new_service.py", "fetch_rates", "FUNCTION_ADDED") in change_keys
        assert ("src/deprecated.py", "old_api", "FUNCTION_REMOVED") in change_keys
    finally:
        try:
            repo.close()
        except Exception:
            pass
        shutil.rmtree(repo_dir, onerror=github_service._remove_readonly)
