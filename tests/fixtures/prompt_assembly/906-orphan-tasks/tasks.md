# Tasks: Orphan tasks and a quoted example

## Phase 1: User Story 1 — Save a link

- [ ] T001 [P] [US1] Write the failing test: saving a URL stores a link with a
      unique short code (spec US1-S1) — must fail.
- [ ] T002 [US1] Store the link and mint the code.

The template quotes its own grammar. The line below is an example of the shape
this lint refuses — a task tagged for the second story sitting inside the
first story's slice — and it is quoted, so it is text *about* a task and
reaches no agent:

```text
- [ ] T999 [US2] Not a task. If this is ever reported, the lint stopped using
      the assembler's fence masking.
```

## Phase 2: User Story 2 — Follow a short link

- [ ] T003 [P] [US2] Write the failing test: following a stored code redirects
      to the original URL (spec US2-S1) — must fail.
- [ ] T004 [US2] Resolve the code and redirect.

## Verification

- [ ] T005 Run the full gate command and paste its summary line.
- [ ] T006 Confirm the store on disk is unchanged by the run.
