# Implementation Plan: a spec answers to its number

**Spec**: `specs/076-a-spec-answers-to-its-number/spec.md`

## What already exists, and where

Every line below was read against **`origin/ergane-buildout` at `a76c0ee`** on
2026-08-20 — not against a working copy. Check each again before you rely on it:
on this repository a spec's anchors rot within the hour when the factory ships
into a file the spec cites, and 075 lost every `workflow.py` anchor that way
between 1:33 and 1:41 PM the same day.

**The three verbs that take a spec, and the one line that resolves it:**

- `factory/cli/nouns/spec.py:88-179` — `_add_spec_parser`, where every spec
  subcommand is registered.
- `factory/cli/nouns/spec.py:112` — `validate_cmd.add_argument("spec_dir", …)`.
- `factory/cli/nouns/spec.py:134` — the same for `derive`.
- `factory/cli/nouns/spec.py:167` — the same for `landed`.
- `factory/cli/nouns/spec.py:231` — `spec_dir = Path(args.spec_dir)`. **A bare
  `Path()`, no resolution, no specs-root join.** This is the whole of the defect
  for `validate`; the other two verbs delegate and resolve in their own modules.

**Where the delegated verbs land:**

- `factory/cli/nouns/spec.py:203-207` — `_derive_command`, a thin wrapper that
  calls `derive_command` and translates errors.
- `factory/cli/nouns/spec.py:213-217` — `_landed_command`, the same shape.
- `factory/workgraph/cli.py:236` — `derive_command`, the real one.
- `factory/workgraph/cli.py:151` — `landed_command`, the real one.
- `factory/cli/nouns/spec.py:193-197` — `_list_command`, delegating to
  `render_command`.
- `factory/roadmap/cli.py:46` — `render_command`. Its docstring states the
  contract US3 must not break: "Reads the corpus from disk (no service) … A
  blocked spec names its unsatisfied dependencies on its line, so the operator's
  next move … is on the line — never a bare 'blocked'."

**The identity a resolved directory has to preserve:**

- `factory/cli/nouns/spec.py:238` — `epic_id = spec_dir.resolve().name`. The
  epic id **is** the directory name, so number resolution must yield the real
  directory. A synthetic path that merely reads the right `spec.md` would produce
  the wrong epic id and dispatch under a name nothing else recognises.

**Two definitions of the same constant, already:**

- `factory/workgraph/cli.py:47` — `SPEC_NAME = "spec.md"`.
- `factory/roadmap/models.py:57` — `SPEC_NAME = "spec.md"`.
  Do not add a third. Whichever module the resolver lands in, import one of
  these.

## Traps

**1. Ambiguity refuses; it never picks.** FR-003, US1-S4. `07` matches ten specs
in this corpus and `1` matches eleven. A resolver that takes the first match, or
the lowest, or the "best" one will be right for months and then silently derive
the wrong spec — and `derive` overwrites `workgraph.json`, so the damage is a
graph that looks fine and builds the wrong thing. That failure has already
happened here once from a stale artifact; do not add a second way to reach it.

**2. The path form is load-bearing and must not regress.** FR-005, US1-S3. Every
runbook, every `~/ergane-ops` note and the roadmap's own S5 pass
`specs/070-…` in full. This story *adds* an accepted form. A change that
normalises everything into numbers, or that resolves paths through the same
matcher, will break a caller that passes an absolute path outside the specs root.
Try a path first; fall back to number resolution only when it is not a directory.

**3. `--specs-root` is the trap this story exists to remove — do not reproduce
it.** FR-006, US1-S6. The runbook records it verbatim: "`spec derive` takes the
full path … `--specs-root` is not joined for you. Getting this wrong prints
`cannot read 070-…/spec.md` and silently leaves the previous graph in place."
Note **which verbs even have the flag** before you write the resolution: they do
not all take one, and a resolver that assumes the flag exists will fail on the
verb that lacks it.

**4. The epic id comes from the directory name.** `factory/cli/nouns/spec.py:238`.
Resolution must return the actual directory path, not a constructed one. Assert
this: a test that resolves `075` and then checks `epic_id` is the full slug is
the cheap guard, and it is the difference between this story working and
producing epics named `075`.

**5. `show` must not need a service.** FR-009, US2-S4. `list` and `validate` both
read the corpus from disk with no control plane — `render_command`'s docstring
says so explicitly. If `show` connects unconditionally it becomes the one spec
verb that fails on a laptop, and an operator's first instinct on a broken floor
is to run a status command. Reach for the control plane, catch the failure, and
report the epic as unknown.

**6. Do not reimplement `landed`.** FR-008. `landed_command`
(`factory/workgraph/cli.py:151`) already reads landed facts, and it already knows
about the default-branch problem. `show` calls it or shares its reader. A second
implementation will drift, and the way it will drift is by defaulting to `main`,
which under-reports between promotions.

**7. A filter that matches nothing renders nothing.** FR-012, US3-S3. The
tempting implementation returns the unfiltered list when the filter matches zero
rows, because an empty screen "looks broken". An empty result *is* the answer,
and a silent fallback to everything is how an operator concludes there is work
ready when there is none.

**8. `list` renders one line per spec, and that is a contract.** `render_command`
promises the blocked-spec case names its blockers on the line. US3 adds a column;
it does not restructure the row into a block, and it must not push the blockers
off the line.

**9. Determinism is not at issue here, but the corpus read is.** These are CLI
verbs, not workflow code — clocks and the filesystem are fine. What is not fine
is reading the corpus twice with two different readers: `read_roadmap` is the
one that computes readiness and blockers, and US3's count must come from the same
pass, not from a second walk that can disagree with it.

**10. One test file per story, named here.**
- US1 → `tests/test_spec_number_resolution.py`
- US2 → `tests/test_spec_show.py`
- US3 → `tests/test_spec_list_filters.py`

**11. The graph is a chain, deliberately.** US2 gates on US1 having **merged**
because `show` takes a number and there is no point building it against an
argument that does not exist yet; US3 gates on US2 because both add columns to
operator-facing output and, more concretely, both touch the same rendering
surface. `depends_on` unlocks on verification and `depends_on_merged` on merge
(`factory/workgraph/derive.py:550`) — these are merge edges on purpose. The cost
is that this epic runs one node at a time. Take it: three stories editing one
CLI surface concurrently is the collision that rejected 068/us2's PR the same
day this was written.

**12. The judge sees the diff and the criteria — and Success Criteria are not
criteria.** `factory/verify/criteria.py` reads Success Criteria bullets past;
what reaches a judge is each story's acceptance scenarios and FR bullets.
SC-001 through SC-005 are the operator's. Every Then-clause above is written
"proven by a committed test" so it is provable from the diff alone.

## Sizing

Three small stories, chained.

US1 is a resolver function and three call sites. Its whole difficulty is trap 1
and trap 2 — refusing ambiguity, and not breaking the path form.

US2 is a new verb that mostly calls things that exist. Its difficulty is trap 5:
degrading without a control plane rather than requiring one.

US3 is a column and a filter on a renderer that already exists.

## Verification the operator will run, independent of the gate

- **Prove US1 by agreement.** Run each verb twice — once with `075`, once with
  the full path — and diff the output. Then run one against `07` and read the
  refusal.
- **Prove US2 against a known answer.** `ergane spec show` beside
  `ergane spec landed --default-branch ergane-buildout` for the same spec; the
  landed counts must agree. Then stop the control plane and run it again.
- **Prove US3 by absence.** `list --state ready` beside the unfiltered list, and
  a filter for a state nothing is in.
