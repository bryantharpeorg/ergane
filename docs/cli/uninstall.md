# `ergane uninstall`

> take Ergane off this host, in the order that is safe

```
ergane uninstall [--check] [--purge] [--scrub-refs]
```

| flag | meaning |
| --- | --- |
| `--check` | print the plan a real run would follow and exit; **writes, removes, stops and signals nothing** |
| `--purge` | also empty Ergane's state home, lock-file siblings included, and whatever else the engine container's project directory holds |
| `--scrub-refs` | also remove the `factory/<epic>/<node>` branches and the refs under `refs/salvage/` that teardown otherwise only counts and names |

## The order is the feature

Teardown runs in a declared order, naming each step as it completes:

1. pause dispatch
2. forget repositories
3. stop the engine container
4. stop and remove units
5. clear state
6. account for the git refs

**A step with nothing to do says so.** **A step that refuses stops the verb
before the next one acts.** That second property is why the order matters: a
refusal at step 3 means steps 4 through 6 have not run, so the host is in a
known state rather than a partial one.

## Run `--check` first

It prints exactly the plan a real run would follow, and touches nothing. There
is no reason not to.

## What is kept unless you ask

**The control-plane config and the secrets beside it are kept either way** —
`--purge` does not remove them. Uninstalling Ergane is not the same as
discarding your gateway credentials, and conflating the two would make
reinstalling an interview instead of a no-op.

**Repository files are kept.** `ergane.yaml`, the `.gitignore` line and
`.ergane/` are committed content in someone's repository; removing them is git
work, done deliberately. See [`ergane repo forget`](repo.md).

**Git refs are counted and named, not removed**, unless `--scrub-refs`. Node
branches and `refs/salvage/` refs are where unlanded work survives an epic that
did not finish, and the default is to tell you they exist rather than to delete
them. Read the count before passing the flag; [`ergane build salvage`](build.md)
is how to see what is on them.

## Export before you forget

If any repository's engine-side history matters — findings, usage, escalations —
export it first. Those records are engine-side, not repository-side, and
teardown discards them:

```bash
ergane repo forget <slug> --export /path/outside/the/runtime/root
```

## See also

- [`ergane repo forget`](repo.md) — one repository, with an export path
- [`ergane worker uninstall`](worker.md) — the units alone
- [`ergane install`](install.md) — the reverse
