# Implementation Plan: a verified tree is the tree that will merge

**Spec**: `specs/118-a-verified-tree-is-the-tree-that-will-merge/spec.md`

A currency test beside the existing validity test, the base carried onto the
record, and the standards document resolved per attempt from the landing branch.

## What already exists, and where

Read `factory/workgraph/worktree.py:1-20` first. It states the three load-bearing
decisions of the module, including the one this spec must not break: a worktree
is "created once, reused across attempts", and "rebuilding or rebasing between
attempts would move the goalposts mid-node, which is the failure 002's criteria
snapshot exists to prevent (R5)".

- **`prepare_worktree`** (`:325`). Its docstring (`:326-343`) is the contract:
  idempotent by construction, "an existing directory is returned as-is,
  untouched — no fetch, no rebase, no reset". Then the pin rule: "A recorded pin
  is reused only when it is still an ancestor of the target's current
  landing-branch head (US1 FR-001); otherwise the worktree is rebuilt and the old
  branch is archived, never deleted (FR-004)."
- **The validity test itself**: `if _is_ancestor(repo, recorded.base_ref):` at
  `:365`, returning the recorded worktree; the diverged arm at `:367-369` calls
  `_archive_node` and clears the record. **US1's currency test goes between those
  two**, and its failure arm is the same `_archive_node` call — the rebuild path
  already exists and is already correct.
- **The adopt arm** (`:371-380`): a worktree from an older run whose record was
  swept is adopted rather than rebuilt, "pinning to where it stands", because
  "rebuilding would discard exactly the in-progress work the reuse rule
  protects". US1 must decide explicitly whether an adopted worktree gets a
  currency test; the safe reading is no — there is no recorded pin to judge, and
  discarding in-progress work is the failure that arm exists to avoid.
- **The explicit-pin authority** (`:387-393`): "Only recorded pins are
  ancestry-checked; an explicit caller instruction remains the caller's
  authority. (spec Edge Cases)". FR-005 preserves this.
- **The ownership refusal** (`:357-360`), ahead of both reuse branches, added by
  107 FR-002. Untouched by this epic.
- **The standards path in the prompt**: `factory/workgraph/prompt.py:224` —
  "Read `{standards}` in this worktree before you write code, and obey it" — and
  the assembly at `:389-432`, whose docstring (`:396`) is explicit that the
  function is "Pure: the four texts, the optional standards *path* (not the
  document…)". That purity is why US3's resolution happens in the caller, not
  here.

## Traps

**Trap 1 — an ancestor is not a current base, and this is the whole spec.** The
existing check reads `_is_ancestor(repo, recorded.base_ref)` and a base three
landings behind passes it, because being behind is exactly what being an ancestor
means. An implementer who reads the docstring's "still an ancestor of the
target's current landing-branch head" as already covering staleness will
correctly conclude there is no defect and land nothing. The new test measures
*distance*, not membership.

**Trap 2 — the tolerance must be a number, not a boolean.** "Any commit behind"
would rebuild almost every worktree, because the landing branch moves constantly
under a live roadmap, and rebuilding discards in-progress work. Make it a
configured tolerance with a sane default, and express it in a unit that means
something — commits behind, or "has the landing branch touched a path this node's
tree contains" if that proves cheap. Do not express it in wall-clock time.

**Trap 3 — never run the currency test between attempts.** FR-004 and US1-S4.
`prepare_worktree` is called both to create and to hand back, and the
distinction matters more here than anywhere else in the module. If a retry can
trigger a rebuild, this spec has caused the exact failure R5 exists to prevent,
and it will present as a debugger persona losing its context mid-node.

**Trap 4 — the adopt arm has no pin to judge.** Decide it explicitly and say so
in the code, because a future reader will ask. The recommendation is to leave it
alone: it fires when the sidecar is gone, its comment says wrong is impossible
there, and adding a currency test to it means discarding work on the strength of
a pin nobody recorded.

**Trap 5 — US2's base must come from the prepared worktree, not be re-derived.**
`PreparedWorktree` already carries `base_ref`. Reading git a second time at
record-writing time gives an answer that can differ from the one the attempt
actually ran against, which is the class of defect this whole spec is about.

**Trap 6 — US3 must not break the prompt builder's purity.** The builder takes a
standards *path* and stays pure by design. Resolve the document's text in the
caller that already reads the repository, pass what the builder expects, and keep
the builder unaware. An implementer who makes the prompt module read git has
traded a documented property for a shortcut.

**Trap 7 — a standards fetch may not fail a node.** FR-008's fallback is not
politeness: the landing branch may be unreachable, the path may not exist yet,
and a node that refuses to start because a document could not be fetched turns a
transient network condition into a dead epic. Fall back to the pinned copy,
report it, and continue.

**Trap 8 — reporting the source is what makes US3 auditable.** The archived
prompt is the record of what an attempt was actually told. If it does not say
whether the standards came from the landing branch or the pinned tree, the next
person debugging a stale-guidance failure is exactly where this spec's author
was.

## Sizing

US1 is small in lines and carries four of the eight traps — the tolerance
decision and the between-attempts boundary are where it goes wrong. US2 is a
field, a rendering and a migration-shaped unknown for old rows. US3 is a
resolution in the caller plus a fallback.

If an attempt is editing the criteria snapshot, or making `prepare_worktree`
rebuild on a retry, it has gone outside the spec.

## Verification the operator will run, independent of the gate

The gate proves the tolerance is applied. Only a live floor proves the stale-base
PASS is gone, because it needs a landing branch that moves under a running node:

```bash
eval "$(scripts/ergane-env.sh)"
# 1. dispatch a multi-story spec so one node sits while siblings land
uv run ergane build start <spec-dir> --target-repo .
# 2. while it runs, watch a node's base against the landing branch head
uv run ergane build status <epic-id>          # expect base + landing head on one line
# 3. after a sibling lands, confirm the waiting node's next dispatch rebuilt
git -C .factory/worktrees/<epic>/<node> merge-base --is-ancestor HEAD origin/<landing>; echo $?
```

The demonstration succeeds when the status line shows both SHAs and a node whose
base fell outside the tolerance was rebuilt rather than verified. Paste the status
line into the attestation — it is the one-line diagnosis the finding says would
have made this visible in seconds.
