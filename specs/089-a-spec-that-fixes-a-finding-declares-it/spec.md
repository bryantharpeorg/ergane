---
state: landed
# Attested landed 2026-08-29 by the away-mode loop. US1 847c4e4c2c17 (#375),
# US2 c810654679c6 (#374), US3 f328e6c73223 (#376) — all three observed on
# ergane-buildout by `ergane spec landed --default-branch ergane-buildout`.
#
# FIRST EPIC EVER DISPATCHED AT --max-concurrent-nodes 2, and the concurrency
# question it was run to answer came back clean. us1 and us2 built side by side
# from 08:40 and both merged by 09:20 — 40 minutes for two stories against ~82
# serial. No session-ID collision: the two live agents carried distinct
# `--session-id` values, which is the mechanism, because `workflow.uuid4()`
# issues one per node. The open critical
# `workgraph/concurrent-nodes-collide-on-agent-session-ids` predicts collision
# above cap 1 and is not refuted by this — its mechanism is a retry overlapping
# its original, which did not occur here — but this is its first
# counter-observation and the first concurrent pair in the transcript record.
#
# US3 TOOK THREE ATTEMPTS, WITH THREE DIFFERENT ENDINGS, and the distinction is
# worth keeping because only one of them is the system working:
#   attempt 1  boundary gate exit 1 on a single test —
#              `tests/test_us4_boundary.py::test_hanging_agent_is_killed_at_deadline_with_no_survivors`.
#              The agent's own run had SKIPPED that test (5154 passed / 58
#              skipped vs the gate's 5154 / 57 / 1 failed). Known flake, filed as
#              `ci/the-deadline-boundary-test-fails-intermittently-in-the-full-suite`,
#              occurrence 3 — and the operator session was running a 112-spec git
#              scan on the same host during that exact 341-second window, so the
#              likely cause is operator load, not decay.
#   attempt 2  gate PASSED outright (5155 passed, exit 0); judge returned RETRY
#              on one of four scenarios. This one is the ladder working.
#   attempt 3  gate and judge both passed.
#
# THE JUDGE FOR THIS EPIC WAS `ollama-cloud/glm-5.3-flash`, not the
# `ollama-cloud/kimi-k2.7-code` the registry names now, and the implementer was
# kimi rather than the glm-5.3 now wired. The registry is snapshotted once at
# epic start (`_persona_snapshot`, factory/workgraph/workflow.py:1319) and the
# rotation landed at 09:10, mid-epic. A persona change reaches the NEXT epic.
# Recorded here because `ergane build status --json` resolves against the live
# registry and will therefore misreport this epic forever.
fixes:
  - doctor/promote-scaffolds-a-spec-that-names-its-findings-in-prose-and-declares-none-of-them
# DRAFTED 2026-08-28 by the operator session, against ergane-buildout at 8bb2d4b.
# The directory `specs/089-a-spec-that-fixes-a-finding-declares-it/` was reserved
# — empty and untracked — by the spec-routing session on 2026-08-23 at 14:04,
# alongside 090-102. Only 099 was written. This fills the first of them, and it
# is first because every other slot in that block depends on it: a spec that
# closes a finding cannot prove it did so until this lands.
#
# WHY THIS EXISTS, IN ONE SENTENCE. `ergane findings promote` — the verb whose
# entire purpose is to scaffold a spec from selected findings — writes
# `state: draft` and nothing else, names each finding key in the generated prose
# four times, and declares none of them under `fixes:`.
#
# THAT IS EXACTLY THE CASE `triage` REFUSES. `factory/doctor/triage.py:543`
# rejects it in as many words: "named in the prose of landed spec(s) …, but no
# 'fixes:' declares it — prose is not a declaration". So a spec produced by
# `promote`, built by the factory and landed, lands in triage's `candidate`
# class — the one class `--apply` may not act on (FR-008). The doctor's two
# halves disagree by construction: `promote` emits what `triage` is built to
# refuse, and the operator closes by hand what the machine was supposed to close.
#
# THE REFUSAL IS RIGHT AND MUST NOT BE RELAXED. The tempting fix is to let
# triage read prose. `triage.py`'s own docstring says why not, from measurement:
# on the corpus 073 was written against, one key was named by six specs — two as
# their fix, one in an out-of-scope list, one as background, and one in a note
# saying the finding had REGRESSED. A rule that read prose as a declaration
# would have closed a live regression. This spec therefore changes the writer,
# never the reader.
#
# THE GRAMMAR IS ALREADY THERE. `fixes` is a member of `_KNOWN_KEYS`
# (`factory/roadmap/models.py:117`), added by 073-US1, parsed by
# `_declaration` (`factory/doctor/triage.py:282-304`), and rejected by name when
# it is not a list of strings. Nothing in this spec widens the frontmatter
# grammar. It makes two writers use a key that already exists, and adds one
# check that the key names something real.
#
# WHY A TYPO IS THE SECOND HALF. A declared key that matches no ledger row is
# indistinguishable, to every reader, from a spec that declares nothing —
# `triage` matches keys exactly or on segment boundaries and simply never fires.
# The failure is silent, permanent, and discovered only when someone asks why a
# finding is still open. `spec validate` already composes five checks and
# refuses precisely; this is a sixth, and it is the only one in this spec that
# needs an argument about severity (US3).
#
# NOT IN SCOPE. This spec does not change `triage`'s classification, does not
# touch the recurrence machine (`factory/doctor/store.py:137`), does not add a
# frontmatter key, does not make `fixes:` mandatory on a hand-written spec, and
# does not backfill the existing corpus. Backfill is an operator act over a
# corpus this spec is what makes checkable; doing both at once would mean
# editing landed specs with a checker that had never run.
---

# Feature Specification: a spec that fixes a finding declares it

**Created**: 2026-08-28
**Depends on**: nothing outside this spec. US1 → US2 are independent and may
build concurrently; US3 depends on neither, but is sequenced last because its
test corpus is easiest to write once US1 emits declarations.

## The gap, stated precisely

The ledger can record a defect, count its recurrences, and scaffold a spec
directory from a set of them. `triage` can then read the specs corpus and close
what a landed spec declared it fixed. Between those two capabilities there is
no connection, and the missing link is one YAML key.

Three specific things stand in the way, in descending order of how much they
cost:

1. **The scaffolding verb drops its own provenance.** `scaffold_spec`
   (`factory/doctor/scaffold.py:27`) is handed the exact `Finding` objects the
   operator selected. It writes `---` / `state: draft` / `---`
   (`:156-158`, `:320-325`). It then names `finding.key` in a Given clause
   (`:347`), an FR (`:370`), a bullet list of what the spec addresses (`:398`),
   and a task (`:415`). The information is in hand at the moment the frontmatter
   is written, and it is spent entirely on prose that `triage` is required to
   ignore.
2. **`spec new` cannot express it at all.** `_new_command`
   (`factory/cli/nouns/spec.py`) scaffolds a full trio and has no `fixes`
   vocabulary, so an operator writing a spec against a known finding — the
   ordinary case — has to know the key exists, remember its spelling, and hand-
   edit frontmatter the verb just wrote.
3. **Nothing checks that a declared key is real.** `spec validate` composes
   frontmatter, work-graph derivation, persona registry, scenario coverage,
   prompt assembly and slice coverage. None of them reads the ledger, so
   `fixes: [verify/a-key-that-does-not-exist]` validates clean and silently
   declares nothing forever.

## The rule this spec is asking for

**A spec that closes a finding says so in the one place a machine reads, and a
declaration that names nothing is refused before the spec is dispatched.**

### What this spec is not

It is not a change to `triage`. The classifier is correct, its precedence order
is argued from measurement, and `prose is not a declaration` is the rule that
protects a live regression from being closed by a passing mention. Every story
here is on the writing side.

It is not a mandate. A spec that fixes no finding declares nothing, and that
stays valid — US3 refuses a `fixes:` that names an *unknown* key, never a spec
that omits the key. Making `fixes:` required would put a false declaration in
an author's mouth on every refactor.

It is not a backfill. The landed corpus has specs that closed findings and never
said so; correcting them is an operator act, it is what the 0.6 sweep is for,
and it wants the checker in US3 to already exist.

## User Scenarios & Testing

### User Story 1 - The promote verb declares what it promoted (Priority: P1)

As an operator, the spec `ergane findings promote` scaffolds carries the keys it
was built from, so landing it closes those findings instead of leaving them as
candidates nobody may act on.

**Why this priority**: P1 and it depends on nothing. It is the whole defect —
073-US1 added `fixes:` to the grammar and this is the writer that was never
taught to use it. Without it the doctor's own loop cannot close.

**Acceptance Scenarios**:

1. **Given** a ledger holding open findings `a/one` and `b/two`, **When** the
   operator runs `ergane findings promote --slug <slug> --keys a/one b/two`,
   **Then** the generated `spec.md` frontmatter carries `state: draft` and a
   `fixes:` list whose members are exactly `a/one` and `b/two`, in the order
   given — proven by a committed test.
2. **Given** a spec generated by that command and then read as a landed record,
   **When** its frontmatter is parsed by `_declaration`, **Then** both keys are
   returned on the parsed record rather than an empty list — proven by a
   committed test.
3. **Given** a promote invocation naming one key, **When** the spec is
   generated, **Then** the existing prose mentions of that key — the Given
   clause, the functional requirement, the addressed-findings bullet and the
   task — are all still present, proven by a committed test. This story adds a
   declaration and removes no evidence.
4. **Given** a promote invocation, **When** the generated trio is validated,
   **Then** `ergane spec validate` returns the same verdict it returns for a
   promote-generated trio today — proven by a committed test.

### User Story 2 - A new spec can name its finding when it is created (Priority: P2)

As an operator, I name the finding a spec addresses once, when I create the
spec, instead of hand-editing frontmatter the verb has just written.

**Why this priority**: P2 and independent. It is convenience over correctness —
US1 fixes the machine-generated path, this fixes the hand-authored one — but it
is where most specs in this corpus actually come from.

**Acceptance Scenarios**:

1. **Given** a ledger holding `a/one`, **When** the operator runs
   `ergane spec new <slug> --fixes a/one`, **Then** the scaffolded `spec.md`
   carries a `fixes:` list with that single member — proven by a committed test.
2. **Given** the flag supplied twice with different keys, **When** the spec is
   scaffolded, **Then** both keys appear in the list in the order given —
   proven by a committed test.
3. **Given** no `--fixes` argument, **When** `ergane spec new <slug>` runs,
   **Then** the scaffolded frontmatter is byte-identical to what the verb writes
   today — proven by a committed test. The flag is additive and its absence
   changes nothing.

### User Story 3 - A declaration that names nothing is refused (Priority: P1)

As an operator, a `fixes:` key that matches no ledger row is refused when I
validate the spec, not discovered months later when someone asks why the finding
is still open.

**Why this priority**: P1, and it is what makes US1 and US2 safe. A typo'd
declaration is worse than an absent one: it reads as done to every human and
behaves as absent to `triage`, which matches keys exactly or on segment
boundaries and simply never fires.

**Acceptance Scenarios**:

1. **Given** a spec whose `fixes:` names a key absent from the ledger, **When**
   `ergane spec validate <spec-dir>` runs, **Then** it refuses, naming the
   unknown key and the store path it read — proven by a committed test.
2. **Given** a spec whose `fixes:` names only keys present in the ledger,
   **When** validate runs, **Then** the layer passes and reports how many keys
   it verified — proven by a committed test.
3. **Given** a runtime root holding no ledger, **When** validate runs on a spec
   declaring `fixes:`, **Then** the layer reports `not checked` naming the
   absent store and does **not** refuse — proven by a committed test. An absent
   store is not evidence that a key is wrong, and a freshly initialised target
   repo has no ledger by construction.
4. **Given** a spec that omits `fixes:` entirely, **When** validate runs,
   **Then** its verdict is unchanged from before this story — proven by a
   committed test over the existing corpus, 68 members of which omit the key.

## Work Graph

```yaml
US1:
  implements: []
  depends_on: []
US2:
  implements: []
  depends_on: []
US3:
  implements: []
  depends_on: []
  depends_on_merged: [US2]
```

US1 changes `factory/doctor/scaffold.py` and is independent of both others. US2
and US3 both change `factory/cli/nouns/spec.py` — US2 adds an option to the
`spec new` subparser, US3 adds a layer to the `validate` composition — so they
are serialised on **file ownership rather than on logic**, which is why the edge
is `depends_on_merged` and not `depends_on`. Raced, whichever landed second
would be rejected for the other's change. `ergane spec validate` infers this
contention and advises the same edge; it is declared here so the graph says what
the tool would otherwise have to guess.

## Requirements

- **FR-001**: `scaffold_spec` MUST write a `fixes:` list into the generated
  frontmatter naming every finding it was given, in the order given.
- **FR-002**: `scaffold_spec` MUST continue to emit each finding key in the
  prose positions it emits today — the Given clause, the functional requirement,
  the addressed-findings bullet and the task.
- **FR-003**: `ergane spec new` MUST accept a repeatable `--fixes <key>` option
  and write the resulting list into the scaffolded frontmatter.
- **FR-004**: When `--fixes` is absent, `ergane spec new` MUST write frontmatter
  byte-identical to what it writes today.
- **FR-005**: `ergane spec validate` MUST refuse a `fixes:` entry that matches no
  key in the ledger, naming the unknown entry and the store path it read.
- **FR-006**: `ergane spec validate` MUST report the `fixes:` layer as *not
  checked* — never as a refusal — when the ledger is absent or unreadable, and
  MUST name which of the two it encountered.
- **FR-007**: Every story MUST leave `_KNOWN_KEYS`
  (`factory/roadmap/models.py:117`) and every classification in
  `factory/doctor/triage.py` unchanged.

## Success Criteria (summary)

- A spec produced by `ergane findings promote`, landed and dated, moves its
  findings from `candidate` to `fixed` under `ergane findings triage`, with no
  hand-editing between generation and landing.
- A `fixes:` typo is refused at authoring time rather than discovered when
  someone asks why a finding is still open.
- A repository with no ledger validates exactly as it does today.
