# Gating the landing branch

`ergane-buildout` is the branch every dispatched node pins its base to. A red one
does not just inconvenience an operator — it costs agent attempts, because a
node's gate runs the whole suite against a base it did not choose and cannot fix
without leaving its own scope.

Two pieces:

| | what it does | cost |
| --- | --- | --- |
| `scripts/gate-commit [sha]` | runs the declared gate against one commit in a scratch worktree, records the pass | ~6 min |
| `scripts/hooks/pre-push` | refuses a push to a guarded branch unless that exact sha was recorded | instant |

## Install

```bash
git config core.hooksPath scripts/hooks
```

Local to this clone, reversible with `git config --unset core.hooksPath`. It does
**not** affect the factory: node worktrees belong to the separate
`ergane-roadmap-target` clone, which has its own hooks path.

## Use

```bash
scripts/gate-commit          # gate HEAD, ~6 minutes
git push origin ergane-buildout
```

Amending or rebasing after gating produces a new sha, which has not been gated,
and the hook will refuse it. That is the point rather than an inconvenience.

## Why the gate is not inside the hook

The first version of this hook ran the suite inline. It was wrong, and the way it
failed is worth keeping.

Git opens the connection to the remote **before** it runs `pre-push`, and holds
it open while the hook works. The suite takes about six minutes; GitHub closes
the connection well short of that. The observed result was:

```
pre-push: gate PASSED on 528809dabdc8 — 3974 passed, 48 skipped in 364.36s
Connection to github.com closed by remote host.
```

The gate ran, the verdict was correct, and **nothing landed** — while the output
read like success. A slow `pre-push` hook does not gate a push; it loses it. So
the expensive half runs out of band and records what it proved, and the hook only
asks whether this sha was proved.

## Why a scratch worktree and not your checkout

On 2026-08-20 an operator pushed `c9dea78` to `ergane-buildout` having just run
the full suite and watched **3934 tests pass**. Trunk went red on four tests
anyway. The suite had run in a *different* worktree — the 068/us2 merge tree —
which did not contain the `personas.yaml` change that `c9dea78` carried. Two
dispatched Opus nodes then diagnosed and repaired the breakage inside their own
stories, and one of them burned an attempt on it.

Running the gate on a tree that shares most of its content with the one you are
pushing produces artifacts **indistinguishable** from having run it properly: the
same pass count, the same green summary, the same confidence. The only defence is
to test the commit itself, so `gate-commit` checks the sha out into a throwaway
worktree where nothing staged, unstaged, stashed or untracked can reach the
verdict.

The gate command is read out of `factory.yaml` rather than hardcoded, so it
cannot drift from what dispatched nodes are held to.

## Override

```bash
ERGANE_SKIP_PREPUSH_GATE=1 git push ...
```

It announces itself on stderr. Use it when you mean it, and say why in the PR.

## This is the second line of defence, not the first

The first is the `factory-queue` ruleset, which requires a pull request, the
`test` check and the merge queue. Those rules were advisory for an
`OrganizationAdmin` with `bypass_mode: always`, which is how the push above
succeeded while GitHub printed all three rules at it. Clearing that bypass is the
real fix:

```bash
gh api -X PUT repos/bryantharpeorg/ergane/rulesets/20538625 -f 'bypass_actors=[]'
```

This hook is what catches the mistake before the forge sees it, and what still
covers the case where a bypass is restored later.

## Controls

Verified in both directions rather than watched to pass — a gate that has never
been seen to fail proves nothing.

| control | setup | required | observed |
| --- | --- | --- | --- |
| `gate-commit` refuses red | commit with a collection error | fail, no record | exit 1, `not recorded` |
| `gate-commit` doesn't false-refuse | **working tree poisoned**, commit clean | pass | `3968 passed` on `eb23d98` |
| hook refuses ungated sha | never gated | fast exit 1 | exit 1 in **0s** |
| hook allows gated sha | after `gate-commit` | exit 0 | exit 0 |
| hook ignores other refs | push to `factory/999/us1` | exit 0 | exit 0 |
| hook ignores deletions | delete `ergane-buildout` | exit 0 | exit 0 |

Row two is the one that proves the verdict comes from the commit rather than the
checkout. Row three is the one that proves the hook cannot lose a push.
