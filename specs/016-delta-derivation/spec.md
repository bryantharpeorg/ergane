---
state: draft
# Drafted 2026-08-07 from the operator's request: desired-state
# reconciliation for the factory. The spec corpus is the declared state,
# per-story landings on the default branch are the actual state, and
# derivation's output becomes the difference — so a fresh spec, an amended
# landed spec, and a resume after partial landing are one mechanism with
# three baselines, and hand-trimmed remainder workgraphs (twice violating
# D-025 on 2026-08-07 alone) become a computed artifact.
# Numbered 016: 010–014 reserved for audit-triage epics, 015 is the doctor.
depends_on_landed: [009-roadmap-scheduler]
---

# Feature Specification: Delta Derivation

**Feature Branch**: `016-delta-derivation`

**Created**: 2026-08-07

**Status**: Drafted the day the need was demonstrated twice before lunch.
007 split across runs and its continuation was a hand-trimmed
`workgraph-remainder.json` — us1's edge deleted by an operator's judgment
that the merged base satisfied it. 009 split the same way hours later,
second hand-trim. Both files sit untracked in the repo right now, and both
violate D-025's rule that a workgraph is compiled, never hand-authored. The
operator computed a graph difference in their head; this spec makes the
factory compute it instead.

**Input**: The factory's unit of change is "a new spec" — editing an
already-landed spec has no semantics at all (the roadmap sees `state:
landed` and ignores the file forever), and resuming a partially-landed epic
has no mechanism except the hand-trim. Yet the inputs to compute the
difference are all repo-authoritative already: the corpus is the declared
state, and every queue landing carries its story attribution in the squash
subject (`<epic>/<node>: <STORY> (#PR)` — verified across all eleven landed
stories of 007/008/009). What is missing is the function that subtracts one
from the other, and the identity discipline that keeps the subtraction
honest when specs are edited.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Landed facts are computed from the repo (Priority: P1)

As the factory operator, I ask which stories of a spec have actually landed
and get an answer computed from the default branch's own history — each
landed story with the commit that carried it — so that "what is already
built" is a repo fact any machine can read, not an operator's memory or a
spec-level attestation that cannot see stories.

The landing attribution grammar is the contract: a story is landed iff a
commit on the default branch's history carries its attribution in the
subject. Attested specs (001/002/005-style, which predate epics and will
never have attributed commits) are the deliberate exception: attestation
counts every story landed as of the commit that wrote `state: landed`.
Alongside the facts, the reader computes each landed story's fingerprint —
its criteria and work-graph declaration as they stood at the landing
commit — because the delta deriver's whole judgment is "has this story
changed since it landed", and that question needs both sides of the
comparison pinned to commits.

**Why this priority**: Every delta rule computes over these facts. Also
standalone value: the roadmap's spec-level landed state gains story-level
resolution the day it lands.

**Independent Test**: Against fixture repositories with scripted histories,
assert attributed commits yield landed facts, unattributed commits are
invisible, the latest landing wins for a re-landed story, attestation
baselines resolve to the attesting commit, and fingerprints at a revision
equal the criteria parser's reading of that revision's file.

**Acceptance Scenarios**:

1. **Given** a default branch whose history holds `epic/us2: US2 (#9)`,
   **When** landed facts are computed for that spec, **Then** US2 reports
   landed with that commit, and stories with no attributed commit report
   unlanded.
2. **Given** a story landed twice (re-work after regression), **When** facts
   are computed, **Then** the most recent landing is the story's fact and
   the earlier one is not reported as current.
3. **Given** a spec whose frontmatter is attested `state: landed` with no
   attributed commits anywhere, **When** facts are computed, **Then** every
   story reports landed as of the commit that introduced the attestation.
4. **Given** a landed story and a revision, **When** its fingerprint is
   computed at that revision, **Then** it reflects exactly that revision's
   criteria and work-graph declaration for the story — the current working
   tree MUST NOT leak into a pinned fingerprint.
5. **Given** commits whose subjects carry no attribution (operator commits,
   fix commits), **When** facts are computed, **Then** they contribute
   nothing and cause no error — the grammar is the contract, and silence
   about non-matching subjects is correct, not lenient.

---

### User Story 2 - Derivation subtracts what already landed (Priority: P1)

As the factory operator, I derive a spec against its landed baseline and get
a workgraph containing only the work that remains — unlanded stories, plus
landed stories whose spec text changed since their landing — with satisfied
edges dropped and every drop attributed to the landing commit that satisfied
it, so that the hand-trimmed remainder file is retired and D-025 holds again.

The rules are few and total: an unlanded story is a node; a landed story
whose fingerprint is unchanged is subtracted, and edges through it are
satisfied with provenance; a landed story whose fingerprint changed is a
node again — re-work, carrying what changed as evidence. An empty baseline
subtracts nothing, so a fresh spec's delta is exactly today's full
derivation: one mechanism, and the existing behaviour is its special case.
Identity is guarded, not assumed: a landed story that vanishes from the
spec, or whose number now carries recognizably different content, is a
refusal by name — renumbering landed stories is how a diff comes to lie,
and the deriver's refuse-by-name discipline extends to exactly this.

**Why this priority**: This is the feature. US1 without it is a nicer
status query.

**Independent Test**: Drive the pure delta function through corpus fixtures:
empty baseline equals full derivation node-for-node; unchanged-landed
stories subtract with provenance; a changed scenario re-opens its story
carrying the change; vanished and renumbered landed stories refuse by name;
the 007 split replays to the hand-trimmed remainder.

**Acceptance Scenarios**:

1. **Given** an empty baseline, **When** delta derivation runs, **Then** the
   graph equals full derivation node-for-node — same ids, edges, and
   requirement keys.
2. **Given** a landed story with an unchanged fingerprint, **When** delta
   derivation runs, **Then** it yields no node, every edge on it is
   satisfied, and the provenance names the landing commit that satisfied it.
3. **Given** a landed story whose acceptance scenarios or work-graph
   declaration changed since its landing commit, **When** delta derivation
   runs, **Then** the story is a node again and the delta's provenance
   carries what changed.
4. **Given** a landed story missing from the spec, or a landed story number
   whose story content no longer matches its landed fingerprint beyond the
   amendment the provenance can explain, **When** delta derivation runs
   without an explicit supersession declared for it, **Then** derivation
   refuses naming the story and the rule — nothing is emitted (the
   deriver's all-or-nothing discipline).
5. **Given** the 007 split as a fixture (us1/us2 landed, us3/us4/us5 not),
   **When** delta derivation runs, **Then** the emitted graph matches the
   2026-08-07 hand-trimmed remainder node-for-node and edge-for-edge — the
   operator's judgment, reproduced by computation.

---

### User Story 3 - The roadmap reconciles instead of ignoring (Priority: P2)

As the factory operator, when I amend a landed spec the roadmap tells me it
drifted instead of ignoring it forever, and when I flip the amended spec to
`ready` it dispatches a delta epic — only the changed work, under the
existing reuse-on-closed workflow id convention — so that the loop from
"edit the declared state" to "the factory builds the difference" closes
with the same single human act every other dispatch already honors.

Dispatch uses delta derivation universally: a fresh spec derives against an
empty baseline and behaves exactly as today; a partially-landed spec
re-readied after a split derives to its remainder; an amended landed spec
derives to its re-work. Drift is reported, never acted on: `state: landed`
plus changed story content renders as amended in the roadmap, and nothing
dispatches until the operator flips the state — the intent/observation
split, unchanged.

**Why this priority**: Real, but the CLI verbs from US1/US2 bank most of
the value with the operator running them by hand; the roadmap integration
makes it unattended.

**Independent Test**: With scripted children, a partially-landed spec
re-readied dispatches only its remainder; an amended landed spec renders as
amended and dispatches only after the state flip; a fresh spec's dispatch is
byte-compatible with today's.

**Acceptance Scenarios**:

1. **Given** a landed spec whose story content changed since its landing
   baseline, **When** the roadmap renders, **Then** the spec is visibly
   amended — distinct from `landed` and from `ready` — and nothing
   dispatches.
2. **Given** an amended spec flipped to `ready`, **When** the roadmap
   schedules, **Then** the dispatched epic's graph is the delta — re-work
   and new stories only — under the reuse-on-closed id convention.
3. **Given** a spec whose epic closed with some stories landed and some not,
   **When** the operator re-readies it, **Then** the dispatched graph is the
   computed remainder and no hand-authored remainder file is involved.
4. **Given** a fresh spec with no landings, **When** it dispatches, **Then**
   the graph is identical to what full derivation produces today — adopting
   delta dispatch changes nothing for the existing corpus.
5. **Given** a delta epic that lands, **When** facts are recomputed,
   **Then** the amended stories' fingerprints at their new landing commits
   match the current spec and the roadmap renders the spec landed again —
   the loop is closed and re-entrant.

---

### Edge Cases

- A changed functional requirement re-opens every story that `implements`
  it: the FR body is part of each implementing story's fingerprint, because
  criteria are what the judge holds a story to and a story judged against
  new criteria is new work.
- Prose-only edits — Status paragraphs, assumptions, frontmatter comments,
  typo fixes outside criteria and declarations — change no fingerprint and
  produce an empty delta: an empty delta is a success ("nothing to build"),
  not an error, and dispatching a zero-node epic is refused before any
  clone.
- The two untracked remainder files from 2026-08-07 are inputs to SC-002's
  replay fixture and are retired by this feature; the operator runbook step
  "trim the remainder by hand" is deleted, not documented.
- Attested baselines have no per-story landing commits, so an amended
  attested spec fingerprints against the attesting commit — coarser but
  honest, and reported as such in provenance.
- A story landed under an old attribution grammar (none exist today; the
  grammar is uniform across all eleven landed stories) would simply read as
  unlanded — the failure mode is visible re-work, never silent subtraction.
- History rewrites on the default branch invalidate landed facts; the
  factory already forbids them (the queue is the only writer), and the
  reader treats an attributed commit no longer reachable from the default
  branch as not landed.
- No new store and no cached graph: facts and deltas are computed from git
  and corpus on demand, every time. Durability comes from purity — any
  historical delta is recomputable at its commit — not from retention.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Per-story landed facts MUST be computed from default-branch
  history via the landing attribution grammar (`<epic>/<node>: <STORY>` in
  the squash subject), yielding story key → landing commit; non-matching
  subjects MUST contribute nothing; the most recent attributed landing MUST
  win for a story landed more than once.
- **FR-002**: A spec attested `state: landed` with no attributed commits
  MUST baseline every story as landed at the commit that introduced the
  attestation, and provenance MUST distinguish attested baselines from
  observed ones.
- **FR-003**: A story's fingerprint — its criteria as the criteria parser
  reads them, the FR bodies it implements, and its work-graph declaration —
  MUST be computable at any revision, pure against that revision's file
  content, with the working tree never leaking into a pinned fingerprint.
- **FR-004**: Delta derivation MUST be a pure function of (current spec
  text, landed facts, pinned fingerprints) emitting a workgraph containing
  exactly: every unlanded story, and every landed story whose fingerprint
  differs from its landing — carrying what changed as provenance evidence.
- **FR-005**: Edges into subtracted stories MUST be dropped as satisfied,
  each with provenance naming the landing commit that satisfied it; the
  emitted artifact MUST remain a compiled workgraph in the existing schema
  (D-025), dispatchable unchanged by the existing interpreter.
- **FR-006**: An empty baseline MUST yield a graph node-for-node identical
  to full derivation — existing behaviour is the special case, and the
  existing derive path MUST NOT change meaning for any current spec.
- **FR-007**: Identity MUST be guarded: a landed story absent from the
  current spec, or a landed story key whose content no longer corresponds
  to its landed fingerprint in a way provenance can attribute to amendment,
  MUST refuse derivation naming the story and rule, emitting nothing —
  landed story numbers are immutable; new work takes new numbers.
- **FR-008**: The CLI MUST expose delta derivation and landed facts as
  offline verbs following the existing exit-code contract, and an empty
  delta MUST be reported as success with nothing emitted and nothing
  dispatchable.
- **FR-009**: The roadmap MUST render a landed spec whose fingerprints
  drifted from their baseline as amended — distinct from `landed` and
  `ready` — and MUST NOT dispatch it until the operator sets `state:
  ready`; drift detection MUST be read-only.
- **FR-010**: Roadmap dispatch MUST derive through the delta path
  universally — fresh, partially-landed, and amended specs are one
  mechanism with different baselines — reusing the closed workflow id
  convention for re-dispatch, and a zero-node delta MUST refuse dispatch
  before any clone or key issuance.
- **FR-011**: This feature MUST add no persistent store and no new
  dependency: landed facts, fingerprints, and deltas are computed from git
  and the corpus on demand, and the decision log MUST record the
  supersession of hand-authored remainder graphs when the first delta epic
  lands.

### Key Entities

- **Landed fact** — one story's landing: key, commit, observed-or-attested.
- **Fingerprint** — a story's judgeable content pinned at a revision:
  criteria, implemented FR bodies, work-graph declaration.
- **Delta** — the compiled workgraph of remaining work plus its provenance:
  subtracted stories with satisfying commits, re-opened stories with what
  changed, satisfied edges.
- **Amended spec** — a landed spec whose current fingerprints differ from
  their baselines: visible in the roadmap, inert until re-readied.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every spec in the current corpus, delta derivation against
  an empty baseline equals full derivation node-for-node — adopting the
  mechanism changes nothing that exists.
- **SC-002**: The 007 and 009 splits, replayed as fixtures, each compute to
  their 2026-08-07 hand-trimmed remainder node-for-node and edge-for-edge —
  and the two remainder files are retired from the operational runbook.
- **SC-003**: A one-scenario amendment to a landed fixture spec produces a
  one-node delta whose provenance quotes the change; a prose-only edit
  produces an empty delta reported as success.
- **SC-004**: Renumbering a landed story in a fixture refuses derivation
  naming the story; no partial graph is ever emitted.
- **SC-005**: The full existing suite stays green; the feature adds no
  dependency and no store; a fresh spec dispatched through the roadmap
  behaves byte-identically to the pre-delta dispatch path.

## Work Graph

US2 imports US1's facts and fingerprint modules — merged, not passed, per
the 009 first-run lesson. US3 imports both and additionally touches the
roadmap's dispatch path and render, so it chains on US2 merged: the
same-file conflict-avoidance argument every sequential epic has used.
Nothing here modifies the epic interpreter: the delta is a compiled
workgraph in the existing schema, and the interpreter runs it exactly as it
runs a full one — which is what keeps this spec buildable by the factory it
reconciles.

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-004, FR-005, FR-006, FR-007]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-008, FR-009, FR-010, FR-011]
```

## Assumptions

- 009 has landed (frontmatter edge): US3 extends the roadmap's render and
  dispatch; drift reporting composes with its readiness computation.
- The landing attribution grammar stays what `prepare_landing_pr` renders
  today; if the subject format ever changes, the reader and the renderer
  change in one commit — they are two ends of one contract.
- The default branch is append-only (the queue is its only writer); landed
  facts assume reachable history.
- Story-level supersession grammar (an explicit "US4 replaces US2"
  declaration) is future work: this spec refuses ambiguous identity rather
  than resolving it, and the refusal message is the specification of what a
  later grammar must express.
- 015-factory-doctor is independent: neither spec imports the other. The
  doctor's ledger is where this spec's own idea was meant to be filed;
  drafting it directly was the operator's call the same day.

## Decision: the corpus declares, the branch testifies, the delta is computed (decided 2026-08-07, Bryan)

Four calls, made in conversation the day two hand-trims proved the need:

1. **Desired state lives in the spec corpus; actual state lives in
   default-branch attributions.** No third register: no graph store, no
   state file — the two histories the repo already keeps are the whole
   input, and purity of the functions over them is what makes any
   historical delta recomputable.
2. **Changes begin at specs, never at graphs.** Editing a workgraph and
   "diffing it on its own" was considered and rejected as a D-025
   violation — the graph remains a compiled artifact in both directions.
3. **Landed story numbers are immutable.** Identity is the precondition of
   honest diffing; the deriver refuses renumbering rather than guessing,
   and supersession earns its own grammar later.
4. **Drift is reported, never auto-dispatched.** An amended landed spec is
   a fact the roadmap shows; work begins at the operator's `ready` flip —
   the intent/observation split survives its third feature intact.

**The decision-log number is deliberately unassigned here** — claimed at
landing time in `docs/decisions.md`, alongside the remainder-graph
supersession FR-011 requires.
