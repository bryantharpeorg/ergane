"""Running a target repo's declared gates, and believing the answer.

The gate runner is the deterministic half of verification (FR-002): it executes
commands the target repo committed in its `factory.yaml`, in the order the repo
declared them, and turns each one into a `GateResult` the verdict truth table can
read. Everything interesting about it is a failure mode, so that is what this
module is mostly made of.

Four properties carry the weight:

- **Failures are data, never exceptions.** A gate that exits 3, hangs past its
  deadline, or has no manifest to run from must come back as a `GateResult` with
  a status, not as something raised past the activity boundary. Anything that
  escapes costs the attempt its evidence, and an empty gate list is precisely the
  shape a naive verdict mistakes for "nothing failed" (data-model.md, SC-002).
- **A gate that fails does not cancel the ones after it.** The contract promises
  one result per declared gate (contracts/activities.md), so `failing-gate` and
  `hanging-gate` both declare a passing gate *after* the broken one, and both are
  asserted to have run — from `.factory-gate-order.log`, which records what
  actually executed rather than what the runner claims it executed.
- **The environment the gate sees is an allowlist.** Env scrubbing is only
  observable from inside the child, so `env-probe` reports its own environment and
  the assertions read that report. A denylist would pass a test naming today's two
  credentials and leak tomorrow's third, so the canary here is a variable with no
  security meaning at all: if an unlisted name reaches the gate, the scrubbing is
  wrong even though nothing secret escaped this time.
- **Deadlines are enforced against processes that do not cooperate.** SIGTERM,
  then SIGKILL after a grace period (R3). `hang.sh` dies politely and
  `hang-ignoring-sigterm.sh` does not; both are bounded by wall-clock assertions,
  because a runner that killed the direct child and left its `sleep` grandchild
  holding the output pipe would still *return* — just thirty seconds later.

Two seams keep the suite fast and honest about what it is testing. Real
subprocesses run against the fixture repo (`tests/fixtures/target_repo/`) wherever
the behaviour under test is a real process's; the `GateExecutor` seam (R3) takes
over wherever it is not — nothing here waits out a 600-second default timeout to
prove the default is 600 seconds, it asserts on the invocation the runner built.

The four `demo`-named tests are the ones quickstart §2 selects with
`pytest -k demo`: passing config, failing gate, hanging gate, missing manifest.

Written before `factory/verify/gates.py` exists (T014 precedes T018): until the
module lands, every test here fails at import.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest

from factory.verify.factory_yaml import MANIFEST_NAME
from factory.verify.gates import (
    DEFAULT_GATE_CONCURRENCY,
    DEFAULT_GATE_TIMEOUT_S,
    OUTPUT_TAIL_LIMIT,
    SCRUBBED_ENV_ALLOWLIST,
    ExecutionOutcome,
    GateConcurrencyLimiter,
    GateInvocation,
    SubprocessGateExecutor,
    run_gates,
    scrubbed_env,
    tail_output,
)
from factory.verify.models import GateResult, GateStatus, VerificationConfig
from tests.target_repo import gate_order

#: The fixture repo's own manifest declares these three, in this order — lint
#: first because it is the cheapest, which is the point of honouring the file.
FIXTURE_GATE_ORDER = ["lint", "test", "typecheck"]

#: Credentials that must never reach a gate subprocess (constitution V, R3).
FACTORY_CREDENTIALS = ("LITELLM_MASTER_KEY", "TELEGRAM_BOT_TOKEN")

#: A wall-clock ceiling for tests whose fixture gate would otherwise run 30s. Set
#: far above the real cost (~1-2s) so a loaded machine does not fail the suite,
#: and far below 30s so a runner that lost track of a child still fails it.
KILL_DEADLINE_S = 12.0


# --- the executor seam ------------------------------------------------------


class RecordingExecutor:
    """A `GateExecutor` that runs nothing and remembers everything it was asked.

    Timeout *resolution* — declared, overridden, or defaulted — is a decision the
    runner makes before any process exists, so this is where it can be asserted
    without a test that sleeps for ten minutes to prove the ten-minute default.
    """

    def __init__(self, outcomes: dict[str, ExecutionOutcome] | None = None) -> None:
        self.invocations: list[GateInvocation] = []
        self.outcomes = outcomes or {}

    def run(self, invocation: GateInvocation) -> ExecutionOutcome:
        self.invocations.append(invocation)
        return self.outcomes.get(
            invocation.name,
            ExecutionOutcome(exit_code=0, output="", duration_s=0.01, timed_out=False),
        )

    @property
    def names(self) -> list[str]:
        return [invocation.name for invocation in self.invocations]

    @property
    def timeouts(self) -> dict[str, int]:
        return {inv.name: inv.timeout_s for inv in self.invocations}


def results_by_name(results: list[GateResult]) -> dict[str, GateResult]:
    return {result.name: result for result in results}


def probe_values(output: str) -> dict[str, str]:
    """Parse `env-probe.sh`'s `NAME=[value]` report lines out of a gate's output."""
    values: dict[str, str] = {}
    for line in output.splitlines():
        name, separator, rest = line.partition("=[")
        if separator and rest.endswith("]"):
            values[name] = rest[:-1]
    return values


# --- declaration order, timeouts, cwd ---------------------------------------


def test_gates_run_in_the_order_the_manifest_declared(
    node_worktree: Callable[..., Path],
) -> None:
    """Sorting gates would spend a full test run before a two-second lint."""
    worktree = node_worktree("passing")
    executor = RecordingExecutor()

    results = run_gates(worktree, executor=executor)

    assert executor.names == FIXTURE_GATE_ORDER
    assert [result.name for result in results] == FIXTURE_GATE_ORDER


def test_declared_timeouts_win_and_the_rest_default_to_600s(
    node_worktree: Callable[..., Path],
) -> None:
    """The fixture declares `lint: 30` and leaves the other two to the default."""
    worktree = node_worktree("passing")
    executor = RecordingExecutor()

    run_gates(worktree, executor=executor)

    assert executor.timeouts == {"lint": 30, "test": 600, "typecheck": 600}


def test_the_default_timeout_is_the_deployment_knob() -> None:
    """Two constants for one number is one constant too many.

    `VerificationConfig.gate_timeout_s` is what an operator edits; the runner's
    default must be the same 600 seconds, or tuning it would silently do nothing.
    """
    assert DEFAULT_GATE_TIMEOUT_S == 600
    assert DEFAULT_GATE_TIMEOUT_S == VerificationConfig().gate_timeout_s


def test_timeout_overrides_apply_per_gate(node_worktree: Callable[..., Path]) -> None:
    """Overrides are the caller's (contracts/activities.md), and they are surgical."""
    worktree = node_worktree("passing")
    executor = RecordingExecutor()

    run_gates(worktree, executor=executor, timeout_overrides={"test": 5})

    assert executor.timeouts == {"lint": 30, "test": 5, "typecheck": 600}


def test_every_gate_runs_in_the_worktree(node_worktree: Callable[..., Path]) -> None:
    """Gates verify the node's worktree, never the repo's own checkout."""
    worktree = node_worktree("passing")
    executor = RecordingExecutor()

    run_gates(worktree, executor=executor)

    assert [invocation.cwd for invocation in executor.invocations] == [worktree] * 3


def test_the_manifest_path_is_independent_of_the_worktree(
    node_worktree: Callable[..., Path], tmp_path: Path
) -> None:
    """The activity takes both paths, so the runner must not conflate them."""
    worktree = node_worktree("passing")
    elsewhere = tmp_path / "elsewhere.yaml"
    elsewhere.write_text(
        (worktree / MANIFEST_NAME).read_text(encoding="utf-8"), encoding="utf-8"
    )
    (worktree / MANIFEST_NAME).unlink()
    executor = RecordingExecutor()

    results = run_gates(worktree, manifest_path=elsewhere, executor=executor)

    assert [result.name for result in results] == FIXTURE_GATE_ORDER
    assert executor.invocations[0].cwd == worktree


def test_commands_are_reported_exactly_as_declared(
    node_worktree: Callable[..., Path],
) -> None:
    """`command` is evidence an operator reruns by hand; rewriting it breaks that."""
    worktree = node_worktree("passing")

    results = run_gates(worktree, executor=RecordingExecutor())

    assert [result.command for result in results] == [
        f"bash gates/{name}.sh" for name in FIXTURE_GATE_ORDER
    ]


# --- outcome mapping --------------------------------------------------------


@dataclass(frozen=True)
class StatusMapping:
    """One executor outcome and the `GateResult` it must become."""

    id: str
    outcome: ExecutionOutcome
    status: GateStatus
    exit_code: int | None


MAPPINGS = [
    StatusMapping(
        id="exit-zero-passes",
        outcome=ExecutionOutcome(
            exit_code=0, output="ok", duration_s=0.5, timed_out=False
        ),
        status=GateStatus.PASS,
        exit_code=0,
    ),
    StatusMapping(
        id="non-zero-fails-with-its-code",
        outcome=ExecutionOutcome(
            exit_code=3, output="boom", duration_s=0.5, timed_out=False
        ),
        status=GateStatus.FAIL,
        exit_code=3,
    ),
    StatusMapping(
        id="signal-death-is-a-failure-not-a-timeout",
        outcome=ExecutionOutcome(
            exit_code=-9, output="", duration_s=0.5, timed_out=False
        ),
        status=GateStatus.FAIL,
        exit_code=-9,
    ),
    StatusMapping(
        id="deadline-is-a-timeout-with-no-code-to-read",
        outcome=ExecutionOutcome(
            exit_code=None, output="hung", duration_s=1.0, timed_out=True
        ),
        status=GateStatus.TIMEOUT,
        exit_code=None,
    ),
]


@pytest.mark.parametrize("case", MAPPINGS, ids=[case.id for case in MAPPINGS])
def test_execution_outcomes_map_to_gate_statuses(
    case: StatusMapping, node_worktree: Callable[..., Path]
) -> None:
    worktree = node_worktree("passing")
    executor = RecordingExecutor({"lint": case.outcome})

    lint = results_by_name(run_gates(worktree, executor=executor))["lint"]

    assert lint.status is case.status
    assert lint.exit_code == case.exit_code
    assert lint.duration_s == case.outcome.duration_s
    assert lint.output_tail == case.outcome.output


def test_a_failing_gate_does_not_stop_the_run(
    node_worktree: Callable[..., Path],
) -> None:
    """One result per declared gate, even after the first one fails."""
    worktree = node_worktree("passing")
    failure = ExecutionOutcome(exit_code=1, output="", duration_s=0.1, timed_out=False)
    executor = RecordingExecutor({"lint": failure})

    results = run_gates(worktree, executor=executor)

    assert [result.name for result in results] == FIXTURE_GATE_ORDER
    assert [result.status for result in results] == [
        GateStatus.FAIL,
        GateStatus.PASS,
        GateStatus.PASS,
    ]


# --- output tail ------------------------------------------------------------


def test_the_tail_limit_is_32_kib() -> None:
    assert OUTPUT_TAIL_LIMIT == 32 * 1024


def test_short_output_is_kept_whole() -> None:
    assert tail_output("test: 1 passed\n") == "test: 1 passed\n"


def test_the_tail_is_the_end_of_the_output_verbatim() -> None:
    """The *end* is where a failure is explained, and nothing is inserted.

    Truncation markers belong to judge-input assembly (R6), where the model has to
    be told not to read a truncation as missing implementation. Gate evidence is
    quoted into retry prompts (FR-006, SC-004), so a marker here would be one more
    line of the factory's own voice in a place that should be the tool's output.
    """
    output = "".join(f"line {index}\n" for index in range(20_000))

    tail = tail_output(output)

    assert len(tail.encode("utf-8")) <= OUTPUT_TAIL_LIMIT
    assert output.endswith(tail)
    assert tail.endswith("line 19999\n")


def test_the_tail_is_measured_in_bytes_and_split_on_a_character_boundary() -> None:
    """A cap that sliced characters would emit a tail that cannot be decoded."""
    output = "é" * 30_000  # two bytes each: 60 000 bytes, 30 000 characters

    tail = tail_output(output)
    encoded = tail.encode("utf-8")

    assert len(encoded) <= OUTPUT_TAIL_LIMIT
    assert len(encoded) > OUTPUT_TAIL_LIMIT - 4, "should keep as much as it can"
    assert output.endswith(tail)


def test_a_noisy_failing_gate_keeps_its_last_32_kib(
    node_worktree: Callable[..., Path],
) -> None:
    """~110 KiB of real subprocess output, capped where it is captured.

    The cap is what stops one verbose test suite from being copied into workflow
    state, an escalation message and the evidence store.
    """
    worktree = node_worktree("noisy-gate")

    results = run_gates(worktree)

    assert len(results) == 1
    noisy = results[0]
    assert noisy.status is GateStatus.FAIL
    assert noisy.exit_code == 1
    assert len(noisy.output_tail.encode("utf-8")) <= OUTPUT_TAIL_LIMIT
    assert "NOISE-HEAD" not in noisy.output_tail
    assert noisy.output_tail.rstrip().endswith("NOISE-TAIL last line of output")


# --- real subprocesses: the quickstart §2 demo ------------------------------


def test_demo_passing_manifest_runs_every_declared_gate(
    node_worktree: Callable[..., Path],
) -> None:
    worktree = node_worktree("passing")

    results = run_gates(worktree)

    assert [result.name for result in results] == FIXTURE_GATE_ORDER
    assert [result.status for result in results] == [GateStatus.PASS] * 3
    assert [result.exit_code for result in results] == [0, 0, 0]
    assert all(result.duration_s > 0 for result in results)
    assert gate_order(worktree) == FIXTURE_GATE_ORDER, "declaration order, in fact"
    assert "lint: 1 file checked, 0 problems found" in results[0].output_tail


def test_demo_failing_gate_reports_its_exit_code_and_both_streams(
    node_worktree: Callable[..., Path],
) -> None:
    """Exit 3, not merely "truthy" — and stderr, where the reason lives."""
    worktree = node_worktree("failing-gate")

    results = run_gates(worktree)

    by_name = results_by_name(results)
    assert [result.name for result in results] == FIXTURE_GATE_ORDER
    assert by_name["test"].status is GateStatus.FAIL
    assert by_name["test"].exit_code == 3
    assert "test: 2 passed, 1 failed" in by_name["test"].output_tail
    assert "E       assert add(2, 2) == 5" in by_name["test"].output_tail
    assert by_name["typecheck"].status is GateStatus.PASS
    assert gate_order(worktree) == FIXTURE_GATE_ORDER, "the run continued past FAIL"


def test_demo_hanging_gate_times_out_and_the_next_gate_still_runs(
    node_worktree: Callable[..., Path],
) -> None:
    """A 1s deadline against a 30s sleep: TIMEOUT, promptly, then keep going."""
    worktree = node_worktree("hanging-gate")

    started = time.monotonic()
    results = run_gates(worktree)
    elapsed = time.monotonic() - started

    by_name = results_by_name(results)
    assert [result.name for result in results] == ["test", "typecheck"]
    assert by_name["test"].status is GateStatus.TIMEOUT
    assert by_name["test"].exit_code is None, "there was no exit status to read"
    assert by_name["test"].duration_s >= 1.0
    assert "hang: started, sleeping" in by_name["test"].output_tail
    assert "hang: finished" not in by_name["test"].output_tail
    assert by_name["typecheck"].status is GateStatus.PASS
    assert gate_order(worktree) == ["test", "typecheck"]
    assert elapsed < KILL_DEADLINE_S, (
        "a runner that left the gate's `sleep` grandchild holding the output pipe "
        "returns too — thirty seconds later"
    )


def test_demo_missing_manifest_is_a_single_config_error(
    node_worktree: Callable[..., Path],
) -> None:
    """No manifest is not "no gates failed" — it is the verification failing."""
    worktree = node_worktree("missing-manifest")
    executor = RecordingExecutor()

    results = run_gates(worktree, executor=executor)

    assert len(results) == 1
    config = results[0]
    assert config.name == "config"
    assert config.status is GateStatus.CONFIG_ERROR
    assert config.exit_code is None
    assert config.command == ""
    assert config.duration_s == 0.0
    assert str(worktree / MANIFEST_NAME) in config.output_tail
    assert executor.invocations == [], "nothing may run without a manifest"
    assert gate_order(worktree) == []


# --- deadlines against uncooperative processes ------------------------------


def test_a_gate_that_ignores_sigterm_is_killed(
    node_worktree: Callable[..., Path],
) -> None:
    """SIGTERM, then SIGKILL after the grace period (R3, factory-yaml.md).

    The grace is shortened from its 10s default so the test costs ~2s; the gate
    it faces traps TERM and INT and would otherwise run for 30 seconds.
    """
    worktree = node_worktree("sigterm-defying-gate")

    started = time.monotonic()
    results = run_gates(worktree, executor=SubprocessGateExecutor(grace_s=0.5))
    elapsed = time.monotonic() - started

    assert len(results) == 1
    defiant = results[0]
    assert defiant.status is GateStatus.TIMEOUT
    assert defiant.exit_code is None
    assert "defy: ignoring SIGTERM" in defiant.output_tail
    assert "defy: finished" not in defiant.output_tail
    assert elapsed < KILL_DEADLINE_S, "only SIGKILL ends this gate"


# --- environment scrubbing --------------------------------------------------


def test_scrubbing_is_an_allowlist() -> None:
    """A denylist protects the credentials we thought of, and no others."""
    hostile = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/home/operator",
        "LITELLM_MASTER_KEY": "sk-master-value",
        "TELEGRAM_BOT_TOKEN": "42:bot-token-value",
        "AWS_SECRET_ACCESS_KEY": "aws-value",
        "TOMORROWS_CREDENTIAL": "not-invented-yet",
    }

    env = scrubbed_env(hostile)

    assert set(env) <= set(SCRUBBED_ENV_ALLOWLIST)
    assert env.get("PATH"), "gates run real commands; PATH has to survive"
    assert env.get("HOME"), "tools that write dotfiles need somewhere to write them"
    for name in FACTORY_CREDENTIALS:
        assert name not in SCRUBBED_ENV_ALLOWLIST
        assert name not in env
    assert "not-invented-yet" not in "\n".join(env.values())


def test_scrubbing_defaults_to_the_process_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-master-must-not-leak")

    assert "LITELLM_MASTER_KEY" not in scrubbed_env()


def test_a_gate_subprocess_never_sees_the_factorys_credentials(
    node_worktree: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Asserted from inside the child, because that is the only place it is true.

    `env-probe.sh` reports what it was handed; the canary is an ordinary variable
    with no secret in it, so this fails on *any* unlisted name reaching the gate
    rather than only on the two credentials that exist today.
    """
    worktree = node_worktree("env-probe")
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-master-must-not-leak")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "42:bot-token-must-not-leak")
    monkeypatch.setenv("FACTORY_TEST_CANARY", "canary-must-not-leak")

    results = run_gates(worktree)

    assert len(results) == 1
    probe = results[0]
    assert probe.status is GateStatus.PASS, probe.output_tail

    for leak in ("sk-master-must-not-leak", "42:bot-token-must-not-leak"):
        assert leak not in probe.output_tail
    assert "FACTORY_TEST_CANARY" not in probe.output_tail
    assert "canary-must-not-leak" not in probe.output_tail

    reported = probe_values(probe.output_tail)
    for name in FACTORY_CREDENTIALS:
        assert reported[name] in ("<unset>", ""), f"{name} reached the gate"
    assert reported["PATH"] not in ("<unset>", "")
    assert reported["HOME"] not in ("<unset>", "")
    assert Path(reported["PWD"]).resolve() == worktree.resolve()


# --- config errors ----------------------------------------------------------


@dataclass(frozen=True)
class ConfigError:
    """A manifest variant and the words its `CONFIG_ERROR` message must contain."""

    variant: str
    names: tuple[str, ...] = ()


CONFIG_ERRORS = [
    ConfigError(variant="missing-manifest", names=("missing_manifest",)),
    ConfigError(variant="malformed-manifest", names=("malformed_yaml",)),
    ConfigError(variant="unknown-gate", names=("gates", "build")),
]


@pytest.mark.parametrize(
    "case", CONFIG_ERRORS, ids=[case.variant for case in CONFIG_ERRORS]
)
def test_an_unusable_manifest_yields_one_actionable_config_error(
    case: ConfigError, node_worktree: Callable[..., Path]
) -> None:
    """Parsed-but-invalid and unparseable are the same story to the verdict.

    `unknown-gate` is the half a YAML check alone would miss: `safe_load` accepts
    it happily and only the schema rejects it. Both arrive here as one result the
    truth table fails on, carrying a message that names the rule and the offending
    key so the operator (or the debugger persona) can fix the file.
    """
    worktree = node_worktree(case.variant)
    executor = RecordingExecutor()

    results = run_gates(worktree, executor=executor)

    assert len(results) == 1
    config = results[0]
    assert config.name == "config"
    assert config.status is GateStatus.CONFIG_ERROR
    assert config.exit_code is None
    for token in case.names:
        assert token in config.output_tail, f"message must name {token!r}"
    assert executor.invocations == [], "an unusable manifest runs no commands"


def test_a_vanished_worktree_is_a_config_error_not_a_crash(tmp_path: Path) -> None:
    """There is no manifest to read, and pass-by-default is never the answer."""
    worktree = tmp_path / "gone"

    results = run_gates(worktree, executor=RecordingExecutor())

    assert len(results) == 1
    assert results[0].status is GateStatus.CONFIG_ERROR
    assert str(worktree / MANIFEST_NAME) in results[0].output_tail


# --- US2: a verdict does not depend on its neighbours (FR-005) ---------------
#
# Fan-out puts N nodes' gates on one host at once, and a fixed wall-clock
# timeout converts neighbour load into a FAIL — a verdict that is not a fact
# about the node's code. The fix bounds gate concurrency below node
# concurrency: a node's agent runs in parallel while its gates take a turn, so
# a gate's wall-clock measures its own work and never the queue it waited in.
# The contention marker records whether a gate ran alongside others, so a slow
# verdict is auditable rather than mysterious.
#
# Contention is a fact *between* nodes, not within one: a single `run_gates`
# call runs its gates in sequence. So these tests run two `run_gates` calls in
# two threads sharing one limiter — the shape the workflow produces when N
# nodes verify at once — and read the results back on the main thread.


def _run_two_concurrent(
    worktree: Path,
    *,
    executor_a: Callable,
    executor_b: Callable,
    limiter: GateConcurrencyLimiter,
) -> tuple[list[GateResult], list[GateResult]]:
    """Run two `run_gates` calls in parallel threads sharing one limiter.

    This is the topology fan-out produces: N nodes, each in its own worker
    thread, each calling `run_gates` against its own worktree. Two is the
    smallest N that contends.
    """
    out: dict[str, list[GateResult]] = {}

    def run(tag: str, executor: Callable) -> None:
        out[tag] = run_gates(worktree, executor=executor, concurrency_limiter=limiter)

    threads = [
        threading.Thread(target=run, args=("a", executor_a), name="gate-node-a"),
        threading.Thread(target=run, args=("b", executor_b), name="gate-node-b"),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30.0)
    return out["a"], out["b"]


class _BarrierExecutor:
    """An executor that holds a gate mid-flight until a peer arrives.

    The barrier is sized for two, so a gate that runs alone breaks the barrier
    after a short timeout and proceeds uncontended; a gate that runs while a
    peer is also in flight releases the barrier immediately and the two are
    observed running at once. `gate_work_s` is the work the gate does once it
    has its turn — the part the wall-clock bound is meant to measure.
    """

    def __init__(
        self,
        outcome: ExecutionOutcome,
        *,
        gate_work_s: float,
        barrier: threading.Barrier,
    ) -> None:
        self._outcome = outcome
        self._gate_work_s = gate_work_s
        self._barrier = barrier
        self.invocations: list[GateInvocation] = []

    def run(self, invocation: GateInvocation) -> ExecutionOutcome:
        self.invocations.append(invocation)
        try:
            self._barrier.wait()
        except threading.BrokenBarrierError:
            pass
        time.sleep(self._gate_work_s)
        return self._outcome


def test_the_default_gate_concurrency_is_one() -> None:
    """Gates serialize across the host by default — the strongest form of
    load-independence, and below any node concurrency above one."""
    assert DEFAULT_GATE_CONCURRENCY == 1


def test_an_uncontended_gate_records_no_contention(
    node_worktree: Callable[..., Path],
) -> None:
    """A gate that ran alone carries a contention marker of zero, so an
    operator reading the evidence sees 'this verdict was not under load'
    rather than having to guess (FR-005 acceptance 3)."""
    worktree = node_worktree("passing")
    executor = RecordingExecutor()

    results = run_gates(worktree, executor=executor)

    assert results, "the fixture declares gates"
    for result in results:
        assert result.concurrent_gates == 0


def test_a_gate_passes_alone_and_passes_contended(
    node_worktree: Callable[..., Path],
) -> None:
    """FR-005 acceptance 1: a node whose gates pass when run alone still pass
    when run at full concurrency.

    The gate's true verdict is PASS and its own work is fast; what would push
    its wall-clock past the bound is a neighbour holding the CPU. Bounding gate
    concurrency means the gate waits for its turn rather than racing for it —
    its wall-clock measures its own work, so the verdict does not move with
    load. We run the *same* gate alone and alongside one busy neighbour and
    assert identical PASS verdicts; the neighbour's presence only stretches the
    wall-clock the runner waited, never the status."""
    worktree = node_worktree("passing")
    passing = ExecutionOutcome(
        exit_code=0, output="ok", duration_s=0.2, timed_out=False
    )

    # Alone: no neighbour, no contention. The barrier breaks on its timeout
    # because no peer ever arrives, and the gate passes on its own merits.
    alone_barrier = threading.Barrier(2, timeout=0.5)
    alone = run_gates(
        worktree,
        executor=_BarrierExecutor(passing, gate_work_s=0.05, barrier=alone_barrier),
    )
    assert [r.status for r in alone] == [GateStatus.PASS] * 3
    assert all(r.concurrent_gates == 0 for r in alone)

    # Contended: a second node's gates run alongside the first's, sharing a
    # limiter that bounds gate concurrency at one. Gates take turns rather than
    # race for the CPU; both nodes still PASS because the bound measures each
    # gate's own work, not the queue it waited in.
    contended_barrier = threading.Barrier(2, timeout=5.0)
    limiter = GateConcurrencyLimiter(DEFAULT_GATE_CONCURRENCY)
    a, b = _run_two_concurrent(
        worktree,
        executor_a=_BarrierExecutor(passing, gate_work_s=0.05, barrier=contended_barrier),
        executor_b=_BarrierExecutor(passing, gate_work_s=0.05, barrier=contended_barrier),
        limiter=limiter,
    )
    assert [r.status for r in a] == [GateStatus.PASS] * 3, (
        "a passing gate's verdict must not move with neighbour load"
    )
    assert [r.status for r in b] == [GateStatus.PASS] * 3


def test_a_genuinely_hanging_gate_is_still_detected_under_contention(
    node_worktree: Callable[..., Path],
) -> None:
    """FR-005 acceptance 2: the protection loosens contention sensitivity, it
    does not remove timeouts. A gate that genuinely hangs past its bound is
    still detected and failed — even when other gates are queued behind it.

    Uses the real subprocess executor against the hanging-gate fixture so the
    deadline enforcement (SIGTERM then SIGKILL) is exercised for real, under a
    concurrency limiter that would let a queued neighbour wait too. The bound
    is short; the gate sleeps 30s; the verdict must be TIMEOUT promptly."""
    worktree = node_worktree("hanging-gate")
    limiter = GateConcurrencyLimiter(DEFAULT_GATE_CONCURRENCY)

    started = time.monotonic()
    results = run_gates(
        worktree,
        executor=SubprocessGateExecutor(grace_s=0.5),
        timeout_overrides={"test": 1, "typecheck": 1},
        concurrency_limiter=limiter,
    )
    elapsed = time.monotonic() - started

    by_name = results_by_name(results)
    assert by_name["test"].status is GateStatus.TIMEOUT
    assert by_name["test"].exit_code is None
    assert elapsed < KILL_DEADLINE_S, "the bound still ends a hang promptly"


def test_a_contended_gate_records_its_contention(
    node_worktree: Callable[..., Path],
) -> None:
    """FR-005 acceptance 3: whether a gate ran contended is on its result and
    readable afterwards, so a slow verdict is auditable.

    Two nodes' gates share a limiter that admits both at once, so each gate
    runs alongside a peer and `concurrent_gates` records that count. The
    barrier forces the overlap to actually happen — without it two fast gates
    might miss each other on a timing fluke and the marker would read zero for
    the wrong reason. The marker is what makes a slow verdict something an
    operator can explain rather than something they have to explain away."""
    worktree = node_worktree("passing")
    passing = ExecutionOutcome(
        exit_code=0, output="ok", duration_s=0.2, timed_out=False
    )
    barrier = threading.Barrier(2, timeout=5.0)
    # A limiter that admits two gate executions at once — wider than the
    # default of one — so a gate genuinely runs alongside a neighbour.
    limiter = GateConcurrencyLimiter(2)

    a, b = _run_two_concurrent(
        worktree,
        executor_a=_BarrierExecutor(passing, gate_work_s=0.1, barrier=barrier),
        executor_b=_BarrierExecutor(passing, gate_work_s=0.1, barrier=barrier),
        limiter=limiter,
    )

    contended = [r for r in [*a, *b] if r.concurrent_gates > 0]
    assert contended, (
        "a gate that ran alongside another must record the contention"
    )
    # The contended gate saw exactly one peer in flight alongside it.
    for result in contended:
        assert result.concurrent_gates == 1
