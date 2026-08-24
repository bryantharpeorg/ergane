# Tasks: a first spec scaffolds, validates and ships

**Spec**: `specs/106-a-first-spec-scaffolds-validates-and-ships/spec.md`
**Plan**: `specs/106-a-first-spec-scaffolds-validates-and-ships/plan.md`

Read the plan's traps before the first task. Five decide whether an attempt
lands. Trap 1: `_build_tasks_md` (`factory/doctor/scaffold.py:169`) emits no
per-story phase heading and its output fails the real validator — do not call
it and do not fix it. Trap 8: sentinels ride the existing `information` channel
(`factory/cli/nouns/spec.py:244`); no third severity, no restructured printer.
Trap 9: the derive gate lives in `_derive_command` (`:204`) and never inside
`derive_workgraph`, which `spec validate` itself calls at `:257`. Trap 10:
the install demonstration never calls `init_command` — `_schedule`
publishes a real Temporal schedule. Trap 19: the demonstration's readiness pass
reuses the findings install already computed and goes through the forge seam;
probing a second time is an LLM call and a network round trip inside a step
that trap 15 declares offline.

Trap 18 governs every verification task below: the judge sees the diff and the
criteria and nothing else, so each one commits **pasted output**. A criterion
that says "run X and observe Y" is unmet however true it is. Where the real
hardware is not reachable from an implementer's sandbox, the criterion is a
**seam capture** — the transcript produced with the named seam rebound — and it
says so in its own text; the real run is on the operator's list in the plan.

## Phase 1: User Story 1 — The scaffold generator emits a trio that validates

### Tests for this story (write FIRST, must fail)

- [ ] T001 [US1] (spec US1-S2) Write the generator's three returned texts into
      a `tmp_path` directory and drive
      `factory.cli.main.main(["spec", "validate", …, "--json"])` over it,
      asserting exit 0 and `document["findings"] == []`. **Run this against the
      unfixed tree first and capture the red** — a trio built from
      `_build_tasks_md` (`factory/doctor/scaffold.py:169`) fails with
      `[prompt_assembly] tasks.md declares no phase naming user story US1`.
      That red is half of what T009 pastes; without it the green proves
      nothing.
- [ ] T002 [P] [US1] (spec US1-S1) Structure assertions on the returned
      `spec.md` text: exactly three story slots; every heading matches
      `### User Story N - Title (Priority: PN)`; every story carries literal
      Given/When/Then `**Acceptance Scenarios**`; the `## Work Graph` fence
      carries an explicit `implements:` on every node; frontmatter reads
      `state: draft` and nothing else (trap 2).
- [ ] T003 [P] [US1] (spec US1-S1) Sentinel placement: at least one
      `ERGANE-TODO:` per mandatory blank, **none** inside the Work Graph fence,
      none inside a story heading, none in a task-id prefix. Assert by parsing
      the returned text, not by diffing a golden file.
- [ ] T004 [P] [US1] (spec US1-S2) Slice self-proof: for every node
      `derive_workgraph` produces from the returned trio, `task_slice_bounds`
      (`factory/workgraph/prompt.py:578`) returns bounds; and every scenario id
      the criteria parser mints from the returned `spec.md` — `<story_key>-S<n>`,
      minted at `factory/verify/criteria.py:355` — appears verbatim in the
      returned `tasks.md`, so the scaffold's first validate carries no
      scenario-coverage advisory.
- [ ] T005 [P] [US1] (spec US1-S2) No self-contention:
      `factory.workgraph.contention.named_files` (`factory/workgraph/contention.py:89`)
      over each generated task slice returns paths for the worked story only;
      the skeletal slots name none (trap 4).
- [ ] T006 [P] [US1] (spec US1-S3) The demonstration mode returns the worked
      story alone — no sentinel anywhere in the three texts, no skeletal slot —
      and `derive_workgraph` over it succeeds. US6 needs exactly this mode and
      discovering it late costs an attempt (trap 14).

### Implementation for this story

- [ ] T007 [US1] The generator: a public entry point in
      `factory/doctor/scaffold.py` beside `scaffold_spec` (`:24`), sharing
      `_sanitize_text` (`:52`) and `state: draft` (`:87`), taking the slug, the
      title and an **already-resolved** `path:line` anchor string, and emitting
      the three slots, the Work Graph fence and a `tasks.md` whose phase
      headings satisfy `_names_story` (`factory/workgraph/prompt.py:502`). It
      must not import or call `_build_tasks_md` (`:169`) — trap 1. It reads no
      filesystem and no repository: resolving the anchor is US2's job, and this
      module's docstring contract (`:8-11`) is text in, text out.
- [ ] T008 [US1] The `demonstration` mode on the same entry point, plus the
      module's two exports US3 consumes: the `ERGANE-TODO:` token itself and a
      pure `scan text → [(line_no, text)]` helper.

### Verification for this story

- [ ] T009 [US1] (spec US1-S1, US1-S2, US1-S3) Paste, committed in the diff:
      T001's red against the unfixed tree; the complete trio the generator
      returns for a fixed slug/title/anchor triple; the
      `ergane spec validate --json` document over it showing `"findings": []`
      with exit 0; and the demonstration mode's trio beside it, with a
      `grep -c ERGANE-TODO` of zero shown.

## Phase 2: User Story 2 — `ergane spec new` numbers, anchors and writes atomically

### Tests for this story (write FIRST, must fail)

- [ ] T010 [US2] (spec US2-S1) Numbering: given a specs root holding `001-…`,
      `007-…` and a numbered directory with **no** `spec.md`, the new directory
      is `008-<slug>`; an existing target directory is refused without writing;
      two directories claiming one number are refused rather than guessed
      (trap 3).
- [ ] T011 [P] [US2] (spec US2-S2) The anchor resolves: the `path:line` written
      into the scaffold names a file tracked in the fixture repository with at
      least that many lines, and
      `factory.workgraph.contention.named_files` over the worked story's text
      returns that path. A fixture repository with no eligible file makes the
      command refuse, naming what it looked for — never an unresolvable anchor.
- [ ] T012 [P] [US2] (spec US2-S3) Atomic-or-nothing: force the self-proof to
      fail (a deriver stub raising `DerivationError`) and assert the specs root
      gains no directory and no `.tmp-*` residue — the temporary directory is
      sited inside the specs root so the rename is same-filesystem
      (`factory/cli/doctor.py:557-559`).
- [ ] T013 [P] [US2] (spec US2-S4) The ending: stdout carries the literal
      `next, run:` followed by an indented, verbatim
      `ergane spec validate <dir> --target-repo <repo>`, in the shape the plan
      cites for `ergane init`'s existing report block. With `load_personas()`
      raising, or returning a registry without the persona the deriver defaults
      to (`factory/workgraph/derive.py:86`), the block also names
      `ergane install` (trap 5).
- [ ] T014 [P] [US2] (spec US2-S4) `--target-repo` is required and resolved
      with `must_exist=True`; the verb never falls back to
      `/srv/factory/targets/short-links` (trap 6). A missing repo is an
      `OperatorError` at the boundary naming the path.
- [ ] T015 [US2] (spec US2-S1, US2-S2) End to end against a fixture target
      repository: `factory.cli.main.main(["spec", "new", …])` then
      `main(["spec", "validate", …, "--json"])` over what it wrote, asserting
      exit 0 and `document["findings"] == []`.

### Implementation for this story

- [ ] T016 [US2] The anchor picker: enumerate the target repository's tracked
      files, keep those whose final segment satisfies `_FILENAME_RE`
      (`factory/workgraph/contention.py:56`) with an extension in
      `_BARE_EXTENSIONS` (`:63-68`), sort for determinism, take the first with
      enough lines, and read the file back to confirm the line resolves. Reuse
      that vocabulary; do not write a third path regex.
- [ ] T017 [US2] The verb: a `new` subparser in `_add_spec_parser`
      (`factory/cli/nouns/spec.py:89`) with `slug`, required `--target-repo`,
      `--specs-root` defaulting to `DEFAULT_SPECS_ROOT`, optional `--title`;
      and its handler — number, pick the anchor, call US1's generator, write
      into a `TemporaryDirectory(dir=specs_root, …)`, prove with
      `derive_workgraph` **and** `task_slice_bounds` per node, `rename` into
      place (`factory/cli/doctor.py:544-579`), then print the directory and the
      `next, run:` block.

### Verification for this story

- [ ] T018 [US2] (spec US2-S1, US2-S2, US2-S3, US2-S4) Paste, committed in the
      diff: the full `ergane spec new` transcript ending in the `next, run:`
      block; a listing of the specs root before and after showing the chosen
      number; the failed-self-proof run with the same listing proving nothing
      was written; and the `ergane spec validate --json` document over the
      created directory showing `"findings": []` with exit 0.

## Phase 3: User Story 3 — Sentinels gate derive, not validate

### Tests for this story (write FIRST, must fail)

- [ ] T019 [US3] (spec US3-S1) Over a fresh scaffold, one `spec validate` run
      carries both halves: exit 0, `findings` empty, the "…all pass" sentence
      printed **unchanged**, and every sentinel listed with `<document>:<line>`
      and the words "not ready to derive" on the `information` channel
      (`factory/cli/nouns/spec.py:244`, printed at `:421-426`). Assert on the
      `--json` document's `information` array and on the human transcript,
      naming which stream each half lands on.
- [ ] T020 [P] [US3] (spec US3-S1) The report grammar does not move: no third
      severity value exists; the label branch at `:393-396` is untouched;
      **both** all-pass sentences stay byte-identical — the clean one at
      `:409-410` (reached by the `else` at `:407`) and the
      `…; see advisory above` variant at `:403-405` (reached from
      `if has_advisory and not has_refusal` at `:401`), which is the one a spec
      carrying an advisory actually prints. Only the clean
      sentence is asserted anywhere today, once, at
      `tests/test_ergane_spec.py:525`; the advisory variant is asserted by
      **nothing**, which is why this task adds that assertion rather than
      relying on an existing one (trap 8). Assert it over a scaffold that has
      both a sentinel and a `slice_contention` advisory — the case where the
      `information` channel and the advisory line coexist. Also assert
      `"sentinels"` appears in `checked` and never in `skipped`, including when
      the graph fails to compile.
- [ ] T021 [P] [US3] (spec US3-S2) `spec derive` over a scaffold with
      sentinels exits non-zero naming **every** sentinel with its file:line and
      the verb that clears it; the same holds with `--delta`; and
      `<spec-dir>/workgraph.json` is not written or modified (trap 17).
- [ ] T022 [P] [US3] (spec US3-S2) With every sentinel removed, `spec derive`
      proceeds unchanged and writes the artifact — the same bytes the verb
      wrote before this story, over the same input.
- [ ] T023 [P] [US3] (spec US3-S1) The gate is at the verb, not the deriver:
      call `derive_workgraph` directly over sentinel-bearing text and assert it
      compiles; assert `spec validate` over the same scaffold does **not**
      refuse (`factory/cli/nouns/spec.py:257` is the reason this test exists);
      assert `factory/workgraph/delta.py`, `factory/cli/doctor.py:566`,
      `factory/doctor/cli.py:326` and the roadmap's derive path are unchanged
      (trap 9).

### Implementation for this story

- [ ] T024 [US3] In `factory/cli/nouns/spec.py`: a private helper reading the
      trio through US1's exported token and text scanner and returning
      `[(document, line, text)]`.
- [ ] T025 [US3] Wire it into `_validate_command` (`:231`): append each
      sentinel to `information` (`:244`) as `_ValidateFinding("sentinel", …)`,
      append `"sentinels"` to `checked` last and unconditionally, and print one
      summary line naming how many remain and that `ergane spec derive` will
      refuse until they are resolved. That summary line goes to **stderr**,
      immediately after the `information` loop at `:421-426` and therefore
      after the all-pass sentence that goes to stdout — the same stream the
      per-sentinel lines already use, so the transcript reads as one block.
      Change nothing else in the printer.
- [ ] T026 [US3] Gate `_derive_command` (`:204`) at its top, before delegating,
      with an `OperatorError` naming every sentinel. Nowhere else.
- [ ] T027 [US3] Grow `tests/test_prompt_assembly.py:254`'s exhaustive
      `checked` assertion by exactly the string `"sentinels"`. This is declared
      work: that list is asserted with `==` and is meant to stay exhaustive.

### Verification for this story

- [ ] T028 [US3] (spec US3-S1, US3-S2) Paste, committed in the diff: the
      single `spec validate` transcript showing structural acceptance and the
      sentinel list together, with its exit code and with stdout and stderr
      distinguished; the `--json` document's `checked`, `findings` and
      `information` arrays; the `spec derive` refusal naming each sentinel; and
      the same `spec derive` succeeding once the sentinels are resolved.

## Phase 4: User Story 4 — `build ship` collapses without hiding

### Tests for this story (write FIRST, must fail)

- [ ] T029 [US4] (spec US4-S1) With `start_command` stubbed at the module
      attribute, `ergane build ship <dir>` streams validate's full labeled
      output, then derive's, then a compiled-graph summary carrying node count,
      dispatch order and one `persona … model …` line per node — in that order,
      asserted on stream positions, not on substring presence alone.
      **Assert no summary line ends in a bare `model `**: a compiled `WorkNode`
      (`factory/workgraph/models.py:174-196`) has no `model_alias` field, so the
      alias comes from the persona registry, not from the node (trap 20).
      Ship's fixture is a hand-written spec directory, **never** a scaffold from
      `ergane spec new`: once US3 lands, a sentinel-bearing scaffold makes
      stage two refuse, and a ship test built on one would start failing for a
      reason that is not ship's.
- [ ] T030 [P] [US4] (spec US4-S1) The model half is resolved, not blank: with
      a persona registry declaring a model for the deriver's persona, the
      summary prints that alias verbatim; with a persona that declares none,
      the line prints the stated literal the plan names rather than an empty
      tail; with a persona missing from the registry the run never reaches the
      summary, because stage one already refused (`_check_personas`,
      `factory/cli/nouns/spec.py:464-480`).
- [ ] T031 [P] [US4] (spec US4-S1) The pause: without `--yes`, a declined
      confirmation returns `EXIT_USER`, prints a cancelled line, and the
      stubbed `start_command` was never called; `EOFError` reads as a decline;
      `--yes` dispatches with no prompt. Same primitive as
      `kill_command` (`factory/cli/nouns/build.py:871-881`).
- [ ] T032 [P] [US4] (spec US4-S2) A validate failure stops ship at stage one:
      that stage's full output is streamed, ship returns validate's code,
      derive is never called and `start_command` is never called. The same for
      a derive failure at stage two.
- [ ] T033 [P] [US4] (spec US4-S2) The empty-delta case: derive prints
      "nothing to build" and writes no artifact; ship refuses clearly naming
      the artifact path it expected rather than raising from `load_workgraph`.
      Ship computes that path the way derive does —
      `Path(args.output) if args.output else spec_dir / ARTIFACT_NAME`
      (`factory/workgraph/cli.py:305`) — so the two can never disagree about
      which file was just written.
- [ ] T034 [P] [US4] (spec US4-S1) No hand-built namespace: inspect ship's
      parsed namespace before dispatch and assert `promotion_persona`, `graph`,
      `max_concurrent_nodes`, `output` and `delta` are all present — the three
      that `start_command` reads by direct attribute
      (`factory/cli/nouns/build.py:589`, `:598`, `:632`) plus the two
      `derive_command` reads (trap 7). `--max-concurrent-nodes` defaults to
      `1`, like `start`'s.
- [ ] T035 [P] [US4] (spec US4-S1) `--target-repo` is required on `ship` and
      never defaults to `/srv/factory/targets/short-links` (trap 6): omitting
      it is an argparse refusal, not a stage-two death naming a path the
      operator never typed.
- [ ] T036 [P] [US4] (spec US4-S3) The constituent verbs are untouched:
      `tests/test_ergane_spec.py` and `tests/test_ergane_build.py` pass
      unmodified, and `tests/test_graph_paths_are_absolute.py:132` still
      imports `_derive_command` by its private name.

### Implementation for this story

- [ ] T037 [US4] Two thin **public** wrappers in `factory/cli/nouns/spec.py` —
      `validate_spec_command(args)` and `derive_spec_command(args)` —
      delegating to `_validate_command` (`:231`) and `_derive_command`
      (`:204`). The private names and their `set_defaults(run=…)` wiring stay
      exactly as they are.
- [ ] T038 [US4] The `ship` subparser beside `start`
      (`factory/cli/nouns/build.py:1522`), composing
      `add_promotion_persona_flag` and `add_landing_dial_flags` and declaring
      `--max-concurrent-nodes`, `--output`, `--delta`, required
      `--target-repo`, `--specs-root`, `--yes` and the positional `spec_dir`.
- [ ] T039 [US4] `ship_command`: stage banner → `validate_spec_command` →
      stage banner → `derive_spec_command` → resolve and check the artifact
      path → `load_workgraph`, resolve each node's model alias from
      `load_personas()` (`factory/config.py:219`, the same registry
      `_check_personas` reads) and print the summary → confirm unless `--yes` →
      set `args.graph` and return `start_command(args)`. Ship sets exactly one
      attribute on its own namespace, and stops at the first non-zero stage.

### Verification for this story

- [ ] T040 [US4] (spec US4-S1, US4-S2, US4-S3) Paste, committed in the diff:
      the full `ergane build ship` transcript through the pause with dispatch
      stubbed, showing both stages' labeled output and the graph summary with a
      non-empty model alias on every line; the declined-confirmation transcript
      with its exit code; the stop-at-validate-failure transcript; and the run
      of `tests/test_ergane_spec.py` and `tests/test_ergane_build.py` green
      with their file paths and counts visible.

## Phase 5: User Story 5 — Every non-passing readiness line names its fix

### Tests for this story (write FIRST, must fail)

- [ ] T041 [US5] (spec US5-S1) `render_check` (`factory/cli/init.py:1308`)
      given a profile with one blocking and one warning finding and a remedy
      table emits a runnable fix clause on each non-passing line, and leaves
      passing lines alone. A check name the table does not carry falls back to
      a stated line naming `ergane init --check` — a non-passing line with no
      fix text is the failure this story exists to prevent (trap 13).
- [ ] T042 [P] [US5] (spec US5-S2) With no remedy table supplied, the rendered
      text is **byte-identical to today's** — capture today's output for a
      fixture profile before the change and assert equality against it — so
      `ergane init --check`'s existing tests stay green untouched.

### Implementation for this story

- [ ] T043 [US5] An optional remedy mapping parameter on `render_check`
      (`factory/cli/init.py:1308`), defaulting to `None`, plus the fallback
      clause. One renderer — do not grow
      `factory/controlplane/verify.py:1127` `render_findings` a remedy column,
      and do not write a third renderer (trap 13). The table itself is US6's,
      supplied by the caller.

### Verification for this story

- [ ] T044 [US5] (spec US5-S1, US5-S2) Paste, committed in the diff: the
      rendered report for a fixture profile with a blocking finding, a warning
      finding, a passing finding and an unrecognised check name, showing the
      fix clause on each non-passing line; the same profile rendered with no
      remedy table beside today's output, byte-identical; and the green run of
      the existing `ergane init --check` tests with their file path and count.

## Phase 6: User Story 6 — Install ends mid-conversation

### Tests for this story (write FIRST, must fail)

- [ ] T045 [US6] (spec US6-S1) **Seam capture, and it says so in the paste.**
      Driven through `_FilePrompter` (`factory/cli/install.py:825`) with exactly
      two seams rebound — `verify_controlplane` at the install module attribute
      and `factory.cli.init._forge_factory` (`factory/cli/init.py:128`) — the
      closing step runs after
      `render_findings`, prints the readiness report, prints the demonstration
      spec's `spec validate` and `spec derive` output with the compiled graph
      shown, and ends with the literal `next, run:` block naming
      `ergane spec new`. The real interactive install on real hardware is the
      operator's run, listed in the plan; this test is what the judge can see.
- [ ] T046 [P] [US6] (spec US6-S1) **Neither of `check_repo`'s two live
      boundaries runs for real** — one test, one fixture, both halves of
      trap 19. (a) The closing step passes install's already-computed findings
      straight through: `check_repo(root, control_plane=(tuple(findings), None))`
      using the `findings` bound at `factory/cli/install.py:722`. Assert
      `factory.cli.init._controlplane_probe` (`factory/cli/init.py:139`) is
      never called during the closing step, and that the findings rendered in
      the readiness report are the same objects install already printed — a
      `control_plane=None` here re-runs the whole LLM/Temporal/memory/telemetry
      probe suite two lines after install just ran it. (b) `check_repo` then
      resolves a forge through `factory.cli.init._forge_factory` (`:128`) and
      `onboard_target_repo` (`factory/activities/merge_activities.py:564`,
      `:573`) calls `describe_repository()` and `landing_policy()` on it — real
      `gh` against a throwaway `git init` repository with no remote. Assert the
      closing step goes through that one seam, rebound to a stub, and that no
      second forge factory is introduced: the comment at
      `factory/cli/init.py:124-127` records nine tests dying the last time this
      file grew a duplicate.
- [ ] T047 [P] [US6] (spec US6-S1) Blast radius: the demonstration creates no
      Temporal schedule and no registry row — assert `_schedule`
      (`factory/cli/init.py:969`), `_register` (`:1036`) and
      `registry.register` are never called, and that the operator's registry
      file is byte-identical before and after. The temporary directory does not
      survive the call (traps 10, 15).
- [ ] T048 [P] [US6] (spec US6-S1) The demonstration spec derives: it is
      generated in US1's sentinel-free demonstration mode, so `spec derive`
      succeeds and a graph is printed (trap 14). A sentinel-bearing scaffold in
      the same position would refuse — assert that too, so the mode is
      load-bearing rather than incidental.
- [ ] T049 [P] [US6] (spec US6-S2) Skippable: a declined answer ends install
      cleanly, prints the **same** `next, run:` block, and runs no
      demonstration. An all-Enter `_FilePrompter` answer file does not hang
      (trap 16).
- [ ] T050 [P] [US6] (spec US6-S1) The demonstration never changes install's
      verdict: force it to raise, and assert install still returns
      `verify_controlplane`'s code with the failure reported, not swallowed.
- [ ] T051 [P] [US6] (spec US6-S1) `--non-interactive`
      (`factory/cli/install.py:761`) and `--from-file` (`:855`) never reach the
      closing step, and their endings at `:806-810` and `:900-904` are
      unchanged (trap 11).
- [ ] T052 [P] [US6] (spec US6-S1) Re-entry converges: running install twice
      against the same config leaves the second run's demonstration behaving
      identically, with no residue from the first (findings §8 failure mode 7).

### Implementation for this story

- [ ] T053 [US6] The module-level `_closing_demonstration(prompter, findings, …)`
      in `factory/cli/install.py`: ask; on accept, inside a
      `TemporaryDirectory`, `git init`, call `_write_scaffold`
      (`factory/cli/init.py:1074`) and **nothing else from init**; run
      `check_repo` (`:1285`) with `control_plane=(tuple(findings), None)` and
      the remedy table through US5's `render_check`; generate the demonstration
      spec through US1's generator; drive
      `factory.cli.main.main(["spec", "validate", …])` and
      `main(["spec", "derive", …])` (`factory/cli/main.py:174`); print the
      graph; end with the `next, run:` block. No dispatch, no LLM call, no
      network, no systemd. The remedy table US5's `render_check` takes is part
      of this task: the check-name → fixing-command mapping, with the stated
      fallback naming `ergane init --check` for a name it does not carry.
- [ ] T054 [US6] Call it from `install_command`'s interactive tail only
      (`factory/cli/install.py:720-724`), after `render_findings` and before
      `return`, passing the `findings` already bound at `:722` and without
      changing the returned code. If 104 has landed first, that tail now has a
      container branch beside the native one — re-open it before editing and
      attach to whichever branch still ends in `render_findings`.
- [ ] T055 [US6] Grow `tests/test_ergane_install_walkthrough.py:251-262`'s
      autouse fixture by one `monkeypatch.setattr` neutralising the closing
      step, so that file's walkthrough tests keep testing the interview
      (trap 12). Declared work, not tidying.

### Verification for this story

- [ ] T056 [US6] (spec US6-S1, US6-S2) Paste, committed in the diff, **labelled
      as a seam capture**: the full closing-step transcript from
      `verifying the control plane…` to the final `next, run:` line, including
      the readiness report with a remedied red line and the demonstration
      spec's compiled graph, produced with the control-plane and forge seams
      rebound; the declined-skip transcript showing the identical ending; and
      the before/after listing proving no schedule, no registry row and no
      surviving temporary directory. Name the rebound seams in the paste, so
      the judge is told what the transcript does and does not prove.
