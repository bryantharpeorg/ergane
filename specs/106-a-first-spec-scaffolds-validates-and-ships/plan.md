# Implementation Plan: a first spec scaffolds, validates and ships

**Spec**: `specs/106-a-first-spec-scaffolds-validates-and-ships/spec.md`
**Evidence base**: `docs/container-onramp-research-findings.md` §7 (the first
run) and §8 failure mode 7 (idempotent re-entry). The rulings in the spec's
frontmatter came from that survey; do not relitigate them, and do not invent a
different interaction pattern because a simpler one occurs to you mid-story.

**Repaired 2026-08-24** against an adversarial review. Three things moved and
you should know which: US1 was split in two on the seam this plan already
named (generator vs verb); the readiness-renderer change was split out of the
install story; and two traps were added — 19 (the closing step must not probe
the control plane or the forge a second time) and 20 (a compiled node carries
no model alias). Trap 8's evidence was wrong in both citations and has been
restated.

## What already exists, and where

**Every line number below was opened individually off `346f811` on 2026-08-24.**
Check each again before you edit it: a plan citing a moved anchor sends you
hunting at the operator's expense. Two of the anchors below exist specifically
because the spec's prose implies machinery that is **not** there — read the
"already exists" claims as carefully as the "must be written" ones.

### The verb surface you are extending

- `factory/cli/nouns/spec.py:89` — `_add_spec_parser`. The `spec` noun's
  verbs today are exactly `list` (`:93`), `validate` (`:110`), `derive`
  (`:132`), `landed` (`:165`); `NOUN` is declared at `:183-188`. There is no
  `new`. US2 adds a fifth `commands.add_parser(...)` block here.
- `factory/cli/nouns/spec.py:116` — `validate_cmd`'s `--target-repo` defaults
  to `/srv/factory/targets/short-links`, **a path that does not exist on this
  host**. `spec validate` never looks at it; `spec derive` resolves it with
  `must_exist=True` (`factory/workgraph/cli.py:261-263`) and refuses. Neither
  `spec new` (US2) nor `build ship` (US4) may inherit that default — see
  trap 6.
- `factory/cli/nouns/build.py:1522` — `add_parser`; `start` is declared at
  `:1530-1548` and already composes `add_promotion_persona_flag` (`:1543`),
  `add_landing_dial_flags` (`:1547`) and its own `--max-concurrent-nodes`
  (`:1534-1542`, `default=1` at `:1537`). US4's `ship` is declared beside it,
  from the same helpers.
- `factory/cli/nouns/build.py:571` — `start_command`. It reads
  `args.promotion_persona` (`:589`), `args.graph` (`:598`) and
  `args.max_concurrent_nodes` (`:632`) by **direct attribute access**; only
  the landing dials are getattr-guarded (`factory/cli/landing.py:185-200`,
  whose docstring says the guard is load-bearing because callers hand-build
  namespaces). Trap 7.
- `factory/cli/nouns/build.py:871-881` — `kill_command`: `--yes`, `input(...)`,
  `except EOFError`, `"ergane: kill cancelled"`, `EXIT_USER` on decline. **The
  confirmation primitive US4 reuses**; do not write a second one.
- `factory/cli/nouns/build.py:549` — `_routing_token(node)`. It takes a
  *mapping* and returns `  persona <persona>  model <alias>` from the line at
  `:565`, reading the keys `persona` and `model_alias`. **It is not the helper
  US4's summary can reuse unchanged** — read trap 20 before you touch it. Its
  own docstring (`:558-560`) says it is absent for a node that has dispatched
  nothing, which is exactly the pre-dispatch case `ship` is in.
- `factory/cli/main.py:174` — `main(argv)` returns an int and routes every
  refusal through `run_cli` (the call is at `:208`). This is a public,
  in-process CLI seam. **US6's demonstration drives it** —
  `main(["spec", "validate", ...])` — which is why US6 needs nothing from US4.
- `factory/config.py:219` — `load_personas()`, returning `{name: Persona}`;
  `Persona.model` (`:184`) is the alias, `str | None`. This is the registry
  `_check_personas` already resolves against, and the only place a
  *pre-dispatch* model alias exists. Trap 20.

### The scaffold generator that already exists (US1 is not greenfield)

The spec's gap statement — "the onramp currently hands over no scaffold" — is
true of the *verb* and false of the *machinery*. Do not write a second
generator.

- `factory/doctor/scaffold.py:24` — `scaffold_spec(...) -> (spec_md, plan_md,
  tasks_md)`. Pure: text in, three texts out, **zero filesystem writes** (the
  module docstring at `:8-11` states the contract). US1 adds its entry point
  in this module, beside it, and inherits that contract: US1 reads no
  repository and no filesystem, which is precisely the seam the story was
  split on.
- `factory/doctor/scaffold.py:21` — `_CREDENTIAL_RE`, the `sk-…` sanitizer;
  `:52-55` `_sanitize_text`. US1's generator runs its inputs through the same
  sanitizer. A slug or title is operator-typed text and gets the same
  treatment.
- `factory/doctor/scaffold.py:87` — `lines.append("state: draft")`. **Keep
  it.** Trap 2.
- `factory/doctor/scaffold.py:169` — `_build_tasks_md`. **Empirically broken
  for `spec validate`**, and the falsification that shaped this plan: it emits
  `## Implementation` / `## Verification` with no per-story phase heading, so a
  generated trio fails the real validator with
  `[prompt_assembly] tasks.md declares no phase naming user story US1, so this
  node has no task slice to work (FR-006)`. `ergane findings promote` only
  proves the scaffold **derives** (`factory/cli/doctor.py:565-577`), never that
  it **validates**, which is how the defect survived. Trap 1.
- `factory/cli/doctor.py:544-579` — the atomic write US2 copies verbatim in
  shape: refuse an existing directory (`:544-548`), `TemporaryDirectory(dir=
  specs_root, ...)` so the rename is same-filesystem (`:557-559`), write the
  three files, prove the result, `temp_dir.rename(spec_dir)` (`:579`). Never
  leave a half-written spec directory.

### What a generated `tasks.md` must satisfy, and who decides

- `factory/workgraph/prompt.py:502` — `_names_story(number)`: the phase
  heading's text must match `\bUser Story <n>(?!\d)`. This, not a style guide,
  is the rule US1's generator must satisfy.
- `factory/workgraph/prompt.py:578` — `task_slice_bounds(node, tasks_text)`,
  **public by design** ("the slice's extent is a fact about dispatch that a
  check running before dispatch needs"). US1 calls it on its own output, per
  node, in its tests; US2 calls it again inside the temporary directory before
  renaming into place. That call is the difference between a scaffold that
  passes its own US1-S2 and the one that already exists.
- `factory/cli/nouns/spec.py:532-569` — `_check_scenario_coverage`: a missing
  `tasks.md` is a **refusal** (`:551-556`); acceptance-scenario ids the tasks
  never mention are an **advisory** (`:563-568`). Note which side mints and
  which side scans, because the generator has to satisfy **both**: the
  *declared* ids come from `parse_spec(spec_text)` reading
  `scenario.scenario_id`, minted as `f"{story_key}-S{position}"` at
  `factory/verify/criteria.py:355`; the *referenced* ids are whatever
  `_SCENARIO_ID_RE` (`factory/cli/nouns/spec.py:47`, the literal
  `US\d+-S\d+`) finds in `tasks.md`. The generated tasks must reference every
  id the generated spec mints, in that spelling, or the scaffold's first
  validate carries an advisory it was written to avoid.
- `factory/workgraph/contention.py:89` — `named_files(text)`, with its
  recognizer vocabulary at `:47-68`: `_TOKEN_RE` (`:51`), `_FILENAME_RE`
  (`:56`), `_BARE_EXTENSIONS` (`:63-68`). The comment at `:47-50` says the
  token regex stops at the `:` of a `file.py:558` anchor **on purpose**, so an
  anchor never has to be stripped. US2's anchor picker reuses this vocabulary;
  there is no third path regex in this repository and there will not be one.
- `factory/workgraph/contention.py:240` — `apply_contention_edges`, whose
  docstring at `:246-249` states that the inferred edge lands in
  `depends_on_merged` (D-025, not a third edge kind). Two generated stories
  whose task prose names the same file get silently ordered; the scaffold's
  later slots therefore name no file paths at all except the one worked anchor.
  Trap 4.

### Anchor resolution: what is **not** there

There is no file:line resolver anywhere in `factory/`. Grepping for `anchor`
returns escalation windows, landing attributions and question headings — prose
uses of the word, nothing that resolves a path against a tree. US2-S2's
"names a tracked file in that repository … read back to confirm it resolves" is
**entirely new code**, small and pure, and `named_files` is the only thing it
inherits.

### Spec numbering: what is **not** there either

Nothing constrains a spec directory's name. `factory/roadmap/models.py`'s
`read_roadmap` walks every direct child directory holding a `spec.md`; the
`NNN-` prefix is convention enforced by no code. US2's numbering logic is the
first and only place it becomes a rule, and no existing validator will catch it
if it gets that wrong. Trap 3.

### The validate report US3 extends

- `factory/cli/nouns/spec.py:224` — `_ValidateFinding(layer, message, *,
  severity="refusal")`. Two severities exist: `"refusal"` and `"advisory"`.
- `factory/cli/nouns/spec.py:240-244` — **two channels**: `findings` (counted
  toward the exit code) and `information` ("Stated, never counted", the comment
  at `:241-243`). US3 needs no new report shape, no new JSON key and no new
  severity value.
- `factory/cli/nouns/spec.py:385-428` — the printer. `has_refusal` (`:385`)
  alone decides the exit code (`:428`). The human block is gated on
  `if findings:` (`:391`) and the label branch at `:393-396` is a two-way
  if/else that prints **anything not `"advisory"` as `"refusal"`**. The
  all-pass sentence goes to **stdout**; the `skipped` loop (`:415-420`) and the
  `information` loop (`:421-426`) both go to **stderr**, and the latter already
  prints `ergane spec validate — noted, not a refusal: [<layer>] <message>`
  for free. Trap 8.
- `factory/cli/nouns/spec.py:257` — **`spec validate` compiles the graph
  itself** by calling `derive_workgraph`. Trap 9, the story-killer.
- `factory/cli/nouns/spec.py:281-286`, `:372-383` — `checked`, `skipped`,
  `findings`, `information`: the JSON report's shape.
- `factory/cli/nouns/spec.py:464-480` — `_check_personas` resolves every node's
  persona against the real `load_personas()`. The deriver's default persona is
  `implementer` (`factory/workgraph/derive.py:86`), present in
  `personas.example.yaml` **only after `ergane install` seeds it**
  (`factory/cli/install.py:741`). Trap 5.

### The install ending US6 attaches to

- `factory/cli/install.py:687` — `install_command`, the interactive path. Its
  tail is `_interview_personas(...)` (`:717-719`, landed by 103), then
  `print("verifying the control plane...")` (`:721`),
  `findings, exit_code = verify_controlplane(str(path))` (`:722`),
  `print(render_findings(findings))` (`:723`), `return` (`:724`). **The name
  `findings` bound at `:722` is the whole of trap 19**: it is the probe result
  the closing step must reuse rather than recompute.
- **The same five-line ending is duplicated at `:806-810`
  (`_install_non_interactive`, defined `:761`) and `:900-904`
  (`_install_from_file`, defined `:855`).** Three endings, not one. Trap 11.
- `factory/cli/install.py:825` — `_FilePrompter`; `:1391` `_ask`, the question
  primitive with `default=`. `factory/cli/init.py:142` `_prompter()` is how
  install reaches a prompter (`install.py:718`).
- `tests/test_ergane_install_walkthrough.py:251-262` — one
  `@pytest.fixture(autouse=True)` monkeypatching
  `install_module._interview_personas` neutralises 103's step across that
  whole file. US6's step must be a **module-level function in `install.py`**
  so the same fixture can grow one line. Trap 12.

### The init half US6 may and may not use

- `factory/cli/init.py:1074` — `_write_scaffold(repo_root, manifest_text)`:
  "writes exactly the declared files and nothing else" — `ergane.yaml`,
  `.gitignore`, `.ergane/`, and `specs/` (`:1091-1092`). **This is the half
  US6 wants.**
- `factory/cli/init.py:969` — `_schedule`. Its docstring at `:976-978`: "the
  only act of `ergane init` whose blast radius reaches past the repository
  being joined". `:942-967` records the incident that produced it — an `env -i`
  init found a live namespace nobody had declared and published into it. It
  refuses only when the control plane is unreadable, and install's closing step
  runs exactly when the control plane *is* readable. **US6 must not call it.**
  Trap 10.
- `factory/cli/init.py:1036` — `_register`, which calls
  `registry.register(slug, repo_root)` with no path override, writing the
  operator's real registry at `resolve_registry_path()`. **US6 must not call
  it either.** (`factory/registry.py:400` does accept `path=`, and `:451`
  `forget` removes one row — but the story's "nothing stays registered" is
  cheaper as a structural fact: nothing ever registers.)
- `factory/cli/init.py:852` — `_wire` is opt-in and safe; irrelevant here.
- `factory/cli/init.py:1344` — `run_check`, `:1308` `render_check`, `:1285`
  `check_repo`, and the `--check` flag at `:343`, documented as "judge this
  repository's readiness and exit; writes nothing"
  (`_git_read`'s docstring at `:1100-1103` holds the whole path to that
  promise). `render_check` already carries the three-mark `PASS`/`WARN`/`FAIL`
  grammar and a summary line that refuses to say "all passed" over a `WARN`.
  **This is US5's subject and US6's readiness pass.** Traps 13 and 19.
- `factory/cli/init.py:128` — `_forge_factory`, and `:139`
  `_controlplane_probe`. **The two seams trap 19 turns on**, both already
  documented as "rebound in tests". The comment at `:124-127` records nine
  tests dying the last time this file grew a second forge factory; do not add a
  third path to either boundary.
- `factory/cli/init.py:821-823` — the shipped "next, run:" ending: the literal
  string `next, run:` (`:821`), then verbatim commands one per two-space-indented
  line (`:822-823`). US2-S4 and US6-S1/S2 both imitate **this** shape. A second
  next-command grammar in the same CLI is the avoidable outcome. (Keep this
  anchor in the plan rather than in a task slice: US5 edits this file and US2
  does not, and a stray path in US2's slice would order the two for nothing.)

### The renderer US5 must not confuse with the other one

`factory/controlplane/verify.py:1127` — `render_findings` emits
`[PASS|FAIL] check: detail` and has **no remedy column**. Only the
host/dependency probe folds a remedy into its detail (`:984-1013`); `LLMProbe`
(`:652`), `TemporalProbe` (`:742`), `MemoryProbe` (`:804`), telemetry (`:881`),
escalation (`:949`) and forge (`:1074`) all pass `snapshot.detail` through
unchanged. US5's "every red line naming its fixing command" is **not** a
property of any existing renderer. Trap 13 rules which one wins and how it
grows.

## Traps

**1. Do not call `_build_tasks_md` (`factory/doctor/scaffold.py:169`), and do
not "fix" it either.** It emits no per-story phase heading, so a trio built
from it fails `check_prompt_assembly` — verified by generating one and running
the real validator. Write US1's task-document builder to emit
`## Phase <n>: User Story <n> — <title>` headings that satisfy
`_names_story` (`factory/workgraph/prompt.py:502`), and leave the ledger
generator alone: `findings promote`'s tests pin its current output, and
retrofitting it is a separate change that belongs to whoever files it as a
finding. Your generator must not import it.

**2. The generated frontmatter says `state: draft`, and a test asserts it.**
The roadmap dispatches ready specs on its own schedule
(`factory/roadmap/schedule.py`, `factory/roadmap/workflow.py`): a scaffold that
ever wrote `state: ready` would be dispatchable, unattended, at real cost. The
existing generator gets this right by accident
(`factory/doctor/scaffold.py:87`); pin it on purpose.

**3. Spec numbers are immutable and no code enforces it but yours.** Scan the
specs root for *every* direct child directory whose name matches `^(\d+)-`,
whatever it contains — a half-written directory with no `spec.md` still owns
its number, and `read_roadmap` would not see it. Take `max + 1`, zero-pad to
three digits, and never reuse. Refuse rather than guess if two directories
claim the same number.

**4. The generated stories must not contend with each other.** Only the worked
story's task slice may name a file path; the skeletal slots name none.
`factory/workgraph/contention.py:240` (`apply_contention_edges`) turns a shared
file path in two slices into a silent `depends_on_merged` edge, which would
make the teaching scaffold compile into a serialized graph for no reason the
reader can see. Assert it: `named_files` over each generated slice, and only
slice one is non-empty.

**5. `spec validate` on a host that never ran `ergane install` refuses a
structurally perfect scaffold.** `_check_personas`
(`factory/cli/nouns/spec.py:464-480`) resolves against the real registry, and
`implementer` is seeded by install (`factory/cli/install.py:741`). `spec new`
must detect this at scaffold time — `load_personas()` raising, or not
containing the persona the deriver will name — and print one line naming
`ergane install` as the fix, in the same "next, run:" block. Do not work around
it by loosening `_check_personas`; that check is load-bearing at dispatch.

**6. Neither new verb inherits `validate`'s `--target-repo` default.** It is
`/srv/factory/targets/short-links` (`factory/cli/nouns/spec.py:116`) and it
does not exist here. `spec new` and `build ship` both declare `--target-repo`
**required**, and resolve it the way derive does —
`_resolve_identity_path(..., must_exist=True)`,
`factory/workgraph/cli.py:261-263`. Otherwise `ergane build ship <dir>` streams
a green validate and dies at stage two naming an absolute path the operator
never typed and cannot place.

**7. `build ship` must not hand-build a `Namespace`.** `start_command` reads
`args.promotion_persona`, `args.graph` and `args.max_concurrent_nodes` by
direct attribute (`factory/cli/nouns/build.py:589`, `:598`, `:632`); a missing
one raises `AttributeError` inside dispatch instead of an `OperatorError` at
the boundary — the opposite of every other refusal in this CLI. Declare those
flags on `ship`'s own parser through the same shared helpers `start` uses
(`:1534-1547`), and let `ship` set exactly one attribute afterwards:
`args.graph`. Same rule for the derive stage: declare `--output` and `--delta`
on `ship`'s parser, because `derive_command` reads `args.delta` at
`factory/workgraph/cli.py:265` and `args.output` at `:305` (`destination =
Path(args.output) if args.output else spec_dir / ARTIFACT_NAME` — which is also
where ship learns the artifact path when `--output` is absent).

**8. Do not add a third severity, and do not restructure the printer — and know
which sentence is actually protected by a test, because one of them is not.**
The label branch at `factory/cli/nouns/spec.py:393-396` prints anything that is
not `"advisory"` as `"refusal"`. There are **two** all-pass sentences:

- the **clean** one at `:409-410` (reached by the `else` at `:407`). It is
  asserted verbatim exactly once in this tree, at `tests/test_ergane_spec.py:525`.
- the **`…all pass; see advisory above`** variant at `:403-405` (reached from
  `if has_advisory and not has_refusal` at `:401`). It is asserted by
  **nothing**. `grep -rn "see advisory above"` over the tree returns one
  production hit and zero test hits.

That asymmetry is the point: the variant a spec carrying a `slice_contention`
advisory actually prints — including *this* spec — is the one a careless edit
breaks with every existing test still green. US3 adds that missing assertion
(T020). Earlier drafts of this plan cited
`tests/test_prompt_assembly.py:67` and `tests/test_slice_coverage.py:116` as
covering these sentences; both line numbers land inside those files' module
docstrings, and the prompt_assembly transcript there is stale (it predates
`slice coverage` joining the sentence). Do not go looking for assertions
there.
Sentinels ride the **existing `information` channel** (`:244`, printed at
`:421-426`), which is already documented as stated-never-counted and already
appears in the JSON report at `:380-382`. That gives US3-S1 both halves —
"structure passes" *and* every sentinel with its file:line — in one transcript,
with the exit code untouched and no existing sentence rewritten. Mind the
streams: the all-pass sentence is on stdout, the `information` lines are on
stderr, and US3's one summary line joins the `information` lines on stderr so
the sentinel block reads as one thing.

**9. The derive gate must not live inside `derive_workgraph`.** It has five
call sites: `factory/cli/nouns/spec.py:257` (**`spec validate` compiles the
graph itself** — a gate here refuses the fresh scaffold and directly
contradicts US3-S1), `factory/workgraph/cli.py:293`,
`factory/workgraph/delta.py:93`, `factory/cli/doctor.py:566` and
`factory/doctor/cli.py:326`; the roadmap's `derive_spec` activity
(`factory/roadmap/workflow.py:1198`) reaches the deriver too, and a gate there
would silently change autonomous dispatch. Put it in
`factory/cli/nouns/spec.py:204` `_derive_command`, the shipped
`ergane spec derive` verb, and nowhere else — and make it cover the `--delta`
path as well, since that is the same verb.

**10. `ergane init` publishes a real Temporal schedule; the closing
demonstration must never call `init_command`.** Call `_write_scaffold`
(`factory/cli/init.py:1074`) for the repo-local half and stop there. No
`_schedule` (`:969`), no `_register` (`:1036`), no `_wire` (`:852`). The
spec says "nothing stays registered"; it is silent on the schedule, and the
schedule is the one with reach past the machine. A test asserts the
demonstration touches neither the registry path nor the schedule client.

**11. The closing step lands on the interactive path only.** The
`verifying the control plane… / verify_controlplane / render_findings /
return` block is duplicated at `factory/cli/install.py:720-724`, `:806-810`
and `:900-904`. `--non-interactive` and `--from-file` are how tests and 104's
container path install; a demonstration on those paths is an interactive prompt
in a non-interactive run. Wire `:720-724` and leave the other two byte-identical.
**If 104 has landed before you start** — and the spec's `depends_on_landed`
edge says it has — `install_command`'s body no longer looks like this: 104's
T035 replaces its placeholder branch with a container path and keeps the native
`verify_controlplane` call. Re-open `install_command` and attach to whichever
branch still ends in `render_findings`, and say in your paste which one you
found.

**12. Declare the closing step as a module-level function in `install.py` for
the sake of one fixture.** `tests/test_ergane_install_walkthrough.py:251-262`
neutralises 103's persona step across ~25 walkthrough tests with a single
autouse monkeypatch. Yours must be stubbable the same way, and growing that
fixture by one `monkeypatch.setattr` line is **required work**, not optional
tidying — otherwise every one of those tests starts running a demonstration.

**13. One renderer, not three.** `render_check`
(`factory/cli/init.py:1308`) wins: three marks, honest summary, blocking vs
warning, and a repository-shaped subject. Do **not** grow
`factory/controlplane/verify.py:1127` `render_findings` a remedy column — that
is a cross-cutting edit to seven `evaluate()` methods in a file both 088 and
103 touched this week — and do not write a third renderer inside `install.py`.
US5 delivers "every red line names its fixing command" by giving
`render_check` an **optional** remedy mapping (default `None`, so
`ergane init --check`'s existing output stays byte-identical and its tests stay
green); US6 supplies the table. Unknown check names get a stated fallback
naming `ergane init --check`; a non-passing line with no fix text is the
failure this trap exists to prevent.

**14. The demonstration's throwaway spec carries no sentinels.** US1's
scaffold is deliberately underivable (US3 makes it so), and the demonstration
must reach `spec derive` and print a compiled graph. So the generator takes an
explicit mode — the fully-worked story alone, no sentinels, no skeletal slots —
and the demonstration uses it. Discovering this at implementation time, as
"why does my demo refuse", is a wasted attempt.

**15. The demonstration is free, local, offline, fast, and re-runnable.** No
dispatch (dispatch is this factory's money step and §7 of the findings names
surprise cost as the classic abandonment cause); no LLM call; no network; no
systemd; no `docker`. It runs inside a `TemporaryDirectory` that is gone when
it returns, and re-running `ergane install` converges rather than erroring
(findings §8 failure mode 7: the health gate becomes the front door). Its
failure never changes install's exit code — install's verdict stays
`verify_controlplane`'s. **Trap 19 is how you actually keep this promise**;
this trap only states it.

**16. Skippable is part of the contract, and both branches print the same next
command.** Ask through the existing prompter (`factory/cli/install.py:1391`
`_ask`, reached via `factory/cli/init.py:142`) so `_FilePrompter` can drive it;
an all-Enter answer file must not hang, and a declined demonstration ends the
transcript with the identical `next, run:` block.

**17. `ergane spec derive --delta` with no `-o` overwrites the tracked
`specs/<dir>/workgraph.json`.** Every test and every code path in this spec
that runs derive against a directory it did not create must pass an explicit
output path or work on a copy. `build ship` runs derive without `--delta` by
default and writes the conventional artifact, which is correct; a ship test
pointed at a real spec directory in this repo is not.

**18. The judge sees the diff and the criteria, nothing else** (constitution
principle VIII, D-037). Every success criterion in `tasks.md` is pasted output
committed in the diff. "Run X and observe Y" is unprovable and will be judged
as unmet, however true it is. Where the real thing is not reachable from your
sandbox — a live control plane, a real `gh` remote, an interactive terminal —
the criterion is a **seam capture**: the transcript produced with the named
seam rebound, labelled as such in the paste, naming which seams were rebound.
Do not dress a seam capture as a hardware run, and do not leave an
unproducible criterion in front of the judge instead.

**19. `check_repo` with `control_plane=None` re-runs the entire probe suite,
and reaches the network through a forge.** This is the trap that would have
made US6 violate trap 15 while every test passed. Two paths, both live:

- `check_repo` (`factory/cli/init.py:1285`) calls `gather_init_facts`
  (`:1224`), and at `:1260-1261` a `None` `control_plane` calls
  `_control_plane_facts()` → `_controlplane_probe` (`:139`) →
  `verify_controlplane` — the full LLM / Temporal / memory / telemetry /
  escalation suite, i.e. an LLM call and network traffic, two lines after
  install just ran exactly that. **Pass install's own result through**:
  `check_repo(root, control_plane=(tuple(findings), None))`, where `findings`
  is the name bound at `factory/cli/install.py:722`. The `control_plane`
  parameter exists for precisely this reuse and its docstring
  (`factory/cli/init.py:1236-1239`) says so.
- `check_repo` then resolves a forge through `_forge_factory`
  (`factory/cli/init.py:128`) and hands it to `onboard_target_repo`
  (`factory/activities/merge_activities.py:514`), which calls
  `forge.describe_repository()` (`:564`) and `forge.landing_policy()` (`:573`)
  — real `gh` calls against a throwaway `git init` repository with no remote.
  **`_forge_factory` is the seam**: the demonstration and its tests go through
  that one name, rebound. Do not add a second factory to that file; the
  comment at `:124-127` records nine tests dying the last time someone did.

**20. A compiled `WorkNode` has no model alias, so `_routing_token` prints a
blank tail.** `_routing_token` (`factory/cli/nouns/build.py:549`) returns
`f"  persona {persona}  model {node.get('model_alias', '')}"` at `:565`.
`WorkNode` (`factory/workgraph/models.py:174-196`) declares
id / story_key / persona / spec_ref / requirement_keys / depends_on /
depends_on_merged / timeout_override_s and **no `model_alias`** — the helper's
own docstring (`:558-560`) says it is absent for a node that has dispatched
nothing, which is the entire pre-dispatch case. Reuse it and every
`build ship` summary line ends in a bare `model ` while a stream-position test
passes: the "a fully green run shipped a command that could not start" class.
**US4 resolves the alias itself, before formatting**, from
`load_personas()` (`factory/config.py:219`) — `Persona.model` (`:184`), the
same registry `_check_personas` already resolved at stage one, so a persona
that is not in it never reaches the summary. Feed the resolved alias into
`_routing_token`'s mapping (`{"persona": …, "model_alias": …}`) so there is
still one formatter; when `Persona.model` is `None`, pass the literal
`<registry default>` rather than an empty string. A test asserts no summary
line ends in `model `.

## Technical approach, per story

### US1 — the scaffold generator (pure)

A new public entry point in `factory/doctor/scaffold.py` beside `scaffold_spec`
(`:24`), sharing `_sanitize_text` (`:52`) and `state: draft` (`:87`). It takes
the slug, the title and an **already-resolved** `path:line` anchor string, and
returns three texts. It reads nothing: no repository, no filesystem, no
registry. That is the seam this story was split on, and it is what makes every
US1 criterion a pure-function assertion.

What the returned trio must contain:

- three story slots — worked, partial, skeletal — each with a conforming
  `### User Story N - Title (Priority: PN)` heading and literal Given/When/Then
  `**Acceptance Scenarios**`;
- a `## Work Graph` yaml block with an explicit `implements:` on every node;
- a `tasks.md` with `## Phase <n>: User Story <n> — …` headings (trap 1)
  referencing every minted `US<n>-S<m>` id (see the mint/scan split above);
- an `ERGANE-TODO:` sentinel on every mandatory blank. **Sentinels appear in
  prose only**: never inside the Work Graph fence, never inside a story
  heading, never in a task-id prefix — a sentinel in any of those breaks the
  structure the scaffold exists to demonstrate;
- only the worked story's task slice names any file path (trap 4).

The module also exports the sentinel token and a pure
`scan text → [(line_no, text)]` helper, which US3 consumes, and takes a
`demonstration` mode returning the worked story alone with no sentinel and no
skeletal slot (trap 14).

US1's own proof is the real validator: write the three texts to a `tmp_path`
directory and drive `main(["spec", "validate", …, "--json"])` over it. Capture
the red first — a trio built from `_build_tasks_md` fails prompt_assembly — or
the green proves nothing.

### US2 — `ergane spec new`

A `new` subparser in `_add_spec_parser` (`factory/cli/nouns/spec.py:89`):
positional `slug`, required `--target-repo`, `--specs-root` defaulting to
`DEFAULT_SPECS_ROOT`, optional `--title`. Its handler:

1. Resolve `--specs-root` and `--target-repo` with `must_exist=True`
   (trap 6), `mkdir(parents=True, exist_ok=True)` the specs root the way
   `factory/cli/doctor.py:542` does.
2. **Number**: scan the specs root's direct children for `^(\d+)-`, take
   `max + 1` zero-padded to three (trap 3). Directory name is
   `<NNN>-<slug>`; refuse if it exists.
3. **Anchor**: pick one real `path:line` from the target repo — enumerate
   tracked files (`git ls-files`), keep those whose final segment satisfies
   `factory/workgraph/contention.py:_FILENAME_RE` with an extension in
   `_BARE_EXTENSIONS` (`:63-68`), sort, take the first with enough lines to
   anchor, and **read it back to confirm the line index resolves**. Refuse,
   naming what it looked for, if the repository offers none — never emit an
   unresolvable anchor. Assert the rendered anchor round-trips through
   `named_files` (`:89`).
4. **Generate** by calling US1's entry point with the slug, the title and that
   anchor. This story writes no document text of its own.
5. **Prove before renaming**: into a `TemporaryDirectory(dir=specs_root, …)`
   (`factory/cli/doctor.py:557-559`), write the trio, call `derive_workgraph`
   and then `task_slice_bounds` (`factory/workgraph/prompt.py:578`) for every
   node. Any failure raises `OperatorError` and the temp directory disappears
   with it. Only then `temp_dir.rename(spec_dir)` (`:579`).
6. **Print** the directory, then an `init.py:821-823`-shaped `next, run:` block
   with the literal `ergane spec validate <dir> --target-repo <repo>` — plus,
   when `load_personas()` refuses or lacks the deriver's persona, a line naming
   `ergane install` (trap 5).

### US3 — sentinels gate derive, not validate

`factory/cli/nouns/spec.py` only.

- A small private helper reads the trio and returns
  `[(document, line, text)]` using US1's exported token and text scanner.
- **Validate**: append every sentinel to `information` (`:244`) as
  `_ValidateFinding("sentinel", "<doc>:<line>: <text> — not ready to derive")`,
  and append `"sentinels"` to `checked` **last**, unconditionally (the scan
  reads text, so it never lands in `skipped`). Print one summary line on
  **stderr**, after the `information` loop (`:421-426`): *N `ERGANE-TODO`
  sentinels remain; `ergane spec derive` will refuse until they are resolved.*
  Nothing else in the printer changes (trap 8).
  `tests/test_prompt_assembly.py:254` asserts `checked` exhaustively and must
  grow by exactly the string `"sentinels"` — that one-line test edit is
  declared work, not collateral damage.
- **Derive**: at the top of `_derive_command` (`:204`), before delegating,
  refuse with an `OperatorError` naming every sentinel with its file:line, and
  say which verb clears it. Covers `--delta` because it is the same verb.
  Nowhere else (trap 9).
- **Add the missing assertion on the advisory all-pass sentence** (trap 8). It
  is the only sentence in this printer that no test protects, and this is the
  story standing next to it.

### US4 — `build ship`

A `ship` subparser beside `start` in `factory/cli/nouns/build.py:1522`,
composing `add_promotion_persona_flag` and `add_landing_dial_flags` and
declaring `--max-concurrent-nodes`, `--output`, `--delta`, `--target-repo`
(required), `--specs-root`, `--yes` and the positional `spec_dir` (trap 7).
`factory/cli/nouns/spec.py` gains two thin **public** wrappers —
`validate_spec_command(args)` and `derive_spec_command(args)` — delegating to
`_validate_command` (`:231`) and `_derive_command` (`:204`); the private names
and their `set_defaults(run=…)` wiring stay exactly as they are, so
`tests/test_graph_paths_are_absolute.py:132` keeps importing what it imports.

`ship_command` then:

1. Prints a stage banner, calls `validate_spec_command(args)` and streams it
   whole. Non-zero → return that code. **No dispatch, no derive.**
2. Prints the next banner, calls `derive_spec_command(args)`, streams it whole.
   Non-zero → return that code. Resolve the artifact path (`--output`, else
   `<spec-dir>/workgraph.json`) and refuse clearly if it is absent — that is
   the empty-delta case, which prints "nothing to build" and writes no file.
3. Loads it with `load_workgraph` and prints the summary: node count, dispatch
   order, and one line per node carrying the node's persona and the alias
   resolved from `load_personas()` — **not** `_routing_token` over a raw
   compiled node, which prints a blank tail (trap 20).
4. Unless `--yes`, confirms with `kill_command`'s primitive (`:871-881`) —
   same `input`, same `EOFError` handling, same cancelled-message shape,
   `EXIT_USER` on decline.
5. Sets `args.graph` to the artifact path and returns `start_command(args)`.

Tests stub `start_command` at the module attribute; nothing in this story opens
a Temporal connection. **Ship's fixture is a hand-written spec directory, never
a `spec new` scaffold**: once US3 lands, a scaffold's sentinels make stage two
refuse, and a ship test built on one starts failing for a reason that is not
ship's. Trap 17 also applies — point derive at a temporary copy, never at a
tracked `specs/<dir>` in this repository.

### US5 — every non-passing readiness line names its fix

One optional parameter on `render_check` (`factory/cli/init.py:1308`),
defaulting to `None`: a mapping from check name to the command that clears it.
With it, every non-passing line gains a fix clause and a name the mapping does
not carry falls back to a stated line naming `ergane init --check`. Without it,
the rendered text is byte-identical to today's, which is what keeps
`ergane init --check`'s existing tests green untouched (trap 13). The table
itself belongs to the caller — US6 supplies it — so this story ships the
mechanism and its fallback, and nothing else.

### US6 — install ends mid-conversation

A module-level `_closing_demonstration(prompter, findings, …)` in
`factory/cli/install.py`, called only from `install_command`'s tail
(`:720-724`) after `render_findings` and before `return` (traps 11, 12). It
never changes the returned code (trap 15).

1. Ask, through the prompter, whether to run it. Declined → print the
   `next, run:` block and return (trap 16).
2. Inside a `TemporaryDirectory`: `git init` a throwaway repo, call
   `_write_scaffold` (`factory/cli/init.py:1074`) — and nothing else from init
   (trap 10).
3. Run the readiness pass: `check_repo` (`factory/cli/init.py:1285`) with
   `control_plane=(tuple(findings), None)` — install's own probe result,
   already computed at `:722`, never a second probe (trap 19) — then
   `render_check` (`:1308`) with US5's remedy mapping (trap 13). The forge that
   `check_repo` resolves comes through `_forge_factory` (`:128`), which is the
   one seam the tests rebind.
4. Generate the demonstration spec through US1's generator in its
   sentinel-free demonstration mode (trap 14) and write it under the
   throwaway repo's `specs/`.
5. Take it through the real CLI in-process: `main(["spec", "validate", …])`
   and `main(["spec", "derive", …])` (`factory/cli/main.py:174`), so the
   transcript is the factory's own labeled output and this story couples to
   nothing US4 does. Print the compiled graph.
6. End with the `next, run:` block: the verbatim `ergane spec new <slug>
   --target-repo <their repo>`. Same block as the skip branch.

## Sizing

Measured task counts: US1 = 9, US2 = 9, US3 = 10, US4 = 12, US5 = 4, US6 = 12
— 56 in all. For scale, the stories that recently landed in this repository run
3–11 tasks each and their specs total 20–33. Two stories here sit one task over
that observed ceiling and both are assembly rather than invention; every other
story is inside it.

The original draft carried this as four stories with US1 at 15 tasks — larger
than any single story in that landed corpus, and bundling a text generator, a
numbering rule, a brand-new anchor resolver, an atomic write, a self-proof and
a verb. The recorded incident is that one oversized, coarsely-split story
burned more than six normal attempts' combined cost, so it was split on the
seam this plan already named: **generator + self-proof** (US1, pure, text in
and text out) versus **verb + numbering + anchor** (US2, which reads a
repository and writes a directory). They no longer share a fixture, and that is
the point — US1's fixture is a string, US2's is a git repository.

The install story was over the same ceiling at 13, and its renderer change is a
clean seam: `render_check`'s optional remedy mapping is a self-contained,
independently testable edit in a different file from the demonstration, with
its own byte-identical-by-default criterion. It is US5, and US6 supplies the
table.

US3 is the smallest by diff and the largest by blast radius: four edits inside
one function, three of which are one line, one existing test that must grow by
one string, and one missing assertion it is the first story ever to be standing
next to. Traps 8 and 9 are its whole survival kit.

US4 is mostly assembly; its risks are traps 7 and 20. US6's risks are traps 10,
13, 14 and 19 — the side-effect blast radius, the renderer choice, the
sentinel-free mode it needs from US1, and the two probes it must not re-run.

## The Work Graph

Mirrors `spec.md`'s declaration exactly — the deriver reads that one, and a
plan whose graph disagrees with the spec's is a plan that lies. `implements` is
empty on every node because this spec's Requirements section is a prose summary
rather than numbered FRs; every task therefore anchors on a scenario id
(`US<n>-S<m>`), which is what `_check_scenario_coverage`
(`factory/cli/nouns/spec.py:532-569`) actually reads.

```yaml
- id: us1
  story_key: US1
  persona: implementer
  depends_on: []
  depends_on_merged: []
  implements: []

- id: us2
  story_key: US2
  persona: implementer
  depends_on: []
  depends_on_merged: [US1]
  implements: []

- id: us3
  story_key: US3
  persona: implementer
  depends_on: []
  depends_on_merged: [US1]
  implements: []

- id: us4
  story_key: US4
  persona: implementer
  depends_on: []
  depends_on_merged: []
  implements: []

- id: us5
  story_key: US5
  persona: implementer
  depends_on: []
  depends_on_merged: []
  implements: []

- id: us6
  story_key: US6
  persona: implementer
  depends_on: []
  depends_on_merged: [US1, US3, US5]
  implements: []
```

Declared chain depth 3 (`US1 → US3 → US6`), with US4 and US5 declared free.

**Two advisories are expected, and both are correct.** US2, US3 and US4 all
name `factory/cli/nouns/spec.py` in their slices, because all three genuinely
edit it. `ergane spec validate` reports exactly this today — verified by
running it against this trio on `346f811`:

```
ergane spec validate — advisory: [slice_contention] inferred, not declared:
US3's task slice and US2's both name `factory/cli/doctor.py`,
`factory/cli/nouns/spec.py`, and the spec declares no ordering between them.
[…] so US3 — the later-declared of the two — waits for US2 to merge.

ergane spec validate — advisory: [slice_contention] inferred, not declared:
US4's task slice and US3's both name `factory/cli/nouns/spec.py`,
`tests/test_ergane_spec.py`, and the spec declares no ordering between them.
[…] so US4 — the later-declared of the two — waits for US3 to merge.
```

Exit code 0, `findings` carrying those two advisories, `information` empty, and
every layer in `checked`. The inference hooks both edges into
`depends_on_merged` itself (`apply_contention_edges`,
`factory/workgraph/contention.py:240`), so the compiled graph runs

```
us1 → us2 → us3 → us4
us1, us3, us5 → us6
```

— **effective chain depth 4**, verified by deriving to a scratch path and
walking the compiled edges. That is two levels of merge-waiting more than the
declared graph, and it is honest: three stories editing one file cannot land
concurrently, and `--max-concurrent-nodes` is pinned at 1 anyway, so depth
costs no wall clock here — only the order in which merges queue.

**Do not silence the advisories with `concurrent_with`**
(`factory/workgraph/derive.py:80-82`). The regions of `spec.py` are disjoint
(US2: a parser block and a new handler; US3: two existing function bodies;
US4: two new wrappers at the end), but "disjoint regions of one file" is a
claim about a diff nobody has written yet, and the merge queue is what would
pay for it being wrong.

## What else is in flight, and what it collides with

Corrected 2026-08-24: the previous version of this section was false in both
directions, and the collisions land exactly where this spec works.

- **088 and 103 are landed.** 103 moved everything in `install.py` down by
  ~440 lines; every `install.py` anchor above is post-103.
- **104 collides hard, and `spec.md` declares the edge.** 104's T035 replaces
  the placeholder branch in `install_command` (`factory/cli/install.py:687`)
  with the container path while keeping the native `verify_controlplane` call
  at `:722` — the very block US6/T054 wires into. Its T038 prints into the
  report block at `factory/cli/init.py:809-823`, the "next, run:" shape US2 and
  US6 imitate, and its T039 grows `gather_init_facts` (`:1224`) and `run_check`
  (`:1344`) in the same neighbourhood as US5's `render_check` (`:1308`).
  Raced, these merge cleanly and behave wrongly. `spec.md` therefore carries
  `depends_on_landed: [104-install-brings-the-container-up-configured]`, which
  is the only mechanism that actually holds: the roadmap dispatches a `ready`
  spec on its own schedule, so a note here would reach no scheduler.
- **105 co-tenants `factory/cli/nouns/build.py` with US4, and no edge is
  drawn.** 105's T026 pins `_cli_revision` (`:741`) and `_skew_notice` (`:761`)
  byte-identical and its T028 adds a call at `:316`; US4 declares a new `ship`
  subparser near `:1522` and a new `ship_command`. The regions are far apart
  and neither story moves the other's, so the merge-group build is a sufficient
  gate — but **every `build.py` anchor in this plan is stale the moment 105
  lands**, which is why the top of this section says to re-open each one.
- 105 also touches `factory/workgraph/preflight.py`,
  `factory/workgraph/cli.py:119`, `factory/controlplane/verify.py` and the
  release workflow. Only `factory/workgraph/cli.py` overlaps this spec at all,
  and only as a *read* (trap 7's `:265` / `:305` anchors).
- Specs 087 and 099 are at draft and name none of these files.

`slice_contention` cannot see any of this: it compares slices *within* one
spec. Cross-spec collision is an operator's job, and this section is where it
was done.

## Dispatch hazards this epic's operator carries, not its implementers

Recorded here because they were reproduced today and they cost an epic each:

- **The landing PR's base comes from whatever branch the target repo has
  checked out**, not from configuration. Confirm the target repo sits on
  `ergane-buildout` before starting this epic.
- **A node worktree left by a dispatch under a different `target_repo` is
  silently reused**, and the mismatch surfaces only as a bare git refspec error
  *after* gates and judge have passed. Clear stale node worktrees before
  relaunching.
- **`--max-concurrent-nodes` above 1 kills nodes** with "Session ID already in
  use", surfaced misleadingly as `DETECT_FAILED` about a missing `stdout.log`;
  the tell is a 74-byte `stdout.log`. Keep the cap at 1 — including through
  `build ship`, whose `--max-concurrent-nodes` default must stay `1` like
  `start`'s (`factory/cli/nouns/build.py:1534-1542`, the `default=1` at
  `:1537`).
- **A hand-harvested PR title makes the landing invisible.**
  `factory/workgraph/landed.py:39` anchors the grammar on
  `<epic_id>/<node_id>: US<N> (#<pr>)`; a prose title makes the story invisible
  to `ergane spec landed` and to `--delta` forever.
- **Six stories at cap 1 is six serial dispatches.** Budget for that before
  starting, and note that US4 and US5 are the two that could be pulled forward
  independently if the epic has to be cut short.

## Verification the operator will run, independent of the gate

Everything below is outside what an implementer's sandbox can produce, which is
why trap 18 sends the implementer to a labelled seam capture and sends the real
thing here.

- **Run a real `ergane install` interactively**, against the real control plane
  and a repository with a real `gh` remote, and watch the closing
  demonstration end the transcript. This is the only run in which
  `_controlplane_probe` and `_forge_factory` are the real ones; the story's
  own tests rebind both (trap 19). Confirm the readiness report's red lines
  name commands that actually work, and that the step adds no perceptible time
  — if it does, something is probing twice.
- **Re-run install** and confirm it converges (findings §8 failure mode 7).
- **Check the blast radius by hand after the demonstration**: no new Temporal
  schedule, no new registry row, no leftover temporary directory.
- **Run `ergane spec new` cold** against a scratch repository and read the
  first `ergane spec validate` as a newcomer would. Does it teach or punish?
  That is the scaffold's whole purpose and the one thing no gate measures.
- **Hand it to a real first-time developer** if one is available, and watch
  where they stop reading.
- **`ergane build ship` a real spec to the pause and then decline it.** Confirm
  nothing was dispatched, that the compiled `workgraph.json` on disk is the one
  the summary described, and that every summary line names a model alias you
  recognise from your own persona registry.
