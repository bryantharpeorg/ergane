---
name: "findings-ingest"
description: "Absorb a large external corpus of reported issues — a consumer's hand-over document, an audit, a review — into the doctor's ledger as stable identity-keyed findings, then classify them with `ergane findings triage`. Covers minting keys, the severity collapse, the defect-versus-want lane, the mandatory scratch-store rehearsal, and the `fixes:` back-fill that lets triage close anything. Use when a document arrives with more findings than you would file by hand."
compatibility: "Requires the ergane CLI via scripts/ergane-env.sh and a checkout of this repository"
metadata:
  author: "operator session, 2026-08-28"
  status: "revised 2026-08-28 after the first sweep: §2 (dedup) added, §8 back-fill still unproven"
user-invocable: true
disable-model-invocation: false
---

# Findings ingest

A consumer hands you sixty findings in prose. The ledger is the right home
for them and `triage` is the right classifier, but nothing connects the two:
turning a document into stable keys is manual, and so is the declaration
that lets triage close anything. This skill is those two manual halves,
plus the rehearsal that keeps a bad batch out of a live ledger.

```
   ingest          →  triage           →  back-fill `fixes:`
   (this skill §1-6)  (deterministic,      (this skill §8)
                       spec 073)              │
                       ▲                      │
                       └──────────────────────┘
```

> **The classifier is not the analysis.** `triage` closes a finding only
> when a **landed** spec declares its key under `fixes:`. Freshly minted
> keys are declared by nothing, so a first triage after ingest returns
> every new row as `needs-human`. That is correct behaviour, not a
> failure — but it means ingesting does not answer "what have we already
> fixed", and you should say so rather than present the classification as
> if it did.

## 1. Read the whole document first

Extract every entry before keying any of them. Two things you are looking
for that a partial read will not give you:

- **Which entries the reporter says are not defects.** Good hand-over
  documents mark them — "not an ergane defect", "a capability gap, not a
  defect", "what worked, filed here because the shape is worth keeping".
  Those go in the feedback lane (§4), not the defect count.
- **Cross-references.** Entries routinely say "this is the defect half of
  PR-1" or "superseded in scope by PR-10". Carry those into `notes`; they
  are what makes the corpus promotable later as coherent specs rather
  than as sixty unrelated rows.

If the source is HTML, strip it with a depth-tracking parser, not a
non-greedy regex — finding blocks nest `<div>`s, and `<article>.*?</\1>`
silently truncates every body at the first inner close tag. That failure
is quiet: you get correct titles and empty evidence.

## 2. Search the ledger before you mint anything

**This is the step that was skipped on 2026-08-28, and it cost the most.**

A consumer's document describes mechanisms the ledger very likely already
tracks under its own keys, written in different words. If you mint a new
key for a mechanism that already has one, you do not add a finding — you
**split an identity**, and the damage is specific: `report()` on the
existing key would have incremented `occurrences` and advanced
`last_seen`, which is the recurrence signal that drives promotion into the
constitution. A parallel row starts at `occurrences: 1` and says the
mechanism was seen once. The second sighting of a known defect is the most
valuable row in the ledger, and minting a new key throws it away.

`triage` will not catch this. Its `fragmented` rule (FR-009) needs keys of
three or more segments sharing their first two; two-segment keys in
different categories look unrelated to it.

So, before keying anything, dump the existing corpus and match by
**mechanism, not by wording**:

```bash
uv run ergane findings list --json \
  | jq -r '.[] | select(.status=="open" or .status=="regressed") | .key'
```

Read that list against the document. The 2026-08-28 corpus produced at
least ten collisions whose vocabulary shared almost nothing:

| Document said | Ledger already had |
| --- | --- |
| a worker restart orphans the running attempt | `hardening/a-worker-restart-orphans-the-in-flight-agent-activity-for-the-full-heartbeat-timeout` |
| the roadmap hard-resets the operator's checkout | `roadmap/dispatch-is-decided-by-the-operators-working-tree` |
| a killed dispatch leaves a blocking remote branch | `landing/kill-and-redispatch-leaves-a-stale-remote-node-branch-that-kills-the-next-landing` |
| an expired subscription session burns the ladder | `agent/an-expired-subscription-oauth-session-burns-every-attempt-and-reports-it-as-an-empty-diff` |
| the PR is based on the operator's checkout | `mergequeue/landing-base-follows-the-operator-checkout` |

A token-overlap heuristic helps but **under-reports** — it missed the
first two above, which are the two highest-severity collisions in that
set. Use it to narrow, then read.

**When a mechanism already has a key, re-report that key** with the new
evidence in `notes` and the source's number as a back-reference. That is
the recurrence signal, and it is the whole point of an identity-keyed
ledger. Mint a new key only for a mechanism genuinely absent from the
corpus.

> **But first: check whether the mechanism was fixed after the document was
> written.** `report()` stamps `last_seen` with *now*, not with when the
> reporter saw it. A hand-over describing a defect against an older release
> is a **historical** sighting, and re-reporting it dates it today — which
> is precisely how `triage` decides `seen-after-fix` (FR-006), the class
> that means "we shipped a fix and it came back". Re-reporting a stale
> sighting onto a key some landed spec already closed manufactures a
> regression that never happened, in the one class the module exists to
> protect.
>
> This happened on 2026-08-28. The round-2 document reported a landing-base
> defect against `ergane-cli 0.2.0`; spec 107 fixed it and declared it on
> 2026-08-25; the merge re-reported it anyway and triage duly announced it
> had been "seen again on 2026-08-29". One row of seven — the other six
> were genuinely still open, so the date was harmless there.
>
> So, before re-reporting: verify the mechanism against the **current
> tree**. Still present → re-report, and the recurrence is real. Already
> fixed → `resolve` the key naming the spec that fixed it, and put the
> document's sighting in the resolution reason. Never re-report a sighting
> you cannot date to after the fix.

## 3. Mint keys that will still match in six months

The key is the identity. It is what `triage` matches, what a spec's
`fixes:` names, and what the recurrence machine counts — so it must
survive the document it came from.

```
<category>/<a-sentence-describing-the-mechanism>
```

- **Reuse an existing category.** Check first; the taxonomy is open and
  nothing validates it, so a typo silently forks a class:
  `uv run ergane findings list --json | jq -r '.[].key' | cut -d/ -f1 | sort -u`
- **Never key on the source's own numbering.** `N30` means nothing to a
  spec author a month from now. Put the source's number as the first
  token of `notes` (`[N30] ...`) so the document stays addressable.
- **Describe the mechanism, not the symptom.** House style is a readable
  sentence: `mergequeue/a-killed-dispatch-leaves-a-remote-branch-that-permanently-blocks-the-next-dispatch-from-landing`.
- **Keep keys at two segments** (`category/slug`) unless you mean to form
  a class. Triage's `fragmented` rule (FR-009) groups keys of **three or
  more** segments sharing their first two *and* one source — three-segment
  keys will cluster whether or not you intended a class.

## 4. Two lanes: a defect and a want are not the same row

`category` is an open taxonomy documented as such at
`factory/doctor/store.py:52`, so a `feedback/` prefix costs nothing to
adopt today. Use it for anything that is **not yet a defect** — a missing
capability, a methodology note, a "keep this shape" record.

| The entry is… | Lane | Severity |
| --- | --- | --- |
| Something ergane does wrong, with a mechanism and evidence | `<category>/…` | mapped (§5) |
| A capability ergane does not have | `feedback/…` | `info` |
| A methodology or doctrine note that binds no implementer | `feedback/…` | `info` |
| The reporter's own "this worked, keep it" | `feedback/…` | `info` |

**File the feedback lane at `info` regardless of the reporter's severity**,
and say so in the note. A want filed at `critical` inflates the open-defect
count the operator reads as a health signal, which is the whole argument
of spec 115. Preserve the reporter's own severity verbatim in `notes` so
nothing is lost by the demotion.

## 5. The severity collapse is lossy — record what you dropped

`severity` is pinned by a `CHECK` at `factory/doctor/store.py:53-54` to
three values. Most reporters use five. The map that has been used:

| Reporter | Store |
| --- | --- |
| critical, high | `critical` |
| medium | `warning` |
| low, note | `info` |

Put `reporter severity: <original>` in every note. The collapse is a
storage constraint, not a re-judgement, and a later reader needs to be
able to tell the two apart.

## 6. Rehearse against a scratch store — this step is not optional

```bash
eval "$(scripts/ergane-env.sh)"          # NOT `source` — it emits export lines
uv run ergane findings report --db /tmp/rehearse.db --batch batch.json
uv run ergane findings list  --db /tmp/rehearse.db --json | jq length
```

Check the rehearsal store, not just the exit code: row count, the severity
distribution, and that every `feedback/` row really is `info`. A generator
bug that files a want at `critical` passes ingestion silently and is
tedious to unwind afterwards.

> **`--batch` is all-or-nothing on the *grammar* only.** The help text and
> spec 015 FR-004 both say all-or-nothing, and `parse_findings_batch`
> genuinely delivers that for the JSON grammar — every violation collected
> before anything is written. **The credential sweep is not covered by it.**
> `_contains_secret` runs *inside* the write loop at
> `factory/cli/doctor.py:458-466`, and `report()` commits per call
> (`factory/doctor/store.py:149`). Entry N tripping the sweep leaves
> entries 1..N-1 **committed** while the verb exits 1 saying "batch
> refused". Filed as
> `doctor/the-credential-sweep-runs-inside-the-batch-write-loop-so-a-refused-batch-is-partially-written`.

That is why the rehearsal is mandatory, and why **you may not simply
re-run a refused batch against the real store.** `report()` is a
recurrence machine: a re-report increments `occurrences` and advances
`last_seen`, and `last_seen` is the exact field triage uses to separate
`fixed` from `seen-after-fix`. Re-running a partially-written batch
corrupts the evidence triage depends on.

**The sweep's regex is `sk-[A-Za-z0-9_\-]{8,}`, unanchored on the left.**
Ordinary hyphenated English words whose interior contains that
three-character sequence followed by eight word characters will trip it,
with no credential present anywhere. The refusal names the key but no
span and no offset, so isolating it means bisecting your own file. Two
consequences for this skill: rehearse, and when writing a note *about*
the sweep, do not quote the trigger verbatim — this skill's own finding
was refused on its first filing for exactly that.

### The batch envelope

```jsonc
{
  "source": "<who-reported-it>-<yyyy-mm-dd>",   // required, applies to every entry
  "findings": [
    {
      "key": "category/mechanism-sentence",
      "category": "category",
      "severity": "critical | warning | info",
      "summary": "one sentence stating the defect",
      "refs": ["factory/path.py:123"],          // required, may be []
      "notes": "[N30] reporter severity: critical. ...evidence..."
    }
  ]
}
```

Entries may **not** carry their own `source` or `status` — the file is one
provenance and the store owns the status machine. Duplicate keys within one
file are refused naming the key. Use one file per source; if a document
carries both defects and platform requirements, that is two sources and
two files, so `findings list --json` can separate them later.

Then ingest for real:

```bash
uv run ergane findings report --batch batch-defects.json
uv run ergane findings report --batch batch-platform.json
```

## 7. Triage, read-only first

```bash
uv run ergane findings triage --specs-root specs --json > triage.json
```

Without `--apply` this is genuinely read-only — it opens `connect_readonly`
and skips the promoted-finding sweep, which is FR-013. Read the
classification before you enact it.

The seven classes, in the precedence order that makes "exactly one class"
well-defined (`factory/doctor/triage.py:10-60` argues each):

| Class | Means |
| --- | --- |
| `fixed` | a landed spec declares the key under `fixes:`, and `last_seen` is at or before the commit that first introduced that attestation |
| `seen-after-fix` | same declaration, **later** sighting — the top of the queue, and most of why the module exists |
| `needs-human, undated` | a declaration whose landing commit cannot be dated; an undated claim is not a proof |
| `fragmented` | ≥2 keys of ≥3 segments sharing their first two segments and one source |
| `candidate` | no `fixes:` declares it, but a landed spec's **prose** names it — reported separately, because naming is not fixing |
| `cold` | older than `--cold-days` and seen exactly once |
| `needs-human` | everything else |

`--apply` closes what a landed spec declared fixed, folds fragmented
classes, and annotates the rest. It may **not** act on `candidate`.

**Do not hand-filter before ingesting.** It is tempting to drop entries you
believe a recent spec already fixed. Don't: triage distinguishes `fixed`
from `seen-after-fix` by comparing `last_seen` against the attestation's
landing commit, and it can only make that call if the new sighting is in
the store with its date. Dropping a finding because it looks already-fixed
destroys the exact evidence that would have proven it wasn't.

## 8. Back-fill `fixes:` — the step that makes triage useful

*Provisional. This section records the intended shape; it has not yet been
run end to end. Revise it once the first sweep closes.*

Triage closes nothing until a landed spec **declares** a key. Prose is not
a declaration (`factory/doctor/triage.py:543`) — on the corpus spec 073 was
written against, one key was named by six specs, one of them to say the
finding had **regressed**. Any rule that read prose as a declaration would
have closed a live regression.

So the completion answer is produced by verifying each candidate against
the tree and writing the confirmed ones into the relevant landed spec's
frontmatter:

```yaml
---
state: landed
fixes:
  - category/the-key-this-spec-actually-closed
---
```

Verify against the current tree before declaring — read the code, don't
trust the spec's own prose about what it did. Then re-run `triage`; the
back-filled keys move from `needs-human` to `fixed`, and `--apply` can
close them.

## Hard rules

- **Rehearse against `--db /tmp/…` before every real ingest.** The
  credential sweep can partially write a batch the verb calls refused.
- **Never re-run a partially-written batch against the real store** — it
  double-counts `occurrences` and advances `last_seen`, corrupting the
  field triage classifies on.
- **Never hand-filter the corpus before ingesting.** Let triage decide.
- **A want is filed at `info` in the `feedback/` lane**, whatever the
  reporter called it.
- **Keys are minted once and never renamed.** A renamed key is a new
  identity: it loses the recurrence count and orphans every `fixes:` that
  named it.
- **Read-only triage before `--apply`, always.** Report what the pass saw
  before enacting it, so the two can be read against each other.
- **Ingesting is not analysing.** Report the classification honestly —
  including "all new rows returned `needs-human`, which is expected" —
  rather than presenting a fresh ingest as a completion answer.
