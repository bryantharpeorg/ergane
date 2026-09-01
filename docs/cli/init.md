# `ergane init`

> join a git repository to Ergane

Interview the operator and write the Ergane declarations into the repository:
`ergane.yaml`, a `.gitignore` entry, and `.ergane/`.

```
ergane init [<path>] [--check] [--wire] [--non-interactive]
```

| argument | default | meaning |
| --- | --- | --- |
| `<path>` | `.` | path inside the repository to initialise |
| `--check` | | judge this repository's readiness and exit; **writes nothing** |
| `--wire` | | also wire the repository's GitHub side to match the declarations |
| `--non-interactive` | | use documented defaults for every question; fields with no safe default cause a refusal |

## It commits nothing

`init` writes files into your working tree and stops. Reviewing and committing
them is your git work — which is the point, because `ergane.yaml` is the
repository's committed statement of how it is built, and a tool that committed
it on your behalf would be writing that statement for you.

## `--check` first

Read-only. It judges readiness and exits, which is the cheapest way to find out
what a repository is missing before anything is written.

## `--wire`

Wires the GitHub side to match what the declarations say:

- enables the merge queue on the declared landing branch
- requires one check per declared gate
- scaffolds the workflow that produces those checks

The merge queue is not a preference here. The gate that decides whether work
lands is the **merge-group build**, which tests the speculative merge; a pull
request's own green check tests the branch, and those are different trees. A
repository without a merge queue has no such gate.

## `--non-interactive`

Answers every question with its documented default. A field with no safe default
is a **refusal**, not a guess — which makes this usable in a script without it
quietly inventing a landing branch.

## After it

The repository is not yet registered until its manifest is committed;
[`ergane repo list`](repo.md) reports the manifest's status, and
[`ergane repo rebuild`](repo.md) adopts it.

## See also

- [`ergane repo onboard`](repo.md) — judge a repository before joining it
- [`ergane install`](install.md) — the control plane, which is a host concern rather than a repository one
- [`ergane repo forget`](repo.md) — the reverse
