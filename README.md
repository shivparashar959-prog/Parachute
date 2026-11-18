# DocGuard — AI-Assisted Documentation Drift Detection Platform

**DocGuard** is a deterministic-first, AI-assisted documentation drift detection platform that connects public GitHub repositories, analyzes Python code changes using static Abstract Syntax Tree (`ast`) analysis, maps Markdown documentation statements to code symbols, detects evidence-backed documentation drift across commits, and generates AI explanations and copyable Markdown correction proposals.

---

## 1. Project Overview

When source code evolves between commits, project documentation frequently falls out of sync. **DocGuard** bridges the gap between source code and documentation by combining static Python AST analysis, line-accurate Markdown parsing, deterministic drift rules (**Rules A–I**), and an isolated AI explanation layer (supporting offline **Mock AI Mode** and **Google Gemini API**).

## 2. Problem Statement

Normal code reviews and CI test suites verify that code compiles and tests pass, but rarely catch when a changed default parameter (`role='user'` → `role='admin'`), a removed parameter (`port`), an added required argument (`recipient_email`), or a renamed/deleted function invalidates statements in `README.md` or `docs/**/*.md`. Conversely, naive LLM wrappers hallucinate or flag every changed code line as documentation drift. DocGuard solves this by making **deterministic AST + Markdown evidence the source of truth** and using AI strictly to explain verified findings and propose minimal fixes.

## 3. Key Features

- **Live GitHub Repository Integration (`POST /api/repositories/inspect` & `/compare`)**: Connects to public HTTPS GitHub repositories in isolated bare clones (`--bare`), retrieves first-parent commit history, and computes unified file diffs (`added`, `modified`, `deleted`, `renamed`).
- **Static Python AST Code Change Analyzer (`POST /api/analyze/code`)**: Uses Python's built-in `ast` module without executing code to extract classes, functions, async functions, methods (`instance`, `@classmethod`, `@staticmethod`), nested functions, and all 5 parameter kinds (`/`, `*`, `*args`, `**kwargs`), detecting 17 symbol change types.
- **Line-Accurate Markdown Parser & Code Mapper (`POST /api/analyze/documentation`)**: Discovers repository Markdown files, extracts verbatim documentation units with exact 1-based line numbers, and maps them to Python symbols with `HIGH`, `MEDIUM`, or `LOW` confidence (`MAPPED`, `AMBIGUOUS`, `UNMAPPED`).
- **Deterministic Drift Detection Engine (`POST /api/analyze/drift`)**: Evaluates 9 deterministic rules (**Rules A–I**) and 12 false-positive guards across base and head commits, classifying findings as `CONFIRMED_DRIFT`, `POTENTIAL_DRIFT`, `UNCERTAIN`, `RESOLVED`, or `UNCHANGED` with numerical confidence (`0.0–1.0`) and severity (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
- **AI Explanations & Fix Suggestions (`POST /api/analyze/explanations`)**: Supports offline deterministic **Mock AI Mode** (`MockAIProvider`) and **Google Gemini API Mode** (`GeminiAIProvider` via `google-genai`) with prompt injection protection, strict JSON validation, and copyable Markdown fix proposals.
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

## 5. Technology Stack

- **Backend**: Python 3.10+, FastAPI, Uvicorn, Pydantic v2, GitPython, Python `ast`, `google-genai`, `python-dotenv`
- **Frontend**: React 19 (JavaScript), Vite 6, Tailwind CSS 4 (`@tailwindcss/vite`)
- **Testing**: Pytest, FastAPI `TestClient` (`httpx`)

## 6. Project Structure

```text
DocGuard/
├── backend/
│   ├── .venv/                             # Local Python virtual environment (git-ignored)
│   ├── app/
│   │   ├── ai/                            # BaseAIProvider, MockAIProvider, GeminiAIProvider, prompt & response validators
│   │   ├── analyzers/                     # Python AST, Markdown parser/extractor/mapper, and Drift Rules A–I
│   │   ├── api/                           # FastAPI routers (repositories, code_analysis, documentation, drift, ai_explanations)
│   │   ├── evaluation/                    # 16-case reproducible benchmark dataset & TP/FP/TN/FN/Precision/Recall/F1 evaluator
│   │   ├── schemas/                       # Pydantic request/response schemas
│   │   ├── services/                      # Business services & controlled demo repository fixture
│   │   └── main.py                        # FastAPI application entrypoint
│   ├── tests/                             # 67 automated pytest unit & integration tests
│   ├── .env.example                       # Safe placeholder environment variables
│   └── requirements.txt                   # Backend Python dependencies
├── frontend/
│   ├── src/
│   │   ├── api/health.js                  # Frontend API client service
│   │   ├── App.jsx                        # DocGuard Dashboard UI
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

## 8. Windows Installation Instructions

Open **Windows PowerShell** in the root `DocGuard` workspace folder (`c:\Users\Dell\Desktop\DocGuard`).

## 9. Backend Setup (Windows PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

*(Note: If PowerShell execution policy blocks `Activate.ps1`, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first, or invoke commands via `.\.venv\Scripts\python.exe`.)*

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
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
FRONTEND_ORIGIN=http://localhost:5173
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
```

## 12. Gemini API Configuration

To enable live Google Gemini explanations:
1. Obtain a Gemini API key from Google AI Studio.
2. Set `GEMINI_API_KEY=your_key_here` in `backend/.env` (never commit `backend/.env` to Git).
3. Restart the FastAPI server and select **Gemini** in the dashboard's **AI Provider** selector.
*(Note: Live Gemini API usage may incur costs depending on your Google AI Studio billing plan.)*

## 13. Mock AI Mode

When `GEMINI_API_KEY` is left blank (or when **Mock (Offline Deterministic)** is selected in the UI), DocGuard runs `MockAIProvider`:
- Requires no API key and makes zero external LLM requests.
- Synthesizes deterministic explanations (`[Mock AI Explanation]`) and surgical Markdown replacement proposals directly from the finding's verified code and documentation evidence.
- Never silently pretends to be Gemini.

## 14. How to Connect a Repository

1. Open http://localhost:5173.
2. Enter any public HTTPS GitHub URL (e.g. `https://github.com/pallets/flask`) or click one of the **Quick Presets** (**Controlled Demo (`docguard-demo/billing-api`)** or **Real GitHub (`pallets/flask`)**).
3. Click **Connect Repository** (`POST /api/repositories/inspect`).

## 15. How to Compare Commits

1. Select a **Base Commit (Older / Starting Point)** and a different **Head Commit (Newer / Target Point)** from the dropdowns.
2. Click **Compare Commits** (`POST /api/repositories/compare`) to browse changed files (`added`, `modified`, `deleted`, `renamed`), line counts, and color-highlighted unified diff patches.

## 16. How to Run Code Analysis & Documentation Mapping

- Click **Analyze Python Changes** (`POST /api/analyze/code`) to run static Python AST comparison between Base and Head commits.
- Click **Analyze Documentation** (`POST /api/analyze/documentation`) to discover Markdown files at the Head commit, extract statements with exact line numbers, and view symbol mappings with confidence filters (**All**, **High**, **Medium**, **Low**, **Ambiguous**, **Unmapped**).

## 17. How to Run Documentation Drift Analysis

- Click **ANALYZE DOCUMENTATION DRIFT** (`POST /api/analyze/drift`).
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
See [docs/TESTING.md](docs/TESTING.md) for full details on the 67 automated tests and the 16-case evaluation benchmark (`Precision = 1.00`, `Recall = 1.00`, `F1 = 1.00`).

## 20. Demo Instructions

See [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md) and [docs/PRESENTATION_SCRIPT.md](docs/PRESENTATION_SCRIPT.md) for the step-by-step walkthrough using the controlled demo repository (`https://github.com/docguard-demo/billing-api`) and the 5–7 minute hackathon presentation script.

## 21. Known Limitations

- **Public GitHub Repositories Only**: Only public `https://github.com/<owner>/<repository>` URLs are accepted.
- **Python (`.py`) & Markdown (`.md`) Focus**: Static code analysis targets Python source files via `ast`, and documentation parsing targets Markdown files (`.md`, `.markdown`, `.mdown`). ReStructuredText (`.rst`) files are skipped as non-Markdown files.
- **Read-Only Advisory Corrections**: DocGuard never automatically edits files, creates commits, pushes branches, or opens pull requests.
- **Deterministic Structural Scope**: Drift detection prioritizes high precision on explicit symbol, parameter, default, return annotation, and file references rather than speculative semantic claims about internal function body changes.

## 22. Security Considerations

- Repository code and Markdown code blocks are **never executed, imported, or evaluated**.
- Git repositories are cloned in `--bare` mode into isolated temporary directories and deleted immediately inside `finally` blocks.
- Untrusted repository evidence sent to AI providers is truncated and isolated inside `<UNTRUSTED_REPOSITORY_DATA>` tags to prevent indirect prompt injection.
- `GEMINI_API_KEY` is stored strictly on the backend, excluded from Git via `.gitignore`, and scrubbed from all error messages.
- See [docs/SECURITY.md](docs/SECURITY.md) for the complete security audit.
