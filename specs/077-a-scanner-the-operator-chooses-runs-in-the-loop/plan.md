# Implementation Plan: a scanner the operator chooses runs in the loop

**Spec**: `specs/077-a-scanner-the-operator-chooses-runs-in-the-loop/spec.md`

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

The 2026-08-20 pass of this plan had every anchor but two moved by hundreds of
lines, because eight specs landed on `factory/verify/` in between. The
2026-09-04 refinement repaired those and was then refuted on six blocking
defects, all of them claims about *mechanism* rather than moved lines: what the
gate boundary actually restricts, where the SARIF file can survive, which
component owns the scanner closed set, how many links the dispatch chain has,
and what US6's central test actually proves. A second adversarial re-read the
same day refuted the repair on three more, again all mechanism: this repository's
manifest is `ergane.yaml` and the trio had named the deprecated `factory.yaml`
five times; `_resolve_target_git_dir` does not deliver the "outside the
worktree" absolute FR-026 was written around; and the `quality:` block had no
key for the command FR-014 requires the adapter to run. A third refuted it on
three more, and those were settled by *running* the tree rather than reading it:
`uvx` is not inside the gate boundary at all, `_VERIFY_STEPS` is also the
absent-key default, and the `command:` key had no stated way to learn the path
the adapter picks. Those repairs are marked **[was wrong]** where they occur.

A note on the citation style, so the next reader does not "fix" it into
refusals: the symbol tier resolves names through `ast` and walks only
`FunctionDef`, `AsyncFunctionDef` and `ClassDef` nodes
(`factory/cli/nouns/spec.py:825` — `_symbol_spans`), so a module-level constant
cannot be written as `` `path.py:NN` — `CONST` `` — that form is refused as "not
defined in that file". Constants below are therefore plain anchors, and every
citation that names a function, a class, or a line *inside* one is written in
the machine-checked form.

## What already exists, and where

### US2 — the parser, the closed set, and the chain the answer rides on

The step tuple and the reserved gate names sit five lines apart:

```python
#: Reserved gate names in schema v2. They collide with step names or the
#: synthetic `config` gate emitted by `config_error_result`.
_RESERVED_GATE_NAMES = frozenset({"gates", "diff_check", "judge", "config"})

#: The verification steps a v2 `verify:` list may name, and today's default.
_VERIFY_STEPS = ("gates", "diff_check", "judge")
```

- `factory/verify/factory_yaml.py:171` is the `_VERIFY_STEPS` tuple. **It has
  two jobs and only one of them may grow.** [was wrong] Its own comment one line
  above, `factory/verify/factory_yaml.py:170`, says both: "The verification steps
  a v2 `verify:` list may name, **and today's default**", and
  `factory/verify/factory_yaml.py:924` — `_read_verify` returns it verbatim when
  a manifest declares no `verify:` key. `ergane.yaml` declares none — its
  top-level keys are `version`, `runtime`, `gates`, `standards`,
  `landing_branch`, `ladder` and `roadmap`, and nothing else — so this
  repository resolves through that return. Growing the one tuple therefore hands
  every v2 repository that omits `verify:` the order
  `('gates', 'diff_check', 'judge', 'quality')`, breaks FR-008 and FR-005's
  second half, fails US2-S5, and moves `loop_digest` through
  `request.verify_order` at
  `factory/workgraph/workflow.py:2650` — `_verify` — a door trap 15 does not
  guard, because trap 15 governs only the digest *dict*. Split the roles:
  `quality` joins the admissible set, and the absent-key return gets its own
  default tuple mirroring the literal already at
  `factory/verify/models.py:340` — `FactoryConfig`, which is
  `("gates", "diff_check", "judge")`. Trap 17 states the wrong move.
- `factory/verify/factory_yaml.py:168` is the `_RESERVED_GATE_NAMES` frozenset.
  `quality` must join this too, or a repo could declare a *gate* named `quality`
  and collide with the step name (trap 9).
- **The scanner closed set belongs here too, on the same two lines' worth of
  file.** [was wrong] The refuted pass told US2 to enforce a closed set and told
  US3 to *create* it in `factory/controlplane/config.py`. Nothing under
  `factory/verify/` imports `factory.controlplane` and nothing in
  `factory/controlplane/config.py` reads a manifest at all (both verified by grep
  at 602a92c), so the messenger precedent works only because the control-plane
  config *is* the parser for escalation adapters; for scanners the parser is this
  file. [was wrong] The refuted repair cited
  `factory/verify/models.py:334-337` — `FactoryConfig` for this, which is the
  `ladder:` field; the comment about a declined import is the `forge:` field's at
  `factory/verify/models.py:329-332` — `FactoryConfig`, and the import it declined
  is `factory.verify.factory_yaml`'s own `DEFAULT_FORGE_NAME` "because importing
  it here would close a cycle through `factory.verify.gates`" — a sibling in this
  same component, not `factory.controlplane`. It is evidence that this component
  guards its import graph, not evidence about the control plane; the grep above
  is what carries the decision. One home, in US2, beside `_VERIFY_STEPS`
  (FR-007). US3 adds the conformance test and no second constant (trap 14).
- `factory/verify/factory_yaml.py:915` — `_read_verify` is the whole ordering
  parser. Its docstring still says "drawn from exactly the three step names" and
  it must be updated with the tuple. Its ordering rule for `judge`
  (`factory/verify/factory_yaml.py:964` — `_read_verify`) is the pattern to
  copy, not to rewrite; the unknown-step refusal it must stay distinguishable
  from is at `factory/verify/factory_yaml.py:943` — `_read_verify`.
  **Every refusal it raises carries the same rule slug,
  `"verify"`** — the first positional argument to `FactoryConfigError` — so a
  test that asserts on the slug cannot tell an ordering refusal from an
  unknown-step one. Assert on the message (US2-S2, US2-S3).
- **Where a new top-level key registers, and the trap in choosing wrong.**
  `factory/verify/factory_yaml.py:109-121` is the `_TOP_LEVEL_KEYS` tuple —
  keys legal in **v1 and v2**, `writes` and `caches` among them — and
  `factory/verify/factory_yaml.py:134` is `_V2_TOP_LEVEL_KEYS`, which is that
  tuple plus `("ladder", "verify")`. FR-011 needs `quality` in the **second**
  one only. `factory/verify/factory_yaml.py:269` — `_reject_unknown_keys` is
  what enforces the split.
- `factory/verify/factory_yaml.py:694` — `_read_caches` is the closest reader to
  copy in shape: a nested block with per-entry key validation and a named
  refusal. Copy its shape, not its registration — `caches` is v1-legal and
  `quality` is not.
- **The block has two keys, and the second one is what the adapter runs.**
  [was wrong] The refuted repair specified `quality: {scanner: ...}` and nothing
  else, while FR-014 required the adapter to run "a declared command" that no
  story parsed. `command:` is that declarer, and it lands here, in US2, with
  `scanner:` — otherwise a US3 implementer meets FR-014 with two moves and both
  are wrong: hardcode a tool's command line inside the adapter, killing the
  swappability the operator's third decision asked for, or add a parser key to a
  file US2 has already landed (trap 14).
- **The closed set holds ADAPTER names, not tool names.** [was wrong] The refuted
  repair told US1 to recommend a scanner and called that recommendation "what
  US2's closed set admits", which cannot be: FR-013 pins the set equal to the
  registry's keys in both directions, and FR-014/FR-015 fix those keys at `sarif`
  and `none`. `ruff` could never be a member without an adapter no requirement
  provides. The precedent says the same thing —
  `factory/controlplane/config.py:51` is `KNOWN_ESC_ADAPTERS`, holding
  `("telegram", "webhook", "none")`, transport names rather than the names of the
  things they carry. So US2 lands `("sarif", "none")`, which is specified by
  FR-014 and FR-015 rather than guessed, and US1's recommendation becomes the
  `command:` string an operator writes. That also disposes of a phantom
  dependency: US2 runs `concurrent_with: [US1]` and could not read US1's note
  even if it needed to.
- `factory/verify/models.py:291` — `FactoryConfig` is the dataclass. [was wrong]
  Its field block does **not** end at 340: `factory/verify/models.py:340` —
  `FactoryConfig` is `verify_order`, `factory/verify/models.py:349` —
  `FactoryConfig` is `diff_refusal_bytes` (092) and
  `factory/verify/models.py:358` — `FactoryConfig` is `caches` (101), which is
  the last field and the class's last line. **A `quality:` block is a new field
  after that one.** `factory/verify/models.py:336` — `FactoryConfig` is the
  `ladder:` field, the exact shape to copy: a nested dataclass with a default
  factory, not a bag of loose keys.
- `factory/verify/models.py:1132` — `loop_digest` and
  `factory/verify/models.py:1158` — `loop_summary` are what FR-009 feeds. Both
  take a `VerificationConfig` — **not** a `FactoryConfig` — plus `verify_order`
  and `gate_names`, and both are called from
  `factory/workgraph/workflow.py:2650` — `_verify` with `request.config`. So the
  scanner reaches them from `EpicInput`, not off the config in hand. Read trap 15
  before adding a key to the digest dict.

**The dispatch chain (FR-010) has five links, and the refuted pass named three
of them.** [was wrong] The pin is a field on the epic dispatch payload:

```python
    #: 023 FR-003. The verification-step order the child epic must execute. It
    #: is part of dispatch so the operator clone's manifest pins it; a node
    #: worktree cannot move it. Defaults to today's order so every pre-023
    #: payload and every v1 repo replays identically.
    verify_order: tuple[str, ...] = ("gates", "diff_check", "judge")
```

- `factory/workgraph/workflow.py:562` — `EpicInput` is that field.
- `factory/verify/factory_yaml.py:1068` — `load_loop_config` is the read, and it
  returns a **fixed three-tuple**, `(config.ladder, config.verify_order,
  config.diff_refusal_bytes)` at `factory/verify/factory_yaml.py:1086` —
  `load_loop_config`. A `quality:` block on `FactoryConfig` reaches no caller
  until that tuple grows. This is link one and the refuted pass had no anchor
  for it.
- `factory/activities/roadmap_activities.py:821` — `ReadLoopConfigResult` is the
  carrier the roadmap's activity builds; its fields are at
  `factory/activities/roadmap_activities.py:832` — `ReadLoopConfigResult`, and
  the docstring there says why a new field is defaulted: "a scripted result
  written before this story still constructs". The activity that fills it is
  `factory/activities/roadmap_activities.py:858` — `read_loop_config`. This is
  link two, and it is the one that makes the roadmap path work — the roadmap is
  how this factory actually dispatches.
- `factory/roadmap/workflow.py:1300` — `_dispatch` reads
  `loop_config.verify_order` off that
  carrier. It does not read the clone.
- `factory/cli/nouns/build.py:826` — `start_command` is the operator-clone read
  for the CLI path and `factory/cli/nouns/build.py:844` — `start_command` is the
  *call* that passes it on — a keyword on a `_start_epic(...)` call, not a
  construction; `factory/cli/nouns/build.py:931` — `_start_epic` is where the
  `EpicInput` is actually built, and `factory/cli/nouns/build.py:935` —
  `_start_epic` is `verify_order`'s keyword inside it.
- **There are exactly three `EpicInput` constructions in the tree and only two of
  them read a manifest.** `grep -rn "EpicInput(" factory/` at 602a92c returns
  `factory/roadmap/workflow.py:1296` — `_dispatch`,
  `factory/cli/nouns/build.py:931` — `_start_epic`, and
  `factory/workgraph/cli.py:675` — `_start_epic`. The third is a legacy handler
  that reads no
  manifest: it passes neither `config`, `verify_order` nor `diff_refusal_bytes`,
  and it stays on `EpicInput`'s defaults here for exactly the same reason it
  already does for those two (FR-010). An implementer who counts to three and
  goes to wire it has widened the diff into a file the Sizing table does not
  list.
- `factory/cli/nouns/build.py:913` — `_start_epic` is the trap inside that
  function: a caller that names no `verify_order` gets the literal
  `("gates", "diff_check", "judge")`. The 092 comment three lines below
  (`factory/cli/nouns/build.py:917` — `_start_epic`) records what that shape has
  already cost: "`None` here is 'this caller read no manifest', never 'no
  ceiling'". A `quality:` default of `None` in this function must mean the same
  thing and must not be reachable by omission.

### US3 — the registry. Two working precedents; copy, do not invent

- `factory/notify/adapter.py:70` is the `_BUILTIN_ADAPTER_MODULES` dict, with the
  comment above it stating the property that matters: "Imported lazily at resolve
  time so this module stays free of the transports' own dependencies."
- `factory/controlplane/config.py:51` is the `KNOWN_ESC_ADAPTERS` tuple — cited
  here **only** as the precedent for holding a registry and a closed set equal in
  both directions. It is not where this spec's closed set goes; see the US2
  section above and trap 14.
- `factory/mergequeue/forge.py:324` is the `_REGISTRY` dict.
- `factory/mergequeue/forge.py:342` — `resolve_forge` is the resolver, including
  the lazy-import-then-retry shape and the error listing the registered names:

```python
    chosen = name or DEFAULT_FORGE
    build = _REGISTRY.get(chosen)
    if build is None:
        _load_builtins()
        build = _REGISTRY.get(chosen)
    if build is None:
        raise UnknownForgeError(
            f"no forge is registered under {chosen!r}; "
            f"registered forges are {', '.join(sorted(_REGISTRY)) or '(none)'}"
        )
    return build(**seams)
```

- `factory/verify/gates.py:288` — `GateExecutor` is the narrow seam inside this
  very component: one Protocol, one method. A `Scanner` Protocol belongs beside
  it in spirit, in its own module in fact.
- `factory/verify/gates.py:1394` — `resolve_gate_executor` is the public helper
  that hands back the backend the manifest selects. The adapter runs its command
  through this, the way gates do at
  `factory/verify/gates.py:1467` — `_run_gate_list_from_config`, rather than
  through a bare `subprocess.run`.
- **The seam that carries the destination to the command is `GateInvocation.env`,
  and it was missing.** [was wrong] Seven places in the refuted trio said the
  adapter "directs" its command's output somewhere, and nothing said how an
  absolute path the factory computes reaches a command string the operator
  wrote. `factory/verify/gates.py:269` — `GateInvocation` is that `env` field;
  `factory/verify/gates.py:614` — `run` hands it to `subprocess.Popen` as the
  bwrap process's own environment, and `_build_argv` emits no `--clearenv`
  (verified by assembling the argv at 602a92c), so anything on it is visible to
  the command inside the namespace. FR-014 fixes the name:
  `ERGANE_QUALITY_SARIF`. The gate path builds that env from
  `factory/verify/gates.py:119-130`, the `SCRUBBED_ENV_ALLOWLIST`, which is why
  the adapter must *set* the variable rather than expect to inherit one.
- `factory/verify/gates.py:1018` — `_resolve_target_git_dir` is what decides
  whether the boundary carries a writable metadata directory at all. [was wrong]
  It has **two** returning branches and the refuted repair described only one.
  Its own docstring says so: "A normal git repository has `.git` as a directory.
  A linked worktree has `.git` as a file pointing at the real metadata under the
  parent repo's `.git/worktrees/<name>`." For the directory case it returns
  `git_file.resolve()` — `<worktree>/.git`, **inside** the worktree. For the
  linked case it returns `gitdir.parent.parent` — the parent repository's `.git`,
  outside. It returns `None` only when `.git` is absent or malformed, and that
  `None` is US3-S6's `scanner_unavailable` case. **And the linked branch returns
  one directory for the whole repository**: every node worktree of a parent
  resolves to that same parent `.git`, so a fixed filename under it is two
  concurrent nodes overwriting each other, and this floor has run the node cap
  at two. FR-026 requires a path unique to the worktree; the `worktrees/<name>`
  directory the worktree's own `.git` file already points at is that path, it is
  inside the bound tree, and it costs no new derivation. Read trap 2 before
  writing a fixture for either.
- **The name `scanner` is already spoken for once in this tree.**
  `factory/discovery/llm_scanner.py` is the endpoint-discovery scanner and has
  nothing to do with this one. `factory/verify/scanner.py` is a different module
  in a different component; do not import, extend, or register into the
  discovery one.

### US4 — scoping, and nothing else

- `factory/verify/diffbounds.py:93` — `split_sections` splits a unified diff into
  its leading text and one section per file. **The diff is already split per
  file. Reuse this.** Do not write a second unified-diff parser.
- `factory/verify/diffcheck.py:172` — `check_output` already holds the attempt's
  diff. The scoping step needs changed line numbers, which means parsing hunk
  headers — the one thing `split_sections` does not already give you.
- US4 lands one new module under `factory/verify/` and its tests. It touches no
  store, no workflow and no config. That is the split line: after it, US4 shares
  no production file with any other story in this spec.

### US5 — the read surface, and the store call it will need

- `factory/cli/nouns/usage.py` is the noun registration to copy: a `Noun` with a
  name, a one-line summary, an `order`, and an `add_parser` handed straight to
  the implementation module. The verb itself is
  `factory/cli/usage.py:29` — `add_usage_parser`, which is the closest existing
  shape to FR-023's ask — a required rollup dimension (`--by`), a window
  (`--since`), a `--json` alternative to the table — and
  `factory/cli/usage.py:65` — `usage_command`, which opens the store read-only,
  builds one document, and prints it. Copy that division: parser, read-only
  connection, one document, one renderer.
- **The store has no cross-epic read, and the Sizing table says so.** Its whole
  reporting surface over verification rows is
  `factory/verify/store.py:899` — `epic_history` and
  `factory/verify/store.py:944` — `attempt_timings`, and both take an `epic_id`.
  FR-023 asks for counts per rule *across* epics over a selectable window, so
  US5 adds one read function beside those. That is a read helper, not new store
  state, and US5's `depends_on: [US6]` already serialises it behind the story
  that adds the column — but it is a second production file and the row now
  names it.
- `factory/verify/store.py:401` — `connect_readonly` is the connection a report
  opens. A read surface that opens the store writable is a read surface that can
  migrate it out from under a running worker.

### US6 — composing, recording, and the call site that makes the step real

- `factory/verify/models.py:998` — `compose_result` is the verdict composer, and
  every input is an explicit keyword argument: `gate_results`, `output_check`,
  `judge`, `criteria_sha256`, `loop_digest`, `base_ref`, `dispatch`, `persona`,
  `model_alias`, `route`. **FR-019 is satisfied by not adding a parameter here.**
- `factory/verify/models.py:114` — `OverallVerdict` has exactly two members,
  `PASS` and `FAIL`. [was wrong] The refuted pass made US6's central test
  "the two attempts compose the same `OverallVerdict`" — a comparison of two
  values drawn from a two-member enum, guaranteed by the structural half of the
  same requirement, which no implementation can fail. US6-S1 now compares the
  whole recorded row and the judge invocation count, driven through `_verify`.
  **Do not invent the harness for that.** `_verify` is an async workflow method
  whose every step is a `workflow.execute_activity` call, and this repository
  drives one exactly one way. `tests/test_092_manifest_threshold.py:157` — `env`
  is the fixture that starts a `WorkflowEnvironment.start_time_skipping()`, and
  `tests/test_092_manifest_threshold.py:213` —
  `test_the_declared_threshold_reaches_the_output_check` runs a real epic through
  it and reads back the `CheckOutputInput` the workflow actually built — the same
  move US6-S1 needs for the recorded row and the judge-call count. Its docstring
  even names the reason: "the half a pure test cannot reach".
  `tests/test_023_us2_dispatch_pin.py` is the second instance. Calling `_verify`
  directly with mocked activities is not how this repository does it.
- `factory/workgraph/workflow.py:2559` — `_verify` is where the loop actually
  runs. `verify_order` does *not* sequence anything:
  `factory/workgraph/workflow.py:2650` — `_verify` and the line below it are the
  only readers, into `loop_digest` and `loop_summary`. The gates → diff check →
  judge sequence is hardcoded here.
- `factory/workgraph/workflow.py:2607` — `_verify` runs `check_output`
  unconditionally, and there is no early return between it and `compose_result`
  at `factory/workgraph/workflow.py:2653` — `_verify`. [was wrong] So a scan
  conditioned only on "the order names `quality`" would run on every attempt
  including ones whose gates already failed, and the spec's own fifth truth-table
  row would be unreachable. FR-027 now carries the guard, mirroring
  `factory/verify/models.py:977` — `judge_required`, whose body is
  `gates_passed(...) and output_check.passed and has_scenarios(...)`. The scan's
  guard is the first two of those three: a scanner does not need scenarios.
- `factory/workgraph/workflow.py:2625` — `_verify` is the `judge_required`
  branch and `factory/workgraph/workflow.py:2626` — `_verify` is the
  `read_worktree_diff` activity call *inside* it, which is the only place
  `diff_text` comes from today. Read trap 5 before deciding where the scan's
  diff text comes from.
- `factory/verify/store.py:218` is the `judge_verdict` column in the DDL:
  `judge_verdict TEXT, -- JSON: JudgeVerdict | NULL (gates failed / no scenarios)`.
  **The exact precedent for FR-021**: a nullable evidence column whose NULL means
  "never ran", distinct from an empty result.
- `factory/verify/store.py:175` is `SCHEMA_VERSION`, and **it is 13, not 6.**
  US6 makes it **14**. The ledger of what each bump meant runs from
  `factory/verify/store.py:123` down to that line; add an entry in the same
  shape.
- `factory/verify/store.py:607` — `_migrate` is the additive
  `ALTER TABLE verification_results ADD COLUMN loop_digest TEXT` migration; its
  whole branch is `factory/verify/store.py:607-614`, and the function it sits in
  begins at `factory/verify/store.py:556` — `_migrate`. Copy this shape; pre-077
  rows read NULL and are never backfilled. But read trap 3 before choosing where
  in `_migrate` to put it.
- `factory/verify/store.py:506` — `_add_dispatch_to_the_upsert_key` is the table
  rebuild every later `ADD COLUMN` must run *after*; it is called from
  `factory/verify/store.py:635` — `_migrate`.
- `factory/verify/store.py:711` is the `_RESULT_COLUMNS` tuple, described one
  line above at `factory/verify/store.py:709` as "Everything `upsert_result`
  writes, in DDL order". [was wrong] The refuted pass cited `:714-734`, which
  starts at `"attempt"` and so is two columns short of the list it claimed to be.
  The entries run `factory/verify/store.py:712-734`, and `"route"` at
  `factory/verify/store.py:734` is the last one before the closing paren. The new
  evidence column joins the end of this tuple and the end of the DDL, in that
  same order. See trap 3.
- `factory/verify/store.py:248-260` is the DDL tail: `persona`, `model_alias`,
  `route`, then `UNIQUE (epic_id, node_id, attempt, form, dispatch)`. That
  five-column UNIQUE is the upsert key FR-022 names; it gained `dispatch` in
  117-US1 and the 2026-08-20 plan predates it.
- `factory/activities/verify_activities.py` is the only module allowed to import
  the judge (trap 7); the scan's activity plumbing lives beside that import
  without adding a second one.

### US1 — the boundary the spike must run inside

[was wrong] The refuted pass described this boundary as "`--clearenv`, no
network". Neither half is in the file. What is:

- **Network egress is deliberately left open.**
  `factory/verify/gates.py:549` — `BwrapGateExecutor` says so in the class
  docstring: "Network is intentionally not unshared — egress is out of scope".
  `factory/verify/gates.py:888` — `_resolver_binds` binds `/etc/resolv.conf` and
  `/etc/ssl` *so that* a gate's network works, naming "the middle of a package
  install" as the failure it exists to prevent. The only namespace unshared is
  the PID one, at `factory/verify/gates.py:747` — `_build_argv`. **So "needs the
  network" disqualifies no candidate**, and the note must not say it does — the
  spike's own `uv tool run` invocations depend on that egress.
- **The environment is an allowlist, not a wipe.**
  `factory/verify/gates.py:119-130` is the `SCRUBBED_ENV_ALLOWLIST` tuple:
  `PATH`, `HOME`, `TMPDIR`, `LANG`, `LC_ALL`, `LC_CTYPE`, `TZ`, `TERM`, `USER`,
  `LOGNAME`, `SHELL`. `factory/verify/gates.py:351` — `scrubbed_env` builds that
  dict and `factory/verify/gates.py:1467` — `_run_gate_list_from_config` puts it
  on the invocation, which the bwrap backend then uses as the *parent* process
  environment. Inside the namespace, `--setenv` adds `HOME`
  (`factory/verify/gates.py:729` — `_build_argv`), each declared cache's own
  variable, `PATH`, and a git identity — through
  `factory/verify/gates.py:744` — `_build_argv`.
- **`TMPDIR` is on that allowlist and is still useless as a destination.**
  `factory/verify/gates.py:678` — `_build_argv` mounts `--tmpfs /tmp`, and
  `factory/verify/gates.py:660` — `_build_argv` puts the gate's `HOME` inside it
  at `/tmp/ergane-gate-home`. Nothing sets `TMPDIR` inside the namespace, so it
  either names a path under that private tmpfs — discarded when the sandbox exits
  — or a host path no bind carries, where the write simply fails. This is the
  defect that would have cost a US3 attempt; trap 2 is its repair.
- **Two binds outside the worktree are writable.** The declared caches
  (`factory/verify/gates.py:718` — `_build_argv`, whose comment claims they are
  the only ones) and whatever
  `factory/verify/gates.py:1018` — `_resolve_target_git_dir` returns
  (`factory/verify/gates.py:704` — `_build_argv`, a `--bind`, deliberately
  writable "so commit/diff work"). The comment at 718 predates or overlooks the
  second; the argv is the authority, and the second is the one an adapter can use
  without asking a target repo to declare anything. For a node — a linked
  worktree — that is the parent repository's `.git`, which is genuinely outside.
  [was wrong] The refuted repair said the other branch is what "US3's fixtures
  will" meet; no fixture in this spec meets it. T034 forbids the `git init`
  shape outright and T038 uses a directory with no `.git` at all. The
  ordinary-repository branch is stated in trap 2 for the reader, and it is
  exercised by nothing here on purpose: no node ever has that shape, and FR-026's
  invariant — git metadata, unstageable by `git add -A` — holds on both branches
  by inspection rather than by a third fixture.
- **The boundary carries four executables as LEAF binds, and `uvx` is not one
  of them.** [was wrong] `factory/verify/gates.py:753` — `_toolchain` resolves
  exactly `(UV, NODE, GIT, DEFAULT_AGENT_RUNNER)`;
  `factory/verify/gates.py:776` — `_toolchain_binds` turns each into a
  `--ro-bind` of `factory/verify/toolchain.py:185` — `bind`, which is
  `(real_path, found_at)` — one file, never its directory — and
  `container_path` derives the container `PATH` from those same resolutions.
  `/home/admin/.local/bin/uvx` is a separate 320 KB binary beside `uv`, not a
  symlink to it, so it does not exist inside the namespace. Measured at 602a92c
  by assembling the real argv: the only `~/.local/bin` entries inside are the
  `uv` leaf bind and a `--symlink` for the agent runner. `uv tool run <tool>`
  runs the same ephemeral install and **does** work, because `uv` is bound — and
  its cache comes with it: `factory/verify/gates.py:943` — `_cache_binds` binds
  `~/.cache/uv` writable unconditionally and
  `factory/verify/gates.py:945` — `_cache_binds` pairs it with `UV_CACHE_DIR`,
  which `_build_argv` emits as a `--setenv`. So an ephemeral tool environment
  persists between runs rather than being re-downloaded into the tmpfs `HOME`.
  Trap 17 states the wrong move.
- `factory/verify/gates.py:113` is `OUTPUT_TAIL_LIMIT = 32 * 1024`, the bound a
  scanner's stderr is subject to when it comes back as gate output — which is why
  stdout is not a viable SARIF channel either, quite apart from
  `factory/verify/gates.py:617` — `run` merging stderr into it with
  `stderr=subprocess.STDOUT`.
- **The boundary is manifest-selected, and it silently falls back.**
  `factory/verify/gates.py:1346` — `_resolve_gate_executor` chooses
  `BwrapGateExecutor` only when the manifest declares `runtime: bwrap` **and**
  `/usr/bin/bwrap` is a file; otherwise it returns `SubprocessGateExecutor`,
  which runs on the host with none of the isolation. This repository's own
  manifest — `ergane.yaml:26`, not the `factory.yaml` beside it; see trap 16 —
  declares `runtime: bwrap`.
  `factory/verify/gates.py:1394` — `resolve_gate_executor` is the public helper
  a spike should call, and it composes `worktree / MANIFEST_NAME` at
  `factory/verify/gates.py:1409` — `resolve_gate_executor` directly rather than
  going through
  `resolve_manifest_path`, so `factory.yaml` is not merely deprecated for this
  read — it is unreachable. A spike that does not record which class it got has not
  measured the boundary, and that is what FR-002 exists to stop.
- **101 landed `caches:`, so "the scanner wants a cache directory" is an
  expressible declaration rather than an automatic disqualification.**
  `factory/verify/factory_yaml.py:694` — `_read_caches` parses it; each entry is
  a `path` plus an `env` name that becomes a `--setenv` pair on the boundary's
  own command line.
- `factory/verify/diffbounds.py:47` is `DIFF_INPUT_LIMIT = 64 * 1024`, and
  `factory/verify/diffbounds.py:66` is `DIFF_REFUSAL_THRESHOLD`, which 092 split
  out of it: the first is what the judge is shown, the second is the size above
  which a story is refused unjudged. The comment above the first records the
  false positive that refused a fully-green story four times at 61,725 bytes.
  **This is why US5 exists and why gating is a separate spec** — and, in this
  refinement, why FR-004's artifacts are bounded by bytes.

## Traps

These are named hazards, met as declared scope rather than as failures.

**Trap 1 — the boundary is not the one folklore describes, and it can fail to be
the boundary at all.** Gates run through whatever
`factory/verify/gates.py:1346` — `_resolve_gate_executor` returns. On a host
with `/usr/bin/bwrap` present and `runtime: bwrap` declared, that is the sandbox
— a PID namespace, eleven inherited environment names plus `--setenv`
HOME/caches/PATH/identity, a read-only system tree, **and open network egress**.
On any host missing that binary it is `SubprocessGateExecutor`, on the host, with
the operator's whole environment. Two wrong moves, and the refuted pass made
both. The first is to run each candidate with `subprocess.run` — or with
`resolve_gate_executor` on a host where bwrap is absent — and write down "it
works"; FR-002 makes the backend class a recorded fact for exactly this reason.
The second is to disqualify a candidate for "needing the network": egress is open
by design (`factory/verify/gates.py:549` — `BwrapGateExecutor`), the resolver and
trust roots are bound to make it work
(`factory/verify/gates.py:888` — `_resolver_binds`), and the spike's own
`uv tool run` invocations would be impossible otherwise. What disqualifies a candidate is the
filesystem and the clock: a writable path no bind carries and no `caches:` entry
could declare, or a wall-clock that changes the loop's economics.

**Trap 2 — the SARIF file has exactly one place it can survive, and `TMPDIR` is
not it.** [was wrong] Two independent mechanisms close every other door.
Inside the boundary, `factory/verify/gates.py:678` — `_build_argv` mounts
`--tmpfs /tmp` and no `--setenv TMPDIR` is ever emitted
(`factory/verify/gates.py:729` — `_build_argv` through
`factory/verify/gates.py:744` — `_build_argv`), so a `results.sarif` under
`TMPDIR` or `/tmp` is destroyed with the namespace and the factory reads
nothing; a path elsewhere on the host is not bound in at all and the write
fails. Outside the boundary, `factory/workgraph/worktree.py:1496` — `diff`
builds the judge's patch by running `git add -A` into a scratch index against
the base ref, so untracked, unignored files are in the patch, and
`factory/workgraph/worktree.py:511` — `salvage` stages the same way before
committing; a real SARIF document over a repository this size is hundreds of
KiB, and `factory/verify/diffbounds.py:66` refuses a story unjudged above 64 KiB
by default. So the two tempting implementations of FR-014 — "write it in the
worktree and read it back", "write it under `TMPDIR`" — are respectively a story
refused unjudged and a file that does not exist. What is left, and what FR-026
names, is whatever `factory/verify/gates.py:1018` — `_resolve_target_git_dir`
resolves: `factory/verify/gates.py:704` — `_build_argv` binds that directory
`--bind`, writable, at the same absolute path inside and out.

**And the invariant is "git metadata", not "outside the worktree".** [was wrong]
The refuted repair wrote FR-026 as an absolute — a path outside the node
worktree — which that function guarantees only for a **linked** worktree, where
`.git` is a file and it returns `gitdir.parent.parent`, the parent repository's
`.git`. For an ordinary repository `.git` is a directory and it returns
`git_file.resolve()`, which is `<worktree>/.git` — inside. Both are equally
invisible to `git add -A`, so the property the adapter actually needs holds in
both branches; the "outside" half holds only in production's shape. That
distinction decides two fixtures, and getting either wrong costs the attempt.
US3-S7's fixture must be a **linked** worktree, built with `git worktree add`
against a parent repo, because that is what a node is and it is the only shape
in which the outside-the-worktree assertion is true. US3-S6's fixture must be a
directory with **no `.git` at all**, because that is the only shape for which the
function returns `None` — the obvious `tmp_path` plus `git init` returns a path,
not `None`, and a test written against it fails a correct implementation. That
`None` is not a crash; it is FR-016's `scanner_unavailable` with the reason named.
US1-S6 pastes the measurement that confirms all of this.

**Trap 3 — the store's column list is positional and its order is load-bearing.**
`factory/verify/store.py:711` is `_RESULT_COLUMNS`, and
`factory/verify/store.py:255-256` states the rule inside the
`verification_results` DDL itself, about the last three columns added to it:
"After `dispatch` because ALTER TABLE ADD COLUMN appends and a migrated store
must have the same column order as a fresh one".
`factory/verify/store.py:643` — `_migrate` repeats it with the consequence
spelled out — a divergent order "does not raise", it "hands every field of every
row to the wrong attribute". So the new quality column goes last in the DDL, last
in `_RESULT_COLUMNS`, and its `ALTER TABLE` runs *after*
`factory/verify/store.py:506` — `_add_dispatch_to_the_upsert_key`, which rebuilds
the table. The wrong move is to insert it beside `judge_verdict` "where it
belongs conceptually". It belongs at the end.

**Trap 4 — the five-column upsert key already works, so only the quality column
makes US6-S4 a new fact.** `factory/verify/store.py:248-260` ends the table with
`UNIQUE (epic_id, node_id, attempt, form, dispatch)`, added by 117-US1, and
`factory/verify/store.py:737-739` explains the semantics: a re-recorded attempt
*of the same dispatch* overwrites, while a second dispatch of the same attempt is
a different row entirely. A test that asserts "the redelivery landed on the first
row" proves 117's behaviour and passes against an untouched store. The assertion
that can fail is the one that reads the **quality column** back off both rows and
holds that the redelivery replaced the first write's evidence rather than
duplicating or losing it. Asserting on four columns proves even less: that is the
pre-117 key.

**Trap 5 — `verify_order` does not run the loop, so US2 alone executes nothing —
and the call US6 adds needs a diff nobody has read yet.**
`factory/workgraph/workflow.py:2650` — `_verify` and the line below it are the
only places the dispatched order is read, into `loop_digest` and `loop_summary`.
The sequence itself is hardcoded in `factory/workgraph/workflow.py:2559` —
`_verify`. The wrong move for a US2 implementer is to go hunting for a step
dispatcher (there is none) or to build one (that is FR-027, and it is US6's).
The wrong move for a US6 implementer is the mirror: to add the scan call and
forget that whether it runs is decided by `request.verify_order` and by the
guard, not by whether the config has a scanner. There is a third wrong move
specific to the diff: `diff_text` today is read only inside the `judge_required`
branch — the branch opens at `factory/workgraph/workflow.py:2625` — `_verify`
and the `read_worktree_diff` call is at
`factory/workgraph/workflow.py:2626` — `_verify` — so a scan that needs
changed lines either reads the worktree a second time — two `read_worktree_diff`
activity calls per attempt, one of them invisible in the cost ledger — or the
single read is hoisted above both consumers and the same text handed to each.
Hoist it, and hoist it only when a consumer will use it.

**Trap 6 — record-only must be structural, not configured.** The temptation is
to pass the quality report into `compose_result` and have it ignore the value
unless a `mode` flag says otherwise. **Do not.** That leaves the gating switch
one line away from being flipped by a future agent that reads `mode` as dead
code and "cleans it up". `factory/verify/models.py:998` — `compose_result` is
the enforcement: the report reaches the store and nothing else. A test asserts
the parameter is absent by inspecting the signature, so the property survives a
refactor that keeps the behavioural test green — but that signature test passes
against today's untouched tree, so it is a fence and not a proof. It therefore
rides *inside* US6-S1's test (T062) rather than standing as a scenario of its
own; the proof is US6-S1 itself, which compares two whole recorded rows.

**Trap 7 — the judge-import fence is enforced on the import graph.** Exactly one
module in this component may import `factory/verify/judge.py`;
`tests/test_verification_sweep.py:146` names it — `verify_activities.py` — and
`tests/test_verification_sweep.py:879` — `test_exactly_one_module_imports_the_judge`
holds it. The stated reason is that importing the judge means you can spend
money. A new scanner module must not become a second importer. The sweep will
catch it, but catching it costs an attempt, so do not write the import.

**Trap 8 — a scanner that fails is data, and there are three precedents.**
`judge_unavailable` behind green gates passes with the fact recorded rather than
fabricated. `DeliveryReceipt` reports a transport that could not send. A broken
manifest is one `CONFIG_ERROR` result, never zero results. All three exist
because "no result" and "a clean result" are the shape a naive reader confuses.
`scanner_unavailable` is the fourth. Nothing in the scanner path raises past its
caller, and in this spec a scanner that segfaults must cost the attempt nothing
at all.

**Trap 9 — `quality` must be reserved as a gate name too.**
`factory/verify/factory_yaml.py:168` is `_RESERVED_GATE_NAMES`, which exists so a
repo cannot declare a gate whose name collides with a step name. Adding
`quality` to `_VERIFY_STEPS` at `factory/verify/factory_yaml.py:171` without
adding it here leaves exactly that collision, and it will present as a confusing
parse error rather than as the clear refusal the parser is built to give.

**Trap 10 — the v2-only tuple, not the shared one.**
`factory/verify/factory_yaml.py:109-121` is `_TOP_LEVEL_KEYS`, legal in both
schema versions; `factory/verify/factory_yaml.py:134` is `_V2_TOP_LEVEL_KEYS`,
which appends `ladder` and `verify`. FR-011 requires `quality` in the second.
The wrong move is to copy `caches` — a perfectly good reader to copy in *shape*
— together with its registration, because `caches` is v1-legal. US2-S7 is
written as one differential test for this reason: the v1-refusal half passes
today, before any change, so only the pair can fail a diff that registered the
key in the wrong tuple.

**Trap 11 — SARIF paths are not worktree-relative by default.** A SARIF
`artifactLocation.uri` may be absolute, worktree-relative, or a `file://` URI,
and different tools choose differently. Normalise against the worktree root and
**refuse to scope any finding whose path does not resolve inside it** rather than
guessing. A finding silently mapped to the wrong file is worse than a finding
dropped, because the record-only phase is being used to set thresholds and a
mis-mapped finding poisons that measurement. Same rule for a result with no
`physicalLocation`: recorded, excluded, never mapped to line 1 (FR-018).

**Trap 12 — the version string is not optional.** FR-020 asks for the scanner's
own version alongside the findings. It looks like bookkeeping. It is the
difference between "the code got worse this week" and "ruff 0.6 added a rule",
and US5's entire purpose is comparing counts across weeks. It has a source and it
is not the manifest: SARIF carries it at `runs[].tool.driver.version`, in the
same document the adapter is already parsing (FR-020). Take it from there at scan
time. The wrong moves are a second invocation of the tool to ask its `--version`
— which doubles the scan's cost and can disagree with the document — and a
manifest key, which would make the operator responsible for keeping a number
accurate that the tool already reports.

**Trap 13 — do not add a coverage scanner, and do not add a threshold.** Both
are named in the spec's "What this spec refuses to measure" and "What this spec
is not". They are declared scope, not oversights. An implementer who adds a
`min_coverage` key because it seemed obviously missing has widened the spec, and
the reviewer should reject it on those grounds alone.

**Trap 14 — the scanner closed set has exactly one home, and it is US2's.**
[was wrong] The refuted pass had US2 enforce a closed set (FR-007) and US3
create one in `factory/controlplane/config.py`, which would land a US3
implementer in front of a constant US2 had already written: either duplicate it,
and FR-013's both-directions test then holds the registry equal to whichever copy
it happened to import, or move a constant the previous story just landed and
break its tests. The set lives beside `factory/verify/factory_yaml.py:171` and
`factory/verify/factory_yaml.py:168`, in US2. US3's FR-013 task adds the
conformance test and imports that constant. `factory/controlplane/config.py:51`
is cited as the precedent for the *test's shape* and for nothing else; US3's
diff must not touch that file.

**Trap 15 — an unconditional digest key moves every repository's `loop_digest`,
including the ones with no scanner.** `factory/verify/models.py:1132` —
`loop_digest` hashes a dict, so adding a `"scanner"` key to it — even with a
`None` value — changes the digest for a repository whose manifest names no
`quality` step at all. That contradicts FR-008 and FR-009's second half, and the
thing that catches it is US2's own pasted before/after evidence (US2-S10, T031).
[was wrong] There is **one** admissible move, not two: put the key in the digest
dict when and only when a scanner is resolved. The refuted repair also offered
bumping the `schema_version` keyword the function already takes at
`factory/verify/models.py:1137` — `loop_digest`, "accepting that every digest
moves once, deliberately". FR-009 forbids that in terms — "a repository that
names no scanner MUST keep the digest it has today" — and a `loop_digest` is a
recorded claim about what *verified* meant, so moving every one of them lands as
silent incomparability across the whole record. The other wrong move is the
unconditional key, with the digest quietly changing underneath every epic on the
floor.

**Trap 16 — this repository's manifest is `ergane.yaml`, and the `factory.yaml`
beside it is a stale v1 file no reader consults.** [was wrong] The refuted repair
named `factory.yaml` five times across the trio and `ergane.yaml` not once.
`factory/verify/factory_yaml.py:71` is `MANIFEST_NAME = "ergane.yaml"`;
`factory/verify/factory_yaml.py:985` — `resolve_manifest_path` returns the
preferred name whenever it exists and warns that "factory.yaml is ignored in
favor of ergane.yaml" when both do — and both do, here;
`factory/verify/gates.py:1409` — `resolve_gate_executor` composes
`worktree / MANIFEST_NAME` directly, so
the boundary selection never even reaches the legacy path. The two files differ
materially and not cosmetically: `factory.yaml:9` is `version: 1` with no
`ladder:` block, while `ergane.yaml:20` is `version: 2` with
`ladder: {max_attempts: 2, promotion_cycles: 1, ...}`. Three wrong moves follow
from reading the wrong one. A US1 spike that establishes FR-002's precondition
from `factory.yaml` has read the file the selector ignores. A US2 verification
that pastes "the `loop_digest` this repository's `factory.yaml` resolves to" has
pasted a digest production never records, because the ladder differs. And US2
lands a **schema-v2-only** key (FR-011), so an operator or implementer who opens
`factory.yaml` to try it meets a v1 file where `verify:` and `quality:` are both
unknown top-level keys and the refusal looks like a bug in the story. One more,
narrower: `factory/verify/factory_yaml.py:73-77` assembles the legacy name from
string fragments precisely so no reader in that module contains it as a literal,
and US2 edits that module — do not write it into a docstring there.

**Trap 17 — `uvx` does not exist inside the boundary the same story is required
to measure through.** [was wrong] FR-002 puts every candidate through
`factory/verify/gates.py:1394` — `resolve_gate_executor`, which on this host
returns `BwrapGateExecutor`. That boundary binds its toolchain as *leaf* binds:
`factory/verify/gates.py:753` — `_toolchain` resolves exactly
`(UV, NODE, GIT, DEFAULT_AGENT_RUNNER)` and
`factory/verify/toolchain.py:185` — `bind` returns `(real_path, found_at)`, one
file rather than its directory. `uvx` is a separate binary beside `uv`, so
inside the namespace it is not there. The wrong move is to run `uvx <tool>` and
record every candidate as disqualified for "a path no bind carries" — which is
what T006 instructs a disqualification to be recorded as, and which would report
that no scanner survives the sandbox. That is the exact false measurement FR-002
was written to prevent, on the one story whose output decides whether US2 to US6
are buildable, feeding a Constitution III decision the operator then makes on
fabricated data. Run `uv tool run <tool>` instead: same ephemeral install, and
`uv` is bound. Its cache is bound too —
`factory/verify/gates.py:943` — `_cache_binds` — so the install is not paid for
on every run.

**Trap 18 — `_VERIFY_STEPS` is also the absent-key default, so growing it moves
this repository's own digest.** [was wrong] The comment at
`factory/verify/factory_yaml.py:170` says so out loud and
`factory/verify/factory_yaml.py:924` — `_read_verify` is the return.
`ergane.yaml` declares no `verify:` key, so this repository resolves through it.
The wrong move is T021 as the refuted repair wrote it: "add `quality` to the
`_VERIFY_STEPS` tuple", full stop. That hands every v2 repository omitting
`verify:` a fourth step it never asked for, fails US2-S5, and moves
`loop_digest` through `request.verify_order` at
`factory/workgraph/workflow.py:2650` — `_verify` — where trap 15's guard does
not reach, because trap 15 guards the digest dict and this moves one of the
values already in it. Once US6 lands, FR-027's "the dispatched verify order
names `quality`" would then be true on every repository that never configured a
scanner. Add `quality` to the admissible set only, and give the absent-key
return its own default tuple mirroring
`factory/verify/models.py:340` — `FactoryConfig`. Correct the comment at
`factory/verify/factory_yaml.py:170` so it stops claiming one tuple is both.

## Approach, story by story

**US1** adds no production code. Run candidates with `uv tool run <tool>` —
**not** `uvx`, which trap 17 shows is not inside the boundary — so nothing
enters `pyproject.toml`. `uv` is already on the approved roster and is one of
the four executables the boundary binds, which is what makes this admissible
under Constitution III without spending an approval. Candidates
worth measuring: `ruff` (lint, fast, single binary), `semgrep`, `bandit`,
`radon`/`xenon` (numbers rather than rules), and the CodeQL CLI (heavy; measure
it so the decision to skip it is a measurement). Commit the note and the bounded
SARIF artifacts under this spec's directory. [was wrong] The note's
recommendation becomes the **`command:` string** an operator writes in
`ergane.yaml`'s `quality:` block — not a member of US2's closed set, which holds
adapter names (`sarif`, `none`) that FR-014 and FR-015 fix and US1 has no say
over. The refuted repair had it the other way round and forbade US2 from
"hardcoding a name this plan guessed at", which would have left US2 unable to
land FR-007 at all: it declares `concurrent_with: [US1]` and cannot read the
note. What US2 must not do is admit a *tool* name into that set.

**US2** is a parser change, a two-key block, a closed set, a config dataclass
field, and the dispatch chain. The chain is the half that is easy to skip and
expensive to skip: `load_loop_config`'s tuple, `ReadLoopConfigResult`, and the
**two** `EpicInput` constructions that read a manifest —
`factory/roadmap/workflow.py:1296` — `_dispatch` and
`factory/cli/nouns/build.py:931` — `_start_epic`. [was
wrong] The refuted repair said three, counting a `_start_epic` call site as a
construction. The tree's actual third construction,
`factory/workgraph/cli.py:675` — `_start_epic`, reads no manifest and passes neither
`verify_order` nor `diff_refusal_bytes`; it is deliberately left on `EpicInput`'s
defaults and is out of scope.

**US3** is the hook system, and it is the story the operator asked for. Follow
`factory/mergequeue/forge.py:342` — `resolve_forge` closely: module-level
registry, a `register_*` function, a `resolve_*` that lazily imports the built-in
module for the name and retries the lookup, and an error that lists what is
registered. The one piece with no precedent to copy is the destination seam, and
FR-014 now fixes it rather than leaving it to be invented: the adapter computes
the per-worktree path FR-026 requires, puts it on the invocation's `env` as
`ERGANE_QUALITY_SARIF` (`factory/verify/gates.py:269` — `GateInvocation`), and
the operator's `command:` references that variable. The adapter's deadline is
fixed the same way, at `factory/verify/models.py:1201` — `VerificationConfig`'s
`gate_timeout_s`, so US3 does not invent a manifest key inside a block US2 has
already landed the parser for (trap 14 again, in its other direction). The
conformance test holding the registry equal to the config's
closed set in both directions already exists for messengers; copy its structure.

**US4** is one new module: hunk-header scoping and SARIF URI normalisation, both
pure functions over fixtures. No store, no workflow, no config.

**US6** is the store column, the migration, the call site that makes the step
real, and the activity plumbing. The migration is additive and follows
`factory/verify/store.py:607` — `_migrate`, subject to trap 3's ordering.

**US5** is a read surface over rows US6 writes. It adds no store *state* — but it
does add one cross-epic read helper beside
`factory/verify/store.py:899` — `epic_history`, because every existing read over
verification rows takes an `epic_id` and FR-023's window does not. Copy
`factory/cli/usage.py:29` — `add_usage_parser` for the verb's shape.

## Sizing

| Story | Production files touched | Test files |
| --- | --- | --- |
| US1 | none. `specs/077-.../research/` only | none |
| US2 | `factory/verify/factory_yaml.py`, `factory/verify/models.py`, `factory/workgraph/workflow.py` (the `EpicInput` field **and** the `loop_digest`/`loop_summary` call at `factory/workgraph/workflow.py:2650-2651`), `factory/activities/roadmap_activities.py`, `factory/roadmap/workflow.py`, `factory/cli/nouns/build.py` | one new, **plus two landed ones**: `tests/test_023_us2_dispatch_pin.py:823` and `tests/test_092_manifest_threshold.py:186` (and `tests/test_092_manifest_threshold.py:233`) unpack `load_loop_config`'s tuple positionally and break the moment T029 widens it |
| US3 | new `factory/verify/scanner.py` plus two built-in adapter modules | one new |
| US4 | one new module under `factory/verify/` | one new |
| US6 | `factory/verify/store.py`, `factory/workgraph/workflow.py` (the call site in `_verify`), `factory/activities/verify_activities.py` | one new |
| US5 | `factory/cli/` (a noun plus its verb module) and one read helper in `factory/verify/store.py` | one new |

US1 shares no production file with anything, because it touches none. After the
US4/US6 split, US3, US4 and US5 share no production file with each other or with
US2. **US2 and US6 both touch `factory/workgraph/workflow.py`**, which the
US2 → US3 → US4 → US6 chain already serialises and which
`depends_on_merged: [US2]` on US6 declares rather than leaves inferred.
`factory/controlplane/config.py` appears in no row: it is a precedent this plan
reads, not a file this spec edits (trap 14).

Every story's diff must stay under `factory/verify/diffbounds.py:66`, which is
64 KiB by default and counts pasted evidence with the code. Two stories are at
risk and each is bounded deliberately:

- **US1**, because its deliverable *is* evidence. FR-004 bounds it by bytes
  rather than by scan: a whole-tree SARIF is hundreds of KiB, but so is a
  one-file scan under semgrep or the CodeQL CLI, whose `tool.driver.rules` array
  carries a `fullDescription` and a `help` blob per rule in the ruleset that ran,
  not per finding. Each committed artifact is therefore reduced to
  `runs[].results` plus the rules those results name, held under 8 KiB, with the
  unreduced byte count recorded in the note instead. [was wrong] The refuted
  repair then left the *number* of artifacts to the implementer — one per
  survivor, with "if the total climbs, drop artifacts and keep counts" as the
  only bound. Five survivors is 40 KiB of a 64 KiB refusal before the note, its
  per-candidate rows, the `ls -l` probe and the byte counts, so the story's size
  was being decided mid-commit against a threshold that refuses it unjudged if
  the guess is wrong. FR-004 now fixes it at **two** — the recommended candidate
  and one contrast — with every other survivor recorded as counts. That is a
  refinement-time decision, which is where a sizing decision belongs.
- **US2**, which carries seven requirements across six production files — the
  same arithmetic that split the old US4, and it is fair to ask why this one is
  not split too. The answer is US2-S8's: *a key that stops at `FactoryConfig` is
  a key production never reads.* The parser half and the chain half are one
  requirement wearing two hats, and a story that lands only the parser lands a
  manifest key with no reader, which is the shape the 2026-08-20 draft had and
  the shape this refinement's fifth "instruction gone wrong" came from. The
  volume is also unlike US4's: `load_loop_config` has two production call sites,
  each chain edit is one to fifteen lines, and the bulk of the diff is a single
  new test file — an estimate in the thirties of KiB against a 64 KiB refusal.
  Two *landed* test files come with it and are declared rather than discovered:
  `tests/test_023_us2_dispatch_pin.py:823` unpacks the tuple as
  `config, verify_order, _` and `tests/test_092_manifest_threshold.py:186` and
  `tests/test_092_manifest_threshold.py:233` unpack it as `_, _, declared`, so
  widening it turns both red until they are updated. The production call sites
  (`factory/activities/roadmap_activities.py:858` — `read_loop_config` and
  `factory/cli/nouns/build.py:826` — `start_command`) are already in the row;
  `loop_digest` and `loop_summary` stay safe because their new input is a
  defaulted parameter.
  Split it and the second half inherits a landed field it must not change, which
  is a worse trade than a large-but-shallow story.
- **US6**, which carries five requirements, a store column with its DDL and
  migration and ledger entry, a call site, activity plumbing, and two pasted
  `PRAGMA table_info` dumps. The two dumps are twenty-odd lines each. Its
  estimate is well under the threshold precisely because the scoping engine and
  its ten fixture-driven tests are US4's, not its.

## Constitution check

- **III (dependencies)**: US1 spends no approval — `uv tool run` runs candidates
  ephemerally, through the `uv` the boundary already binds (trap 17). The
  approval decision belongs to the operator *after* US1 reports,
  and a `docs/decisions.md` entry records it. **No story here may add a package
  to `pyproject.toml`.**
- **IV (determinism at the core)**: this spec moves work *toward* the
  deterministic half. The scanner is a subprocess and a parser; no LLM call is
  added anywhere.
- **II (test-first)**: every story's tests precede its implementation, and US6's
  central test is a negative — that the recorded row does not move.
- **VIII (provable from the diff)**: US1's deliverable is a committed note with
  pasted command output, because the judge sees only the diff. A spike whose
  evidence lives in a terminal is a spike the judge must fail.

## Verification the operator will run, independent of the gate

1. Read US1's committed note and check that every candidate row names the
   backend class that executed it. A row naming `SubprocessGateExecutor` has not
   measured the boundary, whatever else it says. Check also that no row
   disqualifies a candidate for needing the network.
2. Read US1-S6's pasted `ls -l` block. The `$TMPDIR` and `/tmp` lines must show
   nothing surviving and the `.git` line must show the byte. If that is not what
   it says, FR-026 is built on a wrong destination and US3 must be re-planned
   before it is dispatched.
3. `git diff --stat -- pyproject.toml uv.lock` over the whole spec's landed
   range: it must be empty. No story here may spend a Constitution III approval.
4. Run an epic with `quality` absent from `verify:` and confirm the recorded
   `loop_digest` matches one recorded before this spec landed. A green suite is
   evidence, not proof; this repository has shipped a fully green run of a
   command that could not start.
5. Run an epic with `quality` present and a scanner that reports findings, then
   read the verification row: the verdict must be what the same gates, diff
   check and judge would have produced with no scanner, and the quality evidence
   must be populated.
6. Run one with `quality` present and a deliberately failing gate. The quality
   column must be NULL and the scanner must not have been invoked — that is
   FR-027's guard, and it is the row of the truth table that had no mechanism
   before this refinement.
7. After the epic in step 5, run `git status --porcelain` in the node worktree
   before it is torn down: the scanner must have left nothing there (FR-026).
   Anything it left would already have been committed by salvage. Then run two
   nodes of the same epic concurrently and list the SARIF destinations under the
   parent repository's `.git`: there must be one per node. A single shared
   filename there is two attempts scored against each other's findings, and a
   single-node fixture can never surface it.
8. Read US1's note for the string it recommends for `command:`. It must
   reference `ERGANE_QUALITY_SARIF` (FR-014); a recommendation naming a literal
   output path is a command line no adapter can direct.
9. Open the store and confirm `PRAGMA table_info(verification_results)` lists the
   new column **last**, and that a store migrated from a pre-077 copy lists it in
   the same position as a freshly created one (trap 3).
10. Take a repository with **no** `verify:` key at all — this one — and confirm
    its resolved order is still exactly `(gates, diff_check, judge)` after US2
    lands. That is trap 18, and it is the one failure this spec can cause in a
    repository that asked for nothing.
