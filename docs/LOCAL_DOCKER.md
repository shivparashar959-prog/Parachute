# Local Docker Compose

This Compose configuration is for local development only. It is not a production
deployment: it uses local PostgreSQL and Redis containers, plain HTTP, and
development-mode settings. Do not expose it directly to the internet.

Create an untracked `.env` file at the repository root with URL-safe, local-only
passwords (do not commit it):

```dotenv
DOCGUARD_DB_PASSWORD=replace-with-a-local-password
DOCGUARD_REDIS_PASSWORD=replace-with-another-local-password
DOCGUARD_DATABASE_URL=postgresql+psycopg://docguard:replace-with-a-local-password@postgres:5432/docguard
DOCGUARD_CELERY_BROKER_URL=redis://:replace-with-another-local-password@redis:6379/0
```

Keep the passwords URL-safe or percent-encode characters that have special
meaning in URLs. Start the stack with `docker compose up --build`; the migration
service upgrades the database before the API and worker start. The frontend is
available at `http://localhost:8080`. PostgreSQL and Redis are not published to
the host.

Local OAuth, GitHub App webhook delivery, HTTPS, managed databases, secret
rotation, backups, restore drills, monitoring, and staging/rollback are not
configured by this Compose file. Configure those separately before any hosted
deployment. Never place production secrets in this `.env` file.
