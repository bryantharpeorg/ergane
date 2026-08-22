# Tasks: teardown is a verb that names what it removed

**Spec**: `specs/083-teardown-is-a-verb-that-names-what-it-removed/spec.md`
**Plan**: `specs/083-teardown-is-a-verb-that-names-what-it-removed/plan.md`

Read the plan's traps before the first task. Four decide whether an attempt
lands. Trap 1: **do not adopt the environment override as the deletion target** —
the filed finding asks for exactly that and the finding is wrong, and
`tests/test_ergane_repo_forget.py:287` is a committed test that will tell you so.
Trap 2: **the path is already printed** at `factory/cli/repo.py:387`, so a diff
that adds a path print has closed nothing. Trap 3: **do not add `SLICE_UNIT` to
`ENABLE_TARGETS`** — that changes install, and US2-S4 is the control that proves
install did not move. Trap 14 (US3 only): **do not edit
`factory/cli/roadmap.py`** — spec 085's US3 is rewriting
`factory/cli/roadmap.py:432` and `factory/cli/roadmap.py:448` in the same
landing window, and the plan's "The ruling on composition" is why US3 needs no
edit there.

## Phase 1: User Story 1 — `--clean-runtime` says which root it did not clean

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-002) In
      `tests/test_clean_runtime_names_the_root_it_did_not_clean.py`, assert that
      with `ERGANE_ROOT` set to a populated decoy, `repo forget --clean-runtime`
      prints the decoy's path, says an environment override produced it, and
      names the variable. The resolver already returns all three
      (`factory/workgraph/worktree.py:165-170`).
- [ ] T002 [P] [US1] (spec US1-S2, FR-001) **The control.** Assert the decoy's
      files survive and the entry-derived root is the one emptied. Retargeting
      the deletion is the failure this test exists to catch (trap 1).
- [ ] T003 [P] [US1] (spec US1-S3, FR-003) Assert that an override in force over
      an entry-derived root with nothing to empty is refused: non-zero exit, both
      paths in the refusal, registry entry still resolving, schedule still
      present. The refusal is taken before any act (trap 4).
- [ ] T004 [P] [US1] (spec US1-S4, FR-004) **The second control.** Assert that
      with no override set, stdout carries no disagreement line and matches
      today's output (trap 6).
- [ ] T005 [P] [US1] (spec US1-S5, FR-004) Assert the legacy-root disclosure at
      `factory/cli/repo.py:388-393` still prints for a repo that never migrated,
      and that it coexists with the override line.
- [ ] T006 [P] [US1] (FR-001, trap 1) Run
      `tests/test_ergane_repo_forget.py::test_clean_runtime_empties_the_entrys_root_and_not_the_environments`
      and confirm it is green. **Do not edit that file.**

### Implementation for this story

- [ ] T007 [US1] (FR-002) Compare `runtime_root_for(entry.path)`
      (`factory/cli/repo.py:337`) against `resolve_factory_root()`'s root, using
      the imports already present at `factory/cli/repo.py:69-70`, and disclose a
      disagreement in the shape of `:388-393`.
- [ ] T008 [US1] (FR-003) Add the refusal beside the existing one at
      `factory/cli/repo.py:344-345`, not down at `:385`. No escape flag — the
      argument against one is in `:458`'s docstring (trap 5).
- [ ] T009 [US1] (FR-001) Leave `factory/cli/repo.py:337` and `runtime_root_for`
      (`:400-421` — the whole function, *including* the body at `:415-421` that
      picks `.ergane/` over `.factory/`; `:414` is only where its docstring ends)
      exactly as they are.
- [ ] T010 [US1] (FR-004) Leave the emptied line at `factory/cli/repo.py:387`
      and the legacy branch at `:388-393` unchanged (trap 2).

### Verification for this story

- [ ] T011 [US1] (SC-001) Paste the run with a populated decoy, showing the
      disagreement line naming the decoy, the variable, and the emptied
      entry-derived root.
- [ ] T012 [US1] (SC-002) Paste the control **both ways**: today's output and the
      post-change output with no override, so the judge can see they match
      (trap 12).
- [ ] T013 [US1] (SC-003) Paste the field case refused: non-zero exit, both
      paths, and evidence the registry entry survived.

## Phase 2: User Story 2 — `worker uninstall` prints its manifest and leaves nothing loaded

Runs in parallel with US1: disjoint files.

### Tests for this story (write FIRST, must fail)

- [ ] T014 [P] [US2] (spec US2-S1, FR-005) In
      `tests/test_worker_uninstall_prints_its_manifest.py`, assert the rendered
      report names each removed file on its own line and carries no bare count.
      The names are already on the dataclass at
      `factory/supervision/units.py:474` (trap 11).
- [ ] T015 [P] [US2] (spec US2-S2, FR-006) Assert the report says, per unit,
      which of stop, disable and remove was performed.
- [ ] T016 [P] [US2] (spec US2-S3, FR-007) Assert the systemd command sequence a
      fake runner received includes a stop of `ergane.slice`
      (`factory/supervision/units.py:56`), issued after the enabled units are
      disabled at `:549-554`.
- [ ] T017 [P] [US2] (spec US2-S4, FR-007) **The control.** Assert
      `ENABLE_TARGETS` (`factory/supervision/units.py:81`) still holds exactly
      `ergane-worker.service`, `ergane-bridge.service`,
      `ergane-temporal.service`, `ergane-probe.timer` (trap 3).
- [ ] T018 [P] [US2] (spec US2-S5, FR-008) Assert an epic in flight refuses the
      uninstall and the fake runner received no commands at all
      (`factory/supervision/units.py:539-545`).

### Implementation for this story

- [ ] T019 [US2] (FR-005, FR-006) Rewrite `UninstallReport.render`
      (`factory/supervision/units.py:477-480`) to name each removed file and its
      acts, matching the voice of `InstallReport.render`'s `:466`.
- [ ] T020 [US2] (FR-007) Stop the slice in `uninstall`
      (`factory/supervision/units.py:528`), after `:549-554` and before the
      removal loop at `:556`, and record it on the report.
- [ ] T021 [US2] (FR-007) Leave `ENABLE_TARGETS` and the comment at
      `factory/supervision/units.py:74-77` untouched (trap 3).
- [ ] T022 [US2] (FR-008) Leave the open-epic refusal first in the function.

### Verification for this story

- [ ] T023 [US2] (SC-004) Paste the report naming every removed file and every
      unit's stop, disable and remove.
- [ ] T024 [US2] (SC-005) Paste the recorded systemd command sequence showing
      `ergane.slice` stopped, and paste the `ENABLE_TARGETS` control showing all
      four names unchanged (trap 12).

## Phase 3: User Story 3 — `ergane uninstall` owns the ordering

**Depends on US1 and US2 having merged** (`depends_on_merged`). Its `--check`
renders US1's disagreement line and US2's manifest, and neither exists until they
land.

**Read "The ruling on composition" in the plan before T025.** It settles how
teardown calls its three steps, and the ruling is load-bearing for T026, T030,
T033 and trap 14.

### Tests for this story (write FIRST, must fail)

- [ ] T025 [P] [US3] (spec US3-S1, FR-009) In
      `tests/test_teardown_owns_the_ordering.py`, assert teardown calls its steps
      in the declared order — pause dispatch, forget repositories, stop and
      remove units — and names each as it completes. The order comes from the one
      step table, which is also what `--check` prints.
- [ ] T026 [P] [US3] (spec US3-S2, FR-010) Assert `--check` prints the same plan
      and performs none of it, **by substituting a recording step table and
      asserting no step's acting half was called**, plus the direct assertions
      that nothing was written, removed, stopped or signalled. `init --check`'s
      promise is literally `writes nothing` (`factory/cli/init.py:345`).
- [ ] T027 [P] [US3] (spec US3-S3, FR-011) Assert a step with nothing to do says
      so by name rather than being silent — the survey half answers this without
      the acting half running.
- [ ] T028 [P] [US3] (spec US3-S4, FR-012) Assert a refused step stops the verb
      before the next step acts, names which step refused, and names what has
      already been done.
- [ ] T029 [P] [US3] (spec US3-S5, FR-012) Assert that dispatch which could not
      be paused because no owner can be named is a refusal, not a skipped step.
      `factory/cli/roadmap.py:311-319` and `factory/cli/roadmap.py:328-330` are
      why (trap 7).
- [ ] T030 [P] [US3] (spec US3-S6, FR-017) **The control.** Assert the three
      composed commands still behave exactly as they do today when invoked
      directly: `repo_forget_command` (`factory/cli/repo.py:307`) still takes one
      `argparse.Namespace` and still resolves its Temporal client through the
      module attribute at `factory/cli/repo.py:93` — drive it the way
      `tests/test_ergane_repo_forget.py:90` does — `uninstall()` still honours
      `run` (`factory/supervision/units.py:531`) and `open_epics` (`:532`), and
      `roadmap_pause_command` (`factory/cli/roadmap.py:310`) still pauses the
      schedule when the roadmap is schedule-owned. A teardown that works because
      the three commands beneath it were reshaped breaks every operator who never
      runs teardown.
- [ ] T031 [P] [US3] (spec US3-S7, FR-018) Assert a step whose removal target
      contains this installation is refused before any step acts: seed a target
      that is an ancestor of `resolve_layout()`'s `install_root`
      (`factory/supervision/units.py:182`) or of the directory holding the
      interpreter it derives (`factory/supervision/units.py:186`), and assert a
      non-zero exit, that path in the message, and that nothing was removed
      (trap 8).

### Implementation for this story

- [ ] T032 [US3] (FR-009) Add `factory/cli/nouns/uninstall.py`, following
      `factory/cli/nouns/repo.py`'s thirteen-line shape and delegating
      `add_parser` to a new `factory/cli/uninstall.py` the way
      `factory/cli/nouns/repo.py:6` delegates to `factory.cli.repo`. Discovery is
      `factory/cli/main.py:65` and needs no registration elsewhere; `class Noun:`
      is at `factory/cli/nouns/__init__.py:25`.
- [ ] T033 [US3] (FR-009) In `factory/cli/uninstall.py`, build the ordered step
      table — one record per step, each carrying a read-only survey half and an
      acting half — and have both `--check` and the real run read that one table,
      so the printed plan and the performed sequence cannot diverge. `perform`
      calls the three commands **as they stand**: `roadmap_pause_command`
      (`factory/cli/roadmap.py:310`, run through `asyncio.run` in the shape
      `factory/cli/roadmap.py:180-184` already uses), `repo_forget_command`
      (`factory/cli/repo.py:307`), and `uninstall(resolve_layout())`
      (`factory/supervision/units.py:528`, `factory/supervision/units.py:165`).
      The two open-epic seams stay as they are and are different functions:
      `factory/supervision/units.py:622` is passed through `uninstall()`'s
      `open_epics` parameter (`factory/supervision/units.py:532`), while
      `factory/cli/repo.py:96` has no parameter and is replaced as a module
      attribute. **No new seam in `factory/cli/roadmap.py`** (trap 14).
- [ ] T034 [US3] (FR-010) Add `--check`, matching
      `factory/cli/nouns/install.py:130-132` and `factory/cli/init.py:343-345`. It
      calls surveys only; the acting half must be unreachable on that path.
- [ ] T035 [US3] (FR-011, FR-012) Report every step: done, nothing-to-do, or
      refused-and-stopped-here.
- [ ] T036 [US3] (FR-017) Leave `factory/cli/roadmap.py`, `factory/cli/repo.py`'s
      `_temporal_client_factory` (`factory/cli/repo.py:93`) and `uninstall()`'s
      parameter list (`factory/supervision/units.py:531-532`) exactly as they
      are. `git diff --stat` must not list `factory/cli/roadmap.py` (trap 14).
- [ ] T037 [US3] (FR-018) Refuse, before any step acts, any step whose removal
      target contains `resolve_layout()`'s `install_root`
      (`factory/supervision/units.py:182`) or the directory holding the
      interpreter it derives (`factory/supervision/units.py:186`), naming the
      containing path and the reason. Take it in the shape of
      `_refuse_while_epics_run` (`factory/cli/repo.py:436`); no escape flag. Do
      not attempt to close
      `install/restarting-the-worker-deletes-the-operator-cli`.

### Verification for this story

- [ ] T038 [US3] (SC-006) Paste `ergane uninstall --check` output and, beside it,
      the substituted recording step table showing it empty, plus the assertions
      that nothing was written, removed, stopped or signalled. A paste of the
      plan alone proves the plan, not the inertness (trap 12).
- [ ] T039 [US3] (SC-007) Paste a teardown stopped by a refused step, showing
      which step refused and what had already been done.
- [ ] T040 [US3] (SC-008) Paste the control **both ways**: `ergane roadmap
      pause`, `ergane repo forget` and `ergane worker uninstall` invoked directly
      before this story and after it, so the judge can see the three behaviours
      and their seams unchanged (trap 12).
- [ ] T041 [US3] (SC-009) Paste the self-removal refusal: the non-zero exit, the
      containing path in the message, and evidence nothing was removed.

## Phase 4: User Story 4 — Teardown names what it kept as loudly as what it removed

**Depends on US3 having merged** (`depends_on_merged`). Pure contention: it edits
`factory/cli/uninstall.py` and the noun shim US3 creates.

### Tests for this story (write FIRST, must fail)

- [ ] T042 [P] [US4] (spec US4-S1, FR-013) In
      `tests/test_teardown_names_what_it_kept.py`, assert a bare run leaves the
      state home and the config in place and that each surviving path appears on
      its own labelled kept line **in the same block as the removed lines** — the
      shape `UninstallReport.render` already uses for `kept` at
      `factory/supervision/units.py:479`.
- [ ] T043 [P] [US4] (spec US4-S2, FR-014) **The control.** Assert `--purge`
      removes the state home's contents, keeps the config, and names both facts.
      A test that only checks the removal cannot tell state from credentials.
- [ ] T044 [P] [US4] (spec US4-S3, FR-014) Assert no `.lock` sibling survives a
      purge. `factory/locking.py:68` creates it; `factory/locking.py:83` unlocks
      and `factory/locking.py:85` closes, and nothing anywhere unlinks it
      (trap 10) — fix it in teardown, not in `exclusive_lock`.
- [ ] T045 [P] [US4] (spec US4-S4, FR-015) Assert teardown prints a count for
      each namespace — `factory/<epic>/<node>` branches
      (`factory/workgraph/worktree.py:238-240`) and everything under
      `refs/salvage/` (`factory/workgraph/worktree.py:480`) — prints both
      commands verbatim (`git for-each-ref refs/heads/factory/` and
      `git for-each-ref refs/salvage/`), leaves the refs in place, and **does not
      name `ergane build salvage`**, which loads a compiled graph
      (`factory/cli/nouns/build.py:1263`) and answers a different question.
- [ ] T046 [P] [US4] (spec US4-S5, FR-016) Assert `--scrub-refs` removes those
      refs and names them.

### Implementation for this story

- [ ] T047 [US4] (FR-013) Keep the config (`resolve_config_path()`,
      `factory/controlplane/config.py:201`) and the secrets beside it by default,
      and render one labelled kept line per surviving path in the same block as
      the removed lines, in the voice of `factory/supervision/units.py:479`.
- [ ] T048 [US4] (FR-014) Add `--purge`, resolving the state home through
      `factory/registry.py:159` and the config through
      `factory/controlplane/config.py:201`. **Write down which root is emptied
      when an override is in force, and disclose the other** — trap 9 is US1's
      ruling applied here. US3's self-removal refusal still guards this path, and
      `--purge` is the step most able to trip it (trap 8).
- [ ] T049 [US4] (FR-014) Sweep the `.lock` siblings
      (`factory/locking.py:46-49` gives the naming rule).
- [ ] T050 [US4] (FR-015, FR-016) Count the refs with one `for-each-ref` per
      namespace — the shape `factory/workgraph/worktree.py:823` already uses,
      unnarrowed — print the two commands verbatim, and remove the refs only
      under `--scrub-refs`.

### Verification for this story

- [ ] T051 [US4] (SC-010) Paste the two runs side by side — bare and `--purge` —
      showing state removed in the second, config kept in both, and each
      surviving path on its own labelled kept line beside the removed lines.
- [ ] T052 [US4] (SC-011) Paste the ref enumeration with a count per namespace
      and both `git for-each-ref` commands verbatim, once showing the refs
      surviving and once showing them removed under `--scrub-refs`.
