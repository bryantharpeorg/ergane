# Tasks: Agent Home Isolation

**Input**: [spec.md](spec.md) and [plan.md](plan.md) in this directory.

Every task is test-first (constitution II): the test task is written and **must
fail** before its implementation task runs. A task that finds its test already
passing has found a defect in the test, not a task it may skip.

Tasks marked `[P]` touch disjoint files within their story and may be written in
any order. Tasks without it are sequential because they share a file — which is
most of them here, since all four stories converge on
`factory/workgraph/adapter.py`.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (operator preflight — dispatched to no node)

- [x] T001 Operator: **probed 2026-08-08, recorded here as the gate's evidence.**
      The adapter's own argv shape (`claude -p --dangerously-skip-permissions
      --model ollama-cloud/kimi-k2.7-code --session-id <uuid>`, prompt on stdin)
      was run against an empty `HOME` with an environment of exactly
      `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, `PATH`, `HOME`, `LANG`,
      `TERM`. Three findings:
      **(1) It starts.** Exit 0, answered, no prompt, no onboarding wall. The
      CLI created its own `.claude.json`, `.claude/plugins/`,
      `.claude/projects/`, `.claude/sessions/` and `.claude/backups/`. FR-004 is
      therefore small and mostly negative — the home must exist and be writable,
      and nothing of the operator's may be put in it. **US2 is smaller than
      drafted; do not pad it back out.**
      **(2) The agent cannot commit.** `git commit` in the worktree under that
      environment failed `Author identity unknown` (exit 128). FR-005 is a
      confirmed defect of the isolated home, not a precaution.
      **(3) The archive composes.** Re-probed with the worktree as cwd, the CLI
      wrote `<home>/.claude/projects/-tmp-…-worktree/<session-id>.jsonl`, 10,895
      bytes — the exact path `_archive_session` resolves from the child's
      `HOME`. FR-006 costs nothing to keep. T009 still asserts it by reading the
      archive, now as a regression guard rather than a discovery.
      Out of scope but found here and filed:
      `adapter/agent-model-window-unrecognized` — the CLI does not recognize the
      `ollama-cloud/*` aliases and assumes a 200k window with auto-compact on
      **every attempt the factory has ever run**, independent of this spec.
      Still owed at dispatch time: re-verify plan.md's reuse inventory against
      the implementer's worktree — that `PASSTHROUGH_ENV` still holds four
      names, that `_archive_session` still resolves from the child's `HOME`, and
      that `tests/test_workgraph_sweep.py`'s env assertion still pins the exact
      dict.
- [ ] T001a Operator, gating **US4 only**: probe `CLAUDE_CODE_MAX_CONTEXT_TOKENS`
      before that story dispatches. Run the adapter's own argv shape against a
      declared window that is unmistakably not the default — the same one-command
      bet T001 made, which paid for itself by shrinking US2. Record three things
      here as the gate's evidence: whether the CLI's unrecognized-model warning
      changes or disappears; whether the window it reports is the declared number;
      and whether an unset variable leaves behaviour exactly as it is today. If
      the variable does not do what the CLI's own warning message claims, **US4's
      mechanism is wrong and the story must not dispatch** — say so here and stop,
      rather than letting an agent discover it at attempt price. This gates US4
      alone; US1–US3 do not wait on it.

---

## Phase 2: User Story 1 — The agent's home belongs to the factory (Priority: P1) 🎯 MVP

**Goal**: a per-node home under `FACTORY_ROOT`, created before launch, written
into the child environment as a constructed value; the worker's home reaches
nothing.

**Independent Test**: `attempt_env` against a worker environment carrying a
populated `HOME` yields the factory's path; two nodes yield two paths; one node
retried yields one path; the directory exists before the agent launches.

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T002 [US1] Verify prerequisites in this worktree: `uv run pytest -q`
      green; `factory/workgraph/adapter.py`, `factory/workgraph/models.py` and
      `tests/test_workgraph_sweep.py` exist and plan.md's inventory claims hold
      — constitution II gate; STOP and report blocked if not satisfied.
- [ ] T003 [P] [US1] Write path-helper cases FIRST: the home resolves to
      `<factory_root>/homes/<epic>/<node>`, keyed like `worktree_path` and
      `pid_file` and *not* like `transcript_dir` (no attempt component); two
      nodes of one epic resolve to different directories; the same node resolves
      to the same directory across attempts — must fail.
- [ ] T004 [P] [US1] Write child-environment cases FIRST against `attempt_env`:
      given a worker environment whose `HOME` is a recognizable operator path
      (and which also carries `LITELLM_MASTER_KEY`, `TELEGRAM_BOT_TOKEN` and an
      unknown future credential), the built environment holds exactly
      `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, `PATH`, `HOME`, and the
      `HOME` value is the context's factory path; **no value in the result is a
      path under the operator's home**; `HOME` is present, not omitted (FR-002);
      `attempt_env` still takes exactly `(context, environ)` — must fail.
- [ ] T005 [US1] Write creation cases FIRST: the home exists by the time the
      agent is launched; a home that cannot be created raises `AdapterError`
      naming the path; the failure is never a fallback to the worker's home —
      must fail.

### Implementation for User Story 1

- [ ] T006 [US1] Implement the home: `home_path` in the "Paths on the worker
      host" block of `factory/workgraph/adapter.py`; the resolved path as a
      field on `AttemptContext` beside `worktree_path`
      (`factory/workgraph/models.py`); `"HOME"` removed from `PASSTHROUGH_ENV`
      and written in `attempt_env` from the context; creation in `run_attempt`
      beside the existing transcript-directory and pid-file preparation. Until
      T003, T004, T005 pass. `attempt_env` MUST NOT gain a `factory_root`
      parameter — see plan.md § US1, second trap.

---

## Phase 3: User Story 2 — The agent starts, works and is archived on that home (Priority: P1)

**Goal**: the seeded home starts the CLI non-interactively, the agent's own
commits succeed under the factory identity, and the attempt's evidence is
unchanged.

**Independent Test**: a stub-agent attempt on a factory-owned home produces a
transcript directory holding both artifacts; a `git commit` from inside the
worktree under the child environment succeeds with the factory's attribution.

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T007 [P] [US2] Write seeding cases FIRST, driven by T001's finding: the
      home contains exactly what the factory wrote and nothing else; every
      seeded file's content is derived from module constants; **the seeding
      function reads no path under the operator's home and takes no argument
      that could carry one** — the negative assertion is the point of this task
      (plan.md § US2, first trap). Include the case that would catch the
      shortcut: a seeded home must contain no `oauthAccount` key, no MCP server
      the factory did not write, and no instruction file whose content did not
      come from this module's constants. Assert **provenance, not absence** —
      today that means no `CLAUDE.md` at all, because the factory composes none,
      but a later spec that seeds a factory-authored briefing must be able to
      keep this test rather than delete it — must fail.
- [ ] T008 [P] [US2] Write git-identity cases FIRST: a commit made inside a
      fixture worktree under the child environment succeeds where it would
      otherwise fail for want of an identity, and the resulting commit's author
      and committer are `SALVAGE_AUTHOR_NAME`/`SALVAGE_AUTHOR_EMAIL` imported
      from `factory/workgraph/worktree.py`, not re-declared constants and not
      the operator's — must fail.
- [ ] T009 [US2] Write archive-composition cases FIRST, asserted by reading the
      directory rather than by inspecting a path expression: a completed
      stub-agent attempt whose session transcript was written under the
      factory-owned home yields a transcript directory containing both
      `stdout.log` and `<session-id>.jsonl`; an attempt that wrote no session
      transcript still yields `stdout.log` and no error; the archived copy
      survives the home's removal — must fail.

### Implementation for User Story 2

- [ ] T010 [US2] Implement seeding and identity in
      `factory/workgraph/adapter.py`, beside home creation, until T007, T008,
      T009 pass. If T001 found the CLI needs something the factory cannot
      legitimately fabricate, STOP and raise it as an operator question rather
      than copying from the operator's configuration.

---

## Phase 4: User Story 3 — The isolation is asserted, not reviewed (Priority: P2)

**Goal**: the credential sweep holds the new rule, and the docs record the
change together with the boundary it does not cross.

**Independent Test**: restoring `"HOME"` to `PASSTHROUGH_ENV` fails the suite
with a message naming the rule.

### Tests for User Story 3 (write FIRST, must fail)

- [ ] T011 [US3] Extend `test_the_virtual_key_is_read_into_exactly_one_
      environment_variable` in `tests/test_workgraph_sweep.py` rather than
      replacing it: keep both existing guarantees (the virtual key is read in
      exactly `{"attempt_env"}`; the built environment is exactly its documented
      names), and express the new one — the home in that environment comes from
      the context, and a worker `HOME` cannot reach the child. Add the
      structural half: `PASSTHROUGH_ENV` does not contain `"HOME"`, with a
      failure message that says *why*, so the next reader who adds it back
      learns the reason from the failure rather than from `git log` — must fail
      against the pre-US1 tree and pass after it.

### Implementation for User Story 3

- [ ] T012 [US3] Final sweep + docs: claim the decision-log number in
      `docs/decisions.md` (the agent's home is the factory's, keyed like its
      worktree), recording the per-node keying and the seed-from-constants rule;
      extend `docs/architecture.md`'s adapter section with the home and its
      lifetime. **Both must state the boundary** (FR-008): this isolates what an
      agent loads, not what an agent can reach — there is no filesystem sandbox,
      `--dangerously-skip-permissions` is unchanged, and `hardening/agent-sandbox`
      remains the open scope that confines the filesystem. Confirm no new
      dependency and no store.

---

---

## Phase 5: User Story 4 — A persona declares its model's context window (Priority: P2)

**Goal**: an optional per-persona `context_window` reaches the agent as
`CLAUDE_CODE_MAX_CONTEXT_TOKENS`, and changes nothing at all when undeclared.

**Independent Test**: `attempt_env` for a context whose persona declares a window
carries that number under the CLI's variable; for a persona declaring none, the
built environment is exactly what it is without this story.

### Tests for User Story 4 (write FIRST, must fail)

- [ ] T013 [P] [US4] Write registry cases FIRST in the existing config tests:
      `context_window` is accepted as an optional positive integer and lands on
      `Persona`; a zero, a negative, a float and a string are each refused with a
      message naming the persona and the field; the key is refused entirely on an
      `agent: none` persona; **and a persona declaring nothing yields `None`, not
      a default** — plan.md § US4's inventory names `_optional_timeout`
      (`factory/config.py:189`) and the `agent: none` rule (`:149-152`) as the
      shape to copy — must fail.
- [ ] T014 [P] [US4] Write carrier cases FIRST: `persona.context_window` reaches
      `AttemptContext.context_window` through the resolution in
      `factory/activities/agent_activities.py`, and an undeclared persona yields
      `None` there. **Do not copy `resolve_timeout_s`**: there is no node-level
      override, and nothing may raise on `None` — plan.md § US4 states why the
      timeout is not the template at this one step — must fail.
- [ ] T015 [US4] Write the environment cases FIRST against `attempt_env`,
      extending — not replacing — the assertion T011 leaves behind: a context
      carrying a window yields `CLAUDE_CODE_MAX_CONTEXT_TOKENS` equal to that
      number as a string; a context carrying `None` yields an environment whose
      key set is **exactly** the pre-US4 set, with the name absent rather than
      empty or zero (FR-010, SC-006); `attempt_env` still takes exactly
      `(context, environ)` — must fail.

### Implementation for User Story 4

- [ ] T016 [US4] Implement the field end to end until T013, T014 and T015 pass:
      `_OPTIONAL_FIELDS` and the validator in `factory/config.py`, the field on
      `Persona`, the fields on `ResolvedNode` and `AttemptContext`, the
      resolution in `factory/activities/agent_activities.py`, and the conditional
      emit in `attempt_env`. **Leave every persona in `personas.yaml`
      undeclared** — document the key in the header comment block beside
      `timeout` and set no value (plan.md § US4, third trap: there is no source
      for the real numbers and a guess that is too high is worse than today's
      assumption). **Introduce no alias-to-window table anywhere** (second trap;
      constitution VII).

---

## Dependencies & Execution Order

- Phase 1 is operator work and gates everything: T001's finding is FR-004's
  content, so dispatching US2 before it is answered would dispatch a story whose
  size is unknown. T001a gates US4 alone and nothing else.
- Phase 2 (US1) has no dependency and is the MVP seam: the home exists and the
  operator's stops reaching the child.
- Phase 3 (US2) imports US1's helper and edits the same module — **merged, not
  passed**.
- Phase 4 (US3) asserts what US2 establishes and edits the sweep and the docs —
  merged.
- Phase 5 (US4) adds a field beside US1's on `AttemptContext`, a name beside
  US1's in `attempt_env`, and a case to the sweep assertion US3 rewrites —
  **merged**, on US3.
- This is a chain, not a fan-out, and deliberately: all four stories converge
  on `factory/workgraph/adapter.py`, so there is no disjoint pair to dispatch
  concurrently. Do not run any two of these as siblings.

## Implementation Strategy

US1 alone banks most of the value: the moment `HOME` stops being passed through,
the operator's account, MCP servers and global instructions stop reaching every
agent — and it can be verified without running an agent at all. US2 is what
keeps the attempt working on the isolated home, and it is where the real risk
lives, which is why T001 resolves its central unknown before dispatch rather
than inside it. US3 is what stops the property being lost in a later diff about
something else. US4 is the cheapest of the four and the least related; if
anything is cut, cut that one — the factory has run with the 200k assumption
since its first epic and will survive another week of it.

Nothing here changes what an agent is asked to *do*: the prompt assembler, the
standards path, the gates and the judge are all untouched, and no routing
decision moves. US4 adds one optional field to the persona registry and changes
what an agent is *told about its own limits* — not which agent runs, or on what.
