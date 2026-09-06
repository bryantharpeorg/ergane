---
state: draft
depends_on_landed: [008-operator-channel, 009-roadmap-scheduler, 041-escalation-workflow, 079-a-pressed-button-does-what-it-says, 101-the-sandbox-is-portable-and-sealed, 126-a-killed-node-leaves-no-ref-to-collide-with]
# HELD BACK TO DRAFT 2026-08-19 7:15 AM CT at the operator's instruction, so the
# roadmap could be resumed for the 059-064 on-ramp set without picking this spec
# up first. Nothing about the rescope below is withdrawn -- this is a scheduling
# hold, not a rejection.
#
# The reason it cannot ride an unattended roadmap: a peer park that reuses 008's
# operator park pauses the scheduler and deadlocks the answering peer. FR-016
# forbids that construction, but forbidding it in the spec is not the same as
# observing that the implementation avoided it, and a judge PASS cannot tell the
# difference -- the deadlock is a runtime property of two workflows, and the
# judge sees one diff. This spec needs an operator watching a live run.
#
# Flip back to `ready` in a session that can watch it.
#
# RESCOPED 2026-08-18 5:45 PM CT on two operator decisions taken together, after
# he asked "what other agents would we reach out to? could we set up a team
# lead / architect agent that looks at the work tree as the agent has been
# working on it, to see if it can answer the agent's question?"
#
#   1. CONSULTS MOVE SECOND. At the configured concurrency of 1 there is at most
#      one node running, so "a peer in the same epic" almost always means a peer
#      that is NOT running -- which is US1's next-prompt path, one dispatch per
#      exchange. The addressee class that actually answers at cap 1 is a persona
#      consult, and `architect` already exists in personas.yaml. So US5 takes a
#      merge-edge on US1 and everything else follows it. The old ordering put
#      the spec's only cap-1-useful story fourth.
#   2. A CONSULT READS THE ASKER'S WORKTREE, read-only, live. The plan's v0 gave
#      consults no worktree and assembled context from the spec and plan -- so
#      the architect would have answered from the plan rather than from the code
#      the implementer had actually written, which is the opposite of what was
#      asked for. FR-018 is new and states the grant and its bound.
#
# --- prior chain ---
# RELEASED 2026-08-17 3:20 PM CT by the operator, at a keyboard. The hold below
# named exactly one condition -- "flip it then; nothing else about this spec
# needs doing" -- and that condition is now met: the operator is present and
# will watch the first peer exchange happen for real. The roadmap schedule is
# also still paused, so `ready` does not hand this to an unattended scheduler.
# The watched-run requirement in the plan still stands and is now the operator's
# to honour, not a flag's.
#
# --- the 2026-08-16 hold this releases, kept for the chain ---
# HELD AGAIN 2026-08-16 ~10:35 PM CT, and this time the reason is the roadmap
# rather than the spec. The spec itself is ready: `ergane spec validate` passes
# all six layers, US2's missing task phase is repaired, every anchor was
# re-read. What changed is that the roadmap scheduler is about to be unpaused,
# and it dispatches whatever is `ready` on a five-minute cadence without asking.
#
# This epic's plan carries a WATCHED RUN as a dispatch condition -- its worst
# failure mode is a peer park that deadlocks the epic that must answer, which
# every scripted test passes through and no judge reading a diff can catch. An
# unattended scheduler is precisely the thing that condition forbids.
#
# `state: ready` is the only channel the scheduler reads. There is no "ready,
# but only by hand" -- so the flag goes back to `draft` until the operator is
# at a keyboard to watch the first peer exchange happen for real. Flip it then;
# nothing else about this spec needs doing.
# HELD, deliberately — refined 2026-08-08 ~1:10 AM CT but NOT dispatched, at the
# operator's call, because its worst failure mode is one the judge cannot catch.
# The verification pass found that a peer-addressed park would have reused 008's
# operator park, which raises the scheduler's pause flag — and the node that must
# answer a peer question is a node of the same epic, so the pause prevents the
# very dispatch that would answer it. Every peer question would have dead-waited
# the 8h window and then paged the operator, making SC-001's headline claim
# ("zero operator messages") false in production while every scripted test
# passed. FR-016 now forbids that pause. A defect of that shape, inside a
# thousand-line diff, is exactly what the judge's diff-size gap misses — hence a
# watched run rather than an unattended one.
# Also corrected: US1 split into US1 (routing, no adapter change) + US2
# (in-flight delivery, which needs a new adapter direction the original story
# never named), with the rest renumbered; US5 chained on US3 rather than
# parallel, since both edit the same degradation ladder; FR-006 reworded so the
# requirement stops dictating the D-021 banned word into the implementer's
# prompt; FR-004 reconciled with the consult rung FR-013 added; FR-007's
# RFC-2119 inversion fixed; FR-017 added so an external peer's reply arrives as
# attributed advisory text — an outbox is a host directory anyone can write, so
# its content is untrusted input reaching a model's context.
# Drafted 2026-08-08 from the operator's request: agents should be able to
# talk to each other — an instance of claude code messaging another instance
# of claude code — for escalations and coordination, including a named
# external agent (the homelab operator agent in ~/code/homelab). Options
# considered and decided in § Decision: Temporal signals over A2A over MCP.
# Numbered 017: 010–014 reserved for audit-triage epics, 015 doctor, 016 delta.
#
# REFINED 2026-09-04 by the refinement workflow (refinement-2026-09-04); every
# anchor in spec.md, plan.md and tasks.md re-read from ergane-buildout at
# 602a92c. The spec STAYS HELD: the hold above is a runtime condition and this
# refinement did not satisfy it. Do not flip it to `ready`.
#
# THE CITATIONS, COUNTED ONCE EACH. The pre-refinement trio carried twenty-nine
# distinct backticked `path:line` citations. `ergane spec validate` refused
# eighteen of them — sixteen because the citation was a bare filename with no
# directory, two because the line had gone blank. The rest resolved to real,
# non-blank lines and had to be re-read by hand, which is the point: a citation
# that lands on real code passes validate whether or not it names what the prose
# says. The park is at `factory/workgraph/workflow.py:2008` not 1344, the pause
# consumption at 1034 not 691, the drain at 1572 not 1027, `QuestionWorkflow` at
# 90 not 87, every ferry constant 39 lines down, `resolve_question` at 1808 not
# 1183. The refined trio carries seventy-five distinct citations, every one
# re-read at 602a92c and written in the `path.py:NN` — `symbol` form wherever it
# names a definition, so the next drift is machine-caught.
#
# THE DEFECT THIS SPEC WAS HELD FOR HAS THREE PARTS, NOT ONE. The 2026-08-08 pass
# found the pause flag and FR-016 forbade it. Re-reading the scheduler at 602a92c
# shows that removing `self._paused = True` is necessary and NOT sufficient: the
# parked task also keeps its concurrency slot (the drain exemption at 1606 plus
# the fill limit at 1089), and the loop only re-evaluates when some task finishes
# (1137). A peer-parked asker holds a slot the addressee needs, so the addressee
# is never dispatched even with the pause gone — the same deadlock by a different
# door. FR-016 now names all four properties (no pause, no slot, no cross-clear,
# wakes on the message) and US7 asserts them separately.
#
# 079-US4 CHANGED THE PARK'S SHAPE UNDER THIS SPEC. `WAITING_OPERATOR` is now the
# state BOTH doors write — the question and the PAUSE_EPIC press — with `_PARKED`
# as its alias, after a press parked as FAILED and killed three nodes on
# 2026-08-19. Two consequences the old plan could not know: a new node state must
# be classified deliberately in `_UNREACHABLE`, the drain exemption and the
# status derivation or it repeats that incident; and the question path's
# unconditional `self._paused = False` at 2072 must NOT be copied, because a peer
# park that clears it would resume an epic an operator had pressed pause on.
#
# US1 WAS SPLIT, AND THE SPLIT ADDED US6. The old US1 carried the grammar, the
# routing, the park, degradation, the limit, the store table, the prompt section
# and the sweep — provably over the refusal threshold with its evidence. US1 is
# now the leaf half (grammar plus store, no interpreter change); US6 is the
# interpreter half. FR-002 was split too — the straddle the 2026-08-18 edit
# explicitly deferred to this pass — so in-flight delivery is FR-019 and belongs
# to US2, and FR-017 moved from US2 to US3 because an external reply cannot be
# tested before the registry that names its sender exists.
#
# THE SPLIT IS MEASURED, NOT JUDGED. 017 was dispatched once, as a watched run,
# on 2026-08-29 (`5497a6a`). Its US1 attempt 1 was killed and salvaged; the
# salvage commit `3c04efd` holds what that attempt had written: fifteen files,
# 2,488 diff lines, 111,655 bytes — 1.70x the 65,536-byte refusal threshold, and
# not one byte of it pasted evidence. That is the old US1 measured rather than
# estimated. Nothing landed — `ergane spec landed --default-branch
# ergane-buildout` reports no landing for any story — so no immutable number is
# touched by the split. The killed attempt had already reached for two of the
# module names this plan now names, `factory/escalation/message.py` and
# `factory/verify/peer_grammar.py`, which says the shape was right and only the
# size was wrong.
#
# NO `fixes:` IS DECLARED, DELIBERATELY. This spec fixes no open ledger row; it
# is a feature. Two open rows are cited as evidence rather than claimed:
# `hardening/agent-worktree-boundary` (open, critical, 90 occurrences — the spec
# and plan previously named it `agent-edits-outside-its-worktree` at "two
# occurrences of two", a key that does not exist and a count stale by 45x), and
# `interpreter/a-merged-dependency-does-not-wake-the-scheduler-so-a-ready-node-waits-for-an-unrelated-activation`,
# which is the same scheduler-liveness mechanism FR-016 must not fall into.
#
# SUCCESS CRITERIA AND EDGE CASES ARE GONE, FOLDED NOT DROPPED. SC-001..SC-008
# and the eleven edge cases were rewritten into acceptance scenarios, functional
# requirements and plan traps, per the house shape from 126 onward. Every Then
# now names a committed artifact, and four that a do-nothing diff would have
# passed — the byte-identical compatibility claim chief among them — are
# differential now.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): the dial is 2, not 1 — every body
# argument that rested on `max_concurrent_nodes: 1` is re-argued against
# `ergane.yaml:151` (raised 2026-08-30) and the 2026-08-18 ordering is kept
# deliberately rather than by a stale premise; the park's membership sites are
# re-enumerated from a named grep — `_dead_edge` and the kill-while-parked branch
# were missing, and the count is gone; 126 landed on this same code on 2026-09-02
# and is now a declared dependency, because its close-out guard
# (`if state is not _PARKED:`) archives and clears the remote branch of any state
# that is not the park; FR-018 no longer claims a narrowing the sandbox already
# contradicts — the runtime-root bind makes every node worktree readable already,
# so the grant became a typed, differential one; FR-007 was rescoped to the
# surfaces its owner can land and FR-020/FR-021 own the rest; and US6 was split
# again, on measurement, into US6 (routing) and US7 (the park), because the
# implementer-addressed "split it yourself" conditional named a party who cannot
# mint a story. The REFINED block's citation arithmetic above is restated in this
# same pass — it gave two different numbers for one quantity, "fourteen of forty"
# and "the eighteen", and neither matched the file; the numbers now are twenty-nine
# citations in the old document, eighteen refused by validate, seventy-five now.
# Nothing else in the chain is edited. The hold is untouched and the state stays
# `draft`.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04, second pass), on an adversarial
# review that refuted the trio on three blocking counts — one false claim about
# how this factory is routed, and two stories sized by assertion rather than by
# measurement — and on six smaller ones.
#
# THE SUBSCRIPTION CLAIM WAS FALSE, AND IT MADE A TEST VACUOUS. The trio asserted
# three times that this factory routes its implementer persona through the
# subscription, "so that is one edit away". At 602a92c `implementer` is
# `agent: claude-code` (`personas.yaml:270`), moved off the subscription on
# 2026-09-01; the only subscription personas are `debugger` (`personas.yaml:410`)
# and `opus-closer` (`personas.yaml:449`), and neither is named by a story here.
# `_is_subscription_node` reads the persona *on the node*, so the second bound at
# `factory/workgraph/workflow.py:1102` is never entered for a normal epic — which
# made US7-S1's "pin both limits at 1" argument assert nothing about the
# subscription slot. US7-S1 and T047 now require the test to route its two
# scripted nodes to a subscription persona, the way
# `tests/test_subscription_accounting.py:242` already does, as well as pinning the
# dial. The corrected claim is stated in the causal chain, in plan trap 1 and in
# the task.
#
# TWO STORIES WERE SPLIT AGAIN, ON MEASUREMENT, AND THE SPLIT IS THE DECISION
# T001 COULD NOT TAKE. US5 carried a whole new activities module, a config writer
# and a ledger widening *plus* the sandbox grant, and § Sizing gave it no figure;
# US8 now owns FR-018 alone. US6's stated 10 KiB of headroom was computed against
# an evidence list that omitted an assembled prompt, and an assembled prompt
# carries the whole of plan.md verbatim — 41,581 bytes at 602a92c and over 45 KiB
# after this pass, which is most of the 65,536-byte refusal threshold on its own; US9 now owns FR-005 and FR-006,
# and every verification task bounds what it pastes. `3c04efd` is named for what
# it is in § Sizing: a *killed* attempt, so every figure apportioned from it is a
# floor rather than a size.
#
# SMALLER CORRECTIONS. US7-S5 names the outcome a kill on a peer-parked node must
# produce instead of deferring it to whatever the diff declares; FR-005's guard,
# which US9-S2 must extend rather than fork, is anchored for the first time
# (`tests/test_interpreter.py:3591` and `tests/test_workgraph_sweep.py:1168`);
# T031's instruction to coordinate decision-log numbers with US3 named a party
# that claims none. The citation count above is wrong and is not replaced with
# another: the refuted trio carried ninety-nine distinct backticked `path:line`
# citations, not seventy-five, and this pass adds more — what is guaranteed is
# that every one was read at 602a92c, not that anybody counted them twice.
#
# ONE REVIEW FINDING WAS DECLINED, WITH EVIDENCE. It asked that module-level
# constants (`DIFF_INPUT_LIMIT`, `_PARKED`, `WAITING_OPERATOR`, ...) be rewritten
# in the machine-checked `path.py:NN` — `symbol` form. They cannot be:
# `_symbol_spans` builds its map from `FunctionDef`, `AsyncFunctionDef` and
# `ClassDef` nodes only, so a constant written that way is reported as "not
# defined in that file" and, for a draft spec, refuses the gate. Verified by
# calling the checker directly on all six.
#
# The hold is untouched. The state stays `draft`.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04, third pass), on an adversarial
# review that refuted the trio on one blocking count and four smaller ones.
#
# FR-018 WAS OWNED BY TWO STORIES AT ONCE. The second pass minted US8 for the
# sandbox grant and rewrote every prose surface to say so — the frontmatter, the
# US5 narrative, US5-S7, the Work Graph paragraphs, US5's phase goal ("**No
# sandbox grant**"), T001 — but left `FR-018` in US5's `implements` list in the
# yaml. That list is not decoration: `factory/workgraph/prompt.py:598` calls
# `requirement_keys` "the fence, fixed at derivation and identical to what the
# judge will later score against", and `_requirement_sections` pastes each FR's
# verbatim bullet into the node's prompt, so US5's implementer would have been
# dispatched with "the grant MUST be a typed field on the invocation" as a
# requirement inside a slice that forbids it, and judged against it. Building it
# collapses the measured split and collides with US8 one merge-edge later;
# skipping it FAILs the story inside its own fence. US5 now implements FR-013,
# FR-014, FR-015 and FR-021; US8 owns FR-018 alone. All twenty-one requirements
# are still owned.
#
# FR-016 CLAIMED ITS SITE LIST WAS A GREP'S OUTPUT, AND IT IS NOT. The grep it
# names returns 332, 344, 905, 1534, 1594, 1606, 1992, 2006, 2290, 2302, 2309,
# 2370, 2379, 2381, 3137, 3249, 3318, 3320, 4282, 4284 and 4292 at 602a92c — not
# `workflow.py:300` or `workflow.py:313`, which name states by their own names.
# Plan trap 4 already said so; the requirement, which is the surface that reaches
# the implementer verbatim, contradicted it. FR-016 now says what the grep finds
# and what has to be added by hand, and its enumeration gains
# `factory/workgraph/workflow.py:2309` — the 079-US3 raise-path release, a read of
# the park that clears `self._paused` two lines later, which is exactly the
# cross-clear the same requirement forbids.
#
# SMALLER CORRECTIONS. § Sizing states its floor margin as a figure instead of
# leaving it implicit — the four stories cut from the killed attempt are allotted
# roughly 49.5 KiB of tests against the 33,550 the salvage measures — and names
# US6, not US3, as the story to re-measure first: US6 is the largest, its 17 KiB
# of nominal headroom is the thinnest here, and it is the only one whose base is a
# killed attempt. T001's preflight listed five of the six `depends_on_landed`
# entries; 009 is added. US3-S6's refusal-style citation moved off
# `factory/config.py:313`, which is an assignment, onto the guard and its
# `raise fail(...)` at `factory/config.py:314-315`.
#
# NOT IN SCOPE. Nothing here narrows the sandbox's shared mount set: the runtime
# root is bound read-only whole (`factory/workgraph/adapter.py:538`), every node
# worktree is inside it, and making that stop is a different spec — which is why
# FR-018 asks only for a declared grant and US8-S1 proves it differentially. The
# second pass's declined review finding stays declined on the same evidence:
# module-level constants cannot be written in the `path.py:NN` — `symbol` form
# because `_symbol_spans` maps only `FunctionDef`, `AsyncFunctionDef` and
# `ClassDef`. And the hold is not in scope for a refinement pass at all: no
# refinement can satisfy a condition that is a watched live run.
#
# The hold is untouched. The state stays `draft`.
---

# Feature Specification: Peer Channel

**Created**: 2026-08-08

**Depends on**: 008-operator-channel (the channel this one addresses),
009-roadmap-scheduler, 041-escalation-workflow (the question lifecycle is a
child workflow now), 079-a-pressed-button-does-what-it-says (park semantics and
the state the park writes), 101-the-sandbox-is-portable-and-sealed (the bind
list a read-only worktree grant is added to),
126-a-killed-node-leaves-no-ref-to-collide-with (the close-out guard that reads
the park state before it deletes a node's remote ref).

## The gap, stated precisely

008 built a channel with exactly one addressee, and 041, 079 and 126 then
hardened that one addressee's lifecycle until every part of it assumes the
answerer is *outside* the factory. A peer answerer is inside it, and six
mechanisms in the tree are written the other way:

1. **The grammar has no recipient.** `factory/verify/question.py:85` —
   `detect_operator_question` returns a `factory/verify/question.py:71` —
   `QuestionMarker` carrying a body and nothing else, under the fixed heading at
   `factory/verify/question.py:51`. There is no field a question could name a
   recipient in, so every question in the factory is addressed to the same
   person by construction.
2. **The lifecycle is a child workflow that pages a human.** The epic starts
   `factory/escalation/question.py:90` — `QuestionWorkflow` at
   `factory/workgraph/workflow.py:1980`, and that child's
   `factory/escalation/question.py:112` — `run` calls `send_question` before it
   waits. The wait is a signal buffer,
   `factory/escalation/question.py:101` — `question_answered`, and nothing but
   the Telegram bridge or `ergane build answer` ever sends it.
3. **The park raises the scheduler's pause.** `factory/workgraph/workflow.py:2006`
   writes `NodeState.WAITING_OPERATOR` and `factory/workgraph/workflow.py:2008`
   is the single line `self._paused = True`, consumed at
   `factory/workgraph/workflow.py:1034`, which drains the in-flight set and idles
   the whole scheduler until the flag clears. Correct for a sleeping human; fatal
   for a peer, because the node that must answer is a node of this same epic.
4. **The parked node keeps its slot.** `factory/workgraph/workflow.py:1572` —
   `_drain_in_flight` deliberately does not wait on a `WAITING_OPERATOR` node
   (`factory/workgraph/workflow.py:1606`), so its task stays in the in-flight
   set for the whole window — and the dispatch loop stops filling at
   `factory/workgraph/workflow.py:1089`, `len(in_flight) >= request.max_concurrent_nodes`.
   This factory's configured value is 2 (`ergane.yaml:151`, raised from 1 on
   2026-08-30), so a peer-parked asker holds half the epic's slots; the dial is
   per-epic and an operator may set it back to 1, at which the parked asker is
   the whole epic. There is a second door on the same set: a subscription-routed
   node is bounded again at `factory/workgraph/workflow.py:1102` through
   `factory/workgraph/workflow.py:1423` — `_subscription_nodes_in_flight`, which
   counts the same `in_flight` dict. That door is shut twice today, not once. The
   dial is undeclared, defaulting to `None` at
   `factory/workgraph/workflow.py:577`; and no node of a normal epic is routed to
   a subscription persona at all —
   `factory/workgraph/workflow.py:1413` — `_is_subscription_node` reads the
   persona named on the node (`factory/workgraph/workflow.py:993`), and
   `implementer` is `agent: claude-code` (`personas.yaml:270`, moved off the
   subscription on 2026-09-01), with `debugger` (`personas.yaml:410`) and
   `opus-closer` (`personas.yaml:449`) the only subscription entries and neither
   named by a story here. So the second bound is a closed door that is not
   locked: one operator edit re-opens it, and a test that pins the dial without
   routing a node through a subscription persona asserts nothing about it.
5. **Nothing wakes the scheduler but a finished task.** The loop waits at
   `factory/workgraph/workflow.py:1137` on `any(task.done())`, the kill flag, or
   the pause flag. A message arriving is none of those, which is the same
   mechanism the open finding
   `interpreter/a-merged-dependency-does-not-wake-the-scheduler-so-a-ready-node-waits-for-an-unrelated-activation`
   reports from the other side.
6. **The last mile to a live agent is a pull.** `factory/workgraph/adapter.py:1400` —
   `_ferry_once` polls for an answer only once the agent has itself written a
   question file — the guard is `state.question_id is None` at
   `factory/workgraph/adapter.py:1440`. Nothing today can push an unsolicited
   message at a running attempt.

Steps 3, 4 and 5 are why this is not a routing feature with a park bolted on.
Removing the one line at `factory/workgraph/workflow.py:2008` is necessary and
not sufficient: a peer-parked asker that still occupies a slot, in a loop that
only re-evaluates when a task finishes, produces exactly the deadlock the
2026-08-08 verification pass predicted — every peer question dead-waits its
window and degrades to the operator — while every scripted test passes, because
a test whose two attempts overlap never observes any of the three. That is why
the park is its own story (US7) and its own dispatch, downstream of the routing
it parks on.

## The rule this spec is asking for

**A message names its recipient; the recipient may be a peer node, a persona,
a registered external agent or a sibling epic; and the operator is the floor
every undelivered message lands on rather than the only line it can take —
while an addressee-less question stays byte-identical to what 008 ships.**

The address space, complete, with what each route costs:

| addressee | the addressee's state | route | story |
| --- | --- | --- | --- |
| absent | — | 008's operator question, unchanged on every path | — |
| a node of this epic | an attempt in flight | pushed down that attempt's ferry | US2 |
| a node of this epic | no attempt, attempts remain | its next assembled prompt | US6 |
| a node of this epic | terminal | a consult, else the operator floor | US5 |
| a persona name | — | an ephemeral consult, else the operator floor | US5 |
| a registry name | — | the mailbox transport, mirrored to the operator | US3 |
| a node of a sibling epic | — | a signal to that epic's workflow | US4 |
| the sender itself | — | refused to the asker, immediately | US6 |
| any name in no namespace | — | refused to the asker, immediately | US6 |
| any addressee, past the outstanding-message limit | — | refused to the asker, naming the field and its value | US9 |

Every row above delivers a reply into the asker's *next* assembled prompt, which
is a conversation costing one dispatch per exchange. US7 is what lets an asker
wait for the reply inside the attempt it asked from, and the park that waits
obeys four rules at once: it raises no pause, it holds no slot, it clears no
pause somebody else set, and it wakes the scheduler when the reply arrives.

### What this spec is not

It is not a second question grammar. The heading at
`factory/verify/question.py:51` and the ferry files at
`factory/workgraph/adapter.py:187` and `factory/workgraph/adapter.py:188` are
the same two doors; an addressee is a line inside them.

It is not a widening of what an agent may make the factory do. The FR-012
amendment's hole moves from "park and page the operator" to "park and route",
and no further: message text still reaches no gate and no judge (FR-005).

It is not a way for a question to die unheard. Every branch's worst case is the
008 behaviour the factory ships today, which is why the operator is called the
floor rather than the default.

It is not an A2A adoption, and it is not an in-agent messaging tool. Both were
considered and rejected; the reasoning is recorded in § Decision below and the
registry's `transport` field is the seam a future A2A client slots into.

It is not a change to `personas.yaml`'s `needs_worktree`
(`factory/config.py:188`). That field provisions a persona its *own* worktree
from a base; FR-018's grant is a read-only view of somebody else's existing one.

It is not a narrowing of the sandbox's existing mount set. The bwrap backend
already binds the whole runtime root read-only
(`factory/workgraph/adapter.py:538`), and every node worktree lives inside it
(`factory/workgraph/worktree.py:289` — `worktree_path`), so sibling worktrees
are already readable and already unwritable in every attempt. FR-018 adds one
*declared* grant and takes nothing away; closing the wider read is a different
spec against a mount set every attempt shares.

## User Scenarios & Testing

### User Story 1 - A question names its recipient, and every message is on the record (Priority: P1)

As the factory operator, the question grammar an agent already knows gains one
optional line — the addressee — and every message and reply the factory carries
is written down beside the questions, so that the rest of this spec has an
address to route and a record to resolve against.

This story changes no interpreter behaviour at all. It is the leaf half: the
detector learns to read an addressee out of the final-message marker and out of
the ferry question file, the store learns a `messages` table with the same
guarded first-wins resolution `factory/verify/store.py:1808` — `resolve_question`
already uses for questions, and the verification component's credential sweep
learns to drive a message write. Nothing routes yet, which is exactly why it is
separable and why it fits.

**Why this priority**: P1 and it depends on nothing. Every other story in this
spec reads an addressee or writes a message row; neither exists today.

**Independent Test**: Parse one transcript body twice — once with an addressee
line and once without — and read the two markers; write a message row and a
reply row and read them back through the store's own accessors.

**Acceptance Scenarios**:

1. **Given** a final message whose `## OPERATOR QUESTION` body opens with an
   addressee line, **When** the detector reads it, **Then** the committed test
   asserts the returned marker carries both the addressee and the body with the
   addressee line removed, so the body an operator would be paged with is not
   polluted by the routing line.
2. **Given** a ferry question file whose body opens with the same addressee
   line, **When** the ferry reads it, **Then** the committed test asserts the
   same addressee and the same body, because one grammar means one parser and
   two call sites.
3. **Given** one transcript body used twice by a single committed test — once
   with the addressee line and once without — **When** the detector reads each,
   **Then** the addressed read yields an addressee and the unaddressed read
   yields a marker byte-identical to what today's detector returns, asserted
   against the 008 fixtures with no edit to them. A diff that only added a field
   cannot pass this pair, because the pair is differential.
4. **Given** an addressee line that is present but empty, or malformed, **When**
   the detector reads it, **Then** it yields no addressee and the body is left
   whole — a broken routing line degrades to the operator rather than refusing a
   question, and the committed test asserts the body still contains the line so
   the operator can see what the agent meant.
5. **Given** a message and a reply written to the store, **When** they are read
   back, **Then** the row carries sender epic, node, attempt and persona, the
   addressee, the body, the reply, the resolution and the expiry, and a second
   resolution of the same message id returns false — the first-wins arbiter
   `resolve_question` uses, asserted by a committed test that resolves twice.
6. **Given** the credential sweep at
   `tests/test_verification_sweep.py:418` — `test_no_byte_this_component_persists_carries_either_credential`,
   which drives the component and then searches every byte the run persisted,
   **When** it is extended to write a message body and resolve a message row
   carrying the canary credential inside that same run, **Then** the committed
   test fails on an unscrubbed store and the diff shows the two new acts driven
   inside the sweep — a sweep whose run never touched the `messages` table
   searches bytes that were never written, so this scenario cannot pass on a
   sweep that was left alone.

---

### User Story 2 - A message reaches an attempt that is already running (Priority: P1)

As the factory operator, a peer message reaches an agent that is *mid attempt*
rather than waiting for its next dispatch, and that agent's reply travels back
the same way, so that two agents working at the same time can converse instead
of taking turns across attempt boundaries.

This is separated because it is the story with an unstated protocol change in
it. US6 routes to a peer that is *not* running and needs no adapter change at
all. Live delivery does: `factory/workgraph/adapter.py:1400` — `_ferry_once`
only polls for an answer once the agent has itself asked, so the inbound
direction does not exist. This story adds it, plus the prompt instructions that
tell an agent to watch its inbox while it works.

**Why this priority**: P1 with US6, because "the peer answers on its next
attempt" is a slow conversation — each exchange costs a dispatch. It is
genuinely separable: US6 alone already keeps peer questions off the operator's
phone. It also gains weight at the configured concurrency of 2
(`ergane.yaml:151`): the more nodes of one epic run at once, the more often a
same-epic addressee is a node with an attempt in flight.

**Independent Test**: With two scripted agents whose attempts overlap in the
test's own timeline, an unsolicited inbound message is surfaced to the running
addressee, its reply reaches the asker, and neither attempt ends.

**Acceptance Scenarios**:

1. **Given** an addressee with an attempt in flight that has asked nothing —
   so `state.question_id` is unset — **When** a peer message is routed to it,
   **Then** a committed test drives the ferry beat and asserts the message text
   is in the file the agent polls, and the diff shows the inbound path is not
   guarded on a question having been asked.
2. **Given** a running addressee that has been handed a message, **When** it
   writes a reply into the ferry, **Then** a committed test asserts the reply
   threads to the asker by message id and that both attempts are still live
   afterwards — asserted on the attempt records, not on the absence of an error.
3. **Given** an agent that never reads its inbox, **When** its attempt ends
   normally, **Then** the undelivered message degrades exactly as an expired one
   does and the committed test asserts the node's attempt ceiling is unmoved — a
   peer that ignores its inbox costs a message, never a node.
4. **Given** the prompt instructions that tell an agent to watch its inbox,
   **When** an attempt prompt is assembled, **Then** a committed test asserts the
   instruction text is present for an attempt that has an inbox and absent for
   one that does not, so the instruction is a fact about the attempt rather than
   a paragraph pasted into every prompt.

---

### User Story 3 - A message reaches a named external agent (Priority: P2)

As the factory operator, an agent can send a message to an agent I have named in
a registry outside the epic — first among them the homelab operator agent
working in `~/code/homelab` on this same host — and a reply that agent writes
comes back into the asking node's next prompt, so that questions about the
proxy, the stack, or the machines land with the agent that owns them instead of
with me.

External peers live in an operator-owned registry file, sibling to
`personas.yaml`: each entry names the peer, its transport, its address and its
expiry window. The first transport is a durable filesystem mailbox — one JSON
file per message in the peer's inbox directory, replies swept from its outbox by
the same beat that already ticks the asker's expiry. The registry's transport
field is the seam a future A2A client slots into; the mailbox is what the
homelab agent can consume today with one line in its own instructions. Because
an external agent answers on its own schedule — or never — every external send
is mirrored to the operator as a notification, and the unanswered-at-expiry path
is US6's degradation unchanged.

An external reply is also the one reply in this spec that arrives from outside
the factory's trust boundary, which is why FR-017 lives here rather than with
the delivery mechanism: an outbox is a host directory anyone with filesystem
access can write.

**Why this priority**: This is the operator's explicitly named want, and the
story that takes the channel outside one Temporal workflow. It is P2 only
because US6 lands the routing, store and degradation semantics it rides on.

**Independent Test**: With a registry naming a mailbox peer, a scripted agent
addresses it; the message file appears in the inbox with the documented schema,
the mirror is sent, a reply file placed in the outbox reaches the asker's next
prompt verbatim, and an unanswered message degrades to an operator question.

**Acceptance Scenarios**:

1. **Given** a message addressed to a registered mailbox peer, **When** routing
   delivers it, **Then** a committed test asserts exactly one message file
   appears in the peer's inbox carrying id, sender epic/node/persona, body and
   reply instructions, and that one mirror notification was sent with no reply
   key on it.
2. **Given** a reply file in the peer's outbox naming an open message id,
   **When** the sweep beat reads it, **Then** the committed test asserts the
   reply reaches the asking node by US6's paths and the exchange is recorded in
   the store.
3. **Given** an external reply reaching an asking agent, **When** its prompt
   section is assembled, **Then** the committed test asserts the section names
   the registry entry the reply came from and frames it as an outside opinion,
   and that the reply bytes inside that frame are unchanged — verbatim content,
   attributed framing, and the test asserts both halves so neither can be
   dropped for the other.
4. **Given** an external message unanswered at its registry expiry, **When** the
   expiry loop evaluates it, **Then** it degrades to the 008 operator question
   path, and a reply arriving afterwards is stored and never read — asserted by
   a committed test that writes the late reply and reads the asker's next prompt.
5. **Given** a message addressed to a name in no registry, or a registry entry
   whose mailbox path cannot be written, **When** routing evaluates it, **Then**
   it is refused to the asker as undeliverable, named and immediate, and the
   committed test asserts the asker's attempt ceiling is unmoved and that
   routing did not retry.
6. **Given** a registry file whose entry is malformed, or whose peer name
   collides with a node id or a persona name, **When** it is loaded, **Then**
   loading refuses with a named finding in the style
   `factory/config.py:314-315` already uses for `personas.yaml` — the guard and
   the `raise fail(...)` that names the offending field — because one
   namespace with two owners is an address that means two things.
7. **Given** the attempt-side credential sweep at
   `tests/test_workgraph_sweep.py:410` — `test_no_byte_a_real_attempt_persists_carries_either_credential`,
   which drives one whole attempt and then searches every file the run left on
   disk, **When** it is extended to send one external message inside that run,
   **Then** a committed test asserts the sweep fails on a mailbox file or a
   mirror notification carrying the canary credential, and the diff shows the
   mailbox root inside the tree the sweep walks — a mailbox written outside the
   swept tree is a surface the sweep cannot see, so the path is part of the
   assertion.

---

### User Story 4 - A message crosses epics, and the channel is documented (Priority: P3)

As the factory operator, when two epics run concurrently, an agent in one can
message a node in the other — routed as a signal to the sibling epic's workflow,
buffered with the same incurious discipline every existing signal uses — and the
whole channel's decision trail is recorded, so that the factory's conversation
topology is complete and explained.

**Why this priority**: Real, but `max_concurrent_epics` is 1 (`ergane.yaml:150`)
and the reason recorded above it is the worker, not the agents — so same-epic
and external peers are the live need and the cross-epic hop is deliberately
last, priced only after US6's routing and US3's registry exist. It carries the
channel's documentation and decision-log duties as the completing story.

**Independent Test**: With two workflow instances and scripted children, a
message addressed to a node in the sibling epic is delivered into that node's
prompt and the reply returns; the decision log and architecture docs name the
channel.

**Acceptance Scenarios**:

1. **Given** a message addressed to a node in a named sibling epic, **When**
   routing delivers it, **Then** a committed test asserts the sibling workflow
   receives it as a signal, buffers it without validating against state it may
   not have written yet, and delivers it to the target node by US6's rules.
2. **Given** a cross-epic message whose sibling epic is not running or never
   answers, **When** the expiry loop evaluates it, **Then** US6's degradation
   applies unchanged, and the committed test asserts the client signal's failure
   was caught in the activity rather than raised into the workflow.
3. **Given** the feature lands, **When** the decision log and architecture docs
   are read, **Then** the diff adds a `docs/decisions.md` entry claiming the
   transport decision and the FR-012-amendment extension, and a
   `docs/architecture.md` section naming the peer channel, its registry and the
   consult runner.

---

### User Story 5 - A message with no live recipient spawns its answerer (Priority: P1)

As the factory operator, when a message names a persona — or a node whose
attempts are done — the factory spins up an ephemeral consult to answer it: one
process, dispatched with that persona's model, read-only, alive exactly long
enough to produce the reply, then discarded, so that "ask the architect" works
whether or not an architect happens to be running, and the operator rung is
reached only when a machine genuinely could not answer.

The factory already runs this shape everywhere: every attempt is an ephemeral
agent an activity spawns, monitors and tears down —
`factory/workgraph/adapter.py:750` — `adapter_for` and
`factory/workgraph/adapter.py:1022` — `run_attempt` — and the judge is a whole
persona that lives one request at a time. A consult is an attempt with the
ladder removed: no gates, no judge, no verdict, no diff expected, and its entire
output contract is the reply.

A consult also **reads the asking node's worktree** — read-only, as it stands at
spawn time, uncommitted work included. This is what separates an architect that
can answer from one that can only recite the plan: the question an implementer
actually asks is about the code it has just written, and that code is in its
worktree and nowhere else. **The grant itself is US8**, split out of this story
on measurement: it is an adapter change (a typed field and one bind tuple in
`factory/workgraph/adapter.py:464` — `_build_argv`) that shares no production
file with the consult runner, and this story is a whole new activities module
without it. What US5 owes US8 is the call site: a consult is launched through an
invocation, and US8 types what that invocation carries. A consult whose asker has
no readable worktree still answers from assembled context, which is FR-013's
clause and US5-S7 here.

**Why this priority**: This is the escalation vision the channel exists for —
questions answered by the cheapest competent answerer, with the operator as the
floor rather than the default. It is **P1 and lands fifth**, immediately after
the routing, its two safety properties and the park. The 2026-08-18 operator decision that put it there
argued from a configured concurrency of 1; the dial has since been raised to 2
(`ergane.yaml:151`, 2026-08-30) and the ordering is kept anyway, deliberately.
At 2 a same-epic peer is running more often than it was, which strengthens US2
rather than US5 — but US2 is an adapter protocol change that delivers whatever
routing produced, consult replies included, so moving it ahead of the consult
rung would put the transport before its cargo. The argument that survives the
dial move unchanged is the other one: a persona consult is the only addressee
class that answers a question no running node can answer at all, and at any
concurrency the original chain's placement of consults behind the external
mailbox put the spec's cheapest answerer last but one.

**Independent Test**: With a scripted consult adapter, a persona-addressed
message spawns exactly one consult, the reply threads back to the asker, the
consult's spend lands in the ledger as its own row, and a failing consult
degrades to an operator question.

**Acceptance Scenarios**:

1. **Given** a message addressed to a persona with no live attempt, or to a node
   whose attempts are terminal, **When** routing evaluates it and a consult is
   available, **Then** a committed test asserts exactly one consult spawns with
   that persona's registry model, its reply threads back by message id, and its
   process, key and assembled context are discarded after the reply.
2. **Given** a consult that fails, times out, or declines to answer, **When** its
   run ends, **Then** the message degrades to the 008 operator question path —
   the consult rung sits above the floor, never replaces it — asserted for all
   three endings by one committed test.
3. **Given** a consult whose own output carries a peer-addressed marker, **When**
   routing evaluates it, **Then** the marker is refused and the message is
   treated as a decline: consults answer, they do not converse, and an unbounded
   spawn tree is what the refusal exists to prevent.
4. **Given** a factory memory bank named in operator-owned configuration,
   **When** a consult runs, **Then** the committed test asserts the written
   config names that bank; **Given** operator configuration naming a second
   endpoint, **Then** the writer refuses and no config file is written at all,
   which is what makes "no other endpoint can appear in it" an assertion rather
   than a hope; **Given** no bank is configured, **Then** no config file is
   written and the consult still answers from assembled context; and the
   attempt-side credential sweep drives the config write inside its own run, so
   a credential in that file fails it. One committed test, four parts.
5. **Given** consult spawns standing at the configured bound, **When** one more
   is requested, **Then** it is refused and the message degrades to the operator,
   and the refusal names the configuration field and its value — spawning is
   limited by configuration, not by message volume.
6. **Given** two consults answering two messages from the same node, attempt and
   persona, **When** both are metered, **Then** the committed test reads two
   distinct ledger rows with two distinct key aliases — the alias at
   `factory/usage/ledger.py:69` is `UNIQUE`, so a consult that borrows the
   asker's alias silently overwrites the asker's own row and this scenario is
   what catches it.
7. **Given** an asker with no readable worktree — a terminal node, a swept tree,
   or a bare persona address — **When** a consult runs for it, **Then** it still
   answers from assembled context and its reply names which context it had, so a
   thin answer is legible as thin rather than read as authoritative. This is
   FR-013's clause, not FR-018's: a consult must answer without a grant, and the
   grant itself is US8.

---

### User Story 6 - A message reaches a peer that is not running, and the reply comes back (Priority: P1)

As the factory operator, when an agent addresses a question to a peer that is
not currently running, the message is routed and buffered by the epic that owns
both nodes, the addressee is dispatched in its own turn and answers, and the
reply reaches the asker in the asker's next assembled prompt — so that the
operator's phone is reserved for questions only a human can answer.

**This story lands no park, no limit and no guard.** An asker in US6 sends its
message and its attempt ends as it otherwise would; the exchange costs one
dispatch each way. That is a slow conversation and it is a working one, and it is the half of
this feature that can be built without touching the scheduler at all. Waiting
for the reply *inside* the asking attempt is US7, which is where the deadlock
this spec was held for lives. An implementer who reaches for
`factory/workgraph/workflow.py:2006`'s park block in this story has taken US7's
work and its risk into a story sized without them.

**Why this priority**: P1, and it is the story that converts the operator from
single point of attention into escalation floor. Without it nothing else in this
spec has a route. The outstanding-message limit (FR-006) and the no-verdict guard
(FR-005) are US9, split out on measurement: they are two safety properties on the
seam this story lands, and the salvage that measures this story is a *killed*
attempt, so its 55 KiB is a floor rather than a size (plan.md § Sizing).

**Independent Test**: With two scripted nodes in one epic, one addresses a
question to the other; the addressee's next assembled prompt carries the message
under its own section, its reply reaches the asker's next assembled prompt
verbatim, no operator notification is sent, and both nodes' attempt ceilings are
what they were before the exchange.

**Acceptance Scenarios**:

1. **Given** a peer message addressed to a node with no attempt in flight and
   attempts remaining, **When** that node's next attempt is assembled, **Then**
   a committed test asserts its prompt carries the message verbatim under a
   dedicated peer-message section — distinct from the section
   `factory/workgraph/prompt.py:814` — `_answer_section` writes, because the
   operator's voice and a peer's are not the same authority — and that the reply
   threads back to the asker by message id.
2. **Given** a message addressed to a terminal node, to the sender itself, to a
   name in no namespace, or unanswered at its expiry, **When** routing or the
   expiry loop evaluates it and no consult is available for that addressee,
   **Then** a committed test asserts it degrades to the 008 operator question
   path carrying the message body, and that the asker's attempt ceiling is
   unmoved — a peer message may go unanswered; it must never hang a node or
   vanish.

---

### User Story 7 - An asker waits for its reply without stopping the epic (Priority: P1)

As the factory operator, an agent that asks a peer can wait for the answer
inside the attempt it asked from — parked, not spending — while the epic keeps
dispatching, the addressee runs and answers, and the asker resumes on that
reply, so that a peer exchange costs one dispatch instead of two and the epic
never goes quiet waiting for itself.

**This story is the whole reason the spec was held.** 008's park raises the
scheduler's pause at `factory/workgraph/workflow.py:2008` — correct for a
sleeping human, fatal here, because the node that must answer is a node of this
same epic. But the pause is only the first of three: the parked task also keeps
its slot (`factory/workgraph/workflow.py:1606` exempts it from the drain, and
`factory/workgraph/workflow.py:1089` stops dispatching once the slots are full,
with a second bound on the same set at `factory/workgraph/workflow.py:1102`),
and the loop only re-evaluates when some task finishes
(`factory/workgraph/workflow.py:1137`). A peer park that fixes one of the three
still deadlocks; the scenarios below assert them separately for that reason. The
fourth and fifth hazards are membership: a new node state is a decision at every
site that reads the park, and two of those sites — the merge-gated dead-edge
predicate and the close-out that deletes a node's remote ref — decide things
that are not recoverable by retrying.

**Why this priority**: P1 and it lands fourth, on the seam US6 and US9 landed and
before anything else rides it. Every later story delivers replies into an asker
that may be parked.

**Independent Test**: With two scripted nodes in one epic, both concurrency
limits at 1 and both nodes routed to a subscription persona, one addresses a
question to the other; the addressee is dispatched **while the asker is parked**,
its reply reaches the asker verbatim, no operator notification is sent, and both
nodes' attempt ceilings are what they were before the exchange.

**Acceptance Scenarios**:

1. **Given** an asker parked awaiting a peer reply, with `max_concurrent_nodes`
   at 1, `max_concurrent_subscription_nodes` at 1, **and both scripted nodes
   routed to a persona whose `agent` is `subscription`**, **When** the scheduler
   next evaluates, **Then** a committed test asserts the addressee is dispatched,
   the pause flag is unset and the epic state is still running. All three
   conditions are load-bearing and the third is the one a diff will forget:
   `factory/workgraph/workflow.py:1413` — `_is_subscription_node` reads the
   persona named on the node, and the default `implementer` is
   `agent: claude-code` (`personas.yaml:270`), so on a default registry the bound
   at `factory/workgraph/workflow.py:1102` is never evaluated and the test would
   pass whether or not the park released its subscription slot. Install a
   registry that carries one, the way
   `tests/test_subscription_accounting.py:242` — `test_subscription_concurrency_is_bounded_by_declared_limit`
   does with `tests/test_subscription_accounting.py:73` and
   `tests/test_subscription_accounting.py:79` — `_subscription_nodes`.
2. **Given** an asker parked awaiting a peer reply and no other node finishing,
   **When** the message is buffered, **Then** a committed test asserts the
   addressee is dispatched without waiting for an unrelated task to complete,
   and the diff shows the scheduler's wait predicate gained the term that makes
   that true.
3. **Given** an epic paused by an operator's press, **When** a peer-parked node
   in it un-parks, **Then** a committed test asserts the pause is still set —
   the peer park clears only what it raised, and the question path's unconditional
   clear at `factory/workgraph/workflow.py:2072` is the shape this must not copy.
4. **Given** a node parked on a peer message, **When** the epic's state is read,
   **Then** a committed test asserts the node is not reported as awaiting the
   operator (the derivation at `factory/workgraph/workflow.py:903`), its
   dependents are still PENDING rather than KILLED
   (`factory/workgraph/workflow.py:300` is the set that decides it),
   `factory/workgraph/workflow.py:1572` — `_drain_in_flight` does not wait on it,
   and a merge-gated dependent's edge is not read as dead
   (`factory/workgraph/workflow.py:1522` — `_dead_edge` continues past the park
   at `factory/workgraph/workflow.py:1534`, which is keyed on `_PARKED` and not
   on this state).
5. **Given** a kill arriving while a node is parked on a peer message, **When**
   `factory/workgraph/workflow.py:1715` — `_run_node` reaches its terminal
   branches, **Then** a committed test asserts the peer park is matched by a
   branch of its own, that the node's record ends KILLED, and that its pending
   peer message is resolved as undelivered with no wait left outstanding on it.
   The forbidden outcome is named too, because it is the one a silent diff
   produces: falling through `factory/workgraph/workflow.py:2381`'s `elif` into
   the `else` below it closes the node out KILLED while its coroutine is still
   parked on the message wait, and the test asserts on the message's resolution
   rather than only on the node's state, because the state is the half that looks
   right either way.
6. **Given** a peer-parked node whose close-out runs, **When**
   `factory/workgraph/workflow.py:3087` — `_close_out` reaches
   `factory/workgraph/workflow.py:3137`'s `if state is not _PARKED:`, **Then** a
   committed test asserts the node's remote branch was not archived and cleared —
   126-US2 put a destructive act behind an identity check against one park state,
   and a second park state that is not that one falls straight through it.

---

### User Story 8 - The consult's read of the asker's worktree is declared, not inherited (Priority: P1)

As the factory operator, the read a consult has of the asking node's worktree is
a grant the invocation carries and the sandbox emits, rather than a side effect
of a mount every attempt happens to share, so that the capability is legible in
one place, survives a change to the mount set, and can be denied.

This story exists because the read it is about is **already there**. The bwrap
backend binds the whole runtime root read-only
(`factory/workgraph/adapter.py:538`) and every node worktree lives inside it
(`factory/workgraph/worktree.py:289` — `worktree_path`), so a consult can read
the asker's uncommitted files today, on a diff that adds nothing. What is missing
is the declaration: a typed field on
`factory/workgraph/adapter.py:293` — `AgentInvocation` and one `--ro-bind` in
`factory/workgraph/adapter.py:464` — `_build_argv`. Read plan.md § "The worktree
grant already half exists" before writing a line of it.

**Why this priority**: P1 and it lands sixth, immediately after the consult
runner whose invocation it types. It is separate from US5 on measurement, not on
taste: US5 is a new activities module of the size this tree's activity modules
run (26–47 KB under `factory/activities/`), and this is an adapter change plus
one call site. That call site is why the edge is a merge-edge and not a parallel
one: US8 sets a field on the invocation US5's launcher builds, so it edits one
line of `factory/activities/consult_activities.py` and everything else in
`factory/workgraph/adapter.py`.

**Independent Test**: build the sandbox argv twice from the same launcher — once
from an invocation carrying the declared grant, once from one with the field
unset — and compare; resolve the granted path from the asker's node record rather
than rebuilding it; then, on a host that has the sandbox binary, launch for real
and watch a write into that worktree fail.

**Acceptance Scenarios**:

1. **Given** a consult invocation carrying the asker's worktree as its declared
   read grant, **When** the sandbox argv is built, **Then** a committed test
   asserts the argv holds exactly one `--ro-bind` whose source and destination
   are that worktree path and no `--bind` naming it, ordered through
   `factory/verify/gates.py:150` — `ordered_binds`; **and** the same test builds
   the argv a second time from an invocation with the grant field unset and
   asserts no bind names that worktree at all. The control is the point: the
   backend already read-only-binds the runtime root above every worktree, so a
   production diff that adds nothing still lets a consult read the asker's files
   — only the paired assertion fails on it.
2. **Given** a consult launched for an asker whose node record names its
   worktree, **When** the invocation is built, **Then** a committed test asserts
   the grant field holds exactly the path
   `factory/workgraph/worktree.py:289` — `worktree_path` derives for that node,
   and that the path was not rebuilt from strings a second time — one derivation,
   one grant, so a rename of the layout cannot leave the bind pointing at a
   directory that no longer exists.
3. **Given** a host that has the sandbox binary, **When** a consult is launched
   for real against the asker's worktree, **Then** a committed test guarded the
   way `tests/test_us5_gates.py:44` guards its own — `BWRAP_PRESENT` — asserts a
   write from the consult into that worktree and into a path above it both fail
   and the tree's checksum is unchanged, with the don't-write instruction removed
   from the prompt so the assertion measures the grant and not obedience; and the
   test declares its skip reason, because a host without the binary proves
   nothing here and US8-S1 is the assertion that holds everywhere.

---

### User Story 9 - An exchange is bounded, and its text reaches no verdict (Priority: P1)

As the factory operator, two agents cannot talk each other into an unbounded
exchange, and nothing either of them says can reach a gate or the judge, so that
the channel US6 opened costs a known number of messages and widens the FR-012
amendment's hole no further than "park and route".

These are the two safety properties of the routing seam, and they are their own
story for the same reason the park is: US6's own measurement comes from a killed
attempt and is therefore a floor, and a story that is refused unjudged at
`factory/verify/diffbounds.py:66` costs an attempt and teaches nobody anything.
Both properties are written against mechanisms that already exist — the
configuration-refusal shape the scheduler's own limits use, and the read-set
guard 008 wrote for its question text.

**Why this priority**: P1, and it lands third — on the seam US6 has just landed
and before US7 makes waiting for a reply cheap. A limit that arrives after the
park arrives after the loop it exists to stop.

**Independent Test**: drive a two-node exchange that would not otherwise converge
and watch it terminate at the configured limit with both nodes proceeding; then
carry a message and a reply through an exchange and assert the workflow's read
set off an attempt still admits no message text.

**Acceptance Scenarios**:

1. **Given** a node whose outstanding peer messages stand at the configured
   bound, **When** it sends one more, **Then** the send is refused to the asker
   with the refusal naming the configuration field and its value, and a committed
   test drives a two-node exchange that would otherwise not converge and asserts
   it terminates at the bound with both nodes proceeding.
2. **Given** a message and a reply carried through an exchange, **When** the
   gates and the judge run, **Then** a committed test asserts neither can read
   the message text — the guard 008 wrote for its own question text, extended
   rather than forked, with the diff showing the extension. The guard is two
   committed tests, not a rule in prose:
   `tests/test_interpreter.py:3591` — `test_a_marker_never_produces_a_pass_from_its_presence`
   holds that an agent-authored marker can park a node and never grade it, and
   `tests/test_workgraph_sweep.py:1168` — `test_the_workflow_reads_nothing_off_an_attempt_but_its_termination`
   pins the workflow's read set off an attempt result. A message that reached a
   verdict would have to widen one of those two, so the diff shows which one it
   extended and what the new member is for.

## Functional Requirements

- **FR-001**: The question grammar — the final-message marker and the ferry
  question file — MUST accept an optional addressee line, and a question with no
  addressee MUST behave byte-identically to 008's operator question on every
  path. An addressee line that is empty or malformed MUST yield no addressee
  rather than a refusal.
- **FR-002**: A message addressed to a same-epic peer MUST be routed through
  workflow state — buffered, replay-safe, keyed by message id — and delivered
  into the target's next assembled prompt, under a section distinct from the
  operator-answer section, when the target has no attempt in flight. Delivery to
  a target that *does* have an attempt in flight is FR-019; an asker that waits
  for the reply inside its own attempt is FR-016.
- **FR-003**: A peer's reply MUST thread back to the asker by message id,
  verbatim, and reach it by whichever delivery path the asker is on.
- **FR-004**: A message that is undeliverable — unknown addressee, self-address,
  terminal target, unwritable transport — or unanswered at its expiry MUST
  degrade to the 008 operator question path, after the consult rung (FR-013)
  when one is available for that addressee. No message may hang a node or be
  silently dropped, and no degradation may move the asker's attempt ceiling.
- **FR-005**: Message and reply text MUST NOT reach any verdict: the FR-012
  amendment's hole widens only from "park and page the operator" to "park and
  route", and a test MUST assert message content cannot influence gates or judge.
- **FR-006**: The number of outstanding peer messages per node MUST be limited by
  configuration, and a send beyond that limit MUST be refused to the asker with
  the refusal naming the configuration field and its value.
- **FR-007**: A credential value MUST NOT appear in a message body, in a reply,
  or in a stored message row, and the verification component's credential sweep
  MUST drive a message write and a resolution inside its own run so those bytes
  are among the ones it searches. This requirement is scoped to the two surfaces
  US1 lands; the mailbox file and the mirror notification are FR-020 and the
  written consult configuration is FR-021, each owned by the story that creates
  the surface, because a requirement no story can satisfy is a requirement its
  judge must fail.
- **FR-008**: Every message and reply MUST be persisted in the verification
  store, attributed to sender and recipient, alongside 008's questions, and a
  message MUST resolve exactly once under the same first-wins arbiter
  `factory/verify/store.py:1808` — `resolve_question` applies to questions.
- **FR-009**: External peers MUST be declared in an operator-owned registry
  naming peer, transport, address and expiry; the first transport MUST be a
  durable filesystem mailbox with one file per message and replies swept from an
  outbox; unregistered names MUST be refused as undeliverable; and a registry
  name that collides with a node id or a persona name MUST refuse at load.
- **FR-010**: Every external send MUST be mirrored to the operator over the
  existing notify bridge as a notification requiring no action.
- **FR-011**: A message addressed to a node in a sibling epic MUST be delivered
  as a signal to that epic's workflow and buffered with the incurious discipline
  of the existing signals — stored even when unknown, never validated against
  unwritten state — and a signal to a workflow that is gone MUST be caught in the
  activity and degraded, never raised into the workflow.
- **FR-012**: The channel's transport decision and the FR-012-amendment
  extension MUST be recorded in the decision log at landing, and the architecture
  docs MUST name the peer channel, its registry and the consult runner.
- **FR-013**: A message addressed to a persona, or to a node with no live or
  future attempt, MUST be answerable by an ephemeral consult when one is
  available: spawned with the persona registry's model, no gates, no judge, no
  verdict; its reply MUST thread back by message id and its process, key and
  context MUST be discarded after the reply. A consult whose asker has no
  readable worktree MUST still answer from assembled context, and its reply MUST
  name which context it had. A consult that fails, expires or declines MUST
  degrade per FR-004, and a consult MUST NOT send peer messages.
- **FR-014**: Consult memory access MUST be scoped to a factory-owned memory bank
  named in operator-owned configuration; no factory agent may be granted the
  operator's personal bank; a configuration naming a second endpoint MUST be
  refused with no file written; and a consult with no bank configured MUST still
  answer from assembled context alone.
- **FR-015**: Consult spawns MUST be limited by configuration, and each consult's
  spend MUST be metered in the ledger under its own key alias, attributed to the
  asking node. Two consults answering for the same node, attempt and persona MUST
  produce two rows: the alias column at `factory/usage/ledger.py:69` is `UNIQUE`,
  so an alias built the way an attempt's is built would collapse them into one
  and overwrite the asker's own row.
- **FR-016**: A park awaiting a peer reply MUST leave the epic building. It MUST
  NOT set the scheduler's pause flag, MUST NOT occupy one of the epic's
  concurrent-node slots — neither the general limit read at
  `factory/workgraph/workflow.py:1089` nor the subscription limit read at
  `factory/workgraph/workflow.py:1102` — MUST NOT clear a pause that another path
  set, and the scheduler MUST wake on a peer message rather than only on a task
  finishing. It MUST be a distinct node state, and that state MUST be classified
  deliberately at every site that reads the park today. Those sites are not to be
  taken from this list on trust: run
  `grep -n 'WAITING_OPERATOR\|_PARKED' factory/workgraph/workflow.py` and account
  for its output in the diff. That grep finds only the park's *spellings*, so two
  of the decisions below are not in it and MUST be added by hand — the unreachable
  set (`factory/workgraph/workflow.py:300`) and the terminal set
  (`factory/workgraph/workflow.py:313`) name states by their own names, and a park
  is defined by its absence from them. At 602a92c the decisions are those two, the
  alias and its incident comment
  (`factory/workgraph/workflow.py:344`), the status derivation
  (`factory/workgraph/workflow.py:903`), the merge-gated dead-edge predicate
  (`factory/workgraph/workflow.py:1534`, inside
  `factory/workgraph/workflow.py:1522` — `_dead_edge`), the drain exemption
  (`factory/workgraph/workflow.py:1606`), the park itself
  (`factory/workgraph/workflow.py:2006`), the 079-US3 raise-path release
  (`factory/workgraph/workflow.py:2309`, inside
  `factory/workgraph/workflow.py:1715` — `_run_node`, which reads the park and
  then clears `self._paused` at `factory/workgraph/workflow.py:2311` on any raise
  out of a parked node — the cross-clear this requirement forbids, on the path
  nobody looks at), the kill-while-parked branch
  (`factory/workgraph/workflow.py:2381`, inside
  `factory/workgraph/workflow.py:1715` — `_run_node`) and the close-out guard
  that archives and clears a node's remote branch
  (`factory/workgraph/workflow.py:3137`, inside
  `factory/workgraph/workflow.py:3087` — `_close_out`). An asker's wait MUST NOT
  change any other node's dispatch eligibility, and MUST NOT cause any node's
  remote branch to be archived or cleared.
- **FR-017**: A reply from an **external** peer MUST be presented to the asking
  agent as attributed, advisory text — the prompt section naming the registry
  entry it came from and marking it as an outside opinion, not an instruction.
  Verbatim delivery (FR-003) is not in tension with this: the bytes are
  unchanged, the framing around them is not absent. The reason is that an outbox
  is a host directory anyone with filesystem access can write, so its content is
  untrusted input reaching a model's context. FR-005 already keeps it away from
  gates and the judge; this keeps it from reading as a directive.
- **FR-018**: A consult MUST be able to read the asking node's worktree as it
  stands at spawn time, uncommitted work included, and MUST NOT be able to write
  to it or to anything outside its own working directory. The grant MUST be a
  typed field on the invocation, emitted as one `--ro-bind` naming that worktree
  and ordered with every other bind, and enforced where the process is
  configured — never as a sentence in the consult's prompt and never as a path
  smuggled through `env`. The grant MUST add exactly that one path and widen the
  mount set no further. It MUST NOT be claimed as a narrowing: the backend
  already binds the whole runtime root read-only
  (`factory/workgraph/adapter.py:538`) and every node worktree lives inside it,
  so sibling worktrees are readable and unwritable in every attempt today, and a
  test that only observes the read proves nothing about this requirement — which
  is why US8-S1 asserts the declared bind against a control invocation that
  carries none. The granted path MUST be the one
  `factory/workgraph/worktree.py:289` — `worktree_path` derives for the asker's
  node, resolved once rather than rebuilt from strings.
- **FR-019**: A peer message addressed to a node whose attempt is already in
  flight MUST be delivered to that running attempt without requiring the agent to
  have asked a question first, and the attempt's reply MUST be read back the same
  way. The prompt instructions that tell an agent to watch its inbox MUST be
  present only for an attempt that has one.
- **FR-020**: A credential value MUST NOT appear in a mailbox file or in a mirror
  notification, and the attempt-side credential sweep MUST send one external
  message inside its own run, with the mailbox root inside the tree that sweep
  walks, so both surfaces are among the bytes it searches.
- **FR-021**: A credential value MUST NOT appear in a consult's written
  configuration file, and the attempt-side credential sweep MUST drive that write
  inside its own run.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-007, FR-008]
US2:
  depends_on: []
  depends_on_merged: [US8]
  implements: [FR-019]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-009, FR-010, FR-017, FR-020]
US4:
  depends_on: []
  depends_on_merged: [US3]
  implements: [FR-011, FR-012]
US5:
  depends_on: []
  depends_on_merged: [US7]
  implements: [FR-013, FR-014, FR-015, FR-021]
US6:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-002, FR-003, FR-004]
US7:
  depends_on: []
  depends_on_merged: [US9]
  implements: [FR-016]
US8:
  depends_on: []
  depends_on_merged: [US5]
  implements: [FR-018]
US9:
  depends_on: []
  depends_on_merged: [US6]
  implements: [FR-005, FR-006]
```

The chain is strictly serial — US1 → US6 → US9 → US7 → US5 → US8 → US2 → US3 →
US4 — and every edge is a merge-edge (003 FR-009), because each dependent imports
modules its predecessor lands, so its worktree must clone a base already
containing the predecessor's merge. The deriver requires `depends_on: []` spelled
out even when empty.

US6 depends on US1 because routing needs an addressee to route and a row to
resolve against, and US1 changes no interpreter code at all. US9 depends on US6
because a limit counts outstanding messages and a guard fences message text, and
neither exists until routing does; it lands before the park so the loop it stops
is bounded before waiting for a reply becomes cheap. US7 depends on US9 because
both edit the routing seam US6 landed, and the park is the change that must go in
last and alone. US5 depends on US7 because the consult is a rung inserted into
the degradation ladder US6 lands and its reply must be able to reach an asker
that is parked, which is US7's state. US8 depends on US5 because the grant types
an invocation the consult runner builds, so the call site must exist before the
field it carries means anything. US2 depends on US8 rather than beside it because
the adapter's inbound direction delivers whatever routing produced, consult
replies included, and because both edit
`factory/workgraph/adapter.py`. US3 depends on US2 because an external reply
arriving mid attempt is the inbound direction applied to an untrusted sender,
which is FR-017. US4 depends on US3 because registry names and epic names share
one namespace that must exist before a third kind of address joins it, and
because it carries the closing documentation duties.

**US1, US6, US9 and US7 are what one story used to be, split three times on
measurement.** The 2026-08-08 US1 carried the addressee grammar, the workflow
routing and buffers, the non-pausing park, degradation, the limit, a new store
table, the prompt section and the credential sweep. It was dispatched once and
**killed**, and the salvage of that unfinished attempt measures 111,655 bytes
across fifteen files — 1.70x the refusal threshold, before any evidence was
pasted into it, and a floor rather than a size because the attempt never
finished. The first cut, at the interpreter boundary, left US1 (the grammar and
the store) and US6 (the interpreter); measuring US6's half of the same salvage
against `factory/verify/diffbounds.py:66`'s `DIFF_REFUSAL_THRESHOLD` showed it
over on its own, so the second cut took the park out as US7. The third cut, taken
on 2026-09-04 rather than deferred to a pre-dispatch measurement nobody can
perform, takes the outstanding-message limit and the no-verdict guard out as US9
— because US6's remaining headroom was computed against an evidence list that
omitted an assembled prompt, and an assembled prompt carries the whole of
`plan.md` verbatim. US1 touches no interpreter file; US6 touches the interpreter,
the routing activities and the worker registration; US9 touches the routing seam
and the two guard tests; US7 touches the interpreter's park sites and one enum
member. Story numbers are additive here — nothing in this spec has landed, and
the numbers already written keep their meaning.

**US8 is the same cut applied to US5.** The consult story carried a whole new
activities module, a per-consult configuration writer, a ledger widening *and*
the sandbox grant, and § Sizing gave it no figure at all — the one story in the
spec whose size was never measured, in a spec whose splits are all measurements.
US8 takes FR-018: a typed field on an invocation and one bind tuple in
`factory/workgraph/adapter.py`, plus the one call site in US5's launcher that
sets the field.

**US5's placement is an operator decision (2026-08-18), kept on 2026-09-04 with
its premise corrected, and its neighbour re-ordered on 2026-09-04.** That
decision argued from a configured concurrency of 1
— at most one node running, so a same-epic peer is nearly always a peer that is
not running, and the consult is the only addressee class that answers the same
hour. The dial is 2 now (`ergane.yaml:151`, raised 2026-08-30), which weakens
that argument without reversing it and shifts weight toward US2's in-flight
delivery. The ordering is kept anyway: US2 is the transport for whatever routing
produces, consult replies included, so it belongs behind the rung it carries,
and the original chain's placement of consults behind the external mailbox is
what the 2026-08-18 decision was correcting. US8 now sits between them, which
does not disturb that reasoning: it is the consult's own invocation being typed,
and US2 edits the same adapter file, so the two are serial for the ordinary
reason.

US5 and US3 both insert a rung into the same routing ladder, which is a second
reason nothing here runs beside anything else: two in-flight worktrees editing
one function is a merge-queue conflict where the second lander rebases blind. At
the configured concurrency of 2 the serial chain does cost something — the epic
runs one node at a time where it could run two — and that price is paid on
purpose, because every dependent here imports a module its predecessor lands and
a base without that merge does not import.

## Assumptions

- 008 is landed and live (attested 2026-08-07), 041 moved its question
  lifecycle into a child workflow (attested 2026-08-16), and 126 landed on the
  same close-out path on 2026-09-02: marker grammar, ferry files, QUESTION
  termination, park/expiry, answer signal, question store, the Telegram bridge
  and the branch-archiving close-out are all present to extend.
- The homelab agent is a Claude Code instance on this host; the mailbox path and
  the one-line instruction telling it to sweep its inbox are operator wiring
  recorded at onboarding, not factory code. Delivery is durable; attention is the
  peer's own affair — which is exactly why FR-010 mirrors every external send.
- Epic concurrency stays at the operator's configured limit, which is
  `max_concurrent_nodes: 2` and `max_concurrent_epics: 1` at 602a92c
  (`ergane.yaml:151`, `ergane.yaml:150`). Nothing in this spec may be *correct*
  only at a particular value: US7's tests pin both node limits to 1 because that
  is the configuration in which a held slot is observable, and they install a
  registry in which the scripted nodes' persona is `agent: subscription`, because
  the shipped `implementer` is `agent: claude-code` (`personas.yaml:270`) and the
  second bound is not evaluated for a node that is not subscription-routed. US4
  is valuable above one epic and harmless at one.
- A Hindsight server is reachable on the LAN and a factory-owned bank can be
  provisioned for it; provisioning and the endpoint value are operator preflight,
  and FR-014 makes the whole memory layer optional — a factory with no bank
  configured still consults, from assembled context.
- This repository's agents run under the bwrap sandbox (`ergane.yaml:26`), which
  is what makes FR-018's grant a mount rather than a request — and what already
  makes every node worktree readable inside every sandbox, through the runtime
  root bound at `factory/workgraph/adapter.py:538`. A host configured for the
  direct launch has neither: no enforcement and no incidental read, which is why
  FR-018's grant is declared on the invocation rather than inferred from the
  mount set.

## Decision: Temporal signals as the spine, A2A at the edge, no MCP tool (decided 2026-08-08, Bryan + assistant)

Three transports were considered for the factory's internal message routing.

**Temporal signals win.** Messages between agents in this factory are messages
between the workflows that own those agents — the agents themselves are
ephemeral subprocesses that the interpreter dispatches, monitors and kills.
Signals are the durable, replayed, ordered primitive this codebase already trusts
for exactly this shape: `question_answered` carries free text,
`escalation_resolved` carries decisions, and both survive worker crashes and
replay by construction. Queries are read-only by design and cannot deliver; they
remain what they are today, the status surface. The last mile to a running agent
is the 008-US4 ferry — the filesystem the agent already owns, polled by the
monitor beat that already runs.

**A2A is deferred to the registry's transport seam.** The Agent2Agent protocol
solves inter-organization agent discovery and messaging between long-lived HTTP
servers. Ergane's agents live minutes and own no port; standing an A2A server per
attempt inverts the process model, and adopting A2A as the internal bus would
rebuild — with a new dependency and a new attack surface — the durability and
routing Temporal already provides. Today zero peers speak A2A: the homelab agent
is a Claude Code instance that can read a mailbox with one instruction line. When
a real A2A peer exists, it becomes one more `transport` value in the registry,
implemented behind the same interface as the mailbox, and nothing above the
registry changes.

**An in-agent MCP messaging tool was rejected.** Handing every agent a
`send_message` tool means wiring an MCP server into every dispatch and widening
the FR-012 surface — agent-authored calls mutating factory state — that D-018
deliberately keeps at one marker. The ferry file grammar keeps the adapter in
control of what leaves an attempt and keeps the amendment's hole at "park and
route".

## Decision: ephemeral consults, and the two-layer memory split (decided 2026-08-08, Bryan)

The operator asked whether Temporal could spin up an agent to process a message
when none is attached to receive it, discard it afterward, and lean on Temporal
plus Hindsight for what such ephemeral agents remember. **Decided: yes, as US5,
with the memory split drawn deliberately.**

The spawn is not new machinery — every attempt in this factory is already an
ephemeral agent an activity dispatches, monitors and tears down, and the judge is
a persona that lives one request at a time. What US5 adds is an attempt with the
ladder removed, whose output contract is a reply instead of a diff.

**Amended 2026-08-18 (Bryan): a consult reads the asker's worktree.** The
original v0 gave consults no worktree, on the judge's precedent —
context-in-prompt, one request, no tree. That precedent is the wrong one. The
judge scores a *finished* diff and is deliberately blinded to everything else; a
consult advises *work in progress*, and the question an implementer actually asks
— "is this the interface the plan meant" — is about code that exists only in its
worktree, uncommitted. A consult that cannot see it answers from the plan and
repeats what the asker already read.

So the grant is a read of exactly that worktree, and three properties are
deliberate. It is **read-only, enforced by the grant** rather than by
instruction, because the boundary finding
`hardening/agent-worktree-boundary` is open and critical with ninety recorded
occurrences and every one of those agents had been told to stay put. It is
**bounded to one path**, not the persona registry's `needs_worktree` — that field
provisions a persona its own fresh worktree from a base, a different capability
with a larger blast radius, and conflating the two is how this becomes a write.
And it is **unquiesced**: the asker is parked awaiting the reply, so its tree is
as settled as it will get, and a half-written file is a fact rather than an error.

**Read in 2026-09-04's light (refinement, not an amendment).** Two of the three
properties above are already true of every agent this factory launches, and one
is not. Read-only *is* enforced by a grant: `_build_argv` binds the runtime root
read-only (`factory/workgraph/adapter.py:538`) and every node worktree sits
inside it (`factory/workgraph/worktree.py:289` — `worktree_path`), so a consult
can already read the asker's tree and already cannot write to it. Unquiesced is
unchanged. **Bounded to one path is not**: the existing read is the whole runtime
root, sibling worktrees and stores included. Narrowing that would change the
mount set every attempt shares and is out of this spec's scope, so FR-018 asks
for the narrower thing it can actually deliver — a declared, typed grant naming
one worktree, which is what makes the capability survive a mount-set change and
what US8-S1 asserts against a control. The decision above is not withdrawn; its
third property is restated as a property of the declaration rather than of the
namespace.

One consequence to state rather than discover: the advice a consult gives is
shaped by real code, reaches the implementer's next attempt and shapes the diff —
while FR-005 keeps message text away from gates and the judge. So the judge
scores work influenced by reasoning it cannot see. That hole is 008's, already
open at "park and route"; this widens what the advisor knows, not what the judge
is denied. It is accepted, and named here so the next person does not find it by
surprise.

Memory splits in two layers. **Deterministic, epic-scoped context comes from
Temporal and the repo** — the message, the spec and plan, the asker's identity,
the workflow's own question history — assembled into the consult's prompt from
records the factory already keeps, replay-safe and free. **Durable cross-epic
memory comes from Hindsight, through a factory-owned bank** — never the
operator's personal bank, which stays closed to headless agents so machine churn
cannot silt up what the operator reads (the operator's standing rule, adopted
here as factory policy: FR-014). This is also the channel's first agent-facing
MCP surface, and it does not reopen the messaging-tool rejection above: recall
reads memory and retain writes memory — neither touches node state, so the FR-012
hole stays at "park and route". One operational lesson is inherited from the
bank's own history: a retain acknowledgment cannot distinguish "stored" from
"extracted", so any factory retain path verifies extraction, never the ack.

## Decision: the operator is the floor, never the ceiling (decided 2026-08-08)

Every failure mode of every path in this spec — unknown name, dead peer, silent
mailbox, expired wait — lands on the 008 operator question path, because that
path is the one channel whose delivery and expiry semantics are proven in
production. The peer channel may only ever reduce the operator's load; it can
never add a way for a question to die unheard, because the worst case of every
branch is precisely the 008 behaviour the factory ships today. The decision-log
numbers are deliberately unassigned here — claimed at landing in
`docs/decisions.md`, per the 006/008 precedent.
