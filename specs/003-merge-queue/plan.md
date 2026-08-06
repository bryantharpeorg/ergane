# Implementation Plan: Merge Discipline via GitHub Merge Queue

**Branch**: `003-merge-queue` | **Date**: 2026-08-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-merge-queue/spec.md`

## Summary

The component that gets verified work onto the target branch without the factory
ever serializing landings itself (D-007). When a node's ladder says PASS, the
interpreter's new landing phase salvages the worktree, pushes
`factory/<epic>/<node>` (the 005 FR-013 branch) to origin, opens a
ready-for-review PR whose body carries the node's spec reference and verification
summary, and requests auto-merge — GitHub's native merge queue does the
serializing, rebasing, and deterministic re-testing (required checks are the
target repo's gates only, never the LLM judge, D-008/FR-003). The factory's whole
merge role is enqueue → await → classify: a reconciliation poll loop reads PR
state through the `gh` CLI and a pure classifier names the outcome — `merged |
checks_failed | conflict | dequeued_by_human | stalled` (FR-004). Rejections
re-enter the 002 inner loop on a branch synced to the new target head; conflicts
buy the `debugger` persona one bounded cycle in the node's worktree; only then
does the existing Telegram escalation fire, with kill-on-silence and the branch
always preserved (FR-005–008, constitution VI). Nodes now distinguish *verified*
from *merged* so edges can gate on either (FR-009, default verified). Onboarding
validation (FR-010) blocks dispatch against any repo whose queue, protection, or
required-check configuration does not match `factory.yaml` — checked at every
epic start, not cached. This plan is deliberately self-contained: the prompt
assembler ships spec/plan/tasks only, so the data model and every contract an
implementer node needs are inlined below rather than split into files that would
never reach it.

## Technical Context

**Language/Version**: Python 3.11+ (D-003); the worker host runs 3.13.

**Primary Dependencies**: `temporalio` (workflow/activities), `pyyaml`, `httpx` —
all roster items, all already in use. GitHub is driven through the **`gh` CLI as
a worker-host binary** (same standing as `claude` and `git`, D-007's own flow):
`asyncio.create_subprocess_exec` + `--json` output, deliberately chosen over a
GitHub SDK (PyGithub/ghapi) precisely so this component adds **no new Python
dependency** (constitution III). If any task discovers a genuine need for an SDK,
that is an operator-approval conversation, not a quiet `uv add`.

**Storage**: **No new store.** A `Landing` is workflow state on the node's
record, surfaced through the `epic_status` query and the workflow result;
Temporal history is its audit trail, and the durable no-work-lost artifact is the
branch itself (FR-008). The 001 ledger and 002 verification store are consumed
as-is through their owning activities (recovery attempts are ordinary bracketed
attempts). Rationale for rejecting a third SQLite file: every fact the escalation
message or the operator needs lives on the in-flight workflow, and nothing here
outlives the epic except refs GitHub already keeps. Flagged for operator review —
if post-hoc landing analytics are wanted later, a table can be added without
restructuring.

**Testing**: `pytest` + `pytest-asyncio`. The one `gh` boundary
(`factory/mergequeue/gh.py`) takes an injectable runner; `tests/fake_gh.py`
provides `FakeGh` — a strict record/replay stand-in in the mold of `conftest.py`'s
`FakeLiteLLM`: scripted stdout/exit per expected invocation, every call recorded
in order, unexpected commands fail the test at the seam. Pure logic
(classification, PR body rendering, onboarding findings, grammar extension) is
table-tested with no fakes at all. Activities:
`temporalio.testing.ActivityEnvironment` + `FakeGh` + `tmp_path` git repos with a
bare `origin` remote standing in for GitHub's git side. Interpreter:
`WorkflowEnvironment.start_time_skipping()` with scripted merge-activity fakes
registered under the real activity names (the 005 pattern). Live Tier 1 behind a
new env-gated `live_merge` marker, declared in `pyproject.toml` alongside
`live_proxy`/`live_telegram`/`live_epic`, auto-skipping unless
`FACTORY_SAMPLE_REPO` (a clone path of the D-010 sample repo) is set and `gh` is
authenticated.

**Target Platform**: Single Linux worker host owning `.factory/` (001 topology).
`gh` present and authenticated for the target repos (spec assumption); all `gh`
invocations run with `cwd` = the target clone so `gh` resolves the repo from
`origin` and no owner/repo slug is plumbed through payloads.

**Project Type**: Library subpackage (`factory/mergequeue/`, the slot D-004
reserved) + one activity surface (`factory/activities/merge_activities.py`) +
amendments to the interpreter (`factory/workgraph/`) it phases into.

**Performance Goals**: Bootstrap scale — single-digit landings per epic. Landing
poll ~1 `gh pr view` per `poll_interval_s` (default 60s) per in-flight landing;
stall declared after `stall_after_s` (default 7200s) without observable movement.
Both are `LandingConfig` fields on `EpicInput`, never constants buried in code
(constitution VII discipline applied to cadence).

**Constraints**: The factory MUST NOT serialize landings — the only merge
invocation anywhere is `gh pr merge --auto` (FR-002), and the push helper refuses
the target's default branch outright (FR-001, structural). The judge is never a
required check and no merge decision consults an LLM (FR-003, D-008; recovery
re-verification may consult the judge, but that is 002 inner-loop activity,
attributed to verification — never triggered by queue requeues or bisection,
which is SC-003's point). No failure path deletes a branch: `gh pr close` is
never passed `--delete-branch`, and `worktree.remove` already leaves branches
standing (FR-008, SC-004). Recovery agent attempts run inside 001 key brackets
with fresh keys (constitution V); `LITELLM_MASTER_KEY`/`TELEGRAM_BOT_TOKEN`
discipline unchanged. Workflow logic stays pure — every `gh` and `git` touch is
an activity (constitution IV).

**Scale/Scope**: Single operator, one epic in flight, target repos public
(D-007; private-on-Free is out of scope per spec Assumptions).

## Constitution Check

*GATE: evaluated against constitution v2.2.0 before Phase 0; re-checked after Phase 1.*

| Principle | Status | Evidence |
|---|---|---|
| I. Build order, vertical slices | PASS | 001, 002, and 005 are implemented and green; 003 is last in the amended order (D-024) and is the factory's first self-dispatched epic. It consumes the ladder, notifier, ledger, and worktree/workflow seams strictly through their shipped surfaces. |
| II. Test-first | PASS | Every deliverable has a test strategy above; tasks order every failing test before its implementation. |
| III. Ask before dependencies | PASS | Zero new Python dependencies. `gh` is a worker-host binary (like `claude`/`git`), not a package; an SDK was considered and rejected for exactly this principle. |
| IV. Determinism core, LLMs edges | PASS | Outcome classification, PR rendering, onboarding findings, and the grammar extension are pure functions; all `gh`/`git` side effects live in activities. GitHub's queue is the serializer — the factory re-implements none of it — and no LLM sits in any merge decision. LLM use appears only where 002 already put it: recovery re-verification and the debugger's conflict cycle. |
| V. Spend attributed, never anonymous | PASS | The landing path itself spends zero LLM tokens. Recovery attempts (implementer re-verify, debugger conflict cycle) are ordinary attempts bracketed by `issue_attempt_key`/`teardown_attempt` with the persona in the alias (D-026). |
| VI. No work lost | PASS | Salvage precedes push (the branch carries the work before GitHub ever sees it); killed/rejected landings preserve the branch (FR-008, SC-004); manual dequeue is reconciled, never destroyed. |
| VII. Personas over model tiers | PASS | Conflict recovery names the `debugger` persona; the registry resolves everything about it. No model, timeout, poll cadence, or merge method is hardcoded — `LandingConfig` carries the operator-settable knobs. |

**Post-Phase-1 re-check**: PASS — no design element introduced a violation;
Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/003-merge-queue/
├── plan.md                    # This file — self-contained: data model + contracts inlined
└── tasks.md                   # Story-sliced task list (the slicer delivers one phase per node)
```

No `research.md`, `data-model.md`, or `contracts/` ship for this feature: the
factory's prompt assembler hands each implementer node exactly `spec.md`,
`plan.md`, and its `tasks.md` slice (005 FR-006/FR-012) — a contract split into a
side file would never reach the agent that needs it. Everything those files would
hold is inlined below.

### Source Code (repository root)

```text
factory/
├── mergequeue/
│   ├── __init__.py
│   ├── models.py              # Landing, LandingState, QueueOutcome, PrSnapshot, TargetRepoProfile, Finding, LandingConfig
│   ├── gh.py                  # GhClient: the ONE subprocess boundary to the gh CLI (injectable runner, error taxonomy)
│   ├── classify.py            # pure: PrSnapshot + landing clock → QueueOutcome | None (§US1 table below)
│   ├── messages.py            # pure: PR title/body rendering (spec ref + verification summary)
│   └── onboard.py             # pure: repo facts + factory.yaml gates → TargetRepoProfile findings (FR-010)
├── activities/
│   └── merge_activities.py    # open_landing_pr / enqueue_landing / poll_landing / disable_auto_merge /
│                              #   sync_landing_branch / validate_target_repo
├── workgraph/
│   ├── models.py              # AMENDED: NodeState +PR_OPEN/ENQUEUED/MERGED; NodeRecord.verified; WorkNode.depends_on_merged
│   ├── derive.py              # AMENDED: optional `depends_on_merged` in the ## Work Graph grammar (FR-009)
│   ├── worktree.py            # AMENDED: push (refuses default branch) + sync-with-target helpers
│   ├── prompt.py              # AMENDED: optional landing-evidence section (queue history, conflict context)
│   └── workflow.py            # AMENDED: landing phase after PASS, recovery routing, onboarding gate at epic start
├── notify/
│   └── messages.py            # AMENDED: landing-escalation rendering (queue history + [RETRY|KILL|PAUSE_EPIC])
└── worker.py                  # AMENDED: register merge activities

pyproject.toml                 # AMENDED: live_merge marker

tests/
├── fake_gh.py                 # FakeGh: strict record/replay runner (FakeLiteLLM's discipline, subprocess-shaped)
├── test_mergequeue_models.py  # enums exact, Landing/PrSnapshot round-trip (Temporal JSON shape)
├── test_gh_client.py          # invocation shape, cwd, JSON parse, error taxonomy, structural FR-001/FR-008 guards
├── test_classify.py           # the outcome decision table, every row + every spec edge case
├── test_pr_messages.py        # PR title/body: spec ref, verification summary, no credentials, deterministic
├── test_onboard.py            # findings per check, actionable text, fail-closed on missing/malformed inputs
├── test_merge_activities.py   # ActivityEnvironment + FakeGh + tmp git repos: idempotency, refusal-as-data
├── test_worktree.py           # AMENDED: push + sync helpers against tmp repos with a bare origin
├── test_prompt.py             # AMENDED: landing-evidence section verbatim
├── test_workgraph_models.py   # AMENDED: depends_on_merged validation
├── test_derive.py             # AMENDED: depends_on_merged derivation + rejections
├── test_interpreter.py        # AMENDED: landing/recovery/blocking scenarios under time skipping
├── test_epic_cli.py           # AMENDED: `factory-epic onboard`
└── test_live_merge.py         # Tier 1 behind live_merge: real queue on the D-010 sample repo
```

**Structure Decision**: `factory/mergequeue/` is the subpackage D-004 reserved
for this component — the queue client, classifier, and onboarding checks are a
subsystem with their own seam (`gh.py`), not a corner of the interpreter. The
*landing phase*, however, is a stage of the node lifecycle that `EpicWorkflow`
already owns, so it lands as amendments to `factory/workgraph/workflow.py`
rather than a second workflow: one node, one lifecycle, one place its state
machine lives. `merge_activities.py` mirrors the other three activity modules.
The escalation renderer extends `factory/notify/messages.py` because the
notifier owns message shape end to end (callback grammar included); mergequeue
supplies data, not Telegram markup.

## Data Model (inline)

**QueueOutcome** (`StrEnum`, exact members — FR-004): `MERGED`, `CHECKS_FAILED`,
`CONFLICT`, `DEQUEUED_BY_HUMAN`, `STALLED`.

**LandingState** (`StrEnum`): `PR_OPEN → ENQUEUED → MERGED | REJECTED | KILLED`.
`REJECTED` is the recovery-eligible rejection (checks_failed/conflict) and may
transition back to `ENQUEUED` after a successful recovery cycle; `KILLED` is
terminal (operator kill, dequeue-by-human, escalation default, epic kill).

**Landing** (frozen dataclass, workflow state on `NodeRecord`): `node_id`,
`branch`, `pr_number: int | None`, `pr_url: str | None`, `enqueued_at: str |
None`, `outcomes: tuple[ObservedOutcome, ...]` (each `ObservedOutcome` =
`at: str` + `outcome: QueueOutcome` — the queue history the escalation quotes),
`recovery_cycles: int`, `state: LandingState`. Round-trips through
`dataclasses.asdict` + reconstruction (Temporal JSON converter shape), like every
005 model.

**PrSnapshot** (frozen dataclass, activity output): `state`
(`OPEN|CLOSED|MERGED`), `is_draft`, `auto_merge_requested: bool`,
`merge_state_status: str` (GitHub's `mergeStateStatus`, e.g. `DIRTY`),
`merged_at: str | None`, `closed_at: str | None`, `failing_required_checks:
tuple[str, ...]` (names from `statusCheckRollup` with failure conclusions),
`observed_at: str`. Built by `poll_landing` from `gh pr view --json`; the
classifier consumes it pure.

**TargetRepoProfile** (frozen dataclass): `repo: str` (slug as `gh` reports it),
`default_branch: str`, `visibility: str`, `queue_enabled: bool`,
`required_checks: tuple[str, ...]`, `declared_gates: tuple[str, ...]` (from the
repo's `factory.yaml`), `findings: tuple[Finding, ...]`, `passed: bool`.
**Finding**: `check: str` (slug, e.g. `visibility`, `merge_queue`,
`gate_check:test`, `factory_yaml`), `passed: bool`, `detail: str` (actionable —
names what to change, not just what is wrong).

**LandingConfig** (frozen dataclass, new field on `EpicInput`, defaults are code
defaults the operator overrides per epic): `merge_method: str = "squash"`
(passed to `gh pr merge --auto`; must match a method the repo allows),
`poll_interval_s: int = 60`, `stall_after_s: int = 7200`,
`max_recovery_cycles: int = 1` (FR-006's "one bounded cycle").

**NodeState amendments** (`factory/workgraph/models.py`): add `PR_OPEN`,
`ENQUEUED`, `MERGED` after `PASSED` (the architecture §1 lifecycle verbatim).
`PASSED` now means *verified, landing not terminal*; `MERGED` is the new
happy-path terminal. `NodeRecord` gains `verified: bool` (set once when the
ladder grants PASS, never unset) and `landing: Landing | None`. Dependency
gating (FR-009): a verified-gated edge unlocks on `record.verified`; a
merge-gated edge unlocks on `state == MERGED`. `_lock_out_dependents` treats a
landing that ends `KILLED`/`REJECTED`-final as unreachable for merge-gated
dependents only — verified-gated dependents already lawfully dispatched.

**`## Work Graph` grammar extension** (FR-009, additive — D-025 discipline, no
template fork): a story may declare `depends_on_merged: [USn, ...]` beside
`depends_on`. Validation: every entry a declared story, no self-reference, no
key in both lists (an edge gates on one thing), the union of both edge sets
acyclic. `WorkNode` gains `depends_on_merged: tuple[str, ...]`; `workgraph.json`
carries it; absent means empty (every existing graph stays valid). Default
gating is verified — `depends_on` semantics are unchanged.

## Approach by story

### US1 — the landing path (FR-001, 002, 003, 004, 009)

**gh command surface** (all run with `cwd` = target clone; `GhClient` is the only
code that spawns `gh`):

| operation | command | notes |
|---|---|---|
| find existing PR | `gh pr list --head factory/<epic>/<node> --state open --json number,url` | idempotency: reuse before create |
| open PR | `gh pr create --base <default> --head factory/<epic>/<node> --title <t> --body-file <f>` | ready, never `--draft`; body via file to dodge quoting |
| enqueue | `gh pr merge <n> --auto --<merge_method>` | the factory's ONLY merge invocation (FR-002) |
| poll | `gh pr view <n> --json state,isDraft,mergedAt,closedAt,mergeStateStatus,autoMergeRequest,statusCheckRollup` | → `PrSnapshot` |
| kill cleanup | `gh pr merge <n> --disable-auto` | best-effort on epic/node kill: a killed epic must not keep landing |

`GhClient` classifies failures into a small taxonomy (`GH_AUTH`, `GH_NOT_FOUND`,
`GH_REFUSED` with stderr tail, `GH_UNAVAILABLE`) so activities return refusals
as data — an enqueue rejected because the queue was disabled mid-flight is a
queue rejection routed to escalation, never a crash (spec edge case).

**Workflow landing phase.** On ladder PASS: salvage first (the commit is the
work's durable form, constitution VI), then `push_branch` (new `worktree.py`
helper: plain `git push origin <branch>`, refuses the default branch — FR-001's
structural guard; recovery syncs merge target-head *into* the branch, so pushes
stay fast-forward and force is never needed), then `open_landing_pr` →
`enqueue_landing` → `record.state = ENQUEUED`, `record.verified = True` at PASS.
The poll loop runs as a **workflow background task** (`asyncio.ensure_future`
inside the workflow — deterministic under Temporal) so the main sequential
scheduler continues: that is what lets two sibling nodes both be enqueued and
lets the queue, not the factory, order them (US1-S4). The main loop's exit
condition becomes "every node terminal AND every landing terminal"; worktree
removal moves from PASS-time to landing-terminal-time (recovery needs the tree).
Kill (`kill_epic`) cancels poll tasks, calls `disable_auto_merge` best-effort,
marks landings `KILLED`, branches preserved. Pause leaves polling running
(passive) but parks recovery dispatch. Sequential-attempt discipline survives:
only the main loop ever runs an agent attempt.

**Outcome classification** (pure, `classify.py` — the reconciliation answer to
FR-004 and every spec edge case; polling only, no webhooks, matching the D-011
no-public-endpoint posture):

| observation | outcome |
|---|---|
| `merged_at` set | `MERGED` — however it merged; a human merging manually is reconciled, not fought |
| `state == CLOSED`, not merged | `DEQUEUED_BY_HUMAN` — treated as operator kill; escalation notes the manual intervention |
| OPEN, auto-merge gone, `failing_required_checks` non-empty | `CHECKS_FAILED` |
| OPEN, `merge_state_status == DIRTY` (unmergeable) | `CONFLICT` |
| OPEN, auto-merge gone, no failing checks, not dirty | `DEQUEUED_BY_HUMAN` (the remaining known dequeuer; heuristic — flagged) |
| OPEN, auto-merge still requested | pending (`None`) — keep polling |
| pending beyond `stall_after_s` with no state change | `STALLED` → escalation, never a silent stall (SC-002) |

**PR body** (`messages.py`, pure): title `<epic>/<node>: <story title>`; body =
spec reference (feature + requirement keys), branch, attempt count, per-gate
results of the passing attempt, judge outcome or `judge_unavailable`, and the
landing's provenance line. No credential, proxy URL, or transcript path may
appear (public repo — architecture §10).

### US2 — rejection recovery (FR-005, 006, 007, 008)

Routing on a classified rejection, all inside the existing node-lifecycle
machinery (this is a new ladder *entrance*, not a new ladder):

1. **`CHECKS_FAILED`** → `sync_landing_branch`: fetch, then merge
   `origin/<default>` into the node branch in its worktree (merge, not rebase —
   the branch is pushed; history stays fast-forward). The helper returns the new
   effective `base_ref` (the merged-in target head) and the workflow carries it
   into re-verification, so 002's diff and the judge see only the node's own
   work (D-027 extended: recovery moves the branch point). Clean sync → the node
   re-enters the inner loop: fresh attempt with the queue rejection quoted in a
   landing-evidence prompt section (verbatim, 002's feedback discipline), full
   002 ladder authority, re-push + re-enqueue on PASS, `recovery_cycles += 1`.
2. **`CONFLICT`** (from the queue, or a sync that conflicts) → the `debugger`
   persona gets one bounded cycle in the node's worktree: fresh key (fresh
   alias, D-026), prompt carries the conflicted file list and queue history, the
   in-tree conflict markers are the work surface; then re-verify → re-push →
   re-enqueue.
3. **Exhaustion** — a recovery cycle that fails again, or `recovery_cycles ==
   max_recovery_cycles`, or `STALLED`, or an enqueue refusal → Telegram
   escalation through the existing `send_escalation`/`expire_escalation`
   activities and `escalation_resolved` signal, with the queue history rendered
   into the message and choices `[RETRY | KILL | PAUSE_EPIC]` (FR-007). `RETRY`
   grants one more recovery cycle; 1h silence or `KILL` → node `KILLED`,
   **branch preserved** (FR-008); `PAUSE_EPIC` parks the node and pauses the
   epic, exactly as the verification ladder's escalation does.
4. **`DEQUEUED_BY_HUMAN`** → merged manually: `MERGED`, proceed. Closed
   manually: operator kill semantics — node `KILLED`, branch preserved,
   escalation message notes the manual intervention (notify-only, no buttons).

Recovery agent attempts are scheduled by the main loop (one attempt in flight
factory-wide, ever); a pending recovery outranks pending fresh nodes — stranded
verified work is the more expensive kind of idle.

### US3 — target repo onboarding (FR-010)

Fact-gathering (activity) is separated from judgment (pure `onboard.py`):
`validate_target_repo` reads `gh repo view --json
visibility,defaultBranchRef`, `gh api repos/{owner}/{repo}/rules/branches/
{default}` (the `merge_queue` rule and `required_status_checks` contexts;
fall back to the classic branch-protection endpoint for required checks if the
rules list carries none — to be confirmed against the live API on first Tier 1
run, flagged), and the target clone's committed `factory.yaml` via the 002
loader (a malformed manifest is a failing finding, never a shrug). Pure checks,
each one `Finding`:

- repo is public (queue available on any plan, D-007);
- merge queue enabled on the default branch;
- every declared `factory.yaml` gate has a required check **named exactly after
  the gate** (`test`, `lint`, `typecheck` — the naming convention is the
  contract between `factory.yaml` and the repo's CI; flagged as a convention
  this plan sets);
- every required check maps back to a declared gate (an unknown required check
  fails — deterministic gates only is FR-003 made structural, and the LLM judge
  can therefore never be one);
- `factory.yaml` present, valid, non-empty `gates`.

Enforcement is structural (SC-005): `EpicWorkflow.run` calls
`validate_target_repo` before `resolve_graph` — a failing profile fails the epic
before any key is issued or worktree created. The operator preflight surface is
`factory-epic onboard <target-clone-path>` (a subcommand of the existing CLI,
not a new console script): prints every finding, `--json`, exit 0/1/2.

## Complexity Tracking

No constitution violations; table intentionally empty.
