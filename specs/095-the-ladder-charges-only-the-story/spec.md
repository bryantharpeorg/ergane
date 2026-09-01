---
state: landed
fixes:
# ATTESTED 2026-08-31 10:30 AM CT by the operator session, in away mode.
# All three stories are on ergane-buildout: US1 5f2208d (#393), US2 84ffa26
# (#397), US3 109ac89 (#410). Confirmed by `ergane spec landed <this dir>
# --default-branch ergane-buildout`, which observes all three.
#
# THE DEFECT THIS SPEC FIXES KILLED THIS SPEC. US3 was KILLED on 2026-08-31 after
# burning all four rungs — 09:49, 09:56, 10:03, 10:10Z — on an expired OAuth
# session, every stdout exactly 73 bytes, no agent ever starting, each rung still
# paying its full ~380s gate on an unchanged tree. That is occurrence 4 of the
# first finding below, which is the finding US1 and US2 were written to fix. The
# story was recovered by an operator `build reset` plus a re-dispatch once the
# credential was repaired, and passed on attempt 1.
#
# The fix has LANDED but is NOT YET PROVEN. Do not resolve that finding on the
# strength of this attestation — it needs a demonstration that a credential
# failure no longer spends a ladder rung.
  - agent/an-expired-subscription-oauth-session-burns-every-attempt-and-reports-it-as-an-empty-diff
  - verify/max-attempts-is-shadowed-by-max-judge-retries-and-nothing-on-screen-says-which-one-bound
# DRAFTED 2026-08-28 by the operator session, against ergane-buildout at 8bb2d4b.
# Slot reserved — empty and untracked — by the spec-routing session 2026-08-23.
#
# THE LADDER IS RIGHT. THE ACCOUNTING IS NOT. `next_action`
# (`factory/verify/ladder.py:177`) is a good state machine and this spec does not
# redesign it. It charges the story for two things that are not the story: an
# attempt in which no agent ever started, and a distinction the operator cannot
# see.
#
# HALF ONE — A FAILURE BEFORE THE FIRST TOKEN IS CHARGED AS AN ATTEMPT.
# `_attempts_spent` (`:231`) counts every record whose persona is not the
# debugger or the promotion persona. An expired subscription OAuth session
# produces a record just like any other: four attempts ran in thirteen seconds,
# each with a 73-byte stdout reading "Failed to authenticate: OAuth session
# expired and could not be refreshed", and no agent process ever started.
# Because nothing installed dependencies in the fresh worktree, all four gate
# runs then reported a typecheck FAIL with exit 127 and a missing binary — a
# signature that looks exactly like a broken build and names nothing about
# authentication. Four rungs of a six-rung ladder, spent in thirteen seconds, on
# a credential.
#
# THE EXCLUSION SHAPE ALREADY EXISTS. `_attempts_spent`'s docstring already
# argues that the debugger's cycle is excluded because "it is a rung of its own",
# and does the same for a promoted attempt. A pre-agent failure is the same
# argument from the other end: it is not a rung at all. This spec adds a third
# exclusion to a function that already has two and explains why it has them.
#
# HALF TWO — THE DIAL DOES NOT DO WHAT ITS NAME SAYS. `ladder: {max_attempts: 6,
# debugger_cycles: 3}` produced three implementer attempts, then three debugger
# cycles, then escalation. `next_action` grants a retry only if
# `attempts_left and not _judge_vetoes_a_retry(...)` (`:208`), and that veto is
# governed by `max_judge_retries`, whose default is 2. Sharper: the shadowing
# inverts the dial. `_judge_vetoes_a_retry` (`:293`) returns False outright when
# the latest failure carries no judge RETRY outcome, so `max_attempts` is live in
# exactly one regime — the failures the judge never saw, i.e. the deterministic
# ones. Raising it cannot lengthen the fight where an agent might converge, and
# lengthens it only where the same input is re-fed to the same persona. One story
# demonstrated it cleanly: six identical size refusals, then three debugger
# cycles re-running the same model — nine attempts producing one bit of
# information.
#
# THIS HALF IS NOT A LADDER CHANGE. The behaviour is defensible and 068 FR-002
# argues for it deliberately ("a distinction, not a wider number"). What is
# indefensible is that nothing on screen says which rung bound. `loop_summary`
# already carries it, in a place no operator looks.
#
# NOT IN SCOPE. This spec does not change what `_judge_vetoes_a_retry` decides,
# does not merge the two dials, does not add a fourth rung, and does not change
# how a credential is obtained or refreshed. It also does not fix the gate
# signature that follows a pre-agent failure — a typecheck failing on a missing
# binary in an uninstalled worktree is correct behaviour once the attempt itself
# is legible.
---

# Feature Specification: the ladder charges only the story

**Created**: 2026-08-28
**Depends on**: nothing outside this spec.

## The gap, stated precisely

The retry ladder exists to answer one question: has this node had enough chances
to build the story? It answers it with a count that includes attempts in which
the story was never attempted, and it reports its answer without saying which of
its three bounds produced it.

## The rule this spec is asking for

**An attempt that never reached the agent is not charged to the story, and an
exhausted ladder names the rung that ended it.**

### What this spec is not

It is not a redesign of the ladder. `next_action`'s precedence — grant, promote,
debugger, escalate — is correct and stays.

It is not a widening of `max_judge_retries` or a merge of the two dials. The
distinction between "the judge asked for a rewrite" and "a gate refused
deterministically" is deliberate and defensible. It is invisible, and that is
what this spec fixes.

It is not credential management. The factory does not obtain or refresh the
operator's session, and this spec does not give it that job.

## User Scenarios & Testing

### User Story 1 - A pre-agent failure says what it was (Priority: P1)

As an operator, an attempt that died on authentication tells me so, instead of
presenting as a broken build with a missing binary.

**Why this priority**: P1 and it depends on nothing. Until the failure is
distinguishable, US2 has nothing to key its exclusion on.

**Acceptance Scenarios**:

1. **Given** an attempt whose agent process never started because the session
   could not authenticate, **When** the attempt is recorded, **Then** its
   terminal reason names authentication rather than a generic agent error —
   proven by a committed test.
2. **Given** the same attempt, **When** the operator reads it through the CLI,
   **Then** the reason and the remedy are on screen without reading a transcript
   — proven by a committed test.
3. **Given** an attempt whose agent started and then failed, **When** it is
   recorded, **Then** its terminal reason is unchanged from today — proven by a
   committed test. The new reason is for the pre-agent case only.
4. **Given** a pre-agent failure, **When** the gate results are recorded,
   **Then** the record states that the gates ran against a worktree no agent
   prepared — proven by a committed test. A typecheck failing on a missing
   binary is correct; presenting it as the story's failure is not.

### User Story 2 - A pre-agent failure does not consume the attempt budget (Priority: P1)

As an operator, a dead credential costs one legible refusal, not my whole ladder.

**Why this priority**: P1. It is the measured cost — four rungs in thirteen
seconds — and the reason the escalation that followed offered a KILL for a
problem that was one `claude login` away.

**Acceptance Scenarios**:

1. **Given** a history of three pre-agent failures under a `max_attempts` of
   three, **When** the ladder is asked what happens next, **Then** it grants
   another attempt rather than escalating — proven by a committed test.
2. **Given** a history mixing pre-agent failures and real attempts, **When** the
   spent count is computed, **Then** only the real attempts are counted — proven
   by a committed test.
3. **Given** a history of only real attempts, **When** the spent count is
   computed, **Then** it is unchanged from today — proven by a committed test.
4. **Given** an unbroken run of pre-agent failures, **When** the ladder is asked
   what happens next, **Then** it escalates on its own bound rather than
   retrying forever — proven by a committed test. An exclusion without its own
   limit converts a burned ladder into an unbounded one, which is worse.
5. **Given** that escalation, **When** the operator reads it, **Then** it names
   authentication as the cause and does not offer KILL as its default — proven
   by a committed test.

### User Story 3 - An exhausted ladder names the rung that ended it (Priority: P2)

As an operator, when a node escalates I can see in one line which of the three
bounds was spent, without reading the source.

**Why this priority**: P2 — it changes no outcome — but it is what turns a
nine-attempt run producing one bit of information into a diagnosis.

**Acceptance Scenarios**:

1. **Given** a node that escalated with its judge rewrites spent, **When** the
   escalation text is read, **Then** it names that bound and its value — proven
   by a committed test.
2. **Given** a node that escalated with its deterministic attempts spent,
   **When** the escalation is read, **Then** it names that bound instead —
   proven by a committed test.
3. **Given** a node that escalated with its debugger cycles spent, **When** the
   escalation is read, **Then** it names that bound — proven by a committed
   test.
4. **Given** a running epic, **When** the operator asks for its status, **Then**
   the ladder's three dials are shown beside the landing dials — proven by a
   committed test.

## Work Graph

```yaml
US1:
  implements: []
  depends_on: []
US2:
  implements: []
  depends_on: []
  depends_on_merged: [US1]
US3:
  implements: []
  depends_on: []
  depends_on_merged: [US2]
```

US1 makes the failure distinguishable in the adapter and the record; US2 keys an
exclusion on that distinction in `factory/verify/ladder.py`; US3 renders what US2
decided. US2 and US3 both read the ladder's configuration and are serialised on
file ownership; US1 precedes US2 because US2 has nothing to key on without it.

## Requirements

- **FR-001**: An attempt whose agent process never started for an authentication
  reason MUST record a terminal reason that names authentication.
- **FR-002**: That reason and its remedy MUST be readable through the CLI without
  opening a transcript.
- **FR-003**: An attempt whose agent started MUST record the terminal reason it
  records today.
- **FR-004**: A record for a pre-agent failure MUST state that its gates ran
  against a worktree no agent prepared.
- **FR-005**: A pre-agent failure MUST NOT count toward the ordinary attempt
  budget.
- **FR-006**: Consecutive pre-agent failures MUST be bounded by a limit of their
  own and MUST escalate on it rather than retrying without end.
- **FR-007**: An escalation raised on consecutive pre-agent failures MUST name
  authentication as the cause and MUST NOT default to KILL.
- **FR-008**: An escalation MUST name which ladder bound was exhausted and its
  configured value.
- **FR-009**: The operator's status view MUST show the ladder's dials beside the
  landing dials.
- **FR-010**: Every story MUST leave `_judge_vetoes_a_retry`
  (`factory/verify/ladder.py:293`) and `next_action`'s precedence order
  unchanged.

## Success Criteria (summary)

- A dead credential produces one legible refusal naming the remedy, not four
  attempts in thirteen seconds and an escalation offering KILL.
- A node's remaining attempts are the attempts it can still spend on the story.
- An operator reading an escalation learns which bound ended the node from the
  escalation itself.
