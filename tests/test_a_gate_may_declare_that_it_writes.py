"""A gate that is supposed to write says so (084 US3).

US1 made a gate that writes into the node worktree stop reading as PASS. Some
gates write on purpose — a lockfile refresh, a generated client — and a repo
whose green depends on one cannot use the factory at all unless it can say so.
This module holds that declaration to five properties, two of which are the
reason the story exists rather than the feature itself:

- **The declaration is visible in the evidence, not just in config.** A
  declared writer keeps PASS *and* still carries the paths on
  `worktree_writes`, flagged `writes_declared`. An opt-out nobody can see is how
  this defect returns wearing a config key, so the recording is asserted beside
  the passing.
- **Both gate-list runners honour it, or it is dead where it matters.**
  `_run_gate_list` and `_run_gate_list_from_config` are near-identical twins and
  which one a repo takes is decided by whether its worktree carries a candidate
  parser (`factory/verify/gates.py:1156`). The config runner is handed the whole
  `FactoryConfig` and gets a new field for free; the candidate runner is handed
  two views lifted off `_AcceptedConfig` and gets nothing. That second one is
  the runner Ergane's own nodes take — so a declaration that reaches only the
  first is parsed, stored, emitted and never read, which is
  `verify/readiness-proves-a-thing-is-declared-not-that-it-works` filed inside
  the spec written to close it. Both runners are asserted directly, and the
  candidate protocol is asserted end to end through `run_gates` over the JSON
  the parser CLI actually emits.

The controls are the other half. `false` is not a declaration, an unreadable
snapshot is not excused by one, a `writes:` entry naming a gate the manifest
does not declare is refused rather than silently applying to nothing, and a
manifest that declares no `writes:` key at all parses exactly as it does today —
which is every target repo's manifest that exists.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Mapping

import pytest

from factory.verify.factory_yaml import (
    MANIFEST_NAME,
    PARSE_CLI_OK,
    FactoryConfigError,
    load_factory_config,
    parse_factory_config,
)
from factory.verify.gates import (
    CandidateOutcome,
    SubprocessGateExecutor,
    _run_gate_list,
    _run_gate_list_from_config,
    run_gates,
)
from factory.verify.models import FactoryConfig, GateResult, GateStatus, gates_passed
from factory.verify.store import _gate_from_dict, _gate_to_dict

# The fixture topology is US1's, imported rather than re-cut: a throwaway target
# repo with a linked node worktree, the two directories this repository's own
# gate leaves behind, and the `GateExecutor` that is neither shipped class. The
# declaration has to hold on exactly the tree the refusal was proven against, so
# sharing the fixture is what makes the two stories comparable.
from tests.test_a_gate_that_writes_does_not_pass import (  # noqa: E402
    IGNORED_BY_THE_REAL_GATE,
    StubGateExecutor,
    _node_worktree,
)

#: The gate the fixtures declare as a legitimate writer, and what it writes.
WRITING_COMMAND = "echo generated > generated.txt"
WRITTEN_PATH = "generated.txt"


def _manifest(
    repo: Path,
    gates: Mapping[str, str],
    *,
    writes: Mapping[str, bool] | None = None,
) -> Path:
    """Write a minimal v1 manifest, optionally with a `writes:` block.

    `writes` is spelled out here rather than hidden behind a helper because it
    is the artifact under test: the block a target repo's author commits to say
    "this gate writes on purpose". `None` writes no key at all, which is the
    control every existing manifest is.
    """
    lines = ["version: 1", "runtime: bwrap", "gates:"]
    for name, command in gates.items():
        assert "'" not in command, command
        lines.append(f"  {name}: '{command}'")
    if writes is not None:
        lines.append("writes:")
        for name, declared in writes.items():
            lines.append(f"  {name}: {'true' if declared else 'false'}")
    path = repo / MANIFEST_NAME
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# --- T027 US3-S1: a declared gate that writes still passes -------------------


def test_a_declared_gate_that_writes_still_passes(tmp_path: Path) -> None:
    """US3-S1 / FR-009: the manifest said so, so exit 0 is enough again."""
    worktree = _node_worktree(tmp_path, ignore=IGNORED_BY_THE_REAL_GATE)
    manifest = _manifest(
        worktree, {"test": WRITING_COMMAND}, writes={"test": True}
    )

    results = run_gates(
        worktree, manifest_path=manifest, executor=SubprocessGateExecutor()
    )

    [result] = results
    assert result.status is GateStatus.PASS
    assert result.exit_code == 0
    assert gates_passed(results)
    # The write really happened; it is the refusal that was declared away, not
    # the write itself.
    assert (worktree / WRITTEN_PATH).read_text(encoding="utf-8") == "generated\n"


# --- T028 US3-S2: the declaration is on the evidence, not only in config -----


def test_a_declared_gate_still_records_what_it_wrote(tmp_path: Path) -> None:
    """US3-S2 / FR-010: an opt-out nobody can see is how this defect returns.

    The paths are not omitted because they were declared — they are recorded
    *and* flagged declared, so an operator reading the evidence sees a gate that
    wrote, and sees that somebody signed for it.
    """
    worktree = _node_worktree(tmp_path, ignore=IGNORED_BY_THE_REAL_GATE)
    manifest = _manifest(
        worktree, {"test": WRITING_COMMAND}, writes={"test": True}
    )

    [result] = run_gates(
        worktree, manifest_path=manifest, executor=SubprocessGateExecutor()
    )

    assert result.worktree_writes == (WRITTEN_PATH,)
    assert result.writes_declared is True
    # Not a new `GateStatus` member: a declared writer keeps PASS, so the
    # deterministic decider needs no edit and cannot disagree with this row.
    assert result.status is GateStatus.PASS
    assert GateStatus._member_names_ == [
        "PASS",
        "FAIL",
        "TIMEOUT",
        "CONFIG_ERROR",
        "DIRTIED_WORKTREE",
    ]


# --- T029 US3-S3: both gate-list runners -------------------------------------


@pytest.mark.parametrize("runner", ["_run_gate_list", "_run_gate_list_from_config"])
def test_both_gate_list_runners_honour_the_declaration(
    tmp_path: Path, runner: str
) -> None:
    """US3-S3 / FR-012: the runner that gets nothing for free is the one we run on.

    `_run_gate_list_from_config` is handed the whole `FactoryConfig`, so a new
    field arrives there without being carried. `_run_gate_list` is handed only
    the views lifted off `_AcceptedConfig`, and it is the runner a worktree
    carrying `factory/verify/factory_yaml.py` selects — every Ergane node,
    including the one verifying this story. A declaration honoured by only one
    of them reads as working and is dead in the field.
    """
    worktree = _node_worktree(tmp_path, ignore=IGNORED_BY_THE_REAL_GATE)
    manifest = _manifest(
        worktree, {"test": WRITING_COMMAND}, writes={"test": True}
    )
    executor = StubGateExecutor({WRITTEN_PATH: "generated\n"})

    if runner == "_run_gate_list":
        results = _run_gate_list(
            worktree,
            manifest,
            {"test": WRITING_COMMAND},
            {},
            {"test": True},
            executor=executor,
            timeout_overrides=None,
            concurrency_limiter=None,
        )
    else:
        results = _run_gate_list_from_config(
            worktree,
            load_factory_config(manifest),
            executor=executor,
            timeout_overrides=None,
            concurrency_limiter=None,
        )

    [result] = results
    assert result.status is GateStatus.PASS, runner
    assert result.worktree_writes == (WRITTEN_PATH,), runner
    assert result.writes_declared is True, runner


def test_the_candidate_protocol_carries_the_declaration(tmp_path: Path) -> None:
    """US3-S3 / FR-012: emitted, interpreted, and honoured — end to end.

    The candidate's stdout here is not hand-written protocol JSON: it is
    `json.dumps(dataclasses.asdict(config))`, the exact expression the parser
    CLI prints (`factory/verify/factory_yaml.py`). So this asserts the two
    halves agree — a `writes` field that the manifest parser reads and the CLI
    emits, but `_interpret_candidate` never looks at, fails here while every
    other test in this module still passes.
    """
    worktree = _node_worktree(tmp_path, ignore=IGNORED_BY_THE_REAL_GATE)
    candidate = worktree / "factory" / "verify" / "factory_yaml.py"
    candidate.parent.mkdir(parents=True)
    candidate.write_text("# a worktree that carries its own parser\n", encoding="utf-8")
    manifest = _manifest(
        worktree, {"test": WRITING_COMMAND}, writes={"test": True}
    )
    emitted = json.dumps(dataclasses.asdict(load_factory_config(manifest)))
    assert json.loads(emitted)["writes"] == {"test": True}

    def emitting_candidate(
        worktree_path: Path, manifest_path: Path
    ) -> CandidateOutcome:
        return CandidateOutcome(exit_code=PARSE_CLI_OK, stdout=emitted, stderr="")

    [result] = run_gates(
        worktree,
        manifest_path=manifest,
        executor=SubprocessGateExecutor(),
        candidate_runner=emitting_candidate,
    )

    assert result.status is GateStatus.PASS
    assert result.worktree_writes == (WRITTEN_PATH,)
    assert result.writes_declared is True


# --- T030 US3-S4: a declaration that would apply to nothing ------------------


def test_a_writes_entry_for_an_unknown_gate_is_refused() -> None:
    """US3-S4 / FR-011: named, so the typo is fixable from the message alone."""
    text = (
        "version: 1\n"
        "runtime: bwrap\n"
        "gates:\n"
        "  test: 'uv run pytest -q'\n"
        "writes:\n"
        "  typecheck: true\n"
    )

    with pytest.raises(FactoryConfigError) as raised:
        parse_factory_config(text)

    assert raised.value.rule == "writes"
    assert "'typecheck'" in str(raised.value)
    assert "does not declare as a gate" in str(raised.value)
    assert "'test'" in str(raised.value)


def test_a_non_boolean_writes_value_is_refused() -> None:
    """FR-009: the shape `timeouts:` has, refused the way `timeouts:` refuses.

    `1` is spelled out rather than a string because `isinstance(True, int)` is
    true in Python: a check written with `isinstance(value, bool)` would accept
    the mapping's ints in the other direction, so the type check is exact and
    this is what says so.
    """
    text = (
        "version: 1\n"
        "runtime: bwrap\n"
        "gates:\n"
        "  test: 'uv run pytest -q'\n"
        "writes:\n"
        "  test: 1\n"
    )

    with pytest.raises(FactoryConfigError) as raised:
        parse_factory_config(text)

    assert raised.value.rule == "writes"
    assert "'test'" in str(raised.value)


# --- T031 US3-S5: the control ------------------------------------------------


def test_a_manifest_without_the_key_parses_exactly_as_today(tmp_path: Path) -> None:
    """US3-S5 / FR-009: every target repo's committed manifest keeps working.

    Absent is "nothing declared", not "false everywhere" and not an error — the
    same sparseness `timeouts:` has. Equality against a fully spelled
    `FactoryConfig` is the assertion rather than a field-by-field read: a new
    field that defaulted to anything but "nothing declared" fails here.
    """
    worktree = _node_worktree(tmp_path, ignore=IGNORED_BY_THE_REAL_GATE)
    manifest = _manifest(worktree, {"test": "echo ok"})

    assert "writes" not in manifest.read_text(encoding="utf-8")
    config = load_factory_config(manifest)
    assert config == FactoryConfig(version=1, runtime="bwrap", gates={"test": "echo ok"})
    assert config.writes == {}

    [result] = run_gates(
        worktree, manifest_path=manifest, executor=SubprocessGateExecutor()
    )
    assert result.status is GateStatus.PASS
    assert result.writes_declared is False


def test_declaring_false_is_not_a_declaration(tmp_path: Path) -> None:
    """FR-009: `false` and absent both mean nothing is declared.

    Without this the key would be a switch with one position, and a repo could
    turn US1's refusal off by naming a gate at all.
    """
    worktree = _node_worktree(tmp_path, ignore=IGNORED_BY_THE_REAL_GATE)
    manifest = _manifest(
        worktree, {"test": WRITING_COMMAND}, writes={"test": False}
    )

    [result] = run_gates(
        worktree, manifest_path=manifest, executor=SubprocessGateExecutor()
    )

    assert result.status is GateStatus.DIRTIED_WORKTREE
    assert result.worktree_writes == (WRITTEN_PATH,)
    assert result.writes_declared is False


def test_a_declaration_does_not_excuse_an_unreadable_snapshot(tmp_path: Path) -> None:
    """FR-010 / FR-006: the declaration covers writes, not blindness.

    A repo author declaring "this gate writes" has said what the gate does, not
    that the check may stop looking. A snapshot git refused is still a tree that
    may not be reported clean, and `run_gates` still returns a list.
    """
    worktree = tmp_path / "broken-repo"
    worktree.mkdir()
    (worktree / ".git").write_text("gitdir: /nonexistent-ergane-084\n", encoding="utf-8")
    manifest = _manifest(worktree, {"test": "echo hello"}, writes={"test": True})

    results = run_gates(
        worktree, manifest_path=manifest, executor=SubprocessGateExecutor()
    )

    [result] = results
    assert result.status is not GateStatus.PASS
    assert not gates_passed(results)
    assert result.writes_declared is True
    assert "worktree snapshot failed" in result.output_tail


# --- FR-010: the evidence codec ----------------------------------------------


def test_writes_declared_round_trips_through_the_evidence_store() -> None:
    """FR-010 / trap 8: the retry prompt is built from stored evidence.

    A field that skipped either codec half would be lost the moment the row was
    written and read back, and the declaration would vanish from exactly the
    surface an operator reads it on.
    """
    gate = GateResult(
        name="lock",
        command="uv lock",
        status=GateStatus.PASS,
        exit_code=0,
        duration_s=1.5,
        output_tail="",
        worktree_writes=("uv.lock",),
        writes_declared=True,
    )

    stored = _gate_to_dict(gate)
    assert stored["writes_declared"] is True

    read_back = _gate_from_dict(json.loads(json.dumps(stored)))
    assert read_back.writes_declared is True
    assert read_back == gate


def test_a_row_written_before_this_field_reads_back_as_undeclared() -> None:
    """FR-010: absent means "nobody declared this", which is the honest reading."""
    legacy = {
        "name": "test",
        "command": "uv run pytest -q",
        "status": "PASS",
        "exit_code": 0,
        "duration_s": 1.5,
        "output_tail": "",
        "concurrent_gates": 0,
        "worktree_writes": [],
    }

    assert _gate_from_dict(legacy).writes_declared is False
