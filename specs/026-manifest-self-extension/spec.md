---
state: draft
# specs_root: specs
# target_repo: /home/admin/code/ergane
# Scaffolded by `ergane findings promote` from
# `interpreter/manifest-schema-cannot-be-extended-by-a-story` (critical, observed
# 2026-08-09 on epic-020-landing-attribution/us1), then refined against the tree
# at 9594787 on 2026-08-11.
---

# Feature Specification: The gate that judges a story with the parser it is changing

## The defect in one sentence

`run_gates` validates the node's `factory.yaml` with the parser the **worker
process** imported from its own checkout (`factory/verify/gates.py:47`, called
at `:420`), never with the candidate parser sitting in the node's worktree — so
a story that extends the manifest schema is judged by the very code it exists to
change, fails as one `CONFIG_ERROR` in 0.0s before any gate command runs
(`:404-406`), and fails identically on every attempt. 020/us1 burned four
attempts proving it: its worktree held both halves of a correct change — the
parser taught to accept `landing_branch`, and the key declared — and the
worker's older parser rejected the manifest four times at
`_reject_unknown_keys` (`factory/verify/factory_yaml.py:140`).

This is a bootstrap deadlock, not a bug in any story. An escalation RETRY is
guaranteed to reproduce it, which makes the operator's most natural button the
wrong one. The aftermath is visible in the live tree: `factory.yaml:37-43`
carries a hand-written warning about exactly this, and the key it warns about
got in only because the parser landed first (438cfd0) and the worker was
restarted before an operator declared it.

## The fix, and its deliberate shape

Judge the manifest the way gate **commands** are already judged: by the
worktree's own code, run as a subprocess inside the worktree (`uv run`), never
imported into the worker. The worker must survive every way a candidate parser
can misbehave — absent, crashing, hanging, emitting garbage — because a broken
candidate is an ordinary failed attempt, and a worker taken down by one is an
epic taken down by one. A candidate that runs and *rejects* the manifest
surfaces as today's single `CONFIG_ERROR` result carrying the candidate's own
message; a candidate that *cannot run* falls back to the worker's imported
parser, which is exactly today's behaviour and keeps every target repo that
carries no parser — every repo but this one — working unchanged.

One subtlety, stated so nobody re-derives it nervously: **this spec's own
stories do not deadlock themselves.** They edit `gates.py` and add a CLI
entry to `factory_yaml.py`; they change no manifest schema and touch no
`factory.yaml`. The old worker's parser accepts their unchanged manifest, their
gates run, and the fix goes live for *future* stories once it lands and the
worker restarts.

What the fix does **not** buy, carried here as documentation rather than as a
binding rule (see Out of Scope): other worker-side readers of the committed
manifest — the standards read at dispatch
(`factory/activities/agent_activities.py:655-667`), epic onboarding
(`factory/activities/merge_activities.py:447-459`), the landing-branch read
(`factory/workgraph/worktree.py:419-435`) — still use the worker's imported
parser. All three degrade gracefully rather than kill attempts, but the
operational sequencing survives this spec: **a schema-extending story teaches
the parser to accept a key with fixtures only; the repository's own
`factory.yaml` gains the key only after the parser lands and the worker is
restarted on it.**

## User Scenarios & Testing

### User Story 1 - The parser learns to speak for itself (Priority: P1)

The factory package gains a subprocess-invocable entry point for its manifest
parser: `python -m factory.verify.factory_yaml <manifest-path>` parses the
named manifest and reports machine-readably — the parsed config as one JSON
document on stdout with exit 0 when the schema accepts, the
`FactoryConfigError` message on stderr with a distinguished rejection exit code
when it refuses. This is the worktree-side half of the protocol: any worktree
that carries the factory package automatically carries a parser that can be
asked, from outside the process, "do you accept this manifest, and what does it
say?" It is additive — no existing caller of `parse_factory_config` or
`load_factory_config` changes behaviour.

**Goal**: any tree's candidate parser is invocable as a subprocess and
distinguishes "accepted, here is the config" from "rejected, here is why" by
exit code and stream, so a caller never has to import it to consult it.

**Independent Test**: invoke the CLI as a real subprocess against a manifest
the schema accepts and one it refuses; assert the exit codes, the JSON, and the
rejection message without importing anything from the invoking test beyond the
protocol constants.

**Acceptance Scenarios**:

1. **Given** a manifest the schema accepts, **When**
   `python -m factory.verify.factory_yaml <path>` runs as a subprocess,
   **Then** it exits 0 and stdout is a single JSON document whose `gates` and
   `timeouts` equal what `parse_factory_config` returns in-process for the same
   text.
2. **Given** a manifest the schema refuses — an unknown top-level key —
   **When** the CLI runs, **Then** it exits with the distinguished rejection
   code, stdout carries no JSON, and stderr carries the `FactoryConfigError`
   message naming the rule slug and the source file, verbatim.
3. **Given** a manifest path that does not exist, **When** the CLI runs,
   **Then** it is an ordinary rejection carrying the `missing_manifest`
   message — never a traceback, because a traceback is indistinguishable from
   a crashed parser to the caller that matters.
4. **Given** the existing test suite for the parser library, **When** it runs
   unmodified, **Then** it is green: the CLI adds an entry point and changes no
   parsing behaviour.

### User Story 2 - The gate judges a manifest with the candidate's parser (Priority: P1)

`run_gates` resolves the node's manifest through the worktree's candidate
parser whenever the worktree carries one, invoked as a subprocess in the
worktree with the same environment discipline as gate commands. A candidate
acceptance yields the gates to run; a candidate rejection yields today's single
`CONFIG_ERROR` result carrying the candidate's message; a candidate that cannot
run — absent, crashing, timing out, or emitting anything that is not the
protocol — falls back to the worker's imported parser, byte-for-byte today's
behaviour. The worker process survives all four outcomes.

**Goal**: a story whose worktree teaches the parser a new manifest key and
declares that key is judged by its own candidate code and reaches its gate
commands — the 020/us1 shape stops being terminal — while every repo without a
candidate parser, and every worktree with a broken one, behaves exactly as
today.

**Independent Test**: with the candidate-parse seam faked to each of its
outcomes in turn, `run_gates` against a manifest the worker's parser refuses
either runs the declared gates (candidate accepted), returns one
`CONFIG_ERROR` with the candidate's message (candidate rejected), or returns
one `CONFIG_ERROR` with the worker's message plus a could-not-run note
(fallback) — and one unfaked end-to-end run against this repository's own tree
proves the real protocol.

**Acceptance Scenarios**:

1. **Given** a worktree whose candidate parser accepts a manifest that the
   worker's imported parser refuses, **When** `run_gates` runs, **Then** the
   manifest's declared gates are executed and one result per declared gate is
   returned — no `CONFIG_ERROR`, which is the deadlock killed.
2. **Given** a worktree whose candidate parser runs and rejects the manifest,
   **When** `run_gates` runs, **Then** exactly one `CONFIG_ERROR` result comes
   back, its `output_tail` carries the candidate parser's own message, and no
   gate command runs.
3. **Given** a worktree that carries no candidate parser — any target repo that
   is not this one — **When** `run_gates` runs, **Then** no subprocess parse is
   attempted and the manifest is judged by the worker's imported parser exactly
   as today, for both a manifest it accepts and one it refuses.
4. **Given** a worktree whose candidate parser cannot run — it crashes, times
   out, or exits nonzero without the rejection protocol — **When** `run_gates`
   runs, **Then** the worker process survives, the manifest is judged by the
   worker's imported parser, and if that parser also refuses it, the single
   `CONFIG_ERROR`'s `output_tail` carries both facts: the worker parser's
   message and a note that the candidate parser could not run.
5. **Given** a candidate invocation that exits 0 but whose stdout is not the
   protocol's JSON — the exact shape of a worktree based on a commit older than
   User Story 1, where `python -m factory.verify.factory_yaml` runs the module
   body and prints nothing — **When** the outcome is interpreted, **Then** it
   is treated as cannot-run and falls back; exit 0 alone is never acceptance.
6. **Given** this repository's own tree as the worktree and no seam faked,
   **When** `run_gates` parses the manifest through the real subprocess
   protocol, **Then** the gates it resolves equal what the in-process parser
   returns for the same manifest — the protocol proven end to end, not by
   fakes.

## Functional Requirements

- **FR-001**: The factory package MUST expose its manifest parser as a
  subprocess-invocable entry point that, for a manifest the schema accepts,
  emits the parsed config as a single JSON document on stdout and exits 0.
- **FR-002**: For a manifest the schema refuses — including an unreadable or
  absent path — that entry point MUST exit with one distinguished, documented
  rejection code and emit the `FactoryConfigError` message verbatim on stderr,
  never a traceback and never JSON.
- **FR-003**: `run_gates` MUST judge the worktree's manifest with the
  worktree's candidate parser whenever the worktree carries one, by running it
  as a subprocess inside the worktree. Worktree code MUST NOT be imported into
  the worker process on any path.
- **FR-004**: A candidate rejection MUST surface as the existing single
  `CONFIG_ERROR` gate result — carrying the candidate parser's message in
  `output_tail` — and nothing else may run, preserving the one-result contract
  a broken manifest has today.
- **FR-005**: A candidate parser that cannot run — absent, failing to start,
  crashing, exceeding its deadline, or producing output that is not the
  protocol (exit 0 included) — MUST NOT crash or fail the worker; `run_gates`
  MUST fall back to the worker's imported parser and behave exactly as today.
- **FR-006**: When the fallback path's worker parser also refuses the manifest,
  the `CONFIG_ERROR`'s `output_tail` MUST record both the worker parser's
  message and the fact that the candidate parser could not run — an operator
  diagnosing that row needs both halves.
- **FR-007**: The candidate parse subprocess MUST be bounded the way gate
  commands are: a deadline, its own session with group kill on timeout, and the
  scrubbed allowlist environment — a hung or credential-hungry parser gets no
  more room than a hung gate.
- **FR-008**: For any worktree without a candidate parser, behaviour MUST be
  observably unchanged: the existing gate-runner test suite passes without
  modification, and no subprocess is spawned for the parse.

## Success Criteria

- **SC-001**: The 020/us1 shape — a worktree that both teaches the parser a new
  top-level key and declares that key in its manifest — reaches its gate
  commands instead of dying `CONFIG_ERROR` at 0.0s.
- **SC-002**: No code path imports worktree code into the worker process;
  `grep` finds no `importlib`/`sys.path` route from `factory/verify/gates.py`
  into a worktree.
- **SC-003**: The full suite is green with `tests/test_gates.py`'s and
  `tests/test_factory_yaml.py`'s pre-existing tests unmodified — they are the
  regression harness for FR-005/FR-008, and needing to edit one means the
  fallback is not byte-identical.
- **SC-004**: User Story 1 is landable alone and changes no runtime behaviour:
  a tree with the CLI and the old `run_gates` behaves exactly as before.
- **SC-005**: No new dependency (constitution III): the protocol is
  `subprocess`, `json`, and the already-approved `pyyaml`.

## Edge Cases

- **A worktree based on a pre-CLI commit.** Its `factory/verify/factory_yaml.py`
  exists (so the probe finds a candidate) but has no `__main__` handling —
  `python -m` runs the module body, prints nothing, exits 0. US2-S5 pins this
  to cannot-run → fallback. Exit 0 is necessary but never sufficient for
  acceptance.
- **stderr noise.** `uv run` writes progress and warnings to stderr. The
  protocol reads JSON from stdout only; stderr is diagnostics, kept for the
  could-not-run evidence tail.
- **A cold worktree.** The first `uv run` in a fresh worktree may have to build
  its environment. The parse deadline is the gate-timeout default, not a
  "parsing is fast" few seconds — a too-short bound would convert a cold cache
  into cannot-run → fallback → the same four identical `CONFIG_ERROR` attempts
  this spec exists to kill, with extra steps.
- **Candidate accepts keys the worker has never heard of.** The worker consumes
  only `gates` and `timeouts` from the protocol JSON and ignores every other
  field — that forward-compatibility is the point. Structurally invalid JSON
  (gates not a string-to-string mapping, timeouts not positive integers) means
  the candidate is broken: cannot-run, fallback.
- **The manifest-path override.** `RunGatesInput.factory_yaml_path`
  (`factory/activities/verify_activities.py:220`) stays honoured: the candidate
  CLI takes the manifest path as its argument, whatever it is; the *parser* is
  resolved from the worktree, the *manifest* from the request.
- **This epic judging its own stories.** The worker running this spec's epic
  imports the pre-fix `gates.py` from its own checkout; the stories' worktrees
  leave the manifest untouched, so the old in-process parse accepts it and the
  gates run. The fix is inert for the epic that builds it, live after landing +
  worker restart.

## Assumptions

- A candidate parser is present exactly when
  `factory/verify/factory_yaml.py` exists under the worktree root — true for
  this repository and no other current target. The probe is a file-existence
  check, deliberately, so foreign Python repos never pay for a speculative
  `uv run` environment build.
- `uv run` works in any worktree that carries a candidate parser: this
  repository's own gate command is `uv run pytest -q` (`factory.yaml:23`), so a
  worktree where `uv run` is broken was already failing its gates. A carried
  parser that cannot be `uv run` lands in cannot-run → fallback, which is safe.
- The activity surface does not change: `RunGatesInput` keeps its shape, the
  workflow call site (`factory/workgraph/workflow.py:1710-1717`) is untouched,
  and the seam for tests is a parameter on the library's `run_gates`, mirroring
  the existing `executor` parameter.
- No new dependency, no new activity, no new store.

## Out of Scope

- **A constitution rule forbidding schema-extending stories from declaring the
  new key** (the finding's candidate fix 3). The constitution is promoted into
  when a defect class has *recurred*; this one has one occurrence, and the code
  fix removes the deadlock rather than legislating around it. The residual
  sequencing rule — the live manifest gains a key only after its parser lands
  and the worker restarts — is real but operational, already written where an
  operator will meet it (`factory.yaml:37-43`), restated in this spec's
  preamble, and claimed in the landing's decision entry. If a second story
  burns on it after this fix lands, that recurrence is the promotion case.
- **Treating unknown top-level keys as warnings** (candidate fix 2). The
  parser's whole design is that a shrugging verifier hands out PASSes for
  repos it never tested — `factory/verify/factory_yaml.py`'s module docstring
  says exactly this. Weakening rejection to warning would trade a loud
  deadlock for silent under-verification.
- **Candidate-parsing the other manifest readers.** The standards read,
  onboarding, and the landing-branch read still use the worker's parser; all
  degrade gracefully (return `None`, report a finding, fall back to the
  checked-out branch) and none has ever burned an attempt. Extending the
  protocol to them is real work with no motivating failure.
- **023's schema v2 itself.** 023-composable-verification will extend the
  manifest with `version: 2`, `ladder:` and `verify:` blocks — the largest
  schema extension yet planned. The synthesis pass (2026-08-11) examined 023's
  trio and drew **no** `depends_on_landed` edge: 023's own FR-011 keeps the
  repository's committed `factory.yaml` at `version: 1`, byte-unmodified in
  every story diff, with v2 manifests existing only as `tmp_path` test
  fixtures — so the deadlock this spec kills cannot reach 023's stories. The
  live manifest's eventual flip to v2 is an operator act that comes after a
  parser lands and the worker restarts — the same sequencing rule this spec's
  preamble states — which is why landing this fix early remains desirable even
  with no edge drawn.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-003, FR-004, FR-005, FR-006, FR-007, FR-008]
```

US2 takes a merge-edge, not a pass-edge: its end-to-end scenario (US2-S6)
invokes the CLI that US1 builds, so US2's base must *contain* US1's code — a
pass-edge guarantees a verdict, not content.
