# Plan: The gate that judges a story with the parser it is changing

All line references below were read against the tree at commit `9594787` on
2026-08-11. They are cited so you can find the code, not so you can trust the
numbers — beside each anchor is the construct to grep for, because numbers rot
before dispatch (see trap 7).

## Reuse inventory

| What | Where | Used by |
| --- | --- | --- |
| The in-process parse `run_gates` does today (grep `load_factory_config(manifest)`) | `factory/verify/gates.py:420-423` | US2 — the edit point; this call becomes the *fallback* |
| The parser import the worker holds (grep `from factory.verify.factory_yaml import`) | `factory/verify/gates.py:47-52` | US2 — kept, for the fallback path |
| The one-result contract for a broken manifest (grep `runs nothing at all`) | `factory/verify/gates.py:404-406` (docstring), enforced at `:420-423` | US2 — preserved exactly; candidate rejection reuses it |
| `config_error_result` (grep `def config_error_result`) | `factory/verify/factory_yaml.py:352-367` | US2 — the fallback's result; the candidate-rejection result copies its shape (`name="config"`, `status=CONFIG_ERROR`, `duration_s=0.0`) |
| `parse_factory_config` (grep `def parse_factory_config`) | `factory/verify/factory_yaml.py:85` | US1 — the CLI wraps `load_factory_config`, which wraps this |
| `load_factory_config` (grep `def load_factory_config`) | `factory/verify/factory_yaml.py:317` | US1 CLI body; US2 fallback |
| `FactoryConfigError` with `.rule`/`.source` (grep `class FactoryConfigError`) | `factory/verify/factory_yaml.py:66-79` | US1 — its `str()` is the rejection payload, verbatim |
| `_reject_unknown_keys` — the rejection that killed 020/us1 (grep `_reject_unknown_keys`) | `factory/verify/factory_yaml.py:140-148` | US1 test fixture: an unknown-key manifest is the canonical reject case |
| `FactoryConfig` dataclass (grep `class FactoryConfig`) | `factory/verify/models.py:184` | US1 — `dataclasses.asdict` is the JSON shape; US2 consumes only `gates`/`timeouts` from it |
| `scrubbed_env` (grep `def scrubbed_env`) | `factory/verify/gates.py:216` | US2 — the candidate subprocess env, unchanged |
| `DEFAULT_GATE_TIMEOUT_S` (grep `DEFAULT_GATE_TIMEOUT_S`) | `factory/verify/gates.py:58` | US2 — the parse deadline (see trap 5) |
| Group-kill discipline (grep `_signal_group`, `start_new_session`) | `factory/verify/gates.py:349-368`, `:320` | US2 — copy for the parse subprocess's timeout kill |
| `GateConcurrencyLimiter` and `_default_limiter` (grep `_default_limiter`) | `factory/verify/gates.py:162-210` | US2 — acquire around the parse subprocess too (a cold `uv run` builds a venv, which is real load; 007's bound exists for exactly that) |
| `RunGatesInput` + activity (grep `class RunGatesInput`) | `factory/activities/verify_activities.py:208-275` | unchanged — the seam is a library parameter, not a new activity field |
| The workflow call site (grep `RunGatesInput(worktree_path`) | `factory/workgraph/workflow.py:1710-1717` | unchanged, context only |
| `RecordingExecutor` test seam (grep `class RecordingExecutor`) | `tests/test_gates.py:89` | US2 tests — proves gates ran / did not run without processes |
| Fixture target repo (no `factory/` dir — the no-candidate case for free) | `tests/fixtures/target_repo/` | US2 — US2-S3's worktree |
| Graceful readers that must NOT gain candidate parsing (grep `_declared_standards`, `def landing_branch`, `factory_yaml_error`) | `factory/activities/agent_activities.py:655-667`, `factory/workgraph/worktree.py:419-435`, `factory/activities/merge_activities.py:447-459` | boundary — cited so nobody "completes" the fix there; all three degrade gracefully today |
| The live manifest's own warning about this deadlock | `factory.yaml:37-43` | context — the documentation the residual rule already has |

## Traps

### Trap 1 — the plausible wrong fix is importing the worktree's parser

The obvious "use the worktree's parser" implementation is
`importlib.util.spec_from_file_location` (or a `sys.path` insertion) pointed at
`<worktree>/factory/verify/factory_yaml.py`. Do not. The worker must survive a
broken candidate — a syntax error in a candidate parser is an ordinary failed
attempt, and under the import approach it is an exception inside the worker's
activity instead; worse, imported worktree modules poison `sys.modules` for
every other node the worker is running. FR-003 forbids it and SC-002 greps for
it. The subprocess is the design, not an implementation detail — it is the same
trust boundary gate commands already cross.

### Trap 2 — exit 0 is not acceptance

A worktree based on any commit before US1 lands has a
`factory/verify/factory_yaml.py` (the probe finds a candidate) with no
`__main__` handling — `python -m` runs the module body, prints nothing, and
exits 0. An interpreter that reads exit 0 as "accepted" turns every old-base
worktree into an accepted manifest with no gates, which is precisely the
empty-gate-list false PASS the module docstring warns about — or a `json.loads`
crash, which is worse. Acceptance is exit 0 **and** stdout parsing as
structurally valid protocol JSON (`gates`: non-empty str→str mapping,
`timeouts`: str→positive-int mapping). Everything else that isn't the
documented rejection code is cannot-run. US2-S5 and T009 pin this.

### Trap 3 — do not route the protocol through the `GateExecutor` seam

The seam looks anointed for exactly this, and it is wrong here: —
`SubprocessGateExecutor` merges stderr into stdout
(`stderr=subprocess.STDOUT`, `gates.py:317`), and `uv run` writes progress to
stderr, so the JSON document would come back interleaved with uv's chatter.
The candidate parse needs **separated** streams — JSON on stdout, diagnostics
on stderr — so it gets its own small runner (`subprocess`, `start_new_session`,
group kill on timeout, `scrubbed_env()`), injectable via a new `run_gates`
parameter that mirrors the existing `executor` one. Copy the executor's kill
discipline; do not reuse its stream plumbing.

### Trap 4 — the parse must not become an extra gate result

The contract is one result per declared gate, plus exactly one `CONFIG_ERROR`
*instead of* results when the manifest is unusable. A candidate parse that
*accepts* contributes zero results — no "config: PASS" row, which the verdict
truth table and the existing result-count assertions would both choke on. A
candidate rejection is one `CONFIG_ERROR` and nothing else, exactly like
today's `[config_error_result(error)]` return at `gates.py:423`.

### Trap 5 — a "parsing is fast" timeout re-creates the deadlock

The first `uv run` in a fresh worktree may build its environment from the uv
cache; a 10-second parse deadline converts that cold start into cannot-run →
fallback → the worker's old parser → `CONFIG_ERROR` — four identical attempts
again, with extra machinery. Bound the parse with `DEFAULT_GATE_TIMEOUT_S`
(`gates.py:58`), the same knob gates get, and acquire the concurrency limiter
around the subprocess so the venv build cannot stampede the host (007's
rationale, `gates.py:73`).

### Trap 6 — byte-identical fallback, proven by not touching the old tests

FR-008's evidence is negative: every pre-existing test in `tests/test_gates.py`
and `tests/test_factory_yaml.py` passes **unmodified**. If implementing the
fallback makes one of them need an edit — a changed message, a reordered call,
a new required parameter — the fallback is not today's behaviour and the
implementation is wrong, not the test. The probe (file existence) is what makes
this cheap: the fixture repo has no `factory/` directory, so every existing
test takes the fallback path without ever spawning a subprocess.

### Trap 7 — these line numbers rot faster than you think

020's finding carried refs (`gates.py:47`, `:406`; `factory_yaml.py:138`) that
were already a few lines stale by the time this plan was written two days
later: the in-process parse now sits at `:420-423` and the unknown-key
rejection at `:140-148`. Something else may land between this plan and your
worktree. Grep for the construct named beside each anchor; if a citation does
not match what you find, the code wins and you say so in your commit message.

### Trap 8 — you are editing the gate that judges you

`run_gates` is the function that will verify your own attempt — the pre-fix
version of it, imported by the worker from its own checkout, never from your
worktree. Your edits are inert for your own epic; they go live when an operator
restarts the worker after this lands. Two consequences: do not restart
anything, and do not "test" your change by touching this repo's `factory.yaml`
— your stories change no manifest schema, which is exactly why they cannot
deadlock themselves (spec, Edge Cases). Your evidence is the test suite and
nothing else.

### Trap 9 — the rejection exit code must be one no launcher uses

The natural constants — 1, or 2 as "the other error" — collide with the
launchers standing between the worker and the candidate. Measured on this host
(uv 0.11.3): `uv run` in a worktree whose `pyproject.toml` is broken exits
**2** with a TOML parse error on stderr, before Python ever starts; an
unresolvable dependency exits 1; `python -m` exits 1 on an uncaught exception
and 2 on an argparse usage error. Under the interpretation table, a rejection
code of 2 turns an agent-broken `pyproject.toml` — an ordinary failed-attempt
shape — into "the candidate rejected the manifest": one `CONFIG_ERROR`
carrying uv's TOML error instead of cannot-run → fallback, violating FR-005's
"failing to start" clause. `PARSE_CLI_REJECTED = 65` (sysexits `EX_DATAERR`)
is outside everything uv and python exit with on their own; only the candidate
module itself can produce it, which is the protocol working. T008's table pins
the exit-2-with-stderr shape to cannot-run, never rejected.

## Approach

### US1 — the parser learns to speak for itself

1. In `factory/verify/factory_yaml.py`, add two module constants —
   `PARSE_CLI_OK = 0`, `PARSE_CLI_REJECTED = 65` (sysexits `EX_DATAERR`;
   NOT 1 or 2 — see trap 9 for the measured collision) — and a `_main(argv)`
   that:
   takes exactly one argument (the manifest path), calls
   `load_factory_config` on it, and on success prints
   `json.dumps(dataclasses.asdict(config))` to stdout and returns
   `PARSE_CLI_OK`; on `FactoryConfigError` prints `str(error)` to stderr and
   returns `PARSE_CLI_REJECTED`. A missing/unreadable path is already a
   `FactoryConfigError` (`missing_manifest`, `:329-335`), so scenario US1-S3
   needs no extra handling — that is why the CLI wraps `load_factory_config`
   rather than `parse_factory_config`.
2. Guard with `if __name__ == "__main__": sys.exit(_main(sys.argv[1:]))`.
   Wrong argv count is `PARSE_CLI_REJECTED` with a usage line on stderr — the
   caller can only distinguish streams and codes.
3. Nothing else in the module changes. The full `FactoryConfig` goes into the
   JSON (not a curated subset) so the protocol never needs a version bump when
   the dataclass grows a field — the consumer ignores what it does not know.

### US2 — the gate consults the candidate first

1. A small outcome type and a pure interpreter:
   `_interpret_candidate(outcome)` maps (exit code, stdout, stderr, timed_out)
   to one of three results — accepted (with the validated `gates`/`timeouts`
   view), rejected (with the stderr message), cannot-run (with a reason
   string). All of trap 2's table lives here, fully unit-testable without a
   process.
2. A runner behind a seam: `run_gates` gains a keyword parameter (default:
   the real subprocess runner) mirroring `executor`. The real runner: probe
   `worktree / "factory/verify/factory_yaml.py"`; if absent, report
   no-candidate (which `run_gates` treats as cannot-run without a reason to
   record); else `subprocess` with argv
   `["uv", "run", "-q", "python", "-m", "factory.verify.factory_yaml",
   str(manifest)]`, `cwd=worktree`, `env=scrubbed_env()`, separated pipes,
   `start_new_session=True`, `DEFAULT_GATE_TIMEOUT_S` deadline, group kill on
   timeout (copy `_reclaim`'s TERM-then-KILL shape), limiter acquired around
   the whole run.
3. Wire into `run_gates` ahead of today's parse: accepted → iterate the
   JSON view's gates exactly as the config's are iterated today; rejected →
   return one `CONFIG_ERROR` result carrying the candidate's message; cannot-
   run → fall through to the existing `load_factory_config` call at
   `:420-423`, and if *that* raises, return `config_error_result(error)` with
   the candidate's cannot-run reason appended to the `output_tail` (FR-006).
4. Tests fake the seam for the four outcome classes (US2-S1/S2/S3/S4/S5) and
   run one real end-to-end pass (US2-S6) using this repository's own root as
   the worktree — the suite already runs under `uv run`, so the subprocess
   reuses the live venv and costs seconds, not a venv build.

## Complexity Tracking

| Thing | Why it is not simpler |
| --- | --- |
| A subprocess protocol instead of an import | The worker must survive a broken candidate parser (trap 1); an import cannot give that, and it is the same boundary gate commands already cross. |
| Three outcomes instead of accept/reject | The third arm (cannot-run → fallback) is what keeps every non-self-hosted repo, every pre-CLI worktree, and every broken candidate on today's exact behaviour. A two-way design either crashes the worker or `CONFIG_ERROR`s every foreign repo. |
| A dedicated parse runner instead of the `GateExecutor` seam | The executor merges stderr into stdout by design (`gates.py:317`); the protocol needs a clean stdout for JSON (trap 3). |
| A file-existence probe before any subprocess | Without it, every Python target repo pays a speculative `uv run` — possibly a full venv build — per verification, to discover a parser it never had. |
| Full-config JSON rather than a gates-only payload | A curated payload needs a protocol version the day the dataclass grows; emitting `asdict(FactoryConfig)` and having the consumer ignore unknown fields is the forward-compatibility this spec exists to create. |

## Verification

`uv run pytest -q` green, with every pre-existing test in `tests/test_gates.py`
and `tests/test_factory_yaml.py` unmodified (trap 6 — an edit there is a wrong
fallback, not a test update). The tests that did not exist before are the point
of the epic: the interpretation table including exit-0-garbage (trap 2), the
deadlock case where the candidate accepts what the worker refuses, the
both-messages fallback tail, and one unfaked subprocess round-trip against this
tree. Constitution II: each is written first and each must fail first —
US2-S3's and part of US1-S4's are regression guards and must be *stated* as
such in their docstrings, since they fail only if the implementation
over-reaches. Finally, SC-002's grep: no `importlib`, no `sys.path` writes in
`factory/verify/gates.py`.
