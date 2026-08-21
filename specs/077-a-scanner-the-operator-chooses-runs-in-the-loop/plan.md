# Implementation Plan: a scanner the operator chooses runs in the loop

**Spec**: `specs/077-a-scanner-the-operator-chooses-runs-in-the-loop/spec.md`

## What already exists, and where

**Every line below was verified on 2026-08-20 by printing that exact line
number** (`sed -n '<n>p' <file>`), not by reading `grep -A` context and counting.
That distinction is not pedantry: three specs drafted on 2026-08-19 carried
anchors off by one to three lines throughout, and a review found 68
attempt-costing defects in them. Check each against the tree anyway — the tree
moves.

**US2 — the parser:**

- `factory/verify/factory_yaml.py:150` —
  `_VERIFY_STEPS = ("gates", "diff_check", "judge")`. **The tuple that grows.**
- `factory/verify/factory_yaml.py:147` —
  `_RESERVED_GATE_NAMES = frozenset({"gates", "diff_check", "judge", "config"})`.
  `quality` must join this too, or a repo could declare a *gate* named `quality`
  and collide with the step name.
- `factory/verify/factory_yaml.py:650` — `_read_verify(...)`, the whole ordering
  parser. Its docstring says "drawn from exactly the three step names" and its
  ordering rule for `judge` is the pattern to copy, not to rewrite.
- `factory/verify/models.py:264` —
  `verify_order: tuple[str, ...] = ("gates", "diff_check", "judge")` on
  `FactoryConfig`. The default that must stay behaviourally identical.
- `factory/verify/models.py:238-264` — `FactoryConfig`'s field block, opening at
  `version: int` and closing at `verify_order`. **A `quality:` block is a new
  field here**, and `factory/verify/models.py:260` —
  `ladder: "VerificationConfig" = field(default_factory=_default_ladder)` — is
  the exact shape to copy: a nested dataclass with a default factory, not a bag
  of loose keys.

**US3 — the registry. Two working precedents; copy, do not invent:**

- `factory/notify/adapter.py:70` — `_BUILTIN_ADAPTER_MODULES = {`, with the
  comment above it stating the property that matters: "Imported lazily at
  resolve time so this module stays free of the transports' own dependencies."
- `factory/controlplane/config.py:51` —
  `KNOWN_ESC_ADAPTERS = ("telegram", "webhook", "none")`. The closed set the
  parser holds, which the registry is then held equal to in both directions.
- `factory/mergequeue/forge.py:286` — `_REGISTRY: dict[str, ForgeBuilder] = {}`.
- `factory/mergequeue/forge.py:304` —
  `def resolve_forge(name: str | None = None, **seams: Any) -> Forge:`, including
  the retry-after-lazy-import shape at lines 313-320 and the error listing the
  registered names.
- `factory/verify/gates.py:255` — `class GateExecutor(Protocol):`, the narrow
  seam inside this very component. A `Scanner` Protocol belongs beside it in
  spirit, in its own module in fact.

**US4 — scoping, composing, recording:**

- `factory/verify/models.py:517` — `def compose_result(`. **Read its full
  signature at 517-533.** Every input is an explicit keyword argument:
  `gate_results`, `output_check`, `judge`, `criteria_sha256`, `loop_digest`, ...
  **FR-019 is satisfied by not adding a parameter here.** That is the whole
  test: if `compose_result` cannot see the quality report, no future one-line
  change makes a scan gate by accident.
- `factory/verify/diffbounds.py:69` —
  `def split_sections(diff_text: str) -> tuple[str, list[DiffSection]]:`. **The
  diff is already split per file. Reuse this.** Do not write a second unified-diff
  parser; this module exists precisely because two readers of a diff's size drifted
  into two answers.
- `factory/verify/diffcheck.py:156` — `def check_output(`, which already holds
  the attempt's diff. The scoping step needs changed line numbers, which means
  parsing hunk headers — the one thing `split_sections` does not already give you.
- `factory/verify/store.py:158` —
  `judge_verdict     TEXT,               -- JSON: JudgeVerdict | NULL (gates failed / no scenarios)`.
  **The exact precedent for FR-021**: a nullable evidence column whose NULL means
  "never ran", distinct from an empty result.
- `factory/verify/store.py:113` — the schema-version ledger comment; current
  `SCHEMA_VERSION` is **6**. US4 makes it 7.
- `factory/verify/store.py:368-371` — the additive `ALTER TABLE ... ADD COLUMN
  loop_digest TEXT` migration. **Copy this shape exactly**; pre-077 rows read
  NULL and are never backfilled.
- `factory/verify/store.py:439` — the `"judge_verdict"` entry in the column
  list; a new evidence column joins the same list.

**US1 — the sandbox the spike must run inside:**

- `factory/verify/gates.py:97` — `SCRUBBED_ENV_ALLOWLIST: tuple[str, ...] = (`,
  and read the eleven names that follow. `PATH`, `HOME`, `TMPDIR`, `LANG`,
  `LC_ALL`, `LC_CTYPE`, `TZ`, `TERM`, `USER`, `LOGNAME`, `SHELL`. **That is the
  entire environment a scanner gets.** No `XDG_CACHE_HOME`, no proxy variables,
  no network credentials.
- `factory/verify/gates.py:91` — `OUTPUT_TAIL_LIMIT = 32 * 1024`, the bound a
  scanner's stderr is subject to.
- `factory/verify/diffbounds.py:42` — `DIFF_INPUT_LIMIT = 64 * 1024`, with the
  comment above it. Read lines 38-44 in full: *"Raised from 60 KiB on 2026-08-17
  at the operator's direction — the original value was a comfort margin, not a
  measurement, and its first false positive was a fully-green story refused four
  times at 61,725 bytes (035/us1)."* **This is why US5 exists and why gating is a
  separate spec.**

## Traps

These are named hazards, met as declared scope rather than as failures.

### Trap 1 — the sandbox, which is where this will actually break

Gates run under bwrap with `--clearenv` and the eleven-name allowlist above. A
scanner that wants a cache directory, a config file in `$HOME`, a downloaded
rule pack, or any network access will **fail in the gate and pass in CI**, and
the two will disagree in a way that reads as flakiness.

This is the decisive divergence in this factory and it has cost real attempts.
US1's entire value is measuring it *before* the dependency approval, not after.
Run candidates through the real sandbox path. A bare `subprocess.run` proves
nothing here.

Concretely: point every scanner at `TMPDIR` for cache, run it offline, and treat
"needs the network" as disqualifying rather than as a configuration problem to
solve later.

### Trap 2 — do not write a second diff parser

`split_sections` at `diffbounds.py:69` already exists, and its module docstring
explains at length why the measurement lives there rather than behind
`judge.py`. Scoping needs *changed line numbers*, which means hunk headers —
extend within that module's discipline. A second unified-diff parser in this
component is a defect, not a convenience.

### Trap 3 — the judge-import fence is enforced on the import graph

Exactly one module in this component may import `factory/verify/judge.py`
(`FR-009` of an earlier spec, enforced by `tests/test_verification_sweep.py`).
The stated reason is that *importing the judge means you can spend money*. A new
scanner module must not become a second importer, and the sweep test will catch
it — but catching it costs an attempt, so do not write the import.

### Trap 4 — record-only must be structural, not configured

The temptation is to pass the quality report into `compose_result` and have it
ignore the value unless a `mode` flag says otherwise. **Do not.** That leaves the
gating switch one line away from being flipped by a future agent that reads
`mode` as dead code and "cleans it up".

`compose_result`'s signature at `models.py:517` is the enforcement. The report
reaches the store and nothing else. A test should assert the parameter is absent
by inspecting the signature, so the property survives a refactor.

### Trap 5 — a scanner that fails is data, and there are three precedents

`judge_unavailable` behind green gates passes with the fact recorded rather than
fabricated. `DeliveryReceipt` reports a transport that could not send. A broken
manifest is one `CONFIG_ERROR` result, never zero results. All three exist
because "no result" and "a clean result" are the shape a naive reader confuses.

`scanner_unavailable` is the fourth. Nothing in the scanner path raises past its
caller. A scanner that segfaults must not cost an attempt its evidence, and in
this spec it must not cost the attempt anything at all.

### Trap 6 — SARIF paths are not worktree-relative by default

A SARIF `artifactLocation.uri` may be absolute, worktree-relative, or a
`file://` URI, and different tools choose differently. Normalise against the
worktree root and **refuse to scope any finding whose path does not resolve
inside it** rather than guessing. A finding silently mapped to the wrong file is
worse than a finding dropped, because the record-only phase is being used to set
thresholds and a mis-mapped finding poisons that measurement.

### Trap 7 — the version string is not optional

FR-020 asks for the scanner's own version alongside the findings. It looks like
bookkeeping. It is the difference between "the code got worse this week" and
"ruff 0.6 added a rule", and US5's entire purpose is comparing counts across
weeks. Capture it at scan time; do not reconstruct it later.

### Trap 8 — do not add a coverage scanner, and do not add a threshold

Both are named in the spec's "refuses to measure" and "does not change"
sections. They are declared scope, not oversights. An implementer who adds a
`min_coverage` key because it seemed obviously missing has widened the spec, and
the reviewer should reject it on those grounds alone.

### Trap 9 — `quality` must be reserved as a gate name too

`_RESERVED_GATE_NAMES` at `factory_yaml.py:147` exists so a repo cannot declare
a gate whose name collides with a step name. Adding `quality` to `_VERIFY_STEPS`
without adding it here leaves exactly that collision, and it will present as a
confusing parse error rather than as the clear refusal the parser is built to
give.

## Approach, story by story

**US1** adds no production code. Run candidates with `uvx` so nothing enters
`pyproject.toml` — `uv` is already on the approved roster, which is what makes
this admissible under Constitution III without spending an approval. Candidates
worth measuring: `ruff` (lint, fast, single binary), `semgrep`, `bandit`,
`radon`/`xenon` (numbers rather than rules), and the CodeQL CLI (heavy; measure
it so the decision to skip it is a measurement). Commit the note and the SARIF
artifacts under this spec's directory.

The note's recommendation becomes the default scanner in US2's closed set. **US2
must not hardcode a scanner name this plan guesses at.**

**US2** is a parser change and a config dataclass. It is small, and it is
separated from US3 deliberately.

**US3** is the hook system, and it is the story the operator asked for. Follow
`factory/mergequeue/forge.py` closely: module-level `_REGISTRY`, a `register_*`
function, `resolve_*` that lazily imports the built-in module for the name and
retries the lookup, and an error that lists what is registered. The conformance
test holding the registry equal to the config's closed set in both directions
already exists for messengers; copy its structure.

**US4** is the scoping and the store column. The migration is additive and
follows `store.py:368`.

**US5** is a read surface over rows US4 writes. It has no new store state.

## What lands where

| Story | Touches |
| --- | --- |
| US1 | `specs/077-.../research/` only. No production code. |
| US2 | `factory/verify/factory_yaml.py`, `factory/verify/models.py` |
| US3 | new `factory/verify/scanner.py` + built-in adapter modules, `factory/controlplane/config.py` |
| US4 | new scoping code in `factory/verify/`, `factory/verify/store.py`, the verifier activity |
| US5 | `factory/cli/` |

US2 and US4 both touch `factory/verify/models.py`, which the US2 → US3 → US4
chain already serialises.

## Constitution check

- **III (dependencies)**: US1 spends no approval — `uvx` runs candidates
  ephemerally. The approval decision belongs to the operator *after* US1 reports,
  and a `docs/decisions.md` entry records it. **No story here may add a package
  to `pyproject.toml`.**
- **IV (determinism at the core)**: this spec moves work *toward* the
  deterministic half. The scanner is a subprocess and a parser; no LLM call is
  added anywhere.
- **II (test-first)**: every story's tests precede its implementation, and US4's
  central test is a negative — that the verdict does not move.
- **VIII (provable from the diff)**: US1's deliverable is a committed note with
  pasted command output, because the judge sees only the diff. A spike whose
  evidence lives in a terminal is a spike the judge must fail.
