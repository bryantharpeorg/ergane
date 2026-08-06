"""US3's component-wide sweep over the merge surface (spec § US3, T045).

Each module's own tests prove that module does its job. This file asks whether
the merge component, taken whole, still holds the three invariants an operator
has to trust blind — the ones whose failure mode is a merged-then-orphaned
branch, a history rewrite the queue is still deciding on, or a secret published
to a repo the operator may later make public (architecture §10):

- **No merge surface removes a branch or forces a push (FR-001, FR-002,
  FR-008).** The branch is the queue's to land: the factory's only merge
  invocation is `gh pr merge --auto --<method>`, kill cleanup is
  `--disable-auto`, nothing ever reaches for `--delete-branch`, and `push` is
  plain fast-forward with no `--force`. Each is asserted against the *source* of
  every module that spawns git or gh, so a command a test never happens to call
  still cannot be one the code can issue.

- **No merge surface names a credential it does not carry (constitution V).**
  The merge library (`factory/mergequeue/`) has no business reading the worker's
  credentials — the master key, the bot token, the proxy URL. `merge_activities`
  is the single module allowed to read them *into* the PR renderer, which proves
  it drops them; a module elsewhere that could even spell a credential name
  would be a module that could read it, and the distance from "can read" to
  "wrote it into a finding or a PR body" is one refactor. So `LITELLM_MASTER_KEY`
  and `TELEGRAM_BOT_TOKEN` may appear only where they are read into the renderer,
  and never in any rendered output, finding, or error path.

- **The renderer's output proves the redaction it claims.** `render_pr_body`
  accepts the secrets precisely so its *output* is the surface of the
  constraint: give it real-shaped secrets and assert the body drops every one
  and never quotes a `sk-`-shaped literal.

Written last (T045), against the finished component. Unlike most test files here,
this one is expected to pass on arrival; a failure means something that was true
when it was written has since stopped being true.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from factory.mergequeue import messages

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Every module that can spawn git or gh — the whole merge command surface. A
#: `push` inside `worktree.py` is a merge-surface push (FR-001), so it is swept
#: here rather than trusted to an activity that never calls the bad path.
COMMAND_MODULES = sorted(
    [
        *(REPO_ROOT / "factory" / "mergequeue").rglob("*.py"),
        REPO_ROOT / "factory" / "activities" / "merge_activities.py",
        REPO_ROOT / "factory" / "workgraph" / "worktree.py",
    ]
)
COMMAND_IDS = [p.relative_to(REPO_ROOT).as_posix() for p in COMMAND_MODULES]

#: The merge *library* — the modules with no business reading worker secrets.
LIBRARY_MODULES = sorted((REPO_ROOT / "factory" / "mergequeue").rglob("*.py"))
LIBRARY_IDS = [p.relative_to(REPO_ROOT).as_posix() for p in LIBRARY_MODULES]

#: Real-shaped canaries, unlike anything else in the repository, so "this string
#: appears" is never a coincidence.
CANARY_KEY = "sk-canary-9c41d2e8a07b31f5-litellm-master"
CANARY_TOKEN = "8102938475:CANARYc2f7a91b4d08e63a5c1b2f9d4e7a8b0"
CANARY_PROXY = "http://192.168.10.90:4000/secret-proxy"


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _docstring_ids(tree: ast.Module) -> set[int]:
    return {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        )
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }


def _code_strings(tree: ast.Module) -> set[str]:
    """Every string the module's *code* spells, docstrings excluded."""
    docstrings = _docstring_ids(tree)
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


# --- structural guards: no delete, no force, merge is only the queue's forms ---


@pytest.mark.parametrize("path", COMMAND_MODULES, ids=COMMAND_IDS)
def test_no_command_module_ever_deletes_a_branch(path: Path) -> None:
    """FR-008: `--delete-branch` never appears in any merge-surface source."""
    assert "--delete-branch" not in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", COMMAND_MODULES, ids=COMMAND_IDS)
def test_no_command_module_pushes_with_force(path: Path) -> None:
    """FR-001: pushes are plain fast-forward; a forced push rewrites history.

    The module's `remove` uses `git worktree remove --force` legitimately, so
    the guard is scoped to the `push` command itself: any occurrence of `--force`
    in a `git push`/`git ... push` line is a history rewrite.
    """
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if "push" in line and "--force" in line:
            pytest.fail(
                f"{path.relative_to(REPO_ROOT)}:{lineno} forces a push: {line.strip()}"
            )


def test_the_only_merge_form_in_source_is_auto_or_disable_auto() -> None:
    """FR-002: the factory never issues a direct merge.

    `gh pr merge` has exactly two forms in the whole command surface:
    `--auto --<method>` (enqueue) and `--disable-auto` (kill cleanup). A call to
    `pr merge` without either flag would merge a branch the queue has not
    serialized, bypassing the required checks.
    """
    offending: list[str] = []
    for path in COMMAND_MODULES:
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if '"merge"' not in line and "'merge'" not in line:
                continue
            if "pr" not in line:
                continue
            if "--auto" not in line and "--disable-auto" not in line:
                offending.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    assert not offending, "a `gh pr merge` lacks --auto/--disable-auto:\n" + "\n".join(
        offending
    )


def test_push_branch_source_is_fast_forward_only() -> None:
    """FR-001's push is plain; the structural guard names the exact call site."""
    path = REPO_ROOT / "factory" / "workgraph" / "worktree.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "push_branch")
    body = ast.get_source_segment(source, fn)
    assert body is not None
    assert "--force" not in body


# --- credential surface: the merge library never names a worker secret ---------


@pytest.mark.parametrize("path", LIBRARY_MODULES, ids=LIBRARY_IDS)
def test_the_merge_library_never_spells_either_credential(path: Path) -> None:
    """`factory/mergequeue/` has no business reading a worker secret.

    001 reads the master key and 002 reads the bot token inside their own
    activities; this library's only reader is `merge_activities`, which hands
    them to the renderer to prove they are dropped. A library module that could
    spell `LITELLM_MASTER_KEY` or `TELEGRAM_BOT_TOKEN` could read it, and the
    distance from "can read" to "wrote it into a finding" is one refactor.
    """
    spelled = _code_strings(_parse(path)) & {
        "LITELLM_MASTER_KEY",
        "TELEGRAM_BOT_TOKEN",
    }
    assert not spelled, (
        f"{path.relative_to(REPO_ROOT)} names {sorted(spelled)} outside its "
        "docstrings; the merge library reads no worker credential (constitution V)"
    )


def test_only_merge_activities_reads_the_credentials_into_the_renderer() -> None:
    """The credential reads live in exactly one module.

    `merge_activities` reads `LITELLM_MASTER_KEY` (via `MASTER_KEY_ENV`),
    `LITELLM_PROXY_URL` (via `PROXY_URL_ENV`), and `TELEGRAM_BOT_TOKEN` from the
    worker environment to feed the renderer's redaction proof. A second reader
    would be a second thing holding a credential — how one ends up in an error
    message or a finding. Every other module that spawns git or gh must name
    none of them.
    """
    allowed = {
        "LITELLM_MASTER_KEY",
        "TELEGRAM_BOT_TOKEN",
        "MASTER_KEY_ENV",
        "PROXY_URL_ENV",
    }
    readers = [
        p.relative_to(REPO_ROOT).as_posix()
        for p in COMMAND_MODULES
        if p.name != "merge_activities.py"
        and (_code_strings(_parse(p)) & allowed)
    ]
    assert not readers, (
        f"these modules read a worker credential: {readers}; only "
        "merge_activities may, to prove the renderer drops them"
    )


def test_onboard_findings_carry_no_credential_or_proxy_url() -> None:
    """A failed validation's findings must not quote a secret.

    The onboarding gate's failure path renders findings into an epic error an
    operator reads and may paste. None of that prose may echo a credential or a
    proxy URL — the failure is actionable because it names *what to change*, not
    *what the worker host held*.
    """
    # The pure evaluation never sees a credential to leak — its inputs are the
    # repo's public facts. Confirm the signature carries no secret-shaped field.
    import inspect

    from factory.mergequeue.onboard import evaluate_repo

    params = inspect.signature(evaluate_repo).parameters
    assert not any(
        "key" in name or "token" in name or "secret" in name or "url" in name
        for name in params
    ), f"evaluate_repo takes a secret-shaped parameter: {sorted(params)}"


# --- the renderer's output is the redaction's proof ---------------------------


def test_the_renderer_drops_every_secret_it_is_handed() -> None:
    """`render_pr_body` is handed real-shaped secrets and outputs none of them."""
    from factory.verify.models import (
        GateResult,
        GateStatus,
        OutputCheck,
        OverallVerdict,
        VerificationForm,
        VerificationResult,
    )

    result = VerificationResult(
        epic_id="003-merge-queue",
        node_id="us3",
        attempt=1,
        form=VerificationForm.PHASE,
        gate_results=[
            GateResult(
                name="test",
                command="pytest -q",
                status=GateStatus.PASS,
                exit_code=0,
                duration_s=1.25,
                output_tail="1 passed",
            )
        ],
        output_check=OutputCheck(
            write_scope="target",
            has_diff=True,
            expected_artifacts=[],
            artifacts_present=None,
            passed=True,
        ),
        judge=None,
        verdict=OverallVerdict.PASS,
        judge_unavailable=True,
        criteria_drift=False,
        criteria_sha256="abc",
        spec_ref="003-merge-queue@FR-010",
        started_at="2026-08-06T00:00:00Z",
        finished_at="2026-08-06T00:00:01Z",
    )

    body = messages.render_pr_body(
        epic_id="003-merge-queue",
        node_id="us3",
        branch="factory/003-merge-queue/us3",
        attempt=1,
        feature="003-merge-queue",
        requirement_keys=("FR-010", "SC-005"),
        result=result,
        proxy_url=CANARY_PROXY,
        master_key=CANARY_KEY,
        telegram_token=CANARY_TOKEN,
        transcript_path="/var/lib/ergane/transcripts/attempt-00001.log",
    )

    assert CANARY_KEY not in body
    assert CANARY_TOKEN not in body
    assert CANARY_PROXY not in body
    assert "/var/lib/ergane/transcripts" not in body
    assert "sk-" not in body
