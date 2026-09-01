# `ergane status`

> what the whole floor is doing right now

The morning question in one screen. Reads only; writes, signals and creates
nothing.

```
ergane status [<specs-root>] [--json]
```

| argument | default | meaning |
| --- | --- | --- |
| `<specs_root>` | `specs` | the specs root to read |
| `--json` | | print the whole floor as one document instead of the five sections |

## The five sections

```
roadmap
  schedule: ergane-roadmap (running)
  run: roadmap-specs-2026-09-01T12:25:00Z
  next tick: 2026-09-01T12:30:00+00:00
  dispatch: running
  running: -
  parked: 0

epics
  none running

queue (readiness: attestation, plus landings on ergane-buildout (3359a5ae7cf8) in /home/admin/code/ergane, read without fetching)
  072-a-stale-anchor-fails-validate-not-the-attempt  ready  dispatchable

drafts
  017-peer-channel                                         draft
  …

pace
  no epic is running
```

**roadmap** — the scheduler's disposition: whether it is running, which run is
current, when the next tick fires, whether dispatch is paused, and how many
specs are parked.

**epics** — every running epic with its stories and their states.

**queue** — the ready specs and, for each, whether it is dispatchable or what
blocks it. Read the parenthetical: it names the branch and the exact commit
readiness was computed against, and it says **read without fetching**. If you
have not fetched, the queue is answering about the tree you have.

**drafts** — everything at `draft`, which is the refinement backlog.

**pace** — each epic's measured attempt wall-times. This is the only place the
factory tells you how long things are actually taking, rather than how long they
usually take.

## What it does not carry

**Persona and model.** Neither this document nor `build status --json` says
which persona a node is running under. The authority is the epic's own workflow
start payload; the on-disk `workgraph.json` is not rewritten by the roadmap and
will disagree for anything the roadmap dispatched.

That distinction matters for cost, not curiosity: a subscription-routed persona
bills nothing per token and a gateway-routed one bills every token, and a status
that hides the difference is reporting an average nobody is experiencing.

**Anything about GitHub.** Pull requests, merge queue positions and check runs
are not in this document. `gh` is the tool for those, and a pull request's own
green check is not the gate — the merge-group build is, because it tests the
speculative merge rather than the branch.

## See also

- [`ergane spec list`](spec.md) — the corpus alone, without the running floor
- [`ergane build status`](build.md) — one epic in full detail
- [`ergane roadmap status`](roadmap.md) — the scheduler alone
- [`ergane escalations list`](escalations.md) — what is waiting on you
