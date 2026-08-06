# Contract: Two-Loop Attempt Prompt Assembly

Owned by `factory/workgraph/prompt.py` — **pure and unit-testable**: text in,
prompt out, no filesystem, no registry (FR-006, R9). The file *reads* (spec,
plan.md, tasks.md, prior evidence) happen in the workflow's dispatch path via a
read-only activity (`load_prompt_sources`, part of `agent_activities.py`) so the
assembly itself stays pure; retry evidence comes from the `VerificationResult`
already in workflow state.

## Inputs

| input | source | notes |
|---|---|---|
| story sections | spec text, extracted mechanically | the story's body + acceptance scenarios + each `implements` FR bullet, verbatim |
| plan text | the epic's full `plan.md` | whole file (the clarified context set) |
| tasks slice | `tasks.md`, fence-masked header scan | the phase section whose heading names the story (`User Story <n>`); **no findable slice → assembly fails loudly, dispatch fails before a key is issued** |
| standards directive | `factory.yaml` `standards` path (R11) | present iff declared; existence already verified by `prepare_worktree` |
| failure evidence | prior attempts' `VerificationResult`s | gate `output_tail`s + judge feedback, **verbatim** (002 FR-006); attempt ≥ 2 only |
| slice contract | fixed template | the inner-loop contract below, parameterized by story/epic ids |

## Prompt shape (sections, in order)

1. **Role and scope** — you are one node of an epic; work ONLY this story's task
   slice in this worktree; the branch and worktree are yours alone.
2. **The inner loop (advisory)** — the ralph contract generalized to the slice:
   work the story's tasks in order; test-first; run the deterministic gate
   (`factory.yaml` commands) after each task; commit per task; stop when the
   slice is done or blocked. Stated as *fast feedback for you*.
3. **The outer loop (authoritative)** — verification is independent: gates, output
   check, and judge run after you stop; your own assessment of success carries no
   weight (FR-012). Do not weaken tests to pass gates.
4. **Standards directive** (when declared) — read `<standards path>` before
   writing code and obey it.
5. **Story** — the story sections, verbatim.
6. **Plan** — full plan.md.
7. **Your task slice** — the tasks.md slice, verbatim.
8. **Prior attempt evidence** (retries only) — per prior attempt: termination
   class, each failed gate's `output_tail`, judge feedback; all verbatim, newest
   last.

## Rules

- Nothing is summarized, paraphrased, or truncated by the assembler. Bounding
  prompt size is the operator's authoring concern (story-sized slices), not a
  silent transform — the assembler is deterministic and lossless, so SC-001's
  replay determinism extends to prompts.
- The assembler never invents context: a missing input is a loud dispatch
  failure, not an omitted section (the deriver/coverage rules make the story
  sections' presence structural; the tasks slice is the one input that can be
  authored-missing, hence its explicit failure rule).
- No credentials, proxy URLs, or worker paths outside the worktree appear in the
  prompt: the agent's world is its worktree plus its env (adapter.md).

## Test surface

`test_prompt.py`: golden assembly against fixture spec/plan/tasks texts; slice
extraction (story with slice, story without → error naming the story); retry
prompt carries planted `output_tail`/feedback byte-for-byte; standards directive
present iff declared; determinism (same inputs → identical prompt).
