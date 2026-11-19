# DocGuard — AI-Assisted Documentation Drift Detection Platform

**DocGuard** is a deterministic-first, AI-assisted documentation drift detection platform that connects public and private GitHub repositories through user-authorized GitHub App installations, analyzes Python code changes using static Abstract Syntax Tree (`ast`) analysis, maps Markdown documentation statements to code symbols, detects evidence-backed documentation drift across commits, and generates AI explanations and copyable Markdown correction proposals.

---

## 1. Project Overview

When source code evolves between commits, project documentation frequently falls out of sync. **DocGuard** bridges the gap between source code and documentation by combining static Python AST analysis, line-accurate Markdown parsing, deterministic drift rules (**Rules A–I**), and an isolated AI explanation layer (supporting offline **Mock AI Mode** and **Google Gemini API**).

## 2. Problem Statement

Normal code reviews and CI test suites verify that code compiles and tests pass, but rarely catch when a changed default parameter (`role='user'` → `role='admin'`), a removed parameter (`port`), an added required argument (`recipient_email`), or a renamed/deleted function invalidates statements in `README.md` or `docs/**/*.md`. Conversely, naive LLM wrappers hallucinate or flag every changed code line as documentation drift. DocGuard solves this by making **deterministic AST + Markdown evidence the source of truth** and using AI strictly to explain verified findings and propose minimal fixes.

## 3. Key Features

- **Authorized GitHub Repository Integration**: Lists repositories from the signed-in user's linked GitHub App installations. Supports public and private repositories with short-lived server-side installation tokens and read-only repository access.
- **Live Repository Inspection (`POST /api/repositories/inspect` & `/compare`)**: Resolves an authorized numeric GitHub repository ID server-side, uses isolated bare clones (`--bare`), retrieves first-parent commit history, and computes unified file diffs (`added`, `modified`, `deleted`, `renamed`).
- **Static Python AST Code Change Analyzer (`POST /api/analyze/code`)**: Uses Python's built-in `ast` module without executing code to extract classes, functions, async functions, methods (`instance`, `@classmethod`, `@staticmethod`), nested functions, and all 5 parameter kinds (`/`, `*`, `*args`, `**kwargs`), detecting 17 symbol change types.
- **Line-Accurate Markdown Parser & Code Mapper (`POST /api/analyze/documentation`)**: Discovers repository Markdown files, extracts verbatim documentation units with exact 1-based line numbers, and maps them to Python symbols with `HIGH`, `MEDIUM`, or `LOW` confidence (`MAPPED`, `AMBIGUOUS`, `UNMAPPED`).
- **Deterministic Drift Detection Engine (`POST /api/analyze/drift`)**: Evaluates 9 deterministic rules (**Rules A–I**) and 12 false-positive guards across base and head commits, classifying findings as `CONFIRMED_DRIFT`, `POTENTIAL_DRIFT`, `UNCERTAIN`, `RESOLVED`, or `UNCHANGED` with numerical confidence (`0.0–1.0`) and severity (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
- **Persisted, workspace-scoped drift analyses (`POST /api/analyses`, legacy alias `POST /api/analyze/drift`)**: Stores server-derived summaries and bounded deterministic finding evidence, with user/workspace quotas and current repository authorization checks.
- **Durable background analysis jobs (`POST /api/analyses`)**: Returns `202 Accepted`, stores queued/running/terminal job state in PostgreSQL, and runs analysis through Celery with Redis. Status, cancellation, progress, bounded retries, idempotency, stale-worker recovery, and scratch cleanup are exposed through authorized analysis APIs.
- **Authenticated dashboard and persistent history**: Public sign-in and protected analysis/history/detail routes use server-side HttpOnly sessions. Users can review paginated saved analyses, follow progress after reload, retry eligible failures, and delete terminal analyses; repository authorization is rechecked by the backend.
- **AI Explanations & Fix Suggestions (`POST /api/analyze/explanations`)**: Accepts an authorized analysis ID and stored finding IDs only. Mock AI works without credentials in development/tests; production requires configured Gemini, token/spend limits, and explicit repository-evidence disclosure.
- **Built-in Controlled Demo & 16-Case Evaluation Benchmark**: Includes a deterministic 2-commit demo repository (`https://github.com/docguard-demo/billing-api`) and a reproducible 16-case evaluation dataset measuring `TP`, `FP`, `TN`, `FN`, `Precision`, `Recall`, and `F1`.

## 4. Architecture Overview

```text
[React + Vite + Tailwind Dashboard]
               │  (Vite /api proxy -> http://127.0.0.1:8000)
               ▼
[FastAPI Backend (app/main.py)]
  ├── 1. GitHub Service (GitPython bare clone, URL/SHA validation, temp cleanup)
  ├── 2. Python AST Analyzer (symbol_extractor.py + change_detector.py — 17 change types)
  ├── 3. Markdown Parser & Mapper (markdown_parser.py + documentation_extractor.py + documentation_mapper.py)
  ├── 4. Deterministic Drift Engine (documentation_comparator.py + drift_rules.py + drift_detector.py — Rules A–I)
  └── 5. Advisory AI Layer (prompt_builder.py + mock_provider.py / gemini_provider.py + response_validator.py)
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed module responsibilities.
The local-only Docker Compose workflow is documented in [docs/LOCAL_DOCKER.md](docs/LOCAL_DOCKER.md).
Opt-in GitHub pull request automation and its required App permissions are documented in [docs/PULL_REQUEST_AUTOMATION.md](docs/PULL_REQUEST_AUTOMATION.md).

## 5. Technology Stack

- **Backend**: Python 3.10+, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, Celery + Redis, Authlib, Uvicorn, Pydantic v2, GitPython, Python `ast`, `google-genai`
- **Frontend**: React 19 (JavaScript), Vite 6, Tailwind CSS 4 (`@tailwindcss/vite`)
- **Testing**: Pytest, FastAPI `TestClient` (`httpx`)

## 6. Project Structure

```text
DocGuard/
├── backend/
│   ├── .venv/                             # Local Python virtual environment (git-ignored)
│   ├── app/
│   │   ├── auth/                          # GitHub OAuth identity, hashed sessions, principal and origin checks
│   │   ├── db/                            # SQLAlchemy base and request-scoped database sessions
│   │   ├── models/                        # Accounts, workspaces, repositories, analyses and findings
│   │   ├── ai/                            # BaseAIProvider, MockAIProvider, GeminiAIProvider, prompt & response validators
│   │   ├── analyzers/                     # Python AST, Markdown parser/extractor/mapper, and Drift Rules A–I
│   │   ├── api/                           # FastAPI routers, including workspace-scoped persisted analyses
│   │   ├── evaluation/                    # 16-case reproducible benchmark dataset & TP/FP/TN/FN/Precision/Recall/F1 evaluator
│   │   ├── schemas/                       # Pydantic request/response schemas
│   │   ├── services/                      # Business services & controlled demo repository fixture
│   │   ├── tasks/                          # Celery worker, queue dispatch and stale-job recovery
│   │   └── main.py                        # FastAPI application entrypoint
│   ├── tests/                             # Automated pytest unit & integration tests
│   ├── .env.example                       # Safe placeholder environment variables
│   ├── requirements.txt                   # Backend Python dependencies
│   ├── alembic.ini                        # Database migration configuration
│   └── alembic/                           # Reversible database migrations
├── frontend/
│   ├── src/
│   │   ├── api/health.js                  # Frontend API client with AbortController timeouts & cancellation
│   │   ├── api/auth.js                    # Credentialed current-session and sign-out calls
│   │   ├── components/                    # Modular UI components (Connection, Diff, AST, Docs, Drift & AI)
│   │   ├── hooks/useRequestGuard.js       # Reusable AbortController & stale-response prevention hook
│   │   ├── App.jsx                        # Public/protected route and dashboard shell
│   │   ├── AnalysisPage.jsx               # Existing repository analysis workflow
│   │   ├── auth/                          # Current server-side session context
│   │   └── pages/                         # Paginated history and persisted analysis detail
│   │   ├── index.css                      # Tailwind CSS entry
│   │   └── main.jsx                       # React root
│   ├── index.html
│   ├── package.json
│   └── vite.config.js                     # Vite config with /api proxy to FastAPI
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DEMO_GUIDE.md
│   ├── PRESENTATION_SCRIPT.md
│   ├── README.md
│   ├── SECURITY.md
│   └── TESTING.md
├── .gitignore
└── README.md
```

## 7. Prerequisites

- **Operating System**: Windows 10 / 11 (or macOS / Linux)
- **Python**: 3.10+ (`python --version`)
- **pip**: (`pip --version`)
- **Node.js & npm**: Node 18+ (`node --version`, `npm --version`)
- **Git**: 2.30+ (`git --version`)
- **Redis**: A local Redis service for development; production must use a private, authenticated TLS endpoint.

## 8. Windows Installation Instructions

Open **Windows PowerShell** in the root `DocGuard` workspace folder (`c:\Users\Dell\Desktop\DocGuard`).

## 9. Backend Setup (Windows PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

DocGuard now requires a PostgreSQL database for account/session persistence. Create
a local database and configure `DATABASE_URL` in `backend\.env` (the example value
contains placeholders only). For example, with PostgreSQL command-line tools
installed and available on `PATH`:

```powershell
createdb docguard
```

For account identity, create a **GitHub OAuth App** (not a GitHub App) with this
callback URL:

```text
http://localhost:8000/api/auth/callback
```

Set `GITHUB_OAUTH_CLIENT_ID` and `GITHUB_OAUTH_CLIENT_SECRET` in `backend\.env`.
Generate a signing secret locally with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Put the generated value in `GITHUB_OAUTH_STATE_SECRET`; do not commit `.env` or
share the generated secret. GitHub sign-in requests only `read:user` and
`user:email` scopes. It establishes account identity only and does not authorize
private repository access.

### GitHub App setup (repository access)

Create a separate GitHub App in your GitHub account or organization settings.
Use these local callback and webhook URL placeholders:

| GitHub App setting | Local URL |
|---|---|
| Setup URL | `http://localhost:8000/api/github/installations/callback` |
| User authorization callback URL | `http://localhost:8000/api/github/user-callback` |
| Webhook URL | `http://localhost:8000/api/github/webhook` |

Set repository permissions to **Metadata: Read-only**, **Contents: Read-only**,
and **Pull requests: Read-only**. Subscribe to the `installation` and
`installation_repositories` webhook events. Generate a webhook secret and set
`GITHUB_APP_WEBHOOK_SECRET`; provide the App ID, slug, client ID, client secret,
and private key through the matching `GITHUB_APP_*` variables in `backend\.env`.
These are administrator-provisioned credentials; do not put real values in
source control or frontend environment variables. Replace all local URLs with
the corresponding HTTPS backend URLs when deploying.

Users must separately sign in with the GitHub OAuth App and authorize the
GitHub App installation. OAuth sign-in alone never grants repository access.
See [docs/SECURITY.md](docs/SECURITY.md) for the token and authorization
boundaries.

Start a local Redis service for development. For example, with Docker Desktop:

```powershell
docker run --name docguard-redis -p 6379:6379 -d redis:7-alpine
```

Set `CELERY_BROKER_URL=redis://127.0.0.1:6379/0` in `backend\.env` for this
local-only Redis instance. Production requires a private Redis endpoint using
`rediss://` and authentication; do not expose Redis publicly.

Run the schema migration from `backend\` before starting the API:

```powershell
.\.venv\Scripts\alembic.exe upgrade head
```

*(Note: If PowerShell execution policy blocks `Activate.ps1`, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first, or invoke commands via `.\.venv\Scripts\python.exe`.)*

### Start the Backend Worker and Scheduler

Open two additional PowerShell terminals in `backend\`. Keep both running:

```powershell
.\.venv\Scripts\celery.exe -A app.tasks.celery_app:celery_app worker --pool=solo --loglevel=INFO
```

```powershell
.\.venv\Scripts\celery.exe -A app.tasks.celery_app:celery_app beat --loglevel=INFO
```

Windows uses Celery's `solo` pool for local development. Use the normal
prefork worker pool on supported Linux production workers. PostgreSQL remains
the source of truth; Redis is only the broker. The periodic Beat task recovers
stale jobs and redispatches queued rows after broker interruptions.

### Start the Backend Server

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --port 8000
```

- Health Check: http://127.0.0.1:8000/api/health
- Interactive Swagger Docs: http://127.0.0.1:8000/docs

## 10. Frontend Setup (Windows PowerShell)

Open a **second Windows PowerShell** terminal in the root `DocGuard` directory:

```powershell
cd frontend
npm install
npm run dev
```

- Open **http://localhost:5173** in your browser.
- Production build verification:
  ```powershell
  cd frontend
  npm run build
  ```

## 11. Environment Variable Setup

Copy `backend/.env.example` to `backend/.env`:

```powershell
Copy-Item backend\.env.example backend\.env
```

Supported variables in `backend/.env`:
```env
APP_NAME=DocGuard
APP_VERSION=0.1.0
APP_ENV=development
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/docguard
GITHUB_OAUTH_CLIENT_ID=
GITHUB_OAUTH_CLIENT_SECRET=
GITHUB_OAUTH_REDIRECT_URI=http://localhost:8000/api/auth/callback
GITHUB_OAUTH_STATE_SECRET=
GITHUB_APP_ID=
GITHUB_APP_SLUG=
GITHUB_APP_CLIENT_ID=
GITHUB_APP_CLIENT_SECRET=
GITHUB_APP_PRIVATE_KEY=
GITHUB_APP_WEBHOOK_SECRET=
GITHUB_APP_SETUP_URL=http://localhost:8000/api/github/installations/callback
GITHUB_APP_USER_CALLBACK_URL=http://localhost:8000/api/github/user-callback
SESSION_COOKIE_NAME=docguard_session
SESSION_TTL_SECONDS=43200
SESSION_COOKIE_SECURE=false
SESSION_COOKIE_SAMESITE=lax
FRONTEND_ORIGIN=http://localhost:5173
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
GIT_OPERATION_TIMEOUT_SECONDS=45
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
ANALYSIS_PER_USER_HOUR_LIMIT=10
ANALYSIS_PER_WORKSPACE_DAY_LIMIT=100
ANALYSIS_MAX_CONCURRENT_PER_WORKSPACE=2
ANALYSIS_TIMEOUT_SECONDS=180
GEMINI_PROVIDER_TIMEOUT_MS=20000
GEMINI_MAX_OUTPUT_TOKENS=512
GEMINI_DAILY_BUDGET_USD=0
GEMINI_USER_DAILY_BUDGET_USD=0
GEMINI_INPUT_USD_PER_MILLION_TOKENS=0
GEMINI_OUTPUT_USD_PER_MILLION_TOKENS=0
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
ANALYSIS_RETRY_MAX_ATTEMPTS=3
```

With no CORS origins configured, the backend allows the two local Vite origins.
Setting `CORS_ALLOWED_ORIGINS` replaces those defaults with the explicit
comma-separated allowlist; `FRONTEND_ORIGIN` is also supported. Origins must be
bare HTTP(S) origins, and wildcard values are rejected.

`SESSION_COOKIE_SECURE=false` is for local HTTP development only. Production
requires HTTPS origins and `SESSION_COOKIE_SECURE=true`. The persistent session
cookie is HttpOnly; its opaque random value is never returned in JSON or stored
raw in the database.

## 12. Gemini API Configuration

To enable Google Gemini explanations:
1. Obtain a Gemini API key from Google AI Studio and set it in `backend\.env` (never commit this file).
2. Set positive workspace/user daily budgets and input/output USD-per-million-token rates using the current pricing for the configured model. DocGuard fails closed if any spend-control setting is missing or zero.
3. Configure `GEMINI_PROVIDER_TIMEOUT_MS` and `GEMINI_MAX_OUTPUT_TOKENS` within the supported ranges.
4. Restart the backend. Only selected persisted finding evidence (including bounded code/documentation excerpts) is sent to Google Gemini; the dashboard discloses this when Gemini is selected.

## 13. Mock AI Mode

In development and tests, **Mock (Offline Deterministic)** runs `MockAIProvider`:
- Requires no API key and makes zero external LLM requests.
- Synthesizes deterministic explanations (`[Mock AI Explanation]`) and surgical Markdown replacement proposals directly from the finding's verified code and documentation evidence.
- Never silently pretends to be Gemini.

Mock AI is rejected in production. Production explanations require Gemini and configured spend controls.

## 14. How to Connect a Repository

Sign in with the configured GitHub OAuth App first. `/`, `/api/health`, and
`/api/auth/status` remain public; repository, analysis, and AI routes require an
authenticated session. GitHub sign-in is separate from repository authorization:
configure the separate GitHub App to grant access to repositories selected by
the user or organization.

1. Open http://localhost:5173 and sign in.
2. Select **Connect GitHub App** and authorize the App for the desired repositories.
3. Choose a repository from **Authorized GitHub repositories** and click **Load repository**.
4. Open **History** in the dashboard to revisit persisted analysis, follow active jobs, retry eligible failures, or delete terminal records.

## 15. How to Compare Commits

1. Select a **Base Commit (Older / Starting Point)** and a different **Head Commit (Newer / Target Point)** from the dropdowns.
2. Click **Compare Commits** (`POST /api/repositories/compare`) to browse changed files (`added`, `modified`, `deleted`, `renamed`), line counts, and color-highlighted unified diff patches.

## 16. How to Run Code Analysis & Documentation Mapping

- Click **Analyze Python Changes** (`POST /api/analyze/code`) to run static Python AST comparison between Base and Head commits.
- Click **Analyze Documentation** (`POST /api/analyze/documentation`) to discover Markdown files at the Head commit, extract statements with exact line numbers, and view symbol mappings with confidence filters (**All**, **High**, **Medium**, **Low**, **Ambiguous**, **Unmapped**).

## 17. How to Run Documentation Drift Analysis

- Click **ANALYZE DOCUMENTATION DRIFT** (`POST /api/analyze/drift`).
- The response includes a persisted `analysis_id`; only this analysis ID and its stored finding IDs may be used for AI explanations.
- Filter findings by Status (**All Findings**, **Confirmed Drift**, **Potential Drift**, **Uncertain**, **Resolved**) or Severity (**Critical**, **High**, **Medium**, **Low**).
- Click **Inspect Evidence** on any finding to view the exact documentation statement, Base and Head Python code snippets, doc-to-code mapping evidence, detection rule, and recommended action.

## 18. How to Request AI Explanations & Fix Suggestions

- On any drift finding card, click **EXPLAIN WITH AI** or **SUGGEST DOCUMENTATION FIX** (`POST /api/analyze/explanations`).
- Review the AI-generated explanation, code change summary, documentation issue, and proposed Markdown replacement text.
- Click **Copy Suggestion** to copy the replacement Markdown to your clipboard for manual editing.

## 19. How to Run Tests & Evaluation Benchmark

From `backend/` (with `.venv` activated):
```powershell
python -m pytest -v
```
Or from the root `DocGuard` directory:
```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests -v
```
See [docs/TESTING.md](docs/TESTING.md) for backend and frontend test coverage and the 16-case evaluation benchmark (`Precision = 1.00`, `Recall = 1.00`, `F1 = 1.00`).

## 20. Demo Instructions

See [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md) and [docs/PRESENTATION_SCRIPT.md](docs/PRESENTATION_SCRIPT.md) for the step-by-step walkthrough using the controlled demo repository (`https://github.com/docguard-demo/billing-api`) and the 5–7 minute hackathon presentation script.

## 21. Known Limitations

- **Operational maturity**: Durable jobs and user-facing history/retry/deletion are implemented, but actual PostgreSQL/Redis/Celery deployments, browser OAuth, private GitHub access, and Gemini provider calls have not been verified against live services.
- **Worker isolation**: Analysis has configured per-user/workspace quotas, a total deadline, clone/tree/source/evidence caps, and Gemini spend reservations. Celery timeouts do not provide OS/container CPU, memory, filesystem, or network-egress isolation.
- **Retention**: Users can delete terminal analyses and findings; automated retention, export, backup deletion, and restore policies are not implemented.
- **Python (`.py`) & Markdown (`.md`) Focus**: Static code analysis targets Python source files via `ast`, and documentation parsing targets Markdown files (`.md`, `.markdown`, `.mdown`). ReStructuredText (`.rst`) files are skipped as non-Markdown files.
- **Read-Only Advisory Corrections**: DocGuard never automatically edits files, creates commits, pushes branches, or opens pull requests.
- **Deterministic Structural Scope**: Drift detection prioritizes high precision on explicit symbol, parameter, default, return annotation, and file references rather than speculative semantic claims about internal function body changes.
- **Multi-user teams**: Personal workspaces and membership roles exist, but team creation, membership administration, and organization-level access controls are not implemented.

## 22. Security Considerations

- Repository code and Markdown code blocks are **never executed, imported, or evaluated**.
- Git repositories are cloned in `--bare` mode into isolated temporary directories and deleted immediately inside `finally` blocks.
- Only user-selected persisted finding evidence is sent to Gemini; it is bounded and isolated inside `<UNTRUSTED_REPOSITORY_DATA>` tags. Prompt-injection defenses reduce risk but cannot guarantee model obedience.
- `GEMINI_API_KEY` is stored strictly on the backend, excluded from Git via `.gitignore`, and scrubbed from all error messages.
- See [docs/SECURITY.md](docs/SECURITY.md) for the complete security audit.
