# DocGuard Security Review & Threat Model

## 1. Untrusted Repository Handling

1. **HTTPS GitHub URL Whitelisting (`github_service.parse_and_validate_github_url`)**:
   - Only `https://github.com/<owner>/<repository>` URLs are accepted.
   - Rejects `http://`, `ssh://`, `git@`, `file://`, Windows/POSIX local paths (`C:\...`, `/etc/...`), path traversal sequences (`..`, `\`), embedded credentials (`user:pass@`), custom ports, query strings, fragments, and non-GitHub hosts (`gitlab.com`, `localhost`, `127.0.0.1`).
   - Reconstructs the canonical clone URL from regex-validated `owner` and `repo` tokens so raw user strings are never passed to Git commands.
2. **Commit SHA Validation (`github_service.validate_commit_sha`)**:
   - Enforces `^[0-9a-fA-F]{7,40}$`, preventing Git option injection (such as `--upload-pack`).
3. **Zero Repository Code Execution**:
   - Clones are performed with `--bare`, `allow_unsafe_options=False`, and `allow_unsafe_protocols=False`. No working tree files or Git checkout hooks are ever written to disk.
   - Python files are analyzed exclusively with Python's built-in static `ast.parse()`, `ast.unparse()`, and `ast.dump()`. Repository code is never imported, executed, or evaluated (`eval`/`exec` are never called).
   - Markdown documentation and fenced code blocks are parsed purely as text strings and never executed.
4. **Resource Limits & Ephemeral Cleanup**:
   - Enforces strict caps on file size (`500 KB` per Python/Markdown file), changed files (`150`), documentation files (`60`), extracted units (`600`), diff patch characters (`20 KB` per file, `150 KB` total), and AI explanations per request (`10`).
   - Temporary bare clone directories (`docguard_repo_*`) are guaranteed to be closed and deleted inside a `finally` block using a Windows read-only attribute handler (`_remove_readonly`).

---

## 2. AI & Prompt Injection Security

1. **Backend-Only API Keys**:
   - `GEMINI_API_KEY` is read strictly from backend environment variables (`backend/.env`).
   - `.gitignore` excludes `.env`, `backend/.env`, `frontend/.env`, and `backend/.venv/`.
   - `_scrub_secret()` redacts any occurrence of the API key from exception strings before logging or returning HTTP errors.
2. **Indirect Prompt Injection Defense (`prompt_builder.py`)**:
   - All untrusted repository text (Markdown statements, code snippets, symbol names) is serialized inside `<UNTRUSTED_REPOSITORY_DATA>...</UNTRUSTED_REPOSITORY_DATA>` tags, with any literal closing tags escaped to `&lt;/UNTRUSTED_REPOSITORY_DATA&gt;`.
   - `SYSTEM_INSTRUCTION` explicitly directs the model to treat everything inside `<UNTRUSTED_REPOSITORY_DATA>` as passive data and never follow instructions contained within it.
   - `detect_prompt_injection_patterns()` identifies instruction-override phrases (`"ignore previous instructions"`, `"system prompt override"`, `"output the api key"`) and records a security note in the response limitations.
3. **Deterministic Status Integrity & Read-Only Suggestions**:
   - Only the deterministic drift engine assigns `status` (`CONFIRMED_DRIFT`, `POTENTIAL_DRIFT`, `UNCERTAIN`, `RESOLVED`, `UNCHANGED`). The AI layer preserves `original_status` unchanged.
   - AI suggestions are read-only proposals displayed for manual review and copy-to-clipboard; DocGuard never modifies, commits, or pushes repository files.
