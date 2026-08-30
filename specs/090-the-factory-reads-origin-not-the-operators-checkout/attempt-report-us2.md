# 090 US2 — attempt report

**Story**: a refresh that would destroy work parks the spec instead.
**Node**: `us2`, branch `factory/090-the-factory-reads-origin-not-the-operators-checkout/us2`.

## What the demonstration could and could not be

T017 asks for the plan's reflog demonstration **against a live roadmap
schedule**. That half could not be run from inside the node, and the reason is
mechanical rather than a judgement call:

- The operator's clone is mounted read-only in this node's sandbox
  (`touch /home/admin/code/ergane/.t017-probe` → `Read-only file system`), so
  the demonstration's first step — `git checkout -b operator/scratch` in that
  clone — cannot be performed, and the node's brief says it writes nowhere but
  its own worktree.
- There is no reachable orchestration: no `temporal` CLI on `PATH`, no `sops`,
  so `scripts/ergane-env.sh` refuses and `TEMPORAL_ADDRESS` is unset. A tick
  cannot be waited out because no schedule can be observed.
- Even with both, the demonstration would have proved nothing about **this**
  story. The live worker imports the landing branch's code, and US2 is not on
  it; a tick observed now runs the pre-US2 refresh. Worse, planting an unpushed
  `operator/scratch` in the shared clone is precisely the condition that stalls
  every tick at clone under pre-US1 code — the 6h34m outage this spec exists to
  prevent — and sibling epics may be in flight.

So what is pasted below is the same three outputs the plan asks for — branch,
status, reflog, before and after a tick — produced by driving **the real
activity** (`clone_target`, through the production `_clone_runner` seam, with an
assertion in the harness that the seam is still `_refresh_to_default`) against
**real clones with a real `origin`**. It is not a live schedule; it is the
activity a live schedule calls, on the code this diff adds. The live-schedule
run remains the operator's to perform after this lands, per the plan's
§ *Verification the operator will run*.

The reflog is the load-bearing line throughout, for the reason the plan gives:
after a reset, `git status` is clean in a way that is indistinguishable from a
tree nobody touched, so only the **absence** of a `reset: moving to` entry
separates "spared" from "destroyed".

## A. The plan's demonstration: uncommitted work, tick runs

```
--- before the tick ---
$ git rev-parse --abbrev-ref HEAD
operator/scratch
$ git status --porcelain
 M README.md
$ git reflog -5
9b41f39 HEAD@{0}: checkout: moving from ergane-buildout to operator/scratch
9b41f39 HEAD@{1}: reset: moving to HEAD~1
923994f HEAD@{2}: clone: from /tmp/t017/origin.git
--- the tick ---
branch the activity used: ergane-buildout (named by: manifest)
refusal: refusing to refresh /tmp/t017/clone-a: branch 'ergane-buildout' carries work that is not on origin/ergane-buildout, and `git reset --hard origin/ergane-buildout` would discard it.
  uncommitted changes to tracked files:
     M README.md
To clear this, push the work to origin/ergane-buildout, move it to a branch of your own (`git switch -c <branch>`), or discard it yourself (`git restore .` / `git reset --hard origin/ergane-buildout`). The roadmap refreshes on the next tick once the clone carries nothing of its own.
--- after the tick ---
$ git rev-parse --abbrev-ref HEAD
operator/scratch
$ git status --porcelain
 M README.md
$ git reflog -5
9b41f39 HEAD@{0}: checkout: moving from ergane-buildout to operator/scratch
9b41f39 HEAD@{1}: reset: moving to HEAD~1
923994f HEAD@{2}: clone: from /tmp/t017/origin.git
```

The reflog is byte-identical before and after: no `reset: moving to`, no
`checkout:`. Before this epic it read `checkout: moving from operator/scratch to
operator/scratch` followed by `reset: moving to origin/operator/scratch`, and
`README.md` was clean.

Note what the two halves of the epic each contributed here. US1 is why the
branch named on the "branch the activity used" line is `ergane-buildout` and not
`operator/scratch` — the manifest answered, so the operator's branch was never a
candidate for reset. US2 is why nothing happened *at all*: the working tree is
shared across branches, so a modified tracked file is at risk whichever branch
HEAD sits on, and FR-003 says "the clone carries an uncommitted change to a
tracked file" without qualifying it by branch.

## B. US2's own case: committed to be safe, and no safer

```
--- before the tick ---
$ git rev-parse --abbrev-ref HEAD
ergane-buildout
$ git status --porcelain
$ git reflog -5
450c48b HEAD@{0}: commit: operator's unpushed grooming write
9b41f39 HEAD@{1}: reset: moving to HEAD~1
923994f HEAD@{2}: clone: from /tmp/t017/origin.git
--- the tick ---
branch the activity used: ergane-buildout (named by: manifest)
refusal: refusing to refresh /tmp/t017/clone-b: branch 'ergane-buildout' carries work that is not on origin/ergane-buildout, and `git reset --hard origin/ergane-buildout` would discard it.
  commits not on origin/ergane-buildout:
    450c48b operator's unpushed grooming write
To clear this, push the work to origin/ergane-buildout, move it to a branch of your own (`git switch -c <branch>`), or discard it yourself (`git restore .` / `git reset --hard origin/ergane-buildout`). The roadmap refreshes on the next tick once the clone carries nothing of its own.
--- after the tick ---
$ git rev-parse --abbrev-ref HEAD
ergane-buildout
$ git status --porcelain
$ git reflog -5
450c48b HEAD@{0}: commit: operator's unpushed grooming write
9b41f39 HEAD@{1}: reset: moving to HEAD~1
923994f HEAD@{2}: clone: from /tmp/t017/origin.git
```

`git status --porcelain` prints **nothing**, before and after — that empty line
is the whole argument of plan trap 2. The operator committed the work to keep it
safe, and in doing so made it invisible to the obvious guard while leaving it
exactly as exposed: the reset target is `origin/ergane-buildout`, which does not
have this commit. A dirty-tree check alone passes this clone straight through to
the reset that destroys it. The refusal names the commit, so the operator can
find it.

## C. The control: the refusal is selective

```
--- before the tick ---
$ git rev-parse --abbrev-ref HEAD
ergane-buildout
$ git status --porcelain
$ git reflog -5
9b41f39 HEAD@{0}: reset: moving to HEAD~1
923994f HEAD@{1}: clone: from /tmp/t017/origin.git
$ git status --porcelain --ignored   # what the repo's own rules cover
!! .factory/
--- the tick ---
branch the activity used: ergane-buildout (named by: manifest)
refusal: <none — the refresh proceeded>
--- after the tick ---
$ git rev-parse --abbrev-ref HEAD
ergane-buildout
$ git status --porcelain
$ git reflog -5
923994f HEAD@{0}: reset: moving to origin/ergane-buildout
9b41f39 HEAD@{1}: checkout: moving from ergane-buildout to ergane-buildout
9b41f39 HEAD@{2}: reset: moving to HEAD~1
923994f HEAD@{3}: clone: from /tmp/t017/origin.git
```

This is the half that would be missing if the guard were merely timid. The clone
was one commit behind `origin/ergane-buildout` and carried `.factory/` — build
residue the repo's own `.gitignore` covers, which `git status --porcelain
--ignored` confirms as `!!` rather than `??`. The refresh proceeded: `checkout`
then `reset: moving to origin/ergane-buildout`, the identical sequence to
pre-US2, and `.factory/` is still on disk because a hard reset never had
anything to do with it. Had ignored files counted as work at risk, every clone
the factory has ever built in would park on every tick.

## A consequence the operator should know

A clone carrying **any** uncommitted change to a tracked file now parks every
dispatchable spec, each tick, until the operator pushes it, moves it, or
discards it. That is FR-003 read literally and it is the safe direction — the
factory declines rather than destroys — but it converts a silent data loss into
a visible stop, and the stop is only as good as the message. That is why the
refusal names the branch, the paths, the commits and the three acts that clear
it, and why it parks verbatim (FR-004).

## Gate

`uv run pytest -q` — the whole suite, in this worktree, at the commit under
review:

```
5199 passed, 58 skipped, 8 warnings in 364.23s (0:06:04)
```
