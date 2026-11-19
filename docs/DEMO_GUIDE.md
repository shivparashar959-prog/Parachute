# DocGuard Demonstration Guide

This guide explains how to run the deterministic controlled demonstration repository (`https://github.com/docguard-demo/billing-api`) as well as real public GitHub repositories (`https://github.com/pallets/flask`).

---

## 1. Starting the Application (Windows PowerShell)

### Terminal 1 — Start the FastAPI Backend
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
*(If PowerShell script execution is restricted, run `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`.)*

### Terminal 2 — Start the React + Vite Frontend
```powershell
cd frontend
npm run dev
```
Open **http://localhost:5173** in your browser. Confirm the header badge shows **Backend connected**.

---

## 2. Walkthrough A — Controlled Hackathon Demo (`docguard-demo/billing-api`)

DocGuard includes a deterministic 2-commit Git repository builder (`backend/app/services/demo_fixture.py`) mapped to `https://github.com/docguard-demo/billing-api`. When connected, DocGuard creates and clones a real local Git repository on disk and executes the full GitPython + AST + Markdown + Drift + AI pipeline.

### Step-by-Step Demo Flow

1. **Select the Controlled Demo Preset**:
   - Under **Public GitHub Repository URL**, click the quick preset pill **Controlled Demo (`docguard-demo/billing-api`)** (or enter `https://github.com/docguard-demo/billing-api`), then click **Connect Repository**.
2. **Verify Repository & Commits**:
   - Owner/Repository: `docguard-demo/billing-api`, Default Branch: `main`, `2 commits` loaded.
   - **Base Commit** is automatically set to the initial synchronized release (`Initial release: synchronized billing API and documentation`).
   - **Head Commit** is automatically set to the updated commit (`Update role default to admin, remove gateway port arg, require recipient_email`).
3. **Compare Commits**:
   - Click **Compare Commits** to inspect the raw unified Git diff in `src/billing.py` (added lines in green, removed lines in red).
4. **Analyze Python AST Changes**:
   - Click **Analyze Python Changes**.
   - Observe the AST changes detected in `src/billing.py`:
     - `create_user`: `DEFAULT_VALUE_CHANGED` (`role='user'` → `role='admin'`)
     - `connect_gateway`: `PARAMETER_REMOVED` (`port` removed)
     - `send_receipt`: `PARAMETER_ADDED` (required parameter `recipient_email` added)
     - `calculate_platform_fee`: `FUNCTION_MODIFIED` (body-only implementation change)
     - `sync_ledger_entries`: `PARAMETER_ADDED` (optional parameter `timeout: int = 30`)
     - `_hash_audit_payload`: `PARAMETER_ADDED` + `FUNCTION_MODIFIED` (internal unreferenced helper)
5. **Analyze Documentation Mapping**:
   - Click **Analyze Documentation**.
   - Observe `2` discovered Markdown files (`README.md`, `docs/api.md`), `8` extracted documentation units, and `5` high-confidence symbol mappings linking Markdown sections to `src/billing.py` functions.
6. **Run Documentation Drift Detection**:
   - Click **ANALYZE DOCUMENTATION DRIFT**.
   - Observe that DocGuard reports **exactly 3 `CONFIRMED_DRIFT` findings**, `0` potential findings, and no findings for the unrelated code changes:
     1. **`create_user` (`RULE_A_CHANGED_DEFAULT`, `HIGH` severity, `96%` confidence)**: `docs/api.md` line 5 still claims the default `role` is `user` while code now defaults to `admin`.
     2. **`connect_gateway` (`RULE_B_REMOVED_OR_RENAMED_PARAMETER`, `HIGH` severity, `95%` confidence)**: `docs/api.md` line 9 still instructs passing `port` to `connect_gateway(host, port)`.
     3. **`send_receipt` (`RULE_C_ADDED_REQUIRED_PARAMETER`, `CRITICAL` severity, `94%` confidence)**: `README.md` line 11 still shows calling `send_receipt(order_id)` without required parameter `recipient_email`.
   - The UI reports 10 AST change records across 6 symbols. The body-only change in `calculate_platform_fee`, optional parameter `timeout=30` in `sync_ledger_entries`, and internal helper `_hash_audit_payload` do not produce drift findings.
7. **Explain with AI & Copy Documentation Fix**:
   - On the `create_user` finding, click **EXPLAIN WITH AI** or **SUGGEST DOCUMENTATION FIX** (works offline in **Mock** mode or with **Gemini** if `GEMINI_API_KEY` is configured).
   - Inspect the structured explanation and proposed Markdown fix:
     ```markdown
     The `create_user` function provisions an account in `src/billing.py`. The default `role` is `admin`.
     ```
   - Click **Copy Suggestion** to copy the replacement text to your clipboard.

---

## 3. Walkthrough B — Live Public GitHub Repository (`pallets/flask`)

1. Click the quick preset pill **Real GitHub (`pallets/flask`)** (`https://github.com/pallets/flask`) and click **Connect Repository**.
2. Select any two commits from the 20 recent commits on `main`.
3. Run **Compare Commits**, **Analyze Python Changes**, **Analyze Documentation**, and **ANALYZE DOCUMENTATION DRIFT**.
