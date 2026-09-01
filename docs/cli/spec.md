# `ergane spec`

> work with specs: list, validate, derive, new, landed

Everything that happens to a spec before an epic exists. Five verbs, none of
which dispatch anything — `spec` compiles and inspects; `build` and `roadmap`
dispatch.

```
ergane spec list      [<specs-root>] [--json]
ergane spec validate  <spec-dir> [--target-repo PATH] [--specs-root DIR] [--json]
ergane spec derive    <spec-dir> --target-repo PATH [--specs-root DIR] [-o FILE] [--delta] [--json]
ergane spec new       <slug> --target-repo PATH [--specs-root DIR] [--title TEXT] [--fixes KEY]...
ergane spec landed    <spec-dir> [--default-branch BRANCH] [--json]
```

---

## `ergane spec list`

Every spec's state and what blocks each one.

| argument | default | meaning |
| --- | --- | --- |
| `<specs_root>` | `specs` | the specs root to scan |
| `--json` | | print the roadmap and readiness documents instead of the table |

The table is the answer to "what is in the corpus and what could move". For
what the floor is doing *right now*, including running epics, use
[`ergane status`](status.md) instead — it is a superset.

---

## `ergane spec validate`

Run every registered check over one spec directory, and refuse if any of them
refuses.

| argument | default | meaning |
| --- | --- | --- |
| `<spec_dir>` | — | the feature directory holding `spec.md` |
| `--target-repo` | `/srv/factory/targets/short-links` | worker-host path to the target repo |
| `--specs-root` | `specs` | where the worker finds feature specs |
| `--json` | | print a JSON report instead of the human summary |

**Mind the `--target-repo` default.** It is a path that does not exist on most
hosts. Layers that read the target repository skip themselves and say so rather
than refusing, but you are then validating with fewer layers than you think.
When the answer matters, pass it:

```bash
ergane spec validate specs/072-a-stale-anchor-fails-validate-not-the-attempt \
  --target-repo "$PWD"
```

### What the output means

The command speaks in three registers, and they are not interchangeable:

| register | prefix | reaches the exit code |
| --- | --- | --- |
| refusal | `ergane spec validate — refusal: [layer] …` | **yes**, exit 1 |
| advisory | `ergane spec validate — advisory: [layer] …` | no |
| noted, not a refusal | `ergane spec validate — noted, not a refusal: …` | no |
| layer not checked | `ergane spec validate — layer 'x' not checked: …` | no |

A spec that prints advisories and notes still exits 0. "Not checked" is the one
to read carefully — it means a layer had no input, not that it passed. A
document nobody opened has no findings, and treating that as a clean bill of
health is how a check comes to be trusted for something it never did.

A clean run ends with the all-pass sentence and, beneath it, a report of exactly
what the judge will be shown for each node: the diff, the criteria (each story's
own scenarios), and the declared gates.

---

## `ergane spec derive`

Compile a spec into a work graph — the artifact `build start` and the roadmap
dispatch from.

| argument | default | meaning |
| --- | --- | --- |
| `<spec_dir>` | — | the feature directory holding `spec.md` |
| `--target-repo` | **required** | worker-host path to the repository the epic builds in |
| `--specs-root` | `specs` | where the worker finds feature specs |
| `-o`, `--output` | `<spec-dir>/workgraph.json` | write the artifact here instead |
| `--delta` | | derive only the work that remains against the landed baseline |
| `--json` | | print the compiled graph as JSON instead of the artifact path |

`--delta` is what you want for a partially-landed spec: it reads the landing
baseline and emits only the stories still outstanding.

**Re-derive the delta at dispatch time, never reuse an older remainder file.**
The baseline moves every time something lands, and a stale remainder re-runs
stories that are already in git.

`--json` is also the fastest way to see the graph's shape without opening the
artifact — chain depth is what governs how long an epic takes, not story count:

```bash
ergane spec derive specs/<dir> --target-repo "$PWD" --json | jq '.graph.nodes[] | {id, depends_on_merged}'
```

---

## `ergane spec new`

Scaffold a numbered spec directory under the specs root.

| argument | default | meaning |
| --- | --- | --- |
| `<slug>` | — | the feature slug for the new spec |
| `--target-repo` | **required** | worker-host path to the repository the epic builds in |
| `--specs-root` | `specs` | where the new spec directory is created |
| `--title` | the slug | human-readable title for the worked story |
| `--fixes` | none | finding key the spec fixes; repeatable |

The number is assigned, not chosen. `--fixes` records the ledger keys this spec
is meant to close; `ergane spec validate` checks those declarations against the
findings store, and `ergane findings triage` reads them back.

The scaffold contains sentinels marking the blanks an author must fill.
`ergane spec derive` refuses while any remain, and `validate` reports them on
the "noted, not a refusal" channel with a count.

---

## `ergane spec landed`

Which of a spec's stories are in git, story by story, by ancestry and content
rather than by anyone's claim.

| argument | default | meaning |
| --- | --- | --- |
| `<spec_dir>` | — | the feature directory holding `spec.md` |
| `--default-branch` | read from the manifest, else `main` | branch to scan for landing attributions |
| `--json` | | print the landed facts as JSON instead of the human view |

**The trap that has cost the most time here:** the default branch is *not*
necessarily where the factory lands. When a repository's factory lands on a
buildout branch and `main` moves only on an operator promotion, the default
under-reports between promotions:

```bash
ergane spec landed specs/<dir> --default-branch ergane-buildout
```

Pass `--default-branch` whenever the answer matters. A merged pull request is a
claim; this command reads the branch, which is the fact.

## See also

- [`ergane build`](build.md) — `build ship` runs validate and derive for you and
  then pauses for confirmation before dispatching
- [`ergane status`](status.md) — the corpus plus everything running
- [`ergane roadmap`](roadmap.md) — dispatches ready specs without a `build start`
