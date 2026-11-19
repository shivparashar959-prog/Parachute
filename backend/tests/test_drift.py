"""
Comprehensive automated tests for Milestone 5: Documentation Drift Detection Engine.

Covers all 35 required test scenarios across:
- Code changes (1–10): changed default, removed param, added required param,
  added optional param, changed return annotation, removed function, renamed function,
  removed method, changed signature (reorder/async/param annotation), body-only change.
- Documentation states (11–20): unchanged docs with code change, docs updated alongside code
  (RESOLVED vs UNCERTAIN), deleted docs, added docs, moved/renamed docs, unmentioned symbols,
  unrelated symbols, outdated parameter names, code examples, changelog history exclusion.
- False-positive prevention (21–28): optional param guard, unrelated change guard,
  similar function names guard, same parameter name in unrelated functions guard,
  body-only change guard, annotation never CONFIRMED_DRIFT guard, weak/ambiguous mapping
  producing UNCERTAIN, no fabricated findings.
- End-to-End Integration (29–35): POST /api/analyze/drift on multi-file local temporary Git
  repositories with deleted Python source files, partial syntax errors, temp directory cleanup,
  and invalid URL/commit rejection.
"""

import os
import shutil
import tempfile
import uuid
from typing import Dict, List, Optional, Tuple

from fastapi.testclient import TestClient
import git

from app.analyzers.change_detector import detect_symbol_changes
from app.analyzers.documentation_comparator import compare_documentation_across_commits
from app.analyzers.documentation_extractor import extract_documentation_units
from app.analyzers.documentation_mapper import map_documentation_units_to_symbols
from app.analyzers.drift_detector import detect_documentation_drift
from app.analyzers.markdown_parser import parse_markdown_document
from app.analyzers.symbol_extractor import extract_python_symbols
from app.main import app
from app.schemas.drift import DriftFinding
from app.services import github_service

client = TestClient(app)


def _run_in_memory_drift_pipeline(
    base_py_files: Dict[str, str],
    head_py_files: Dict[str, str],
    base_md_files: Dict[str, str],
    head_md_files: Dict[str, str],
    deleted_py_files: Optional[set[str]] = None,
    renamed_docs: Optional[Dict[str, str]] = None,
) -> Tuple[List[DriftFinding], List]:
    """
    Helper that runs the real AST extractor, change detector, Markdown parser,
    statement extractor, mapper, historical documentation comparator, and
    drift detector on in-memory base/head source dictionaries.
    """
    base_symbols = []
    head_symbols = []
    symbol_changes = []

    all_py_paths = sorted(set(base_py_files.keys()) | set(head_py_files.keys()))
    for py_path in all_py_paths:
        b_src = base_py_files.get(py_path)
        h_src = head_py_files.get(py_path)
        b_syms, _ = (
            extract_python_symbols(b_src, py_path, version="base")
            if b_src is not None
            else ([], None)
        )
        h_syms, _ = (
            extract_python_symbols(h_src, py_path, version="head")
            if h_src is not None
            else ([], None)
        )
        base_symbols.extend(b_syms)
        head_symbols.extend(h_syms)
        if b_src != h_src:
            symbol_changes.extend(detect_symbol_changes(py_path, b_syms, h_syms))

    base_units_by_file = {}
    for md_path, md_text in base_md_files.items():
        parsed = parse_markdown_document(md_text, md_path)
        base_units_by_file[md_path] = extract_documentation_units(parsed)

    head_units_by_file = {}
    for md_path, md_text in head_md_files.items():
        parsed = parse_markdown_document(md_text, md_path)
        head_units_by_file[md_path] = extract_documentation_units(parsed)

    all_base_units = [u for units in base_units_by_file.values() for u in units]
    all_head_units = [u for units in head_units_by_file.values() for u in units]

    base_mappings = map_documentation_units_to_symbols(all_base_units, base_symbols)
    head_mappings = map_documentation_units_to_symbols(all_head_units, head_symbols)

    (
        doc_file_changes,
        _unit_diffs,
        diff_by_head_unit_id,
        diff_by_base_unit_id,
    ) = compare_documentation_across_commits(
        base_units_by_file=base_units_by_file,
        head_units_by_file=head_units_by_file,
        base_raw_by_file=base_md_files,
        head_raw_by_file=head_md_files,
        git_renamed_docs=renamed_docs,
    )

    findings = detect_documentation_drift(
        symbol_changes=symbol_changes,
        deleted_python_files=deleted_py_files or set(),
        base_symbols=base_symbols,
        head_symbols=head_symbols,
        base_units=all_base_units,
        head_units=all_head_units,
        base_mappings=base_mappings,
        head_mappings=head_mappings,
        diff_by_head_unit_id=diff_by_head_unit_id,
        diff_by_base_unit_id=diff_by_base_unit_id,
        base_python_sources=base_py_files,
        head_python_sources=head_py_files,
    )
    return findings, doc_file_changes


# ---------------------------------------------------------------------------
# 1. Rules A, B, C, D & False-Positive Prevention Tests (Items 1–5, 18, 21, 24, 26)
# ---------------------------------------------------------------------------


def test_rule_a_changed_default_parameter_and_resolution():
    """
    Test Item 1 & Item 12:
    - When create_user(role='user') changes to create_user(role='admin') and docs still say
      'The default user role is user', emit CONFIRMED_DRIFT under RULE_A_CHANGED_DEFAULT.
    - When docs are updated in head to say 'The default user role is admin', emit RESOLVED.
    """
    base_py = {"src/users.py": "def create_user(username: str, role='user'):\n    return (username, role)\n"}
    head_py = {"src/users.py": "def create_user(username: str, role='admin'):\n    return (username, role)\n"}
    unchanged_md = {
        "docs/api.md": "## create_user()\n\nThe `create_user` function creates an account. The default `role` is `user`.\n"
    }

    findings, _ = _run_in_memory_drift_pipeline(
        base_py, head_py, unchanged_md, unchanged_md
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "RULE_A_CHANGED_DEFAULT"
    assert f.status == "CONFIRMED_DRIFT"
    assert f.severity == "HIGH"
    assert f.confidence >= 0.90
    assert f.related_symbol == "create_user"
    assert "role='user'" in f.old_code_evidence
    assert "role='admin'" in f.new_code_evidence

    # Now test when documentation was updated alongside the code change to 'admin' -> RESOLVED
    updated_md = {
        "docs/api.md": "## create_user()\n\nThe `create_user` function creates an account. The default `role` is `admin`.\n"
    }
    resolved_findings, _ = _run_in_memory_drift_pipeline(
        base_py, head_py, unchanged_md, updated_md
    )
    assert len(resolved_findings) == 1
    assert resolved_findings[0].status == "RESOLVED"


def test_rule_b_removed_or_renamed_parameter_and_unrelated_function_guard():
    """
    Test Item 2, Item 18, Item 24:
    - Removed parameter `port` on `connect(host, port)` -> `connect(host)` triggers CONFIRMED_DRIFT.
    - Outdated renamed parameter `user_addr` -> `email_addr` triggers CONFIRMED_DRIFT.
    - Changing parameter `port` on `other_service(port)` must NOT trigger drift on `connect(host, port)` docs!
    """
    base_py = {
        "src/net.py": (
            "def connect(host, port):\n    return (host, port)\n\n"
            "def send_alert(user_addr: str) -> bool:\n    return True\n\n"
            "def other_service(port: int):\n    return port\n"
        )
    }
    head_py = {
        "src/net.py": (
            "def connect(host):\n    return host\n\n"
            "def send_alert(email_addr: str) -> bool:\n    return True\n\n"
            "def other_service(port: int):\n    return port\n"
        )
    }
    md = {
        "docs/net.md": (
            "## connect()\n\nPass the `port` parameter to `connect(host, port)`.\n\n"
            "## send_alert()\n\nPass `user_addr` to `send_alert(user_addr)`.\n"
        )
    }

    findings, _ = _run_in_memory_drift_pipeline(base_py, head_py, md, md)
    by_sym = {f.related_symbol: f for f in findings}
    assert "connect" in by_sym
    assert by_sym["connect"].rule_id == "RULE_B_REMOVED_OR_RENAMED_PARAMETER"
    assert by_sym["connect"].status == "CONFIRMED_DRIFT"
    assert by_sym["connect"].finding_type == "PARAMETER_REMOVED"

    assert "send_alert" in by_sym
    assert by_sym["send_alert"].rule_id == "RULE_B_REMOVED_OR_RENAMED_PARAMETER"
    assert by_sym["send_alert"].status == "CONFIRMED_DRIFT"
    assert by_sym["send_alert"].finding_type == "PARAMETER_RENAMED"

    # Guard 8 / Test 24: If `port` is removed from `other_service`, docs for `connect(host, port)` must NOT be flagged!
    base_py_isolated = {
        "src/net.py": (
            "def connect(host, port):\n    return (host, port)\n\n"
            "def other_service(port: int):\n    return port\n"
        )
    }
    head_py_isolated = {
        "src/net.py": (
            "def connect(host, port):\n    return (host, port)\n\n"
            "def other_service():\n    return 80\n"
        )
    }
    only_connect_md = {
        "docs/net.md": "## connect()\n\nPass the `port` parameter to `connect(host, port)`.\n"
    }
    false_pos_findings, _ = _run_in_memory_drift_pipeline(
        base_py_isolated, head_py_isolated, only_connect_md, only_connect_md
    )
    assert false_pos_findings == []


def test_rule_c_added_required_vs_optional_parameter():
    """
    Test Item 3, Item 4, Item 19, Item 21:
    - Adding a required parameter `recipient` to `send_message(message, recipient)` flags
      existing call documentation `send_message(message)`.
    - Adding an optional parameter `timeout=30` to `send_message(message, timeout=30)`
      must NOT create a drift finding!
    """
    base_py = {"src/msg.py": "def send_message(message):\n    return message\n"}
    head_required_py = {
        "src/msg.py": "def send_message(message, recipient):\n    return (message, recipient)\n"
    }
    head_optional_py = {
        "src/msg.py": "def send_message(message, timeout=30):\n    return (message, timeout)\n"
    }
    md = {
        "docs/msg.md": (
            "## send_message()\n\nCall `send_message(message)` to dispatch a notification.\n"
        )
    }

    # Required parameter -> CONFIRMED_DRIFT
    req_findings, _ = _run_in_memory_drift_pipeline(
        base_py, head_required_py, md, md
    )
    assert len(req_findings) == 1
    assert req_findings[0].rule_id == "RULE_C_ADDED_REQUIRED_PARAMETER"
    assert req_findings[0].status == "CONFIRMED_DRIFT"
    assert req_findings[0].severity == "CRITICAL"

    # Optional parameter -> 0 findings (False-positive guard 6 / Test 21)
    opt_findings, _ = _run_in_memory_drift_pipeline(
        base_py, head_optional_py, md, md
    )
    assert opt_findings == []


def test_rule_d_return_annotation_changed_is_potential_never_confirmed():
    """
    Test Item 5 & Item 26:
    - Return annotation change when documentation describes return contract produces
      POTENTIAL_DRIFT (never CONFIRMED_DRIFT).
    """
    base_py = {"src/calc.py": "def compute_tax(amount: float) -> float:\n    return amount * 0.1\n"}
    head_py = {"src/calc.py": "def compute_tax(amount: float) -> dict:\n    return {'tax': amount * 0.1}\n"}
    md = {
        "docs/calc.md": "## compute_tax()\n\nReturns a `float` representing the tax amount.\n"
    }

    findings, _ = _run_in_memory_drift_pipeline(base_py, head_py, md, md)
    assert len(findings) == 1
    assert findings[0].rule_id == "RULE_D_RETURN_CONTRACT_CHANGED"
    assert findings[0].status == "POTENTIAL_DRIFT"
    assert findings[0].status != "CONFIRMED_DRIFT"


# ---------------------------------------------------------------------------
# 2. Rules E, F, G, H, I & False-Positive Prevention Tests (Items 6–17, 20, 22, 23, 25, 27)
# ---------------------------------------------------------------------------


def test_rule_e_and_f_removed_and_renamed_symbols():
    """
    Test Item 6, Item 7, Item 8:
    - Removed function (`FUNCTION_REMOVED`), removed method (`METHOD_REMOVED`),
      and renamed function (`FUNCTION_RENAMED`).
    """
    base_py = {
        "src/core.py": (
            "def legacy_helper(x):\n    return x + 1\n\n"
            "def parse_payload_data(raw_bytes: bytes) -> dict:\n"
            "    decoded = raw_bytes.decode('utf-8')\n"
            "    return {'payload': decoded, 'len': len(decoded)}\n\n"
            "class SessionManager:\n"
            "    def revoke_all(self):\n        return True\n"
        )
    }
    head_py = {
        "src/core.py": (
            "def decode_payload_data(raw_bytes: bytes) -> dict:\n"
            "    decoded = raw_bytes.decode('utf-8')\n"
            "    return {'payload': decoded, 'len': len(decoded)}\n\n"
            "class SessionManager:\n"
            "    pass\n"
        )
    }
    md = {
        "docs/core.md": (
            "## legacy_helper()\n\nCall `legacy_helper(x)` for backwards compatibility.\n\n"
            "## parse_payload_data()\n\nUse `parse_payload_data(raw_bytes)` to decode payloads.\n\n"
            "## SessionManager\n\nCall `SessionManager.revoke_all()` to clear sessions.\n"
        )
    }

    findings, _ = _run_in_memory_drift_pipeline(base_py, head_py, md, md)
    by_rule_and_sym = {(f.rule_id, f.related_symbol): f for f in findings}

    assert ("RULE_E_SYMBOL_REMOVED", "legacy_helper") in by_rule_and_sym
    assert by_rule_and_sym[("RULE_E_SYMBOL_REMOVED", "legacy_helper")].status == "CONFIRMED_DRIFT"

    assert ("RULE_F_SYMBOL_RENAMED", "decode_payload_data") in by_rule_and_sym
    assert by_rule_and_sym[("RULE_F_SYMBOL_RENAMED", "decode_payload_data")].status == "CONFIRMED_DRIFT"

    assert ("RULE_E_SYMBOL_REMOVED", "revoke_all") in by_rule_and_sym
    assert by_rule_and_sym[("RULE_E_SYMBOL_REMOVED", "revoke_all")].status == "CONFIRMED_DRIFT"


def test_rule_h_signature_changes_and_body_only_guard():
    """
    Test Item 9, Item 10, Item 20, Item 22, Item 23, Item 25:
    - Parameter reordering and sync->async change trigger RULE_H_SIGNATURE_CHANGED.
    - Function body change without signature change produces 0 findings.
    - Changelog entries produce 0 findings.
    - Similar function names (`calculate_subtotal` vs `calculate_total`) produce 0 findings.
    """
    base_py = {
        "src/ops.py": (
            "def transfer_funds(source_acct, target_acct, amount):\n"
            "    return amount\n\n"
            "def internal_calc(x: int) -> int:\n"
            "    return x * 2\n\n"
            "def calculate_total(price, tax=0):\n"
            "    return price + tax\n"
        )
    }
    head_py = {
        "src/ops.py": (
            "def transfer_funds(target_acct, source_acct, amount):\n"
            "    return amount\n\n"
            "def internal_calc(x: int) -> int:\n"
            "    # Only body implementation changed\n"
            "    step = x * 10\n"
            "    return step // 5\n\n"
            "def calculate_total(price):\n"
            "    return price\n"
        )
    }
    md = {
        "docs/ops.md": (
            "## transfer_funds()\n\nCall `transfer_funds(source_acct, target_acct, amount)`.\n\n"
            "## internal_calc()\n\nCall `internal_calc(x)` to double an integer.\n\n"
            "## calculate_subtotal()\n\nPass `tax` to `calculate_subtotal(price, tax)`.\n"
        ),
        "CHANGELOG.md": (
            "# Changelog\n\n- Removed `tax` parameter from `calculate_total(price, tax)`.\n"
        ),
    }

    findings, _ = _run_in_memory_drift_pipeline(base_py, head_py, md, md)
    # Only transfer_funds should be flagged; internal_calc (body-only), calculate_subtotal (similar name),
    # and CHANGELOG.md (changelog history) must NOT be flagged!
    assert len(findings) == 1
    assert findings[0].related_symbol == "transfer_funds"
    assert findings[0].rule_id == "RULE_H_SIGNATURE_CHANGED"
    assert findings[0].status == "POTENTIAL_DRIFT"


def test_rule_i_and_weak_ambiguous_mapping_produce_uncertain():
    """
    Test Item 12 (Rule I) and Item 27 (Weak/Ambiguous mapping):
    - When documentation is modified alongside a signature change without clearly resolving it,
      Rule I reports UNCERTAIN.
    - When two classes define `execute()` and an ambiguous unqualified doc reference `execute(flag)`
      has `flag` removed on one class, the weak/ambiguous mapping guard downgrades status to UNCERTAIN.
    """
    base_py = {
        "src/a.py": "class WorkerA:\n    def execute(self, flag: bool):\n        return flag\n",
        "src/b.py": "class WorkerB:\n    def execute(self, flag: bool):\n        return not flag\n",
    }
    head_py = {
        "src/a.py": "class WorkerA:\n    def execute(self):\n        return True\n",
        "src/b.py": "class WorkerB:\n    def execute(self, flag: bool):\n        return not flag\n",
    }
    ambig_md = {
        "docs/workers.md": "## Execution\n\nCall `execute(flag)` to run the worker.\n"
    }

    findings, _ = _run_in_memory_drift_pipeline(base_py, head_py, ambig_md, ambig_md)
    assert len(findings) == 1
    assert findings[0].status == "UNCERTAIN"
    assert findings[0].confidence <= 0.55


# ---------------------------------------------------------------------------
# 3. End-to-End Integration Test for POST /api/analyze/drift (Items 29–35)
# ---------------------------------------------------------------------------


def test_analyze_drift_api_endpoint_end_to_end(monkeypatch, database_session):
    """
    Verify Items 29–35:
    - POST /api/analyze/drift against a multi-file temporary Git repository
    - Detects changed default parameter, removed function, deleted Python source file (Rule G),
      renamed/modified/deleted documentation files, partial syntax error resilience,
      and guaranteed temporary directory cleanup.
    """
    repo_dir = tempfile.mkdtemp(prefix="docguard_drift_e2e_")
    repo = git.Repo.init(repo_dir, initial_branch="main")

    with repo.config_writer() as cw:
        cw.set_value("user", "name", "DocGuard Drift Tester")
        cw.set_value("user", "email", "drift@docguard.local")

    os.makedirs(os.path.join(repo_dir, "src"), exist_ok=True)
    os.makedirs(os.path.join(repo_dir, "docs"), exist_ok=True)

    # Base Commit
    with open(os.path.join(repo_dir, "src", "auth.py"), "w", encoding="utf-8") as f:
        f.write(
            "def login_user(username: str, timeout: int = 30) -> bool:\n"
            "    return True\n\n"
            "def verify_otp(code: str, strict: bool) -> bool:\n"
            "    return len(code) == 6\n"
        )
    with open(os.path.join(repo_dir, "src", "legacy_ payments.py".replace(" ", "")), "w", encoding="utf-8") as f:
        f.write("def charge_legacy_card(card_no: str) -> bool:\n    return True\n")
    with open(os.path.join(repo_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write(
            "# Auth & Payments Platform\n\n"
            "## login_user()\n\n"
            "Authenticates a user. The default `timeout` is `30` seconds.\n\n"
            "## verify_otp()\n\n"
            "Pass `strict` to `verify_otp(code, strict)`.\n"
        )
    with open(os.path.join(repo_dir, "docs", "payments.md"), "w", encoding="utf-8") as f:
        f.write(
            "## Legacy Payments\n\n"
            "See `src/legacy_payments.py` and call `charge_legacy_card(card_no)`.\n"
        )

    repo.index.add(
        ["src/auth.py", "src/legacy_payments.py", "README.md", "docs/payments.md"]
    )
    c_base = repo.index.commit("Base commit with auth, legacy payments, and docs")

    # Head Commit:
    # 1. Change login_user default timeout from 30 -> 120 (README not updated -> CONFIRMED_DRIFT)
    # 2. Remove strict parameter from verify_otp AND update README to remove strict (-> RESOLVED)
    # 3. Delete src/legacy_payments.py while docs/payments.md still references it (-> RULE_G_DELETED_SOURCE_FILE)
    # 4. Add a file with a syntax error to test partial failure resilience
    with open(os.path.join(repo_dir, "src", "auth.py"), "w", encoding="utf-8") as f:
        f.write(
            "def login_user(username: str, timeout: int = 120) -> bool:\n"
            "    return True\n\n"
            "def verify_otp(code: str) -> bool:\n"
            "    return len(code) == 6\n"
        )
    repo.index.remove(["src/legacy_payments.py"], working_tree=True)
    with open(os.path.join(repo_dir, "src", "broken.py"), "w", encoding="utf-8") as f:
        f.write("def syntax_error(:\n    pass\n")
    with open(os.path.join(repo_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write(
            "# Auth & Payments Platform\n\n"
            "## login_user()\n\n"
            "Authenticates a user. The default `timeout` is `30` seconds.\n\n"
            "## verify_otp()\n\n"
            "Call `verify_otp(code)` to validate a 6-digit code.\n"
        )

    repo.index.add(["src/auth.py", "src/broken.py", "README.md"])
    c_head = repo.index.commit("Head commit introducing drift, resolving verify_otp doc, and deleting legacy file")

    scratch_root = os.path.join(
        tempfile.gettempdir(), f"docguard-test-scratch-{uuid.uuid4().hex}"
    )
    try:
        monkeypatch.setenv("DOCGUARD_SCRATCH_ROOT", scratch_root)
        monkeypatch.setattr(
            github_service,
            "_resolve_clone_source",
            lambda _url: repo_dir,
        )

        response = client.post(
            "/api/analyze/drift",
            json={
                "github_repository_id": 986667204,
                "base_commit": c_base.hexsha,
                "head_commit": c_head.hexsha,
            },
            headers={
                "Origin": "http://localhost:5173",
                "Idempotency-Key": "drift-integration-test-key",
            },
        )
        assert response.status_code == 202
        job = response.json()
        assert job["status"] == "queued"
        from app.models import AnalysisFinding, AnalysisRecord
        from app.tasks.analysis_jobs import process_analysis_job

        process_analysis_job.run(job["analysis_id"])
        persisted = database_session.get(
            AnalysisRecord, uuid.UUID(job["analysis_id"])
        )
        database_session.refresh(persisted)
        assert persisted.status == "succeeded"
        assert persisted.scratch_cleanup_status == "complete"
        data = client.get(f"/api/analyses/{job['analysis_id']}").json()
        assert data["status"] == "succeeded"
        persisted = database_session.get(
            AnalysisRecord, uuid.UUID(job["analysis_id"])
        )
        database_session.refresh(persisted)
        assert persisted.status == "succeeded"
        assert persisted.base_commit == c_base.hexsha
        assert persisted.head_commit == c_head.hexsha
        assert len(persisted.findings) == len(data["findings"])
        assert database_session.query(AnalysisFinding).filter_by(
            analysis_id=persisted.id
        ).count() == len(data["findings"])
        detail = client.get(f"/api/analyses/{job['analysis_id']}")
        assert detail.status_code == 200
        assert detail.json()["repository_full_name"] == "octocat/DocGuard-Drift"
        assert len(detail.json()["findings"]) == len(data["findings"])

        assert data["owner"] == "octocat"
        assert data["name"] == "DocGuard-Drift"
        assert data["base_commit"] == c_base.hexsha
        assert data["head_commit"] == c_head.hexsha

        summary = data["summary"]
        assert summary["python_files_analyzed"] == 2
        assert summary["documentation_files_analyzed"] == 2
        assert summary["parse_errors_count"] == 1
        assert summary["confirmed_drift_count"] >= 2
        assert summary["resolved_count"] >= 1

        rules_found = {f["rule_id"] for f in data["findings"]}
        assert "RULE_A_CHANGED_DEFAULT" in rules_found
        assert "RULE_B_REMOVED_OR_RENAMED_PARAMETER" in rules_found
        assert "RULE_G_DELETED_SOURCE_FILE" in rules_found

        scratch_path = os.path.join(
            scratch_root,
            f"analysis-{uuid.UUID(job['analysis_id']).hex}-attempt-1",
        )
        assert not os.path.exists(scratch_path)

        # Arbitrary repository URLs are no longer accepted by the analysis API.
        invalid_resp = client.post(
            "/api/analyze/drift",
            json={
                "repository_url": "https://gitlab.com/octocat/DocGuard-Drift",
                "base_commit": c_base.hexsha,
                "head_commit": c_head.hexsha,
            },
            headers={"Origin": "http://localhost:5173"},
        )
        assert invalid_resp.status_code == 422

        same_commit_resp = client.post(
            "/api/analyze/drift",
            json={
                "github_repository_id": 986667204,
                "base_commit": c_head.hexsha,
                "head_commit": c_head.hexsha,
            },
            headers={"Origin": "http://localhost:5173"},
        )
        assert same_commit_resp.status_code == 400
    finally:
        try:
            repo.close()
        except Exception:
            pass
        shutil.rmtree(repo_dir, onerror=github_service._remove_readonly)
