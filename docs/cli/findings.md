# `ergane findings`

> manage the findings ledger

The ledger is the factory's memory of what has gone wrong. It is what makes
"this has happened before" a fact rather than a recollection, and it is the
evidence a constitutional rule is promoted on.

```
ergane findings list    [--db PATH] [--severity SEV] [--status STATUS] [--json]
ergane findings report  [--db PATH] --key KEY --category CAT --severity SEV --summary TEXT [--refs REF] [--notes TEXT] [--source SRC]
ergane findings report  [--db PATH] --batch FILE
ergane findings resolve [--db PATH] --key KEY --reason TEXT
ergane findings promote [--db PATH] --slug DIR --specs-root DIR --target-repo PATH [--keys KEY...]
ergane findings triage  [--db PATH] [--specs-root DIR] [--cold-days N] [--json] [--apply]
```

`--db` defaults to the resolved runtime root's `doctor.db` on every verb.

---

## `ergane findings list`

```
KEY                                           SEV      STATUS         # AGE
hardening/agent-worktree-boundary             critical open          88 1d
interpreter/replay-test-nondeterminism-under-load critical promoted   8 15d
ci/test-suite-pins-the-operator-dial          critical regressed      7 2d
```

| column | meaning |
| --- | --- |
| `KEY` | `category/slug` — the finding's stable identity |
| `SEV` | `critical`, `warning` or `info` |
| `STATUS` | `open`, `promoted`, `resolved` or `regressed` |
| `#` | occurrence count — how many times this has been seen |
| `AGE` | since it was last seen |

Filter with `--severity` and `--status`, and script against `--json`.

**Count by `status`, not by whether a resolution note exists.** A resolved
finding keeps its row. Treating every row as live overstates the ledger by a
large factor; treating "has a resolution" as resolved understates it, because
`regressed` rows carry one too.

**`regressed` is the status to read first.** It means something that was closed
came back, which is a stronger signal than a new `open` — the remedy was tried
and did not hold.

**A rising count during hard running is healthy.** Findings come from running
things, not from reading them. A flat ledger through a heavy week means nobody
was looking.

---

## `ergane findings report`

File a finding, or bump an existing key's occurrence count.

| flag | meaning |
| --- | --- |
| `--key` | `category/slug` identity — reuse the key to record a recurrence |
| `--category` | finding category |
| `--severity` | `critical`, `warning` or `info` |
| `--summary` | short description |
| `--refs` | `file:line` reference strings |
| `--notes` | extra evidence |
| `--source` | reporter source (default `operator`) |
| `--batch` | ingest findings from a JSON batch file, all-or-nothing |

**The key is the identity.** Reporting the same key again records a recurrence
rather than a second finding, and the occurrence count is what later makes a
promotion argument. Inventing a new slug for the same defect destroys the
evidence that it recurred.

**Put a reproduction in `--notes`, not a narration.** A finding with a
reproduction in it is worth a spec later. A finding that describes a feeling is
worth nothing.

---

## `ergane findings resolve --key KEY --reason TEXT`

Close a finding. Both flags are required — a resolution with no reason is
unreviewable, and the reason is what a later regression is read against.

---

## `ergane findings promote`

Turn findings into a spec directory.

| flag | meaning |
| --- | --- |
| `--slug` | **required** — target spec directory name |
| `--specs-root` | **required** — parent directory where the spec directory will be created |
| `--target-repo` | **required** — target repo path recorded in the compiled workgraph |
| `--keys` | finding keys to promote |

This is the ledger's exit into work. The spec that results still needs
refinement before it is fit to dispatch — promotion produces a starting point,
not a brief.

---

## `ergane findings triage`

Classify the ledger: what a landed spec declared fixed, which fragmented classes
should fold together, and what has gone cold.

| flag | default | meaning |
| --- | --- | --- |
| `--specs-root` | `specs` | the corpus to read state and `fixes:` declarations from |
| `--cold-days` | `14` | a finding seen once and untouched for longer is cold |
| `--json` | | emit JSON |
| `--apply` | | **enact** the classification |

Without `--apply` it reports. With `--apply` it closes what a landed spec
declared fixed, folds the fragmented classes, and annotates the rest.

**`--apply` writes.** Run it without the flag first and read what it proposes.
Note also that a spec *naming* a finding in its `fixes:` is a declaration, not
proof the defect is gone — triage takes the declaration at face value, so a
sweep can close findings whose mechanism is still live.

## See also

- [`ergane doctor`](doctor.md) — runs the registered probes and files what they find
- [`ergane spec new --fixes`](spec.md) — declares which findings a spec closes
