# Tasks: Merge Discipline via GitHub Merge Queue

**Input**: Design documents from `/specs/003-merge-queue/`

**Prerequisites**: plan.md (self-contained — data model, gh command surface, classification table, and onboarding checks are inlined there), spec.md

**Tests**: Mandatory (constitution II, test-first). Every implementation task is preceded by its failing test task.

**Organization**: This epic is dispatched by the factory (D-024) — tasks.md is sliced per user story and each node receives ONLY its own story's phase, so every buildable task lives inside a story phase and each slice is self-contained. Phase 1 is operator preflight that no node executes. Phases 2–4 are the stories in graph order: US1 (landing path), US2 (recovery, depends on US1's landed code), US3 (onboarding, independent — its slice therefore re-states its prerequisites as create-if-absent).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies). Each node's agent executes its slice strictly in file order; [P] documents independence, not scheduling.
- **[Story]**: US1 (verified work lands through the queue), US2 (queue rejection recovery), US3 (target repo onboarding)

## Phase 1: Setup (operator preflight — dispatched to no node)

**Purpose**: Environment facts the spec assumes. The slicer never delivers this phase to an agent; these are the operator's own checklist, and every live test auto-skips until they are done.

- [ ] T001 Operator: create the D-010 sample repo (public; committed `factory.yaml` with at least a `test` gate; CI check named exactly after each declared gate; merge queue enabled on the default branch via a ruleset), authenticate `gh` on the worker host for it, and record the clone path for `FACTORY_SAMPLE_REPO`

---

## Phase 2: User Story 1 — Verified work lands through the queue (Priority: P1) 🎯 MVP

**Goal**: The component's core value: on ladder PASS, salvage → push `factory/<epic>/<node>` → ready PR with spec ref + verification summary → `gh pr merge --auto` → poll → classified outcome, with GitHub's queue doing all serialization and the interpreter distinguishing verified from merged (FR-001, 002, 003, 004, 009).

**Independent Test**: On a sample public repo with merge queue enabled, drive one node branch through PR → enqueue → merged, and assert the factory observed the final state correctly (spec US1).

### Tests for User Story 1 (write FIRST, must fail)

^- [x] T002 [US1] Verify prerequisites in this worktree: `uv run pytest -q` passes and `factory/workgraph/workflow.py`, `factory/verify/ladder.py`, `factory/usage/`, `factory/notify/`, `factory/activities/` exist — constitution I gate; STOP and report blocked if not satisfied
^- [x] T003 [US1] Create skeletons and marker: `factory/mergequeue/__init__.py`, and a `live_merge` pytest marker in `pyproject.toml` alongside `live_epic` ("drives real PRs through the sample repo's merge queue; auto-skips unless FACTORY_SAMPLE_REPO is set and gh is authenticated")
^- [x] T004 [P] [US1] Write `tests/test_mergequeue_models.py` FIRST per plan.md § Data Model: `QueueOutcome` StrEnum with exactly `MERGED|CHECKS_FAILED|CONFLICT|DEQUEUED_BY_HUMAN|STALLED`; `LandingState` transitions as documented (REJECTED may re-enter ENQUEUED, KILLED terminal); `Landing`/`ObservedOutcome`/`PrSnapshot`/`LandingConfig` round-trip through `dataclasses.asdict` + reconstruction (Temporal JSON shape); `PrSnapshot.from_gh_json` parses a captured `gh pr view --json` payload including absent `autoMergeRequest` and failing `statusCheckRollup` entries — must fail (no models.py yet)
^- [x] T005 [US1] Implement `factory/mergequeue/models.py` until T004 passes
^- [x] T006 [P] [US1] Create `tests/fake_gh.py` — `FakeGh`, a strict record/replay runner in `conftest.py`'s `FakeLiteLLM` discipline: scripted `(argv-matcher → stdout, stderr, exit)` expectations, every invocation recorded in order with its `cwd`, any unexpected command raises immediately; helpers to script the canned `gh pr view` JSON states the classifier table needs
^- [x] T007 [US1] Write `tests/test_gh_client.py` FIRST per plan.md § US1 gh command surface: `GhClient` spawns the injected runner with `cwd` = target clone; `--json` outputs parsed; failure taxonomy (`GH_AUTH`/`GH_NOT_FOUND`/`GH_REFUSED` with stderr tail/`GH_UNAVAILABLE`) — a refused enqueue is returned as data, never raised as a crash; structural guards: no code path ever passes `--delete-branch` (FR-008) and the only `gh pr merge` form is `--auto` (+ `--disable-auto`), never a direct merge (FR-002) — must fail
^- [x] T008 [US1] Implement `factory/mergequeue/gh.py` until T007 passes
^- [x] T009 [P] [US1] Write `tests/test_classify.py` FIRST — the plan's classification table, one test per row plus the spec edge cases: merged (incl. merged manually while enqueued) → MERGED; closed-unmerged → DEQUEUED_BY_HUMAN; auto-merge gone + failing required checks → CHECKS_FAILED; `mergeStateStatus DIRTY` → CONFLICT; auto-merge gone, clean, open → DEQUEUED_BY_HUMAN; auto-merge still requested → pending None; pending past `stall_after_s` with unchanged snapshot → STALLED; classification is a pure function of (PrSnapshot, Landing, LandingConfig, now) — must fail
^- [x] T010 [US1] Implement `factory/mergequeue/classify.py` until T009 passes
^- [x] T011 [P] [US1] Write `tests/test_pr_messages.py` FIRST: PR title `<epic>/<node>: <story title>`; body carries the spec reference (feature + requirement keys), branch name, attempt count, per-gate results of the passing attempt, judge outcome or `judge_unavailable`; plant `LITELLM_MASTER_KEY`/`TELEGRAM_BOT_TOKEN`/proxy URL values in the inputs' environs and assert none appear in the rendered body (public repo, architecture §10); same inputs → identical bytes — must fail
^- [x] T012 [US1] Implement `factory/mergequeue/messages.py` (PR rendering) until T011 passes
^- [x] T013 [US1] Write push-helper tests FIRST in `tests/test_worktree.py` against `tmp_path` repos with a bare `origin` remote: `push_branch` pushes `factory/<epic>/<node>` to origin (fast-forward, never `--force`); pushing a branch named the target's default branch is refused with an error naming FR-001; re-push after new commits succeeds — must fail (no helper yet)
^- [x] T014 [US1] Amend `factory/workgraph/worktree.py` with `push_branch` until T013 passes
^- [x] T015 [US1] Write `tests/test_merge_activities.py` FIRST (`ActivityEnvironment` + `FakeGh` + tmp repos with bare origin): `open_landing_pr` pushes then creates a ready (never draft) PR with the rendered body via `--body-file`, and is idempotent — an existing open PR for the branch is reused, not duplicated; `enqueue_landing` issues `gh pr merge <n> --auto --<merge_method>` from `LandingConfig` and returns a queue-disabled refusal as rejection data (spec edge case); `poll_landing` returns a `PrSnapshot`; `disable_auto_merge` is best-effort (a failure is reported, not raised); no activity deletes any branch — must fail
^- [x] T016 [US1] Implement `factory/activities/merge_activities.py` (US1 surface: `open_landing_pr` / `enqueue_landing` / `poll_landing` / `disable_auto_merge`) until T015 passes
^- [x] T017 [US1] Write grammar-extension tests FIRST: in `tests/test_workgraph_models.py` — `WorkNode.depends_on_merged` defaults empty, round-trips, and `validate_workgraph` rejects unknown story, self-reference, a key in both `depends_on` and `depends_on_merged`, and a cycle through the union of both edge sets (errors name the offender); in `tests/test_derive.py` — a fixture spec declaring `depends_on_merged: [US1]` derives it onto the node, and each rejection emits nothing — must fail
^- [x] T018 [US1] Amend `factory/workgraph/models.py` and `factory/workgraph/derive.py` (additive `depends_on_merged`, FR-009; existing graphs without it stay valid) until T017 passes
- [x] T019 [US1] Write landing-phase tests FIRST in `tests/test_interpreter.py` (time skipping, scripted merge-activity fakes registered under the real names): US1-S1/S3 — a PASS node salvages, pushes, opens PR, enqueues, transitions PASSED → PR_OPEN → ENQUEUED → MERGED on a scripted merged snapshot, and its worktree is removed only after the landing is terminal; FR-004 — a scripted event gap (poll returns pending, then merged) reconciles correctly; FR-009 — a verified-gated dependent dispatches while the landing is still ENQUEUED, a merge-gated dependent (`depends_on_merged`) waits for MERGED; US1-S4 — two independent nodes both reach ENQUEUED and the epic completes only when both landings are terminal, in whatever order the scripted queue settles them; FR-003/SC-003 — the judge fake trips on any invocation during landing; `kill_epic` mid-landing cancels polling, calls `disable_auto_merge`, marks the landing KILLED, branch preserved; `epic_status` reports landing state + PR number per node — must fail
- [x] T020 [US1] Implement the landing phase in `factory/workgraph/workflow.py` per plan.md § US1 (NodeState additions, `NodeRecord.verified`/`.landing`, `LandingConfig` on `EpicInput`, background poll task per landing, main-loop exit = all nodes AND all landings terminal, worktree removal deferred to landing-terminal, kill/pause semantics), register the merge activities in `factory/worker.py` (the mechanical worker-registration test must stay green), until T019 passes
- [x] T020a [US1] **Migrate the pre-landing CLI fixtures — do this before anything else if T020's code is already present in the worktree.** T020's main-loop change gates epic completion on `_all_landings_terminal()` via an unbounded `wait_condition`. That is correct, but `tests/test_epic_cli.py` predates landings: its `ScriptedEpic`/`worker_for` fixtures script no merge activities, so a node PASSES, opens a landing that never settles, and the workflow parks forever. Four tests then hang and die with `RuntimeError: No completion event found`. Measured on the salvaged branch: baseline `b1194a6` is **33 passed in 2.35s**; with T020 present it is **4 failed, 29 passed in 81.73s** — the 35× runtime is the tell that these hang rather than fail. Beware the misleading secondary symptom: once a hung test's time-skipping environment is torn down, *later* connections report `tcp connect error to 127.0.0.1:<port>`, which looks like a broken environment and is not — it is downstream of this hang, and leaked `temporal-test-server` processes are a consequence of it too. Failing tests: `test_the_started_epic_carries_the_compiled_graph_and_the_proxy_url`, `test_status_reads_a_live_epic_mid_flight`, `test_status_json_is_the_query_result_verbatim`, `test_the_human_status_is_an_epic_line_then_one_line_per_node`. Fix by scripting the merge activities in those fixtures so landings reach a terminal state; all four exist and pass at baseline, so this is a regression to repair, not new behaviour to design. Any future wait added to the main loop must have its fixtures migrated in the same task.
- [x] T021 [US1] Add `tests/test_live_merge.py` with `@pytest.mark.live_merge`: drive one real branch of `FACTORY_SAMPLE_REPO` through PR → enqueue → merged via the real activities; assert the observed outcome is MERGED and the PR body carries the spec reference; auto-skips without the env
- [x] T022 [US1] Docs truth: update `docs/architecture.md` §7 (landing path implemented — module table, lifecycle, classification table, polling-only reconciliation) and record a decision-log entry in `docs/decisions.md` (next free D-number) covering: no landing store (workflow state + query), `depends_on_merged` grammar extension, polling-only outcome observation, `LandingConfig` knobs incl. merge method

**Checkpoint**: A verified node lands through the real queue with the factory only observing — MVP

---

## Phase 3: User Story 2 — Queue rejection recovery (Priority: P2)

**Goal**: No silent stalls: checks-failed re-enters the 002 inner loop on a synced branch, conflicts buy the `debugger` one bounded cycle, everything else escalates over Telegram with the queue history — and no failure path ever deletes a branch (FR-005, 006, 007, 008).

**Independent Test**: Manufacture a conflicting pair of PRs on the sample repo; assert the loser is detected, re-driven, and either lands after repair or escalates (spec US2).

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T023 [P] [US2] Write sync-helper tests FIRST in `tests/test_worktree.py`: `sync_with_target` fetches and merges `origin/<default>` into the node branch inside its worktree; a clean merge reports `clean` and returns the merged-in target head as the new `base_ref` (D-027 extended — subsequent diffs show only the node's own work); a conflicting merge reports `conflict` with the conflicted file list and leaves the markers in the tree (the debugger's work surface); the node branch is never rewritten (no rebase, push stays fast-forward) — must fail
- [ ] T024 [US2] Amend `factory/workgraph/worktree.py` with `sync_with_target` until T023 passes
- [ ] T025 [P] [US2] Write landing-evidence prompt tests FIRST in `tests/test_prompt.py`: when landing evidence is supplied, the assembled prompt carries a landing section with the classified outcome, the queue history, and (for conflicts) the conflicted file list verbatim; absent evidence → no section, existing golden prompts unchanged; same inputs → identical bytes — must fail
- [ ] T026 [US2] Amend `factory/workgraph/prompt.py` (optional landing-evidence section) until T025 passes
- [ ] T027 [US2] Write recovery-activity tests FIRST in `tests/test_merge_activities.py`: `sync_landing_branch` wraps the T024 helper (clean/conflict as data, new base_ref returned); re-enqueue after recovery reuses the same PR (no duplicate); a `gh` failure during recovery is surfaced as data with the stderr tail, never a silent pass — must fail
- [ ] T028 [US2] Implement the recovery surface of `factory/activities/merge_activities.py` (`sync_landing_branch`) until T027 passes
- [ ] T029 [P] [US2] Write landing-escalation message tests FIRST in `tests/test_messages.py`: rendering takes the `Landing` (queue history timestamps + outcomes, recovery cycles) and offers exactly `[RETRY | KILL | PAUSE_EPIC]` inline buttons with the existing `esc:<id>:<choice>` callback grammar; the manual-intervention notice variant (PR closed by a human) renders with no buttons; no credential appears — must fail
- [ ] T030 [US2] Amend `factory/notify/messages.py` (landing escalation + manual-intervention notice) until T029 passes
- [ ] T031 [US2] Write recovery-routing tests FIRST in `tests/test_interpreter.py` (scripted fakes): US2-S1 — a scripted CHECKS_FAILED syncs clean, re-enters the inner loop (fresh key issued/torn down, FR-004/constitution V; landing evidence verbatim in the recovery prompt), re-verifies through the real ladder path, re-enqueues on PASS, `recovery_cycles` incremented; US2-S2 — a scripted CONFLICT routes one bounded cycle to persona `debugger` (alias carries the persona, D-026) with conflict context in the prompt, then re-verify → re-enqueue; US2-S3 — a second failure escalates with the queue history rendered and choices [RETRY|KILL|PAUSE_EPIC], the 1h timer defaults to KILL, and `RETRY` grants exactly one more cycle; US2-S4/FR-008 — on every rejected/killed path no branch-delete is recorded by any fake and the salvage commit is reachable on `factory/<epic>/<node>`; edge cases — enqueue refusal (queue disabled) goes to escalation not crash, manual merge while enqueued reconciles to MERGED, manual close ends the node KILLED with the manual-intervention notice sent; a pending recovery outranks pending fresh nodes in the scheduler — must fail
- [ ] T032 [US2] Implement recovery routing in `factory/workgraph/workflow.py` per plan.md § US2 (rejection → sync/debugger/escalate state machine, `max_recovery_cycles` from `LandingConfig`, recovery attempts scheduled by the main loop only, base_ref carried forward into re-verification) until T031 passes
- [ ] T033 [US2] Add a `@pytest.mark.live_merge` case to `tests/test_live_merge.py`: manufacture a conflicting pair of branches on `FACTORY_SAMPLE_REPO`, land the winner, assert the loser is classified CONFLICT by the real poll/classify path and its branch survives untouched (full recovery drive stays in the time-skipping suite — the live case proves detection, not the agent cycle)
- [ ] T034 [US2] Docs truth: update `docs/architecture.md` §7 (recovery routing implemented) and §9 (landing escalations and the manual-intervention notice now use the notifier)

**Checkpoint**: Every queue rejection ends in exactly one of re-land, bounded debugger recovery, or operator escalation — never a silent stall (SC-002)

---

## Phase 4: User Story 3 — Target repo onboarding (Priority: P3)

**Goal**: Nothing dispatches against a repo whose queue/protection/required-check configuration doesn't match `factory.yaml` — validated live at every epic start, with an operator preflight CLI (FR-010, SC-005).

**Independent Test**: Run onboarding validation against a repo with and without merge queue configured; assert pass/fail with actionable findings (spec US3).

### Tests for User Story 3 (write FIRST, must fail)

- [ ] T035 [US3] Slice self-containment gate: this node's graph edge is independent of US1, so its worktree may predate US1's landing. If `factory/mergequeue/gh.py`, `factory/mergequeue/models.py` (`TargetRepoProfile`/`Finding` live there either way), `tests/fake_gh.py`, or the `live_merge` marker are absent, create them per plan.md §§ Data Model / US1 gh command surface (and T004–T008's test discipline) before proceeding; if present, touch nothing
- [ ] T036 [P] [US3] Write `tests/test_onboard.py` FIRST — pure findings per plan.md § US3, one case per check: public repo + queue rule + checks named exactly after every declared gate → `passed=True` with one passing Finding per check; private repo → failing `visibility` finding; no `merge_queue` rule on the default branch → failing `merge_queue` finding; a declared gate with no required check of that name → failing `gate_check:<gate>` finding naming the missing check; a required check mapping to no declared gate → failing finding (deterministic gates only, FR-003 — this is what keeps the judge out of CI structurally); missing or malformed `factory.yaml` → failing `factory_yaml` finding carrying the 002 loader's error, never a pass by default; every failing Finding's detail names the remedy — must fail
- [ ] T037 [US3] Implement `factory/mergequeue/onboard.py` (+ `TargetRepoProfile`/`Finding` in `factory/mergequeue/models.py` if T035 created it fresh) until T036 passes
- [ ] T038 [US3] Write `validate_target_repo` activity tests FIRST in `tests/test_merge_activities.py` (`ActivityEnvironment` + `FakeGh` + a tmp clone carrying `factory.yaml`): gathers repo facts (`gh repo view`, rules endpoint, classic-protection fallback when the rules list carries no required checks), loads the clone's `factory.yaml` via `factory.verify.factory_yaml`, returns the pure profile; any `gh` failure yields a failed validation with a finding, never a pass — must fail
- [ ] T039 [US3] Implement `validate_target_repo` in `factory/activities/merge_activities.py` until T038 passes
- [ ] T040 [US3] Write CLI tests FIRST in `tests/test_epic_cli.py`: `factory-epic onboard <target-clone-path>` prints every finding (pass and fail) human-readably and with `--json`; exit 0 all-pass / 1 any-fail / 2 usage — must fail
- [ ] T041 [US3] Implement the `onboard` subcommand in `factory/workgraph/cli.py` until T040 passes
- [ ] T042 [US3] Write dispatch-blocking tests FIRST in `tests/test_interpreter.py`: a scripted failing profile fails the epic before `resolve_graph`, with zero keys issued and zero worktrees prepared (SC-005), and the failure message carries the findings; a passing profile proceeds to normal dispatch — must fail
- [ ] T043 [US3] Wire `validate_target_repo` into `EpicWorkflow.run` ahead of `resolve_graph` in `factory/workgraph/workflow.py` until T042 passes
- [ ] T044 [US3] Add a `@pytest.mark.live_merge` case to `tests/test_live_merge.py`: onboarding validation passes against `FACTORY_SAMPLE_REPO` and fails with actionable findings against a queue-less repo (this factory clone itself serves); auto-skips without the env
- [ ] T045 [US3] Final sweep + docs: extend the credential sweep to `factory/mergequeue/` (no `LITELLM_MASTER_KEY`/`TELEGRAM_BOT_TOKEN`/proxy URL in any payload, PR body, finding, or error path); assert component-wide by grep-backed tests that no code passes `--delete-branch` or `push --force` and no `gh pr merge` lacks `--auto`/`--disable-auto` (FR-001/002/008 structural); update `docs/architecture.md` §7 (onboarding implemented; component 3 no longer "does not exist in code") and §1's build-order line

**Checkpoint**: All user stories independently functional; dispatch is structurally impossible against an unvalidated repo

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: operator-only; gates nothing but the live markers, which auto-skip
- **Phase 2 (US1)**: first — T002 is a hard gate (constitution I)
- **Phase 3 (US2)**: after Phase 2 — the graph declares `US2.depends_on: [US1]`, and during this bootstrap epic the human operator acts as the merge queue (D-024): US1's branch must be merged to the target branch before US2 dispatches, so US2's worktree (branched from the head captured at its own dispatch) contains US1's code
- **Phase 4 (US3)**: independent in the graph; dispatches after US2 in declaration order, but T035 makes its slice self-sufficient if US1 never landed

### Within stories

- Every test task precedes its implementation task and must FAIL first for the right reason
- US1: models → gh seam → classify → messages → push → activities → grammar → workflow → live → docs; US2: sync → prompt → activities → escalation messages → workflow → live → docs; US3: self-containment gate → pure checks → activity → CLI → workflow gate → live → sweep

### Parallel Opportunities

- T004/T006, T009/T011 touch different files; T023/T025/T029 are mutually independent; T036 is pure-only. Each node's agent ignores parallelism and works its slice strictly in order — [P] documents safety, not scheduling.

---

## Implementation Strategy

**MVP = Phase 2**: after T020 the crossover behavior exists — a verified node lands through the queue with the factory only observing — and T021 proves it against real GitHub. Phase 3 makes rejection survivable (SC-002); Phase 4 closes the "queue silently unavailable" class (SC-005).

**Execution**: `factory-epic derive specs/003-merge-queue && factory-epic start specs/003-merge-queue/workgraph.json` — one node per story on `factory/003-merge-queue/<node>`, each implementer working its slice test-first under the inner ralph contract, `uv run pytest -q` as the factory.yaml gate, the human operator standing in as the merge queue between nodes until this very component lands (D-024).
