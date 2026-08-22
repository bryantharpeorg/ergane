---
state: ready
# RELEASED draft -> ready 2026-08-22 ~8:25 AM CT at the operator's explicit
# ruling (Q&A in the operator session, after the review docket): he ACCEPTED
# US1's ruling against the finding's own proposed fix — disclosure, never
# retargeting — and chose the FULL four-story scope over the US1-only cut.
# The hold below is answered.
#
# RE-ANCHORED 2026-08-22 against 732ff88 before the flip. An exhaustive pass
# re-printed every citation in spec/plan/tasks (~200 anchors):
#   - ZERO broken constructs. US1's and US2's entire surfaces (cli/repo.py,
#     supervision/units.py, worktree.py, registry.py, config.py, locking.py,
#     the noun shims, test_ergane_repo_forget.py) are byte-identical to the
#     draft-time tree — those two stories needed no re-anchoring at all.
#   - factory/cli/roadmap.py drifted wholesale (+11/+32) when 081's landing
#     dials landed: pause command :310 -> :342, _connect :189 -> :200,
#     Client.connect :193 -> :204, and every render anchor. All updated. The
#     "no injectable client seam" premise RE-VERIFIED: Client.connect still
#     occurs exactly once. Trap 14 and FR-017 stand unchanged in force —
#     and note the irony: the silent-anchor-shift hazard trap 14 warned
#     about has now actually happened once, caused by 081, not by anyone
#     breaking a rule.
#   - factory/cli/nouns/build.py salvage surface drifted +129 (078/081):
#     load_workgraph :1263 -> :1392, salvage_command :1244 -> :1373, parser
#     :1512 -> :1645. Updated; FR-015's reasoning unaffected.
#   - The trap-3a stale-comment claim (units.py:78-80 vs :81) re-verified
#     still true; T017's four-name assertion still matches.
#
# THE ORIGINAL HOLD, kept for the record:
# HELD AT DRAFT deliberately. Drafted 2026-08-21 ~5:30 PM CT by an operator
# session from a field report, against a tree at dcc854d which is byte-identical
# to `origin/ergane-buildout`. It is held because US1 makes a ruling that
# contradicts the filed finding's own proposed fix, and the operator should read
# that ruling before an implementer is dispatched against it.
#
# WHAT THIS IS. On 2026-08-19 a consumer ran a full install -> build ->
# uninstall cycle on tharpebox against `bryantharpeorg/ergane-test` and could
# not get the host clean. Four separate defects came back from that one
# afternoon; all four live on the same verb surface, which is why they are
# drafted together rather than as four specs that would collide in the same
# files.
#
# THE MEASUREMENT, verified line by line on 2026-08-21:
#   - `factory/cli/repo.py:337` `runtime_root = runtime_root_for(entry.path)`
#     derives the deletion target from the registry entry's directory name.
#   - `factory/cli/repo.py:387` prints it:
#       print(f"emptied {runtime_root} ({emptied} entr{'y' if emptied == 1 else 'ies'})")
#   - In the field, `ERGANE_ROOT` was exported and had been used by the worker
#     all day. The command printed `emptied ... (0 entries)` against the
#     repo-default path and exited 0. 9.7MB of worktrees, transcripts and
#     databases survived in the root the worker had actually used. The operator
#     read success and believed the host was clean.
#   - `factory/supervision/units.py:478` `lines = [f"removed {len(self.removed)} file(s)"]`
#     -- the count-not-names defect in one line, while `:474` already carries
#     `removed: tuple[str, ...]` and `:479` already names `kept`.
#   - `ergane --help`, run live 2026-08-21, lists: install worker init spec
#     status build escalations answer doctor findings usage repo roadmap env
#     completion. **There is no `uninstall` noun.** `install --verify`
#     (`factory/cli/nouns/install.py:130`) and `init --check`
#     (`factory/cli/init.py:343`) exist; `uninstall --check` does not.
#
# THE RULING THAT HOLDS THIS AT DRAFT. The critical finding says
# `--clean-runtime` should resolve its target through `resolve_factory_root`,
# "overrides included". **This spec refuses that fix and specifies the opposite
# shape.** `factory/cli/repo.py:403-410` documents why the environment is not
# consulted for a deletion: on 2026-08-14 this repository lost its whole runtime
# root to a process acting on a root it had been handed rather than one it had
# derived, and `tests/test_ergane_repo_forget.py:287` is a committed test that
# pins the current behaviour on purpose. Adopting the override as the deletion
# target is that catastrophe re-armed. The defect is not the target; it is the
# silence about the disagreement.
#
# WHAT IS ALREADY FIXED, so no implementer rebuilds it:
#   - The path IS printed (`factory/cli/repo.py:387`). The finding asks for a
#     print that exists. Out of scope.
#   - A second runtime root the repo never migrated IS already disclosed
#     (`factory/cli/repo.py:388-393`). That is the precedent US1 copies, not
#     work US1 repeats.
#   - `worker uninstall`'s exact-inverse-of-install contract HELD in the field
#     and `UninstallReport.kept` is already rendered by name. Only `removed` is
#     reduced to a count.
#   - The open-epic refusals (`factory/cli/repo.py:436`,
#     `factory/supervision/units.py:539-545`) both held. Keep them.
#
# IF THE OPERATOR WANTS THIS CUT DOWN: US1 alone closes the critical and the
# other three stories can be dropped without unpicking it.
#
# Filed as, one critical and three warnings, all open:
#   uninstall/clean-runtime-cleans-the-repo-default-not-the-resolved-root  (critical)
#   uninstall/there-is-no-uninstall-verb                                   (warning)
#   uninstall/worker-uninstall-leaves-the-slice-loaded-and-names-nothing-it-removes
#                                                                          (warning)
#   uninstall/state-and-config-have-no-removal-path                        (warning)
#
# CROSS-SPEC CRITIC PASS APPLIED 2026-08-21 ~6:50 PM CT, against the same tree
# (dcc854d, byte-identical to `origin/ergane-buildout`). A critic read 083, 084
# and 085 together, plus the 081 exemplar, and returned one hard cross-spec
# collision and nine defects here. Every anchor written by this pass was
# verified by printing that exact line. The material rulings, all new since the
# draft:
#
#   - **HOW TEARDOWN COMPOSES ITS THREE STEPS -- RULED.** Teardown calls the
#     three existing argparse commands as they stand, behind one ordered step
#     table in teardown's own module, each record carrying a read-only survey
#     half and an acting half. It does **not** extract a library layer beneath
#     them. The draft named this problem in US3's Sizing and declined to solve
#     it; declining is what made SC-006 unprovable, because the seam it needs
#     has to exist somewhere. Putting it in teardown's own module is what makes
#     `--check` conclusive -- the acting half is never called at all -- with no
#     Temporal fake, no systemd fake and no filesystem fake required.
#   - **THE 085 COLLISION -- RULED, and this spec takes the avoiding side.**
#     `085-a-schedule-that-has-not-run-does-not-say-running`'s US3 rewrites two
#     lines of `factory/cli/roadmap.py` (`:464` and `:480`). Both stories sit at
#     the tail of their chains, so they land in the same window if the two epics
#     run together. `factory/cli/roadmap.py` has no injectable client seam --
#     `_connect()` at `:200` calls `Client.connect` inline at `:204` -- so an
#     implementer making step one testable will reach for exactly that file.
#     **This spec does not edit it.** Plan trap 14 is the full account.
#   - **US3 GAINS A CONTROL** (US3-S6 / FR-017 / SC-008). It was the only story
#     in the batch without one, while its implementation composes three live
#     call paths.
#   - **TRAP 8 AND THE DRAFT'S T034 MADE REAL** (FR-018 / US3-S7 / SC-009, now
#     tasks T031 and T037). "Do design so that the process does not saw its own
#     branch" was a sentiment with no mechanism, no anchor and no FR behind the
#     task that cited it. It is now a containment check against the
#     `install_root` `resolve_layout()` derives at
#     `factory/supervision/units.py:182` and the interpreter it derives at
#     `:186`, taken before any step acts.
#   - **FR-013 WAS UNFALSIFIABLE FROM A DIFF** -- "as prominently as" is a
#     judgement about presentation. It now names the rendering rule: one
#     labelled kept line per surviving path, in the same block as the removed
#     lines, in the shape `factory/supervision/units.py:479` already renders.
#   - **FR-015 NAMED A COMMAND THAT CANNOT ANSWER IT.** `ergane build salvage`
#     loads a compiled graph (`factory/cli/nouns/build.py:1392`) and reports one
#     epic's nodes; it does not enumerate a host's refs. Teardown prints
#     `git for-each-ref refs/heads/factory/` and `git for-each-ref refs/salvage/`
#     verbatim instead.
#   - **FR-009 RESTATED ITS OWN STORY TITLE** and now constrains what an
#     implementer could get wrong: the discovery path, and the single-step-table
#     rule that stops the printed plan and the performed sequence diverging.
#
# US1 and US2 are unchanged by this pass. The critic rated both as strong as the
# exemplar's, and the cut-down option above still stands: US1 alone closes the
# critical.
#
# BOOKKEEPING for anyone comparing against the draft: FR count 16 -> 18
# (FR-017, FR-018 added; FR-009, FR-010, FR-013, FR-015 rewritten). SC count
# 9 -> 11, and US3's two new criteria were *inserted* as SC-008 and SC-009 to
# keep the criteria in story order, so the draft's SC-008 and SC-009 are now
# SC-010 and SC-011. Task count 47 -> 52, and US3 gained four tasks, so every
# US3 task from the draft's T031 on and every US4 task is renumbered. Nothing
# here has landed, so nothing renumbered was immutable. Every anchor written by
# this pass -- 26 distinct (file, line) pairs new to this trio -- was verified by
# printing that exact line with `sed -n '<n>p'`, and no line number was derived
# by applying an offset to another.
---

# Feature Specification: teardown is a verb that names what it removed

## The gap, stated precisely

Ergane can be installed by one command and cannot be removed by any. Taking it
off a host takes three tools and four hand-ordered steps that a consumer had to
reverse-engineer from `--help` output, and every step of that sequence reports
in a way the operator cannot audit:

- `repo forget --clean-runtime` empties a root derived from the registry entry
  and says so, while the root the worker actually used — the one `ERGANE_ROOT`
  named — is neither emptied nor mentioned. When the derived root is already
  empty the output is `emptied <path> (0 entries)` and exit 0: a success message
  for a deletion that removed nothing, in a shell where 9.7MB of state was live.
- `worker uninstall` says `removed 6 file(s)` and names none of them, and
  leaves `ergane.slice` loaded and active until a hand-run stop and
  `daemon-reload`.
- `~/.local/state/ergane` and `~/.config/ergane/config.toml` have no removal
  path at all, and a `config.toml.lock` outlives everything.

The through-line is not that the wrong thing is deleted. It is that **the output
does not distinguish "removed it" from "did not look there."**

## The rule this spec is asking for

**A verb that removes things names every thing it removed, names every thing it
deliberately did not, and refuses rather than report success for an act it could
not meaningfully perform.**

## What this spec does not change

- **What `--clean-runtime` deletes.** It keeps deriving its target from the
  registry entry's path (`factory/cli/repo.py:337`, `runtime_root_for` at
  `:400`). The environment does not select what is deleted, now or ever. The
  committed test at `tests/test_ergane_repo_forget.py:287` stays green.
- **The printed path.** `factory/cli/repo.py:387` already names the root it
  emptied. Nobody rebuilds that line.
- **The legacy-root disclosure** at `factory/cli/repo.py:388-393`. It is the
  model for US1's new disclosure, not a thing to replace.
- **`ENABLE_TARGETS`** (`factory/supervision/units.py:81`). The slice is
  deliberately not enabled — `:74-77` explains why — and adding it there changes
  `install`, which is not what any of these findings reported.
- **The refusals that held.** `_refuse_while_epics_run`
  (`factory/cli/repo.py:436`), `_refuse_unsafe_removal` (`:458`), the open-epic
  refusal in `uninstall` (`factory/supervision/units.py:539-545`), and the
  export-inside-the-root refusal (`factory/cli/repo.py:424`).
- **The ordering contract** in `repo_forget_command`'s docstring
  (`factory/cli/repo.py:307-323`): every refusal before any act, `--export`
  before `--clean-runtime`, `--clean-runtime` last. This spec adds a refusal to
  the front of it and changes nothing else about it.
- **`install` and `init`.** This spec builds teardown. It does not touch the
  interview, the walkthrough, or what install writes.
- **`factory/cli/roadmap.py`.** Teardown *imports* `roadmap_pause_command`
  (`factory/cli/roadmap.py:342`) and edits nothing in that module. Spec
  `085-a-schedule-that-has-not-run-does-not-say-running` is rewriting
  `factory/cli/roadmap.py:464` and `factory/cli/roadmap.py:480` in the same
  window, and that file has no injectable Temporal client seam to borrow, which
  is exactly the reason an implementer would open it. The seam this spec needs
  lives in teardown's own step table instead. The plan's trap 14 is the full
  account, and it is scope, not a footnote.
- **The signatures of the three commands teardown composes.**
  `roadmap_pause_command` (`factory/cli/roadmap.py:342`), `repo_forget_command`
  (`factory/cli/repo.py:307`) and `uninstall()`
  (`factory/supervision/units.py:528`) keep the shapes and injection seams they
  have today. FR-017 is the control that says so.

## User Scenarios & Testing

### User Story 1 - `--clean-runtime` says which root it did not clean (Priority: P1)

As an operator emptying a departing repository's runtime state, I am told when
the root this command deletes is not the root my processes have been using, and
I am refused rather than congratulated when the deletion could not have done
anything.

**Why this priority**: P1, and it is the whole critical. Silent wrong-target
success is the failure mode: the operator believes the host is clean and it is
not.

**Independent Test**: export `ERGANE_ROOT` at a populated decoy, run
`repo forget --clean-runtime` against a registered repo, and read the output for
the decoy's path.

**Acceptance Scenarios**:

1. **Given** `ERGANE_ROOT` or `FACTORY_ROOT` set to a path that is not the
   registry entry's derived runtime root, **When** `--clean-runtime` runs,
   **Then** the output names that other path, says an environment override
   produced it, and names the variable that supplied it — proven by a committed
   test asserting all three appear in stdout. The resolver already returns the
   triple (`factory/workgraph/worktree.py:170`); nothing needs to be inferred.
2. **Given** the same override, **When** the command finishes, **Then** the
   root it emptied is still the entry-derived one and the override's path is
   untouched — proven by a committed test asserting the decoy's files survive.
   **This is the control**, and it is the point of the whole story: the fix is
   disclosure, never retargeting.
3. **Given** an environment override in force **and** an entry-derived root
   holding nothing to empty, **When** `--clean-runtime` runs, **Then** the verb
   refuses before deleting the schedule or the registry entry, naming both
   roots — proven by a committed test asserting exit is non-zero, both paths
   appear in the refusal, the registry entry still resolves, and the schedule
   still exists. This is the field case byte for byte: `(0 entries)` and exit 0
   is the output an operator cannot tell from success.
4. **Given** no override set at all, **When** `--clean-runtime` runs against a
   populated root, **Then** the output is what it is today — the emptied line at
   `factory/cli/repo.py:387` and nothing added — proven by a committed test
   asserting no disagreement line is printed. **The second control**: a
   disclosure that fires when there is nothing to disclose is noise, and noise is
   how the legacy-root line would stop being read.
5. **Given** a repo that never migrated, so a second `.factory` root exists,
   **When** `--clean-runtime` runs, **Then** the existing legacy disclosure at
   `factory/cli/repo.py:388-393` still prints — proven by a committed test. Two
   disclosures must be able to coexist without either swallowing the other.

---

### User Story 2 - `worker uninstall` prints its manifest and leaves nothing loaded (Priority: P1)

As an operator removing the supervised units, I can read exactly which units
were stopped, disabled and deleted, by name, and nothing install pulled in is
still loaded when the command returns.

**Why this priority**: P1. The exact-inverse-of-install contract held in the
field; what failed was the audit. A teardown you cannot audit is one you re-run
by hand.

**Independent Test**: run `worker uninstall` against a fake systemd runner and
read the rendered report for each unit name.

**Acceptance Scenarios**:

1. **Given** an installation whose manifest records every generated file,
   **When** `worker uninstall` runs, **Then** the report names each removed file
   on its own line instead of a count — proven by a committed test asserting each
   name appears in the render. The names are already on the object
   (`factory/supervision/units.py:474`); only `render()` at `:478` throws them
   away.
2. **Given** the same run, **When** the report is rendered, **Then** it says for
   each unit which of stop, disable and remove was performed — proven by a
   committed test. `removed 6 file(s)` is unauditable because deletion and
   deactivation are different acts and one line reported both.
3. **Given** `ergane.slice` written by install
   (`factory/supervision/units.py:259`), **When** `worker uninstall` runs,
   **Then** the slice is stopped and the stop is named in the report — proven by
   a committed test asserting the systemd command sequence the fake runner
   received. The slice surviving as loaded/active is what forced the hand-run
   stop.
4. **Given** this story landed, **When** the enabled-unit set is read, **Then**
   `ENABLE_TARGETS` is unchanged — proven by a committed test naming all four of
   `ergane-worker.service`, `ergane-bridge.service`, `ergane-temporal.service`,
   `ergane-probe.timer`. **The control.** Fixing uninstall by changing install is
   the wrong repair, and `factory/supervision/units.py:74-77` says why.
5. **Given** an epic in flight, **When** `worker uninstall` runs, **Then** it
   refuses and stops nothing — proven by a committed test asserting the fake
   runner received no commands. `factory/supervision/units.py:539-545` holds
   today; a story that reorders the stops must not move the refusal off the
   front.

---

### User Story 3 - `ergane uninstall` owns the ordering (Priority: P1)

As an operator taking Ergane off a host, one verb performs teardown in the order
that is safe, and `--check` tells me what it would do without doing any of it.

**Why this priority**: P1. Four hand-ordered steps discoverable only by `--help`
spelunking is the finding; the ordering is knowledge the tool has and the
operator had to reconstruct.

**Independent Test**: run `ergane uninstall --check` on a host with a registered
repo and installed units, and read the plan it prints.

**Acceptance Scenarios**:

1. **Given** a host with dispatch running, registered repositories and installed
   units, **When** `ergane uninstall` runs, **Then** it performs teardown in the
   declared order — pause dispatch, forget repositories, stop and remove units —
   and names each step as it completes — proven by a committed test asserting the
   call order.
2. **Given** the same host, **When** `ergane uninstall --check` runs, **Then**
   it prints the same plan and performs none of it — proven by a committed test
   that substitutes a recording step table and asserts that no step's acting
   half was ever called, alongside assertions that nothing was written, removed,
   stopped or signalled. **The seam that produces that evidence is teardown's
   own step table, not a fake for any of the three commands** — `--check` is
   conclusive because the acting half is unreachable on that path, which needs
   no Temporal client fake and cannot get one: `factory/cli/roadmap.py:200`
   connects inline at `:204`. `init --check` (`factory/cli/init.py:343-345`) and
   `install --verify` (`factory/cli/nouns/install.py:130-132`) are the two shapes
   to match for the flag itself.
3. **Given** a step with nothing to do — no repositories registered, no units
   installed — **When** teardown runs, **Then** that step says so by name rather
   than being silent — proven by a committed test. A skipped step and a step that
   ran are indistinguishable from silence, which is the same defect US1 closes.
4. **Given** a step that refuses — an epic in flight, a control plane that
   cannot be reached — **When** teardown runs, **Then** the verb stops before the
   next step acts, names which step refused, and names what has already been done
   — proven by a committed test. A half-teardown the operator cannot bound is
   worse than one that was refused.
5. **Given** dispatch that cannot be paused because no owner can be named,
   **When** teardown runs, **Then** that is a refusal and not a skipped step —
   proven by a committed test. `roadmap pause`
   (`factory/cli/roadmap.py:342-363`) reports success when it signalled a run it
   could not establish ownership of, and continuing past that is how a schedule
   goes on dispatching into a host being dismantled.
6. **Given** this story landed, **When** `ergane roadmap pause`,
   `ergane repo forget` and `ergane worker uninstall` are invoked directly
   rather than through teardown, **Then** each behaves exactly as it does today
   — proven by a committed test asserting that `repo_forget_command`
   (`factory/cli/repo.py:307`) still takes one `argparse.Namespace` and still
   resolves its Temporal client through the module attribute at
   `factory/cli/repo.py:93` that `tests/test_ergane_repo_forget.py:90` replaces,
   that `uninstall()` still honours its `open_epics` parameter
   (`factory/supervision/units.py:532`) and its `run` parameter (`:531`), and
   that `roadmap_pause_command` (`factory/cli/roadmap.py:342`) still pauses the
   schedule when the roadmap is schedule-owned. **The control.** This story
   composes three live call paths, and the failure it exists to catch is a
   teardown that works because the commands beneath it were reshaped to suit
   it — which would break `ergane repo forget` and `ergane worker uninstall` for
   every operator who never runs teardown at all.
7. **Given** a step whose removal target contains the installation this process
   is running from — the `install_root` `resolve_layout()` derives at
   `factory/supervision/units.py:182`, or the directory holding the interpreter
   it derives at `:186` — **When** teardown runs, **Then** it refuses before any
   step acts and names the containing path and the reason — proven by a
   committed test asserting a non-zero exit, that path in the message, and that
   nothing was removed. `install/restarting-the-worker-deletes-the-operator-cli`
   is an open critical of this family; this refusal *bounds* teardown, it does
   not close that finding.

---

### User Story 4 - Teardown names what it kept as loudly as what it removed (Priority: P2)

As an operator, I can remove Ergane's state, I keep my config and secrets unless
I ask otherwise, and I am told in both cases exactly what survives.

**Why this priority**: P2. It is the last mile of the same field report, and it
carries the one judgement the operator must not have made for them: config and
secrets are expensive to recreate, state is not.

**Independent Test**: run teardown twice against a seeded state home and config
directory, once bare and once with `--purge`, and diff what survives.

**Acceptance Scenarios**:

1. **Given** a populated state home and a written config, **When**
   `ergane uninstall` runs without `--purge`, **Then** both survive and the
   report carries one labelled kept line per surviving path, in the same block
   as the removed lines — the shape `UninstallReport.render` already uses for
   `kept` at `factory/supervision/units.py:479` — proven by a committed test
   asserting the files exist and that each path appears on a kept-labelled line
   of that block.
2. **Given** the same, **When** `ergane uninstall --purge` runs, **Then** the
   state home's contents are removed, the config is still kept, and both facts
   are named — proven by a committed test. **The control**: `--purge` removes
   state, not credentials, and a test that only checks the removal cannot tell
   the difference.
3. **Given** a lock file a prior run left beside the registry or the config,
   **When** teardown removes state, **Then** the lock file goes with it —
   proven by a committed test asserting no `.lock` sibling survives.
   `factory/locking.py:68` creates the lock with `O_CREAT` and
   `factory/locking.py:82-85` unlocks (`:83`) and closes (`:85`) without ever
   unlinking, which is why `config.toml.lock` outlived the field teardown.
4. **Given** a repository carrying `factory/<epic>/<node>` branches
   (`factory/workgraph/worktree.py:238`) and refs under `refs/salvage/`
   (`factory/workgraph/worktree.py:480`), **When** teardown runs, **Then** it
   prints a count for each of the two namespaces and prints, verbatim, the two
   commands that list them — `git for-each-ref refs/heads/factory/` and
   `git for-each-ref refs/salvage/` — and removes neither — proven by a
   committed test asserting the counts, both command strings, and the refs'
   survival. It does **not** name `ergane build salvage`: that verb loads a
   compiled graph (`factory/cli/nouns/build.py:1392`) and reports one epic's
   nodes, so it cannot answer what is on the host. Salvage refs are evidence;
   leaving them is defensible, leaving them unmentioned is not, and pointing at
   a command that will not list them is worse than either.
5. **Given** the same repository, **When** teardown runs with `--scrub-refs`,
   **Then** those refs are removed and named — proven by a committed test
   asserting both.

## Requirements

### Functional Requirements

- **FR-001**: `--clean-runtime` MUST keep deriving its deletion target from the
  registry entry's path alone; no environment variable may select what is
  deleted.
- **FR-002**: When `resolve_factory_root()` returns a root other than the
  entry-derived one, `--clean-runtime` MUST name that other root, state that an
  environment override produced it, and name the variable that supplied it.
- **FR-003**: `--clean-runtime` MUST refuse, before deleting the schedule or the
  registry entry, when an environment override is in force and the entry-derived
  root has nothing to empty; the refusal MUST name both roots and a remedy.
- **FR-004**: With no override in force, `--clean-runtime`'s output MUST be
  unchanged, and the existing legacy-root disclosure MUST keep printing.
- **FR-005**: `worker uninstall` MUST name every file it removed, one per line,
  and MUST NOT report a bare count.
- **FR-006**: `worker uninstall` MUST report, per unit, which of stop, disable
  and remove it performed.
- **FR-007**: `worker uninstall` MUST stop `ergane.slice` and MUST name the stop,
  while leaving `ENABLE_TARGETS` unchanged.
- **FR-008**: `worker uninstall`'s open-epic refusal MUST still precede every
  systemd command.
- **FR-009**: The `uninstall` noun MUST be a module under `factory/cli/nouns/`
  that the discovery loop at `factory/cli/main.py:65` finds with no registration
  anywhere else, and the order it performs — pause dispatch, forget
  repositories, stop and remove units — MUST come from a single ordered step
  table that both `--check` and a real run read, so the printed plan and the
  performed sequence cannot diverge.
- **FR-010**: `ergane uninstall --check` MUST print the plan a real run would
  follow and MUST write, remove, stop and signal nothing; the acting half of
  every step MUST be unreachable on the `--check` path, proven by substituting a
  recording step table and asserting no step acted.
- **FR-011**: A teardown step with nothing to do MUST say so by name.
- **FR-012**: A refused step MUST stop the verb before the next step acts, and
  the refusal MUST name which step refused and what has already been done.
- **FR-013**: `ergane uninstall` MUST keep the control-plane config
  (`resolve_config_path()`, `factory/controlplane/config.py:201`) and any
  secrets beside it by default, and its report MUST carry one labelled kept line
  per surviving path in the same block as the removed lines — the shape
  `factory/supervision/units.py:479` already renders for `kept` — so that a kept
  path and a removed path are told apart by their label rather than by one of
  them being absent.
- **FR-014**: `ergane uninstall --purge` MUST remove the state home's contents
  including lock-file siblings, and MUST still keep the config.
- **FR-015**: `ergane uninstall` MUST print a count of the git refs it does not
  remove, one count per namespace — `factory/<epic>/<node>` branches
  (`factory/workgraph/worktree.py:238`) and everything under `refs/salvage/`
  (`factory/workgraph/worktree.py:480`) — and MUST print, verbatim, the two
  commands that list them: `git for-each-ref refs/heads/factory/` and
  `git for-each-ref refs/salvage/`. It MUST NOT name `ergane build salvage`,
  which loads a compiled graph (`factory/cli/nouns/build.py:1392`) and reports
  one epic's nodes rather than a host's refs.
- **FR-016**: `ergane uninstall --scrub-refs` MUST remove those refs and name
  them; without it they MUST survive.
- **FR-017**: The three commands teardown composes MUST keep the signatures and
  injection seams they have today: `roadmap_pause_command`
  (`factory/cli/roadmap.py:342`) and `repo_forget_command`
  (`factory/cli/repo.py:307`) MUST still take one `argparse.Namespace`,
  `repo_forget_command` MUST still resolve its Temporal client through the
  module attribute at `factory/cli/repo.py:93`, and `uninstall()` MUST still
  accept `run` (`factory/supervision/units.py:531`) and `open_epics` (`:532`).
  `factory/cli/roadmap.py` MUST NOT be edited by this spec.
- **FR-018**: `ergane uninstall` MUST refuse, before any step acts, any step
  whose removal target contains the installation this process is running from —
  the `install_root` `resolve_layout()` derives at
  `factory/supervision/units.py:182` or the directory holding the interpreter it
  derives at `:186` — and the refusal MUST name the containing path. No flag may
  override it.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
  persona: opus-closer
US2:
  depends_on: []
  implements: [FR-005, FR-006, FR-007, FR-008]
  persona: opus-closer
US3:
  depends_on: []
  depends_on_merged: [US1, US2]
  implements: [FR-009, FR-010, FR-011, FR-012, FR-017, FR-018]
  persona: opus-closer
US4:
  depends_on: []
  depends_on_merged: [US3]
  implements: [FR-013, FR-014, FR-015, FR-016]
  persona: opus-closer
```

US1 and US2 touch disjoint files — `factory/cli/repo.py` and
`factory/supervision/units.py` — and run in parallel. US3 calls both, so its
merge-edges are logic: its `--check` must render US1's disagreement line and
US2's manifest, and neither exists until they land. US4's edge to US3 is pure
contention — it edits the noun module and the teardown module US3 creates, and
needs their lines to have stopped moving.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Paste `repo forget --clean-runtime` run with `ERGANE_ROOT` set to
  a populated decoy, showing the disagreement line naming the decoy, the
  variable, and the emptied entry-derived root.
- **SC-002**: Paste the control: the same command with no override set, showing
  output byte-identical to today's.
- **SC-003**: Paste the field case refused — an override in force over an empty
  entry-derived root — with the non-zero exit, both paths, and evidence the
  registry entry survived.
- **SC-004**: Paste `worker uninstall`'s report naming every removed file and
  every unit's stop, disable and remove.
- **SC-005**: Paste the systemd command sequence a fake runner recorded,
  showing `ergane.slice` stopped, and paste the `ENABLE_TARGETS` control showing
  all four names unchanged.
- **SC-006**: Paste `ergane uninstall --check` output and, beside it, the
  recording step table the test substituted, showing it empty — no step's acting
  half was called — together with the assertions that nothing was written,
  removed, stopped or signalled. The step table is the seam; a paste that only
  shows the plan proves the plan, not the inertness.
- **SC-007**: Paste a teardown stopped by a refused step, showing which step
  refused and what had already been done.
- **SC-008**: Paste the control: `ergane roadmap pause`, `ergane repo forget`
  and `ergane worker uninstall` each invoked directly after this story, beside
  the same three before it, showing the behaviour and the seams unchanged —
  including `repo_forget_command` still driven through the module attribute at
  `factory/cli/repo.py:93` and `uninstall()` still driven through `open_epics`.
- **SC-009**: Paste the self-removal refusal: a step whose removal target
  contains `resolve_layout()`'s `install_root`, showing the non-zero exit, the
  containing path in the message, and evidence nothing was removed.
- **SC-010**: Paste the two teardown runs side by side — bare and `--purge` —
  showing state removed in the second, config kept in both, and each surviving
  path on its own labelled kept line in the same block as the removed lines.
- **SC-011**: Paste the ref enumeration with a count per namespace and both
  `git for-each-ref` commands verbatim, once showing the refs surviving and once
  showing them removed under `--scrub-refs`.

## Assumptions

- `resolve_factory_root()` is the only resolver the worker's dispatch path
  consults for the runtime root. Verified 2026-08-21 by reading its callers in
  `factory/activities/`, `factory/doctor/` and `factory/cli/`; if an implementer
  finds a dispatch path resolving the root some other way, that is in scope and
  belongs in the diff.
- The critical was **not** independently reproduced on this box. The artifacts
  (`~/code/ergane-build-feedback.md`) live on tharpebox. Every line number in the
  plan was verified here; the field narrative was not.
- `ergane uninstall` *offering* to remove the tool that is executing it is out
  of scope. `install/restarting-the-worker-deletes-the-operator-cli` is a
  separate open critical and this spec does not close it. What this spec does do
  is **bound** the hazard: FR-018 refuses any step whose removal target contains
  this installation, detected against the two values `resolve_layout()` already
  derives (`factory/supervision/units.py:182` and `:186`). That is a check, not
  a fix — the finding stays open.
- Whether teardown should offer to remove the `uv tool` installation at all is
  left unanswered. The four steps this spec orders are the ones the factory
  itself put on the host.
- The state home resolves through `factory/registry.py:159`
  (`resolve_state_home`) and the config through
  `factory/controlplane/config.py:201` (`resolve_config_path`). Both honour env
  overrides, and for a *removal* that is the same hazard US1 rules on. FR-014's
  implementer must decide and state which root `--purge` empties, using US1's
  ruling as the precedent.
