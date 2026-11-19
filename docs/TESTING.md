# DocGuard Testing & Evaluation Guide

## 1. Running the Automated Backend Test Suite

From the root `DocGuard` directory in Windows PowerShell:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests -v
```

Or after activating the virtual environment inside `backend/`:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest -v
```

### Test Suite Organization

| Test File | Milestone Scope | Key Coverage |
| :--- | :--- | :--- |
| `backend/tests/test_main.py` | Foundation/Auth | Root endpoint (`GET /`), public health check, environment-driven CORS allowlist, production fail-closed defaults, and restricted CORS methods/headers |
| `backend/tests/test_repositories.py` | Milestone 2 | GitHub HTTPS URL validation, 19 unsafe/non-GitHub URL rejections, commit retrieval, added/modified/deleted/renamed file diffs, `--no-ff` merge commit handling, oversized/binary diffs, temp directory cleanup, and Git timeouts with child-process termination across clone/history/fetch/diff |
| `backend/tests/test_code_analysis.py` | Milestone 3 | All 17 Python AST symbol change types, all 5 parameter kinds (`/`, `*`, `*args`, `**kwargs`), nested functions, `@classmethod`/`@staticmethod`, syntax error resilience, non-execution security guarantee |
| `backend/tests/test_documentation.py` | Milestone 4 | Line-accurate Markdown parser (headings, hierarchies, lists, tables, links, code blocks), statement extraction, evidence-based symbol mapping, ambiguity detection, and similar-name non-matching |
| `backend/tests/test_drift.py` | Milestone 5 | Deterministic drift rules A–I, historical base-vs-head documentation comparison, `CONFIRMED_DRIFT` / `POTENTIAL_DRIFT` / `UNCERTAIN` / `RESOLVED` classification, and all 12 false-positive guards |
| `backend/tests/test_ai_explanations.py` | AI policy | Mock development/test mode, production Mock rejection, stored finding selection, Gemini timeout/output caps, spend reservation, prompt injection defense, secret scrubbing, and strict JSON validation |
| `backend/tests/test_analysis_persistence.py` | Persisted analysis | Cross-user detail/AI IDOR denial, per-user analysis quota, Gemini spend-budget failure, and production demo-interception guard |
| `backend/tests/test_evaluation.py` | Milestone 7 | End-to-end 16-step controlled demo workflow (`docguard-demo/billing-api`) and 16-case reproducible evaluation benchmark (`TP`, `FP`, `TN`, `FN`, `Precision`, `Recall`, `F1`) |
| `backend/tests/test_auth.py` | Milestone 2 | GitHub OAuth state/PKCE, callback replay and transaction-cookie rejection, hashed sessions, personal workspaces, expiry/rotation/logout, origin protection, rate limiting, secret redaction, and unauthenticated route denial |
| `backend/tests/test_db_migrations.py` | Persistence | Fresh schema upgrade, downgrade, re-upgrade, and model/migration parity; uses `TEST_POSTGRES_URL` when supplied and SQLite for local fallback |
| `backend/tests/test_github_app.py` | Milestone 3 | User-bound one-time installation state, GitHub identity match, public/private catalog sync, workspace IDOR denial, token redaction/expiry, signed webhook verification/replay, uninstall revocation, and rate-limit errors |
| `backend/tests/test_analysis_jobs.py` | Milestones 5–6 | 202 enqueue, idempotency, ID-only Celery dispatch, duplicate claims, bounded retry/backoff, stale-worker recovery, cancellation, authorization recheck, scratch cleanup, broker outage handling, production Redis configuration, workspace-scoped history, revoked-access redaction, safe retry, and deletion |

---

## 2. Running the Frontend Production Build

From the root `DocGuard` directory:

```powershell
cd frontend
npm run build
```

---

## 3. Running Frontend API Tests

From the `frontend` directory:

```powershell
npm test
```

These focused Node.js tests cover API timeouts and caller cancellation while response bodies are being parsed.

The current frontend suite also tests credentialed current-session requests,
logout requests, GitHub sign-in navigation, authorized GitHub App API requests,
stale-response protection, persisted analysis/history API contracts, and
session-expiry notification. The production session token is kept in an
HttpOnly cookie and is not placed in localStorage.

### Latest local verification

| Command | Result |
|---|---|
| `backend\.venv\Scripts\python.exe -m pytest tests -v` from `backend\` | **PASS** — 134 passed, 0 failed, 0 skipped, 0 errors |
| `npm test` from `frontend\` | **PASS** — 12 passed, 0 failed, 0 skipped |
| `npm run build` from `frontend\` | **PASS** — Vite production build completed |
| `git diff --check` | **PASS** — no whitespace errors |
| Browser smoke test | **PASS** — public landing rendered and anonymous navigation to `/dashboard/history` redirected to `/signin`; API reported that database/sign-in configuration is unavailable |
| Browser E2E across live login, GitHub installation, private repository, and worker | **NOT TESTED** — requires configured external credentials/services; mocked API tests are not a live browser journey |

The backend tests use SQLite unless `TEST_POSTGRES_URL` is supplied. This run
did not exercise PostgreSQL locking behavior, a live Redis broker, or a
separately running Celery worker/Beat deployment. The 16-case deterministic
evaluation test passed within the backend suite; its perfect metrics describe
that controlled corpus only.

## 4. Authentication and Migration Checks

From `backend\`, after configuring PostgreSQL and the GitHub OAuth App in
`backend\.env`:

```powershell
.\.venv\Scripts\alembic.exe upgrade head
python -m pytest tests -v
```

`test_auth.py` and `test_github_app.py` use mocked provider boundaries; they do
not call GitHub or require real credentials. GitHub OAuth uses state and PKCE.
OIDC nonce validation is not applicable because this implementation uses GitHub
OAuth, not OIDC. GitHub App callbacks, private repository cloning, and webhook
delivery have not been tested against a real GitHub App.

The CI workflow provisions a temporary PostgreSQL 16 service and points
`TEST_POSTGRES_URL` at it for real PostgreSQL migration testing. A local
verification that only exercises the SQLite fallback does not prove that hosted
CI or the PostgreSQL service passed; check the Actions run before claiming that.

## 5. Reproducible Evaluation Dataset & Measured Quality Metrics

DocGuard includes a deterministic 16-case evaluation benchmark in `backend/app/evaluation/evaluator.py` (`build_labeled_evaluation_dataset()` and `run_drift_evaluation_benchmark()`).

### How the Dataset & Ground-Truth Labels Were Created
- **8 Positive Cases (`expected_unresolved_drift = True`)**: Each case pairs a specific Python AST breaking change (changed default value, removed parameter, renamed parameter, added required parameter, changed return annotation, removed function, renamed function, deleted Python file) with a Markdown documentation statement that explicitly states the old signature, parameter, default, return type, or file path.
- **8 Negative Cases (`expected_unresolved_drift = False`)**: Each case represents a common false-positive trap (added optional parameter with default, function body-only modification, parameter removed from an unrelated function in the same file, function with a similar name, historical `CHANGELOG.md` entry, documentation already updated in the head commit, general project overview prose, and comment/whitespace-only code edit).

### Measured Benchmark Results

You can execute the benchmark directly via PowerShell:

```powershell
.\backend\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'backend'); from app.evaluation.evaluator import run_drift_evaluation_benchmark; r = run_drift_evaluation_benchmark(); print(f'Cases: {r.total_cases} | TP={r.true_positives} FP={r.false_positives} TN={r.true_negatives} FN={r.false_negatives} | Precision={r.precision:.2f} Recall={r.recall:.2f} F1={r.f1_score:.2f}')"
```

- **Total Benchmark Cases**: `16` (`8` positive, `8` negative)
- **True Positives (TP)**: `8`
- **False Positives (FP)**: `0`
- **True Negatives (TN)**: `8`
- **False Negatives (FN)**: `0`
- **Precision (`TP / (TP + FP)`)**: `1.00` (`100.0%`)
- **Recall (`TP / (TP + FN)`)**: `1.00` (`100.0%`)
- **F1 Score (`2 * P * R / (P + R)`)**: `1.00` (`100.0%`)

> **Dataset Limitation Note**: These metrics are measured on a controlled 16-case benchmark dataset designed to verify deterministic rule accuracy across supported AST and Markdown patterns. On large, unstructured real-world repositories where documentation makes implicit behavioral claims without naming symbols or parameters, recall will naturally be lower because DocGuard prioritizes high precision and zero false positives over speculative guessing.
