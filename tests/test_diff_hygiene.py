"""What a node's diff may not carry — and why `.gitignore` could not stop it.

Overnight 2026-08-14→15 the agents working `033-ergane-install/us1` and
`034-ergane-init/us1` committed their own session homes — `.ergane/homes/`,
18 files, 2.0 MB — into their node worktrees. Eight consecutive judge scorings
across two epics then read archive noise instead of code, every one of them
flagged `truncated_input`, every one of them confidently describing work as
absent that the truncation had hidden. One of those blind verdicts told a us2
agent to "re-do the work on the correct branch", and it committed straight onto
the operator's checkout. The verdicts were not wrong about the diff they saw.
They were wrong about the work.

Prospectively adding `.ergane/` to `.gitignore` (`f6f5a67`) could not close the
class, and this file exists to prove why rather than to assert it: the
incident's files were **tracked**, and git reports a tracked file as clean no
matter what pattern it matches — unless it is asked with `--no-index`. That
asymmetry is re-run inside the suite by
`test_plain_check_ignore_reports_a_tracked_file_as_clean`, against a fixture
that commits the file first, because a fixture that left it untracked would
prove nothing at all: untracked-and-ignored is the one case plain
`check-ignore` gets right.

So the check has to be the factory's rather than git's, and it has two rules,
because the incident needed both:

- **The target's own ignore rules**, evaluated with `--no-index` so tracked
  status cannot hide a match. This is what catches a committed `__pycache__`
  or a committed gate log.
- **The runtime roots**, `.ergane/` and the legacy `.factory/`, by prefix. This
  is what catches the incident itself: the fixture target repo's `.gitignore`
  never mentions `.ergane/`, and neither did this repository's on the night, so
  no ignore rule of any kind would have refused those eighteen files.

Two exemptions are load-bearing and are pinned here as tests rather than left
to inference. Untracked *ignored* files — build noise, gate logs — are not in
the diff, so they neither manufacture one (the rule 002 already had) nor fail
hygiene (the rule this adds). And the read scope, whose personas may run with
`needs_worktree: false` and no repository at all, is not hygiene-checked in
either direction.

Real git throughout, on the `tests/fixtures/target_repo/` skeleton: the whole
subject is what git says about a real worktree, and a fake would only prove the
fake agrees with itself.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable

import pytest

from factory.config import WriteScope
from factory.verify.diffcheck import (
    HygieneViolation,
    WorktreeMissingError,
    check_output,
    hygiene_violations,
    runtime_root_prefixes,
)
from factory.verify.models import (
    CriteriaSet,
    GateResult,
    GateStatus,
    OutputCheck,
    OverallVerdict,
    Requirement,
    RequirementKind,
    Scenario,
    VerificationForm,
    VerificationResult,
    compose_result,
    judge_required,
)
from factory.verify.store import connect, node_history, upsert_result
from factory.workgraph.worktree import DEFAULT_RUNTIME_ROOT, LEGACY_FACTORY_ROOT
from tests.target_repo import GATE_ORDER_LOG, add_worktree, git, git_env

#: A tracked source file, for "the agent did ordinary work" cases.
TRACKED_FILE = "src/calc.py"

#: The artifact a read-scoped node (researcher) declares.
REPORT = "reports/findings.md"

#: The shape the 2026-08-14 incident actually had: `<runtime root>/homes/
#: <epic>/<node>/…`, which is `home_path` (factory/workgraph/adapter.py:652)
#: resolved inside the worktree instead of beside it.
INCIDENT_HOME = ".ergane/homes/033-ergane-install/us1"
INCIDENT_FILES = {
    f"{INCIDENT_HOME}/.claude.json": '{"numStartups": 1, "projects": {}}\n',
    f"{INCIDENT_HOME}/.gitconfig": "[user]\n\tname = Ergane Factory\n",
    f"{INCIDENT_HOME}/.claude/projects/session.jsonl": '{"type":"user"}\n',
}


def write(worktree: Path, relative: str, text: str = "new content\n") -> Path:
    """Create or overwrite a file in the worktree, parents and all."""
    path = worktree / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def base_of(worktree: Path) -> str:
    """The commit the node branched from — `base_ref` as dispatch supplies it."""
    return git(worktree, "rev-parse", "HEAD").strip()


def commit(worktree: Path, message: str, *, force: bool = False) -> None:
    """Commit everything in the worktree, the way an agent following ralph does.

    `force` is what an agent reaches for when git declines to add an ignored
    path — and it is how the tracked-ignored case in US1-S2 comes about at all.
    """
    git(worktree, "add", *(("-f",) if force else ()), "-A")
    git(worktree, "commit", "--quiet", "-m", message)


def paths_of(violations: list[HygieneViolation]) -> set[str]:
    return {violation.path for violation in violations}


def check_ignore(worktree: Path, path: str, *flags: str) -> tuple[int, str]:
    """Ask git directly, so the tests can compare the factory against the source."""
    completed = subprocess.run(
        ["git", "-C", str(worktree), "check-ignore", "-v", *flags, path],
        capture_output=True,
        text=True,
        env=git_env(),
    )
    return completed.returncode, completed.stdout


# --- the asymmetry that makes this the factory's check and not git's --------


def test_plain_check_ignore_reports_a_tracked_file_as_clean(
    node_worktree: Callable[..., Path],
) -> None:
    """Trap 1, executed rather than cited: tracked files are invisible to it.

    The fixture repo ignores `.factory-gate-order.log`. Commit one with
    `git add -f` — which is exactly how the incident's homes became tracked —
    and git's own ignore query reports nothing:

        $ git check-ignore -v .factory-gate-order.log
        $ echo $?
        1
        $ git check-ignore -v --no-index .factory-gate-order.log
        .gitignore:4:.factory-gate-order.log   .factory-gate-order.log
        $ echo $?
        0

    A hygiene check that consulted the index would therefore report the entire
    2026-08-14 class clean. That is the whole reason `--no-index` is not an
    optimisation here but the mechanism.
    """
    worktree = node_worktree()
    write(worktree, GATE_ORDER_LOG, "lint test typecheck\n")
    commit(worktree, "an agent forces in an ignored file", force=True)

    tracked_code, tracked_out = check_ignore(worktree, GATE_ORDER_LOG)
    no_index_code, no_index_out = check_ignore(
        worktree, GATE_ORDER_LOG, "--no-index"
    )

    assert (tracked_code, tracked_out) == (1, ""), "git calls a tracked file clean"
    assert no_index_code == 0
    assert no_index_out.startswith(".gitignore:")
    assert f":{GATE_ORDER_LOG}\t{GATE_ORDER_LOG}\n" in no_index_out


# --- US1-S1: the 2026-08-14 incident, replayed ------------------------------


def test_a_committed_session_home_fails_the_output_check(
    node_worktree: Callable[..., Path],
) -> None:
    """SC-001. The eighteen files, in the shape they actually landed in.

    `has_diff` stays True because it is a fact about the worktree and the files
    are really there; `passed` is False because a diff carrying a session home
    is not a diff anyone can judge.
    """
    worktree = node_worktree()
    base = base_of(worktree)
    write(worktree, TRACKED_FILE, "def add(a, b):\n    return a + b\n")
    for relative, text in INCIDENT_FILES.items():
        write(worktree, relative, text)
    commit(worktree, "us1: the work, and the agent's own home")

    result = check_output(worktree, WriteScope.WORKTREE, base_ref=base)

    assert result.has_diff is True, "the files are there; that much is factual"
    assert result.passed is False
    assert paths_of(result.hygiene_violations) == set(INCIDENT_FILES)


def test_the_refusal_names_the_rule_that_refused_each_path(
    node_worktree: Callable[..., Path],
) -> None:
    """A path with no reason beside it sends the next attempt hunting.

    The fixture repo's `.gitignore` never mentions `.ergane/` — this repository's
    did not either on the night — so no ignore rule of any kind would have
    refused these files. The runtime-root prefix is what does, and the record
    has to say so.
    """
    worktree = node_worktree()
    base = base_of(worktree)
    write(worktree, list(INCIDENT_FILES)[0], "{}\n")
    commit(worktree, "us1: the home lands")

    ignore_code, _ = check_ignore(worktree, list(INCIDENT_FILES)[0], "--no-index")
    result = check_output(worktree, WriteScope.WORKTREE, base_ref=base)

    assert ignore_code == 1, "gitignore never had an opinion about this path"
    assert [violation.rule for violation in result.hygiene_violations] == [
        f"runtime root: {DEFAULT_RUNTIME_ROOT.name}/"
    ]


def test_the_legacy_runtime_root_is_refused_on_the_same_terms(
    node_worktree: Callable[..., Path],
) -> None:
    """FR-007. A node whose base predates the rename writes the old name.

    That is the entire population this check exists for — a node branched
    before `f6f5a67` cannot have the fixed `.gitignore` and cannot have the new
    root name either.
    """
    worktree = node_worktree()
    base = base_of(worktree)
    legacy = f"{LEGACY_FACTORY_ROOT.name}/homes/034-ergane-init/us1/.claude.json"
    write(worktree, legacy, "{}\n")
    commit(worktree, "us1: the legacy home lands")

    result = check_output(worktree, WriteScope.WORKTREE, base_ref=base)

    assert result.passed is False
    assert result.hygiene_violations == [
        HygieneViolation(path=legacy, rule=f"runtime root: {LEGACY_FACTORY_ROOT.name}/")
    ]


def test_the_runtime_root_prefixes_are_derived_not_restated() -> None:
    """FR-007: both names, from the resolver's own constants.

    043/US2 exists because one module hardcoded a single root literal. The
    prefixes are compared against `factory.workgraph.worktree`'s constants here
    so that renaming the root again moves this check with it.
    """
    assert set(runtime_root_prefixes()) >= {
        DEFAULT_RUNTIME_ROOT.name,
        LEGACY_FACTORY_ROOT.name,
    }


def test_an_uncommitted_session_home_is_refused_too(
    node_worktree: Callable[..., Path],
) -> None:
    """FR-001 says committed *or* uncommitted; salvage would commit it anyway."""
    worktree = node_worktree()
    write(worktree, f"{INCIDENT_HOME}/.claude.json", "{}\n")

    result = check_output(worktree, WriteScope.WORKTREE)

    assert result.passed is False
    assert paths_of(result.hygiene_violations) == {f"{INCIDENT_HOME}/.claude.json"}


def test_a_hygiene_failure_means_the_judge_is_never_asked(
    node_worktree: Callable[..., Path],
) -> None:
    """FR-002, the second half of US1-S1: no judge verdict is recorded.

    The mechanism is the one 002 already built — `judge_required` refuses to
    spend a completion once the output check has decided a FAIL no judge could
    lift — so hygiene rides it rather than adding a second place a FAIL is
    decided (plan trap 4). Asserted end to end, on the real composed result.
    """
    worktree = node_worktree()
    base = base_of(worktree)
    for relative, text in INCIDENT_FILES.items():
        write(worktree, relative, text)
    commit(worktree, "us1: the home lands")

    output = check_output(worktree, WriteScope.WORKTREE, base_ref=base)
    gates = [
        GateResult(
            name="test",
            command="uv run pytest -q",
            status=GateStatus.PASS,
            exit_code=0,
            duration_s=1.0,
            output_tail="1 passed\n",
        )
    ]
    criteria = CriteriaSet(
        feature="045-judge-diff-hygiene",
        spec_ref="specs/045-judge-diff-hygiene/spec.md",
        requirements=[
            Requirement(
                key="US1",
                kind=RequirementKind.STORY,
                title="A diff carrying ignore-pattern or runtime-root paths fails",
                priority="P1",
                body="",
                scenarios=[Scenario("US1-S1", ["Given", "When", "Then"], "…")],
            )
        ],
        source_path="specs/045-judge-diff-hygiene/spec.md",
        source_sha256="0" * 64,
        snapshotted_at="2026-08-15T00:00:00+00:00",
    )

    assert judge_required(gates, output, criteria) is False, "green gates, so only hygiene stops it"

    result = compose_result(
        epic_id="045-judge-diff-hygiene",
        node_id="us1",
        attempt=1,
        form=VerificationForm.PHASE,
        gate_results=gates,
        output_check=output,
        judge=None,
        criteria_sha256="0" * 64,
        spec_ref="specs/045-judge-diff-hygiene/spec.md",
        started_at="2026-08-15T00:00:00+00:00",
        finished_at="2026-08-15T00:01:00+00:00",
    )

    assert result.verdict == OverallVerdict.FAIL
    assert result.judge is None, "never ran is a different fact from ran and agreed"


# --- US1-S2: the tracked file its own repository ignores --------------------


def test_a_tracked_ignored_file_fails_naming_path_and_pattern(
    node_worktree: Callable[..., Path],
) -> None:
    """US1-S2. The case plain `check-ignore` reports clean, refused anyway.

    The recorded rule is compared against what git itself says under
    `--no-index`, rather than against a literal, so the assertion pins the
    *source* of the pattern (`<file>:<line>:<pattern>`) without pinning the
    fixture's line numbering.
    """
    worktree = node_worktree()
    base = base_of(worktree)
    write(worktree, TRACKED_FILE, "def add(a, b):\n    return a + b\n")
    write(worktree, GATE_ORDER_LOG, "lint test typecheck\n")
    commit(worktree, "us1: work, plus a gate log forced in", force=True)

    _, expected = check_ignore(worktree, GATE_ORDER_LOG, "--no-index")
    result = check_output(worktree, WriteScope.WORKTREE, base_ref=base)

    source, _, _ = expected.partition("\t")
    assert result.passed is False
    assert result.hygiene_violations == [
        HygieneViolation(path=GATE_ORDER_LOG, rule=source)
    ]
    # The pattern, not just the file it came from: "which rule refused this?"
    # is the question the next attempt has to answer.
    assert source.endswith(f":{GATE_ORDER_LOG}")
    assert source.startswith(".gitignore:")


# --- US1-S3: parity, which means byte parity --------------------------------


def test_an_ordinary_diff_produces_todays_output_check_exactly(
    node_worktree: Callable[..., Path],
) -> None:
    """US1-S3, trap 6. Equality against the value today's code constructs.

    `OutputCheck` is a frozen dataclass, so this compares every field: a
    hygiene field that defaulted to anything but empty, or a `passed` that
    moved, fails here rather than in a prompt three days later.
    """
    worktree = node_worktree()
    base = base_of(worktree)
    write(worktree, TRACKED_FILE, "def add(a, b):\n    return a + b\n")
    commit(worktree, "us1: ordinary work, committed as it goes")
    write(worktree, "src/new_module.py", "VALUE = 1\n")

    result = check_output(worktree, WriteScope.WORKTREE, base_ref=base)

    assert result == OutputCheck(
        write_scope=WriteScope.WORKTREE.value,
        has_diff=True,
        expected_artifacts=[],
        artifacts_present=None,
        passed=True,
    )


def test_an_untouched_worktree_produces_todays_output_check_exactly(
    node_worktree: Callable[..., Path],
) -> None:
    """The floor 002 built is untouched: no diff is still the FAIL it was."""
    worktree = node_worktree()

    result = check_output(worktree, WriteScope.WORKTREE)

    assert result == OutputCheck(
        write_scope=WriteScope.WORKTREE.value,
        has_diff=False,
        expected_artifacts=[],
        artifacts_present=None,
        passed=False,
    )


# --- US1-S4: untracked ignored files are nobody's work ----------------------


def test_untracked_ignored_noise_is_neither_a_diff_nor_a_violation(
    node_worktree: Callable[..., Path],
) -> None:
    """Trap 2, first half. Running the gates must not fail hygiene.

    `.factory-gate-order.log` is what the fixture's gate scripts append to on
    every run. It has never manufactured the diff FR-004 demands, and it must
    not start manufacturing a hygiene failure either.
    """
    worktree = node_worktree()
    write(worktree, GATE_ORDER_LOG, "lint test typecheck\n")

    result = check_output(worktree, WriteScope.WORKTREE)

    assert result.has_diff is False
    assert result.hygiene_violations == []
    assert result.passed is False, "for having no diff, exactly as before"


def test_untracked_ignored_noise_beside_real_work_still_passes(
    node_worktree: Callable[..., Path],
) -> None:
    """Trap 2, second half — the one that would break every gated node.

    Hygiene examines the paths that are *in* the diff. It does not go looking
    for ignored files on disk, or every attempt that ran its gates would be
    refused for the log the gates themselves wrote.
    """
    worktree = node_worktree()
    base = base_of(worktree)
    write(worktree, TRACKED_FILE, "def add(a, b):\n    return a + b\n")
    commit(worktree, "us1: ordinary work")
    write(worktree, GATE_ORDER_LOG, "lint test typecheck\n")

    result = check_output(worktree, WriteScope.WORKTREE, base_ref=base)

    assert result.hygiene_violations == []
    assert result.passed is True


# --- US1-S5 / FR-008: the read scope is untouched ---------------------------


def test_a_read_scope_node_with_no_git_is_untouched(tmp_path: Path) -> None:
    """US1-S5, trap 3. `judge` and `researcher` are `needs_worktree: false`.

    A hygiene check that asked git anything here would break every read-scope
    persona, because there is no repository to ask.
    """
    workdir = tmp_path / "scratch"
    workdir.mkdir()
    (workdir / "findings.md").write_text("# Findings\n", encoding="utf-8")

    result = check_output(workdir, WriteScope.READ, expected_artifacts=["findings.md"])

    assert result == OutputCheck(
        write_scope=WriteScope.READ.value,
        has_diff=False,
        expected_artifacts=["findings.md"],
        artifacts_present=True,
        passed=True,
    )


def test_a_read_scope_node_is_not_hygiene_checked(
    node_worktree: Callable[..., Path],
) -> None:
    """FR-008 in the direction that could bite: a read node with a real repo.

    Its verdict is the artifact's, and the diff is recorded as evidence and
    ignored as a criterion (R7). Hygiene may not quietly become a second
    criterion for a scope whose proof was never the diff.
    """
    worktree = node_worktree()
    write(worktree, REPORT, "# Findings\n\nThe proxy paginates at 100.\n")
    write(worktree, f"{INCIDENT_HOME}/.claude.json", "{}\n")

    result = check_output(worktree, WriteScope.READ, expected_artifacts=[REPORT])

    assert result.hygiene_violations == []
    assert result.passed is True


# --- FR-006: nothing fails open ---------------------------------------------


def break_exclude_file(worktree: Path) -> Path:
    """Make git unable to read the repository's ignore rules, for real.

    A linked worktree reads `info/exclude` from the *common* git directory, so
    replacing that file with a directory is a state git refuses to work in
    regardless of who is running the tests — no permission bit, no monkeypatch:

        $ printf 'README.md\\0' | git -C wt check-ignore -v -z --no-index --stdin
        fatal: cannot use …/repo/.git/info/exclude as an exclude file
        exit=128
    """
    common = Path(git(worktree, "rev-parse", "--git-common-dir").strip())
    exclude = common / "info" / "exclude"
    exclude.unlink(missing_ok=True)
    exclude.mkdir(parents=True)
    return exclude


def test_ignore_rules_git_cannot_read_are_not_a_pass(
    target_repo: Callable[..., Path], tmp_path: Path
) -> None:
    """FR-006, isolated to the hygiene read itself.

    The paths are handed in, so nothing else about the worktree is being
    consulted: the only question is what happens when git cannot answer the
    ignore question. An empty list of violations would be a pass-by-default,
    which is the one thing this component refuses everywhere.
    """
    worktree = add_worktree(target_repo("passing"), tmp_path / "wt")
    break_exclude_file(worktree)

    with pytest.raises(WorktreeMissingError) as excinfo:
        hygiene_violations(worktree, [TRACKED_FILE])

    assert str(worktree) in str(excinfo.value)


def test_check_output_refuses_a_worktree_whose_ignore_rules_are_unreadable(
    target_repo: Callable[..., Path], tmp_path: Path
) -> None:
    """The same state, end to end: an infrastructure failure, not a verdict.

    `WorktreeMissingError` is what the activity maps to `WORKTREE_MISSING`
    (contracts/activities.md), so the attempt budget is not charged for a git
    the worker could not get an answer out of.
    """
    worktree = add_worktree(target_repo("passing"), tmp_path / "wt")
    write(worktree, TRACKED_FILE, "def add(a, b):\n    return a + b\n")
    break_exclude_file(worktree)

    with pytest.raises(WorktreeMissingError):
        check_output(worktree, WriteScope.WORKTREE)


def test_a_read_scope_node_survives_unreadable_ignore_rules(
    target_repo: Callable[..., Path], tmp_path: Path
) -> None:
    """Trap 3 again: git's troubles cannot change a verdict that never asked it."""
    worktree = add_worktree(target_repo("passing"), tmp_path / "wt")
    write(worktree, REPORT, "# Findings\n")
    break_exclude_file(worktree)

    result = check_output(worktree, WriteScope.READ, expected_artifacts=[REPORT])

    assert result.artifacts_present is True
    assert result.passed is True


# --- trap 5: rows written before 045 are still rows --------------------------


def stored_result(output_check: OutputCheck) -> VerificationResult:
    """The smallest complete evidence bundle carrying one output check."""
    return compose_result(
        epic_id="epic-7",
        node_id="node-3",
        attempt=1,
        form=VerificationForm.PHASE,
        gate_results=[
            GateResult(
                name="test",
                command="uv run pytest -q",
                status=GateStatus.PASS,
                exit_code=0,
                duration_s=1.0,
                output_tail="1 passed\n",
            )
        ],
        output_check=output_check,
        judge=None,
        criteria_sha256="a" * 64,
        spec_ref="045-judge-diff-hygiene/US1",
        started_at="2026-08-15T10:00:00Z",
        finished_at="2026-08-15T10:03:00Z",
    )


def test_an_output_check_written_before_045_still_loads(tmp_path: Path) -> None:
    """Trap 5. `verification.db` is full of rows whose JSON predates this field.

    The row is rewritten to the exact five-key payload the store wrote before
    this story, so the assertion is about a real historical shape rather than
    about a shape this test invented.
    """
    conn = connect(tmp_path / "verification.db")
    passing = OutputCheck(
        write_scope=WriteScope.WORKTREE.value,
        has_diff=True,
        expected_artifacts=[],
        artifacts_present=None,
        passed=True,
    )
    row_id = upsert_result(conn, stored_result(passing))
    conn.execute(
        "UPDATE verification_results SET output_check = ? WHERE id = ?",
        (
            json.dumps(
                {
                    "write_scope": "worktree",
                    "has_diff": True,
                    "expected_artifacts": [],
                    "artifacts_present": None,
                    "passed": True,
                }
            ),
            row_id,
        ),
    )
    conn.commit()

    [loaded] = node_history(conn, "epic-7", "node-3")

    assert loaded.output_check == passing


def test_a_hygiene_failure_round_trips_through_the_evidence_store(
    tmp_path: Path,
) -> None:
    """The record has to survive, or the reason for the FAIL dies with the run.

    The retry prompt and the escalation summary are both built from the stored
    evidence, so a violation that did not round-trip would be a FAIL nobody
    could explain a day later.
    """
    conn = connect(tmp_path / "verification.db")
    refused = OutputCheck(
        write_scope=WriteScope.WORKTREE.value,
        has_diff=True,
        expected_artifacts=[],
        artifacts_present=None,
        passed=False,
        hygiene_violations=[
            HygieneViolation(
                path=f"{INCIDENT_HOME}/.claude.json",
                rule=f"runtime root: {DEFAULT_RUNTIME_ROOT.name}/",
            ),
            HygieneViolation(path=GATE_ORDER_LOG, rule=".gitignore:4:.factory-gate-order.log"),
        ],
    )
    upsert_result(conn, stored_result(refused))

    [loaded] = node_history(conn, "epic-7", "node-3")

    assert loaded.output_check == refused
    assert loaded.verdict == OverallVerdict.FAIL
