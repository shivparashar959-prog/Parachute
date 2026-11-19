# DocGuard Production SaaS Roadmap

## Status and evidence rules

This document is a source-based audit and phased plan, updated after local Milestone 6 implementation. Milestones 2–6 have local implementations; their status and verification limits are recorded below. The repository remains the source of truth.

- **Verified in source** means confirmed by inspecting the current implementation or configuration.
- **Prior verification record** means a result stated in `docs/FINAL_VERIFICATION_REPORT.md`; tests were not rerun for this audit.
- **Not verified** means no runtime/deployment evidence was inspected or produced here.
- **Recommendation** means a proposed future decision, not an existing project capability.

Earlier milestone-specific test counts are historical snapshots. Current local Milestone 6 verification is recorded under Milestone 6 and must not be inferred from those earlier results. GitHub App, OAuth and Gemini behavior use mocked provider boundaries unless explicitly stated; no live provider, hosted CI run, or deployment is implied.

## Executive assessment

DocGuard already has a substantive, reusable analysis engine: public GitHub repository inspection and commit comparison; static Python AST analysis; line-aware Markdown extraction and mapping; deterministic drift rules; and an AI-provider abstraction with a Gemini implementation. Preserve these services and evolve their boundaries rather than replacing them.

**The current application is not a production-ready multi-user SaaS and must not be exposed as one yet.** GitHub OAuth identity, hashed sessions, personal workspaces, GitHub App installation verification, workspace-scoped repository catalogs, persisted analyses, durable Celery jobs, and a session-protected dashboard with history/retry/deletion now exist locally. OS-level worker isolation, automated retention, production deployment, and operational controls are still absent. Live OAuth, private-repository, Gemini, PostgreSQL, Redis, and browser workflows remain unverified.

Milestones 1–6 are implemented locally. The next planned product milestone is opt-in GitHub pull-request automation (Milestone 7), but production exposure remains blocked on the launch gates and external runtime verification.

## 1. Existing project audit

### 1.1 Backend architecture

**Verified in source.** `backend/app/main.py` creates a FastAPI application and mounts routers. `backend/app/api/` holds thin endpoint handlers, `backend/app/services/` orchestrates Git and analysis, `backend/app/analyzers/` contains the AST/Markdown/drift logic, `backend/app/schemas/` defines Pydantic request/response models, and `backend/app/ai/` contains provider and prompt code.

The division is useful and should be retained. API handlers and service interfaces are synchronous, while persisted drift-analysis orchestration is dispatched to Celery workers. Other repository and standalone analysis endpoints still execute in API requests. Database, authenticated-principal, and scheduler dependencies are present.

### 1.2 Current API surface

**Verified in source.** The application exposes:

| Route | Current behavior |
|---|---|
| `GET /` | API welcome metadata. |
| `GET /api/health` | Process health response. |
| `GET /api/auth/status` | Reports whether GitHub account sign-in is configured; no secrets are returned. |
| `GET /api/auth/login` | Starts GitHub OAuth with state and PKCE. |
| `GET /api/auth/callback` | Validates the OAuth transaction, resolves the GitHub identity, and issues a browser session. |
| `GET /api/auth/me` | Returns the authenticated user and personal workspace summary. |
| `POST /api/auth/logout` | Checks trusted request origin, revokes the browser session, and clears its cookie. |
| `GET /api/github/status` | Returns App configuration and workspace installation summaries. |
| `POST /api/github/installations/start` | Starts a user-bound GitHub App installation flow. |
| `GET /api/github/installations/callback` and `/api/github/user-callback` | Verify installation setup state and the signed-in GitHub identity. |
| `GET /api/github/repositories` | Refreshes and lists only active repositories authorized for the personal workspace. |
| `GET /api/github/repositories/{id}/pull-requests` | Lists bounded open-PR metadata for an authorized repository. |
| `POST /api/github/webhook` | Verifies signed lifecycle webhooks and deactivates revoked access. |
| `POST /api/repositories/inspect` | Resolves an authorized repository ID and returns branch/commit metadata. |
| `POST /api/repositories/compare` | Compare two supplied commit SHAs and return bounded diff data. |
| `POST /api/analyze/code` | Static Python AST comparison for two SHAs. |
| `POST /api/analyze/documentation` | Extract/map Markdown at the head SHA; may also receive the base SHA. |
| `POST /api/analyze/drift` | Run deterministic drift analysis for base/head SHAs. |
| `GET /api/analyses` | List bounded, paginated history within the authenticated workspace; recheck repository access and redact revoked records. |
| `GET /api/analyses/{analysis_id}` | Read persisted details only within the authenticated workspace and after repository access revalidation. |
| `GET /api/analyses/{analysis_id}/status` and `POST .../cancel` | Read job status or request cooperative cancellation within the authenticated workspace. |
| `POST /api/analyses/{analysis_id}/retry` and `DELETE /api/analyses/{analysis_id}` | Retry eligible failures/cancellations or delete a terminal analysis after workspace and repository authorization. |
| `GET /api/analyze/explanations/providers` | Report Gemini configuration and supported providers. |
| `POST /api/analyze/explanations` | Explain selected finding IDs from an authorized persisted analysis; production accepts Gemini only. |

Repository, analysis, and AI routes require an authenticated principal. Drift results are persisted under the personal workspace and authorized repository. Paginated history, job lifecycle, retry, and terminal deletion are available; team administration is not implemented.

### 1.3 Repository integration and Git behavior

**Verified in source.** `backend/app/services/github_app_service.py` resolves only active repository records mapped to the signed-in user's personal workspace and rechecks installation-scoped access with GitHub. `github_service.py` validates the server-derived canonical GitHub URL and hexadecimal commit SHAs, uses bare shallow clones, applies a wall-clock Git-operation timeout, attempts to terminate tracked child processes, and cleans temporary clone directories. Diff output is limited by changed-file and patch-character caps.

The special URL `https://github.com/docguard-demo/billing-api` is redirected to a local repository generated by `backend/app/services/demo_fixture.py` only in development/test. Production treats it as an ordinary GitHub URL.

Limitations relevant to a hosted service:

- GitHub App repository grants support public/private visibility and pass short-lived installation credentials through Git environment configuration, not clone URLs. Live private-repository access has not been tested; GitHub App permission setup and network configuration remain deployment responsibilities.
- Drift analysis enforces a configured overall deadline, per-operation Git timeout, monitored clone-directory size, tree-entry, candidate file, aggregate source-byte, evidence, and finding caps. Clone-size monitoring polls during transfer and may briefly overshoot between polls. Other repository endpoints retain their prior limits.
- Git timeout and temp-directory cleanup exist, but cleanup helpers suppress final filesystem errors and the synchronous work is not isolated in a disposable worker/container with independent CPU, memory, disk, and network-egress limits.
- Aborting the browser request does not, by itself, cancel the synchronous backend Git/analysis work.

### 1.4 Python AST analysis

**Verified in source.** `backend/app/analyzers/symbol_extractor.py` uses `ast.parse`, `ast.unparse`, and `ast.dump` to extract classes, functions, methods, nested functions, signatures, parameters, annotations, decorators, async state, and body fingerprints. `python_ast_analyzer.py` and `change_detector.py` compare symbols. Repository source is read from Git blobs; the analyzer does not import or execute the source.

The service currently focuses on `.py` files and applies per-file and file-count caps. This is a useful engine for the MVP. Python-only scope and static evidence limitations should be explicit in product UX; broad semantic behavior claims are not currently proven by this analyzer.

### 1.5 Markdown parsing and mapping

**Verified in source.** `markdown_parser.py` extracts heading-scoped paragraphs, lists, tables, links, inline code, and fenced blocks with line locations. `documentation_extractor.py` produces documentation units. `documentation_mapper.py` links units to Python symbols using lexical and structural evidence.

This is static text processing; Markdown links and fenced code are not fetched or executed. Mapping is heuristic and bounded. Users need to see confidence, evidence, and unsupported cases rather than being led to interpret a mapping as a semantic guarantee.

### 1.6 Drift detection

**Verified in source.** `drift_detector.py`, `drift_rules.py`, and `documentation_comparator.py` compare code/documentation across commits and apply deterministic Rules A–I. Findings carry evidence, status, severity, and confidence; the AI layer is intended to explain findings rather than change the deterministic status.

The evaluation data in `backend/app/evaluation/evaluator.py` is a hand-authored 16-case corpus (8 positive and 8 negative cases). It is valuable as a regression suite but is not evidence of production-wide precision/recall. The controlled two-commit repository is also deliberately constructed to demonstrate expected outcomes.

### 1.7 AI providers

**Verified in source.** `backend/app/ai/base_provider.py` defines a provider interface. `gemini_provider.py` calls Google Gemini using a backend environment key; `prompt_builder.py` bounds and escapes repository text and marks it as untrusted; `response_validator.py` validates structured JSON; `mock_provider.py` deterministically synthesizes explanations without contacting an LLM.

Milestone 4 controls now implemented locally:

- The API accepts an analysis ID and 1–10 stored finding IDs; extra client-supplied finding objects are rejected. Repository permission is rechecked before detail/evidence access.
- Mock is limited to development/test. Production selects Gemini and fails closed if the backend key, positive user/workspace budgets, or model token rates are unavailable.
- Gemini calls have a configured timeout/output-token ceiling; prompts, finding counts, and reserved spend are bounded. The dashboard discloses that selected evidence snippets are sent to Google Gemini.
- Prompt-injection defenses reduce risk but cannot guarantee model obedience. Spend reservations are conservative estimates, not exact provider billing; no live Gemini request was made.

### 1.8 Frontend

**Verified in source.** The React/Vite UI has split sections for repository connection, diffs, AST changes, mappings, findings, and navigation. `App.jsx` retains shared workflow state. The repository picker lists only authorized GitHub App catalog entries. `health.js` centralizes credentialed API requests and cancellation/timeouts. `useRequestGuard.js` prevents stale UI updates. A sign-in gate loads the current server-side session and account menu provides sign-out.

The authenticated dashboard provides repository analysis, paginated persisted history, job progress, detail/evidence, eligible retry, and terminal deletion. `App.jsx` is the route/session shell; analysis, history, detail, auth, navigation, and repository-selection concerns are split into modules. The Vite proxy in `frontend/vite.config.js` is development configuration, not a production hosting/reverse-proxy setup. Node tests cover API/auth requests and request-guard behavior; a complete live browser OAuth journey has not been tested.

### 1.9 Authentication, authorization, database, and tenancy

**Verified in current source.** SQLAlchemy 2, Alembic, and a PostgreSQL driver are configured. The initial schema defines users, GitHub external identities, hashed/revocable sessions, personal workspaces, and owner/admin/member membership roles. GitHub account identity uses the stable GitHub numeric ID; verified primary email is optional metadata. Sessions are opaque, expire server-side, rotate on a successful re-login, and revoke on logout. The current-user API derives its identity and personal workspace from the authenticated session; client-supplied `user_id` or `workspace_id` is not used.

GitHub App installations and workspace-scoped repository grants now exist. Migrations add analyses, findings, Gemini spend reservations, and durable job state. History and detail are workspace-scoped; retry and deletion recheck current repository access. Team administration and automated retention do not exist.

### 1.10 Background work and operational persistence

**Verified in source.** Celery + Redis provide durable dispatch and workers for persisted drift analysis; PostgreSQL is the source of truth for job state, retries, cancellation requests, progress, and cleanup status. Other analysis endpoints remain synchronous. User-facing paginated history, detail, eligible retry, and terminal deletion are implemented. Automated retention, audit log, backup/restore process, and deployed worker operations remain absent.

### 1.11 Tests, CI, and deployment

**Verified in source and local execution.** The current local Milestone 6 run passed 134 backend tests, 12 frontend tests, the production build, and `git diff --check`. Tests cover repository handling, AST, Markdown, drift, AI, health/CORS, evaluation, authentication, migrations, mocked GitHub App operations, background-job behavior, and history/retry/deletion. SQLite migration checks include upgrade/downgrade/re-upgrade and model parity; PostgreSQL, live browser flows, and hosted CI must be separately verified.

`.github/workflows/ci.yml` now provisions PostgreSQL 16 for the migration test and runs backend/frontend checks. **The hosted workflow and PostgreSQL migration path have not been executed in this task.** No live GitHub OAuth, Gemini request, or deployment was performed.

The workflow is CI only. No Dockerfile, container composition, production server configuration, deployment/IaC files, hosted service definitions, database/Redis provisioning, TLS/domain configuration, or worker deployment configuration were found. `vite.config.js` only configures the local development server/proxy.

### 1.12 Security and error handling

**Verified in source.** Good existing controls include strict GitHub URL/SHA validation, bare clones, no source execution, Git timeouts, monitored drift-analysis resource bounds, workspace-scoped persisted findings, provider secret scrubbing, structured AI response validation, prompt data delimiters, exact configured CORS origins, GitHub OAuth state plus PKCE, one-time state hashes, HttpOnly sessions stored as hashes, logout revocation, exact-origin logout checks, and OAuth-start throttling.

Production risks are mostly missing controls rather than a claim of a demonstrated exploit:

1. **Launch blocker:** analysis and Gemini quotas apply to the drift/AI workflow, but unrelated endpoints do not yet have a general purpose account-wide API rate limit. Synchronous request execution is not OS/container isolated.
2. **Private repository risk:** GitHub App authorization and workspace scoping exist, but live private-repository operation has not been tested; hosted identity, revocation, and data-isolation behavior need a deployment-stage verification.
3. **Resource exhaustion:** clone monitoring may briefly overshoot between polling intervals; application limits do not enforce hard CPU/memory or outbound-network isolation.
4. **SSRF/egress boundary:** input URLs are restricted to GitHub hosts, which is good; production should additionally constrain outbound network access and test Git redirect/proxy/config behavior in the actual worker environment.
5. **Untrusted evidence:** caller-supplied finding objects are rejected. Repository data and AI output remain untrusted; model prompt protections are not a guarantee of correct or safe output.
6. **Cleanup/isolation:** cleanup exceptions are suppressed; worker/container isolation and a cleanup-failure signal/alert are absent.
7. **Cookie/auth boundary:** production must provide HTTPS origins, `SESSION_COOKIE_SECURE=true`, and a strong OAuth state signing secret. Logout validates Origin/Fetch Metadata. Hosted cookie/CORS deployment behavior remains untested.
8. **Operational recovery:** user-initiated deletion exists, but automated retention, encrypted backups, restore drills, and a security audit trail do not.
9. **AI privacy and abuse:** selection-time disclosure and conservative per-user/workspace spend reservations exist, but a full published retention/consent policy, provider audit trail, and live billing verification remain outstanding.

The OAuth flow was tested with a mocked provider boundary only. The live GitHub OAuth provider, deployed network posture, secret manager, hosted PostgreSQL migration, hosted CI execution, and production host were **not tested**. GitHub OAuth is not OIDC, so OIDC nonce validation is not applicable; state and PKCE are used instead.

## 2. Recommended production architecture

### 2.1 Preserve and extend the current stack

| Area | Recommendation | Fit to existing project |
|---|---|---|
| Frontend | Keep React, Vite, and the existing dashboard sections. Add routing/auth/history screens incrementally. | Existing UI and API client can be extended; no rewrite needed. |
| API | Keep Python/FastAPI and existing analyzer/service modules. Add explicit auth, repository, analysis, and job resource boundaries. | Preserves current analysis engine and request schemas where appropriate. |
| Database | PostgreSQL + SQLAlchemy 2 + Alembic. Use synchronous SQLAlchemy initially to match current synchronous GitPython/services; move to async DB access only if measured need justifies it. | Adds missing persistence without changing the analysis algorithms. |
| Account authentication | Use GitHub OAuth via Authlib for account identity, with secure server-side sessions. This identity connection is separate from the later GitHub App repository installation. Do not build password/reset/MFA flows in this milestone. | Keeps account identity distinct from repository authorization. |
| GitHub repository access | GitHub App installations, repository selection, and short-lived installation tokens with minimum permissions. | Supports both public and private repositories without embedding tokens in clone URLs or browser storage. |
| Background processing | PostgreSQL is the source of truth for job state; Celery + managed Redis is a reasonable first queue because of retry/routing support. Run analysis in isolated worker containers with hard resource and network limits. | Current synchronous GitPython operations naturally move to workers. |
| AI | Retain `BaseAIProvider` and Gemini implementation. Require Gemini for production explanations; disable Mock outside tests/development. Keep deterministic drift status authoritative and validate all AI output. | Reuses existing provider design while removing production mock paths. |
| Hosting | Managed static frontend, managed API containers, managed worker containers, managed PostgreSQL, managed Redis, custom HTTPS domain, and centralized secret storage/monitoring. | Adds deployment services not currently present. |

The exact cloud/vendor is an implementation decision for a later deployment milestone. Do not put database credentials, GitHub App private keys, installation tokens, Gemini keys, or session secrets in frontend variables or source control.

### 2.2 Multi-user and future multi-tenant data model

Build an owner boundary in the first persistence migration:

- `users`: stable internal ID, verified email/profile metadata, status, timestamps.
- `user_identities`: unique issuer/subject mapping. GitHub numeric account ID is the stable subject; email is not used to auto-link accounts.
- `sessions`: opaque random session identifier stored as a hash, user ID, creation/expiry/revocation metadata.
- `workspaces`: initially one personal workspace per user; designed to support teams later.
- `workspace_members`: workspace/user membership and role. Do not expose team administration until its authorization semantics are tested.
- `github_installations`: GitHub installation ID, owning GitHub account metadata, installation state, and internal owner/workspace relationship. Do not store long-lived plaintext access tokens.
- `repositories`: GitHub numeric repository ID, installation ID, owner/name, visibility, default branch, last-synced metadata. Treat names/URLs as mutable labels; use GitHub IDs as stable keys.
- `workspace_repositories` or equivalent grants: which workspace can use a repository, derived from the installation and current GitHub installation repository selection.
- `analyses`: workspace/user creator, repository ID, base/head SHA or PR number, lifecycle status, timestamps, options, provider/model, errors safe for users, and deletion/retention metadata.
- `analysis_findings`: analysis ID, deterministic finding data/evidence, status, severity, confidence, and optional AI output. Keep only the evidence needed for history; avoid storing whole source trees.
- `analysis_events` or audit records: important authorization, installation, analysis, cancellation, and deletion events without storing secrets.

Every read/write query must be scoped by the authenticated user and authorized workspace/repository. Derive the actor from the server-validated session, never from request JSON. Enforce repository access from the GitHub App installation at time of use (and define behavior when access is revoked). Add PostgreSQL row-level security only as defense in depth; it does not replace correct service-layer authorization. Use composite foreign keys or equivalent constraints to prevent cross-workspace references.

### 2.3 Product workflow

1. The user opens the hosted DocGuard site over HTTPS.
2. The user signs in or creates an account; the API establishes a secure server-side session.
3. The user chooses **Connect GitHub** and installs/authorizes the DocGuard GitHub App for selected repositories.
4. The backend validates the callback state and records the installation/account relationship; the UI lists only repositories accessible to that user/workspace.
5. The user selects a repository from the authorized list, not an arbitrary untrusted clone URL.
6. The user selects a pull request or base/head commits; the server resolves them to immutable SHAs and records that selection.
7. The API creates an analysis record and enqueues it. A worker obtains short-lived, least-privilege GitHub access and securely retrieves the necessary Git data.
8. The worker applies resource/time limits, runs the existing AST, Markdown, mapping, and deterministic drift pipeline without executing repository code.
9. The analysis/findings are stored under the authorized workspace and repository. Status and progress are available through an authorized job endpoint.
10. Gemini receives only the minimum required evidence after the user’s provider/privacy policy is applied. Its structured output is validated; it cannot change deterministic findings.
11. The user reviews evidence and a proposal. No repository files are changed automatically in the MVP.
12. The user can revisit history; access is rechecked against current workspace membership and GitHub installation permissions.
13. Users can delete analyses and disconnect GitHub. Retention and deletion must also cover worker scratch data, cached tokens, logs, and backups according to the published policy.

## 3. Phased implementation roadmap

Complexity is relative to the existing codebase: **S** small, **M** medium, **L** large, **XL** very large. Each phase should be independently testable and separately reviewable.

### Milestone 1 — Production audit and architecture

- **Objective/functionality:** Confirm this roadmap, MVP scope, data classification/retention, threat model, tenant boundary, GitHub permissions, authentication approach, and deployment topology. Preserve the current analyzer and explicitly mark the demo fixture and Mock provider as development/test-only for the future production profile.
- **Likely files:** `docs/PRODUCTION_ROADMAP.md`, `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, `README.md`, and a future architecture-decision-record directory if the team wants separately versioned decisions. This roadmap supplies the initial audit; implementation decisions still require product approval.
- **Database changes:** None.
- **API changes:** None.
- **Security requirements:** Define assets, trust boundaries, abuse cases, token lifecycle, repository-data retention, user deletion, and launch-blocking controls before adding private data.
- **Tests/acceptance:** Review/approve threat model and architecture; produce traceable decisions for identity provider, GitHub App permissions, data retention, queue, and hosting. No application test result is claimed for this documentation milestone.
- **Credentials/external services:** None required.
- **Dependencies:** None.
- **Complexity:** **S**.

### Milestone 2 — Authentication and PostgreSQL persistence

**Implementation status:** Implemented locally; PostgreSQL CI is configured but its hosted run remains unverified. At this milestone's completion, 97 backend tests and 6 frontend tests passed, the frontend production build passed, and SQLite migration upgrade/downgrade/re-upgrade plus model parity passed. The later Milestone 4 full-suite results are recorded below.

- **Objective/functionality:** Add real user accounts and secure sessions. Add migrations and repository/data-access patterns. Establish a personal workspace/owner boundary from the first stored record. Persist only product/account metadata at this stage; do not yet enable unscoped private repository access.
- **Implemented files:** `backend/app/config.py`; `backend/app/db/`; `backend/app/models/`; `backend/app/auth/`; `backend/app/api/auth.py`; `backend/app/schemas/auth.py`; `backend/alembic.ini`; `backend/alembic/`; `backend/requirements.txt`; `backend/.env.example`; protected analysis routers; `frontend/src/api/auth.js`; credentialed `frontend/src/api/health.js`; sign-in/account UI; tests and CI; setup/security documentation.
- **Database changes:** Added users, GitHub identities, hashed sessions, personal workspaces, membership roles, OAuth state hashes, and login rate-limit buckets. No analysis, repository, or team-management data is stored.
- **API changes:** Added `GET /api/auth/status`, `GET /api/auth/login`, `GET /api/auth/callback`, `GET /api/auth/me`, and `POST /api/auth/logout`. Protected the existing repository, analysis, and AI routes with an authenticated-principal dependency; `/` and `/api/health` remain public.
- **Identity protocol decision:** GitHub OAuth via Authlib, separate from future GitHub App repository authorization. Authlib validates state and PKCE is enabled; GitHub OAuth does not provide an OIDC ID-token nonce, so OIDC nonce validation is not applicable and is not claimed.
- **Security requirements:** Production requires HTTPS frontend/callback origins and Secure cookies. The persistent HttpOnly session cookie holds an opaque random token; only its hash is stored. Re-login rotates the browser session, expiration is server-enforced, logout revokes, logout requests require exact trusted Origin/Fetch Metadata, CORS is restricted, and OAuth initiation is throttled. Provider tokens are used only during callback and never stored or returned.
- **Tests/acceptance:** Locally verified callback state and transaction-cookie handling, PKCE URL, one-time state/expiry rejection, cookie flags, session hashing/expiry/rotation/logout, origin rejection, current-user isolation against forged IDs, unauthenticated route denial, login throttling, and no token leakage. At M2 completion, backend: **97 passed**; frontend: **6 passed**; production build and SQLite migration upgrade/downgrade/re-upgrade/schema parity: **passed**. The later M4 full-suite run is recorded below. Live GitHub OAuth and hosted PostgreSQL/CI were **not tested**.
- **Remaining boundary:** Authentication and GitHub App access now protect repository operations, and persisted drift analyses are workspace scoped. The direct repository-comparison, standalone AST, and standalone documentation endpoints still return transient results rather than history records; team administration and organization-level workspaces are not implemented.
- **Credentials/external services:** PostgreSQL and a GitHub OAuth App client ID/secret with the exact callback URL. Keep secrets in a managed secret store; no credentials are included in this repository.
- **Dependencies:** Milestone 1 approval.
- **Complexity:** **L**.

### Milestone 3 — GitHub App integration and authorized repository catalog

- **Implementation status:** Implemented locally; GitHub behavior is mocked in tests and requires a separately configured GitHub App. At M3 completion, 106 backend tests and 7 frontend tests passed, along with the frontend production build. Later M4 verification is recorded below.
- **Implemented functionality:** User-bound installation initiation and callbacks; installation verification against the signed-in GitHub identity; workspace-scoped public/private repository catalog; short-lived installation tokens; authorized repository-ID analysis request contracts; open-PR metadata; signed, deduplicated uninstall/suspension/repository-removal webhook handling.
- **Implemented files:** `backend/app/auth/github_app.py`; `backend/app/services/github_app_service.py`; `backend/app/api/github_app.py`; `backend/app/models/github_app_installation.py`; `backend/app/models/authorized_repository.py`; `backend/app/models/github_app_state.py`; `backend/app/models/github_webhook_delivery.py`; `backend/alembic/versions/0002_github_app_repository_catalog.py`; repository/analysis request schemas and routers; `backend/.env.example`; `frontend/src/api/githubApp.js`; `frontend/src/components/AuthorizedRepositoryPicker.jsx`; `frontend/src/App.jsx`; and focused backend/frontend tests.
- **Database changes:** An additive migration adds GitHub App installations, workspace-scoped authorized repositories, hashed callback state, and webhook delivery deduplication. No long-lived installation token is persisted.
- **Security requirements:** Read-only permissions are expected; callback binds installation to the signed-in GitHub numeric identity; state is one-time and user-bound; repository IDs are workspace checked; tokens are short lived and not embedded in URLs; webhook signatures and body limits are checked; revocation deactivates records.
- **Tests/acceptance:** Local tests cover public/private catalog data, identity mismatch, cross-workspace denial, uninstall revocation, token expiry/redaction, rate-limit mapping, signed webhook and replay behavior. Live GitHub App callbacks, actual private repository cloning, hosted PostgreSQL migration, and hosted CI remain **not tested**.
- **Credentials/external services:** GitHub App ID, slug, client ID/secret, private key, webhook secret, and callback URLs. Setup placeholders are documented in the root README and `backend/.env.example`; no credentials are included.
- **Dependencies:** Milestone 2.
- **Complexity:** **L**.

### Milestone 4 — Persisted real analysis and production Gemini policy

- **Implementation status:** Implemented locally. Full backend suite: **112 passed, 0 failed, 0 skipped, 0 errors**. Frontend suite: **8 passed, 0 failed, 0 skipped**; production build passed. Migration upgrade/downgrade/re-upgrade and Alembic model parity passed against the SQLite fallback; `TEST_POSTGRES_URL` was not configured, so PostgreSQL migration behavior remains untested. Hosted CI, live GitHub App, and live Gemini also remain untested.
- **Implemented functionality:** `POST /api/analyze/drift` requires an authorized repository ID and full SHA-1 base/head SHAs, rechecks GitHub permission, runs the existing deterministic AST/Markdown/drift pipeline, and persists canonical commits, summary, and bounded evidence. The response includes `analysis_id`; `GET /api/analyses/{analysis_id}` returns workspace-scoped details after rechecking current repository access. AI requests use only an analysis ID and 1–10 stored finding IDs.
- **Implemented files:** `backend/app/models/analysis_record.py`; `backend/app/models/gemini_spend_reservation.py`; `backend/alembic/versions/0003_persisted_analysis_and_ai_budget.py`; `backend/app/services/analysis_service.py`; `backend/app/services/drift_analysis_service.py`; `backend/app/services/github_service.py`; `backend/app/api/analyses.py`; `backend/app/api/drift.py`; `backend/app/api/ai_explanations.py`; `backend/app/schemas/analysis.py`; `backend/app/schemas/drift.py`; `backend/app/schemas/ai_explanation.py`; `backend/app/config.py`; `backend/app/ai/`; frontend API/provider selection; focused backend tests; `.env.example`; README and architecture/security documentation.
- **Database changes:** Added workspace/repository-scoped `analyses` and `analysis_findings`, plus conservative Gemini spend reservation records. Database foreign keys bind each analysis to a repository in the same workspace. Full source trees and complete source files are not stored.
- **API changes:** Extended `/api/analyze/drift` to persist and return an analysis ID; added `GET /api/analyses/{analysis_id}`. `POST /api/analyze/explanations` rejects caller-supplied findings and loads selected evidence from the authorized analysis.
- **Security requirements:** Drift SHAs must be full; GitHub access is rechecked for analysis/detail/AI; Mock is disabled in production; provider calls have configured timeout/output caps; spend budgets/rates, prompt, request/finding count, clone size, tree, file, byte, evidence, and analysis time limits are enforced in application code. The UI discloses Gemini evidence processing. No OS-level worker isolation is claimed.
- **Tests/acceptance:** The full local backend suite passed **112/112** with no failures, skips, or errors. It covers SQLite migration upgrade/downgrade/re-upgrade and model parity, auth, workspace/IDOR boundaries, GitHub mocked integration, drift persistence, quota/spend reservations, Gemini timeout/policy, demo-interception, deterministic evaluation, and legacy analysis behavior. Frontend tests passed **8/8**, and `npm run build` succeeded. Live GitHub/Gemini, PostgreSQL, hosted CI, OS-level isolation, and deletion/retention behavior were not tested.
- **Credentials/external services:** GitHub App from Milestone 3; production Gemini API key/model plus operator-selected token rates and budgets; PostgreSQL. No credentials were invented or added to frontend configuration.
- **Dependencies:** Milestones 2 and 3.
- **Complexity:** **L**.

### Milestone 5 — Durable background processing

- **Implementation status:** Implemented locally using Celery + Redis; no live Redis, deployed worker, or hosted Beat process was available for runtime verification. PostgreSQL remains the source of truth.
- **Implemented functionality:** `POST /api/analyses` returns `202 Accepted` and the existing `/api/analyze/drift` path is an asynchronous compatibility alias. PostgreSQL stores queue/run/terminal states, attempt counts, progress, timestamps, safe error categories, cancellation, idempotency, dispatch leases, and scratch cleanup status. Celery task payloads contain the analysis UUID only. A periodic Beat task redispatches queued records and recovers stale workers. Worker authorization and repository access are rechecked before cloning. Retries are bounded to transient GitHub/network failures; polling and cancellation APIs are available.
- **Implemented files:** `backend/app/tasks/celery_app.py`; `backend/app/tasks/analysis_jobs.py`; `backend/app/models/analysis_record.py`; `backend/app/alembic/versions/0004_durable_analysis_jobs.py`; `backend/app/services/analysis_service.py`; `backend/app/services/github_app_service.py`; `backend/app/services/drift_analysis_service.py`; `backend/app/services/github_service.py`; `backend/app/api/analyses.py`; `backend/app/api/drift.py`; `backend/app/schemas/analysis.py`; frontend `health.js`, `App.jsx`, and `DriftFindingsSection.jsx`; Celery/Redis dependency and environment configuration; focused job tests.
- **Database changes:** Add job attempt/progress/cancel/heartbeat/dispatch/cleanup fields, queued timestamps, idempotency key hash, request fingerprint, unique idempotency constraint, and worker query indexes to `analyses`.
- **API changes:** Added `POST /api/analyses` (`202`), `GET /api/analyses/{id}/status`, and `POST /api/analyses/{id}/cancel`. Existing detail remains available at `GET /api/analyses/{id}`. The frontend polls status and fetches persisted findings on success; cancellation is cooperative.
- **Security requirements:** Redis URL configuration requires TLS and authentication in production and rejects local broker hostnames. The operator must supply private network policy, Redis persistence/no-eviction, and secret management. Tasks carry IDs only; workers recheck workspace membership and live repository access. Time limits and file bounds are application protections, not OS/container CPU, memory, filesystem, or egress isolation. A currently running bounded Git command may finish before cooperative cancellation is observed.
- **Tests/acceptance:** Local tests cover 202 job creation, idempotency conflicts/replay, workspace IDOR, trusted-origin cancellation, duplicate claims, bounded exponential retry, stale worker recovery, broker payload contents, broker outage safe state, cleanup status/orphan cleanup, authorization recheck, and end-to-end demo drift through the worker function. SQLite migrations pass. Actual Redis delivery, PostgreSQL locking, worker process crash under a broker, and runtime isolation were not tested.
- **Credentials/external services:** Private authenticated Redis with TLS; worker process deployment; existing GitHub App, PostgreSQL and Gemini configuration. No credentials were invented.
- **Dependencies:** Milestones 2–4.
- **Complexity:** **L–XL**.

### Milestone 6 — Complete authenticated production dashboard and history

- **Implementation status:** Implemented locally. Backend: **134 passed, 0 failed, 0 skipped, 0 errors**. Frontend: **12 passed, 0 failed, 0 skipped**; Vite production build and `git diff --check` passed. Live browser login, GitHub installation/private repository, PostgreSQL, Redis/worker, and Gemini journeys remain **not tested** because they require configured external services and credentials.
- **Implemented functionality:** Public landing/sign-in and protected dashboard routes; current-session/logout handling; authorized GitHub repository and PR selection; persisted job polling/progress; findings/evidence and AI explanation UI; paginated workspace history; permission-revocation redaction; safe retry of classified retryable failures/cancelled jobs; terminal-analysis deletion with spend records retained for accounting.
- **Implemented files:** `frontend/src/App.jsx`; `frontend/src/auth/AuthContext.jsx`; `frontend/src/AnalysisPage.jsx`; `frontend/src/pages/AnalysisHistoryPage.jsx`; `frontend/src/pages/AnalysisDetailPage.jsx`; account/sign-in/sidebar/repository picker components; `frontend/src/api/analyses.js`; `backend/app/api/analyses.py`; `backend/app/services/analysis_service.py`; `backend/app/schemas/analysis.py`; migration `backend/alembic/versions/0005_preserve_spend_reservations.py`; backend/frontend tests; README and architecture/security/testing documentation.
- **Database changes:** Reuses Milestones 2–5 tables. Migration 0005 makes spend-reservation references nullable with `ON DELETE SET NULL`; deleting an analysis preserves spend amounts while deleting findings and analysis metadata.
- **API changes:** Added paginated `GET /api/analyses`, retry `POST /api/analyses/{id}/retry`, and deletion `DELETE /api/analyses/{id}`. Listing/detail/retry/delete are workspace-scoped and recheck live repository access. History responses suppress repository identity, commit SHAs, and finding counts for revoked access. Retry and delete require trusted Origin; retry uses normal quota enforcement and delete rejects active jobs.
- **Security requirements:** Frontend uses server-side HttpOnly cookie sessions and stores no session token in localStorage. Backend authorization is authoritative. Repository revocation redacts history details and prevents detail/mutation. AI explanations are loaded from persisted analysis/finding IDs. Deletion retains spend accounting.
- **Tests/acceptance:** Local tests cover API pagination and workspace isolation, revoked-access redaction, retry eligibility, Origin/authorization checks, terminal-only deletion, and spend-accounting retention; frontend tests cover session/API contracts and request cancellation. Full live browser flow, component-level rendered-state testing, real provider callbacks, and deployed-worker behavior were not tested.
- **Remaining boundary:** User-initiated deletion is implemented; automated retention, teams, organization-level roles, export, backup deletion, and full production deployment remain future work.
- **Credentials/external services:** Real GitHub OAuth App/GitHub App, PostgreSQL, authenticated Redis/Celery worker/Beat, and Gemini are required for live end-to-end verification; no credentials were invented.
- **Dependencies:** Milestones 2–5.
- **Complexity:** **L**.

### Milestone 7 — Opt-in GitHub pull-request automation

- **Objective/functionality:** Offer a user-initiated or explicitly configured PR review workflow that analyzes PR base/head commits and posts a concise, idempotent check/comment linking to findings. Start with read-only analysis and review comments; do not modify documentation or push commits automatically.
- **Likely files:** New proposed GitHub webhook/event handlers, PR service, comment formatter, delivery/idempotency store, webhook configuration, job/task routing, frontend installation/PR settings.
- **Database changes:** Add webhook delivery IDs, PR analysis association, comment/check IDs, idempotency keys, and opt-in installation/repository settings.
- **API changes:** Webhook receiver, PR analysis status, and explicit enable/disable/configuration routes; use GitHub App permissions only for required check/comment writing, separately from initial read-only permissions.
- **Security requirements:** Verify webhook HMAC before parsing/processing; deduplicate deliveries; avoid trusting webhook branch/head values without fetching/validating them; protect against replay and stale events; honor installation revocation; constrain comment content and rate; never post secrets or full source excerpts; no automatic repository write/update.
- **Tests/acceptance:** Valid/invalid signatures, replay/deduplication, out-of-order events, changed force-push head SHA, permission revocation, retries, comment size/sanitization, and proof the integration does not push commits or edit repository files.
- **Credentials/external services:** GitHub App webhook secret and approved additional permissions; public HTTPS webhook URL.
- **Dependencies:** Milestones 3–6.
- **Complexity:** **L–XL**.

### Milestone 8 — Security hardening, deployment, and public launch

- **Objective/functionality:** Productionize operations: managed frontend/API/database/Redis/worker, custom domain and TLS, secrets, migrations, backups, observability, support, privacy/retention controls, and launch gates.
- **Likely files:** Add production container/build configuration, deployment manifests/IaC, CI/CD workflow(s), health/readiness endpoints, structured logging/metrics, backup/restore runbooks, `.env.example`, `docs/SECURITY.md`, `docs/ARCHITECTURE.md`, incident/operations docs. Exact files depend on the hosting choice.
- **Database changes:** Production migration/backups/restore strategy, retention jobs, and (if adopted) PostgreSQL row-level security and audit records. Test restoration into an isolated environment.
- **API changes:** Readiness/liveness split, versioned API strategy if needed, explicit rate-limit responses, request IDs, admin health/metrics not exposed publicly, and consistent safe errors.
- **Security requirements:** HTTPS/HSTS, locked CORS, security headers, CSRF, rate limits and abuse detection, secret rotation, egress policy, dependency/container scans, private worker networking, encrypted backups, least-privilege service identities, incident response, data export/deletion and retention enforcement.
- **Tests/acceptance:** Restore from backup; deploy/rollback and migration tests; load/soak and rate-limit tests; resource exhaustion tests; security review/penetration test; TLS/CORS/cookie checks; alert delivery; verify no secrets in artifacts/logs; staged beta with incident and support process.
- **Credentials/external services:** Managed frontend/backend/PostgreSQL/Redis/worker services, domain/DNS/TLS, secret manager, monitoring/alerting, backup storage, identity provider, GitHub App, Gemini.
- **Dependencies:** Milestones 2–7; can begin deployment experiments earlier, but launch gates depend on the full security and operations checklist.
- **Complexity:** **XL**.

## 4. MVP launch gates

Do not announce a public SaaS launch until all of these are true:

1. Every user-facing route requires a session or is explicitly public and safe; tenant and repository authorization tests prove cross-user access is denied.
2. Private repositories are accessed only through a valid, user-authorized GitHub App installation; tokens are short-lived and never placed in URLs or browser storage.
3. No production workflow accepts arbitrary caller-supplied findings or uses Mock AI; Gemini use is disclosed, budgeted, rate-limited, and failures are surfaced.
4. Repository ingestion has pre-download and in-worker resource/time limits; clone/analysis/cancellation cleanup is observable and failure-tested.
5. Analyses are persisted under the correct owner/workspace, history access is scoped, and deletion/retention behavior is documented and tested.
6. PostgreSQL/Redis/worker deployment, migrations, backups, restore, monitoring, TLS, secret rotation, and incident response have been exercised in a staging environment.
7. CI covers backend, frontend, migrations, authorization, job behavior, and security-relevant regressions. Hosted CI must actually pass before claiming it does.

## 5. Recommended next step

Milestones 1–6 are implemented locally. The next planned code milestone is **Milestone 7: opt-in GitHub pull-request automation**, after the user approves that scope. Do not start it as part of this milestone. Before any public launch, complete Milestone 8's deployment/security gates and verify live OAuth, private repository access, PostgreSQL, Redis/workers, Gemini, backups, and runtime isolation.
