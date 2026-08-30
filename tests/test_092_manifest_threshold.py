"""The refusal threshold is a manifest key, and its floor is the judge's budget.

US1 split one constant into two names. This story hands the second one to the
operator: `diff_refusal_bytes` in the target repo's manifest is the size above
which that repository refuses to build a story, and until it existed the only
way to move that size was to edit `factory/verify/diffbounds.py` — which is not
a thing an operator of a target repo can do at all.

Four things are proven here, and the awkward one is the third:

- **The declared value is what the check refuses at** (US2-S1). Proven twice,
  because "declared" has two halves and each can be right while the other is
  wrong: `test_a_declared_threshold_is_what_the_check_refuses_at` shows the
  loaded number changing the outcome of a real worktree, and
  `test_the_declared_threshold_reaches_the_output_check` runs an epic under
  Temporal and reads the `CheckOutputInput` the workflow actually built. A
  manifest key nothing threads is a manifest key that does nothing.
- **A manifest that declares nothing behaves exactly as it did** (US2-S2). This
  is the control, and it is written over the *corpus* rather than over one
  hand-built manifest (plan trap 8): every `ergane.yaml`, every legacy
  `factory.yaml` and every fixture manifest in this repository omits the key, so
  the whole population is available to say so, including the three that are
  refused today and must go on being refused for the same rule.
- **A threshold below the attention budget is refused at load time** (US2-S3,
  plan trap 4). Not defensive tidiness: a repository that refuses at less than
  the size `prepare_diff` abridges to refuses every diff the judge would merely
  have abridged, which is this spec's own defect wearing a manifest key as a
  disguise. The floor is `DIFF_INPUT_LIMIT` and the refusal names both numbers,
  because an operator who typed 32768 needs to be told what they collided with.
- **A near-miss is refused in the shape the ladder's numeric keys are refused**
  (US2-S4): a `_type` rung and a `_min` rung, each naming the offending value.

Sizes come from the two constants, never from 65536 — the reason
`tests/test_diff_size.py` and `tests/test_092_two_limits.py` both give: they are
tuned values, one has moved already, and a test pinning the number turns the
next tuning into a false failure.
"""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator, Callable

import pytest
from temporalio.testing import WorkflowEnvironment

from factory.config import WriteScope
from factory.verify.diffbounds import (
    DIFF_INPUT_LIMIT,
    DIFF_REFUSAL_THRESHOLD,
    size_refusal,
)
from factory.verify.diffcheck import check_output
from factory.verify.factory_yaml import (
    LEGACY_MANIFEST_NAME,
    MANIFEST_NAME,
    FactoryConfigError,
    load_loop_config,
    parse_factory_config,
)
from factory.workgraph.worktree import diff as worktree_diff
from tests.test_092_two_limits import RAISED_THRESHOLD, between_the_limits, measured
from tests.test_diff_size import (
    BULK_FILE,
    TRACKED_FILE,
    WORK,
    base_of,
    commit,
    payload,
    write,
)
from tests.test_interpreter import (
    ScriptedWorld,
    make_graph,
    make_node,
    passing,
    run_epic,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The manifest key this story adds. Spelled once here so the corpus control can
#: assert its absence from files it does not otherwise read.
THRESHOLD_KEY = "diff_refusal_bytes"

#: Every manifest this repository commits, discovered rather than listed, so a
#: fixture added next month joins the control without anyone remembering to add
#: it (plan trap 8). Both filenames, because the legacy one is still honoured.
CORPUS = tuple(
    sorted(
        {REPO_ROOT / MANIFEST_NAME, REPO_ROOT / LEGACY_MANIFEST_NAME}
        | set((REPO_ROOT / "tests" / "fixtures").rglob(MANIFEST_NAME))
        | set((REPO_ROOT / "tests" / "fixtures").rglob(LEGACY_MANIFEST_NAME))
        | set((REPO_ROOT / "tests" / "fixtures" / "target_repo" / "manifests").glob("*.yaml"))
    )
)

#: The corpus manifests that are refused today, and the rule each is refused
#: for. Three fixtures exist precisely to be rejected, so "loads exactly as it
#: does today" has to include them: a story that made one of them *parse* would
#: have broken the schema every bit as much as one that made a valid manifest
#: fail. A new invalid fixture belongs on this map, deliberately.
REFUSED_TODAY = {
    "forge-unknown.yaml": "forge",
    "malformed.yaml": "malformed_yaml",
    "unknown-gate.yaml": "gates",
}


def manifest_text(declaration: str = "") -> str:
    """The smallest valid manifest, with `declaration` appended verbatim.

    Deliberately minimal and hand-built: this is the *subject*, unlike the
    corpus, and a subject copied from a live file would drift with it.
    """
    return (
        "version: 1\n"
        "runtime: bwrap\n"
        "gates:\n"
        '  test: "uv run pytest -q"\n' + declaration
    )


def declaring(tmp_path: Path, declaration: str, *, name: str = "repo") -> Path:
    """A target-repo directory whose committed manifest carries `declaration`.

    A directory and a file is the whole of what the dispatch-time read needs:
    `load_loop_config` resolves the manifest by name and parses it, and nothing
    about the pin depends on the repository being a git one.
    """
    repo = tmp_path / name
    repo.mkdir(parents=True, exist_ok=True)
    (repo / MANIFEST_NAME).write_text(manifest_text(declaration), encoding="utf-8")
    return repo


def refusal_for(declaration: str) -> FactoryConfigError:
    """The error a manifest carrying `declaration` is refused with."""
    with pytest.raises(FactoryConfigError) as raised:
        parse_factory_config(manifest_text(declaration), source=MANIFEST_NAME)
    return raised.value


def grow_past(worktree: Path, nbytes: int) -> None:
    """Commit enough further work that this worktree's diff exceeds `nbytes`.

    A second commit on the same worktree rather than a second worktree: the diff
    is read against the node's base, so it grows with the work, and one branch
    point keeps "the same attempt, larger" as the only variable between two
    readings.
    """
    write(worktree, BULK_FILE, payload(nbytes + DIFF_INPUT_LIMIT))
    commit(worktree, "us2: and then a great deal more of it")


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    environment = await WorkflowEnvironment.start_time_skipping()
    try:
        yield environment
    finally:
        await environment.shutdown()


# --- US2-S1: the declared value is the one the check refuses at --------------


def test_a_declared_threshold_is_what_the_check_refuses_at(
    node_worktree: Callable[..., Path], tmp_path: Path
) -> None:
    """T009, US2-S1. The manifest's number, read from a manifest, changing a verdict.

    One worktree, three readings. Between the two limits it passes at the
    declared threshold and — the control that makes the first line mean
    something — fails at the default, so the declaration is demonstrably what
    moved the outcome rather than the outcome having been a pass all along. Then
    a worktree past the declared threshold, to show the ceiling was raised and
    not removed: it is refused, and the refusal quotes the operator's number
    rather than the tool's.

    Mutation: have `_read_diff_refusal_bytes` return the default whatever the
    manifest says, and the first assertion still passes while the third reports
    `DIFF_REFUSAL_THRESHOLD` as its limit.
    """
    repo = declaring(tmp_path, f"{THRESHOLD_KEY}: {RAISED_THRESHOLD}\n")
    _, _, declared = load_loop_config(repo)

    assert declared == RAISED_THRESHOLD, "the dispatch read is the operator's number"

    worktree, base = between_the_limits(node_worktree)

    assert DIFF_INPUT_LIMIT < measured(worktree_diff(worktree, base_ref=base)) < declared

    raised = check_output(
        worktree, WriteScope.WORKTREE, base_ref=base, diff_size_limit=declared
    )
    default = check_output(worktree, WriteScope.WORKTREE, base_ref=base)

    assert raised.size_refusal is None and raised.passed is True
    assert default.size_refusal is not None and default.passed is False

    grow_past(worktree, declared)
    refused = check_output(
        worktree, WriteScope.WORKTREE, base_ref=base, diff_size_limit=declared
    )

    assert refused.passed is False
    assert refused.size_refusal is not None
    assert refused.size_refusal.limit_bytes == declared
    assert refused.size_refusal.total_bytes > declared


async def test_the_declared_threshold_reaches_the_output_check(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """T009/T015, US2-S1. "When a node is verified", taken literally.

    The half a pure test cannot reach: a key an operator declares is worth
    nothing until the value is threaded from the manifest to the seam, and the
    seam had no production caller at all before this story
    (`factory/verify/diffcheck.py`'s `diff_size_limit`). So this runs a real
    epic and reads the `CheckOutputInput` the workflow built for it.

    The value is pinned at dispatch and rides `EpicInput`, the way 023 pinned
    the ladder and for the same reason (constitution IX): a node worktree that
    rewrote its own manifest would otherwise be voting on the size at which its
    own work is refused.

    Mutation: drop the argument from the workflow's `CheckOutputInput` and this
    reports the default while every parser test stays green.
    """
    repo = declaring(tmp_path, f"{THRESHOLD_KEY}: {RAISED_THRESHOLD}\n")
    _, _, declared = load_loop_config(repo)

    script = ScriptedWorld({"us1": [passing()]}, client=env.client)
    await run_epic(
        env,
        script,
        graph=make_graph([make_node("us1", "US1")]),
        diff_refusal_bytes=declared,
    )

    assert [request.diff_size_limit for request in script.output_requests] == [declared]


# --- US2-S2: the control, over the corpus ------------------------------------


def test_every_manifest_in_the_corpus_loads_exactly_as_it_does_today() -> None:
    """T010, US2-S2, plan trap 8. The population that omits the key.

    Not one hand-built manifest: every manifest this repository commits, the
    valid ones and the three written to be refused. The valid ones must parse
    and resolve to today's threshold; the invalid ones must still fail, and for
    the rule they failed for before — a key that made `malformed.yaml` parse
    would be as much a regression as one that broke `ergane.yaml`.

    The absence of the key from the corpus is asserted rather than assumed. If a
    fixture ever declares it, this test is measuring something other than the
    undeclared case and should say so out loud rather than pass quietly.

    Mutation: give `_read_diff_refusal_bytes` a default of its own — any number
    that is not `DIFF_REFUSAL_THRESHOLD` — and every valid manifest in the
    corpus reports it here.
    """
    assert len(CORPUS) >= 12, f"the corpus discovery found only {len(CORPUS)} files"
    assert REPO_ROOT / MANIFEST_NAME in CORPUS, "this repository's own manifest"
    assert REPO_ROOT / LEGACY_MANIFEST_NAME in CORPUS, "the legacy name, still honoured"

    resolved: dict[str, int] = {}
    refused: dict[str, str] = {}
    for path in CORPUS:
        text = path.read_text(encoding="utf-8")

        assert THRESHOLD_KEY not in text, f"{path} declares the key this test omits"

        try:
            config = parse_factory_config(text, source=path.name)
        except FactoryConfigError as error:
            refused[path.name] = error.rule
            continue
        resolved[path.name] = config.diff_refusal_bytes

    assert resolved, "no manifest in the corpus parsed; the control is vacuous"
    assert set(resolved.values()) == {DIFF_REFUSAL_THRESHOLD}
    assert refused == REFUSED_TODAY, (
        "a corpus manifest changed which rule refuses it; if a new invalid "
        "fixture was added, put it on REFUSED_TODAY deliberately"
    )


def test_an_undeclared_threshold_refuses_where_it_refuses_today(
    node_worktree: Callable[..., Path],
) -> None:
    """T010, US2-S2's second half: loading unchanged is not behaving unchanged.

    The corpus test proves the number that comes out of a manifest declaring
    nothing. This one spends that number on the check, either side of it, so
    "the default applies" is a statement about a verdict and not only about a
    parsed field.

    Mutation: resolve an absent key to `None` — which reads as "no limit" at the
    seam — and the second half of this test stops refusing anything.
    """
    config = parse_factory_config(manifest_text(), source=MANIFEST_NAME)

    assert config.diff_refusal_bytes == DIFF_REFUSAL_THRESHOLD == DIFF_INPUT_LIMIT

    worktree = node_worktree()
    base = base_of(worktree)
    write(worktree, TRACKED_FILE, WORK)
    commit(worktree, "us2: ordinary work, well under the default")

    kept = check_output(
        worktree,
        WriteScope.WORKTREE,
        base_ref=base,
        diff_size_limit=config.diff_refusal_bytes,
    )

    assert kept.size_refusal is None and kept.passed is True

    grow_past(worktree, config.diff_refusal_bytes)
    refused = check_output(
        worktree,
        WriteScope.WORKTREE,
        base_ref=base,
        diff_size_limit=config.diff_refusal_bytes,
    )

    assert refused.passed is False
    assert refused.size_refusal is not None
    assert refused.size_refusal.limit_bytes == DIFF_REFUSAL_THRESHOLD


# --- US2-S3: a threshold under the budget is the defect renamed --------------


def test_a_threshold_below_the_attention_budget_is_refused_naming_both() -> None:
    """T011, US2-S3, plan trap 4. The misconfiguration that must not ship.

    A repository refusing at less than the size `prepare_diff` abridges to
    refuses every diff the judge would merely have abridged — today's defect
    with a manifest key on it — so the floor is the attention budget and the
    message carries both numbers: the one the operator typed and the one it
    collided with. Naming only the floor leaves them hunting for their own
    value; naming only their value explains nothing.

    The boundary is asserted in both directions, because a floor written `<=`
    would refuse the one setting an operator is most likely to try first: the
    budget exactly.
    """
    error = refusal_for(f"{THRESHOLD_KEY}: {DIFF_INPUT_LIMIT - 1}\n")

    assert error.rule == f"{THRESHOLD_KEY}_min"
    assert str(DIFF_INPUT_LIMIT - 1) in error.problem, "the operator's own value"
    assert str(DIFF_INPUT_LIMIT) in error.problem, "and what it collided with"
    assert MANIFEST_NAME in str(error)

    at_the_floor = parse_factory_config(
        manifest_text(f"{THRESHOLD_KEY}: {DIFF_INPUT_LIMIT}\n"), source=MANIFEST_NAME
    )

    assert at_the_floor.diff_refusal_bytes == DIFF_INPUT_LIMIT


# --- US2-S4: near-misses, in the ladder's shape ------------------------------


@pytest.mark.parametrize(
    "declared",
    ['"131072"', "131072.0", "true", "null", '"128 KiB"'],
    ids=["string", "float", "bool", "null", "prose"],
)
def test_a_non_integer_threshold_is_refused_naming_the_value(declared: str) -> None:
    """T012, US2-S4. Every near-miss YAML makes easy, refused with the value shown.

    `true` has its own entry for the reason `_read_version` and `_read_ladder`
    give: `isinstance(True, int)` is True in Python, so a bool has to be
    excluded by type identity or `diff_refusal_bytes: true` becomes a ceiling of
    one byte. `null` is here for plan trap 5: `None` at the seam means *the
    check is disabled*, and a manifest that could spell that would have no
    ceiling at all while appearing to declare one.
    """
    error = refusal_for(f"{THRESHOLD_KEY}: {declared}\n")

    assert error.rule == f"{THRESHOLD_KEY}_type"
    assert THRESHOLD_KEY in error.problem


def test_a_negative_threshold_is_refused_in_the_ladder_s_shape() -> None:
    """T012, US2-S4. The same two rungs the ladder's integer dials are refused on.

    A negative threshold is below every floor, so it is the floor rung that
    catches it — `ladder_max_attempts_min`'s counterpart — and the type rung
    catches the rest. Rather than asserting a wording this test cannot own, it
    compares the two refusals against the ladder's own for the same two
    mistakes: same rule suffixes, same `gives ...` opening, same rendered value.

    Mutation: fold both refusals into one `type(value) is not int or value < 0`
    and the shape check fails on the missing `_min` rung.
    """
    mine_type = refusal_for(f'{THRESHOLD_KEY}: "3"\n')
    mine_min = refusal_for(f"{THRESHOLD_KEY}: -1\n")
    ladder_type = refusal_for('version: 2\nladder:\n  max_attempts: "3"\n')
    ladder_min = refusal_for("version: 2\nladder:\n  max_attempts: 0\n")

    assert (mine_type.rule, ladder_type.rule) == (
        f"{THRESHOLD_KEY}_type",
        "ladder_max_attempts_type",
    )
    assert (mine_min.rule, ladder_min.rule) == (
        f"{THRESHOLD_KEY}_min",
        "ladder_max_attempts_min",
    )
    for mine, ladder in ((mine_type, ladder_type), (mine_min, ladder_min)):
        assert mine.problem.startswith("gives ") == ladder.problem.startswith("gives ")
        assert mine.source == ladder.source

    assert "-1" in mine_min.problem, "the offending value, rendered"
