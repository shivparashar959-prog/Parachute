# DocGuard Architecture Overview

## 1. System Architecture

**DocGuard** is a full-stack documentation drift detection platform built on a deterministic-first, AI-assisted architecture:

1. **Deterministic Verification Engine (Source of Truth)**:
   - Connects to public HTTPS GitHub repositories via `GitPython` using ephemeral bare clones (`--bare`).
   - Performs static Python AST analysis (`ast.parse`, `ast.unparse`, `ast.dump`) to detect 17 categories of structural code changes between `base_commit` and `head_commit`.
   - Parses Markdown documentation files (`README.md`, `docs/**/*.md`, `CONTRIBUTING.md`, `CHANGELOG.md`) with exact 1-based line preservation.
   - Maps documentation statements to Python AST symbols using deterministic evidence (qualified names, API headings, inline code spans, call expressions, parameter references, and module paths).
   - Evaluates 9 deterministic drift detection rules (**Rules A–I**) and 12 false-positive prevention guards.
2. **Advisory AI Layer (`backend/app/ai/`)**:
   - Consumes verified `DriftFinding` records to produce human-readable explanations and surgical Markdown replacement proposals.
   - Supports offline **Mock AI Mode** (`MockAIProvider`) and **Google Gemini API Mode** (`GeminiAIProvider` via `google-genai`).
   - Never alters deterministic finding statuses (`CONFIRMED_DRIFT`, `POTENTIAL_DRIFT`, `UNCERTAIN`, `RESOLVED`, `UNCHANGED`) and never modifies repository files automatically.

---

## 2. Backend Module Layout (`backend/app/`)

```text
backend/app/
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
│   ├── repositories.py            # POST /api/repositories/inspect & /compare
│   ├── code_analysis.py           # POST /api/analyze/code
│   ├── documentation.py           # POST /api/analyze/documentation
│   ├── drift.py                   # POST /api/analyze/drift
│   └── ai_explanations.py         # GET /providers & POST /api/analyze/explanations
├── evaluation/
│   └── evaluator.py               # 16-case reproducible benchmark (TP, FP, TN, FN, Precision, Recall, F1)
├── schemas/
│   ├── repository.py
│   ├── code_analysis.py
│   ├── documentation.py
│   ├── drift.py
│   └── ai_explanation.py
├── services/
│   ├── github_service.py          # URL/SHA validation, bare cloning & temp cleanup
│   ├── code_analysis_service.py   # Git blob reader & AST analysis orchestration
│   ├── documentation_service.py   # Markdown discovery & symbol mapping orchestration
│   ├── drift_analysis_service.py  # Single-clone base/head drift analysis service
│   ├── ai_explanation_service.py  # AI provider resolution & request bounding
│   └── demo_fixture.py            # Controlled 2-commit demonstration Git repository builder
└── main.py                        # FastAPI app, CORS middleware, health/root endpoints
```

---

## 3. Data Flow Pipeline

1. **Repository Inspection (`POST /api/repositories/inspect`)**:
   - Validates `repository_url`, clones a shallow bare repository into a temporary directory, extracts `default_branch` and up to 20 first-parent distinct-tree commits, and cleans up the temporary directory.
2. **Commit Diff Comparison (`POST /api/repositories/compare`)**:
   - Uses `git diff-tree -r -M --raw -z` for file change classification (`added`, `modified`, `deleted`, `renamed`) and `git diff-tree -r -p -M` for unified diff patches.
3. **Python AST Analysis (`POST /api/analyze/code`)**:
   - Reads Python blobs directly from `base_commit.tree` and `head_commit.tree` in memory, parses AST trees with `ast.parse()`, and emits `SymbolChange` items.
4. **Documentation Parsing & Mapping (`POST /api/analyze/documentation`)**:
   - Discovers `.md` files at `head_commit`, extracts `DocumentationUnit` statements with exact 1-based line numbers, and maps them to extracted Python AST symbols with `HIGH`, `MEDIUM`, or `LOW` confidence.
5. **Deterministic Drift Detection (`POST /api/analyze/drift`)**:
   - Extracts AST symbols and Markdown units at both `base_commit` and `head_commit` (caching unchanged blob SHAs), evaluates Rules A–I, and outputs `DriftFinding` records.
6. **AI Explanations & Fix Suggestions (`POST /api/analyze/explanations`)**:
   - Sends minimal, sanitized finding evidence to `MockAIProvider` or `GeminiAIProvider`, validates the JSON response, and returns explanations and copyable Markdown replacement proposals.
