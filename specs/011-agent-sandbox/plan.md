# Plan: The worktree is where the agent starts, not where it is kept

Refined against the tree at `5f0042e` on 2026-08-11. Every anchor below was
resolved against that commit. If one does not resolve when you read it, trust the
code and say so in your handoff rather than hunting.

## What to read before writing anything

| Thing | Where | Why |
| --- | --- | --- |
| The entire current boundary | `factory/workgraph/adapter.py:469-477` | `cwd=str(worktree)` and nothing else. This is what US2 replaces |
| The agent's argv | `factory/workgraph/adapter.py:441` | `argv(context)` — US2 wraps this, it does not rewrite it |
| Why the child is a session leader | `factory/workgraph/adapter.py:463`, `:476` | `start_new_session=True` exists for the deadline, see trap 2 |
| The pid file and the group kill | `factory/workgraph/adapter.py:282`, `:404`, `:665` | The deadline's whole mechanism; US2 must keep it working |
| Transcript archiving | `factory/workgraph/adapter.py:696` | Reads `env["HOME"]` and **returns early if absent** — trap 3 |
| The dead runtime seam | `factory/verify/factory_yaml.py:61`, `:99`, `:172` | `runtime:` is parsed and validated today |
| …and that it is dead | `factory/verify/models.py:187` | *"`runtime` is recorded but execution-reserved — gates run as `bash -c` on the host."* |
| The gate seam to copy | `factory/verify/gates.py:153` | `GateExecutor` is already a `Protocol` |
| The host implementation | `factory/verify/gates.py:296-312` | `bash -c` in the worktree. US3 adds a sibling, it does not edit this |
| The declared image | `factory.yaml:15` | `runtime: ghcr.io/astral-sh/uv:python3.11-bookworm` |

The shape of this work is unusually favourable and worth saying out loud: the
manifest **already declares the image it intends to run in**, the key is already
parsed and validated, and gate execution is **already behind a Protocol with one
implementation**. US2 and US3 are finishing a design that was drawn and then left
unwired — not introducing a concept.

## US1 — the detector

Capture `git status --porcelain` (or equivalent plumbing) over the *target
repository* at attempt start, capture it again at teardown, diff the two, and
file a finding when tracked paths differ. Key it so recurrence is countable per
epic/node, and put the changed paths in the evidence.

Where it hangs is a judgement call the implementer owns, but it must be a place
that runs on **every** termination path — completed, agent error, timeout, killed
— because the breach is likeliest on the paths that end badly. The teardown
bracket that 010 just made total (`try/finally` around the key lease) is the
precedent for "runs whatever happens": read it before choosing.

Note the target repo is not always the operator's checkout — it is
`graph.target_repo`. Write it against that, not against a hardcoded path.

## US2 — the boundary

Wrap the launch at `adapter.py:469` so the agent executes inside the resolved
`runtime:` image, rootless. What must be inside its filesystem view:

- the node worktree, writable;
- the git plumbing that worktree needs (see trap 1) — the *plumbing*, not the
  working tree it lives beside;
- the toolchain the agent needs to work: the agent CLI, `git`, `uv`, and the
  interpreter the gates will call;
- a writable temporary directory;
- a home for the agent CLI's own state (see trap 3, and 018's discussion of why
  a bare home is enough).

What must **not** be inside it: the target repository's working tree, and the
operator's home.

## US3 — the gates

Add a second `GateExecutor` beside the host one at `gates.py:296`. Do not edit
the host implementation; do not change the Protocol. `run_gates` at `:388` picks
between them. This is the whole reason `GateExecutor` was made a Protocol.

## Traps

**Trap 1 — the one that decides the design. A worktree's `.git` is a file, not a
directory.** Verified on this tree:

```
$ cat .factory/worktrees/<epic>/<node>/.git
gitdir: /home/admin/code/ergane/.git/worktrees/<node>
```

So git *inside* the worktree reaches back into the target repository's `.git`
directory, and "just don't mount the target repo" breaks `add`, `commit`, `diff`,
`branch` and salvage — every operation the attempt performs at its end. The
boundary must expose `.git/worktrees/<node>` **and the shared object store**
while keeping the working tree invisible. Get this wrong and the failure arrives
at commit time, after the agent has done all its work, which is the most
expensive place in the ladder to discover it. Prove it with FR-005's scenario
(`git add`/`commit`/`diff` inside the boundary) before building anything else in
US2.

**Trap 2 — the deadline is a process-group kill, and a container changes what the
pid means.** `start_new_session=True` (`:476`) makes the agent a session leader
so its pid *is* its process-group id (`:749`), the pid file records the pgid
(`:404`, `:746`), and the deadline kills the group (`:665`). Put the agent behind
a container runtime and the pid the adapter holds is the *runtime client's*, not
the agent's; killing that group can leave the container and its children running
while the workflow believes the attempt is over. That is a leaked attempt holding
a live virtual key — the exact class 010 just spent an epic closing. FR-006 is
not a formality: whatever mechanism you choose, the termination path must be
re-established deliberately and tested with a deliberately hanging agent.

**Trap 3 — the transcript disappears silently.** `_archive_session`
(`adapter.py:696`) resolves the session file from `env["HOME"]` and **returns
early when `HOME` is absent**, because an agent that wrote no transcript is not
an error. Inside a container, `HOME` is the container's, and the archive step
runs on the host: unless the agent's home is a bind of a host path the archive
step can read, every attempt silently stops producing a transcript and the code
treats it as normal. The test that catches this asserts on the archive's
*contents*, not on the environment. This is the same failure shape 018 carries as
its own trap — read that one too.

**Trap 4 — do not let this quietly become 018, or 018 quietly become this.** If
US2 lands first, the agent stops seeing the operator's `HOME` as a side effect,
and it will be tempting to close 018 as done. Do not: 018 *states* the property,
tests it and keeps it stated, and a later change to the mount set could restore
the inherited home with nothing failing. If 018 lands first, US2 must not undo
its `PASSTHROUGH_ENV` edit while rearranging the environment. The two specs are
orthogonal on purpose and each keeps its own assertion.

**Trap 5 — the suite must not need a container.** FR-010. Ergane's own CI and
every developer machine must stay able to run the tests. `GateExecutor` shows the
pattern: a Protocol with a substitutable implementation. Put the agent boundary
behind the same kind of seam and let the tests drive a fake. A suite that skips
when no runtime is present is not compliance — that is
`live-tier-skips-by-guard-not-marker`, an already-filed defect, and a skipped
test proves nothing.

**Trap 6 — rootless, or the deployment story changes.** The factory runs as the
operator's uid with no daemon. A mechanism requiring root or a system service
moves part of the guarantee outside the repository, where `ergane doctor` cannot
see it and no test can assert it. Prefer something that works unprivileged.

**Trap 7 — the detector must not clean up after the agent.** FR-002. It is
reporting on the operator's own tree, which may contain the operator's own
uncommitted work. A detector that "helpfully" stashes or checks out destroys real
work to make a metric look clean. Read-only, always.

**Trap 8 — do not contain the worker.** Out of scope, and worth restating here
because the refactor invites it: the activities, the workflow and the merge-queue
poller all stay on the host. Only the agent process and the gate process move.

## What "done" looks like

A scripted agent that tries to write an absolute path into the target
repository's working tree gets an error on its own tool call; `git status` in the
operator's checkout is byte-identical before and after; and the same attempt
still commits, is judged, and lands. Then, on a host with no container runtime
installed at all, `uv run pytest` is green.
