# DocGuard Hackathon Presentation Script (5–7 Minutes)

---

## Slide / Stage 1 — The Problem: Documentation Drift (0:00 – 0:45)

- **Talking Points**:
  - "Every engineering team has experienced documentation drift: a developer updates a default parameter from `'user'` to `'admin'`, removes an obsolete `port` parameter, or adds a required `recipient_email` argument—all unit tests pass, the PR merges, and the Markdown documentation silently becomes wrong."
  - "Standard linters and CI pipelines check code syntax, and generic LLM wrappers hallucinate or flag every single changed line as drift."
  - "We built **DocGuard**: a deterministic-first, AI-assisted documentation drift detection platform."

---

## Stage 2 — Architecture & Live Connection (0:45 – 1:45)

- **Action in Browser (`http://localhost:5173`)**:
  - Point out the **Backend connected** live health indicator (`GET /api/health`).
  - Click the quick preset **Controlled Demo (`docguard-demo/billing-api`)** and click **Connect Repository**.
- **Talking Points**:
  - "DocGuard validates the HTTPS GitHub URL, performs an isolated bare clone (`--bare`) without checking out or executing any untrusted code, and loads the commit history."
  - "Here we have two commits on `main`: our initial synchronized release (`Base Commit`) and a feature update (`Head Commit`)."

---

## Stage 3 — Git Commit Comparison & Static Python AST Analysis (1:45 – 3:00)

- **Action in Browser**:
  - Click **Compare Commits** to show the unified Git diff in `src/billing.py` (green additions and red deletions).
  - Click **Analyze Python Changes** to run Milestone 3's static Python AST analyzer (`POST /api/analyze/code`).
- **Talking Points**:
  - "Raw line diffs aren't enough to understand semantic API changes. DocGuard parses both commit versions with Python's `ast` module without ever importing or executing repository code."
  - "Notice that our AST engine detected 10 change records across 6 symbols in `src/billing.py`: a `DEFAULT_VALUE_CHANGED` on `create_user`, a `PARAMETER_REMOVED` on `connect_gateway`, a required `PARAMETER_ADDED` on `send_receipt`, a body-only `FUNCTION_MODIFIED` on `calculate_platform_fee`, an optional parameter `timeout=30` on `sync_ledger_entries`, and changes to the internal helper `_hash_audit_payload`."

---

## Stage 4 — Documentation Parsing & Evidence-Based Code Mapping (3:00 – 4:00)

- **Action in Browser**:
  - Click **Analyze Documentation** to run Milestone 4's Markdown parser and mapper (`POST /api/analyze/documentation`).
  - Filter by **High Confidence** and expand a mapping card (e.g., `create_user()` in `docs/api.md`).
- **Talking Points**:
  - "Next, DocGuard discovers `README.md` and `docs/api.md`, extracts 8 structured documentation units with exact 1-based line numbers, maps 5 to Python AST symbols, and leaves 3 unmapped using deterministic evidence such as API headings, inline code spans, parameter names, and source file references."

---

## Stage 5 — Deterministic Drift Detection & False-Positive Prevention (4:00 – 5:15)

- **Action in Browser**:
  - Click **ANALYZE DOCUMENTATION DRIFT** (`POST /api/analyze/drift`).
  - Expand the evidence view on the 3 `CONFIRMED_DRIFT` findings (`create_user`, `connect_gateway`, `send_receipt`).
- **Talking Points**:
  - "This is DocGuard's core intelligence. Even though the AST reports 10 change records across 6 symbols in `src/billing.py`, DocGuard produces only the 3 evidence-backed drift findings and no potential findings:"
    1. `create_user` (`RULE_A_CHANGED_DEFAULT`): `docs/api.md:L5` claims the default `role` is `user`, contradicting the new code default `'admin'`.
    2. `connect_gateway` (`RULE_B_REMOVED_OR_RENAMED_PARAMETER`): `docs/api.md:L9` tells callers to pass `port`, which was removed.
    3. `send_receipt` (`RULE_C_ADDED_REQUIRED_PARAMETER`): `README.md:L11` shows calling `send_receipt(order_id)` without the new required `recipient_email` argument.
  - "Crucially, DocGuard did **not** flag `calculate_platform_fee` (because a body implementation change doesn't invalidate its signature documentation) and did **not** flag `sync_ledger_entries` (because adding an optional parameter `timeout=30` doesn't break existing calls). The internal helper change also produced no finding."

---

## Stage 6 — AI Explanations & Copyable Documentation Fix Suggestions (5:15 – 6:30)

- **Action in Browser**:
  - On the `create_user` finding, click **EXPLAIN WITH AI** / **SUGGEST DOCUMENTATION FIX**.
  - Show the explanation, code change summary, and the proposed Markdown fix (`"The default role is admin."`), then click **Copy Suggestion**.
- **Talking Points**:
  - "Finally, our modular AI layer—supporting both offline deterministic **Mock AI Mode** and **Google Gemini (`gemini-2.5-flash`)**—explains the finding using strictly isolated repository evidence inside `<UNTRUSTED_REPOSITORY_DATA>` tags to prevent prompt injection."
  - "Deterministic detection remains the source of truth: AI cannot alter the finding status or automatically overwrite files, and developers can copy the verified Markdown fix with one click."
