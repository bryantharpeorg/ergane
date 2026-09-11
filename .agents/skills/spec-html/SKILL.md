---
name: spec-html
description: Render an Ergane spec trio (spec.md, plan.md, tasks.md) as one readable HTML page, with the Work Graph drawn as a DAG and the library validator's actual report. Rendering returns that local path; publication is a separate authorized action. Use when asked to make a spec readable, share a spec, review one visually, or check one validation verdict.
---

# Rendering a spec as HTML

A spec is hard to read because the parts that matter most are the parts prose is
worst at: a Work Graph as raw YAML, validator findings, and landing truth across
three files.

This renders the trio as one page and **resolves all three against the tree
first**. The reading improvement is a side effect; the point is that the page
states facts the markdown only claims.

## Run it

```bash
cd /home/admin/code/ergane
python3 .agents/skills/spec-html/render.py specs/<spec-dir> -o <caller-selected-local-path>
```

Options that change the answer, not the styling:

- `--tree <dir>` — the target repository the validator resolves against. **Defaults to the repo
  root, which is usually the wrong tree.** A node's worktree branches from the
  landing branch, not from your working copy, so a spec can read clean for you
  and land an agent in the middle of a docstring. To get the answer an agent
  would get, materialise the branch first:
  ```bash
  mkdir -p /tmp/origin && cd /tmp/origin
  git -C /home/admin/code/ergane archive origin/ergane-buildout | tar -x
  ```
  then `--tree /tmp/origin`.
- `--landed-branch ergane-buildout` — marks landed stories green in the DAG and
  fills the story table. Reads landing facts from the declared target without
  fetching. **Never pass `main`**; the factory does not land there.

The command prints the local output path. Without `-o`, it writes one unique
scratch path beside the trio.

## What the page shows that the markdown does not

- **Work Graph as a DAG.** Layered by dependency depth. **Solid edge = waits for
  merge (`depends_on_merged`); dashed = waits only for verification
  (`depends_on`).** That distinction is invisible in YAML and it is the one that
  costs reworks: a dashed edge releases a story while its dependency is still in
  the merge queue, so the dependent builds against a base without it.
- **The validator's verdict**, with every finding's layer, message, and severity;
  every skipped layer's reason; and the checked sequence. This is
  `factory.spec.validate_spec`, not a second implementation.
- **Coverage**, computed: FRs with no task, stories against the graph, tasks done.
- **Provenance**, collapsed. The frontmatter comment block is where a spec records
  why it is held, and it is usually the longest thing in the file — worth keeping,
  worth folding away.

## Publication is separate

Rendering never publishes. It returns that local path and touches no remote.
Publication is a separate authorized action, and only after an operator grants
that intent.

1. Confirm the publication is authorized and where it may go.
2. Publish the returned local file, never as part of the render call.

Publishing sends the spec's full text off the machine. Ergane specs are ordinary
engineering documents, but check the frontmatter before publishing one: hold
notes sometimes quote incident detail, and 064's records a live credential leak.

## Reading the output honestly

**A pass is not a clean spec by itself.** Read refusals, advisories, skipped
layers, and the validator's reasons. Information and skipped layers do not
change the verdict, but they still tell the reader what was not proven.

**Re-render after anything lands.** Validation and landing facts age when the
factory ships. A page rendered before a merge is evidence about a tree that no
longer exists; the footer records which tree it was resolved against.
