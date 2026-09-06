# Tasks: the judge can look at what the story built

Read `plan.md` before starting. Trap 1 is the one that is not about code: this
spec adds an input to the judge, Principle VIII
(`.specify/memory/constitution.md:63`) says there is none beyond the diff and the
criteria, and it has been out of step with the tree since 116 landed the gate
results on 2026-08-31. The amendment is an operator act done before dispatch and
**no task here edits `.specify/memory/constitution.md`** — if your story seems to
need that edit, stop. Trap 2 is the shortest wrong fix in the tree: one `--binary`
flag at `factory/workgraph/worktree.py:1527` — `diff` would put a screenshot in
the diff and rewrite every prompt in the corpus. Trap 3 is the red that arrives
from the existing judge tests when the message type is widened for every message
instead of only for a prompt that carries a picture. Trap 4 is the red that
arrives from a file no story touches:
`tests/test_final_sweep.py:614` — `test_the_component_cannot_even_spell_a_cap`
fails on an identifier or string constant containing `budget`, `cap`, `quota`,
`breach` or `exceed`, and the declared `test` gate is the whole suite. Trap 7 is
the one that would waste US1: `factory/verify/judge.py:307` — `build_prompt` is
pure and takes bytes, never a path. Trap 9 is the one that would waste US2: a test
that hands artifact records straight to the assembler has re-tested US1 and proved
nothing about what a gate declared. Trap 11 is the one that reds the trunk: no
test may assert what this repository's own `personas.yaml` chose. Trap 14 is the
cheapest red to avoid and the worst to ship: every field this spec adds crosses a
Temporal payload boundary, and
`tests/test_temporal_payload_shape.py:629` — `test_every_boundary_field_has_a_default_or_is_allowlisted`
fails any that has no default. Trap 15 is the one that silently deletes the retry
ladder: the records travel through the library entry point
`factory/verify/judge.py:752` — `run_judge`, and the activity never calls the
assembler itself. Trap 16 is the one that would ship the inverse of this spec: a
subtraction with no floor hands `prepare_diff` a limit of zero and posts a judge a
picture with no code. Trap 17 is the one that lands green and reads false forever:
a field on `JudgeVerdict` that is not written into the store's two longhand codecs
round-trips as false on every stored row. Trap 18 is the assertion that cannot be
made true: the allowance shrinks by exactly the artifacts' bytes, the *rendered*
diff section does not, and a test written for the second number is a red no
production change can clear. Trap 19 is the one that arrives from another epic:
three drafts are queued against these same files.

The stories dispatch in the order US1, US4, US2, US3, and the phases below are in
that order. US4 is numbered fourth because it was cut out of US1 on sizing grounds
after the trio was written, and a story number is never reused.

Tests are written first and must fail before the implementation that satisfies
them — except the tasks marked **The control**, which assert non-regression and
are green from the first commit; do not manufacture a failure for those. Every
acceptance scenario is provable from the diff, which is all the judge sees;
runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — The prompt can carry a picture, and the picture is spent from the same allowance the text is

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001, FR-003, FR-009, trap 7) Given one
      artifact record carrying bytes, a declared type of `image`, a media type and
      its producing gate and declared path, assert the assembled `JudgePrompt`'s
      user message carries a list of typed blocks whose image block holds those
      bytes, that the text block immediately before it names the gate and the
      path, and that the system prompt constant
      (`factory/verify/judge.py:138`) states a shown artifact is evidence of the
      same standing as the gate results. Construct the record in the test — it
      takes bytes, never a path, and this test writes no file.
- [ ] T002 [P] [US1] (spec US1-S2, FR-007, trap 3) **The control, and the most
      important one in this phase.** Given no artifact records, assert the
      assembled object equals the one the same criteria, diff and gate results
      produce with the artifact argument absent — message shape included, so the
      user message's content is still the single string it is today. Every prompt
      comparison in the existing judge suite depends on this; if those tests go
      red, the design is wrong and the fixtures are not the thing to change.
- [ ] T003 [P] [US1] (spec US1-S3, FR-004) Given one artifact record carrying no
      bytes and a stated reason, assert the assembled text carries a line naming
      that gate, that path and that reason **and** that the content carries no
      image block for it. Both halves in one test: an assembler that simply
      dropped the record satisfies the second half alone.
- [ ] T004 [P] [US1] (spec US1-S4, FR-005, traps 16 and 18) Given a diff built to
      assemble just inside `DIFF_INPUT_LIMIT` with no artifact record beside it,
      assert that prompt's `truncated_input` is false, that the same diff
      assembled with one artifact record carrying bytes has it true, and that the
      second prompt's artifacts section and diff section together are within
      `DIFF_INPUT_LIMIT`. Copy the shape from
      `tests/test_116_judge_sees_gates.py:385` — `test_the_gate_section_is_spent_from_the_diffs_own_allowance`
      and
      `tests/test_116_judge_sees_gates.py:406` — `test_the_gate_section_and_the_diff_together_stay_under_the_input_limit`,
      including their diff-building helper. **Do not assert that the rendered diff
      section is exactly N bytes shorter** — it is not, on any natural fixture
      (trap 18). If you want the exact number, assert it on the limit handed to
      `factory/verify/judge.py:473` — `prepare_diff` through a spy, never on the
      text that comes back.
- [ ] T005 [US1] (spec US1-S5, FR-022, trap 16) Given artifact records whose
      assembled blocks together measure more than the artifacts section's total
      bound, and a diff long enough to be abridged, assert the records past the
      bound carry no image block and assemble as text lines naming it, that the
      assembled image blocks together are within the bound, and that **the
      assembled diff section is not empty**. Three assertions in one test; the
      third is the one that fails on an implementation with only the subtraction,
      because `factory/verify/judge.py:500` — `prepare_diff` grants every section
      zero without complaining. Not `[P]`: it shares T004's accounting fixture.

### Implementation for this story

- [ ] T006 [US1] (FR-001, FR-002, trap 7) Widen the message field at
      `factory/verify/judge.py:285` — `JudgePrompt` so a user message's content may
      be a list of typed blocks in the shape the path at
      `factory/verify/judge.py:111` accepts, and add the pure artifact record
      `factory/verify/judge.py:307` — `build_prompt` will take: producing gate,
      declared path, declared type, media type, and either bytes or nothing plus a
      stated reason. The record takes **bytes**; do not give it a path, and do not
      open one anywhere in this module.
- [ ] T007 [US1] (FR-003, FR-004, FR-009) Assemble the artifact section: a named
      heading and a named preamble constant of their own, modelled on the ones at
      `factory/verify/judge.py:197` and `factory/verify/judge.py:202` and named for
      the same two reasons their docstring gives; one image content block per
      record carrying bytes, preceded by a text block naming its gate and path; one
      text line per record carrying none, naming its gate, path and reason. Extend
      the system prompt at `factory/verify/judge.py:138` with the sentence FR-009
      requires, in the register of the paragraph it already makes about gate
      results.
- [ ] T008 [US1] (FR-005, FR-022, traps 4, 16 and 18) Subtract the artifact
      blocks' encoded size from the allowance handed to
      `factory/verify/judge.py:473` — `prepare_diff`, on the same basis
      `gate_bytes` is measured at
      `factory/verify/judge.py:345` — `build_prompt` — **and bound the whole
      section first**, by a named constant well under `DIFF_INPUT_LIMIT`
      (`factory/verify/diffbounds.py:47`), on the per-gate model
      `factory/verify/judge.py:218` uses: a record whose block would carry the
      running total past the bound assembles as a text line naming it, in
      declaration order. Without the bound a large enough picture hands
      `prepare_diff` a limit of zero and the judge is posted no diff at all
      (trap 16). The subtraction is exact on the allowance and not on what comes
      back (trap 18). Name the new locals and both constants with `limit` or
      `bound`:
      `tests/test_final_sweep.py:614` — `test_the_component_cannot_even_spell_a_cap`
      fails the whole suite on `budget`, `cap`, `quota`, `breach` or `exceed` in an
      identifier, a keyword or a string constant, and docstrings are the only
      exemption (`tests/test_final_sweep.py:602` — `code_words`).

### Verification for this story

- [ ] T009 [US1] Paste, as committed evidence, the assembled prompt for a run with
      one shown artifact and for the same run with none — the second showing the
      single-string content unchanged. **Elide both large halves**: paste the image
      block's media type, its byte length and a hash where the base64 payload was,
      and paste the diff section as its heading, its byte length and its first and
      last three lines. A pasted prompt that still carries the payload is a
      screenshot committed as evidence, and a pasted prompt that still carries the
      diff section is up to 64 KiB of text spending the same bound the code does
      (D-050, `factory/verify/diffbounds.py:47`). State the two diff-section byte
      lengths and the two `truncated_input` values as numbers: that is the whole of
      what T004 compares.

## Phase 2: User Story 4 — `image` is a declarable type, and the row says whether the judge was shown one

### Tests for this story (write FIRST, must fail)

- [ ] T010 [P] [US4] (spec US4-S1, FR-008) Given a v2 manifest declaring an
      artifact whose type is `image`, assert it parses and the parsed
      configuration carries that type, **and** that the same manifest with the
      type spelled `picture` is refused with the entry named. The pair, because
      the accepting half alone passes on a reader that takes any string.
- [ ] T011 [P] [US4] (spec US4-S2, FR-006) Given a prompt that assembled at least
      one image block and one that assembled none, assert the parsed
      `JudgeVerdict` carries the shown flag true and false respectively, following
      the argument at `factory/verify/models.py:594` — `JudgeVerdict`.
- [ ] T012 [P] [US4] (spec US4-S3, FR-020, trap 15) Given artifact records
      carrying bytes handed to `factory/verify/judge.py:752` — `run_judge` over a
      stubbed transport, assert that the verdict returned for a readable response
      **and** the verdict returned for an unreadable one both carry the shown flag
      true. The pair in one test: the first fails when the entry point drops the
      records before `factory/verify/judge.py:798` — `run_judge`, the second fails
      when the malformed-response construction at
      `factory/verify/judge.py:836` — `run_judge` omits the flag, and only the
      pair catches both.
- [ ] T013 [P] [US4] (spec US4-S4, FR-021, trap 17) Given a `JudgeVerdict`
      carrying the shown flag true, assert it survives a write-and-read through the
      evidence store, **and** that a stored document whose payload has no such key
      decodes carrying it false. Go through
      `factory/verify/store.py:1238` — `_judge_to_dict` and
      `factory/verify/store.py:1261` — `_judge_from_dict`, not through the
      in-memory record: a field added to the dataclass and not to those two
      longhand codecs passes every other test in this phase and reads false on
      every row forever.

### Implementation for this story

- [ ] T014 [US4] (FR-008) Add `image` to the artifact-type enum 134 defines in
      `factory/verify/models.py` beside
      `factory/verify/models.py:241` — `CacheDeclaration`, and to nothing else.
      **Then read 134's landed reader in `factory/verify/factory_yaml.py` before
      deciding whether it needs an edit**: if it validates a declared type against
      that enum, widening the enum is the whole change and the reader keeps
      refusing an unknown type with no edit; if it spells the four type names a
      second time, widen it there too. T010 is the test that answers this either
      way, and plan.md § Sizing states both outcomes.
- [ ] T015 [US4] (FR-006, trap 14) Carry the shown flag on `JudgePrompt`,
      true exactly when at least one image block was assembled — read off the
      assembled blocks and never off the argument, the way
      `factory/verify/judge.py:405` — `build_prompt` reads `gates_shown` — and
      through the keyword arguments at
      `factory/verify/judge.py:597` — `parse_verdict` onto
      `factory/verify/models.py:576` — `JudgeVerdict` as a plain bool defaulted
      false, beside `factory/verify/models.py:609` — `JudgeVerdict`. US1's control
      — the prompt assembled with the artifact argument absent must still equal
      the one assembled with no records — has to stay green through this: a prompt
      that assembled no image block carries the flag false either way, and its
      content is still one string.
- [ ] T016 [US4] (FR-020, trap 15) Give
      `factory/verify/judge.py:752` — `run_judge` the artifact-records argument,
      defaulted to none exactly as `gate_results` is at
      `factory/verify/judge.py:760` — `run_judge`; forward it to `build_prompt` at
      `factory/verify/judge.py:798` — `run_judge`; and carry the assembled prompt's
      shown flag onto **both** verdicts, beside `gates_shown` at
      `factory/verify/judge.py:822` — `run_judge` and again at
      `factory/verify/judge.py:836` — `run_judge`. Both, for the reason the comment
      at `factory/verify/judge.py:833` — `run_judge` already gives about gate
      results: what the judge was shown is a fact about the ask, and an ask that
      produced garbage was still made with, or without, the picture. Nothing in
      this task reads a file — the bytes arrive as an argument, and US2 is what
      fills it.
- [ ] T017 [US4] (FR-021, trap 17) Write the flag into the evidence store's
      verdict codec by hand, beside `gates_shown`: the key at
      `factory/verify/store.py:1257` — `_judge_to_dict` and the read with an absent
      key defaulting to false at
      `factory/verify/store.py:1281` — `_judge_from_dict`. Two lines, and they are
      not optional: the codec is longhand for the reason its own docstring at
      `factory/verify/store.py:1286` — `_contradiction_to_dict` gives, and a field
      that skips it round-trips as false on every row while every in-memory test
      stays green. Spec 132 adds its own field to these same two functions; expect
      a one-line conflict if both epics run at once (trap 19).

### Verification for this story

- [ ] T018 [US4] Paste, as committed evidence, the stored verdict row for one
      attempt judged with an artifact record carrying bytes and for one judged with
      none — the flag's two values as they come back out of the store, not as they
      were set in memory — and the parsed manifest fragment showing the `image`
      artifact declared. Fields and lengths only: no payload, no diff section.

## Phase 3: User Story 2 — Only a declared picture reaches the model, only when the judge can be shown one

### Tests for this story (write FIRST, must fail)

- [ ] T019 [P] [US2] (spec US2-S1, FR-010, traps 10 and 11) Given three synthetic
      registries written by the test — one declaring vision on a persona that runs
      an agent, one omitting the key, one declaring it on a persona whose agent is
      the deterministic one — assert the first parses carrying the declaration, the
      second parses carrying its absence, and the third is refused with the field
      named. Copy `tests/test_config.py:55` — `_entry` and
      `tests/test_config.py:309` — `test_context_window_loads_as_positive_integer`
      for the first two and
      `tests/test_config.py:345` — `test_deterministic_persona_with_a_context_window_is_rejected`
      for the third.
      **Do not assert anything about this repository's own `personas.yaml`**:
      `tests/test_122_registry_is_not_pinned.py:372` — `test_no_assertion_about_the_shipped_registry_constrains_a_vendor_or_route`
      reds the trunk for it, and the trunk is every node of every epic.
- [ ] T020 [P] [US2] (spec US2-S2, FR-011, FR-012) Given a judge persona resolved
      from a registry entry declaring vision, assert the returned
      `factory/workgraph/models.py:295` — `ResolvedPersona` carries it, that one
      decoded from a payload written without the field carries its absence, and
      that the value reaches
      `factory/activities/verify_activities.py:399` — `RunJudgeInput` rather than
      stopping at the resolver.
- [ ] T021 [US2] (spec US2-S3, FR-013, traps 9 and 15) Given a `GateResult`
      carrying one `GateArtifact` declared `image` and recorded present, whose
      stored location is a real file holding known bytes, and a judge persona
      declaring vision, assert the record handed to
      `factory/verify/judge.py:752` — `run_judge` carries exactly those bytes and a
      media type derived from the declared path's suffix. Assert on the entry
      point's argument, through a stub or a spy on that function — that is what
      fails an activity which assembled its own prompt instead — and on the bytes
      themselves, which is what fails a pass-through that never opened the file.
      Build the fixture from a `GateResult`, never by constructing the assembler's
      record directly: that is US1's test and it is already green.
- [ ] T022 [US2] (spec US2-S4, FR-014, trap 9) Given the same gate results and a
      judge persona that does **not** declare vision, assert every record handed to
      the entry point carries no bytes and a reason naming the persona declaration.
      Give the artifact a stored location that does **not** exist: that is how "the
      file is never opened" is proven from the diff, and an implementation that
      reads first and discards afterwards raises instead of passing. Not `[P]`: it
      shares T021's fixture module.
- [ ] T023 [US2] (spec US2-S5, FR-013, traps 4 and 12) Given four artifacts
      declared `image` — one recorded present whose stored file is larger than the
      per-artifact show-limit, one recorded present and stored a single byte below
      it, one 134 recorded with its true size and **no stored location at all**,
      and one 134 recorded **not present** — assert the four records handed to the
      entry point are, in declaration order, one carrying no bytes and a reason
      naming that limit, one carrying its bytes, one carrying no bytes and a reason
      naming that the bytes were never stored, and one carrying no bytes and the
      "not written" reason; and assert the on-disk sizes after the call, so a
      truncating implementation fails. The third case fails an implementation
      treating an unstored artifact as absent, and it is only constructible because
      this spec's show-limit sits strictly below 134's storage bound (trap 12).
      Spell the limit and its message with `limit` or `bound`; "exceeds" is
      gate-red (trap 4).
- [ ] T024 [US2] (spec US2-S6, FR-013, FR-016) **The control.** Given gate results
      carrying declared artifacts of every type other than `image`, and no artifact
      of type `image` declared at all, assert the entry point is handed no record
      whatsoever and that the resulting prompt equals the one the same criteria and
      diff assemble with the artifact argument absent. Every repository that
      declares no picture is this test, which is why it is the control and why it
      is green from the first commit. The declared-but-not-written picture is
      **not** this case — it is T023's fourth record, and it assembles a text line
      (FR-004), so a prompt carrying it is not the no-artifact prompt.

### Implementation for this story

- [ ] T025 [US2] (FR-010, trap 10) Add the optional vision declaration to the
      persona registry: register the name in the optional-field tuple at
      `factory/config.py:152`, parse it to `bool | None` with a helper modelled on
      `factory/config.py:350` — `_optional_context_window`, refuse it for a
      deterministic persona beside `factory/config.py:298` — `_build_persona`, and
      pass it to the constructor beside `factory/config.py:326` — `_build_persona`.
      `bool | None` and not `bool`: a `False` default gives the deterministic
      refusal nothing to test. Document the field at `personas.example.yaml:19`
      beside `context_window`, and leave `personas.yaml` alone.
- [ ] T026 [US2] (FR-011, trap 14) Add the defaulted field to
      `factory/workgraph/models.py:295` — `ResolvedPersona`, following
      `factory/workgraph/models.py:320` — `ResolvedPersona`'s own default and the
      reason its docstring gives for one, and fill it from the registry entry at
      `factory/activities/agent_activities.py:370` — `resolve_persona`,
      `factory/workgraph/workflow.py:1267` — `_resolve` and
      `factory/workgraph/workflow.py:1285` — `_resolve`.
- [ ] T027 [US2] (FR-012, traps 8 and 14) Add one bool to
      `factory/activities/verify_activities.py:399` — `RunJudgeInput`, defaulted
      absent, and fill it from the resolved judge persona at
      `factory/workgraph/workflow.py:2923` — `_score`. One bool and nothing else:
      the bytes may not travel on this payload and workflow code may not read them.
      Defaulted, and not added to the allowlist at
      `tests/test_temporal_payload_shape.py:443` — a payload written before this
      spec carries no such key, and an allowlist entry would say its absence must
      stay loud when in fact its absence is the answer.
- [ ] T028 [US2] (FR-013, FR-014, FR-015, traps 4, 8, 12 and 15) Between
      `factory/activities/verify_activities.py:430` — `run_judge` and
      `factory/activities/verify_activities.py:444` — `run_judge`, turn the
      request's gate results into the records the library entry point now takes:
      skip every declared artifact whose type is not `image`; for each that is,
      read the stored bytes only when the persona declared vision, the record says
      present **with a stored location**, the declared path's suffix is in a named
      closed media-type set, and the stored size is within the named show-limit —
      otherwise emit a record carrying no bytes and the reason. A stored location
      that cannot be read emits a withheld record naming the read failure and never
      raises: an unreadable file costs a note in the prompt, not the attempt. Hand
      the records to `factory/verify/judge.py:752` — `run_judge` on the parameter
      US4 added, at `factory/activities/verify_activities.py:444` — `run_judge`;
      **do not call the assembler from here** — that skips the completion, the
      malformed-response RETRY and the contradiction re-ask the entry point owns
      (trap 15). Name the show-limit and the reason strings with `limit` or
      `bound`, and set the show-limit strictly below 134's storage bound (trap 12).

### Verification for this story

- [ ] T029 [US2] Paste, as committed evidence, the artifact records the activity
      produced for one attempt under a vision-declaring judge persona and for the
      same attempt under one that declares none — reasons included — and the
      registry refusal text for the deterministic case. Paste the records' fields,
      never their bytes: a record's byte length and media type, never the payload.

## Phase 4: User Story 3 — A criterion about the built artifact is admissible

### Tests for this story (write FIRST, must fail)

- [ ] T030 [P] [US3] (spec US3-S1, FR-017, trap 6) Given a target repository whose
      manifest declares an `image` artifact at a path, and a spec whose Then-clause
      carries one of the refused phrasings while its scenario names that declared
      path, assert the clause is admitted, **and** that the same spec validated
      against a target repository whose manifest declares no `image` artifact is
      still refused. The pair, because the admitting half alone passes on a checker
      that stopped refusing anything.
- [ ] T031 [P] [US3] (spec US3-S2, FR-018) Given a target repository declaring an
      `image` artifact and a clause whose scenario names neither that artifact nor a
      declared gate, assert the refusal names a third remedy — declare a picture on
      a gate and name its path — beside the two at
      `factory/cli/nouns/spec.py:1605` — `_evidence_refusal`.
- [ ] T032 [P] [US3] (spec US3-S3, FR-018, trap 6) **The control.** Given a target
      repository whose manifest declares no `image` artifact, assert the refusal
      text is character-for-character the text it is today. Pin the string:
      operators have it in their runbooks, and every repository in the world is this
      test until it declares a picture.
- [ ] T033 [P] [US3] (spec US3-S4, FR-019) Given a target repository declaring
      `image` artifacts, assert the emitted evidence document names those declared
      artifacts beside the declared gates it names today at
      `factory/cli/nouns/spec.py:1685` — `as_dict`.

### Implementation for this story

- [ ] T034 [US3] (FR-017, FR-019) Carry the declared `image` artifacts on
      `factory/cli/nouns/spec.py:1539` — `_Declarations` beside the gate set
      documented at `factory/cli/nouns/spec.py:1548` — `_Declarations`, filled from
      the same `load_factory_config` call at
      `factory/cli/nouns/spec.py:1559` — `_declared_gates`, and admit at
      `factory/cli/nouns/spec.py:1830` — `_check_evidence` a marked clause whose
      scenario names one of those paths — a third admission beside
      `factory/cli/nouns/spec.py:1513` — `_names_a_declared_gate`, counted as
      provable rather than borderline. Add the artifacts to the emitted document at
      `factory/cli/nouns/spec.py:1685` — `as_dict`. Read the module before you
      start: spec 133 is a queued draft that restructures this whole file, and if
      it lands first every line number in this phase has moved (trap 19).
- [ ] T035 [US3] (FR-017, FR-018, trap 6) Add the third remedy to
      `factory/cli/nouns/spec.py:1588` — `_evidence_refusal`, conditioned on the
      manifest declaring at least one `image` artifact. **Remove no entry from
      `factory/cli/nouns/spec.py:1440`** — in particular not
      `factory/cli/nouns/spec.py:1454`, which is the one that makes the failing
      example pass and would admit every unprovable clause in every repository.
      If you find yourself editing that tuple, the design is wrong.

### Verification for this story

- [ ] T036 [US3] Paste, as committed evidence, the validate output for one spec
      against two target repositories differing only in whether their manifest
      declares the `image` artifact — the admitted run and the refused one — and
      the refusal text for a repository that declares none, unchanged.

## Verification

- [ ] T037 The full gate command passes green.
- [ ] T038 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end. Step 1 comes before dispatch, not after: it is
      the Principle VIII amendment and its `docs/decisions.md` entry, and no gate
      can check it. Step 2 is the re-validate after 134, 133 or 136 lands, and it
      is the only thing that catches the anchor drift those three cause in the
      files this trio points into. Step 5 — dispatching with the judge persona's
      vision declaration removed and confirming the row says the picture was not
      shown — is the falsifiable test of this whole spec, because the failure it
      was written from is twelve stories, four gates and a judge all reading green
      on a product nobody had looked at.
