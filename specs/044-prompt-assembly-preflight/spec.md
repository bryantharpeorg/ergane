---
state: draft
# Drafted 2026-08-15 by an operator session, same morning as the incident in the
# Context. Scaffolded by hand, not by `ergane findings promote`; the driving
# finding is `interpreter/prompt-assembly-fails-only-at-dispatch` (critical,
# filed the same morning). Every acceptance scenario is provable from the diff
# (D-037): incidents are reproduced as committed fixtures, never referenced as
# history the judge cannot see.
---

# Feature Specification: 044-prompt-assembly-preflight

## Context

On the morning of 2026-08-15 the roadmap dispatched `043-runtime-root-integrity`.
One tick later every node was dead, killed before any agent ran:

```
node 'us1': tasks.md declares no phase naming user story US1, so this node has
no task slice to work (FR-006)
```

The grammar that message enforces — a phase heading containing literally
`User Story <n>` — lives in `factory/workgraph/prompt.py` and is checked in
exactly one place: `build_attempt_prompt`, called from the epic workflow at
dispatch (`factory/workgraph/workflow.py:1212`). Dispatch is therefore the first
moment a spec author learns their tasks.md does not parse, and the price of the
lesson is an epic.

The same session found the subtler variant in `011-agent-sandbox` before it
dispatched: subsection headings written at phase level, so `_task_slice` — which
returns the first matching section *up to the next heading of the same or
shallower level* — would have produced a slice containing only the story's
tests. Five agents would have been dispatched with half their tasks silently
missing, and the failure would have surfaced as inexplicable judge FAILs at full
attempt price, not as a grammar error.

`ergane spec validate` already runs four layers — frontmatter, work-graph
derivation, persona registry, scenario coverage (`factory/cli/nouns/spec.py:262`)
— and none of them assembles a prompt. The roadmap's pre-epic preflight checks
model aliases only (`factory/activities/roadmap_activities.py:353`). The one
function that knows whether a spec can be dispatched is never asked until the
answer costs something. The operator closed the gap by hand, importing
`prompt._task_slice` into a throwaway script; this spec makes that check a
first-class layer with one shared implementation.

---

### User Story 1 - `ergane spec validate` assembles every node's prompt (Priority: P1)

A spec trio that cannot be assembled into prompts is not ready, and the operator
must learn that from `ergane spec validate` at refinement time — offline, in
seconds, naming the node and the document at fault — never from a dispatch tick.

**Why this priority**: It is the cheapest point of the whole leverage curve. The
measured cost of learning this at dispatch is one killed epic per defect; the
cost of learning it at refinement is one command.

**Independent Test**: Run `ergane spec validate` against a fixture trio carrying
the exact 043 heading defect and confirm the finding names the node, the story
and tasks.md; run it against a well-formed trio and confirm the new layer
reports clean.

**Acceptance Scenarios**:

1. **Given** a fixture spec trio whose tasks.md phase headings omit the literal
   `User Story <n>` (the 2026-08-15 defect, reconstructed), **When**
   `ergane spec validate` runs, **Then** it exits non-zero with a
   `prompt_assembly` finding naming the node, the story key and tasks.md,
   proven by a committed test.

2. **Given** a fixture trio whose spec.md declares no section for a story the
   graph derives, **When** validate runs, **Then** the finding names the node
   and spec.md, proven by a committed test.

3. **Given** a well-formed trio, **When** validate runs, **Then** the report's
   `checked` list contains `prompt_assembly` alongside the four existing layers
   and no finding is emitted, proven by a committed test.

4. **Given** a trio whose plan.md or tasks.md is missing entirely, **When**
   validate runs, **Then** the layer reports the missing file as a finding
   rather than crashing, proven by a committed test.

5. **Given** the diff, **When** the new layer's implementation is read, **Then**
   it assembles prompts by calling the same functions the dispatch path calls,
   and no second copy of the heading grammar exists — proven by a committed test
   that fails if the validate layer's module defines its own story-heading
   regex.

---

### User Story 2 - The roadmap refuses to dispatch an epic whose prompts cannot assemble (Priority: P1)

Validation the operator must remember to run is advice. The roadmap already
refuses to dispatch an epic whose model aliases are unserved — one preflight
check, run as an activity before any node starts, parking the spec with a
finding the operator can read and fix. Prompt assembly belongs in that same
slot: it is knowable before any key is issued, and a spec whose prompts cannot
assemble must park exactly the way one whose aliases are unserved does, with
zero nodes dispatched and zero attempts burned.

**Why this priority**: Specs are read live at dispatch, so a tasks.md edited
after a clean `spec validate` can still arrive broken. The preflight is the last
gate that costs nothing.

**Independent Test**: Point a roadmap at a spec with a defective tasks.md, let
it tick, and confirm the spec parks with the assembly finding and no node was
ever dispatched.

**Acceptance Scenarios**:

1. **Given** a ready spec whose tasks.md carries the 043 heading defect,
   **When** the roadmap reaches it, **Then** the spec parks with a preflight
   finding whose check is `prompt-assembly`, quoting the `PromptAssemblyError`
   message verbatim, and no agent attempt was dispatched for any node — proven
   by a committed workflow test asserting the park and the absence of any
   dispatched attempt.

2. **Given** a well-formed ready spec, **When** the roadmap reaches it, **Then**
   dispatch proceeds exactly as before, proven by a committed test.

3. **Given** the diff, **When** the preflight's implementation is read, **Then**
   the assembly check makes no proxy call and opens no client — it is a pure
   read of the spec trio and the derived graph, proven by a committed test that
   runs it with no network available.

4. **Given** a spec that parks under this check and whose tasks.md is then
   fixed, **When** the operator unparks it, **Then** the next tick dispatches
   it normally, proven by a committed workflow test.

---

### User Story 3 - Tasks that reach no agent are named (Priority: P2)

The 011 near-miss was not an assembly failure — every slice assembled. The
defect was that tasks the author wrote for a story were outside that story's
slice, so agents would have received prompts that assemble perfectly and are
silently incomplete. The complement also exists in the tree today: task lines in
a trailing section that belong to no story's slice and therefore reach no agent
at all. Both facts are computable offline from the same assembly the validate
layer already performs, and both should be reported — the first as a defect, the
second as information the author confirms or acts on.

**Why this priority**: P2 because it guards against silent scope loss rather
than epic death; it rides on US1's machinery.

**Independent Test**: Run validate against a fixture reproducing the 011
subsection defect and confirm the misplaced task ids are named with their story;
run it against a trio with an untagged trailing verification section and confirm
the orphan ids are reported as information, not error.

**Acceptance Scenarios**:

1. **Given** a fixture tasks.md where phase-level headings split a story's tests
   from its implementation (the 011 defect, reconstructed), **When** validate
   runs, **Then** a `slice_coverage` finding names each task id that references
   the story but falls outside its slice, and names the story — proven by a
   committed test.

2. **Given** a tasks.md whose task line carries a story reference (a `[US<n>]`
   tag or a `spec US<n>-` citation) and sits inside a different story's slice,
   **When** validate runs, **Then** the finding names the task id, the story it
   references and the slice it sits in, proven by a committed test.

3. **Given** a tasks.md with task ids inside no story's slice and carrying no
   story reference, **When** validate runs, **Then** they are reported as
   information listing the ids, the exit code is unchanged by them, and a
   trailing section with no task ids reports nothing — proven by committed
   tests.

4. **Given** a well-formed trio where every task id falls inside exactly the
   slice its story reference names, **When** validate runs, **Then**
   `slice_coverage` reports nothing, proven by a committed test.

---

## Functional Requirements

- **FR-001**: `ergane spec validate` MUST assemble the complete attempt prompt
  for every node of the derived graph, using the same functions the dispatch
  path uses, and MUST report each assembly failure as a finding naming the node
  and the document at fault.
- **FR-002**: The assembly check MUST be pure and offline: no proxy call, no
  Temporal connection, no network.
- **FR-003**: The roadmap MUST run the same assembly check before dispatching
  any node of an epic, and on failure MUST park the spec naming the node and
  quoting the assembly error, with no node dispatched and no key issued.
- **FR-004**: The offline layer and the roadmap preflight MUST share one
  implementation. A second copy of the heading grammar anywhere is a defect.
- **FR-005**: A task line referencing a story whose assembled slice does not
  contain that line MUST be reported as a defect naming the task id and the
  story.
- **FR-006**: Task lines inside no slice and referencing no story MUST be
  reported as information naming the ids, and MUST NOT fail validation.
- **FR-007**: The check MUST read the spec trio through the same reads the
  dispatch path performs, so the bytes checked are the bytes dispatched.

## Success Criteria

- **SC-001**: The 2026-08-15 kill is reproducible as a fixture and caught
  offline: validate on the reconstructed 043 trio reports the defect that the
  dispatch tick reported, before any dispatch.
- **SC-002**: The 011 near-miss is reproducible as a fixture and caught offline:
  validate names the task ids a tests-only slice would have dropped.
- **SC-003**: A roadmap pointed at a defective ready spec parks it with zero
  dispatched nodes, proven in a workflow test.
- **SC-004**: **Control.** The two fixture defects above pass the four existing
  validate layers with no finding — proven by a committed test that runs only
  those layers — establishing that the new layer changed an outcome rather than
  duplicating one.

## Out of Scope

- Retry-signature analysis (an attempt failing identically twice) — a separate
  candidate spec.
- Any change to the prompt grammar itself. This spec makes the existing grammar
  checkable early; loosening or extending it is other work.
- Scenario-coverage semantics — layer four exists and is untouched.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-004, FR-007]
US2:
  depends_on: [US1]
  implements: [FR-003]
US3:
  depends_on: [US1]
  implements: [FR-005, FR-006]
```
