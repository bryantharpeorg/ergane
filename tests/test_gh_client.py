"""`GhClient`: the one place this component spawns `gh` (plan.md § US1).

The whole merge-queue component talks to GitHub through this client, and only
through it. Two structural guarantees are what these tests actually defend:

- **`gh` runs with `cwd` = the target clone, never a worktree** (FR-001). A
  `gh pr merge --auto` issued from inside a node worktree would operate on the
  wrong repository's branch namespace — the push already happened from the
  clone, and the queue decision has to be made there too.
- **The command surface is exactly the plan's table, no wider** (FR-002,
  FR-008). The client issues `gh pr list --head`, `gh pr create --base/--head`,
  `gh pr merge <n> --auto --<method>`, `gh pr view <n> --json`, and
  `gh pr merge <n> --disable-auto`. It never issues a direct (non-`--auto`)
  merge — the factory's only merge invocation is the queue's — and no path ever
  passes `--delete-branch`, which would destroy the branch the queue still
  needs to land (FR-008, constitution VI).

Failures are classified, never crashed: `GhClient` raises a typed `GhFailure`
carrying a `kind` in the small taxonomy (`GH_AUTH`, `GH_NOT_FOUND`, `GH_REFUSED`
with stderr tail, `GH_UNAVAILABLE`) so an activity can catch it and return the
refusal as data — an enqueue rejected because the queue was disabled mid-flight
is a queue rejection routed to escalation, not a workflow failure (spec edge
case).

`FakeGh` (tests/fake_gh.py) is the injected runner. It records every invocation
with its `cwd`, so the tests below assert both *what* was issued and *from where*
— and an unscripted command fails the test immediately.

Written before `factory/mergequeue/gh.py` exists (T007 precedes T008): until the
module lands, every test here fails at import.
"""

from __future__ import annotations

import pytest

from factory.mergequeue.gh import (
    CheckFailure,
    GhClient,
    GhError,
    GH_AUTH,
    GH_NOT_FOUND,
    GH_REFUSED,
    GH_UNAVAILABLE,
    PrCheckEntry,
    _FAILED_LOG_PER_CHECK_LIMIT,
    _parse_run_id,
)
from tests.fake_gh import FakeGh, FakeGhResult

TARGET_CLONE = "/srv/target"


# --- the runner seam ----------------------------------------------------------


def test_gh_client_spawns_the_injected_runner_with_cwd_the_target_clone() -> None:
    """`cwd` = target clone, asserted as a recorded fact (FR-001)."""
    gh = FakeGh()
    gh.expect_json(
        "pr", "list", "--head", "factory/003-merge-queue/us1", "--state", "open",
        "--json", "number,url", payload=[],
    )
    client = GhClient(runner=gh, repo=TARGET_CLONE)

    client.find_existing_pr("factory/003-merge-queue/us1")

    assert [(c.args, c.cwd) for c in gh.calls] == [
        (
            ("pr", "list", "--head", "factory/003-merge-queue/us1", "--state", "open",
             "--json", "number,url"),
            TARGET_CLONE,
        )
    ]


def test_json_output_is_parsed() -> None:
    gh = FakeGh()
    gh.expect_json(
        "pr", "list", "--head", "factory/003-merge-queue/us1", "--state", "open",
        "--json", "number,url", payload=[{"number": 7, "url": "https://x/pull/7"}],
    )
    client = GhClient(runner=gh, repo=TARGET_CLONE)

    found = client.find_existing_pr("factory/003-merge-queue/us1")

    assert found.number == 7
    assert found.url == "https://x/pull/7"


def test_no_existing_pr_is_none() -> None:
    gh = FakeGh()
    gh.expect_json(
        "pr", "list", "--head", "factory/003-merge-queue/us1", "--state", "open",
        "--json", "number,url", payload=[],
    )
    client = GhClient(runner=gh, repo=TARGET_CLONE)

    assert client.find_existing_pr("factory/003-merge-queue/us1") is None


def test_create_pr_uses_base_head_title_and_body_file_never_draft() -> None:
    """Ready, never draft — a draft PR does not enter the queue (US1)."""
    gh = FakeGh()
    gh.expect_json(
        "pr", "create", "--base", "main", "--head", "factory/003-merge-queue/us1",
        "--title", "003-merge-queue/us1: story title", "--body-file",
        "/tmp/pr-body.md", payload={"number": 7, "url": "https://x/pull/7"},
    )
    client = GhClient(runner=gh, repo=TARGET_CLONE)

    created = client.create_pr(
        base="main",
        head="factory/003-merge-queue/us1",
        title="003-merge-queue/us1: story title",
        body_file="/tmp/pr-body.md",
    )

    assert created.number == 7
    assert "--draft" not in [a for c in gh.calls for a in c.args]


# --- the failure taxonomy -----------------------------------------------------


@pytest.mark.parametrize(
    ("exit_code", "stderr", "expected_kind"),
    [
        (4, "gh: not authenticated", GH_AUTH),
        (1, "HTTP 404: Not Found (pr not found)", GH_NOT_FOUND),
        (1, "gh: error: merge queue is disabled for this repository", GH_REFUSED),
    ],
    ids=["auth", "not-found", "refused"],
)
def test_nonzero_exit_is_classified_not_crashed(
    exit_code: int, stderr: str, expected_kind: str
) -> None:
    gh = FakeGh()
    gh.expect(
        "pr", "merge", "7", "--auto",
        stderr=stderr, returncode=exit_code,
    )
    client = GhClient(runner=gh, repo=TARGET_CLONE)

    with pytest.raises(GhError) as excinfo:
        client.enqueue_pr(7, merge_method="squash")

    assert excinfo.value.kind == expected_kind


def test_refused_carries_the_stderr_tail() -> None:
    """GH_REFUSED is actionable — it quotes the last of what `gh` refused with."""
    gh = FakeGh()
    gh.expect(
        "pr", "merge", "7", "--auto",
        stderr="gh: error: merge queue is disabled for this repository",
        returncode=1,
    )
    client = GhClient(runner=gh, repo=TARGET_CLONE)

    with pytest.raises(GhError) as excinfo:
        client.enqueue_pr(7, merge_method="squash")

    assert excinfo.value.kind == GH_REFUSED
    assert "merge queue is disabled" in excinfo.value.stderr_tail


def test_runner_raising_os_error_is_unavailable() -> None:
    """A runner that cannot spawn `gh` at all is unavailable, not refused."""
    client = GhClient(repo=TARGET_CLONE, runner=_raising_runner)

    with pytest.raises(GhError) as excinfo:
        client.poll_pr(7)

    assert excinfo.value.kind == GH_UNAVAILABLE


def _raising_runner(argv, cwd):  # type: ignore[no-untyped-def]
    raise OSError("no such gh")


# --- structural guards (FR-002, FR-008) ---------------------------------------


def test_the_only_merge_form_is_auto_or_disable_auto() -> None:
    """No direct merge ever: enqueue is `--auto`, kill cleanup is `--disable-auto`."""
    gh = FakeGh()
    gh.expect("pr", "merge", "7", "--auto")
    gh.expect("pr", "merge", "7", "--disable-auto")
    client = GhClient(runner=gh, repo=TARGET_CLONE)

    client.enqueue_pr(7, merge_method="squash")
    client.disable_auto_merge(7)

    # Flagless: a queue-ruleset branch owns its merge method (proved live
    # 2026-08-07 — gh refuses the strategy flag on queue-governed branches).
    merge_forms = [c.args for c in gh.calls]
    assert merge_forms == [
        ("pr", "merge", "7", "--auto"),
        ("pr", "merge", "7", "--disable-auto"),
    ]


def test_no_code_path_passes_delete_branch() -> None:
    """FR-008: the branch is the queue's to land, never the cleanup's to delete."""
    import inspect

    from factory.mergequeue import gh as gh_module

    source = inspect.getsource(gh_module)
    assert "--delete-branch" not in source


def test_poll_pr_uses_the_full_json_field_set() -> None:
    gh = FakeGh()
    payload = FakeGh.pr_view_payload(auto_merge=False)
    gh.expect_json(
        "pr", "view", "7", "--json",
        "state,isDraft,mergedAt,closedAt,mergeStateStatus,autoMergeRequest,statusCheckRollup",
        payload=payload,
    )
    client = GhClient(runner=gh, repo=TARGET_CLONE)

    snapshot = client.poll_pr(7)

    assert snapshot.state == "OPEN"
    assert snapshot.auto_merge_requested is False


# --- US2: check-failure evidence (plan.md § US2, FR-005/006/007) --------------


def test_pr_checks_parses_name_state_and_link() -> None:
    """`gh pr checks` becomes a list of (name, state, link) entries."""
    gh = FakeGh()
    gh.expect_json(
        "pr", "checks", "7", "--json", "name,state,link",
        payload=[
            {"name": "lint", "state": "FAIL", "link": "https://github.com/acme/target/actions/runs/123/job/456"},
            {"name": "test", "state": "PASS", "link": "https://github.com/acme/target/actions/runs/124/job/457"},
        ],
    )
    client = GhClient(runner=gh, repo=TARGET_CLONE)

    checks = client.pr_checks(7)

    assert len(checks) == 2
    assert checks[0] == PrCheckEntry(
        name="lint", state="FAIL", link="https://github.com/acme/target/actions/runs/123/job/456"
    )
    assert checks[1] == PrCheckEntry(
        name="test", state="PASS", link="https://github.com/acme/target/actions/runs/124/job/457"
    )
    assert [(c.args, c.cwd) for c in gh.calls] == [
        (("pr", "checks", "7", "--json", "name,state,link"), TARGET_CLONE),
    ]


def test_run_failed_log_issues_gh_run_view_log_failed_and_returns_tail() -> None:
    """`gh run view <id> --log-failed` returns the failing step log, bounded."""
    gh = FakeGh()
    big_log = "line\n" * 2000 + "FAILED tests/test_calc.py::test_add\n"
    gh.expect(
        "run", "view", "123", "--log-failed",
        stdout=big_log,
    )
    client = GhClient(runner=gh, repo=TARGET_CLONE)

    tail = client.run_failed_log("123")

    assert "FAILED tests/test_calc.py::test_add" in tail
    assert len(tail.encode("utf-8")) <= _FAILED_LOG_PER_CHECK_LIMIT
    # It is the tail: the early repetition is dropped.
    assert tail.startswith("FAILED tests/test_calc.py::test_add")


def test_run_id_is_parsed_from_actions_run_link() -> None:
    assert _parse_run_id("https://github.com/acme/target/actions/runs/123/job/456") == "123"
    assert _parse_run_id("https://github.com/acme/target/actions/runs/123") == "123"


def test_run_id_parse_fails_for_non_run_links() -> None:
    assert _parse_run_id("https://github.com/acme/target/checks") is None
    assert _parse_run_id("") is None
