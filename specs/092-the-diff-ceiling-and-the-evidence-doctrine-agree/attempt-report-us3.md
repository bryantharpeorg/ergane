# Attempt report — 092 / US3: an abridged verdict is auditable

T023 and T024, run by hand on 2026-08-30 against this worktree.

## T023 — FR-008 confirmed: the abridgement algorithm is untouched, and no path is exempt

The algorithm FR-008 names is unchanged by this story and by this epic. The
whole of what US3 changed about the module that owns it is nothing: `git diff`
against the epic's base reports no hunk in it, and the epic's two landed stories
report none either.

```
$ git diff --stat 19b4eb4..HEAD -- factory/verify/judge.py   # the whole epic, so far
(no output: not one line of it changed)

$ git status --porcelain factory/verify/judge.py             # nothing uncommitted here either
(no output)
```

The abridger's tests still pass unchanged, which is the other half of the claim:
`test_the_judges_own_truncation_survives_behind_the_new_check` (045 US2-S4) and
`test_a_diff_between_the_two_limits_reaches_the_judge_abridged` (092 US1-S2) both
assert its output, and this story edited neither.

No path is exempted by name or by pattern anywhere in this epic (plan trap 1).
The measurement this story added weighs the same assembly the refusal weighs —
the always-complete file listing, the preamble and every file's section — and
weighs all of it: there is no allow-list, no suffix test, no lockfile clause and
no filename in any of the three stories' code.

```
$ git grep -nEi "exempt|allow-?list|ignore-?list|lockfile|package-lock|yarn\.lock|uv\.lock|node_modules|generated" \
    -- factory/verify/diffbounds.py factory/verify/diffcheck.py factory/verify/judge.py
factory/verify/diffcheck.py:50:not, which is what keeps generated noise from manufacturing the diff FR-004
factory/verify/diffcheck.py:530:    The environment is the gate runner's allowlist (constitution V) — a
```

Two hits, both prose and neither an exemption: line 50 describes git's own
treatment of ignored files in the diff it produces, and line 530 is the
subprocess environment allowlist that keeps factory credentials out of a `git`
child. The one filename-shaped mechanism in the neighbourhood is the hygiene
check's runtime-root prefixes, which predates this epic (045 FR-001), decides a
refusal rather than a size, and is untouched here.

## T024 — the operator's demonstration

### Part 1: today's behaviour is preserved at the default

Verbatim from the plan's § *Verification the operator will run*.

<!-- T024-PART1 -->

### Part 2: a node whose diff exceeds the old constant reaches a verdict, and the record says it was abridged

**What could not be run from here, stated plainly.** The plan's second half asks
for one *real dispatched node* — `ergane build status <epic-id>` over an epic
whose implementer produced an oversize diff. That needs a Temporal server, a
worker, a proxy key and an epic dispatched by the operator; a node running inside
its own worktree can start none of them, and starting one would be an action well
outside this story. So the fact the gate cannot show is shown here the only other
honest way: the same code path, on a real git worktree with a real oversize diff,
driven through the real output check, the real evidence store and the real CLI.
It is weaker than a dispatched build in exactly one respect — no judge model was
called — and the operator's own run is still owed.

<!-- T024-PART2 -->

The three claims the demonstration makes:

1. **The node is buildable at all.** Before this epic the same diff had one
   possible outcome and it was FAIL: gates green, judge never reached, every
   ladder rung identical. It now passes the output check and would be judged.
2. **The judge is shown as much as it may be, and no more.** `prepare_diff`
   abridged it, to the attention budget, exactly as it did before — nothing in
   this story reached that function.
3. **The verdict says so.** The row records that the input was abridged and by
   how much, and the CLI prints it beside the PASS, so an operator can tell that
   PASS from one taken on a diff the judge read whole.

### The gate

<!-- GATE -->
