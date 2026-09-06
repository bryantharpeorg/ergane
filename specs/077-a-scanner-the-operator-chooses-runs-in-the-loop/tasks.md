# Tasks: a scanner the operator chooses runs in the loop

**Spec**: `specs/077-a-scanner-the-operator-chooses-runs-in-the-loop/spec.md`
**Plan**: `specs/077-a-scanner-the-operator-chooses-runs-in-the-loop/plan.md`

Read `plan.md` before the first task. Eight of its traps decide whether an
attempt lands. **Trap 17**: the boundary binds four executables as read-only
*leaves* — `uv`, `node`, `git`, the agent runner — and never their directories,
so `uvx` does not exist inside it; run `uv tool run <tool>` or every candidate is
disqualified for a path no bind carries, which is the false measurement US1
exists to prevent. **Trap 18**: `_VERIFY_STEPS` is *also* what `_read_verify`
returns for a manifest with no `verify:` key, and `ergane.yaml` has none, so
growing that one tuple moves this repository's own `loop_digest` and fails
US2-S5. **Trap 1**: the gate boundary is manifest-selected, falls back to a host
subprocess when bwrap is absent, and leaves network egress open on purpose — so
"needs the network" disqualifies nothing and a spike can silently measure the
wrong machine. **Trap 2**: `/tmp` inside that boundary is a private tmpfs and no
`TMPDIR` is set, so a SARIF file written there is gone before the factory reads
it; anything written *inside* the worktree is staged by `git add -A`, committed
by salvage and charged against the 64 KiB refusal threshold. The one destination
that survives is the node's metadata directory under the parent repository's
`.git`. **Trap 3**: the store's column tuple is positional and a column added out
of order hands every field of every row to the wrong attribute without raising.
**Trap 5**: `verify_order` sequences nothing — US2's step name changes a digest
and executes nothing until US6 wires the call, and the diff text that call needs
is read today only inside the judge branch. **Trap 14**: the scanner closed set
has exactly one home, it is US2's, and it holds ADAPTER names (`sarif`, `none`)
rather than tool names. **Trap 15**: an unconditional key in the digest dict
moves every repository's `loop_digest`, including the ones with no scanner — and
there is exactly one admissible fix for it, not two.
**Trap 16**: this repository's manifest is `ergane.yaml`; the `factory.yaml`
still sitting beside it is a stale `version: 1` file no reader consults, and
reading or editing it costs an attempt.

**This spec is record-only by construction.** No story in it may cause a scan to
change a verdict. If a task looks like it needs to, the task has been misread —
re-read the spec's truth table under "The rule this spec is asking for".

Phases below run in story-number order except one: **Phase 6 (User Story 6) runs
before Phase 5 (User Story 5)**, because US6 is the half of the original US4 that
was split out at refinement and US5 queries the rows US6 writes. The Work Graph
in `spec.md` is the authority on order; this document is ordered by number so
nothing is hunted for.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the
judge sees; runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — The operator learns which scanners survive this sandbox

No production code lands in this story. Its deliverable is committed evidence,
because the judge sees only the diff (Constitution VIII) — a spike whose proof
lives in a terminal is a spike that must fail.

### Tests for this story (write FIRST, must fail)

- [ ] T001 [US1] (trap 1, trap 16) Before running any candidate, write down the
      expected backend by reading `factory/verify/gates.py:1346` —
      `_resolve_gate_executor` and checking two facts on this host: that
      **`ergane.yaml:26`** declares `runtime: bwrap`, and that `/usr/bin/bwrap`
      is a file. Paste both checks. Read `ergane.yaml`, not the `factory.yaml`
      beside it: `factory/verify/factory_yaml.py:71` is
      `MANIFEST_NAME = "ergane.yaml"` and
      `factory/verify/gates.py:1409` — `resolve_gate_executor` composes
      `worktree / MANIFEST_NAME`
      directly, so the legacy file is never consulted — and it is `version: 1`
      with no `ladder:` block, so a fact read off it is a fact about a file
      production ignores. If the bwrap check is false, every later measurement is
      a host measurement and the note must say so before it says anything else.
- [ ] T002 [US1] (spec US1-S6, FR-003, trap 2) Before any candidate runs, probe
      the artifact channel. Through `factory/verify/gates.py:1394` —
      `resolve_gate_executor`, run one command that writes a byte to `$TMPDIR`,
      one to `/tmp`, and one to the node's metadata directory under the parent
      repository's `.git`. Paste a host-side `ls -l` of all three taken **after
      the executor returned**. The expected result, derived in plan.md from
      `factory/verify/gates.py:678` — `_build_argv` and
      `factory/verify/gates.py:704` — `_build_argv`, is that only the third
      survives. If the paste says otherwise, stop and say so in the note: FR-026
      is built on this fact and US3 must be re-planned before it is dispatched.

### Implementation for this story

- [ ] T003 [P] [US1] (spec US1-S1, FR-001, trap 17) Run each candidate through
      **`uv tool run <tool>`**, never `uvx`, so nothing enters `pyproject.toml`.
      `uvx` is a separate binary beside `uv` and the boundary binds only leaves:
      `factory/verify/gates.py:753` — `_toolchain` resolves
      `(UV, NODE, GIT, DEFAULT_AGENT_RUNNER)` and
      `factory/verify/toolchain.py:185` — `bind` returns one file per tool, not
      its directory, so `uvx` is not in there and every candidate would die
      `command not found`. Candidates: `ruff`, `semgrep`, `bandit`,
      `radon`/`xenon`, and the CodeQL CLI. Paste
      `git diff --stat -- pyproject.toml uv.lock` showing no change into the
      note.
- [ ] T004 [US1] (spec US1-S3, FR-003) For each candidate record the **exact**
      command, exit code, wall-clock and whether SARIF came back well-formed.
      Record the flag that actually worked, not the one the docs claim — a
      documented flag that does not exist is this repository's most expensive
      recurring defect class (`gh pr checks --json`, which never existed, cost
      epic 061 three stories).
- [ ] T005 [US1] (spec US1-S2, FR-002, trap 1, trap 17) Run each surviving
      candidate through `factory/verify/gates.py:1394` — `resolve_gate_executor`
      rather than a bare `subprocess.run`, with the command spelled
      `uv tool run <tool> ...` for the reason T003 gives, and record the **class
      name of the backend it returned** beside each result. A candidate executed by
      `SubprocessGateExecutor` is recorded as **not measured** in those words.
- [ ] T006 [US1] (spec US1-S7, FR-003, trap 1) Record why each disqualified
      candidate failed, in the boundary's own terms: a path no bind carries, or
      a wall-clock overrun. **"Needs the network" is not a disqualification** —
      `factory/verify/gates.py:549` — `BwrapGateExecutor` leaves egress open
      deliberately and `factory/verify/gates.py:888` — `_resolver_binds` binds
      the resolver and trust roots to make it work, which is also why T003's
      `uv tool run` invocations are possible at all. A note that disqualifies a
      candidate for needing the network has measured a constraint this boundary
      does not impose. Before writing "a path no bind carries" against a
      candidate, check it is not trap 17 wearing that sentence: a `command not
      found` for the runner itself is a defect in the invocation, not a fact
      about the candidate.
- [ ] T007 [US1] (trap 1, trap 17) For any candidate that failed for want of a
      cache directory, record whether a `caches:` declaration would carry it —
      `factory/verify/factory_yaml.py:694` — `_read_caches` binds a path and
      sets one environment name. A cache is declarable; a writable path with no
      bind and no possible declaration is what disqualifies. Record separately
      that the **uv** cache needs no declaration:
      `factory/verify/gates.py:943` — `_cache_binds` binds `~/.cache/uv`
      writable unconditionally and
      `factory/verify/gates.py:945` — `_cache_binds` pairs it with
      `UV_CACHE_DIR`, so a `uv tool run` install persists between runs and the
      wall-clock T009 measures is a warm one. Say in the note which runs were
      cold.
- [ ] T008 [P] [US1] (spec US1-S4, FR-004, trap 2) Commit **exactly two** SARIF
      artifacts under `specs/077-a-scanner-the-operator-chooses-runs-in-the-loop/research/`
      — the recommended candidate's and one contrasting candidate's — each
      **reduced** to `runs[].results` plus only the rules those results name and
      held under 8 KiB. Every other surviving candidate is recorded as counts
      alone. The number is fixed by FR-004 rather than chosen here: five
      survivors at 8 KiB is 40 KiB of a 64 KiB refusal before the note exists.
      Scanning one small file does not bound a SARIF
      document: `tool.driver.rules` is sized by the ruleset that ran and carries
      a description and a help blob per rule, which for semgrep and the CodeQL
      CLI is hundreds of KiB from a one-file scan.
- [ ] T009 [US1] (spec US1-S5, FR-003) Measure each candidate against a **real
      node diff** from this repository, not against the whole tree, and paste
      the wall-clock beside the gates' own runtime. A scanner slower than the
      suite it follows changes the loop's economics and the recommendation must
      reckon with it.
- [ ] T010 [US1] (spec US1-S5, trap 14) Recommend one default scanner, citing
      the pasted measurements, and write the recommendation as **the `command:`
      string an operator puts in `ergane.yaml`'s `quality:` block** — a full
      command line with the SARIF flag T004 proved, not a bare tool name. The
      output path in that string must be **`$ERGANE_QUALITY_SARIF`**, the
      variable FR-014 fixes: the adapter chooses the destination and exports it
      on the invocation's `env`
      (`factory/verify/gates.py:269` — `GateInvocation`), so a recommendation
      naming a literal path is a command line no adapter can direct. Run the
      recommended command once with that variable set by hand and paste the
      result, so the string is proven rather than composed. It is
      **not** a member of US2's closed set: that set holds the adapter names
      `sarif` and `none`, which FR-014 and FR-015 fix, and US2 runs
      `concurrent_with: [US1]` and cannot read this note at all.

### Verification for this story

- [ ] T011 [US1] (spec US1-S4, FR-004) Paste, as committed evidence, the output
      of `git diff --stat` for this story's own branch, the total byte count,
      and the unreduced byte count of **every** candidate's full SARIF document
      beside the two reduced artifacts that were committed, naming which
      survivors are recorded as counts alone. The bound is FR-004's two, decided
      at refinement, not a judgement made here against
      `factory/verify/diffbounds.py:66`: a story that discovers its own size at
      commit time discovers it by being refused unjudged.

## Phase 2: User Story 2 — A loop can name a quality step, and one that does not costs nothing

### Tests for this story (write FIRST, must fail)

- [ ] T012 [P] [US2] (spec US2-S1, FR-005) In `tests/test_quality_step_config.py`,
      assert a v2 manifest with `quality` in `verify:` resolves and the step
      appears in the resolved order.
- [ ] T013 [P] [US2] (spec US2-S2, FR-006) Assert `quality` before `gates`, and
      `quality` before `diff_check`, are each refused, **and that each refusal
      is the ordering one** — its message names the step `quality` must follow —
      rather than the unknown-step refusal at
      `factory/verify/factory_yaml.py:943` — `_read_verify`. Both refusals carry
      the same rule slug, `"verify"`, so the slug cannot tell them apart; assert
      on the message. Note in the test that until T021 admits `quality` into
      `_VERIFY_STEPS` this assertion fails for the wrong reason, which is what
      makes it a first-failing test rather than a vacuous one.
- [ ] T014 [P] [US2] (spec US2-S3, FR-006) Assert `judge` before `quality` is
      refused with the ordering message and not the unknown-step one. The
      ordering rule exists so the follow-on gating spec has a seam; it does
      **not** mean a red scan skips the judge, because in this spec a scan
      changes nothing.
- [ ] T015 [P] [US2] (spec US2-S4, FR-007, trap 14) Assert a `scanner:` outside
      the closed set — use `ruff`, which is a tool name and belongs in
      `command:` — is refused with the admissible names listed in the message,
      and that the names come from the single closed set this story lands in
      `factory/verify/factory_yaml.py`. The set is `("sarif", "none")`: those are
      **adapter** names, fixed by FR-014 and FR-015 rather than guessed, and
      US3's FR-013 conformance test holds the registry equal to them.
- [ ] T016 [P] [US2] (spec US2-S5, FR-005, FR-008, trap 18) Assert a manifest
      omitting `quality` resolves to a `FactoryConfig` equal to today's, **that
      its resolved `verify_order` is still exactly
      `("gates", "diff_check", "judge")`**, and that the module path
      `factory.verify.scanner` is absent from `sys.modules` afterwards. The
      order assertion is the one that can fail: `_VERIFY_STEPS` is also what
      `factory/verify/factory_yaml.py:924` — `_read_verify` returns for an
      absent `verify:` key, so T021 done the obvious way turns this red. State
      in the test that the `sys.modules` half becomes load-bearing the moment US3
      creates that module — it is named by path for exactly that reason.
- [ ] T017 [P] [US2] (spec US2-S6, FR-009) Assert two manifests differing only
      in scanner name produce different `loop_digest` values.
- [ ] T018 [P] [US2] (spec US2-S7, FR-011, trap 10) Assert **one** manifest body
      declaring `quality:` parses under `version: 2` and is refused under
      `version: 1` as an unknown top-level key. Both halves in one test: the v1
      half alone passes today, before any change, so only the pair can fail a
      diff that registered the key in `_TOP_LEVEL_KEYS`
      (`factory/verify/factory_yaml.py:109-121`) instead of
      `_V2_TOP_LEVEL_KEYS` (`factory/verify/factory_yaml.py:134`).
- [ ] T019 [P] [US2] (spec US2-S8, FR-010) Assert the scanner survives the whole
      carrier chain, link by link, not merely that a constructor names it: the
      tuple `factory/verify/factory_yaml.py:1068` — `load_loop_config` returns,
      the `factory/activities/roadmap_activities.py:821` —
      `ReadLoopConfigResult` the activity builds from it, and the `EpicInput`
      constructed at `factory/roadmap/workflow.py:1296` — `_dispatch` beside the
      `verify_order` read at `factory/roadmap/workflow.py:1300` — `_dispatch`. A second
      assertion covers the CLI path, whose manifest read at
      `factory/cli/nouns/build.py:826` — `start_command` reaches its **one**
      `EpicInput` at `factory/cli/nouns/build.py:931` — `_start_epic` through
      the call at `factory/cli/nouns/build.py:844` — `start_command`. Two
      constructions carry a manifest, not three; the tree's third,
      `factory/workgraph/cli.py:675` — `_start_epic`, reads none and is out of
      scope (FR-010).
      The roadmap is how this factory actually dispatches, and a test that stops
      at the parser would pass against a key the roadmap never carries.
- [ ] T081 [P] [US2] (spec US2-S9, FR-007) Assert a `quality:` block naming
      `scanner: sarif` with no `command:` is refused by name, and — in the same
      test — that the identical block *with* a `command:` parses and the command
      survives onto the resolved config. Both halves, because a refusal that
      rejects the whole block would pass the first assertion alone. Without this
      key FR-014's "declared command" has no declarer anywhere in the schema and
      a US3 implementer is left to hardcode a tool's command line inside the
      adapter.
- [ ] T020 [P] [US2] (trap 9) Assert a repo declaring a **gate** named `quality`
      is refused, as `_RESERVED_GATE_NAMES`
      (`factory/verify/factory_yaml.py:168`) already refuses `gates`,
      `diff_check`, `judge` and `config`.

### Implementation for this story

- [ ] T021 [US2] (FR-005, FR-008, trap 18) Split `_VERIFY_STEPS`'s two roles
      before growing either. `factory/verify/factory_yaml.py:171` is the tuple,
      and the comment above it at `factory/verify/factory_yaml.py:170` says it is
      both "the verification steps a v2 `verify:` list may name" **and** "today's
      default" — `factory/verify/factory_yaml.py:924` — `_read_verify` returns
      it verbatim when the manifest declares no `verify:` key, which
      `ergane.yaml` does not. So: add `quality` to the **admissible set only**,
      give the absent-key return its own default tuple mirroring the literal
      already at `factory/verify/models.py:340` — `FactoryConfig`, and correct
      the comment so it no longer claims one tuple is both. Adding `quality` to
      the single tuple hands every v2 repository that omits `verify:` a fourth
      step it never asked for, fails T016, and moves its `loop_digest`.
- [ ] T022 [US2] (trap 9) Add `quality` to the `_RESERVED_GATE_NAMES` frozenset
      at `factory/verify/factory_yaml.py:168`.
- [ ] T023 [US2] (FR-011, trap 10) Register `quality` in `_V2_TOP_LEVEL_KEYS`
      (`factory/verify/factory_yaml.py:134`) and **not** in `_TOP_LEVEL_KEYS`
      (`factory/verify/factory_yaml.py:109-121`), so
      `factory/verify/factory_yaml.py:269` — `_reject_unknown_keys` refuses it
      under v1.
- [ ] T024 [US2] (FR-006) Extend the ordering rules in
      `factory/verify/factory_yaml.py:915` — `_read_verify`, and update its
      docstring, which still says "exactly the three step names". **Copy the
      existing `judge` ordering check at
      `factory/verify/factory_yaml.py:964` — `_read_verify`; do not rewrite the
      function.** The new refusals must stay distinguishable in their message
      from the unknown-step refusal, which T013 and T014 assert.
- [ ] T025 [US2] (FR-007, trap 14) Land the scanner closed set as a module-level
      constant in `factory/verify/factory_yaml.py`, beside `_VERIFY_STEPS`
      (`factory/verify/factory_yaml.py:171`), holding the two **adapter** names
      FR-014 and FR-015 fix: `sarif` and `none`. This is the **only** copy of
      that set in the tree; US3 imports it and adds no second one. Then parse the
      `quality:` block's **two** keys: `scanner:`, held to that set, and
      `command:`, the command line the adapter runs — required when
      `scanner: sarif`, and carried unread beside `scanner: none` rather than
      refused, so disabling a scanner stays a one-word edit (T081 asserts both).
      Copy the shape of
      `factory/verify/factory_yaml.py:694` — `_read_caches` and the field shape
      of the `ladder:` field at `factory/verify/models.py:336` — `FactoryConfig`:
      a nested dataclass with a default factory, not loose keys. Do not write the
      legacy manifest filename as a literal in this module —
      `factory/verify/factory_yaml.py:73-77` assembles it from fragments on
      purpose (trap 16).
- [ ] T026 [US2] (FR-007) Append the new field to `FactoryConfig` **after**
      `factory/verify/models.py:358` — `FactoryConfig`, which is `caches` and is
      the class's current last line. The block does not end at 340; a field
      inserted mid-class changes nothing functionally but the plan's earlier
      claim that it did was wrong, and the last-field position keeps the
      dataclass's default ordering legal.
- [ ] T027 [US2] (FR-008) Confirm the default `verify_order`
      (`factory/verify/models.py:340` — `FactoryConfig`) is unchanged and that
      resolution imports no scanner module.
- [ ] T028 [US2] (spec US2-S10, FR-009, trap 15) Fold the resolved scanner into
      `factory/verify/models.py:1132` — `loop_digest` and
      `factory/verify/models.py:1158` — `loop_summary`. Both take a
      `VerificationConfig` rather than a `FactoryConfig` and both are called at
      `factory/workgraph/workflow.py:2650` — `_verify` with `request.config`, so
      the scanner arrives from `EpicInput`. **Put the key in the digest dict when
      and only when a scanner is resolved.** That is the only admissible move:
      bumping the `schema_version` keyword at
      `factory/verify/models.py:1137` — `loop_digest` moves every digest on the
      floor at once, which FR-009 forbids in terms and US2-S10 fences with
      pasted evidence. An unconditional key does the same thing more quietly.
      T031 is what catches either.
- [ ] T029 [US2] (FR-010) Widen the carrier chain end to end so the resolved
      `quality:` block reaches dispatch: the tuple returned at
      `factory/verify/factory_yaml.py:1086` — `load_loop_config`, a **defaulted**
      field on `factory/activities/roadmap_activities.py:832` —
      `ReadLoopConfigResult` (defaulted for the reason its own docstring gives —
      a scripted result written before this story must still construct), the
      construction at `factory/activities/roadmap_activities.py:858` —
      `read_loop_config`, `factory/roadmap/workflow.py:1300` — `_dispatch`, and the field
      beside `verify_order` at `factory/workgraph/workflow.py:562` — `EpicInput`.
      **It must never be read from the node worktree** — that asymmetry is the
      whole reason a gate was rejected as the destination. Widening
      `load_loop_config`'s tuple turns **two landed test files** red and they are
      declared work, not a surprise: `tests/test_023_us2_dispatch_pin.py:823`
      unpacks it as `config, verify_order, _`, and
      `tests/test_092_manifest_threshold.py:186` and
      `tests/test_092_manifest_threshold.py:233` unpack it as `_, _, declared`.
      Update both in this story.
- [ ] T030 [US2] (FR-010) In `factory/cli/nouns/build.py:913` — `_start_epic`,
      give the new parameter the same treatment 092 gave `diff_refusal_bytes`
      three lines below at `factory/cli/nouns/build.py:917` — `_start_epic`: a
      caller that read no manifest must not silently get a scanner, and "no
      scanner" must not be reachable by omission from a caller that had one.
      Wire the call at `factory/cli/nouns/build.py:844` — `start_command`, which
      is a keyword on a `_start_epic(...)` call rather than a construction, and
      the one construction it reaches, `factory/cli/nouns/build.py:931` —
      `_start_epic`. Leave `factory/workgraph/cli.py:675` — `_start_epic`
      alone: it reads no
      manifest and passes neither `verify_order` nor `diff_refusal_bytes`.

### Verification for this story

- [ ] T031 [US2] (spec US2-S5, spec US2-S10, FR-008, FR-009, trap 15, trap 18)
      Paste, as committed evidence, the `loop_digest` this repository's own
      **`ergane.yaml`** resolves to before and after this story, showing them
      equal, and beside them the resolved `verify_order` before and after, also
      equal — the manifest names no `quality` step and declares no `verify:` key
      at all, so neither may move. Name the file in the
      pasted command. `ergane.yaml` is what `MANIFEST_NAME`
      (`factory/verify/factory_yaml.py:71`) resolves and the only one carrying
      this repository's `ladder:` block; a digest taken from the `factory.yaml`
      beside it is a digest of a `version: 1` file production never reads, and
      the ladder difference alone would make the two numbers disagree.

## Phase 3: User Story 3 — A scanner is an adapter resolved by name

This is the hook system. Follow `factory/mergequeue/forge.py:342` —
`resolve_forge` and the dict at `factory/notify/adapter.py:70` closely — two
working precedents, both lazy-import registries held to a config's closed set.
Invent nothing, and add no second closed set (trap 14).

### Tests for this story (write FIRST, must fail)

- [ ] T032 [P] [US3] (spec US3-S1, FR-012) In `tests/test_scanner_registry.py`,
      assert importing the registry module leaves no candidate scanner's package
      in `sys.modules`.
- [ ] T033 [P] [US3] (spec US3-S2, FR-014, FR-007) Assert **first** that the
      `GateInvocation` the adapter builds carries `ERGANE_QUALITY_SARIF` on its
      `env` (`factory/verify/gates.py:269` — `GateInvocation`), holding the same
      absolute path the adapter then reads; **then** that it runs the `command:`
      the manifest's `quality:` block declares — the key US2 landed in T025, not
      a string this module holds — and returns parsed findings. Both, in that
      order: an adapter that computes a path, never tells the command, and reads
      a fixture already sitting there passes the second assertion alone, and a
      fixture-driven test is exactly where that goes unnoticed. Driven by a
      committed fixture SARIF file, with no real scanner installed. Hardcoding a
      tool's command line inside the adapter satisfies the letter of this and
      kills the swappability the whole spec exists for.
- [ ] T034 [P] [US3] (spec US3-S7, FR-026, trap 2) **Build the fixture as a
      linked worktree** — a parent repo plus `git worktree add` — because that is
      what every node is and it is the only shape in which
      `factory/verify/gates.py:1018` — `_resolve_target_git_dir` returns a path
      outside the worktree. Against it, assert the path the adapter directs the
      command to write is under the directory that function resolves, which for
      this shape is the parent repository's `.git`; that it is **unique to this
      worktree**, asserted by adding a second linked worktree to the same parent
      and showing the two destinations differ — that one `.git` is shared by
      every node of the repository and this floor has run the node cap at two, so
      a fixed filename there is two attempts scored against each other's
      findings; that it is not under `/tmp` or `$TMPDIR`; and that
      `git status --porcelain` in the worktree is empty and its tracked listing
      byte-identical before and after. **Do not use
      `tmp_path` plus `git init`**: that is the other branch, where the function
      returns `<worktree>/.git` — still git metadata `git add -A` never stages,
      which is the invariant FR-026 rests on, but *inside* the worktree, so the
      outside-the-worktree half of this assertion would fail a correct
      implementation. This is the test that keeps the scanner out of
      `factory/workgraph/worktree.py:1496` — `diff`, which stages untracked
      files with `git add -A`, and out of
      `factory/workgraph/worktree.py:511` — `salvage`, which commits them.
- [ ] T035 [P] [US3] (spec US3-S3, FR-015) Assert the `none` scanner returns an
      empty report and executes no command.
- [ ] T036 [P] [US3] (spec US3-S4, FR-016) Assert **three** separate failure
      modes each produce `scanner_unavailable` with a reason and **raise
      nothing**: non-zero exit, exceeded deadline, malformed SARIF. One
      assertion covering one mode does not prove the other two. The deadline is
      not this story's to invent: FR-016 fixes it at the one a gate with no
      `timeouts:` entry already gets,
      `factory/verify/models.py:1201` — `VerificationConfig`'s `gate_timeout_s`,
      carried on the same dispatched config. Do **not** add a `timeout:` key to
      the `quality:` block — that widens a two-key block US2 has already landed
      the parser for, and `timeouts:` maps gate names only.
- [ ] T037 [P] [US3] (spec US3-S5, FR-013, trap 14) Assert the registry's keys
      and the closed set US2 landed in `factory/verify/factory_yaml.py` match
      **in both directions**, importing that constant rather than restating it.
      Copy the messenger conformance suite's structure, which holds
      `factory/controlplane/config.py:51` and `factory/notify/adapter.py:70`
      together the same way — that suite is the precedent for the test's shape
      and for nothing else; this story's diff must not touch
      `factory/controlplane/config.py`.
- [ ] T038 [P] [US3] (spec US3-S6, FR-016, trap 2) Assert that when
      `factory/verify/gates.py:1018` — `_resolve_target_git_dir` returns `None`,
      the adapter records `scanner_unavailable` naming the missing destination
      rather than returning an empty report. **Drive it with a directory that has
      no `.git` entry at all** — that function's only `None` return is
      `if not git_file.exists()`, so a `git init` fixture returns
      `<worktree>/.git` and this test would prove nothing. A boundary that cannot
      carry the artifact back must never read as a clean scan.
- [ ] T039 [P] [US3] (FR-012) Assert resolving an unregistered name raises with
      the registered names listed.

### Implementation for this story

- [ ] T040 [US3] (FR-012) Add `factory/verify/scanner.py`: a `Scanner` Protocol
      in the shape of `factory/verify/gates.py:288` — `GateExecutor`, a
      module-level registry, a `register_scanner`, and a `resolve_scanner(name)`
      with the lazy-import-then-retry shape from
      `factory/mergequeue/forge.py:342` — `resolve_forge`. It is a new module in
      `factory/verify/`, unrelated to `factory/discovery/llm_scanner.py`.
- [ ] T041 [US3] (FR-014, FR-026, trap 2) Ship the built-in `sarif` adapter. It
      runs the `command:` the manifest declared through
      `factory/verify/gates.py:1394` — `resolve_gate_executor`, and it directs
      the command's SARIF output by **exporting the destination it chose as
      `ERGANE_QUALITY_SARIF` on the invocation's `env`**
      (`factory/verify/gates.py:269` — `GateInvocation`); the boundary runs the
      command with that environment and emits no `--clearenv`
      (`factory/verify/gates.py:614` — `run`), so the variable is readable
      inside. The destination is a path **unique to the worktree being scanned**
      under the directory
      `factory/verify/gates.py:1018` — `_resolve_target_git_dir` resolves — for
      a node that is the `worktrees/<name>` subdirectory its own `.git` file
      already points at, because the parent `.git` itself is shared by every node
      of the repository. The bind at
      `factory/verify/gates.py:704` — `_build_argv` is writable at the same
      absolute path inside the boundary and out, and `git add -A` never stages
      anything under a `.git` directory on either of that function's two
      returning branches. Then parse what comes back. **Not `TMPDIR`, not
      `/tmp`**: `factory/verify/gates.py:678` — `_build_argv` mounts a private
      tmpfs over `/tmp` and nothing sets `TMPDIR` inside the namespace, so a file
      written there is destroyed with the sandbox. It must not know which tool
      produced the file, and it must leave nothing inside the worktree.
- [ ] T042 [US3] (FR-015) Ship the built-in `none` scanner.
- [ ] T043 [US3] (FR-016) Make every failure path return a report, never raise —
      including the no-writable-destination path T038 drives. Precedents:
      `judge_unavailable`, `DeliveryReceipt`, and `CONFIG_ERROR` being one result
      rather than zero.
- [ ] T044 [US3] (trap 7) Confirm the new module does not import
      `factory/verify/judge.py`. `tests/test_verification_sweep.py:879` —
      `test_exactly_one_module_imports_the_judge` enforces the single-importer
      rule on the import graph, and catching it there costs an attempt.

### Verification for this story

- [ ] T045 [US3] (spec US3-S7, spec US3-S2, FR-026, FR-014) Paste, as committed
      evidence, three things taken from one run of the `sarif` adapter against
      the linked-worktree fixture: a `git status --porcelain` inside the worktree
      showing no output; an `ls -l` of the artifact on its chosen path showing it
      present; and the `env` mapping of the `GateInvocation` the adapter built,
      showing `ERGANE_QUALITY_SARIF` holding that same path. The first two prove
      the file went somewhere the factory can read and no diff can see; the third
      proves the command was told where to put it rather than the adapter
      reading a file that happened to be there. Paste beside them the two
      destinations from the two-worktree assertion in T034, showing they differ.

## Phase 4: User Story 4 — A report is scoped to the lines this attempt touched

One new module and its tests. No store, no workflow, no config: everything this
phase touches is a pure function over fixtures.

### Tests for this story (write FIRST, must fail)

- [ ] T046 [P] [US4] (spec US4-S1, FR-017) Assert findings outside the attempt's
      changed lines are dropped from the scoped set, and that a finding on a
      path the diff renamed survives under the new path only.
- [ ] T047 [P] [US4] (spec US4-S2, FR-017) Assert every finding in a file the
      attempt created is in scope.
- [ ] T048 [P] [US4] (spec US4-S3, FR-018, trap 11) Assert a finding whose path
      does not resolve inside the worktree, and separately a SARIF result with
      no `physicalLocation`, are each recorded and excluded — never mapped to
      line 1 and never to a nearest-matching file.
- [ ] T049 [P] [US4] (spec US4-S4, FR-018, trap 11) Assert an absolute
      `artifactLocation.uri`, a `file://` one and a worktree-relative one all
      normalise to the same worktree-relative path. Three spellings, three
      assertions: different tools choose differently and one passing does not
      prove the others.

### Implementation for this story

- [ ] T050 [US4] (FR-017, plan "do not write a second diff parser") Scope
      findings to changed lines in a new module under `factory/verify/`.
      **Reuse `factory/verify/diffbounds.py:93` — `split_sections`** and extend
      within that module's discipline for hunk-header line numbers. Do not write
      a second unified-diff parser; the attempt's diff is already in hand at
      `factory/verify/diffcheck.py:172` — `check_output`.
- [ ] T051 [US4] (FR-018, trap 11) Normalise SARIF URIs against the worktree
      root; refuse to scope anything that does not resolve inside it.

### Verification for this story

- [ ] T052 [US4] (spec US4-S1, FR-017) Paste, as committed evidence, the scoped
      and excluded counts the module produces for one committed fixture pair —
      a unified diff and a SARIF document — beside the fixture's own totals, so
      a reader can check the arithmetic rather than being told it holds.

## Phase 5: User Story 5 — The recorded scans are queryable, so thresholds can be measured

This phase runs **after** Phase 6: it reads the column US6 adds.

### Tests for this story (write FIRST, must fail)

- [ ] T053 [P] [US5] (spec US5-S1, FR-023) Against a store seeded with known
      rows, assert per-rule counts ordered by frequency over a selectable
      window.
- [ ] T054 [P] [US5] (spec US5-S2, FR-023) Assert per-story output gives findings
      per attempt, so "did attempt 2 improve" is answerable.
- [ ] T055 [P] [US5] (spec US5-S3, FR-024) Assert rows whose quality column is
      NULL report as **unmeasured**, not as zero findings. A zero here would
      silently halve any average the follow-on spec sets a threshold from.
- [ ] T056 [P] [US5] (spec US5-S4, FR-025) Assert a scanner-name change inside
      the window is named in the output.

### Implementation for this story

- [ ] T057 [US5] (FR-023) Add the read surface: a `Noun` under
      `factory/cli/nouns/` in the shape of `factory/cli/nouns/usage.py`, its verb
      module beside `factory/cli/usage.py:29` — `add_usage_parser` (a required
      dimension, a `--since` window, a `--json` alternative to the table) and
      `factory/cli/usage.py:65` — `usage_command` (open read-only, build one
      document, print it). It needs **one new read function** in
      `factory/verify/store.py`: every existing read over verification rows takes
      an `epic_id` — `factory/verify/store.py:899` — `epic_history` and
      `factory/verify/store.py:944` — `attempt_timings` — and FR-023's window
      spans epics. Open the store through
      `factory/verify/store.py:401` — `connect_readonly`; a report that opens it
      writable can migrate it out from under a running worker.
- [ ] T058 [US5] (FR-024) Report NULL-column rows as unmeasured.
- [ ] T059 [US5] (FR-025) Surface scanner-name changes within a window.

### Verification for this story

- [ ] T060 [US5] (spec US5-S3, FR-024) Paste, as committed evidence, the
      command's output against a seeded store holding both pre-077 NULL rows and
      recorded zero-finding rows, showing the two reported differently.

## Phase 6: User Story 6 — The scoped report is recorded, and changes nothing

This phase runs **before** Phase 5 and after Phase 4. It is the store column,
the migration, the call site and the activity plumbing — and nothing else.

### Tests for this story (write FIRST, must fail)

- [ ] T061 [P] [US6] (spec US6-S1, FR-019, **the central test**) Assert that two
      attempts with the same gate results, the same diff check and the same
      criteria — one whose scan reports four hundred findings, one whose scan is
      clean — driven through `factory/workgraph/workflow.py:2559` — `_verify`,
      record `VerificationResult` rows equal field for field except the quality
      column, and that the judge was invoked the same number of times in both.
      **Do not assert on `OverallVerdict` alone**:
      `factory/verify/models.py:114` — `OverallVerdict` has two members and
      FR-019 already forbids `compose_result` from seeing the report, so that
      comparison cannot fail whatever the implementation does. **Copy the
      harness, do not invent one**: `_verify` is an async workflow method whose
      every step is a `workflow.execute_activity` call, and this repository
      drives one exactly one way —
      `tests/test_092_manifest_threshold.py:157` — `env` starts a
      `WorkflowEnvironment.start_time_skipping()` and
      `tests/test_092_manifest_threshold.py:213` —
      `test_the_declared_threshold_reaches_the_output_check` runs a real epic
      through it and reads back what the workflow actually built.
      `tests/test_023_us2_dispatch_pin.py` is the second instance.
- [ ] T062 [US6] (spec US6-S1, FR-019, trap 6) **In the same test as T061**,
      assert by signature inspection that
      `factory/verify/models.py:998` — `compose_result` takes no quality
      parameter. It rides on T061's scenario rather than standing as one of its
      own, because it passes against today's untouched tree: a scenario a
      test-only diff satisfies is a scenario the judge can pass while nothing was
      built. State that in the test — it is a regression fence that survives a
      refactor, not this story's proof, and T061's whole-row comparison is.
- [ ] T063 [P] [US6] (spec US6-S2, FR-020) Assert the row carries the scoped
      findings, the scanner name and its version string.
- [ ] T064 [P] [US6] (spec US6-S3, FR-021, FR-027) Assert that an attempt whose
      gates failed writes NULL quality evidence **and** invoked no scan, and
      that NULL is distinguishable from a recorded empty report. Mirror the
      `judge_verdict` column at `factory/verify/store.py:218`.
- [ ] T065 [P] [US6] (spec US6-S4, FR-022, trap 4) Assert a redelivered activity
      replaying into the **same** workflow run leaves one row whose **quality
      column** holds the redelivery's evidence rather than a duplicate or a
      NULL, and that a **second dispatch** of the same attempt carries its own
      quality evidence on its own row. Read the column back on both rows: the
      five-column key at `factory/verify/store.py:248-260` already holds for
      every other column and asserting on that alone proves 117-US1's behaviour
      against an untouched store.
- [ ] T066 [P] [US6] (spec US6-S5, FR-027, trap 5) Assert the scan is invoked
      exactly once when the dispatched `verify_order` names `quality` on a green
      attempt, and not at all in two other cases: an order that omits `quality`,
      and an order that names it on an attempt whose gates failed.
      `verify_order` reaches only
      `factory/workgraph/workflow.py:2650` — `_verify` today, so a test that
      asserts on the config rather than on the dispatched order would pass
      against a step that executes nothing.
- [ ] T067 [P] [US6] (trap 3) Assert a store migrated from a pre-077 copy and a
      freshly created store list the `verification_results` columns in the
      **same order**, and that the new column is last in both. A divergent order
      raises nothing and hands every field of every row to the wrong attribute.

### Implementation for this story

- [ ] T068 [US6] (FR-020, FR-022, trap 3) Add the evidence column **last** in
      the DDL, **last** in the `_RESULT_COLUMNS` tuple
      (`factory/verify/store.py:711`, entries `factory/verify/store.py:712-734`),
      and put its `ALTER TABLE ... ADD COLUMN` in
      `factory/verify/store.py:556` — `_migrate` **after**
      `factory/verify/store.py:506` — `_add_dispatch_to_the_upsert_key`, which is
      called at `factory/verify/store.py:635` — `_migrate`. Copy the additive
      shape at `factory/verify/store.py:607` — `_migrate`. Bump
      `SCHEMA_VERSION` (`factory/verify/store.py:175`) from **13 to 14** and add
      a ledger entry in the shape of the ones above it.
- [ ] T069 [US6] (FR-021) Write NULL when the scan did not run.
- [ ] T070 [US6] (FR-027, FR-019, trap 5, trap 6) Wire the scan into
      `factory/workgraph/workflow.py:2559` — `_verify`, invoked after the diff
      check when `request.verify_order` names `quality` **and** the gates and the
      diff check both passed — the same first two conditions
      `factory/verify/models.py:977` — `judge_required` applies. The scan needs
      the attempt's diff for scoping, and today that read happens only inside the
      judge branch that opens at
      `factory/workgraph/workflow.py:2625` — `_verify`, as the
      `read_worktree_diff` activity call at
      `factory/workgraph/workflow.py:2626` — `_verify`: hoist that single call
      above both consumers and hand the same text to each rather than reading the
      worktree twice. The report reaches the
      **store and nothing else**; `compose_result` gains no parameter.
- [ ] T071 [US6] (FR-020, trap 12) Capture the scanner's version at scan time,
      never reconstruct it later.
- [ ] T072 [US6] (FR-019, trap 7) Add the activity plumbing inside
      `factory/activities/verify_activities.py`, which is already the one module
      permitted to import the judge, so the scan's activity adds no second
      importer to the graph.

### Verification for this story

- [ ] T073 [US6] (spec US6-S1, FR-019) Paste, as committed evidence, the two
      recorded rows from T061 side by side — the clean scan and the 400-finding
      scan — field for field, showing every column but the quality one identical,
      rather than asserting equality and describing the result.
- [ ] T074 [US6] (trap 3) Paste, as committed evidence, the
      `PRAGMA table_info(verification_results)` output for a freshly created
      store and for one migrated from a pre-077 copy, showing the same column
      order with the new column last in both.

## Verification

- [ ] T075 Full suite green: `uv run pytest -q`.
- [ ] T076 Confirm `git diff --stat -- pyproject.toml uv.lock` is empty across
      the whole spec. **No story here adds a dependency** — the Constitution III
      approval is the operator's to spend after US1 reports, with a
      `docs/decisions.md` entry.
- [ ] T077 Run a real epic end to end with `quality` absent from `verify:` in
      `ergane.yaml` — this repository's manifest, not the legacy `factory.yaml`
      beside it (trap 16), and note that it declares no `verify:` key at all,
      which is trap 18's case — and confirm both the recorded `loop_digest` and
      the dispatched `verify_order` match ones recorded before this spec landed.
      A green suite is evidence, not proof; this repository has shipped
      a fully green run of a command that could not start.
- [ ] T078 Run a real epic with a `quality:` block in `ergane.yaml` naming
      `scanner: sarif` and a `command:` that reports findings — the command
      writes its SARIF to `$ERGANE_QUALITY_SARIF`, which is the only way FR-014
      lets a command learn the destination — and confirm the recorded verdict is
      what the same gates, diff check and judge would have produced with no
      scanner, with the quality evidence populated beside it.
- [ ] T079 Run one with that same `ergane.yaml` block and a deliberately failing
      gate, and
      confirm the quality column is NULL and no scan was invoked — FR-027's
      guard, and the truth-table row that had no mechanism before this
      refinement.
- [ ] T080 In the epic from T078, before teardown, run `git status --porcelain`
      in the node worktree and confirm the scanner left nothing behind, then
      confirm the SARIF artifact is readable on its chosen path outside it, on a
      path naming that node rather than a filename every node of the repository
      would share (FR-026).
