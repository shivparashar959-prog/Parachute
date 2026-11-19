"""
Automated tests for Milestone 2: GitHub Repository Integration.
Uses temporary local Git repository fixtures and mocked network errors so the
test suite runs deterministically offline without live GitHub dependencies.
"""

import os
import shutil
import tempfile
from typing import Any, Dict

from fastapi.testclient import TestClient
import git
from git import GitCommandError
import pytest

from app.main import app
from app.services import github_service

client = TestClient(app)


@pytest.fixture()
def local_git_fixture():
    """
    Create a temporary local Git repository with two commits covering:
    - added file
    - modified file
    - deleted file
    - renamed file
    """
    repo_dir = tempfile.mkdtemp(prefix="docguard_test_fixture_")
    repo = git.Repo.init(repo_dir, initial_branch="main")

    with repo.config_writer() as cw:
        cw.set_value("user", "name", "DocGuard Tester")
        cw.set_value("user", "email", "tester@docguard.local")

    # Commit 1: Initial files
    readme_path = os.path.join(repo_dir, "README.md")
    app_path = os.path.join(repo_dir, "app.py")
    delete_me_path = os.path.join(repo_dir, "legacy.py")
    rename_src_path = os.path.join(repo_dir, "old_name.py")

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write("# Sample Project\nInitial documentation.\n")
    with open(app_path, "w", encoding="utf-8") as f:
        f.write("def calculate(x):\n    return x + 1\n")
    with open(delete_me_path, "w", encoding="utf-8") as f:
        f.write("# Deprecated module\nLEGACY = True\n")
    with open(rename_src_path, "w", encoding="utf-8") as f:
        f.write(
            "def shared_helper():\n"
            "    '''Helper function with enough lines for git rename detection.'''\n"
            "    value = 42\n"
            "    return value * 2\n"
        )

    repo.index.add(["README.md", "app.py", "legacy.py", "old_name.py"])
    commit_1 = repo.index.commit("Initial commit with base files")

    # Commit 2: Modify app.py, add feature.py, delete legacy.py, rename old_name.py -> new_name.py
    with open(app_path, "w", encoding="utf-8") as f:
        f.write("def calculate(x, step=2):\n    return x + step\n")

    feature_path = os.path.join(repo_dir, "feature.py")
    with open(feature_path, "w", encoding="utf-8") as f:
        f.write("def new_feature():\n    return 'enabled'\n")

    repo.index.remove(["legacy.py"], working_tree=True)

    rename_dst_path = os.path.join(repo_dir, "new_name.py")
    os.rename(rename_src_path, rename_dst_path)
    repo.index.remove(["old_name.py"])
    repo.index.add(["app.py", "feature.py", "new_name.py"])
    commit_2 = repo.index.commit("Add feature, modify calculate, remove legacy, rename helper")

    fixture_info: Dict[str, Any] = {
        "path": repo_dir,
        "repo": repo,
        "commit_1": commit_1.hexsha,
        "commit_2": commit_2.hexsha,
    }

    yield fixture_info

    try:
        repo.close()
    except Exception:
        pass
    shutil.rmtree(repo_dir, onerror=github_service._remove_readonly)


# ---------------------------------------------------------------------------
# 1. URL & Security Validation Tests
# ---------------------------------------------------------------------------


def test_valid_github_url_parsing():
    """Verify valid public HTTPS GitHub URLs are parsed and normalized properly."""
    owner, name, canonical, clone = github_service.parse_and_validate_github_url(
        "https://github.com/pallets/flask.git"
    )
    assert owner == "pallets"
    assert name == "flask"
    assert canonical == "https://github.com/pallets/flask"
    assert clone == "https://github.com/pallets/flask.git"


@pytest.mark.parametrize(
    "invalid_url",
    [
        "",
        "   ",
        "http://github.com/pallets/flask",  # HTTP instead of HTTPS
        "git@github.com:pallets/flask.git",  # SSH URL
        "file:///C:/Users/Dell/Desktop/DocGuard",  # Local file scheme
        "C:\\Users\\Dell\\Desktop\\DocGuard",  # Windows local path
        "/etc/passwd",  # POSIX local path
        "https://github.com/pallets/../../etc/passwd",  # Path traversal
        "https://user:secret@github.com/pallets/flask",  # Embedded credentials
        "https://github.com:8443/pallets/flask",  # Non-standard port
        "https://github.com/pallets",  # Missing repository name
        "https://github.com/pallets/flask/tree/main",  # Extra path segments
        "https://github.com/pallets/flask?tab=readme",  # Query parameters
    ],
)
def test_reject_invalid_or_unsafe_urls(invalid_url: str):
    """Verify malformed, non-HTTPS, local path, and traversal URLs return HTTP 400."""
    response = client.post(
        "/api/repositories/inspect",
        json={"repository_url": invalid_url},
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "non_github_url",
    [
        "https://gitlab.com/owner/repo",
        "https://bitbucket.org/owner/repo",
        "https://evilgithub.com/owner/repo",
        "https://github.com.attacker.tld/owner/repo",
        "https://localhost/owner/repo",
        "https://127.0.0.1/owner/repo",
    ],
)
def test_reject_non_github_domains(non_github_url: str):
    """Verify non-GitHub domains and internal hosts are strictly rejected."""
    response = client.post(
        "/api/repositories/inspect",
        json={"repository_url": non_github_url},
    )
    assert response.status_code == 400
    assert "github.com" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 2. Repository Inspection & Commit Retrieval Tests
# ---------------------------------------------------------------------------


def test_inspect_repository_retrieves_commits(monkeypatch, local_git_fixture):
    """Verify POST /api/repositories/inspect returns owner, name, branch, and real commits."""
    monkeypatch.setattr(
        github_service,
        "_resolve_clone_source",
        lambda _url: local_git_fixture["path"],
    )

    response = client.post(
        "/api/repositories/inspect",
        json={"repository_url": "https://github.com/octocat/Sample-Repo"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["owner"] == "octocat"
    assert data["name"] == "Sample-Repo"
    assert data["default_branch"] == "main"
    assert len(data["commits"]) == 2

    latest = data["commits"][0]
    older = data["commits"][1]
    assert latest["sha"] == local_git_fixture["commit_2"]
    assert latest["short_sha"] == local_git_fixture["commit_2"][:7]
    assert "Add feature" in latest["message"]
    assert latest["author"] == "DocGuard Tester"
    assert latest["timestamp"]

    assert older["sha"] == local_git_fixture["commit_1"]
    assert "Initial commit" in older["message"]


def test_repository_not_found_handling(monkeypatch):
    """Verify missing or private GitHub repositories return HTTP 404."""
    def fake_clone_from(*args, **kwargs):
        raise GitCommandError("git clone", 128, stderr="remote: Repository not found.")

    monkeypatch.setattr(git.Repo, "clone_from", fake_clone_from)

    response = client.post(
        "/api/repositories/inspect",
        json={"repository_url": "https://github.com/octocat/nonexistent-repo-xyz"},
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_network_error_handling(monkeypatch):
    """Verify network failures or DNS timeouts return HTTP 502 with a safe message."""
    def fake_clone_from(*args, **kwargs):
        raise GitCommandError(
            "git clone",
            128,
            stderr="fatal: unable to access 'https://github.com/a/b.git/': Could not resolve host: github.com",
        )

    monkeypatch.setattr(git.Repo, "clone_from", fake_clone_from)

    response = client.post(
        "/api/repositories/inspect",
        json={"repository_url": "https://github.com/octocat/Hello-World"},
    )
    assert response.status_code == 502
    assert "unable to connect" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 3. Commit Comparison (Added, Modified, Deleted, Renamed Files) Tests
# ---------------------------------------------------------------------------


def test_compare_commits_detects_added_modified_deleted_renamed(
    monkeypatch, local_git_fixture
):
    """Verify POST /api/repositories/compare classifies all 4 change types and returns diffs."""
    monkeypatch.setattr(
        github_service,
        "_resolve_clone_source",
        lambda _url: local_git_fixture["path"],
    )

    response = client.post(
        "/api/repositories/compare",
        json={
            "repository_url": "https://github.com/octocat/Sample-Repo",
            "base_commit": local_git_fixture["commit_1"],
            "head_commit": local_git_fixture["commit_2"],
        },
    )
    assert response.status_code == 200
    data = response.json()

    assert data["base_commit"] == local_git_fixture["commit_1"]
    assert data["head_commit"] == local_git_fixture["commit_2"]
    assert data["total_changed_files"] == 4
    assert data["added_files"] == ["feature.py"]
    assert data["modified_files"] == ["app.py"]
    assert data["deleted_files"] == ["legacy.py"]
    assert data["renamed_files"] == ["new_name.py"]
    assert data["total_additions"] > 0
    assert data["total_deletions"] > 0

    files_by_path = {item["file_path"]: item for item in data["files"]}

    assert files_by_path["feature.py"]["change_type"] == "added"
    assert "+def new_feature():" in files_by_path["feature.py"]["patch"]

    assert files_by_path["app.py"]["change_type"] == "modified"
    assert "-def calculate(x):" in files_by_path["app.py"]["patch"]
    assert "+def calculate(x, step=2):" in files_by_path["app.py"]["patch"]

    assert files_by_path["legacy.py"]["change_type"] == "deleted"
    assert "-LEGACY = True" in files_by_path["legacy.py"]["patch"]

    assert files_by_path["new_name.py"]["change_type"] == "renamed"
    assert files_by_path["new_name.py"]["previous_path"] == "old_name.py"


def test_compare_rejects_invalid_or_identical_commits(monkeypatch, local_git_fixture):
    """Verify invalid commit SHAs, option injection, or identical commits are rejected."""
    monkeypatch.setattr(
        github_service,
        "_resolve_clone_source",
        lambda _url: local_git_fixture["path"],
    )

    # Option injection attempt
    resp_injection = client.post(
        "/api/repositories/compare",
        json={
            "repository_url": "https://github.com/octocat/Sample-Repo",
            "base_commit": "--upload-pack=evil",
            "head_commit": local_git_fixture["commit_2"],
        },
    )
    assert resp_injection.status_code == 400

    # Identical base and head commit
    resp_same = client.post(
        "/api/repositories/compare",
        json={
            "repository_url": "https://github.com/octocat/Sample-Repo",
            "base_commit": local_git_fixture["commit_1"],
            "head_commit": local_git_fixture["commit_1"],
        },
    )
    assert resp_same.status_code == 400

    # Non-existent commit SHA in repository
    resp_missing = client.post(
        "/api/repositories/compare",
        json={
            "repository_url": "https://github.com/octocat/Sample-Repo",
            "base_commit": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            "head_commit": local_git_fixture["commit_2"],
        },
    )
    assert resp_missing.status_code == 404


# ---------------------------------------------------------------------------
# 4. Temporary Directory Cleanup & Oversized/Binary Diff Tests
# ---------------------------------------------------------------------------


def test_temporary_directory_is_cleaned_up(monkeypatch, local_git_fixture):
    """Verify temporary clone directories are deleted after inspection and comparison."""
    created_temp_dirs: list[str] = []
    real_mkdtemp = tempfile.mkdtemp

    def tracking_mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        created_temp_dirs.append(path)
        return path

    monkeypatch.setattr(tempfile, "mkdtemp", tracking_mkdtemp)
    monkeypatch.setattr(
        github_service,
        "_resolve_clone_source",
        lambda _url: local_git_fixture["path"],
    )

    resp = client.post(
        "/api/repositories/inspect",
        json={"repository_url": "https://github.com/octocat/Sample-Repo"},
    )
    assert resp.status_code == 200
    assert len(created_temp_dirs) == 1
    assert not os.path.exists(created_temp_dirs[0])


def test_oversized_and_binary_diff_handling(monkeypatch, local_git_fixture):
    """Verify oversized diffs are safely truncated and binary files are flagged."""
    repo = local_git_fixture["repo"]
    repo_dir = local_git_fixture["path"]

    large_path = os.path.join(repo_dir, "huge.txt")
    binary_path = os.path.join(repo_dir, "asset.bin")

    with open(large_path, "w", encoding="utf-8") as f:
        f.write("\n".join(f"line {i}: " + ("x" * 80) for i in range(600)))
    with open(binary_path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x01")

    repo.index.add(["huge.txt", "asset.bin"])
    commit_3 = repo.index.commit("Add oversized text file and binary asset")

    monkeypatch.setattr(
        github_service,
        "_resolve_clone_source",
        lambda _url: repo_dir,
    )

    response = client.post(
        "/api/repositories/compare",
        json={
            "repository_url": "https://github.com/octocat/Sample-Repo",
            "base_commit": local_git_fixture["commit_2"],
            "head_commit": commit_3.hexsha,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["diff_truncated"] is True

    files_by_path = {item["file_path"]: item for item in data["files"]}
    assert files_by_path["huge.txt"]["truncated"] is True
    assert "truncated" in files_by_path["huge.txt"]["patch"].lower()
    assert files_by_path["asset.bin"]["is_binary"] is True


def test_no_ff_merge_commit_comparison_returns_actual_changes(
    monkeypatch, local_git_fixture
):
    """
    Simulate GitHub's 'Create a merge commit' (--no-ff) workflow (as used in pallets/flask),
    where a PR branch commit (c_branch) is merged into main via a merge commit (c_merge)
    that shares the exact same Git tree as c_branch.
    Verify:
    1. inspect_repository returns first-parent commits with distinct trees so default
       commits[1] -> commits[0] comparison always yields real file changes.
    2. Explicitly comparing c_branch -> c_merge resolves against the merge base parent
       and returns the actual files changed in that PR instead of 0 changed files.
    """
    repo = local_git_fixture["repo"]
    repo_dir = local_git_fixture["path"]

    # Create a feature branch from commit_2 (current main HEAD)
    main_before_pr = local_git_fixture["commit_2"]
    feature_branch = repo.create_head("pr-branch", main_before_pr)
    feature_branch.checkout()

    pr_file_path = os.path.join(repo_dir, "app.py")
    with open(pr_file_path, "w", encoding="utf-8") as f:
        f.write("def calculate(x, step=2):\n    '''Updated docstring in PR.'''\n    return (x + step) * 10\n")

    repo.index.add(["app.py"])
    c_branch = repo.index.commit("PR commit modifying calculate")

    # Switch back to main and create a --no-ff merge commit with parents [main_before_pr, c_branch]
    repo.heads.main.checkout()
    repo.git.merge("--no-ff", "pr-branch", "-m", "Merge pull request #100 from pr-branch")
    c_merge = repo.head.commit

    # Confirm c_merge and c_branch have the exact same tree hash
    assert c_merge.tree.hexsha == c_branch.tree.hexsha
    assert len(c_merge.parents) == 2

    monkeypatch.setattr(
        github_service,
        "_resolve_clone_source",
        lambda _url: repo_dir,
    )

    # 1. Inspect repository: commits[0] and commits[1] must have distinct trees
    inspect_resp = client.post(
        "/api/repositories/inspect",
        json={"repository_url": "https://github.com/pallets/flask"},
    )
    assert inspect_resp.status_code == 200
    commits = inspect_resp.json()["commits"]
    assert len(commits) >= 2
    assert commits[0]["sha"] == c_merge.hexsha
    assert commits[1]["sha"] == main_before_pr

    # Compare the default top two commits returned by inspect
    default_cmp_resp = client.post(
        "/api/repositories/compare",
        json={
            "repository_url": "https://github.com/pallets/flask",
            "base_commit": commits[1]["sha"],
            "head_commit": commits[0]["sha"],
        },
    )
    assert default_cmp_resp.status_code == 200
    default_cmp = default_cmp_resp.json()
    assert default_cmp["total_changed_files"] == 1
    assert default_cmp["modified_files"] == ["app.py"]
    assert "+    return (x + step) * 10" in default_cmp["files"][0]["patch"]

    # 2. Explicitly compare c_branch (second parent) -> c_merge (merge commit)
    merge_pair_resp = client.post(
        "/api/repositories/compare",
        json={
            "repository_url": "https://github.com/pallets/flask",
            "base_commit": c_branch.hexsha,
            "head_commit": c_merge.hexsha,
        },
    )
    assert merge_pair_resp.status_code == 200
    merge_pair_cmp = merge_pair_resp.json()
    assert merge_pair_cmp["total_changed_files"] == 1
    assert merge_pair_cmp["modified_files"] == ["app.py"]
    assert merge_pair_cmp["total_additions"] >= 2
    assert "+    return (x + step) * 10" in merge_pair_cmp["files"][0]["patch"]


# ---------------------------------------------------------------------------
# 5. Git Operation Timeout, Process Termination & Cleanup Tests
# ---------------------------------------------------------------------------


def test_git_clone_timeout_terminates_process_and_cleans_up_temp_dir(monkeypatch):
    """
    Verify that when a Git clone operation exceeds GIT_OPERATION_TIMEOUT_SECONDS:
    1. Any spawned child process is forcibly terminated.
    2. The temporary clone directory is cleaned up.
    3. The API returns HTTP 504 Gateway Timeout with a safe, clear message.
    """
    import sys
    import time
    created_temp_dirs: list[str] = []
    spawned_procs: list = []
    real_mkdtemp = tempfile.mkdtemp

    def tracking_mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        created_temp_dirs.append(path)
        return path

    def hanging_clone_from(*args, **kwargs):
        # Write a marker file inside the target temp dir and spawn a real subprocess via git.cmd.Popen
        target_dir = kwargs.get("to_path") or (args[1] if len(args) > 1 else None)
        if target_dir and os.path.isdir(target_dir):
            with open(os.path.join(target_dir, "partial_pack.tmp"), "w", encoding="utf-8") as f:
                f.write("partial git clone data")
        proc = git.cmd.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=git.cmd.subprocess.PIPE,
            stderr=git.cmd.subprocess.PIPE,
        )
        spawned_procs.append(proc)
        proc.wait()
        raise RuntimeError("The timed-out test child was terminated.")

    monkeypatch.setattr(tempfile, "mkdtemp", tracking_mkdtemp)
    monkeypatch.setattr(github_service, "GIT_OPERATION_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(git.Repo, "clone_from", hanging_clone_from)

    start_ts = time.monotonic()
    response = client.post(
        "/api/repositories/inspect",
        json={"repository_url": "https://github.com/octocat/Hello-World"},
    )
    elapsed = time.monotonic() - start_ts

    assert response.status_code == 504
    detail = response.json()["detail"].lower()
    assert "clone" in detail
    assert "timed out" in detail
    assert elapsed < 5.0

    # Verify the spawned subprocess was terminated
    assert len(spawned_procs) == 1
    assert spawned_procs[0].poll() is not None

    # Verify temporary directory was deleted even after timeout
    assert len(created_temp_dirs) == 1
    assert not os.path.exists(created_temp_dirs[0])


def test_git_history_fetch_and_diff_timeouts_clean_up_temp_dirs(
    monkeypatch, local_git_fixture
):
    """
    Verify real timeouts and temporary directory cleanup for:
    - commit history retrieval (inspect)
    - commit fetch (compare)
    - diff patch extraction (compare)
    """
    import sys

    created_temp_dirs: list[str] = []
    spawned_procs: list = []
    real_mkdtemp = tempfile.mkdtemp

    def tracking_mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        created_temp_dirs.append(path)
        return path

    def wait_for_hanging_child():
        proc = git.cmd.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=git.cmd.subprocess.PIPE,
            stderr=git.cmd.subprocess.PIPE,
        )
        spawned_procs.append(proc)
        proc.wait()
        raise RuntimeError("The timed-out test child was terminated.")

    monkeypatch.setattr(tempfile, "mkdtemp", tracking_mkdtemp)
    monkeypatch.setattr(
        github_service,
        "_resolve_clone_source",
        lambda _url: local_git_fixture["path"],
    )
    # Give local bare clone (~0.3s on Windows) enough time to finish so the
    # timeout specifically triggers during history, fetch, and diff operations.
    monkeypatch.setattr(github_service, "GIT_OPERATION_TIMEOUT_SECONDS", 1.0)

    # 1. History retrieval timeout
    real_iter_commits = git.Repo.iter_commits

    def hanging_iter_commits(self, *args, **kwargs):
        wait_for_hanging_child()
        return real_iter_commits(self, *args, **kwargs)

    monkeypatch.setattr(git.Repo, "iter_commits", hanging_iter_commits)
    resp_history = client.post(
        "/api/repositories/inspect",
        json={"repository_url": "https://github.com/octocat/Sample-Repo"},
    )
    assert resp_history.status_code == 504
    assert "history" in resp_history.json()["detail"].lower()
    assert "timed out" in resp_history.json()["detail"].lower()
    monkeypatch.setattr(git.Repo, "iter_commits", real_iter_commits)

    # 2. Fetch timeout when resolving a missing commit SHA
    real_resolve_commit = github_service._resolve_commit_object

    def hanging_fetch_resolve(repo, commit_sha, label, owner="octocat", repo_name="Sample-Repo"):
        def _slow_fetch():
            wait_for_hanging_child()

        github_service._run_git_operation_with_timeout(
            operation_name="fetch",
            owner=owner,
            repo_name=repo_name,
            func=_slow_fetch,
            repo=repo,
        )

    monkeypatch.setattr(github_service, "_resolve_commit_object", hanging_fetch_resolve)
    resp_fetch = client.post(
        "/api/repositories/compare",
        json={
            "repository_url": "https://github.com/octocat/Sample-Repo",
            "base_commit": local_git_fixture["commit_1"],
            "head_commit": local_git_fixture["commit_2"],
        },
    )
    assert resp_fetch.status_code == 504
    assert "fetch" in resp_fetch.json()["detail"].lower()
    assert "timed out" in resp_fetch.json()["detail"].lower()
    monkeypatch.setattr(github_service, "_resolve_commit_object", real_resolve_commit)

    # 3. Diff operation timeout
    def hanging_diff(self, *args, **kwargs):
        wait_for_hanging_child()

    monkeypatch.setattr(git.Commit, "diff", hanging_diff)
    resp_diff = client.post(
        "/api/repositories/compare",
        json={
            "repository_url": "https://github.com/octocat/Sample-Repo",
            "base_commit": local_git_fixture["commit_1"],
            "head_commit": local_git_fixture["commit_2"],
        },
    )
    assert resp_diff.status_code == 504
    assert "diff" in resp_diff.json()["detail"].lower()
    assert "timed out" in resp_diff.json()["detail"].lower()

    # Confirm all 3 temporary clone directories were cleaned up
    assert len(created_temp_dirs) == 3
    for temp_dir in created_temp_dirs:
        assert not os.path.exists(temp_dir)
    assert len(spawned_procs) == 3
    assert all(proc.poll() is not None for proc in spawned_procs)


def test_git_env_includes_non_interactive_and_low_speed_stall_guards():
    """Verify _get_git_env configures non-interactive prompts and HTTP low-speed stall guards."""
    env = github_service._get_git_env()
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GCM_INTERACTIVE"] == "never"
    assert env["GIT_HTTP_LOW_SPEED_LIMIT"] == str(github_service.GIT_LOW_SPEED_LIMIT_BYTES)
    assert env["GIT_HTTP_LOW_SPEED_TIME"] == str(github_service.GIT_LOW_SPEED_TIME_SECONDS)


def test_git_timeout_reads_environment_value(monkeypatch):
    """Verify valid timeout configuration is honored and invalid values use the default."""
    monkeypatch.setenv("GIT_OPERATION_TIMEOUT_SECONDS", "12.5")
    assert github_service._load_git_timeout_seconds() == 12.5

    monkeypatch.setenv("GIT_OPERATION_TIMEOUT_SECONDS", "not-a-number")
    assert github_service._load_git_timeout_seconds() == 45.0

    monkeypatch.setenv("GIT_OPERATION_TIMEOUT_SECONDS", "0")
    assert github_service._load_git_timeout_seconds() == 45.0


def test_git_timeout_error_is_classified_as_timeout_not_not_found():
    """Verify a timed-out GitCommandError is classified as RepositoryTimeoutError even if stderr mentions 'not found'."""
    exc = GitCommandError(
        "git fetch origin abc",
        -9,
        stderr='Timeout: the command "git fetch origin abc" did not complete in 45 secs. repository not found',
    )
    result = github_service._classify_git_error(exc, "octocat", "Hello-World")
    assert isinstance(result, github_service.RepositoryTimeoutError)
    assert isinstance(result, github_service.RepositoryNetworkError)
    assert "timed out" in str(result).lower()


def test_commit_fetch_timeout_is_not_reported_as_missing_commit():
    """If the fallback single-commit fetch fails with a timeout stderr, surface RepositoryTimeoutError instead of CommitNotFoundError."""
    from contextlib import nullcontext
    from git.exc import BadName

    class FakeGit:
        def custom_environment(self, **_kwargs):
            return nullcontext()

        def fetch(self, *args, **kwargs):
            raise GitCommandError(
                "git fetch",
                -9,
                stderr="Timeout: the command did not complete in 45 secs.",
            )

    class FakeRepo:
        git = FakeGit()

        def commit(self, _sha):
            raise BadName("abcdef1")

    with pytest.raises(github_service.RepositoryTimeoutError):
        github_service._resolve_commit_object(FakeRepo(), "abcdef1", "base commit")
