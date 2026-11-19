"""
Automated tests for Milestone 7:
1. Controlled Demonstration Repository End-to-End 16-Step Workflow
   (`https://github.com/docguard-demo/billing-api`).
2. Reproducible 16-Case Evaluation Benchmark (TP, FP, TN, FN, Precision, Recall, F1).
"""

from fastapi.testclient import TestClient

from app.evaluation.evaluator import run_drift_evaluation_benchmark
from app.main import app
from app.services.demo_fixture import DEMO_REPO_CANONICAL_URL

client = TestClient(app)


def test_controlled_demo_repository_complete_16_step_workflow():
    """
    Execute the complete end-to-end DocGuard workflow on the controlled
    demonstration repository (`https://github.com/docguard-demo/billing-api`):
    1. Check backend health (`GET /api/health`)
    2. Inspect demo repository (`POST /api/repositories/inspect`)
    3. Compare base and head commits (`POST /api/repositories/compare`)
    4. Run Python AST code analysis (`POST /api/analyze/code`)
    5. Run Markdown documentation parsing & code mapping (`POST /api/analyze/documentation`)
    6. Run deterministic documentation drift detection (`POST /api/analyze/drift`)
    7. Verify genuine drift findings (create_user, connect_gateway, send_receipt)
       and confirm benign/unrelated changes (calculate_platform_fee, sync_ledger_entries,
       _hash_audit_payload) produce 0 false positives
    8. Request AI explanations and correction suggestions (`POST /api/analyze/explanations`)
    """
    # 1. Health Check
    health_resp = client.get("/api/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "ok"

    # 2. Inspect Controlled Demo Repository
    inspect_resp = client.post(
        "/api/repositories/inspect",
        json={"github_repository_id": 1},
    )
    assert inspect_resp.status_code == 200
    inspect_data = inspect_resp.json()
    assert inspect_data["owner"] == "docguard-demo"
    assert inspect_data["name"] == "billing-api"
    assert len(inspect_data["commits"]) == 2
    head_sha = inspect_data["commits"][0]["sha"]
    base_sha = inspect_data["commits"][1]["sha"]

    # 3. Compare Commits
    compare_resp = client.post(
        "/api/repositories/compare",
        json={
            "github_repository_id": 1,
            "base_commit": base_sha,
            "head_commit": head_sha,
        },
    )
    assert compare_resp.status_code == 200
    compare_data = compare_resp.json()
    assert compare_data["total_changed_files"] == 1
    assert compare_data["modified_files"] == ["src/billing.py"]

    # 4. Python AST Analysis
    ast_resp = client.post(
        "/api/analyze/code",
        json={
            "github_repository_id": 1,
            "base_commit": base_sha,
            "head_commit": head_sha,
        },
    )
    assert ast_resp.status_code == 200
    ast_data = ast_resp.json()
    assert ast_data["summary"]["analyzed_python_files_count"] == 1
    assert ast_data["summary"]["total_symbol_changes"] >= 5

    # 5. Documentation Parsing & Mapping
    doc_resp = client.post(
        "/api/analyze/documentation",
        json={
            "github_repository_id": 1,
            "base_commit": base_sha,
            "head_commit": head_sha,
        },
    )
    assert doc_resp.status_code == 200
    doc_data = doc_resp.json()
    assert doc_data["summary"]["discovered_doc_files_count"] == 2
    assert doc_data["summary"]["mapped_units_count"] >= 5

    # 6. Deterministic Drift Detection
    drift_resp = client.post(
        "/api/analyze/drift",
        json={
            "github_repository_id": 1,
            "base_commit": base_sha,
            "head_commit": head_sha,
        },
        headers={
            "Origin": "http://localhost:5173",
            "Idempotency-Key": "controlled-demo-analysis-key",
        },
    )
    assert drift_resp.status_code == 202
    job = drift_resp.json()
    assert job["status"] == "queued"
    from app.tasks.analysis_jobs import process_analysis_job

    process_analysis_job.run(job["analysis_id"])
    status_resp = client.get(f"/api/analyses/{job['analysis_id']}/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "succeeded"
    detail_resp = client.get(f"/api/analyses/{job['analysis_id']}")
    assert detail_resp.status_code == 200
    drift_data = detail_resp.json()
    assert drift_data["analysis_id"]
    findings = drift_data["findings"]

    # Exactly 3 genuine drift findings: create_user, connect_gateway, send_receipt
    flagged_symbols = {f["related_symbol"] for f in findings}
    assert flagged_symbols == {"create_user", "connect_gateway", "send_receipt"}

    # Unrelated / benign changes must NOT be flagged
    assert "calculate_platform_fee" not in flagged_symbols
    assert "sync_ledger_entries" not in flagged_symbols
    assert "_hash_audit_payload" not in flagged_symbols

    # 7. AI Explanations & Correction Suggestions in Mock Mode
    ai_resp = client.post(
        "/api/analyze/explanations",
        json={
            "analysis_id": drift_data["analysis_id"],
            "provider": "mock",
            "finding_ids": [finding["finding_id"] for finding in findings],
        },
    )
    assert ai_resp.status_code == 200
    ai_data = ai_resp.json()
    assert ai_data["explanations_generated"] == 3
    by_sym = {e["related_symbol"]: e for e in ai_data["explanations"]}

    assert by_sym["create_user"]["correction_available"] is True
    assert "admin" in (by_sym["create_user"]["suggested_correction"] or "")


def test_reproducible_evaluation_benchmark_metrics():
    """
    Execute the 16-case labeled evaluation benchmark and verify measured
    TP, FP, TN, FN, Precision, Recall, and F1 score.
    """
    report = run_drift_evaluation_benchmark()
    assert report.total_cases == 16
    assert report.positive_cases == 8
    assert report.negative_cases == 8
    assert report.true_positives == 8
    assert report.false_positives == 0
    assert report.true_negatives == 8
    assert report.false_negatives == 0
    assert report.precision == 1.0
    assert report.recall == 1.0
    assert report.f1_score == 1.0
