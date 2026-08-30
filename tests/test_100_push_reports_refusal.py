"""US2 — a refused push says why (epic 100).

A node reached `PASSED` in under seven minutes, then died pushing its branch,
and the whole account an operator got was `terminal_reason: Activity task
failed`. Git had said exactly what was wrong — `! [rejected] … (non-fast-forward)` —
and four hours went to rediscovering it.

Where the reason was actually lost is worth stating, because it is not where the
spec's drafting note guessed. `--quiet` does **not** suppress a push's failure
diagnosis: git writes the rejection to stderr with or without it (the measured
proof is pasted in `test_100_push_reports_refusal_paste.txt`), and `_git` already
folds stderr into the `WorktreeError` it raises. The flattening happens two
layers up. `open_landing_pr` re-raises as `ApplicationError(str(exc), …)`, the
workflow sees an `ActivityError` whose own `str` is the fixed sentence "Activity
task failed", and `_reap_finished` wrote *that* into `terminal_reason` — the one
place in the workflow that recorded a dead node's reason without walking to the
cause that carries it. `_failure_detail` was written for this exact walk in
078-US3 and was simply not used here.

So the three tests below split along that seam:

- **T010 (US2-S1)** — `test_a_refused_push_carries_gits_own_stderr`. Real git,
  real remote, a real refusal: every line git wrote must be findable in the
  raised error, and reachable structurally as `WorktreeError.stderr` rather than
  only as prose. Nothing here hard-codes git's wording — the expected text is
  whatever the same push wrote when run raw a moment earlier, so a git that
  rewords its rejection changes the fixture and not the assertion. The
  structured half is what US3 classifies on (spec § Work Graph: US3 "classifies
  on the stderr US2 captures"), and a substring hunt through a prose message is
  the fragile version of that.

  Beside it, `test_the_refusal_leads_with_the_verdict_not_with_an_argv` pins the
  half that test cannot: carrying git's stderr is already satisfied by `_git`'s
  default message, so every assertion above survives deleting the `refusal`
  hook. What does not survive is the *order* — the reason is read flattened and
  from the front, and the default opens with an argv. Both tests are needed
  because they fail for different reasons.

- **T011 (US2-S2)** — `test_the_nodes_terminal_reason_names_the_refusal`. The
  end-to-end reading: a real refusal message, carried by a fake
  `open_landing_pr` that fails exactly the way the real one does
  (`ApplicationError(str(exc), type=PUSH_FAILED) from exc`), through a real
  workflow, to the reason `ergane build status` prints. Asserted both on the
  record and on the rendered line, and asserted *negatively* against the
  sentence that cost the four hours.

- **T012 (US2-S3, plan trap 4)** — `test_a_successful_push_is_no_noisier_than_it_was`.
  The control. The tempting fix is to drop `--quiet`, which buys the diagnosis on
  the failure path by paying for it on every landing that works. This asserts the
  flag is still there and that the successful push subprocess wrote nothing at
  all — measured at the subprocess, not inferred from the flag.

Two things these tests deliberately do not assert, because they belong to US3 and
a test that owned them would have to be rewritten by a sibling story: how many
times the activity is retried, and which state the node ends in. US2's claim is
about the *reason*, whatever the routing around it becomes.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pytest
from temporalio import activity
from temporalio.converter import default as default_data_converter
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment

from factory.activities.merge_activities import PUSH_FAILED, OpenLandingPrInput
from factory.cli.nouns.build import render_status
from factory.workgraph.worktree import (
    WorktreeError,
    branch_name,
    ensure,
    push_branch,
)
from tests.target_repo import git, git_env
from tests.test_interpreter import (
    EPIC_ID,
    ScriptedWorld,
    env,  # noqa: F401  — pytest fixture, re-exported for this module
    one_node,
    passing,
    run_epic,
)

#: The node `one_node()` compiles, so the refusal the workflow test carries names
#: the branch that workflow's own node would have pushed.
NODE = "us1"
BRANCH = branch_name(EPIC_ID, NODE)

#: The sentence this story exists to replace. Asserted absent by name: FR-005 is
#: about a reason that names the refusal, and "some other string" is not the
#: claim.
GENERIC = "Activity task failed"


def flat(text: str) -> str:
    """Whitespace-flattened, the way `_reason_token` renders a reason."""
    return " ".join(text.split())


# --- setup -------------------------------------------------------------------


@pytest.fixture(autouse=True)
def no_operator_git_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every identity git could fall back on (tests/test_worktree.py)."""
    empty_home = tmp_path / "empty-home"
    empty_home.mkdir()
    monkeypatch.setenv("HOME", str(empty_home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    for name in (
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def factory_root(tmp_path: Path) -> Path:
    """The worker host's state directory — outside the target clone."""
    return tmp_path / ".ergane"


@pytest.fixture
def repo(target_repo: Callable[..., Path]) -> Path:
    """The dispatched target clone, whose ref store the push goes through."""
    return target_repo("passing", name="clone")


def _origin(repo: Path, tmp_path: Path) -> Path:
    """Give the clone an `origin` that can refuse a push. Real, not a double."""
    bare = tmp_path / "origin.git"
    git(repo, "init", "--bare", str(bare))
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "--quiet", "-u", "origin", "main")
    return bare


def _prepare(repo: Path, factory_root: Path) -> Path:
    """The node worktree with an attempt's worth of work committed on it."""
    prepared = ensure(repo, EPIC_ID, NODE, factory_root=factory_root)
    worktree = Path(prepared.path)
    (worktree / "landed.txt").write_text("work\n", encoding="utf-8")
    git(worktree, "add", "-A")
    git(worktree, "commit", "--quiet", "-m", "node work")
    return worktree


def _rebuild_on_a_sibling_commit(worktree: Path) -> None:
    """Put the branch on a commit the pushed tip is not an ancestor of.

    The defect's own shape, reduced: a kill salvages and pushes a tip, the
    re-dispatch branches fresh from the landing branch, and the two share no
    ancestry — so a plain, correct, non-forced push is refused. Reproduced here
    by dropping the pushed commit and committing different work in its place,
    which is the same ancestry relationship with none of the epic machinery.
    """
    git(worktree, "reset", "--hard", "HEAD~1")
    (worktree / "landed.txt").write_text("work from the re-dispatch\n", encoding="utf-8")
    git(worktree, "add", "-A")
    git(worktree, "commit", "--quiet", "-m", "node work, second dispatch")


def _raw_push_stderr(repo: Path) -> str:
    """What git writes for this refusal when nothing is wrapping it.

    Run before `push_branch` and against the same state, so the expected text is
    git's own current wording rather than a string this file decided git ought to
    use. The refusal changes nothing, so running it twice is one refusal twice.
    """
    completed = subprocess.run(
        ["git", "-C", str(repo), "push", "--quiet", "origin", BRANCH],
        capture_output=True,
        text=True,
        env=git_env(),
    )
    assert completed.returncode != 0, (
        "the fixture did not produce a refused push; the rest of this file is "
        f"about a refusal that did not happen:\n{completed.stderr}"
    )
    return completed.stderr


def _rejection_line(stderr: str) -> str:
    """Git's own one-line verdict on the ref it would not move."""
    for line in stderr.splitlines():
        if line.strip().startswith("! ["):
            return line.strip()
    raise AssertionError(f"no rejection line in git's stderr:\n{stderr}")


@dataclass(frozen=True)
class Refusal:
    """One real refused push: what git said, and what `push_branch` raised."""

    error: WorktreeError
    stderr: str

    @property
    def rejection(self) -> str:
        return _rejection_line(self.stderr)


@pytest.fixture
def refusal(repo: Path, factory_root: Path, tmp_path: Path) -> Refusal:
    """A real `push_branch` refusal, from a real remote refusing a real push."""
    _origin(repo, tmp_path)
    worktree = _prepare(repo, factory_root)
    # The push a killed epic's salvage leaves on origin. It succeeds.
    push_branch(repo, EPIC_ID, NODE, factory_root=factory_root)
    _rebuild_on_a_sibling_commit(worktree)

    stderr = _raw_push_stderr(repo)
    with pytest.raises(WorktreeError) as raised:
        push_branch(repo, EPIC_ID, NODE, factory_root=factory_root)
    return Refusal(error=raised.value, stderr=stderr)


# --- T010 [US2] (spec US2-S1, FR-004) -----------------------------------------


def test_a_refused_push_carries_gits_own_stderr(refusal: Refusal) -> None:
    """Every line git wrote is in the error, and reachable as data.

    Two halves, and the story needs both. The prose half is what an operator
    reads: the message must contain git's account, not a summary of it, so the
    `hint:` lines that name the fix travel too. The structured half is
    `WorktreeError.stderr` — git's stderr verbatim, unmixed with the factory's
    own words — because US3 has to decide "was this a non-fast-forward?" from it,
    and deciding that by hunting for a substring inside a prose message is how a
    guard starts firing on unrelated failures (plan trap 5).
    """
    message = str(refusal.error)

    for line in refusal.stderr.splitlines():
        if line.strip():
            assert line in message, (
                f"git said this and the error dropped it: {line!r}\n"
                f"error was:\n{message}"
            )

    assert refusal.error.stderr.strip() == refusal.stderr.strip(), (
        "the error carries no verbatim copy of git's stderr for US3 to classify on"
    )

    # The line that ends the diagnosis, present in both halves.
    assert refusal.rejection in message
    assert refusal.rejection in refusal.error.stderr

    # And the message says which push, so a reason read alone is still a reason.
    assert BRANCH in message
    assert "origin" in message


def test_the_refusal_leads_with_the_verdict_not_with_an_argv(
    refusal: Refusal,
) -> None:
    """The front of the reason names the refusal (FR-005).

    Separate from the test above because it fails for a different reason, and
    the difference is the whole of why `_git` grew a `refusal` hook. Carrying
    git's stderr is satisfied by `_git`'s own default message — delete the hook
    and every assertion in `test_a_refused_push_carries_gits_own_stderr` still
    passes, because the stderr rides along either way. What the default cannot
    do is *lead* with the verdict: its first line is the argv it ran followed
    by git's `To <remote>`, and the rejection lands on line two.

    That ordering is not cosmetics. `terminal_reason` reaches an operator
    whitespace-flattened into a single untruncated line (`_reason_token`), so
    it is read from the front — and a reason whose front is
    `git push --quiet origin … failed in /tmp/…: To /tmp/…` opens with the two
    facts the operator already had. This pins the first line to the one fact
    they did not: which ref was refused, and why.

    Mutation: drop the `refusal=` argument from `push_branch`'s `_git` call and
    this is the test that goes red.
    """
    first = str(refusal.error).splitlines()[0]

    assert refusal.rejection in first, (
        "the reason does not lead with git's verdict; an operator reading the "
        f"front of the flattened line learns nothing new.\nfirst line: {first!r}"
    )
    assert BRANCH in first, f"the leading sentence does not say which branch: {first!r}"
    assert not first.startswith("git push"), (
        f"the reason leads with the argv rather than the refusal: {first!r}"
    )


# --- T011 [US2] (spec US2-S2, FR-005) -----------------------------------------


def _activity_name(fn: Any) -> str:
    """The name Temporal registers a scripted activity under."""
    definition = getattr(fn, "__temporal_activity_definition", None)
    return getattr(definition, "name", "")


class RefusedPushWorld(ScriptedWorld):
    """The scripted world with an `open_landing_pr` that git refused.

    Only that activity is replaced, and it fails the way the real one does, to
    the letter: `raise ApplicationError(str(exc), type=PUSH_FAILED) from exc`
    over a `WorktreeError` that a real git really raised
    (`factory/activities/merge_activities.py`). The cause chain is the point — it
    is what the workflow has to walk — so the `from exc` is not decoration.
    """

    def __init__(
        self, script: dict[str, list[Any]], *, error: WorktreeError, **kwargs: Any
    ) -> None:
        super().__init__(script, **kwargs)
        self.error = error
        self.open_attempts = 0

    def activities(self) -> list[Any]:
        world = self
        inherited = [
            fn for fn in super().activities() if _activity_name(fn) != "open_landing_pr"
        ]

        @activity.defn(name="open_landing_pr")
        async def open_landing_pr(request: OpenLandingPrInput) -> Any:
            world._log("open_landing_pr", request.node_id)
            world.landing_requests.append(request)
            world.open_attempts += 1
            raise ApplicationError(
                str(world.error), type=PUSH_FAILED
            ) from world.error

        return inherited + [open_landing_pr]


def _rendered_line(status: Any) -> str:
    """The one line `ergane build status` prints for the node."""
    payload = default_data_converter().payload_converter.to_payload(status)
    document: dict[str, Any] = json.loads(payload.data)
    rendered = render_status(EPIC_ID, document, "COMPLETED")
    lines = [line for line in rendered.splitlines() if line.startswith(NODE)]
    assert len(lines) == 1, f"expected one '{NODE}' line in:\n{rendered}"
    return lines[0]


async def test_the_nodes_terminal_reason_names_the_refusal(
    env: WorkflowEnvironment, refusal: Refusal
) -> None:
    """The reading an operator gets is git's verdict, not the SDK's category.

    The node verifies, the landing's push is refused, and the node ends. What it
    ends *saying* is the whole story: before this change the record and the
    rendered line both read "Activity task failed", which is true of every
    failing activity in the factory and therefore diagnoses none of them.

    Nothing is asserted here about how many times the activity was tried or which
    terminal the node reached. Both are US3's to change, and a control that
    pinned them would make a sibling story edit this file to land.
    """
    script = RefusedPushWorld(
        {NODE: [passing()]}, client=env.client, error=refusal.error
    )

    status = await run_epic(env, script, graph=one_node())

    assert script.open_attempts >= 1, "the landing never tried to push"

    reason = status.nodes[NODE].terminal_reason or ""
    assert reason, "the node ended with no reason at all"
    assert GENERIC not in reason, (
        f"the reason is still the SDK's category, not git's: {reason!r}"
    )
    assert flat(refusal.rejection) in flat(reason), (
        f"the reason does not name the refusal.\nreason: {reason!r}"
    )
    assert BRANCH in reason

    # And it is readable where an operator actually reads it.
    line = _rendered_line(status)
    assert flat(refusal.rejection) in flat(line)
    assert GENERIC not in line


# --- T012 [US2] (spec US2-S3, FR-006, plan trap 4) ----------------------------


def test_a_successful_push_is_no_noisier_than_it_was(
    repo: Path,
    factory_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The control: the diagnosis is bought on the failure path only.

    `--quiet` is still passed, and the push subprocess still writes nothing —
    asserted at the subprocess rather than inferred from the flag, because "no
    more output than today" is a fact about what the landing emits, and a remedy
    that kept the flag while teeing git's output somewhere would satisfy the flag
    and not the requirement.
    """
    _origin(repo, tmp_path)
    worktree = _prepare(repo, factory_root)

    pushes: list[subprocess.CompletedProcess[str]] = []
    argvs: list[list[str]] = []
    real_run = subprocess.run

    def spy(args: Any, *a: Any, **k: Any) -> Any:
        completed = real_run(args, *a, **k)
        if isinstance(args, list) and "push" in args:
            argvs.append(list(args))
            pushes.append(completed)
        return completed

    monkeypatch.setattr(subprocess, "run", spy)

    pushed = push_branch(repo, EPIC_ID, NODE, factory_root=factory_root)

    assert pushed == git(worktree, "rev-parse", "HEAD").strip()
    assert len(argvs) == 1, f"expected exactly one push subprocess, got {argvs}"
    assert "--quiet" in argvs[0], (
        "the push stopped being quiet; every successful landing now pays for the "
        f"failure path's diagnosis: {argvs[0]}"
    )

    completed = pushes[0]
    assert completed.returncode == 0
    assert completed.stdout == ""
    assert completed.stderr == "", (
        f"a successful push wrote to stderr: {completed.stderr!r}"
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
