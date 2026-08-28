"""114-US1: the live-epic smoke's own repository onboards.

The smoke in `tests/test_live_epic.py` costs an operator real minutes and real
model spend, so it runs only under `-m live_epic` with a proxy, a `claude`
binary and a Temporal server present. That is the right price for what it
proves — and it is why, between 2026-08-15 and 2026-08-27, nobody noticed that
its scratch repository had stopped being dispatchable at all. `011-agent-sandbox`
changed the value domain of `runtime:` from a container image to a sandbox
backend name (`_read_runtime`, `factory/verify/factory_yaml.py:294`), the
smoke's manifest went on declaring `python:3.11-bookworm`, and every epic
dispatched against it would have died at the onboarding gate before a virtual
key was issued. Twelve days of green suites said nothing, because nothing cheap
ever read that manifest.

These tests are the two-second version of the ten-minute one. They carry no
`live_epic` marker and read no environment: they build the smoke's scratch
repository through the smoke's *own* builder, run the real manifest loader and
the real onboarding over it, and assert on the `EpicInput` the smoke's own
`start` constructs. Nothing here is a copy of the code under test — the backend
name comes from `SUPPORTED_BACKENDS` and the landing-only predicate is
imported from the workflow — because a fixture that agrees with the code by
coincidence is exactly the defect that produced this story.

Two independent blockers stood between the smoke and a dispatch, and both are
pinned below:

- the manifest declared a runtime the loader refuses (`factory_yaml`);
- the scratch repository has no git remote, so the forge cannot read it
  (`repo_read`). That one is not fixed by editing the repository — it is
  answered by dispatching in the halting mode 109-US3 built for precisely this
  situation, where an epic that will never open a proposal is not judged by the
  checks that describe landing.

Verification evidence (constitution VIII; US1-S4, FR-003, SC-001)
-----------------------------------------------------------------

The offline onboarding transcript, produced by building the smoke's scratch repo
through `build_scratch_repo` and calling the real `onboard_target_repo`. No
proxy, no agent, no Temporal server, no network — about two seconds each.

**Before** (at 1045370, the manifest declaring the pre-`011-agent-sandbox` value):

.. code-block:: text

    manifest declares 'runtime: python:3.11-bookworm'
    passed: False
      [FAIL] repo_read: could not read the repo via its forge (GH_REFUSED): To
        get started with GitHub CLI, please run: gh auth login ...
      [FAIL] factory_yaml: manifest failed to load: /tmp/.../factory.yaml:
        [runtime] declares `runtime: 'python:3.11-bookworm'`; the supported
        backend is `bwrap`
    after --halt-after-pass filter -> remaining failures: 1
      [BLOCKS] factory_yaml: manifest failed to load: /tmp/.../factory.yaml:
        [runtime] declares `runtime: 'python:3.11-bookworm'`; the supported
        backend is `bwrap`
    PASSES ONBOARDING UNDER HALT: False

**After** (this branch):

.. code-block:: text

    manifest declares 'runtime: bwrap'
    passed: False
      [FAIL] repo_read: could not read the repo via its forge (GH_REFUSED): To
        get started with GitHub CLI, please run: gh auth login ...
    after --halt-after-pass filter -> remaining failures: 0
    PASSES ONBOARDING UNDER HALT: True

Both findings are real and independent: correcting the manifest alone still
leaves `repo_read` fatal, and halting mode alone still leaves `factory_yaml`
fatal. The `repo_read` detail differs from the one `plan.md` recorded ("no git
remotes found") only because this host's `gh` is unauthenticated and complains
about that first; either way it is the same forge refusal, the same `repo_read`
check, and the same landing-only classification.

**Nothing the smoke asserts changed** (FR-003). The twelve tests in
`tests/test_live_epic.py`, collected on this branch, all unmodified —
`git diff 1045370 HEAD -- tests/test_live_epic.py` touches no test function, no
assertion and no fixture, only `manifest_source`'s runtime line, `start`'s
`EpicInput`, one import and two docstrings:

.. code-block:: text

    $ uv run pytest tests/test_live_epic.py --collect-only -q
    tests/test_live_epic.py::test_the_node_passed_and_the_epic_completed
    tests/test_live_epic.py::test_the_node_passed_on_its_first_attempt
    tests/test_live_epic.py::test_the_branch_holds_the_salvage_commit_for_the_attempt
    tests/test_live_epic.py::test_the_branch_carries_the_agent_s_work
    tests/test_live_epic.py::test_the_worktree_was_swept_and_the_branch_outlived_it
    tests/test_live_epic.py::test_the_attempt_has_its_ledger_row
    tests/test_live_epic.py::test_the_attempt_has_its_verification_row
    tests/test_live_epic.py::test_the_gate_the_repository_declared_is_the_gate_that_ran
    tests/test_live_epic.py::test_the_attempt_s_stdout_was_archived
    tests/test_live_epic.py::test_the_agent_s_session_transcript_was_found_and_archived
    tests/test_live_epic.py::test_factory_epic_status_reports_what_the_workflow_reported
    tests/test_live_epic.py::test_no_stored_byte_of_the_epic_repeats_the_master_key

    12 tests collected in 0.11s

The three that could plausibly have been disturbed by halting mode — the salvage
commit on the branch, the branch carrying the agent's work, and the swept
worktree — are precisely what `factory/workgraph/workflow.py:2179-2193` does
before it stops at PASSED.

**Full suite, before and after** — the five new tests here, and nothing else
moved:

.. code-block:: text

    $ uv run pytest -q      # at 1045370
    5055 passed, 57 skipped, 6 warnings in 332.84s (0:05:32)

    $ uv run pytest -q      # this branch
    5060 passed, 57 skipped, 7 warnings in 338.05s (0:05:38)

(The warning tally is run-to-run noise — pytest dedupes by first location, and a
repeat of the "after" run reported `5060 passed, 57 skipped, 6 warnings`. The
claim here is about the passed and skipped counts.)

The skip count is identical: the live tier still skips without credentials, and
the five tests added here are not in it. That is the point — before this branch,
whether the smoke could dispatch at all was proven by nothing a credential-free
`uv run pytest -q` executed.
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from typing import Any

import pytest

from factory.activities.merge_activities import _forge, onboard_target_repo
from factory.mergequeue.models import Finding
from factory.verify.factory_yaml import (
    SUPPORTED_BACKENDS,
    FactoryConfigError,
    load_factory_config,
    resolve_manifest_path,
)
from factory.workgraph.workflow import EpicInput, _is_landing_only_check

from tests import test_live_epic as smoke

#: Deliberately not marked `live_epic`: FR-004's whole value is that this runs
#: when nothing else in the tier does (plan trap T4). If a guard, a credential
#: or a network call ever appears in this module, it becomes a second invisible
#: test and this story has produced nothing.


@pytest.fixture
def scratch_repo(tmp_path: Path) -> Path:
    """The smoke's scratch target repository, built by the smoke's own builder.

    Calling `build_scratch_repo` rather than re-writing its files is the point:
    a second copy of the manifest in this module would go green while the
    smoke's went on being undispatchable.
    """
    return smoke.build_scratch_repo(tmp_path / "target-repo")


def test_the_smoke_s_manifest_loads(scratch_repo: Path) -> None:
    """US1-S1: the real loader accepts the repository the smoke dispatches against.

    `onboard_target_repo` reads this manifest through `load_factory_config`, and
    a `FactoryConfigError` there is a failing `factory_yaml` finding, which is a
    failing profile, which is `GRAPH_INVALID` before any key is issued
    (`factory/workgraph/workflow.py:1098`).
    """
    manifest, _name = resolve_manifest_path(scratch_repo)
    try:
        config = load_factory_config(manifest)
    except FactoryConfigError as error:
        pytest.fail(
            "the live-epic smoke's own manifest does not load, so every epic "
            f"dispatched against its scratch repo dies at the onboarding gate: {error}"
        )
    assert smoke.GATE_NAME in config.gates, (
        f"the smoke's manifest declares gates {sorted(config.gates)}, and the "
        f"gate its spec tells the node to turn green is {smoke.GATE_NAME!r}"
    )


def test_the_manifest_s_backend_is_read_from_the_supported_tuple(
    scratch_repo: Path,
) -> None:
    """US1-S2: the declared backend is derived, not restated (plan trap T2).

    Two assertions, because the first alone is satisfied by a fixture that
    hardcodes today's value: the loaded runtime must equal `SUPPORTED_BACKENDS[0]`
    read from the tuple *here*, and `manifest_source` must not contain any
    supported backend's name as a literal. The next tightening of that tuple
    then fails where it is made, rather than twelve days later at dispatch.
    """
    manifest, _name = resolve_manifest_path(scratch_repo)
    config = load_factory_config(manifest)
    assert config.runtime == SUPPORTED_BACKENDS[0], (
        f"the smoke declares `runtime: {config.runtime!r}` while the supported "
        f"backends are {SUPPORTED_BACKENDS!r}"
    )

    source = inspect.getsource(smoke.manifest_source)
    for backend in SUPPORTED_BACKENDS:
        assert backend not in source, (
            f"`manifest_source` writes the backend name {backend!r} as a literal; "
            "it must interpolate SUPPORTED_BACKENDS so the fixture tracks the "
            "tuple by construction rather than by coincidence"
        )
    assert "SUPPORTED_BACKENDS" in source, (
        "`manifest_source` names no backend literal and does not read "
        "SUPPORTED_BACKENDS either — the runtime it declares comes from nowhere "
        f"this test can hold to {SUPPORTED_BACKENDS!r}"
    )


class _CapturingClient:
    """A Temporal client that records the dispatch instead of sending it.

    The point of US1-S3's check is that it costs nothing and therefore actually
    runs: the assertion is on the `EpicInput` the smoke constructs, not on a run
    that needs a server, a proxy and ten minutes.
    """

    def __init__(self) -> None:
        self.workflow: Any = None
        self.epic_input: Any = None
        self.kwargs: dict[str, Any] = {}

    async def start_workflow(
        self, workflow: Any, epic_input: Any, /, **kwargs: Any
    ) -> Any:
        self.workflow = workflow
        self.epic_input = epic_input
        self.kwargs = kwargs
        return object()  # the handle; this test reads none of it


def _config() -> Any:
    """A `LiveConfig` with nothing real in it — `start` only passes it through."""
    return smoke.LiveConfig(
        proxy_url="http://127.0.0.1:1",
        master_key="not-a-key",
        model_alias="not-an-alias",
        address="127.0.0.1:1",
        namespace="ergane",
        timeout_s=1,
    )


def _workspace(root: Path) -> Any:
    """A `Workspace` shaped like the smoke's, addressing nothing that must exist."""
    epic_id = "live-epic-0"
    return smoke.Workspace(
        epic_id=epic_id,
        target_repo=root / "target-repo",
        specs_root=root / "specs",
        spec_dir=root / "specs" / epic_id,
        factory_root=root / ".factory",
        ledger_path=root / ".factory" / "ledger.db",
        verification_db=root / ".factory" / "verification.db",
        task_queue=f"workgraph-{epic_id}",
    )


def test_the_smoke_dispatches_in_halting_mode(tmp_path: Path) -> None:
    """US1-S3: `start` constructs an `EpicInput` that halts at PASSED.

    The scratch repository has no git remote and never will — it is minted per
    run by `git init`, there is no forge to open a proposal on, and the smoke
    asserts nothing above PASSED. Halting mode is the accurate description of
    that epic, and it is what keeps the forge-dependent `repo_read` finding from
    disqualifying the dispatch (109-US3, FR-012).
    """
    client = _CapturingClient()
    asyncio.run(smoke.start(client, _config(), _workspace(tmp_path), object()))

    assert isinstance(client.epic_input, EpicInput), (
        "the smoke's `start` no longer dispatches an EpicInput; this test reads "
        f"the second positional argument, which was {client.epic_input!r}"
    )
    assert client.epic_input.halt_after_pass is True, (
        "the live-epic smoke dispatches with halt_after_pass=False against a "
        "repo with no remote, so onboarding's `repo_read` finding disqualifies "
        "it and the epic never starts"
    )


def _surviving_failures(findings: tuple[Finding, ...]) -> list[Finding]:
    """The failures that still block a dispatch made with `halt_after_pass=True`.

    `_is_landing_only_check` is imported rather than restated (FR-005): a second
    copy of `_LANDING_ONLY_CHECKS` in a test is two lists that drift while both
    stay green, and the day a fifth landing check is added this filter follows it.
    """
    return [
        finding
        for finding in findings
        if not finding.passed and not _is_landing_only_check(finding.check)
    ]


def test_onboarding_clears_the_smoke_s_repository(scratch_repo: Path) -> None:
    """US1-S3: the real onboarding, over the real repo, leaves nothing blocking.

    No proxy, no agent, no Temporal server and no network: `onboard_target_repo`
    reads the clone's manifest and asks a forge about a repository with no
    remote, and the forge refuses locally. The refusal is a `repo_read` finding,
    which is landing-only, which is why the filter above is the whole of what
    halting mode changes here.

    The message names every survivor with its check and its detail (FR-006):
    `assert profile.passed` would say that something is wrong and nothing about
    which of two independent blockers to go and fix.
    """
    profile = onboard_target_repo(
        _forge(repo_path=str(scratch_repo)), str(scratch_repo)
    )
    survivors = _surviving_failures(profile.findings)
    assert not survivors, (
        "the live-epic smoke's scratch repo does not onboard even in halting "
        "mode; these findings survive the landing-only filter:\n"
        + "\n".join(f"  [FAIL] {f.check}: {f.detail}" for f in survivors)
    )


def test_the_filter_is_what_clears_the_repository(scratch_repo: Path) -> None:
    """The filter above is load-bearing, not decorative (plan trap T5).

    A test that asserts "nothing survives" is vacuously green if onboarding
    returned no failing findings at all. It does return one — the forge cannot
    read a repository with no remote — so this asserts the unfiltered profile
    still fails and that every failure it carries is landing-only. If a future
    change makes the scratch repo readable, this test says so out loud rather
    than letting the one above quietly stop proving anything.
    """
    profile = onboard_target_repo(
        _forge(repo_path=str(scratch_repo)), str(scratch_repo)
    )
    failures = [f for f in profile.findings if not f.passed]
    assert failures, (
        "onboarding now passes the smoke's remote-less scratch repo outright; "
        "the landing-only filter above no longer proves anything"
    )
    assert not profile.passed, "a profile carrying failing findings claims to pass"
    assert all(_is_landing_only_check(f.check) for f in failures), (
        "onboarding fails the smoke's repo for something other than landing:\n"
        + "\n".join(f"  [FAIL] {f.check}: {f.detail}" for f in failures)
    )
