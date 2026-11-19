# DocGuard Security Review & Threat Model

## 1. Authorized Repository Handling

1. **Repository ID and workspace authorization**:
   - Browser requests provide a GitHub numeric repository ID, not an arbitrary clone URL.
   - The backend resolves the ID only from the authenticated user's personal workspace, requires an active linked installation and catalog entry, then rechecks the installation-scoped repository with GitHub.
   - Repository names and URLs are mutable metadata; repository IDs are the stable lookup key. Cross-workspace IDs fail closed.
   - `github_service.parse_and_validate_github_url` remains a defense-in-depth check for canonical URLs constructed from trusted server-side catalog metadata.
2. **GitHub App token handling**:
   - Installation tokens are short-lived and minted for the selected repository when possible. Tokens are held only in server memory for the API request or worker operation and supplied to Git through HTTP extra-header environment configuration, never embedded in clone URLs or Celery task payloads.
   - The App should have read-only Metadata, Contents, and Pull requests permissions. Installation and repository access are rechecked with GitHub before source retrieval or PR listing.
   - Installation state is random, hashed at rest, short-lived, user-bound, purpose-bound, and consumed once. The installation is verified against the signed-in GitHub numeric identity before linking.
   - Signed webhooks validate HMAC-SHA256, cap body size, and deduplicate delivery IDs. Uninstall, suspension, or repository removal deactivates access.
3. **Commit SHA Validation (`github_service.validate_commit_sha`)**:
   - General repository endpoints validate `^[0-9a-fA-F]{7,40}$`; persisted drift analyses additionally require full 40-character SHA-1 values, then resolve the commit objects server-side. This prevents Git option injection and avoids storing mutable refs or abbreviated identifiers.
4. **Zero Repository Code Execution**:
   - Clones are performed with `--bare`, `allow_unsafe_options=False`, and `allow_unsafe_protocols=False`. No working tree files or Git checkout hooks are ever written to disk.
   - Python files are analyzed exclusively with Python's built-in static `ast.parse()`, `ast.unparse()`, and `ast.dump()`. Repository code is never imported, executed, or evaluated (`eval`/`exec` are never called).
   - Markdown documentation and fenced code blocks are parsed purely as text strings and never executed.
5. **Resource Limits & Ephemeral Cleanup**:
   - Enforces strict caps on file size (`500 KB` per Python/Markdown file), changed files (`150`), documentation files (`60`), extracted units (`600`), diff patch characters (`20 KB` per file, `150 KB` total), and AI explanations per request (`10`).
   - Persisted drift analysis also has a configurable overall deadline, existing per-operation Git timeout, a monitored `200 MB` clone-directory cap, `25,000` tree entries per commit, `5,000` analyzable-file cap, `20 MB` aggregate source-byte cap, `500` persisted findings, and `4 MB` aggregate evidence cap. Clone size is polled during transfer and may briefly overshoot between polls. Prompt input is capped at `16 KB`; Gemini output tokens and provider time are capped by configuration.
   - Per-user hourly and per-workspace daily/concurrent analysis limits apply. Gemini spend is pre-reserved against operator-configured user/workspace daily budgets and model token rates; this is a conservative estimate, not the provider invoice.
   - Worker clones use a per-analysis/per-attempt scratch directory. Job records expose cleanup state; Celery Beat retries removal of orphaned scratch directories after worker loss. Existing transient API clone helpers still suppress some final filesystem errors; their cleanup is not represented in persisted job state.

## 2. Background Processing (Milestone 5)

- PostgreSQL is the source of truth for job state and progress. Celery messages contain only the analysis UUID, never repository evidence, user IDs supplied by the browser, GitHub tokens, Gemini credentials, or installation credentials.
- Workers load the initiator and workspace from the persisted analysis, recheck membership and current GitHub installation/repository authorization, then mint a short-lived installation token immediately before Git access.
- Duplicate deliveries are safe because a conditional database transition permits only one worker to claim a queued row. Bounded retries apply only to classified transient GitHub/network failures; validation, authorization, and resource-limit failures are terminal.
- A periodic Celery Beat task redispatches queued rows and reclaims stale running rows after worker loss. Redis broker outages leave the PostgreSQL analysis queued with a safe `queue_unavailable` category for later redispatch.
- Production configuration requires a TLS Redis URL, authentication credentials, and a non-local broker hostname. Operators must additionally configure the Redis service as private, persistent, authenticated, and no-eviction; the application cannot verify the provider's network policy or persistence settings.
- Cancellation is cooperative at analysis checkpoints and may wait for an in-progress bounded Git operation. Celery task timeouts bound duration but do not enforce CPU, memory, filesystem, or network-egress isolation. Production workers still require a restricted container/runtime before accepting arbitrary repositories.

---

## 3. AI & Prompt Injection Security

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
4. **Provider and Data-Disclosure Policy**:
   - AI explanations are selected by persisted analysis and finding IDs; client-supplied evidence objects are rejected.
   - Mock AI is available only in development/test. Production selects Gemini and fails closed if the API key, model budget, or token rates are not configured.
   - The UI discloses that selected finding evidence, including bounded code/documentation excerpts, is sent to Google Gemini. The user must explicitly select Gemini.

---

## 4. Account Authentication and Browser Sessions

1. **Identity Provider Is Separate from Repository Authorization**:
   - Local accounts use an email address and a scrypt password hash. Passwords
     are not stored in plaintext; registration and login are rate limited.
   - Account sign-in uses GitHub OAuth via Authlib with `read:user` and
     `user:email` scopes. This is not a GitHub App installation and grants no
     private-repository access.
   - The stable GitHub numeric account ID is the external subject. Accounts are
     not linked by email. Only GitHub's verified primary email is stored.
   - OAuth access tokens are used only in memory to retrieve the profile and
     verified email; they are not stored in PostgreSQL, cookies, frontend state,
     logs, or API responses.
2. **Callback Integrity and Replay Resistance**:
   - Authlib validates the OAuth `state` against a short-lived, signed,
     HttpOnly transaction cookie. The callback also consumes the matching
     database state hash exactly once, preventing callback replay.
   - PKCE with `S256` is enabled. GitHub OAuth is not OIDC and does not provide
     an OIDC ID-token nonce claim; DocGuard does not claim OIDC nonce validation.
   - The callback destination is configured server-side. No arbitrary client
     `next`/redirect URL is accepted.
3. **Opaque Persistent Sessions**:
   - A successful callback issues a cryptographically random opaque session
     cookie. PostgreSQL stores only the SHA-256 hash of that value.
   - The session cookie is `HttpOnly`, host-only, `SameSite=Lax` by default,
     and `Secure` in production. Local HTTP development may explicitly set
     `SESSION_COOKIE_SECURE=false`; production configuration rejects that value.
   - Sessions expire server-side, a successful re-login revokes/rotates the
     current browser session, and logout revokes the record and clears the
     cookie. Session values are never included in JSON.
4. **CSRF, CORS, and Login Throttling**:
   - Cookie-authenticated logout and GitHub App installation initiation require
     an exact configured `Origin` and reject cross-site Fetch Metadata. No
     state-changing logout is exposed as GET.
   - Production CORS requires a configured HTTPS frontend origin. The
     credentialed allowlist is exact; only GET/POST and Accept/Content-Type are
     allowed.
   - OAuth starts and local password attempts are limited to 10 requests per
     client address per 60-second PostgreSQL bucket. The address is stored as
     an HMAC, and untrusted forwarded headers are not used to determine it.
   - OAuth failures return generic safe messages; provider tokens, callback
     codes, and session values are not reflected in responses.

### Remaining Authorization Boundaries

- GitHub account sign-in is not GitHub repository permission. The current
  repository catalog and analysis routes require explicit GitHub App
  authorization and support public/private visibility when granted.
- Drift analyses and findings are persisted under the personal workspace and
  their authorized repository. History, detail, retry, and deletion APIs are
  workspace scoped and recheck current GitHub repository access. History rows
  for revoked repositories omit repository ID, name, commits, and finding
  counts; detail and mutations fail closed. Deletion is limited to terminal
  jobs and retains unlinked Gemini spend reservations for quota accounting.
  Team-workspace authorization and automated retention policy remain future
  work.
- The controlled demo URL maps to a local fixture only in development/test;
  production does not intercept it.
- Analysis quotas and Gemini spend reservations apply to the drift/AI workflow.
  Other API endpoints do not yet have a general purpose account-wide rate limit.
- Automated tests cover history pagination, workspace isolation, revoked-access
  redaction, retry eligibility, terminal-only deletion, and spend-accounting
  retention. They do not replace a live multi-user deployment test or a formal
  security assessment.
- The hosted GitHub OAuth callback and production cookie/CORS settings require
  real, administrator-provisioned secrets and HTTPS configuration; no live
  provider credentials or hosted callback were tested here.
- GitHub App installation, repository sync, worker authorization, and webhook
  paths are covered with mocked tests only. A real App, private repository
  clone, live webhook, and hosted callback were not tested.
- PostgreSQL row-lock behavior and quotas were not executed against a live
  PostgreSQL server; local tests use SQLite. A live authenticated Redis broker,
  Celery worker/Beat deployment, and crash behavior under an actual worker
  process were not exercised in this environment.
- Application limits and Celery timeouts do not enforce OS/container CPU,
  memory, filesystem, or network-egress isolation. Production worker runtime
  isolation remains a launch requirement.
