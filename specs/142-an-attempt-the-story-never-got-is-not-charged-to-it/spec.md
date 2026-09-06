---
state: draft
fixes:
  - gates/concurrent-epics-collide-on-a-fixed-gate-port
  - ladder/operator-question-consumes-an-attempt
# DRAFTED 2026-09-04 by the refinement workflow (refinement-2026-09-04) from
# docs/triage-2026-09-03-ergane-web-round3.md § "an-attempt-the-story-never-got-is-not-charged-to-it"
# (lines 221-240), against ergane-buildout at 602a92c. Every `file:line` in
# spec.md and plan.md was read from that commit and verified to resolve to the
# symbol named, not recalled.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), against ergane-buildout at
# 602a92c: `feedback/pr-6-a-pre-agent-failure-is-not-an-attempt` withdrawn from
# `fixes:` and given the paragraph below, because 095 built its half and
# declined to close it and this spec disclaims its trigger; two chain-one
# anchors corrected in prose (`factory/verify/ladder.py:218` counts, it does not
# escalate; `factory/verify/gates.py:1625-1626` is the branch and the
# assignment); the measured-cost block now separates the cost 095 has already
# excluded from what these triggers carry; the answered-question record's
# verdict named as `FAIL` in the truth table, in FR-009 and in plan trap 7,
# because `AttemptRecord.verdict` has no default and a PASS lands the node
# unverified; US2-S5's fail-safe clause split out of the composed-string
# assertion it cannot be proven from; and the operator sequence rewritten onto
# readings that exist — `ergane build status --json`, never `ergane build
# attempts`, whose steps 1 and 4 named surfaces this tree does not have.
#
# REPAIRED 2026-09-05 (refinement-2026-09-04), against ergane-buildout at
# 602a92c, answering an adversarial review: the missing-`bwrap` reproduction is
# refuted and replaced — `factory/verify/gates.py:1346` — `_resolve_gate_executor`
# falls back to `SubprocessGateExecutor` when the binary is absent, so moving
# `bwrap` aside runs the gates on the host and refuses nothing, while the *agent*
# side hard-refuses (`factory/workgraph/adapter.py:675`) and pages exactly the
# credential-shaped escalation FR-008 forbids; chain one now names the
# `ToolchainError` arm as the production-reachable one and the missing-binary arm
# as a post-selection race, plan trap 13 carries the mechanism, and operator steps
# 1-2 were rewritten onto it. Second: there are THREE sites that append a
# verification-derived `AttemptRecord`, not one — `factory/workgraph/workflow.py`
# at 2095, 2885 and 4017 — so FR-013 and US2-S7 were added to set the reason at
# every one of them, and plan trap 14 reproduces the half-fix. Also: FR-004 now
# answers a MIXED result list (US1-S6), FR-007 states the dial's default and why
# it must sit above `max_attempts` (US2-S2/S4 assert through `exhausted_bound`,
# which can say *which* bound stopped a node where `next_action` cannot), US2-S1
# drops an assertion about a `termination` `AttemptRecord` does not carry, and one
# anchor gained the symbol form.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), against ergane-buildout at
# 602a92c, answering a second adversarial review. One blocking gap: FR-013 named
# three append sites and only two were asserted — US2-S1 proves the ladder loop
# and US2-S7 the recovery, while nothing held the operator's hand-back at
# `factory/workgraph/workflow.py:2885`, so a two-of-three diff passed every
# scenario in the trio while the declared row's own sentence stayed true on that
# path. US2-S8 and T018b close it, on the seam that already exists
# (`tests/test_external_completion.py:705` —
# `test_external_completion_fails_when_work_breaks_gates`), and trap 14 now cites
# both scenarios. Three minor ones: the C-70 paragraph below claimed US1/US2 end
# that row's charge while the paragraph above it said the boundary refusals have
# no dated sighting — reconciled, because `factory/verify/gates.py:753` —
# `_toolchain` resolves `uv` and `git` off the host, so a worktree that was never
# prepared does not produce the boundary's refusal and C-70's 127 stays charged by
# design (trap 2, US1-S3); FR-004 was silent on an empty gate-result list and now
# answers "it ran", fail-closed, with US1-S5 and T005 carrying the fourth case;
# and US4-S3 was provable by a do-nothing diff, so it is pinned against a
# parseable sibling in one test and T033 loses its `[P]`. One anchor the review
# called wrong was re-read and kept: `tests/test_sandbox_mount_set.py:133` is the
# `gates_module` line — 132 is the `adapter_module` one and 134 is blank, so the
# proposed move would have cited a blank line. The wording beside it was wrong,
# though: `tests/test_toolchain_discovery.py:131` — `PlantedHost` is a
# module-local helper class the new test imports, not a pytest fixture.
#
# WHERE THIS CAME FROM. Four sightings of one mechanism, from three independent
# corpora: the `ergane-web` round-2 hand-over (PR-6/N52), the `ergane-web`
# round-3 hand-over (the gate-port key and the operator-question key), and the
# wolfenstein-container corpus (C-70). In each of them the ladder counted a
# record as an attempt when no work was done. 095 built the exclusion —
# `AttemptRecord.pre_agent` — and wired it for exactly one trigger, an
# authentication failure before the first token. Every other trigger still burns
# a rung: a gate boundary that never started, an operator question the node was
# told to ask, an infrastructure refusal on the worker host. Fixing them
# separately would touch the same accounting function three times.
#
# WHAT IT COST, MEASURED. C-70: four attempts in seven seconds with a
# byte-identical gate tail, the escalation firing fifteen seconds after the
# first genuine failure, and nothing in the ladder, the store or the escalation
# text noticing that no work had been done. A second node on a second epic:
# attempts at 9m15s, then 14s, then 13s, same result each time. PR-6/N52: an
# expired subscription OAuth session consumed four rungs of a six-rung ladder in
# thirteen seconds. 095's own US3 was KILLED by this defect while it was being
# built — four rungs at 09:49, 09:56, 10:03 and 10:10Z, every stdout exactly 73
# bytes — and recovered only by an operator reset.
#
# WHAT THAT MEASUREMENT NO LONGER PROVES. Every figure above is one trigger: an
# expired subscription OAuth session, the agent dying before its first token.
# 095-US1/US2 landed on 2026-08-30 (5f2208d, 84ffa26) and 095-US3 on 2026-08-31
# (109ac89), and that trigger is now classified structurally
# (`factory/workgraph/adapter.py:1577`) and excluded from the count
# (`factory/verify/ladder.py:389`). So the block above measures what the class
# cost while it had no fix at all — not what these three triggers are burning
# today. The two boundary refusals have no dated sighting of their own: they are
# argued from the code path (`factory/verify/gates.py:583`,
# `factory/verify/gates.py:605`) rather than from an occurrence, and the
# operator-question row's real cost is the hole in the history rather than a
# rung (chain two). What is measured, still unfixed and still on the paging path
# is the escalation's silence about elapsed time — C-70's own surviving remedy,
# which is US4.
#
# NOT IN SCOPE. This spec does not give the gate boundary its own network
# namespace: `factory/verify/gates.py:885` — `_resolver_binds` documents why
# `/etc/resolv.conf` and `/etc/ssl` are bound, and `--unshare-net` without a
# userspace network turns every `uv sync` into a name-resolution failure that
# reads like a broken dependency. It does not allocate or arbitrate ports — a
# gate command that started and then could not bind one is a gate that ran, and
# the fixed port in the reporting repository lives in that repository's own
# `web/playwright.config.ts`. It adds no third `OverallVerdict`: an attempt whose
# gates never ran still fails. It does not re-open `Termination`, and it does not
# change what any gate runs.
#
# ONE KEY THE TRIAGE ENTRY LISTED IS DELIBERATELY NOT DECLARED.
# `verify/a-rung-that-does-not-re-dispatch-and-a-rung-whose-agent-dies-in-two-seconds-both-count-as-attempts-so-a-four-attempt-budget-becomes-one`
# (critical, open, occurrences 1) is the C-70 row, and what this spec gives it is
# less than the first draft of this paragraph claimed. That row's chain runs
# agent-dies -> worktree never prepared -> "the gate found no toolchain and exited
# 127" -> the gate failure is charged. US1 and US2 end that charge only where the
# 127 came from the boundary's **own** refusal (`factory/verify/gates.py:583`,
# `factory/verify/gates.py:605`). C-70's 127 is attributed to neither, and cannot
# be on the reading trap 2 mandates: `factory/verify/gates.py:753` — `_toolchain`
# resolves `uv` and `git` off the *host*, which an agent dying in two seconds does
# not disturb, so a gate command that exited 127 inside a worktree that was never
# prepared is a command that RAN and must keep costing a rung — US1-S3 exists to
# fail any diff that excuses it. What this spec does deliver for that row is US4,
# the elapsed-time sentence its own notes ask for by name; the trigger it actually
# measured, the expired credential, is 095's and is already excluded at
# `factory/verify/ladder.py:389`. Its second surviving remedy — "refuse to
# re-verify an unchanged tree: the branch tip is one rev-parse away" — is unbuilt
# here. Declaring the key would close a `critical` row on part of a fix, which
# this floor has now recorded three times (100, 092, 118). It stays open and is
# named here so the next author can see what is left. The row's first half, "a
# rung that does not re-dispatch", was already refuted by the reporter's own
# disconfirming test: transcripts exist for every attempt.
#
# THE GATE-PORT KEY IS DECLARED FOR ITS ACCOUNTING HALF, WHICH IS ALL OF IT THAT
# SURVIVED. `gates/concurrent-epics-collide-on-a-fixed-gate-port` is refuted by
# its own later occurrences: 3-5 record `max_concurrent_nodes=1`, the failure
# windows are disjoint, and the port lives in a target-repo file. Its ledger note
# already carries that correction and states what remains — "a boundary gate that
# never started is still recorded as a FAIL and still charges the node a rung",
# which is exactly FR-001 through FR-005 plus FR-013 — FR-013 because "the node"
# is charged at three append sites and a fix wired to one of them would leave the
# sentence true on the other two. A spec cut from the key's literal name would
# have built port arbitration and fixed nothing.
#
# A THIRD KEY THE FIRST DRAFT DECLARED IS WITHDRAWN.
# `feedback/pr-6-a-pre-agent-failure-is-not-an-attempt` (info, open) was in the
# first draft's `fixes:` and is not in this one. Its summary asks for "a terminal
# reason for pre-agent failure that does not consume the attempt budget, is
# surfaced in status, and names the remedy", and its notes fix the scenario as
# N52: an expired subscription OAuth session that consumed four rungs in thirteen
# seconds without ever starting an agent. Every clause of it is the credential
# trigger — the one this spec explicitly disclaims, since FR-005 refuses to set
# `AttemptRecord.pre_agent` or to classify the boundary case
# `Termination.PRE_AGENT_FAILURE` on the ground that the agent did start. 095
# built that half: its sibling row
# `agent/an-expired-subscription-oauth-session-burns-every-attempt-and-reports-it-as-an-empty-diff`
# is resolved on `095-the-ladder-charges-only-the-story`, and 095's own
# attestation declines to close PR-6 — "the fix has LANDED but is NOT YET PROVEN.
# Do not resolve that finding ... it needs a demonstration that a credential
# failure no longer spends a ladder rung." Nothing here produces that
# demonstration, and no FR here puts a reason on the rendered status line, which
# is the row's second clause. Declaring it would close an open row on a fix made
# elsewhere and never proven — the same shape the paragraph above refuses for the
# critical key, and the one this floor has now recorded three times (100, 092,
# 118).
#
# WHAT THE ANCHORS SAID WHEN RE-READ. Every citation in the triage entry and in
# the two new ledger rows was re-read at 602a92c. Two were wrong in the dangerous
# way — they point at real, plausible code and say something that is not true of
# it, which no validate layer can catch.
#
# ONE: the entry and BOTH new ledger rows name `charged_attempts` at
# `factory/verify/ladder.py:386-390`. THERE IS NO SUCH SYMBOL, and there never
# was — `git log -S charged_attempts -- factory/verify/ladder.py` returns nothing.
# The function is `_attempts_spent`, the lines are right, the name is invented.
# An implementer grepping the entry's name finds an empty tree and concludes the
# mechanism has to be built. Plan trap 1 exists for that.
#
# TWO: the entry says "gates.py:757-763 returns exit_code=127 for a missing bwrap
# binary and the toolchain discovery at :770-774 refuses the same way". Those
# lines are the *docstring* and the `resolve_toolchain` call of
# `factory/verify/gates.py:753` — `BwrapGateExecutor._toolchain`; neither returns
# anything with an exit code. The two 127 refusals this spec turns on are at
# `factory/verify/gates.py:583` and `factory/verify/gates.py:605`, and only the
# second involves the toolchain at all.
#
# Everything else the entry claimed held on re-reading, including
# `factory/verify/gates.py:1623-1626` mapping any non-zero exit to FAIL,
# `factory/verify/models.py:962-964` requiring every result to be PASS,
# `factory/verify/models.py:76` and `factory/verify/factory_yaml.py:1103`
# reserving CONFIG_ERROR, and `concurrent_gates` having no reader anywhere in the
# verdict path. No commit has touched any file this spec edits since 2026-09-02,
# so there are no neighbour landings to route around.
---

# Feature Specification: an attempt the story never got is not charged to it

**Created**: 2026-09-04
**Depends on**: nothing.

## The gap, stated precisely

The ladder spends a rung whenever a record lands in a node's history, and three
different events put a record there without anything having been attempted of the
story.

**Chain one — the boundary that never started.**

1. The gate boundary refuses before it runs anything, in two arms. Toolchain
   discovery refuses at `factory/verify/gates.py:605` — raised when `uv` or `git`
   cannot be resolved, or when a system path can be neither mirrored nor bound —
   and the sandbox backend binary is refused missing at
   `factory/verify/gates.py:583`. Both return an outcome carrying `exit_code=127`
   and the reason in its output, deliberately: the code beside them calls it "a
   127 outcome carrying the reason, not an exception the gate runner has no place
   to put". The two arms are **not** equally reachable, and the difference decides
   how this is reproduced. Production selects the backend through
   `factory/verify/gates.py:1346` — `_resolve_gate_executor`
   (`factory/activities/verify_activities.py:280` is the call), which returns a
   `SubprocessGateExecutor` (`factory/verify/gates.py:1366`) unless the binary is
   present (`factory/verify/gates.py:1364`). So the toolchain arm is the live one;
   the missing-binary arm is a post-selection race, or an executor a caller
   injected. Removing `bwrap` does not produce it — see "What this spec is not".
2. `factory/verify/gates.py:1625-1626` tests **any** non-zero exit and maps it
   to `GateStatus.FAIL` with no branch on why, inside
   `factory/verify/gates.py:1583` — `_to_result`, the single line every backend's
   outcome passes through. From here on, a boundary that never started is
   indistinguishable from a suite that ran and failed.
3. `factory/verify/models.py:950` — `gates_passed` requires every result to be
   `PASS`, so the attempt's verdict is FAIL. That part is correct and stays:
   nothing was checked, so nothing may land.
4. The workflow appends the attempt's history record with exactly one exclusion
   flag, `factory/workgraph/workflow.py:2109`, which reads
   `pre_agent=termination == Termination.PRE_AGENT_FAILURE`. That is False here:
   `Termination.PRE_AGENT_FAILURE` (`factory/usage/models.py:68`) means no agent
   turn ever ran, and in this chain the agent ran and produced a diff. That append
   is not the only one: `factory/workgraph/workflow.py:2885` —
   `_apply_external_completion_if_present` and `factory/workgraph/workflow.py:4017`
   — `_recovery_attempt` each run the same gates on the same host and append their
   own record, under the node's own persona (`factory/workgraph/workflow.py:3910`
   raises the attempt number under a comment reading "a recovery is an attempt
   too"). All three are counted by step 5, so a fix wired to one of them leaves the
   defect standing on the other two — FR-013.
5. `factory/verify/ladder.py:389` counts every record that is not the debugger's,
   not the promotion persona's and not `pre_agent`, inside
   `factory/verify/ladder.py:368` — `_attempts_spent`. So the rung is spent on a
   verdict that measured nothing: `factory/verify/ladder.py:218` compares that
   count with the allowance, and once it is no longer under it the node falls
   past the RETRY branch to `factory/verify/ladder.py:240`, the
   `NextAction.ESCALATE` that ends it.

**Chain two — the question the node was told to ask.** An attempt whose final
message carries the operator-question marker is reclassified at
`factory/workgraph/workflow.py:1949` and parks. When the operator answers,
`factory/workgraph/workflow.py:2058` records the exchange and the loop
`continue`s to `factory/workgraph/workflow.py:1815`, which increments
`record.attempt` — while the comment at `factory/workgraph/workflow.py:2053` says
in the tree's own words that no history record is appended. **The number moves and
the history does not.** The ordinary allowance is genuinely preserved, so the
ledger row's harshest reading is wrong; what is real is that every surface
rendering "attempt N" now over-reports, and the ladder's history has a hole
exactly where the pause was, which is why the reporting repository read its own
node as one rung down. This spec closes the hole and leaves the number alone:
`record.attempt` is part of the evidence store's upsert key
(`factory/verify/store.py:260`), so the rendered `attempt N` goes on counting
dispatches and no story here adds a reason token beside it.

**Chain three — the escalation cannot tell the operator which it was.**
`factory/notify/messages.py:531`, inside `factory/notify/messages.py:529` —
`_render_attempt`, renders `Attempt {n} — {verdict}` and a per-gate duration, and
nothing else about time. "Attempt 4 of 4" and "attempt 4 of 4, three of them in
seven seconds" call for opposite decisions and render identically today — even
though `factory/verify/models.py:937` and `factory/verify/models.py:938` already
carry each attempt's start and finish.

The three chains meet in one function. Fixing them separately would edit
`_attempts_spent` three times.

## The rule this spec is asking for

**A record enters a node's history for every attempt, but only an attempt in which
the story was actually attempted spends a rung — and a record that spends no rung
says why, rather than being absent.**

The cases, complete:

| what happened | gate results | verdict | rung spent |
|---|---|---|---|
| the gate ran and failed | `FAIL` | FAIL | **yes — unchanged** |
| the gate timed out, or dirtied the worktree | `TIMEOUT` / `DIRTIED_WORKTREE` | FAIL | **yes — unchanged** |
| the manifest was unusable | `CONFIG_ERROR` | FAIL | **yes — unchanged**, the repository under test is what broke |
| the boundary never started a gate | **new status** | FAIL | **no**, and bounded on a dial of its own |
| no agent turn ever ran | as today | FAIL | no — 095, unchanged |
| the operator answered a question | none ran | FAIL † | **no, and the history now says so** |
| the question expired unanswered | none ran | FAIL | **yes — unchanged** (008-US2) |

† `FAIL`, not a blank and not a third verdict: `AttemptRecord.verdict`
(`factory/verify/models.py:1264`) has no default, so the appended record must
carry one, and `factory/verify/ladder.py:209` returns `NextAction.PASSED` the
moment the last record reads `PASS` — a record written `PASS` to mean "nothing
failed here" would land the node with nothing verified. The record is uncharged,
not un-failed; the reason field is what makes it uncharged.

### What this spec is not

It is not a relaxation of the verdict. A gate that never ran keeps the attempt at
FAIL, because `gates_passed` refuses anything that is not `PASS` and this spec does
not touch it. Nothing lands that would not have landed before.

It is not a second use of `pre_agent`. That flag is a claim about the agent, it is
persisted, and it is what `factory/verify/ladder.py:311` uses to tell the operator
to re-authenticate. Setting it for a boundary whose toolchain would not resolve
would page the operator about a credential that is fine.

It is not port arbitration and not a network change to the boundary. A gate
command that started and then failed to bind a port is a gate that ran; the
platform may only exclude the refusals it issued itself, before the command.

It is not reproduced by removing `bwrap`. That is the tempting experiment and it
demonstrates the opposite: with the binary gone, `factory/verify/gates.py:1346` —
`_resolve_gate_executor` hands verification a `SubprocessGateExecutor`, the gates
run on the host and pass or fail normally, while the *agent* launch refuses at
`factory/workgraph/adapter.py:675` — "never a silent fallback to the host launch"
(`factory/workgraph/adapter.py:1207` — `_resolve_backend`) — and the node pages on
`max_pre_agent_failures`, which is the credential-shaped escalation FR-008 exists
to forbid. The refusal this spec is about is reached with the boundary's binary in
place and its toolchain unresolvable.

It is not a new `OverallVerdict` and not a new `Termination`.

It is not a new operator rendering. The reason field travels to the operator on
the plumbing that exists: `factory/workgraph/workflow.py:895` puts the whole
ladder history in the status query document and
`factory/cli/nouns/build.py:1175-1188` copies that document and prints it as
JSON, so `ergane build status <epic> --json` reads every record's reason the
moment it is written. The rendered line
(`factory/cli/nouns/build.py:503`) still prints only `attempt N`, and `ergane
build attempts` still prints no gate row at all
(`factory/cli/nouns/build.py:1390`). Neither gains a reason token here.

## User Scenarios & Testing

### User Story 1 - A boundary that never started is not a gate that failed (Priority: P1)

As the ladder, I can tell a suite that ran and failed from a boundary that never
got as far as running it, without reading an exit code that both can produce.

**Why this priority**: P1 and it depends on nothing. Every other story about the
gate half needs a fact that does not exist yet. It is also the half that must not
change any verdict, so it is the safest thing to land first.

**Independent Test**: Build a gate result from an outcome the boundary refused, and
one from a command that ran and exited non-zero, and read the two statuses.

**Acceptance Scenarios**:

1. **Given** a gate boundary whose sandbox backend binary is absent, **When** a
   declared gate is run through it, **Then** the executor's outcome records that
   the command never started as a field of its own, and a committed test asserts
   that field rather than inferring it from the exit code.
2. **Given** an outcome flagged as never started, **When** it is turned into a gate
   result, **Then** the result carries a `GateStatus` distinct from `FAIL`,
   `TIMEOUT`, `CONFIG_ERROR` and `DIRTIED_WORKTREE`, and keeps both the boundary's
   own refusal text and its exit code, proven by a committed test.
3. **Given** a gate command that ran and exited 127 of its own accord, **When** it
   is turned into a gate result, **Then** it is `FAIL` exactly as today — the diff
   shows the new branch keying on the outcome's field and not on the exit code, and
   a committed test pins the two cases side by side so a branch on `127` cannot
   pass.
4. **Given** a result list holding only the never-started status, **When** the
   deterministic half is composed, **Then** `gates_passed` is False and the
   attempt's verdict is FAIL, asserted by a committed test, because nothing was
   checked and nothing may land.
5. **Given** result lists holding, in turn, the never-started status, a `FAIL`, a
   `CONFIG_ERROR` and no gate results at all, **When** the new predicate is asked
   whether the boundary ever ran a gate, **Then** it answers "never ran" for the
   first only, and a committed test asserts all four answers — a `CONFIG_ERROR` is
   a fact about the repository under test, which the attempt itself may have
   broken, and an empty list is evidence that is missing, which this module charges
   rather than excuses.
6. **Given** a result list holding one never-started result **and** one `FAIL` from
   a gate that ran, **When** the predicate is asked, **Then** it answers "it ran",
   asserted by a committed test, because one gate that started is a gate that
   started — a predicate written `any(never started)` would hand a genuine gate
   failure a free, uncharged retry.

### User Story 2 - The ladder does not spend a rung on a verdict that measured nothing (Priority: P1)

As an operator, a worker host that cannot start a gate does not silently convert my
four-attempt allowance into one.

**Why this priority**: P1. This is the story that ends the measured cost, and it
carries its own limit in the same change so no landed commit ever holds the
exclusion without the bound that stops it looping.

**Independent Test**: Drive the ladder over a history of records flagged
boundary-refused and read what it decides, and read the sentence its escalation
composes.

**Acceptance Scenarios**:

1. **Given** an attempt whose gate results say the boundary never ran, **When** the
   history record is appended, **Then** the record carries a reason field naming
   the boundary and leaves `pre_agent` False, proven by a committed test that also
   asserts `pre_agent_failures_spent` reads zero over that history — the assertion
   that fails if the implementer took the shortcut of reusing the credential flag.
2. **Given** a history of three such records and an ordinary allowance of three,
   **When** the ladder is asked what happens next, **Then** the ordinary allowance
   still reads as unspent **and** `exhausted_bound` names no bound at all,
   asserted by one committed test over both, because `next_action`'s return value
   cannot say *which* bound stopped a node and `exhausted_bound` can.
3. **Given** a history whose records are one boundary refusal, one ordinary FAIL
   and one more boundary refusal, **When** the ladder is asked, **Then** the
   ordinary allowance counts exactly one, so the exclusion is a property of each
   record rather than of the run, asserted by a committed test.
4. **Given** a history of consecutive boundary refusals reaching the declared
   limit, **When** the ladder is asked, **Then** it returns ESCALATE rather than
   RETRY **and** `exhausted_bound` names the new dial rather than `max_attempts`,
   asserted by a committed test over both, because a host that will never run a
   gate must stop rather than retry forever and must say which dial stopped it.
5. **Given** that escalation, **When** its bound sentence is composed, **Then** it
   names the new dial and the boundary and names neither the credential nor
   `max_pre_agent_failures` — the three asserted by a committed test over the
   composed string — and the workflow passes the same non-destructive fail-safe
   default the pre-agent limit passes at `factory/workgraph/workflow.py:2146`,
   asserted by a committed test over that call, which the composed string never
   carries.
6. **Given** a manifest declaring the new ladder dial and a manifest declaring none,
   **When** each is loaded, **Then** the first parses and the configuration carries
   the declared value while the second parses to the shipped default, asserted by
   one committed test holding both, so the dial is real in the manifest and not
   only in the dataclass. The default the second reads is greater than the default
   `max_attempts` of 3.
7. **Given** a node driven to a recovery attempt (`factory/workgraph/workflow.py:4017`
   — `_recovery_attempt`) whose scripted gate results say the boundary never ran,
   **When** its history record is appended, **Then** that record carries the same
   reason field the ladder loop's record carries and the ordinary allowance does not
   move, asserted by a committed test driving the scripted world at
   `tests/test_rung_resolves_its_own_model.py:183` —
   `test_a_clean_resync_recovery_keeps_the_nodes_own_persona_and_model`, because a
   fix wired to one of the three append sites leaves the defect standing on the
   other two.
8. **Given** a node the ladder has already exhausted whose branch the operator then
   hands back (`factory/workgraph/workflow.py:2837` —
   `_apply_external_completion_if_present`), and whose scripted gate results for
   that hand-back say the boundary never ran, **When** the record at
   `factory/workgraph/workflow.py:2885` is appended, **Then** it carries the same
   reason field the ladder loop's record carries and the ordinary allowance counts
   only the genuine attempts that preceded it, asserted by a committed test driving
   the scripted world at `tests/test_external_completion.py:705` —
   `test_external_completion_fails_when_work_breaks_gates`, because a diff that
   wires two of the three append sites passes every other scenario here while the
   declared row's own sentence stays true on the third.

### User Story 3 - An answered question leaves a record, not a hole (Priority: P2)

As an operator, a node that obeyed its standards document and stopped to ask me
something does not read afterwards as a node that has already spent a rung.

**Why this priority**: P2. It reuses the reason field US2 adds, and it is the
smallest of the three: one branch in the question path, and the history stops
disagreeing with the attempt number.

**Independent Test**: Answer a parked question in a driven workflow and read the
node's history and the ladder's decision; then let one expire and read both again.

**Acceptance Scenarios**:

1. **Given** a node parked on an operator question that the operator answered,
   **When** the loop resumes, **Then** the history holds a record for the parked
   attempt whose reason field names the pause and whose verdict is
   `OverallVerdict.FAIL`, asserted by a committed test — today the history holds
   nothing at all for that attempt while its number has already advanced.
2. **Given** that history, **When** the ladder is asked what happens next, **Then**
   the ordinary allowance reads exactly as it did before the question, asserted by
   a committed test over the accounting function, so obeying a stop-and-ask still
   costs no rung.
3. **Given** a node whose question expired unanswered, **When** the loop resumes,
   **Then** the charged FAIL record it appends today is unchanged and still counts
   toward the ordinary allowance, asserted by one committed test that pins the
   answered and the expired path side by side, because 008-US2 charges an expiry on
   purpose.

### User Story 4 - The escalation says how long each attempt took (Priority: P3)

As an operator holding a page at 3am, I can see from the message itself whether
those four attempts were four fights or four seconds.

**Why this priority**: P3 and independent of the other three — it renders facts the
result already carries. It is the difference between a page that is answerable and
one that requires opening the evidence store.

**Independent Test**: Render an escalation history from results whose stored
timestamps are known, and read the rendered text.

**Acceptance Scenarios**:

1. **Given** a verification result whose stored start and finish timestamps differ
   by a known amount, **When** the attempt is rendered into an escalation history,
   **Then** the attempt's line states exactly that difference, proven by a committed
   test asserting the rendered string — computed from the two stored values and
   from no clock read, which the same assertion proves because any clock reading
   would produce a different number.
2. **Given** four results whose first start and last finish are seven seconds
   apart, **When** the history is rendered, **Then** it carries one further line
   stating the span across all four, proven by a committed test on the rendered
   text, so four attempts that did no work read differently from four that did.
3. **Given** two results rendered side by side — one whose stored timestamps cannot
   be parsed and one whose can — **When** the history is rendered, **Then** the
   first attempt's line carries no elapsed clause and nothing is raised while the
   second's states its elapsed time, asserted by one committed test over both,
   because this renderer sits on the paging path and a page that raises is a page
   that never arrives — while an omission asserted on its own also passes a diff
   that renders no elapsed time anywhere.

## Functional Requirements

- **FR-001**: An executor that refused before running the gate command MUST report
  that fact structurally on its outcome, as a field of its own, never by an exit
  code — a command that ran can exit 127 too.
- **FR-002**: A gate result built from such an outcome MUST carry a `GateStatus`
  distinct from `FAIL`, `TIMEOUT`, `CONFIG_ERROR` and `DIRTIED_WORKTREE`, and MUST
  keep the boundary's own refusal text and its exit code.
- **FR-003**: `gates_passed` (`factory/verify/models.py:950` — `gates_passed`) MUST
  keep refusing that status so the attempt's verdict stays FAIL, and MUST NOT be
  edited; every existing status MUST keep the verdict it produces today.
- **FR-004**: A named predicate over a result's gate results MUST answer whether the
  boundary ever ran a gate, and MUST answer "it ran" for `CONFIG_ERROR`, so no
  caller re-derives the fact from an exit code or from message text. It MUST answer
  "never ran" only when **no** result in the list records a command that started, so
  a list mixing a boundary refusal with a gate that ran and failed stays charged.
  A list holding **no** gate results at all MUST answer "it ran": fail-closed is
  this module's rule wherever the evidence is missing
  (`factory/verify/gates.py:1620`), and an empty list read as "never ran" would
  hand an uncharged rung to the one shape `factory/verify/models.py:950` —
  `gates_passed` already documents as not green.
- **FR-005**: An attempt whose gates never ran MUST NOT count toward the ordinary
  attempt allowance, decided by a predicate of its own; it MUST NOT set
  `AttemptRecord.pre_agent` (`factory/verify/models.py:1273`) and MUST NOT be
  classified `Termination.PRE_AGENT_FAILURE`, because the agent did start.
- **FR-006**: A history record that spends no rung MUST name the reason it spent
  none, so the ladder's history distinguishes an uncharged record from an absent
  one, and one field MUST serve every such reason rather than a new flag per
  trigger.
- **FR-007**: Consecutive boundary refusals MUST be bounded by a limit of their own,
  declarable in the manifest beside the other ladder dials, so a host that will
  never run a gate escalates instead of retrying forever. Its shipped default MUST
  be greater than the default `max_attempts` of 3 — 4, for the reason
  `factory/verify/models.py:1206` gives for `max_pre_agent_failures`: a default at
  or below the ordinary allowance escalates at the same rung the ordinary allowance
  would have, which makes the exclusion unobservable and US2-S2 unprovable.
- **FR-008**: The escalation raised on that limit MUST name that dial and the
  boundary through `factory/verify/ladder.py:270` — `exhausted_bound`, MUST NOT
  attribute it to the credential, and MUST carry the same non-destructive fail-safe
  default the pre-agent limit carries at `factory/workgraph/workflow.py:2146`.
- **FR-009**: An operator question the operator answered MUST append a history
  record carrying `OverallVerdict.FAIL` and the same reason field FR-006
  introduces, naming the pause, and that record MUST NOT count toward the
  ordinary attempt allowance. `FAIL` because `AttemptRecord.verdict`
  (`factory/verify/models.py:1264`) has no default and a record written `PASS`
  would land the node unverified at `factory/verify/ladder.py:209`.
- **FR-010**: A question that expired unanswered MUST keep appending the charged
  FAIL record it appends today at `factory/workgraph/workflow.py:2040`, still
  counted, and a committed test MUST assert it.
- **FR-011**: The escalation's attempt history MUST state each attempt's elapsed
  time, computed from `factory/verify/models.py:937` and
  `factory/verify/models.py:938` and from no clock read at render time.
- **FR-012**: A history holding more than one attempt MUST also state the span from
  the first attempt's start to the last attempt's finish, and a timestamp the
  renderer cannot read MUST make it omit the line rather than raise.
- **FR-013**: Every site that appends a verification-derived `AttemptRecord` MUST
  set that reason from one shared derivation over the result's gate results —
  `factory/workgraph/workflow.py:2095` (the ladder loop),
  `factory/workgraph/workflow.py:2885` — `_apply_external_completion_if_present`
  and `factory/workgraph/workflow.py:4017` — `_recovery_attempt` — so the exclusion
  is a property of the record wherever the record is written, and no site may
  re-derive it from an exit code or from message text.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005, FR-006, FR-007, FR-008, FR-013]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-009, FR-010]
US4:
  depends_on: []
  concurrent_with: [US1, US2, US3]
  implements: [FR-011, FR-012]
```

Two `depends_on_merged` edges, declared rather than left inferred (069-US2
FR-007), and both buy correctness of sequencing on a shared file rather than
freedom from contention. US2 reads the status and the predicate US1 adds to
`factory/verify/models.py`, and both stories edit that file, so the edge is real
twice over. US3 sets the reason field US2 adds to `AttemptRecord` and edits
`factory/workgraph/workflow.py`, which US2 also edits at three separate append
sites (FR-013), so the same argument applies one step later and with more force;
without the field US3 has nothing to write. US4 is on no
edge at all: it touches `factory/notify/messages.py` alone, reads two fields that
already exist on every stored result, and could land first, last or in the middle
without changing what the other three do — which is why it carries the lowest
priority and not a dependency. `concurrent_with: [US1, US2, US3]` is the author's
override of the contention edges the compiler infers from citations rather than
from edits: US4's tasks *cite* `factory/verify/models.py` for the two timestamp
fields they read and `factory/workgraph/workflow.py` for the format those
timestamps are written in, while US1, US2 and US3 *edit* those files. The slices
name a file in common and touch no line in common, so the override is the
declaration that they may run together.
