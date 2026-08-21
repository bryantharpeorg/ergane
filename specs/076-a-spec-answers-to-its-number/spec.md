---
state: draft
# Drafted 2026-08-20 2:00 PM CT by an operator session, from the operator's own
# ask and from a session that had just spent a day typing
# `specs/075-a-stronger-rung-runs-a-stronger-model` by hand, repeatedly, into
# four different verbs.
#
# DO NOT FLIP READY without a pre-dispatch review.
---

# Feature Specification: a spec answers to its number

**Created**: 2026-08-20

## The gap, stated precisely

Specs are numbered. Nothing accepts the number.

```
$ ergane spec validate 075
ergane: cannot read 075/spec.md: [Errno 2] No such file or directory
```

Every verb that takes a spec takes a **path** — `validate` at
`factory/cli/nouns/spec.py:112`, `derive` at `:134`, `landed` at `:167` — and
each resolves it with a bare `Path(args.spec_dir)` (`:231`). So the operator
types `specs/075-a-stronger-rung-runs-a-stronger-model` in full, four times, for
four verbs, and a spec's identity in conversation ("075") is not its identity at
the command line.

The runbook already carries the scar tissue: *"`spec derive` takes the full path,
not the feature name — `--specs-root` is not joined for you. Getting this wrong
prints `cannot read 070-…/spec.md` and silently leaves the previous graph in
place."* That is a documented trap that exists only because the argument is a
path.

## And there is no way to look at one spec

`ergane spec list` renders every spec with its state and blockers
(`factory/roadmap/cli.py:46`). That is the corpus view, and it is the only view.
To answer "what is going on with 075" an operator today runs `spec list` and
greps, then `spec landed` with `--default-branch` remembered correctly, then
`build status` against an epic id they assemble by hand, then reads the
frontmatter for the hold note. Four commands and a paste, for one spec.

The information is all there. Nothing collects it.

## What the number is worth

Numbers are how this project already refers to specs — in conversation, in
commit subjects, in finding notes, in every hold note in every frontmatter in
the corpus. The slug carries the meaning and the number carries the identity,
and the CLI is the one place that insists on the slug.

## User Scenarios & Testing

### User Story 1 - Every spec verb takes a number (Priority: P1)

As an operator, I can name a spec by its number in any verb that takes a spec, so
the identity I use in conversation is the identity I type.

**Why this priority**: P1 and independently useful. It removes a documented trap
and it is the prerequisite for anyone bothering to use US2.

**Acceptance Scenarios**:

1. **Given** a corpus containing `075-a-stronger-rung-runs-a-stronger-model`,
   **When** a spec verb is given `075`, **Then** it operates on that directory —
   proven by a committed test over a supplied corpus.
2. **Given** the same corpus, **When** a verb is given `75`, **Then** it resolves
   the same way; a leading zero is not required — proven by a committed test.
3. **Given** the same corpus, **When** a verb is given the full path it takes
   today, **Then** it behaves exactly as it does today — proven by a committed
   test. Every existing script and runbook passes a path.
4. **Given** a corpus containing both `070-…` and `071-…`, **When** a verb is
   given `07`, **Then** it is refused, naming every candidate — proven by a
   committed test. A prefix that matches more than one spec must never pick one.
5. **Given** a corpus with no spec of that number, **When** a verb is given it,
   **Then** the refusal names the number and the specs root it looked in —
   proven by a committed test.
6. **Given** a number and a `--specs-root` that is not the default, **When** a
   verb runs, **Then** the number resolves against that root — proven by a
   committed test. Not joining it is the documented trap this story removes.

### User Story 2 - One spec's whole picture, in one command (Priority: P1)

As an operator, `ergane spec show <n>` tells me what is true about one spec
without my running four commands and assembling the answer.

**Why this priority**: P1. It is the ask, and it is what the corpus view cannot
do — `list` is one line per spec by construction.

**Acceptance Scenarios**:

1. **Given** any spec, **When** `show` runs, **Then** it reports the state from
   frontmatter, the story count, the landed count, and the task count — proven by
   a committed test.
2. **Given** a spec whose stories have landed, **When** `show` runs, **Then** the
   landed count is read against the declared landing branch, not `main` — proven
   by a committed test. `main` under-reports between promotions and is the wrong
   default for every question an operator asks.
3. **Given** a spec that is blocked, **When** `show` runs, **Then** it names what
   blocks it, the same way `list` does — proven by a committed test.
4. **Given** no reachable control plane, **When** `show` runs, **Then** it prints
   everything readable from disk and reports the epic's state as unknown, rather
   than failing — proven by a committed test. `list` and `validate` work without
   a service and `show` must not be the verb that needs one.
5. **Given** a reachable control plane and a dispatched epic, **When** `show`
   runs, **Then** it reports that epic's state — proven by a committed test.
6. **Given** `--json`, **When** `show` runs, **Then** the same facts are emitted
   as a document — proven by a committed test.

### User Story 3 - The corpus view answers "what should I look at" (Priority: P2)

As an operator, `ergane spec list` shows me progress and lets me filter, so the
list is a work queue rather than an inventory.

**Why this priority**: P2. `list` works today; this makes it answer the question
an operator actually brings to it.

**Acceptance Scenarios**:

1. **Given** a corpus, **When** `list` runs, **Then** each row carries its landed
   count against its total — proven by a committed test.
2. **Given** `--state ready`, **When** `list` runs, **Then** only specs in that
   state are rendered — proven by a committed test.
3. **Given** `--state` naming a state no spec is in, **When** `list` runs,
   **Then** it renders nothing and says so, rather than rendering everything —
   proven by a committed test. A filter that silently falls back to unfiltered is
   worse than no filter.
4. **Given** no flags, **When** `list` runs, **Then** every spec is rendered as
   it is today — proven by a committed test.

## Requirements

- **FR-001**: Every verb accepting a spec MUST accept a spec number in place of a
  path.
- **FR-002**: A number MUST resolve by matching the leading numeric segment of a
  directory under the specs root, with or without leading zeros.
- **FR-003**: A value that matches more than one spec MUST be refused, naming
  every candidate.
- **FR-004**: A value that matches no spec MUST be refused, naming the value and
  the specs root searched.
- **FR-005**: An existing path argument MUST keep working unchanged.
- **FR-006**: Resolution MUST honour `--specs-root` wherever the verb accepts one.
- **FR-007**: `ergane spec show` MUST report, for one spec: state, story count,
  landed count, task count, and blockers.
- **FR-008**: `show` MUST read landed facts against the declared landing branch,
  never `main` by default.
- **FR-009**: `show` MUST degrade when no control plane is reachable, reporting
  the epic state as unknown rather than failing.
- **FR-010**: `show` MUST offer `--json`.
- **FR-011**: `ergane spec list` MUST carry a landed-versus-total count per row.
- **FR-012**: `list` MUST accept a state filter, and MUST render nothing and say
  so when the filter matches nothing.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-007, FR-008, FR-009, FR-010]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-011, FR-012]
```

## Success Criteria

- **SC-001**: Run each spec verb against a number and paste the output, then run
  the same verb against the full path and paste it. They must agree.
- **SC-002**: Run a verb against an ambiguous prefix and paste the refusal.
- **SC-003**: Run `ergane spec show` against a spec with landed stories and paste
  the output beside `ergane spec landed --default-branch ergane-buildout` for the
  same spec. The counts must agree.
- **SC-004**: Run `show` with the control plane stopped and paste the output.
- **SC-005**: Run `list --state ready` and paste it beside the unfiltered list.

## Assumptions

- The numeric segment is the identity. Every spec directory in this corpus is
  `NNN-slug`, and landed story numbers are immutable, so a number is stable.
- Ownership — which specs a factory instance *manages* versus which merely exist
  in a tree — is a separate question and deliberately not in scope. It becomes
  real when Ergane is installed into a brownfield repo it did not bootstrap, and
  it touches the registry and install rather than the spec verbs.
- `show` is a reader. It dispatches nothing, writes nothing, and needs no
  confirmation.
