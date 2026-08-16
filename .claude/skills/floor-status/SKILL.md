---
name: "floor-status"
description: "Report what the factory floor is doing right now and when the remaining work will land: active nodes, per-spec backlog, and an ETA table derived from measured cycle times rather than guesses. Use when asked for status, an ETA, or what is left to build."
compatibility: "Requires the ergane CLI on PATH via scripts/ergane-env.sh, gh authenticated, and a checkout of this repository"
metadata:
  author: "operator session, 2026-08-16"
user-invocable: true
disable-model-invocation: false
---

# Floor status

Answer three questions, in this order, and never from memory:

1. **What is running?** — dispatched nodes and open pull requests.
2. **What is left?** — landed-versus-total per spec.
3. **When does it land?** — an ETA table driven by **chain depth**, not story count.

The whole point is that every number is measured. `CLAUDE.md` says this
repository can answer questions about itself; a status report that recites a
remembered figure is worse than no report, because it reads as evidence.

## Ask the tree first

```bash
eval "$(scripts/ergane-env.sh)"     # NOT `source` — it emits export lines
git fetch origin --quiet
```

**Open pull requests, with their arm state:**

```bash
gh pr list --repo bryantharpeorg/ergane --state open \
  --json number,mergeStateStatus,autoMergeRequest \
  --jq '.[] | "#\(.number) \(.mergeStateStatus) auto=\(.autoMergeRequest!=null)"'
```

`auto=false` on its own means nothing, and reading it as a dropped arm will
send you re-arming PRs that are already merging. **A PR's `autoMergeRequest`
goes null the moment it enters the merge queue**, so the armed-and-progressing
state and the arm-dropped state look identical in that column. You have to ask
the queue:

```bash
gh api graphql -f query='{repository(owner:"bryantharpeorg",name:"ergane"){
  mergeQueue(branch:"ergane-buildout"){entries(first:10){nodes{
    position state pullRequest{number}}}}}}' \
  --jq '.data.repository.mergeQueue.entries.nodes[]? | "q\(.position) #\(.pullRequest.number) \(.state)"'
```

Read the two together:

| `auto=` | in the queue | meaning |
| --- | --- | --- |
| `true` | no | armed, waiting on checks — fine |
| `false` | **yes** | in the queue — fine, this is the normal post-entry state |
| `false` | **no** | **the arm dropped.** Work stalled on you, not on the queue |
| `true` | yes | transient, mid-entry |

Only the third row needs action: re-enqueue with a bare `gh pr merge <n>`.
The drop is real and it happened repeatedly on 2026-08-16 — but so did the
false alarm, which cost a `gh pr merge` against a PR already at queue position
one. Check both before you touch anything.

**Backlog per spec** — `landed` reads git, `state:` reads frontmatter, and they
disagree whenever nobody has attested a completed epic:

```bash
for d in <spec-dirs>; do
  t=$(grep -c '^### User Story' specs/$d/spec.md)
  l=$(uv run ergane spec landed specs/$d --default-branch ergane-buildout 2>/dev/null | grep -c 'landed at')
  printf "  %-30s %s/%s\n" "$d" "$l" "$t"
done
```

**`--default-branch ergane-buildout` is not optional.** `ergane spec landed`
scans `main` by default and the factory does not land there, so the default
under-reports between promotions.

**Chain depth per spec**, which is what actually governs the ETA:

```bash
uv run ergane spec derive specs/$d --target-repo "$PWD" --json 2>/dev/null | uv run python -c "
import json,sys
g=json.load(sys.stdin).get('graph',{})
nodes={n['id']:(n.get('depends_on_merged') or []) for n in g.get('nodes',[])}
def depth(i,seen=()):
    if i in seen: return 0
    return 1+max([depth(d,seen+(i,)) for d in nodes.get(i,[])] or [0])
print('depth', max([depth(i) for i in nodes] or [0]), 'nodes', len(nodes))"
```

**Node progress**, for anything dispatched into a worktree — commits against the
node's own base, and the last subject line:

```bash
git -C "$wt" log --oneline origin/ergane-buildout..HEAD | wc -l
git -C "$wt" log -1 --format='%s'
```

## Building the ETA table

**Chain depth governs, not story count.** Six independent stories finish in one
round; six chained stories take six. Report per chain, and name the longest one
as the critical path explicitly — it is the only number that moves the finish.

Per-story wall time = **agent build + landing overhead**:

- **Agent build**: measured 24–84 minutes on 2026-08-16 across a dozen stories,
  median around 55. Re-measure from the current session's own task durations
  rather than reusing that range; it will drift with model and story shape.
- **Landing overhead**: boundary gate ~4:15, judge 2–4 minutes, PR and merge
  queue 10–20. Roughly 25 minutes, and **the judge can run concurrently with the
  gate** — it is network-bound and the gate is CPU-bound. Serialising them costs
  four minutes a story for nothing.

So a story is roughly **1.0–1.75 hours** with up to four nodes in parallel.

### State the assumptions the number rests on

A range without its assumptions is a guess wearing a decimal point. Always say:

- **Rework rate.** On 2026-08-16 it ran ~45% — five of eleven stories needed a
  second pass, each costing +20–55 minutes. Fold it *into* the ranges and say you
  have, rather than adding it as a surprise later.
- **What would blow the estimate**, concretely and from the record — not
  "unknowns". Two live incidents that day (test schedules created on the
  production namespace, a toolchain regression) each cost about an hour of
  operator attention and neither was predictable.
- **Sample size.** One day of data with 2–3× variance is a planning number, not
  a commitment. Say so.

### Then give the one number you would actually bet on

End with a single narrow claim backed by why — "048 complete within two hours,
because its last story is already three commits in". A table of ranges plus one
falsifiable bet is more useful than five confident ranges.

## Things that are not in the numbers and should be said anyway

- **Degraded surfaces with known expiries.** `ergane roadmap status specs`
  resolves the newest `roadmap-specs*` run regardless of whether it failed, so
  one failed run breaks the verb until it ages out of the 72-hour retention
  window.
- **Whether the roadmap schedule is paused**, and whether that is deliberate.
- **Findings direction.** Report the open/critical count *and* whether it rose.
  A day of hard running should raise it — findings come from running things, not
  from reading them — and a falling count during heavy work is the suspicious
  one.
- **File contention.** `depends_on_merged` models what a story needs to *exist*,
  not what it will *touch*. Two correctly-independent stories of one epic can
  both extend one file; `factory/cli/init.py` took eight commits in a day and
  cost two hand-merges and a rework cycle. If two in-flight nodes plausibly touch
  the same surface, that is a real risk line, and it will present as tests dying
  after a clean rebase rather than as a conflict.

## Honesty rules

- **"Everything is green" is almost never true.** Separate *green* from *not
  green but not blocking* and say both. The second list is the one worth reading.
- **Distinguish what you ran from what you were told.** An agent's report is
  evidence, not proof; a merge-group build is the gate, and a pull request's own
  green check proves little.
- **If a number moved since the last report, say which way and why.** An estimate
  that silently improves reads as noise; one that improves *because three of four
  nodes are nearly done* reads as information.
