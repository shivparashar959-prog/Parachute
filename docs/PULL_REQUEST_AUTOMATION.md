# GitHub pull request automation

Pull request automation is repository-specific and defaults to off. A workspace
owner must explicitly enable it for each authorized repository. The signed
GitHub webhook receiver verifies `X-Hub-Signature-256` before decoding the
payload and deduplicates delivery IDs in the database.

For each supported open-PR event, DocGuard fetches the current pull request
through a repository-scoped installation token and uses the API-returned base
and head SHAs. Webhook SHAs and branch names are not used to select analysis
inputs. Analyses are persisted before dispatch through the durable job
dispatcher; repeated delivery and same-SHA updates reuse existing results.

The GitHub App needs repository metadata/content read access and **Checks:
write**. The app must subscribe to `pull_request`, `installation`, and
`installation_repositories` webhook events. Check Run summaries are sanitized,
bounded, and link to the authenticated DocGuard analysis detail. Automation
does not edit repository files or documentation, and does not add billing or
team administration.

Configure the App ID, slug, client credentials, private key, and webhook secret
using the deployment's secret manager. Keep the webhook endpoint reachable over
HTTPS. Do not copy real values into `.env.example`, source control, or issue/PR
text. Live GitHub App installation, permission revocation, and webhook delivery
must be verified in the target environment before enabling this feature.
