"""
Controlled Demonstration Git Repository Builder for DocGuard (Milestone 7).

Builds a deterministic, reproducible local Git repository on disk with two
real commits (`base_commit` and `head_commit`) specifically designed to
demonstrate DocGuard's end-to-end capabilities:
1. Genuine documentation drift cases:
   - RULE_A_CHANGED_DEFAULT: `create_user(username, role='user')` -> `role='admin'`
     while `docs/api.md` still states `"The default role is user."`
   - RULE_B_REMOVED_OR_RENAMED_PARAMETER: `connect_gateway(host, port)` -> `connect_gateway(host)`
     while `docs/api.md` still says `"Pass the port parameter to connect_gateway(host, port)."`
   - RULE_C_ADDED_REQUIRED_PARAMETER: `send_receipt(order_id)` -> `send_receipt(order_id, recipient_email)`
     while `README.md` still shows `"Call send_receipt(order_id) to email a receipt."`
2. Unrelated code changes that must NOT create false-positive drift findings:
   - Body-only implementation change in `calculate_platform_fee(amount)`
   - Optional parameter addition `timeout: int = 30` in `sync_ledger_entries(batch_id, timeout=30)`
   - Internal helper `_hash_audit_payload(raw)` modified without any documentation reference
"""

import os
import tempfile
from typing import Dict

import git

from app.services.github_service import _remove_readonly

DEMO_REPO_OWNER = "docguard-demo"
DEMO_REPO_NAME = "billing-api"
DEMO_REPO_CANONICAL_URL = f"https://github.com/{DEMO_REPO_OWNER}/{DEMO_REPO_NAME}"
DEMO_REPO_CLONE_URL = f"https://github.com/{DEMO_REPO_OWNER}/{DEMO_REPO_NAME}.git"

_DEMO_DIR_PATH = os.path.join(
    tempfile.gettempdir(), "docguard_controlled_demo_billing_api"
)


def ensure_demo_git_repository() -> Dict[str, str]:
    """
    Idempotently create (or reuse) the deterministic 2-commit demonstration Git
    repository on disk and return its path and commit SHAs.
    """
    git_dir = os.path.join(_DEMO_DIR_PATH, ".git")
    if os.path.exists(git_dir):
        try:
            existing = git.Repo(_DEMO_DIR_PATH)
            commits = list(existing.iter_commits("main", max_count=5))
            if len(commits) == 2:
                head_sha = commits[0].hexsha
                base_sha = commits[1].hexsha
                existing.close()
                return {
                    "path": _DEMO_DIR_PATH,
                    "base_commit": base_sha,
                    "head_commit": head_sha,
                }
            existing.close()
        except Exception:
            pass

    if os.path.exists(_DEMO_DIR_PATH):
        import shutil

        shutil.rmtree(_DEMO_DIR_PATH, onerror=_remove_readonly)

    os.makedirs(os.path.join(_DEMO_DIR_PATH, "src"), exist_ok=True)
    os.makedirs(os.path.join(_DEMO_DIR_PATH, "docs"), exist_ok=True)

    repo = git.Repo.init(_DEMO_DIR_PATH, initial_branch="main")
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "DocGuard Demo Engineer")
        cw.set_value("user", "email", "demo@docguard.local")

    # -----------------------------------------------------------------------
    # COMMIT 1 (Base Commit): Code and documentation are 100% synchronized
    # -----------------------------------------------------------------------
    base_billing_py = "\n".join(
        [
            '"""Core billing and account management functions."""',
            "",
            "def create_user(username: str, role: str = 'user') -> dict:",
            '    """Create a user record with the configured role."""',
            "    return {'username': username, 'role': role}",
            "",
            "def connect_gateway(host: str, port: int) -> bool:",
            '    """Connect to the payment gateway host and port."""',
            "    return bool(host and port > 0)",
            "",
            "def send_receipt(order_id: str) -> bool:",
            '    """Dispatch a payment receipt for the given order."""',
            "    return bool(order_id)",
            "",
            "def calculate_platform_fee(amount: float) -> float:",
            '    """Compute the 2.5% platform transaction fee."""',
            "    return round(amount * 0.025, 2)",
            "",
            "def sync_ledger_entries(batch_id: str) -> int:",
            '    """Synchronize a ledger batch and return processed count."""',
            "    return len(batch_id)",
            "",
            "def _hash_audit_payload(raw: str) -> str:",
            "    return f'v1:{raw}'",
            "",
        ]
    )

    readme_md = "\n".join(
        [
            "# Billing API Service",
            "",
            "Payment gateway and user provisioning library for e-commerce checkout.",
            "",
            "## Installation",
            "",
            "Run `pip install billing-api` inside your virtual environment.",
            "",
            "## send_receipt()",
            "",
            "Call `send_receipt(order_id)` to email a receipt after checkout completes.",
            "",
            "## sync_ledger_entries()",
            "",
            "Call `sync_ledger_entries(batch_id)` to synchronize a ledger batch.",
            "",
        ]
    )

    docs_api_md = "\n".join(
        [
            "# API Reference",
            "",
            "## create_user()",
            "",
            "The `create_user` function provisions an account in `src/billing.py`. The default `role` is `user`.",
            "",
            "## connect_gateway()",
            "",
            "Pass the `port` parameter to `connect_gateway(host, port)` to open a gateway socket.",
            "",
            "## calculate_platform_fee()",
            "",
            "Use `calculate_platform_fee(amount)` to calculate the platform fee for an order.",
            "",
        ]
    )

    with open(
        os.path.join(_DEMO_DIR_PATH, "src", "billing.py"), "w", encoding="utf-8"
    ) as f:
        f.write(base_billing_py)
    with open(os.path.join(_DEMO_DIR_PATH, "README.md"), "w", encoding="utf-8") as f:
        f.write(readme_md)
    with open(
        os.path.join(_DEMO_DIR_PATH, "docs", "api.md"), "w", encoding="utf-8"
    ) as f:
        f.write(docs_api_md)

    repo.index.add(["src/billing.py", "README.md", "docs/api.md"])
    c_base = repo.index.commit(
        "Initial release: synchronized billing API and documentation"
    )

    # -----------------------------------------------------------------------
    # COMMIT 2 (Head Commit): Code changes introduce 3 genuine drift items
    # and 3 benign/unrelated changes while Markdown docs remain unchanged
    # -----------------------------------------------------------------------
    head_billing_py = "\n".join(
        [
            '"""Core billing and account management functions."""',
            "",
            "def create_user(username: str, role: str = 'admin') -> dict:",
            '    """Create a user record with the configured role."""',
            "    return {'username': username, 'role': role}",
            "",
            "def connect_gateway(host: str) -> bool:",
            '    """Connect to the payment gateway host using standard TLS port."""',
            "    return bool(host)",
            "",
            "def send_receipt(order_id: str, recipient_email: str) -> bool:",
            '    """Dispatch a payment receipt to recipient_email for the given order."""',
            "    return bool(order_id and recipient_email)",
            "",
            "def calculate_platform_fee(amount: float) -> float:",
            '    """Compute the platform transaction fee with minimum floor."""',
            "    fee = amount * 0.025",
            "    return round(max(0.50, fee), 2)",
            "",
            "def sync_ledger_entries(batch_id: str, timeout: int = 30) -> int:",
            '    """Synchronize a ledger batch with an optional timeout."""',
            "    return len(batch_id) if timeout > 0 else 0",
            "",
            "def _hash_audit_payload(raw: str, salt: str = 'v2') -> str:",
            "    return f'{salt}:{raw}'",
            "",
        ]
    )

    with open(
        os.path.join(_DEMO_DIR_PATH, "src", "billing.py"), "w", encoding="utf-8"
    ) as f:
        f.write(head_billing_py)

    repo.index.add(["src/billing.py"])
    c_head = repo.index.commit(
        "Update role default to admin, remove gateway port arg, require recipient_email"
    )

    base_sha = c_base.hexsha
    head_sha = c_head.hexsha
    repo.close()

    return {
        "path": _DEMO_DIR_PATH,
        "base_commit": base_sha,
        "head_commit": head_sha,
    }
