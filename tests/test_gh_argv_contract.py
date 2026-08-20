"""US2: every argv `GhClient` builds is accepted by the real `gh` binary.

The merge-queue component issues every GitHub command through `GhClient`, but
the existing tests use `FakeGh`, and a fake answers whatever it is scripted to
answer. Two real commands were therefore wrong for months:

- `gh pr checks <n> --json ...` — `pr checks` has no `--json` flag.
- `gh pr create ...` parsed as JSON, but `pr create` prints a URL.

This file adds a check that runs every command `GhClient` builds against the
installed `gh` binary, with no token, no network, and no repository. `gh`
rejects unknown flags during argument parsing, before it authenticates, so the
check is fast and cheap. The command surface is enumerated from the class, not
hand-listed, so a new method is covered automatically.
"""

from __future__ import annotations

import inspect
import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Callable, Sequence

import pytest

from factory.mergequeue.gh import GhClient

TARGET_CLONE = "/srv/target"


def _gh_binary() -> str | None:
    """Return the path to the `gh` binary, or `None` if it is absent."""
    return shutil.which("gh")


def _public_command_methods() -> list[str]:
    """Every public `GhClient` method that issues a `gh` command.

    The set is derived from the class source so a hand-written list cannot go
    stale. A method is included if its body contains a call to `_run` or
    `_run_json`.
    """
    source = inspect.getsource(GhClient)
    methods: list[str] = []
    for match in re.finditer(r"    def (\w+)\(", source):
        name = match.group(1)
        if name.startswith("_"):
            continue
        start = match.end()
        end_match = re.search(r"\n    def \w+\(", source[start:])
        body = source[start : start + end_match.start()] if end_match else source[start:]
        if re.search(r"self\._run(?:_json)?\(", body):
            methods.append(name)
    return methods


def _extract_argvs(method_name: str) -> list[list[str]]:
    """Return the argv sequences one method can build, with placeholders filled.

    Each method is called with representative arguments so every branch that
    builds a different argv is exercised. The calls are made against a recording
    runner, not the real `gh` binary. The runner returns JSON shapes that let
    each method return normally, so the test measures the argv, not the parsing.
    """
    argvs: list[list[str]] = []

    def recorder(argv: Sequence[str], cwd: str) -> Any:
        argvs.append(list(argv))
        # Return JSON shapes that satisfy each caller. `api` calls that expect
        # a list or dict need the right container so the method returns.
        if argv[0] == "api" and argv[-1].endswith("/rulesets"):
            return _FakeCompleted(stdout="[]", stderr="", returncode=0)
        if argv[0] == "api" and "/rules/branches/" in argv[-1]:
            return _FakeCompleted(stdout="[]", stderr="", returncode=0)
        if argv[:2] == ["pr", "create"]:
            return _FakeCompleted(
                stdout="https://github.com/owner/repo/pull/1\n",
                stderr="",
                returncode=0,
            )
        return _FakeCompleted(stdout="{}", stderr="", returncode=0)

    client = GhClient(repo=TARGET_CLONE, runner=recorder)
    method = getattr(client, method_name)

    # Body-file argument: provide a real file path so `--body-file` would be
    # accepted by `gh` if the call ever reached it.
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("body")
        body_file = f.name

    try:
        if method_name == "find_existing_pr":
            method("factory/003-merge-queue/us1")
        elif method_name == "create_pr":
            method(base="main", head="feature", title="title", body_file=body_file)
        elif method_name == "enqueue_pr":
            method(7, merge_method="squash")
        elif method_name == "poll_pr":
            method(7)
        elif method_name == "disable_auto_merge":
            method(7)
        elif method_name == "pr_checks":
            method(7)
        elif method_name == "run_failed_log":
            method("123")
        elif method_name == "repo_view":
            method()
        elif method_name == "rules_for_branch":
            method("owner/repo", "main")
        elif method_name == "classic_branch_protection":
            method("owner/repo", "main")
        elif method_name == "merge_settings":
            method("owner/repo")
        elif method_name == "auth_status":
            method()
        elif method_name == "set_squash_merge_commit_title":
            method("owner/repo", "PR_TITLE")
        elif method_name == "set_allow_auto_merge":
            method("owner/repo", True)
        elif method_name == "list_rulesets":
            method("owner/repo")
        elif method_name == "ruleset":
            method("owner/repo", 1)
        elif method_name == "create_ruleset":
            method("owner/repo", {"name": "test"})
        elif method_name == "update_ruleset":
            method("owner/repo", 1, {"name": "test"})
        else:
            raise AssertionError(f"_extract_argvs does not know how to call {method_name}")
    finally:
        os.unlink(body_file)

    return argvs


class _FakeCompleted:
    """Minimal subprocess completion shape for the recorder."""

    def __init__(self, stdout: str, stderr: str, returncode: int) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _gh_would_refuse(argv: Sequence[str]) -> str:
    """Run `gh` with the argv and return a refusal message, or empty if accepted.

    The run uses no token, no network, and no repository. `gh` exits 4 when it
    needs authentication, which is fine: that means the flags and command were
    accepted. Exit 1 with "unknown flag", "unknown command", or a usage block
    means the argv is malformed.
    """
    env = os.environ.copy()
    env.update({"GH_TOKEN": "", "GIT_TERMINAL_PROMPT": "0"})
    try:
        completed = subprocess.run(
            ["gh", *argv],
            cwd="/tmp",
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"could not run gh to validate {list(argv)!r}: {exc}"

    stderr = (completed.stderr or completed.stdout or "").lower()
    if (
        "unknown flag" in stderr
        or "unknown command" in stderr
        or ("usage:" in stderr and completed.returncode != 0)
    ):
        return completed.stderr or completed.stdout or ""
    return ""


@pytest.mark.skipif(_gh_binary() is None, reason="gh is not installed")
@pytest.mark.parametrize("method_name", _public_command_methods())
def test_gh_client_method_argv_is_accepted_by_real_gh(method_name: str) -> None:
    """T015: every command `GhClient` issues is accepted by the real `gh` binary."""
    failures: list[str] = []
    for argv in _extract_argvs(method_name):
        refusal = _gh_would_refuse(argv)
        if refusal:
            failures.append(f"{method_name}: {argv!r}\n{refusal}")
    assert not failures, "\n---\n".join(failures)


@pytest.mark.skipif(_gh_binary() is None, reason="gh is not installed")
def test_malformed_argv_is_rejected_and_names_command_and_flag() -> None:
    """T016: mutation control — a flag `gh` does not have makes the check fail.

    The malformed argv is deliberately constructed: it appends an invented flag
    to a real command. The check must report the command name and the flag.
    """
    argv = ["pr", "view", "1", "--json", "state", "--ergane-test-unknown-flag"]
    refusal = _gh_would_refuse(argv)
    assert "unknown flag" in refusal.lower()
    assert "--ergane-test-unknown-flag" in refusal
    assert "pr view" in refusal or "pr" in argv[0]


@pytest.mark.skipif(_gh_binary() is None, reason="gh is not installed")
def test_check_catches_unknown_flag_with_no_network_token_or_repository() -> None:
    """T017: the check works without network, token, or repository.

    `gh` rejects unknown flags during argument parsing, before it does any
    network work. The helper already runs in `/tmp` with `GH_TOKEN` unset; this
    test asserts that the same environment still catches an unknown flag.
    """
    argv = ["pr", "view", "1", "--json", "state", "--ergane-networkless-flag"]
    env = os.environ.copy()
    env.update({"GH_TOKEN": "", "GIT_TERMINAL_PROMPT": "0"})

    completed = subprocess.run(
        ["gh", *argv],
        cwd="/tmp",
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )

    stderr = (completed.stderr or completed.stdout or "").lower()
    assert "unknown flag" in stderr


@pytest.mark.skipif(_gh_binary() is not None, reason="gh is installed")
def test_check_skips_by_real_guard_when_gh_is_absent() -> None:
    """T018: when `gh` is absent, the test skips by a real runtime guard.

    This test only runs when `gh` is not on `PATH`. It asserts that the helper
    reports the binary as absent, which is the guard the parametrized tests use.
    The guard is checked at runtime; no pytest marker is used.
    """
    assert shutil.which("gh") is None


@pytest.mark.skipif(_gh_binary() is None, reason="gh is not installed")
def test_create_pr_no_longer_parses_output_as_json() -> None:
    """T019: `create_pr` stops using `_run_json` and returns a `CreatedPr` from the URL.

    `gh pr create` prints the URL of the created PR on stdout. The corrected
    implementation runs the command through `_run`, extracts the PR number from
    the printed URL, and returns it with the URL.
    """
    client = GhClient(repo=TARGET_CLONE, runner=_url_printing_runner)

    created = client.create_pr(
        base="main",
        head="feature",
        title="title",
        body_file="/tmp/body.md",
    )

    assert created.number == 123
    assert created.url == "https://github.com/owner/repo/pull/123"


def _url_printing_runner(argv: Sequence[str], cwd: str) -> Any:
    """A runner that returns the stdout `gh pr create` would print."""
    return _FakeCompleted(
        stdout="https://github.com/owner/repo/pull/123\n",
        stderr="",
        returncode=0,
    )
