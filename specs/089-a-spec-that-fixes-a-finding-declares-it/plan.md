# Implementation Plan: a spec that fixes a finding declares it

**Spec**: `specs/089-a-spec-that-fixes-a-finding-declares-it/spec.md`

Three stories, three modules, no shared file. US1 changes the doctor's
scaffolder, US2 the `spec new` verb, US3 the `spec validate` composition. The
frontmatter grammar is not touched by any of them.

## What already exists, and where

Read these before writing anything. Every anchor below was read from the tree at
`8bb2d4b`, not recalled.

- **`fixes` is already a legal frontmatter key.** `_KNOWN_KEYS` at
  `factory/roadmap/models.py:117` is `("state", "depends_on_landed", "fixes")`,
  added by 073-US1. The comment above it (`:114-116`) explains why the set is
  closed and says the refusal quotes the tuple back at an author who typed
  anything else. **No story here widens it** (FR-007).
- **The parser that reads it** is `_declaration`
  (`factory/doctor/triage.py:282-304`): one `yaml.safe_load` of one frontmatter
  block returning `(state, fixes)`, with a non-list `fixes` rejected naming the
  spec. US1's output must satisfy this parser, and US1-S2 proves it does.
- **The classifier that consumes it** is `classify`
  (`factory/doctor/triage.py`), whose `fixed` class (FR-005 of 073) requires a
  `state: landed` spec to declare the key. Its prose class (`:543`) is the
  refusal this spec exists to stop hitting.
- **`scaffold_spec`** (`factory/doctor/scaffold.py:27`) has **two variants and
  two separate frontmatter writers** — see trap 1.
- **`findings_promote_command`** (`factory/cli/doctor.py:514`) resolves each
  `--keys` value through `get_finding`, refuses unknown / already-promoted /
  already-resolved keys before generating anything, sanitises each finding, and
  calls `scaffold_spec(slug=…, findings=…, specs_root=…, target_repo=…)` at
  `:551`. By the time the scaffolder runs, **every key is known to exist** — so
  US1 needs no validation of its own.
- **`ergane spec` verbs** are `list, validate, derive, new, landed`. `spec new`
  scaffolds a trio, picks the next number, derives the graph to validate before
  committing, and writes atomically through a temp directory.
- **The "not checked" idiom** validate already uses for a layer it could not
  run: `ergane spec validate — layer '<name>' not checked: <reason>`. US3's
  absent-store path emits this, not a refusal (FR-006).
- **A read-only store opener that does not create the store** exists and its
  docstring gives exactly US3's reason: `open_store_readonly`
  (`factory/cli/status.py`) — "the existence check is what stops a report from
  creating the store (and its parent directory) as a side effect of asking about
  it". US3 needs the same property; reuse the idiom rather than calling
  `connect()`.

## Traps

**Trap 1 — there are two frontmatter writers, and only one of them is yours.**
`scaffold_spec` dispatches on whether `findings` was passed. The **findings**
variant is `_build_spec_md` (`factory/doctor/scaffold.py:316`), writing its
frontmatter at `:320-325`. The **slot** variant is `_build_spec_md_from_slots`
(`:152`), writing its frontmatter at `:156-158`. US1 changes `_build_spec_md`
only. The slot variant has no findings and must keep writing `state: draft`
alone; changing it would put an empty `fixes:` into every spec scaffolded from a
title and an anchor.

**Trap 2 — do not teach the reader to read prose.** The obvious cheaper fix is
to let `triage` treat a prose mention as a declaration. It is wrong, and the
measurement is in `triage.py`'s own docstring: on the corpus 073 was written
against, one key was named by six landed specs — two as their fix, one in an
out-of-scope list, one as background, and one in a note saying the finding had
**regressed**. A prose-reading rule closes a live regression. Any attempt that
edits `factory/doctor/triage.py` has misread this spec (FR-007).

**Trap 3 — the frontmatter is built as literal lines, not dumped.**
`_build_spec_md` appends `"---"`, `"state: draft"`, `"---"` as strings. Emit
`fixes:` the same way — a `yaml.safe_dump` of the whole block would reformat and
reorder what the other writer emits by hand, and the two variants' output would
stop matching. A finding key is `category/slug` and needs no quoting today; do
not add quoting logic for a case the store's own identity grammar cannot
produce.

**Trap 4 — the shape check already exists; do not add a second one.** `fixes`
is already validated exactly as `depends_on_landed` is, at
`factory/roadmap/models.py:351-360`, and the comment there records why: "A
scalar where a list belongs is the defect this repository has already paid for:
read as a list it is a list of characters, and every consumer downstream
believes the spec declared one fix per letter." Absent reads `[]`, `None` reads
`[]`, anything else is a finding. US1 and US2 only need to *emit* text that
parser already accepts — US1-S2 is the proof — and US3 reads keys it returns.
An attempt that adds validation here has duplicated a guard.

**Trap 5 — an absent ledger is not a failed check.** US3's most likely wrong
implementation refuses when it cannot open the store. A freshly initialised
target repo has no `doctor.db` by construction, and `ergane init` creates the
runtime root without one — so a refusal here would fail validation on every new
repo that declared a `fixes:` key. FR-006 is the requirement; US3-S3 is its
proof. Distinguish *absent* from *unreadable* in the message, because they need
different operator acts.

**Trap 6 — the check may not create what it reads.** Calling `connect()` on a
missing path bootstraps a store, which would turn "validate a spec" into "write
a database into the operator's runtime root". Use the existence-check-then-
readonly-open idiom named above.

**Trap 7 — fixtures are supplied trees, never `.factory/`.** Every test here
needs a specs corpus and a findings store. Build both under `tmp_path`. A test
that reads the operator's real ledger will pass on this host and fail in the
gate boundary, where `HOME` is a tmpfs and no runtime root exists.

**Trap 8 — US1-S3 is a regression guard, not a feature.** It is easy to
"clean up" the four prose mentions while adding the declaration, on the theory
that the declaration replaces them. It does not: the prose is what a human
reads and what the `candidate` class reports on, and FR-002 keeps it. Removing
it would make this spec destroy evidence while adding a pointer to it.

## Sizing

US1 is the smallest and the most valuable: one list comprehension and three
appended lines in `_build_spec_md`, plus four tests. US2 is an argparse option
and a pass-through. US3 is the only story with a design decision in it (the
three-way not-checked / pass / refuse outcome) and should be sized above the
other two despite touching fewer lines.

None of the three should need more than one attempt. If an attempt is reaching
for `factory/doctor/triage.py` or `factory/roadmap/models.py`, it has gone
outside the spec — both are read-only to this epic.

## Verification the operator will run, independent of the gate

The gate proves the tests pass. It does not prove the loop closes, because
closing it requires a landed spec and a dated commit, which no gate can produce.
After US1 lands, run this by hand and paste the output into the attestation:

```bash
eval "$(scripts/ergane-env.sh)"
# 1. promote a scratch finding into a throwaway specs root
uv run ergane findings report --db /tmp/loop.db --key demo/one --category demo \
  --severity info --summary "a demonstration finding" --refs [] --notes ""
uv run ergane findings promote --db /tmp/loop.db --slug 999-demo \
  --keys demo/one --specs-root /tmp/specs --target-repo .
# 2. the declaration is in the frontmatter, not only in the prose
head -6 /tmp/specs/999-demo/spec.md
# 3. flip it to landed, commit it so the landing can be dated, then:
uv run ergane findings triage --db /tmp/loop.db --specs-root /tmp/specs --json \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['counts'])"
```

The demonstration succeeds when `demo/one` classifies as `fixed` rather than
`candidate`. That single transition is the whole point of the spec, and it is
the one fact the gate cannot establish.
