# Ergane

## If you are a factory implementer node, this is not your brief

You were dispatched with an assembled prompt and a standards path named by `factory.yaml`.
Those bind you; this page does not. It is written for an operator session — an agent
working *on* the factory rather than a node working *inside* it. Nothing here widens,
narrows or overrides your task scope. You are reading it only because it sits on an
ancestor path of your worktree. Follow your prompt and the standards file it names.

## What this is

Ergane is a software factory that builds itself: specs go in, merged and verified code
comes out, and no production code in this repository is written by a human. A Temporal
workflow compiles one spec into a graph of user stories, dispatches each to an agent in its
own git worktree, runs deterministic gates and an LLM judge over what comes back, and lands
what passes through a merge queue. `docs/architecture.md` is the description — read it
before you reason about mechanism, rather than re-deriving mechanism from this page.

## Which document binds

- `.specify/memory/constitution.md` — **normative**. `factory.yaml` names it as the
  standards path, and every dispatched attempt is told to read and obey it. Editing it
  changes what future agents are held to, which is why it is promoted into rather than
  appended to.
- `docs/architecture.md` — descriptive. How the thing works. Binding on nobody.
- `docs/decisions.md` — the decision log, immutable by construction. Supersede an entry
  with a new one; never edit one in place.
- `CONTEXT.md` — the vocabulary. When a word here feels overloaded, it probably is; that
  file says which term to use and flags the ambiguities that have already cost money.

## Ask the system, don't trust this file

This repository can answer questions about itself, so this page names no spec states, no
story counts and no spend figures. All three have live sources, and a copy here would rot
between the day it was written and the day you read it.

| Question | Ask |
| --- | --- |
| Every spec's state, and what blocks each one | `factory-roadmap render specs` |
| Which of a spec's stories are landed in git, story by story | `factory-epic landed <spec-dir>` |
| What one epic is doing right now | `factory-epic status <epic-id>` |
| What defects are open, and how often each has recurred | `factory-doctor list` |
| What an epic cost | `factory-usage --by epic` |
| What a running workflow is actually doing | Temporal's Web UI on `:8233` |

`scripts/ergane-env.sh` puts the environment those commands need into your shell.

One trap in that table: `factory-epic landed` scans `main` unless told otherwise, and the
factory does not land on `main` — it lands on the buildout branch, and `main` moves only
when an operator promotes. Between promotions the default under-reports. Say
`factory-epic landed <spec-dir> --default-branch <branch>` whenever the answer matters.

## How to work here

The measured leverage is in refinement and verification, not in dispatch. Starting an epic
is a few commands and nearly free. A story that reaches an agent under-specified is not:
the same week produced a spec whose stories each passed on the first attempt after a
pre-dispatch pass fixed five defects, and a story that burned more than six of those
attempts' combined cost in one go because it was oversized and split too coarsely.

- **Refine before dispatch.** Read a spec, its plan and its tasks as one set, and check
  every reuse claim and line anchor against the actual tree. A plan citing a function that
  has since moved sends the agent hunting for it, at your expense.
- **Verify what the factory believes, not what it reports.** A green suite and a PASS
  verdict are evidence, not proof — a fully green run has shipped a command that could not
  start. Run the thing.
- **Never modify factory code while an attempt is in flight.** The worker imports it live.
- **Spec edits reach only the next epic.** A running one compiled its graph at dispatch.
- **Landed story numbers are immutable.** New work takes new numbers, always.
- **A pull request's own green check proves little.** The merge-group build is the gate,
  because it is the one that tests the speculative merge rather than the branch.
- **Never press an escalation button on the operator's behalf.** Silence is a decision the
  operator is entitled to make, and expiry is part of the contract.

## Recall before you refine

Durable lessons live in cross-session memory rather than in the constitution. The
constitution is promoted *into*, once a defect class has recurred, and the doctor's ledger
is what makes "recurred" a fact instead of a recollection.

That routing has a consequence worth stating plainly: **a lesson in memory reaches no
implementer.** Nothing dispatches it. The only path from something you learned to something
an agent obeys runs through you, at refinement time, writing it into that spec's plan as a
**trap** — a named hazard the implementer meets as declared scope instead of as a failure.
So recall first, then put what you recalled into the plan. A lesson you keep to yourself
gets rediscovered by an agent, at full price.

## Where knowledge goes

| What you have | Where it belongs |
| --- | --- |
| A constraint that must change how future code is written, and has now bitten twice | `.specify/memory/constitution.md`, with a new `docs/decisions.md` entry |
| Something learned that helps you reason but binds no implementer | cross-session memory |
| Ongoing project state, goals or constraints not derivable from the tree | project memory |
| An open defect or risk, with its mechanism and its evidence | `factory-doctor report` |

`CONTEXT.md` defines the terms that table turns on — **binding rule**, **lesson**,
**finding**, **trap** — if the line between them is ever unclear.

## What this file may not become

A second standards channel. Implementer agents already have one, named by `factory.yaml`
and enforced at dispatch, and it was chosen deliberately so that nothing depends on a
`CLAUDE.md` being auto-loaded. Requirements for how code is written go there. This page
orients an operator session and nothing else, and `tests/test_claude_md.py` holds it to
that: every command it names must resolve, every path it cites must exist, and it may not
state a status that a live source already answers.
