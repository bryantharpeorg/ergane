# Plan — a `CLAUDE.md` for operator sessions

**Status**: planned, not written. Produced 2026-08-08 from a grilling session with the
operator. This document is the agreed shape and the reasoning behind it; delete it once
`CLAUDE.md` and its test exist, or keep it as the ADR-shaped record of why the file looks
the way it does.

**Goal**: an agent waking into this repo should learn, without being told, what Ergane is,
what it can do, and where its own leverage is.

## What was decided, and why

**1. Audience: operator sessions, not implementer nodes.** The factory already has a
channel to the agents that write code — `factory.yaml`'s `standards` key names
`.specify/memory/constitution.md`, prompt assembly emits *"Read `{standards}` in this
worktree before you write code, and obey it"*, and `prepare_worktree` fails the dispatch
loudly if the file is absent. D-025 chose that path deliberately, *"because a committed
file is adapter-agnostic — no reliance on `CLAUDE.md` auto-loading."* A CLAUDE.md must not
become a second standards channel.

**2. It will be inherited by agents anyway, so it carries a scope fence.** Claude Code
collects `CLAUDE.md` from the working directory *and every ancestor*. Verified empirically:
a file three levels above a child directory was loaded (a magic word planted in the parent
came back from the child). Node worktrees live at `<repo>/.factory/worktrees/<epic>/<node>`
because `DEFAULT_FACTORY_ROOT = Path(".factory")` resolves against the worker's cwd — so a
root `CLAUDE.md` is an ancestor of every attempt. Gitignoring changes nothing; the file is
on disk in an ancestor path.

Accepted cost: ~1.5k tokens per request for agents, small beside the ~72 MCP tool schemas
they already carry through the HOME-inheritance defect. Mitigation: the file opens with an
explicit fence telling implementer nodes it is not their brief.

Filed for later: moving the worktree root outside the repo, which fixes this properly and
also stops agents having the ledger, the verification store, and other epics' worktrees on
an ancestor path.

**3. Content: a map and an interrogation guide, not a snapshot.** As of 2026-08-08 the
system can answer questions about itself — `factory-roadmap render` for spec states,
`factory-epic landed` for per-story truth from git, `factory-doctor list` for open
findings. Anything with a live source is therefore forbidden in this file. The repo has
been bitten twice in a week by duplicated truth: a hardcoded model-alias list left the
trunk red for six hours after a persona swap, and derived `workgraph.json` artifacts are
tracked for three specs and untracked for three others.

**4. Centre of gravity: guard quality, not throughput.** Dispatching is four commands and
nearly free. The measured leverage is elsewhere: 015 landed three stories first-attempt at
$11.48 each after a pre-dispatch refinement pass fixed five defects, while 016's us4 — a
story flagged as oversized and split, but not enough — burned $78.73 on a single attempt.
And verification has a ceiling: 1,784 green tests plus three PASS verdicts shipped a
`factory-doctor check` that cannot start.

**5. Lessons default to memory; the constitution is promoted into.** Operator's call,
against the recommendation on this page's author. A lesson goes to cross-session memory
first and only becomes a **Binding rule** in the constitution after a defect class recurs.

The reasoning that makes this work: because a lesson in memory reaches no implementer, the
operator's refinement pass *is* the enforcement mechanism — recall, then write the lesson
into that spec's plan as a **Trap**, which is how it reached the agent in 016 (the plan's
`_git`-helper trap was ignored on attempt 1 and followed on attempt 3). And the doctor's
ledger is the recurrence counter that makes "twice" detectable rather than remembered, since
findings carry occurrence counts and a `regressed` status.

Accepted cost, on the record: a lesson only the operator can apply does not bind when the
operator is not in the loop. If the roadmap scheduler ever dispatches unattended,
memory-stored lessons reach nothing.

**6. Anti-rot: a test, not a convention.** In-idiom here — the `gh` command surface, the
forbidden-vocabulary sweep, and the FR-012 process discipline are all already asserted by
tests that read source.

## The file

`/home/admin/code/ergane/CLAUDE.md`, committed, 90–110 lines.

The repo is public: no infra hosts, no key paths, no Telegram specifics. Commands
reference `scripts/ergane-env.sh` rather than anything it decrypts.

### Sections

1. **Scope fence** (~5 lines, first thing on the page). If you are a factory implementer
   node, this is not your brief — follow your assembled prompt and the standards path in
   `factory.yaml`. Nothing here overrides your task scope.
2. **What Ergane is** (one paragraph). The factory builds itself from specs; no
   human-written production code. Pointer to `docs/architecture.md`, no architecture prose.
3. **The documents, and which one binds.** `.specify/memory/constitution.md` is normative
   and is what implementer agents are told to obey. `docs/architecture.md` describes.
   `docs/decisions.md` is immutable — supersede, never edit. `CONTEXT.md` is the
   vocabulary.
4. **Ask the system, don't trust this file.** `factory-roadmap render specs`,
   `factory-doctor list`, `factory-epic status <epic>`, `factory-epic landed <spec>`, the
   Temporal UI on `:8233`. Stated explicitly: this file names no spec statuses, no story
   counts, no spend figures, because all three have live sources.
5. **How to work here** — the operator contract:
   - Refine before dispatch; verify every reuse claim and line anchor against the tree.
   - Verify what the factory *believes*, not what it reports. A green suite and a PASS
     verdict are evidence, not proof.
   - Never modify factory code while an attempt is in flight.
   - Spec edits reach only the next epic.
   - Landed story numbers are immutable; new work takes new numbers.
   - A PR's own green check proves little — the merge-group build is the gate.
   - Never press an escalation button on the operator's behalf. Silence is a decision.
6. **Recall before refining.** The mechanism that makes lessons-in-memory work: recall,
   then write what you learn into *that spec's plan* as a **Trap**. Traps in plans are
   what reach implementers; memory does not.
7. **Where knowledge goes.** Four stores, one routing rule — binding-and-recurred to the
   constitution with its D-0xx entry; lesson to cross-session memory; project state to
   project memory; open defect with a mechanism to the doctor's ledger. Vocabulary for
   these terms lives in `CONTEXT.md`.

### Anti-rot test — `tests/test_claude_md.py`

- Every backticked `factory-*` verb the file names resolves (`--help` parses).
- Every repo path it cites exists.
- It contains no spec-status word adjacent to a spec id, so section 4's no-state rule is
  enforced rather than aspirational.

Rename a CLI verb or move a document, and the file that lied about it fails CI — instead of
being discovered six hours later by a burned attempt.

## Open items this plan depends on

- `factory-doctor check` is broken (`doctor/check-crashes-on-nested-asyncio-run`), so
  section 4 should cite `list` as the working entry point and not promise `check`.
- The HOME-inheritance defect (`hardening/agents-inherit-operator-home`) is what makes the
  token cost of an inherited CLAUDE.md relatively small. If it is fixed first, revisit
  whether the scope fence is still the right trade against moving the worktree root.
