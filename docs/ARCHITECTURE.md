# DocGuard Architecture Overview

## 1. System Architecture

**DocGuard** is a full-stack documentation drift detection platform built on a deterministic-first, AI-assisted architecture:

1. **Deterministic Verification Engine (Source of Truth)**:
   - Resolves a workspace-authorized GitHub numeric repository ID and retrieves public or private data through a linked GitHub App installation. Git uses ephemeral bare clones (`--bare`).
   - Performs static Python AST analysis (`ast.parse`, `ast.unparse`, `ast.dump`) to detect 17 categories of structural code changes between `base_commit` and `head_commit`.
   - Parses Markdown documentation files (`README.md`, `docs/**/*.md`, `CONTRIBUTING.md`, `CHANGELOG.md`) with exact 1-based line preservation.
   - Maps documentation statements to Python AST symbols using deterministic evidence (qualified names, API headings, inline code spans, call expressions, parameter references, and module paths).
   - Evaluates 9 deterministic drift detection rules (**Rules A–I**) and 12 false-positive prevention guards.
2. **Advisory AI Layer (`backend/app/ai/`)**:
   - Consumes verified `DriftFinding` records to produce human-readable explanations and surgical Markdown replacement proposals.
   - Supports offline **Mock AI Mode** (`MockAIProvider`) in development/tests and **Google Gemini API Mode** (`GeminiAIProvider` via `google-genai`) for production.
   - Never alters deterministic finding statuses (`CONFIRMED_DRIFT`, `POTENTIAL_DRIFT`, `UNCERTAIN`, `RESOLVED`, `UNCHANGED`) and never modifies repository files automatically.

---

## 2. Backend Module Layout (`backend/app/`)

```text
backend/app/
├── auth/
│   ├── github_app.py               # GitHub App JWT, API calls and short-lived tokens
│   ├── sessions.py                # Opaque hashed session issuance/revocation
│   ├── dependencies.py             # Authenticated-principal dependency
│   └── csrf.py                     # Trusted-origin validation
├── db/
│   ├── base.py                     # SQLAlchemy declarative base
│   └── session.py                  # Request-scoped SQLAlchemy sessions
├── models/                         # Accounts, repository catalog, analyses, findings and spend reservations
├── ai/
│   ├── base_provider.py           # Abstract BaseAIProvider interface & error hierarchy
│   ├── gemini_provider.py         # Google Gemini SDK provider (GEMINI_API_KEY, GEMINI_MODEL)
│   ├── mock_provider.py           # Offline deterministic Mock AI provider
│   ├── prompt_builder.py          # Minimal evidence prompt builder & injection guard
│   └── response_validator.py      # Strict JSON & Pydantic schema validator
├── analyzers/
│   ├── symbol_extractor.py        # Static Python AST symbol & parameter extractor
│   ├── change_detector.py         # 17-type AST symbol diff & conservative rename engine
│   ├── python_ast_analyzer.py     # File-level Python AST coordinator
│   ├── markdown_parser.py         # Line-accurate static Markdown parser
│   ├── documentation_extractor.py # Documentation unit classifier & token extractor
│   ├── documentation_mapper.py    # Evidence-based doc-to-code symbol mapper
│   ├── documentation_comparator.py# Base-vs-head Markdown file & unit comparator
│   ├── evidence_builder.py        # Code snippet slicer & confidence/severity calculator
│   ├── drift_rules.py             # Deterministic Rules A–I & false-positive guards
│   └── drift_detector.py          # Drift detection coordinator
├── api/
│   ├── auth.py                     # GitHub sign-in, current account and logout routes
│   ├── github_app.py               # Installations, authorized repositories, PR metadata and webhooks
│   ├── analyses.py                 # Workspace-authorized history, job lifecycle and details
│   ├── repositories.py            # POST /api/repositories/inspect & /compare
│   ├── code_analysis.py           # POST /api/analyze/code
│   ├── documentation.py           # POST /api/analyze/documentation
│   ├── drift.py                   # POST /api/analyze/drift
│   └── ai_explanations.py         # GET /providers & POST /api/analyze/explanations
├── evaluation/
│   └── evaluator.py               # 16-case reproducible benchmark (TP, FP, TN, FN, Precision, Recall, F1)
├── schemas/
│   ├── auth.py
│   ├── repository.py
│   ├── code_analysis.py
│   ├── documentation.py
│   ├── drift.py
│   ├── analysis.py
│   └── ai_explanation.py
├── services/
│   ├── github_app_service.py       # Workspace-scoped installation and repository authorization
│   ├── github_service.py          # Canonical URL/SHA validation, bare cloning & temp cleanup
│   ├── code_analysis_service.py   # Git blob reader & AST analysis orchestration
│   ├── documentation_service.py   # Markdown discovery & symbol mapping orchestration
│   ├── drift_analysis_service.py  # Single-clone base/head drift analysis service
│   ├── analysis_service.py        # Persistence, quotas, and Gemini spend reservations
│   ├── ai_explanation_service.py  # AI provider resolution & request bounding
│   └── demo_fixture.py            # Controlled 2-commit demonstration Git repository builder
├── tasks/
│   ├── celery_app.py               # Redis broker, JSON-only tasks and Beat schedule
│   └── analysis_jobs.py            # ID-only dispatch, workers, retries and recovery
└── main.py                        # FastAPI app, CORS middleware, health/root endpoints

backend/alembic/                    # Reversible PostgreSQL schema migrations
```

---

## 3. Data Flow Pipeline

1. **Repository Inspection (`POST /api/repositories/inspect`)**:
   - Accepts a GitHub numeric repository ID, resolves active workspace authorization, mints a short-lived installation token, rechecks the repository with GitHub, clones the server-derived canonical URL into a temporary bare repository, and cleans up.
2. **Commit Diff Comparison (`POST /api/repositories/compare`)**:
   - Uses `git diff-tree -r -M --raw -z` for file change classification (`added`, `modified`, `deleted`, `renamed`) and `git diff-tree -r -p -M` for unified diff patches.
3. **Python AST Analysis (`POST /api/analyze/code`)**:
   - Reads Python blobs directly from `base_commit.tree` and `head_commit.tree` in memory, parses AST trees with `ast.parse()`, and emits `SymbolChange` items.
4. **Documentation Parsing & Mapping (`POST /api/analyze/documentation`)**:
   - Discovers `.md` files at `head_commit`, extracts `DocumentationUnit` statements with exact 1-based line numbers, and maps them to extracted Python AST symbols with `HIGH`, `MEDIUM`, or `LOW` confidence.
5. **Durable Analysis Creation (`POST /api/analyses`)**:
   - Requires an authorized repository ID and full commit SHAs. Rechecks GitHub App access and inserts a workspace-scoped queued analysis with idempotency metadata into PostgreSQL. Returns `202 Accepted`; `/api/analyze/drift` is a compatibility alias with the same asynchronous contract.
   - The Celery broker message contains only the analysis UUID. PostgreSQL owns state, attempts, timestamps, progress, cancellation requests, safe errors and cleanup status; Celery result storage is disabled.
6. **Background Drift Worker (Celery + Redis)**:
   - Claims a queued row atomically, rechecks its stored workspace membership and live GitHub repository access, then runs the existing synchronous AST/Markdown/drift service. The short-lived installation token exists only in worker memory for the operation.
   - Celery Beat periodically redispatches queued database rows and recovers stale workers, covering the database-commit/broker-publish failure window. Workers use a per-analysis/per-attempt scratch directory; the scheduler retries cleanup of orphaned scratch directories.
   - Per-task time limits bound work but do not provide OS/container CPU, memory, filesystem or network-egress isolation. Production must deploy workers with runtime isolation before exposing them to arbitrary repository workloads.
7. **AI Explanations & Fix Suggestions (`POST /api/analyze/explanations`)**:
   - Accepts an authorized `analysis_id` plus up to 10 persisted finding IDs; client-supplied finding objects are rejected. Deterministic findings remain authoritative.
   - Sends only the selected evidence to a provider. Mock is development/test-only; production requires Gemini, configured spend limits, provider timeout/output-token limits, and a visible repository-text disclosure.
8. **Authenticated dashboard and history**:
   - React Router exposes a public sign-in/landing page and cookie-session-protected analysis, history, and detail routes.
   - The history API is paginated and workspace-scoped; each distinct repository is reauthorized before details are shown. Revoked access produces a redacted tombstone rather than exposing repository IDs, names, commits, or finding counts.
   - Users can retry eligible failed/cancelled jobs and delete terminal analyses. Deletion removes findings but retains unlinked Gemini spend reservations for quota accounting. The UI polls persisted job state and renders saved evidence after refresh.

---

## 4. Account Identity and Persistence (Milestone 2)

- Account identity uses GitHub OAuth through Authlib with the minimum `read:user`
  and `user:email` scopes. This OAuth login is not GitHub App repository
  authorization; it does not grant private-repository access.
- The authorization-code flow uses Authlib-managed state and PKCE. The database
  stores a hash of each one-time state value to prevent callback replay. GitHub
  OAuth is not OIDC and does not issue an OIDC ID-token nonce; no nonce validation
  is claimed for this provider.
- GitHub profile identity is keyed by the stable GitHub account ID, not email.
  Only a verified primary email returned by GitHub is persisted. The short-lived
  provider access token is used in memory during the callback and is neither
  stored nor returned.
- SQLAlchemy 2 models and Alembic migrations persist users, external identities,
  opaque browser sessions, personal workspaces, and workspace memberships.
  Membership roles are prepared for future teams; no team administration exists.
- Browser sessions use a random opaque value in an HttpOnly cookie. PostgreSQL
  stores only its SHA-256 hash. Sessions expire server-side, are rotated on a
  new successful sign-in, and are revoked on logout. The cookie is Secure in
  production and uses the configured SameSite policy.
- Cookie-authenticated logout requires an exact configured `Origin`; cross-site
  Fetch Metadata is rejected. Production CORS requires explicit HTTPS origins
  and allows only the API methods and headers needed by the app.
- `/` and `/api/health` remain public. Auth status and OAuth start/callback are
  public protocol endpoints. The current-user endpoint and all repository,
  analysis, and AI routes require an authenticated principal.

## 5. GitHub App and Authorized Repository Catalog (Milestone 3)

- Account identity remains separate from repository access. A user must link
  the GitHub App installation and authorize it with the same GitHub account used
  for DocGuard sign-in.
- Installation and repository records are workspace-scoped and use stable
  numeric GitHub IDs. The repository picker only lists active catalog entries.
- Installation tokens are short-lived and used server-side. Git receives an
  authorization extra header through environment configuration; credentials
  are not embedded in clone URLs or returned by API responses.
- Installation setup state is hashed, one-time, short-lived, and bound to the
  signed-in user and personal workspace. The callback also verifies the
  installation against the signed-in GitHub identity.
- Read-only PR metadata is available. Webhooks validate signatures, limit body
  size, deduplicate deliveries, and deactivate records when installations or
  repository grants are removed.

## 6. Persisted Analysis and AI Policy (Milestone 4)

- `analyses` and `analysis_findings` bind canonical base/head SHAs, summary, and
  bounded evidence to the current personal workspace and authorized repository.
  Findings retain deterministic status, severity, and confidence; source trees
  are not stored.
- `GET /api/analyses/{analysis_id}` and AI explanation requests are workspace
  scoped. Both recheck the linked repository with GitHub before returning
  private-derived evidence or invoking Gemini. Client-provided finding objects
  are rejected.
- Analysis quotas limit per-user rate, per-workspace daily volume and concurrent
  queued/running work. Repository processing is bounded by an analysis deadline,
  Git-operation timeouts, clone-size, tree-entry, file-count, source-byte, and
  persisted-evidence limits. Milestone 5's scheduler recovers stale running
  jobs. These application-level bounds do not provide OS/container resource
  isolation.
- Gemini calls have a configured timeout, output-token cap, prompt-byte cap,
  and conservative per-user/workspace spend reservations based on operator-set
  model token rates. Reservations are not an exact provider invoice.
- The controlled demo URL maps to a local fixture only in development/test;
  production resolves it as a normal GitHub URL.
- Durable job orchestration is implemented in Milestone 5; persistent history
  listing and dashboard navigation are implemented in Milestone 6.

## 7. Background Job Runtime (Milestone 5)

- Celery with Redis fits the existing synchronous GitPython pipeline and avoids
  rewriting the analyzer. PostgreSQL remains the source of truth; task payloads
  carry analysis IDs only. Configure the managed broker as private, authenticated,
  TLS-enabled, persistent, and no-eviction.
- `ANALYSIS_RETRY_MAX_ATTEMPTS` bounds retryable GitHub/network failures.
  Validation, authorization and resource-limit errors are not retried. Retry
  delay is exponential and capped.
- `GET /api/analyses/{analysis_id}/status` and
  `POST /api/analyses/{analysis_id}/cancel` are workspace scoped. Cookie-authenticated
  creation and cancellation require a trusted Origin.
- Run one Celery worker pool and one Celery Beat scheduler. Beat is required for
  dispatch recovery after broker outages and stale worker recovery. An API with
  no worker leaves accepted jobs in the durable queued state.
- Cancellation is cooperative at analysis checkpoints and may wait for a bounded
  Git operation to complete. Worker limits and stale-job recovery are not a
  substitute for process/container resource or network isolation.

## 8. Authenticated dashboard and history (Milestone 6)

- `/` and `/signin` are public; `/dashboard/analyze`,
  `/dashboard/history`, and `/dashboard/history/:analysisId` require a
  server-validated cookie session. Session tokens are never put in browser
  storage. Protected API 401 responses clear the frontend session and return
  the user to sign-in.
- The analysis page uses the existing authorized repository catalog and
  server-returned PR SHAs. The history list uses bounded pagination, and detail
  reloads persisted findings and polls the job status endpoint while active.
- Retry creates a new analysis only for cancelled jobs or classified retryable
  failures; the backend enforces this policy and normal quotas. Deletion is
  limited to terminal analyses and rechecks both workspace and live repository
  authorization. Spend reservations are retained without their analysis link.
- `App.jsx` contains route/session composition. Analysis flow, history, detail,
  account, navigation, repository selection, and findings presentation live in
  separate modules under `frontend/src/`.
- Automated tests cover history pagination/workspace isolation, revoked-access
  redaction, retry/delete rules, unauthenticated route denial, API request
  contracts, session expiry, and request cancellation. A real browser login,
  private-repository journey, and deployed worker flow still require configured
  external services and credentials.
