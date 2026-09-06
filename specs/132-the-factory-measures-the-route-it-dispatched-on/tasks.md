# Tasks: the factory measures the route it dispatched on

Read `plan.md` before starting. Five traps decide whether this spec is worth
anything.

Trap 1 is the one that makes a wrong fix look right in two opposite directions:
the response's `model` may echo the alias it routed under, so comparing it to the
requested alias agrees with itself always; and the gateway's declaration lives in
a different namespace (`hosted_vllm/qwen3-coder-30b` against `judge-primary`), so
comparing those raw disagrees on every healthy alias. The rule that survives both
is FR-016 — a finding only when the answered model matches neither the declared
upstream nor the alias itself.

Trap 3 is the one that decides how US1 is built: `chat_completion` is called by
three production paths and implemented by no client in this tree — only by test
fakes. "Reuse the existing probe" means implementing that one method, not lifting
a nested closure out of the doctor. Defining it repairs one of those three call
sites, flips a `hasattr` branch onto a client the doctor has already closed
(which is FR-010), and turns the canary's `AttributeError` into a use-after-close
that this spec does **not** fix and must not claim to.

Trap 15 is the one that decides where US3's code goes:
`factory/activities/verify_activities.py:493` — `record_verification` has no
credential, no gateway address and a committed sweep forbidding it from naming
the master key. The `/model/info` read happens in the judge activity, where
`virtual_key` and `proxy_url` already arrive as data.

Trap 16 is the one that decides what US2 is recording: the attempt row's
`model_alias` is the implementer rung's and the answered model comes from the
judge's completion. They are two different requests and this floor's own registry
gives them two different models.

Trap 18 is the one that decides whether US3 is worth building at all: its
`/model/info` read runs on the judge's per-attempt virtual key, and nothing in
this tree establishes that such a key is shown `litellm_params`. FR-017 turns an
unrecognised payload into silence, and all five of US3's scenarios run through
doubles, so a US3 that can never fire in production still passes every test and
the judge. The operator establishes the premise before US3 dispatches (plan
§ Verification, step 6) and the diff commits the payload it produced.

Tests are written first and must fail before the implementation that satisfies
them. A test that is green before the diff proves nothing — trap 17 is the
worked example of one — so check each new test is red for the reason the story
names, not for a fixture that happens to be missing.

Every acceptance scenario is provable from the diff, which is all the judge sees;
runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — Preflight exercises what will serve

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001, FR-002, trap 4) Given a fake gateway
      that advertises alias `a` in `/v1/models` and answers `POST
      /chat/completions` for it with a 500, assert the preflight returns a failing
      finding whose text names the alias, the gateway address the completion was
      posted to, the proxy's own refusal words, and the fact that nothing was
      dispatched. **Placement, for T001–T007:** write them into the existing
      `tests/test_predispatch_landing_preflight.py`, beside the parity test T015
      extends, rather than opening a new module. Plan § Sizing measures this story
      at roughly 45 KB against the 64 KiB deterministic refusal
      (`factory/verify/diffbounds.py`, `DIFF_INPUT_LIMIT`), evidence included, and
      a new module's imports, fixtures and scaffolding are the cheapest way to
      spend headroom on nothing.
- [ ] T002 [P] [US1] (spec US1-S2, FR-001) **The control.** Given a fake gateway
      that advertises and serves every gateway-routed alias the graph names,
      assert the fake recorded one completion per alias and the preflight returned
      no finding for any of them. Asserting the recorded calls is what keeps this
      control from passing on a diff that added nothing.
- [ ] T003 [P] [US1] (spec US1-S3, FR-004, trap 8) **The control.** Given a graph
      naming a persona that does not route through the gateway, assert the fake
      recorded no completion for that persona's alias.
      `factory/workgraph/preflight.py:835` — `aliases_to_check` already filters on
      `factory/config.py:208` — `routes_through_gateway`, which drops deterministic
      personas as well as subscription ones; this asserts the property is not lost.
- [ ] T004 [P] [US1] (spec US1-S4, FR-005) Given one fixture graph and one fake,
      assert each preflight surface's alias findings are the ones
      `factory/workgraph/preflight.py:857` — `check_aliases` returned: equal across
      the two dispatch surfaces the existing parity test already compares —
      `factory/activities/roadmap_activities.py:662` — `preflight_spec` and
      `factory/cli/nouns/build.py:359` — `_run_preflight` — and present unchanged
      in `factory/workgraph/cli.py:141` — `_run_preflight`. Do not assert the three
      *whole* lists are equal: two surfaces drop informational findings
      (`factory/activities/roadmap_activities.py:665-667`) and the third does not,
      and the roadmap's list also carries assembly findings.
- [ ] T005 [P] [US1] (spec US1-S5, FR-006, trap 5) **The control.** Given an alias
      the proxy does not advertise at all, assert today's declaration-based
      refusal still fires and the fake recorded no completion for it — one outage,
      one finding.
- [ ] T006 [P] [US1] (spec US1-S6, FR-007, trap 5) Given a fake gateway that
      refuses every request, assert the findings returned are exactly the **two**
      transport findings this function returns today — `model-aliases-served` from
      `factory/workgraph/preflight.py:876` — `check_aliases` and
      `first-attempt-key-aliases` from `factory/workgraph/preflight.py:914` —
      `check_aliases`, each worded as it is today — and that the probe added no
      third. Read the code before you write the assertion: the two reads are
      independent and the docstring at `factory/workgraph/preflight.py:860` —
      `check_aliases` says so deliberately. A test asserting "exactly one finding"
      is red for a reason no diff in this story can cause, and the cheapest way to
      make it green is to delete the key-list arm — which this spec never asked
      for.
- [ ] T007 [P] [US1] (spec US1-S7, FR-008, trap 6) Given a graph naming four
      served gateway-routed aliases, assert four completions were recorded and
      that they overlapped — hold the fake's first completion on a barrier until
      the fourth request has arrived, and assert the four still return. Do not ask
      the test to assert `asyncio.gather` itself: a test cannot see a call
      structure without reading source, and the diff is where the judge reads it.
- [ ] T008 [P] [US1] (spec US1-S8, FR-009, trap 3) Given the doctor's per-alias
      probe answering with a payload whose `model` differs from the requested
      alias, assert the result carries the payload's `model`, and carries **the
      empty string, not `None`**, when the payload reports none.
      `factory/controlplane/verify.py:585` — `_probe_one_alias` sets `model=alias`
      today; the field is `str | None` on `factory/controlplane/verify.py:80` —
      `LLMAliasResult`, so `None` would satisfy a looser reading and would be
      indistinguishable from a field nobody set. Nothing under `factory/` reads
      that field, so no consumer breaks.
- [ ] T009 [P] [US1] (spec US1-S9, FR-010, traps 3 and 17) **The regression this
      seam causes, proved with a double that can fail.** Write a double whose
      `aclose()` marks it closed and whose later `chat_completion` raises
      `RuntimeError("Cannot send a request, as the client has been closed.")` —
      httpx's own wording, and deliberately not an `httpx.HTTPError`, because
      `factory/usage/litellm_client.py:409` — `_call` catches only that. Given a
      gateway that serves the alias, assert `factory/controlplane/verify.py:428` —
      `gather` reports the alias completed. Do **not** reuse
      `tests/test_controlplane_llm_probe.py:81` — `_AliasRecordingLLMClient` or
      `tests/test_controlplane_llm_probe.py:302` —
      `_RefusingForOneAliasLLMClient`: their `aclose()` is `pass`, so the
      assertion is green today and stays green after a diff that changes nothing.
      Assert the outcome — a served alias completes — not which branch ran.
- [ ] T010 [P] [US1] (spec US1-S9, FR-010, trap 3) **The real-transport half of
      the same scenario.** `tests/test_controlplane_verify.py:1147` —
      `test_verify_llm_gather_against_live_double` builds the real client through
      `from_env` against a loopback listener and asserts `finding.passed is True`;
      its docstring says "the client has no chat_completion path, so the gather
      falls back to httpx — that is the code path being exercised here". FR-003
      makes that sentence false and this test red. Keep the assertion, rewrite the
      docstring to name the path now taken, and commit that reversal as the
      evidence that the closed client was fixed rather than worked around.

### Implementation for this story

- [ ] T011 [US1] (FR-003, FR-008, traps 3 and 6) Add one `chat_completion` method
      to `factory/usage/litellm_client.py:108` — `LiteLLMClient`, implemented
      through `factory/usage/litellm_client.py:409` — `_call` so a status ≥ 400
      arrives as a `LiteLLMError` carrying the proxy's own scrubbed message from
      `factory/usage/litellm_client.py:445` — `_proxy_message`. This is the method
      `factory/cli/install.py:375` — `_async_probe_one_token` and
      `factory/controlplane/canary/probe.py:261` — `judge_canary` already call and
      no client defines. `_call` takes no timeout and the client's is fixed at
      `factory/usage/litellm_client.py:128` — `__init__`, so give the probe a
      per-request timeout here rather than inheriting the admin client's 30s. Write
      no comment claiming the canary is repaired: its caller closed the client at
      `factory/controlplane/canary/probe.py:208` — `probe_judge_canary` before
      `factory/controlplane/canary/probe.py:220` — `probe_judge_canary` uses it,
      which is a separate open key and out of scope.
- [ ] T012 [US1] (FR-001, FR-002, FR-006, FR-007, FR-008, trap 5) Inside
      `factory/workgraph/preflight.py:857` — `check_aliases`, probe the aliases the
      `/v1/models` read confirmed served, concurrently, and turn a refusal into a
      failing `PreflightFinding`. Probe nothing when that read failed, and nothing
      for an alias it did not advertise. Leave both existing transport arms and
      their wording untouched. `factory/workgraph/preflight.py:131` —
      `PreflightFinding` has no severity field: do not add one, and do not use
      `passed=True` to soften a failure — that value means informational.
- [ ] T013 [US1] (FR-009, FR-010, traps 3 and 17) In
      `factory/controlplane/verify.py:585` — `_probe_one_alias`, carry the
      payload's own `model` onto the result instead of the requested alias, using
      the empty string when the payload names none. Then fix the lifetime:
      `factory/controlplane/verify.py:535` — `gather` closes the client before
      `factory/controlplane/verify.py:594` — `gather` runs the probe loop, and
      httpx raises `RuntimeError`, which `_call` does not catch and
      `_probe_one_alias`'s bare `except Exception` turns into `completed=False` for
      every alias. Whatever shape you choose must still close the client on the
      **early return** at `factory/controlplane/verify.py:539` — `gather`, which
      leaves before the loop whenever the key-management probe failed: moving the
      `aclose()` below the loop leaks it there. A second client for the probe loop,
      closed in its own `finally`, cannot leak on either exit.
- [ ] T014 [US1] (trap 4) Teach `tests/conftest.py:119` — `FakeLiteLLM` a
      `POST /chat/completions` route, defaulting to serving every alias it
      advertises, with an explicit lever for the dead-upstream case and a barrier
      T007 can hold the first completion on. `tests/conftest.py:262` — `_handle`
      returns 404 for it today, and every existing preflight test drives this fake
      — four test modules name a preflight entry point through it directly and
      seventeen import it, so run the whole suite before calling this done.
- [ ] T015 [US1] (FR-005) Confirm by reading that none of the three call sites
      needs an edit — all three call `check_aliases` directly — and extend the
      existing parity test,
      `tests/test_predispatch_landing_preflight.py:460` —
      `test_both_dispatch_surfaces_return_the_same_findings`, rather than writing
      a second one.

### Verification for this story

- [ ] T016 [US1] Paste, as committed evidence, exactly three short transcripts, a
      handful of lines each with alias lists elided — the plan's § Sizing bounds
      this story at three and the diff limit is measured with evidence included
      (D-050). (1) The preflight refusing against a proxy that advertises an alias
      whose upstream is stopped, and passing once it is back — the exact state
      observed on this host on 2026-09-03. (2) The same preflight against a
      stopped proxy, showing the two transport findings and no third. (3)
      `ergane doctor`'s LLM probe before and after, each run preceded by the
      one-line `hasattr(LiteLLMClient, "chat_completion")` print, reporting the
      same aliases completing in both. The third is the operator-visible proof of
      FR-010; `tests/test_controlplane_verify.py:1147` —
      `test_verify_llm_gather_against_live_double` is the committed one.

## Phase 2: User Story 2 — The attempt records what answered

### Tests for this story (write FIRST, must fail)

- [ ] T017 [P] [US2] (spec US2-S1, FR-011, FR-012, trap 16) Given a judge
      completion issued under the judge's alias `judge-primary` whose response
      payload reports `model: "qwen3-coder-30b"`, on an attempt whose routing
      dispatched the implementer under `ollama-cloud/kimi-k2.7-code`, assert the
      row's answered column carries `qwen3-coder-30b`, the verdict on that row
      carries `judge-primary`, and the row's own `model_alias` still carries
      `ollama-cloud/kimi-k2.7-code`. The answered model belongs beside
      `factory/verify/models.py:608` — `JudgeVerdict`'s alias, not beside
      `factory/verify/models.py:946` — `VerificationResult`'s, which
      `factory/workgraph/workflow.py:2688` — `_verify` fills from the routing.
- [ ] T018 [P] [US2] (spec US2-S2, FR-013, trap 13) **The control that matters.**
      Given a response payload reporting no `model` field, assert the answered
      column holds the empty string and is not the requested alias. A field that
      falls back to the request can never disagree with it, which is the tautology
      this spec exists to delete.
- [ ] T019 [P] [US2] (spec US2-S3, FR-014, trap 13) Given an attempt with no judge
      verdict at all — the implementer route, whose CLI adapter surfaces no
      response body — assert the answered column is stored as SQL NULL and reads
      back as the unobserved sentinel, and assert that value is not equal to the
      empty string T018 asserts. Two facts, two values.
- [ ] T020 [P] [US2] (spec US2-S4, FR-012, FR-014, trap 12) Given a verification
      store written before this feature, assert the column is added in place, its
      pre-existing rows read back as the unobserved sentinel, and the migrated
      store's column order equals a fresh store's. `factory/verify/store.py:711` is
      zipped positionally by `factory/verify/store.py:1031` — `_result_from_row`: a
      divergent order does not raise, it hands every field of every row to the
      wrong attribute.
- [ ] T021 [P] [US2] (spec US2-S5, FR-014, traps 12 and 13) **The control that
      keeps a judge outage from recording a false fact.** Given the
      `JudgeOutcome.UNAVAILABLE` verdict `factory/workgraph/workflow.py:2942` —
      `_score` builds when the judge activity raised — a verdict assembled from an
      error message, holding no response body — assert the answered column is the
      unobserved sentinel and not the empty string. Then, separately, assert the
      verdict survives its own JSON round trip through
      `factory/verify/store.py:1238` — `_judge_to_dict` and
      `factory/verify/store.py:1261` — `_judge_from_dict`, and that a stored
      verdict written before this spec — a dict with no such key — reads back as
      the sentinel rather than raising `KeyError`. Build that second fixture by
      hand from a dict, not by round-tripping through the new writer, or the test
      cannot fail.

### Implementation for this story

- [ ] T022 [US2] (FR-011, FR-014, traps 11 and 13) Carry the payload's `model` out
      of `factory/verify/judge.py:982` — `_assistant_content` and
      `factory/verify/judge.py:955` — `_complete` onto the `JudgeVerdict` the judge
      activity returns, beside the `model_alias` it already carries. Four sites
      build that verdict and they split two and two. The two that hold a body set
      the value — `factory/verify/judge.py:653` — `parse_verdict` and the
      malformed-response arm at `factory/verify/judge.py:826` — `run_judge` — using
      the empty string when the payload named none. The two that hold none must
      leave the unobserved sentinel standing: `factory/workgraph/workflow.py:2942`
      — `_score`'s `JudgeOutcome.UNAVAILABLE` verdict, and
      `factory/verify/store.py:1261` — `_judge_from_dict` rebuilding an old row.
      Default the field on `factory/verify/models.py:608` — `JudgeVerdict` to the
      sentinel, never to `""`, so the outage path cannot silently claim a body
      answered. The value must ride out of the activity as data: the row is built
      in workflow code, which may not read a response.
- [ ] T023 [US2] (FR-012, FR-013, FR-014, traps 12 and 16) Add the answered field
      to `factory/verify/models.py:946` — `VerificationResult` with a sentinel
      meaning unobserved, set it in `factory/verify/models.py:998` —
      `compose_result` from the verdict it already receives, and leave that
      function's `model_alias` argument exactly as it is. Then five store edits,
      not four: append the column last in the fresh DDL, append it last in
      `factory/verify/store.py:640` — `_migrate` keyed off `PRAGMA table_info`, add
      it to the `_RESULT_COLUMNS` tuple at `factory/verify/store.py:711` in the
      same position, write it in `factory/verify/store.py:971` — `_result_values`
      with the sentinel stored as NULL the way `factory/verify/store.py:1024` —
      `_result_values` already does for `model_alias`, and read it back in
      `factory/verify/store.py:1031` — `_result_from_row`. The fifth is the
      verdict's own codec in the same file: write the field in
      `factory/verify/store.py:1238` — `_judge_to_dict` and read it in
      `factory/verify/store.py:1261` — `_judge_from_dict` **with a default** —
      `data.get(...)`, the way `factory/verify/store.py:1281` — `_judge_from_dict`
      reads `gates_shown` — because `factory/verify/store.py:1275` —
      `_judge_from_dict`'s hard `data["model_alias"]` is the shape that raises
      `KeyError` on every row written before this spec.

### Verification for this story

- [ ] T024 [US2] Paste, as committed evidence, one attempt row dumped from the
      verification store showing the implementer's `model_alias`, the judge's
      alias and an answered model that differs from both, and one pre-migration
      row reading back as unobserved. A row dump, not a transcript: the diff limit
      is measured with evidence included.

## Phase 3: User Story 3 — A disagreement is a finding, not a silence

### Tests for this story (write FIRST, must fail)

- [ ] T025 [P] [US3] (spec US3-S1, FR-015, FR-016, trap 1) Given an attempt whose
      answered model is `llama-3.1-8b`, whose judge completion was issued under
      alias `judge-primary`, and a gateway declaring that alias's upstream as
      `hosted_vllm/qwen3-coder-30b`, assert a finding is reported naming the alias,
      the answered model and the declared upstream. The answered name is neither of
      the two names that alias is allowed to answer with, which is the only shape
      that can be a mis-route rather than an echo. **Assert the key literal**
      `verify/an-alias-answered-with-a-model-its-gateway-does-not-declare` — not a
      substring, not a prefix — and then assert a second, differently mis-mapped
      alias files under that same literal. `factory/doctor/store.py:137` — `report`
      upserts `ON CONFLICT (key)` and increments `occurrences`, so a key built from
      the alias mints a parallel row per mis-mapped alias and the recurrence count
      never rises above one; two aliases in this test is what makes that
      unbuildable. The alias and the two model names belong in `refs` and `notes`.
- [ ] T026 [P] [US3] (spec US3-S2, FR-015, FR-017, trap 1) **The control that
      keeps this off every healthy attempt.** Given an answered model of
      `qwen3-coder-30b` against a declared upstream of
      `hosted_vllm/qwen3-coder-30b`, assert no finding is reported: the two differ
      only by the provider prefix the declaration carries.
- [ ] T027 [P] [US3] (spec US3-S3, FR-016, FR-017, trap 1) **The control that
      keeps the tautology out one layer down.** Given an answered model equal to
      the issuing alias string itself while the declared upstream differs, assert
      no finding is reported. A proxy echoing the requested alias has told us
      nothing the request did not already say.
- [ ] T028 [P] [US3] (spec US3-S4, FR-017, trap 15) **The control.** Given an
      unobserved answered model, and separately a `/model/info` read that fails or
      times out so no declaration is held, assert no finding is reported, the
      verdict is returned unchanged and the attempt row is still written. Absence
      of evidence must not be filed as evidence of mis-routing, and this check must
      never be able to break a recording or a verdict.
- [ ] T029 [P] [US3] (spec US3-S5, FR-015, trap 16) **The control that proves the
      comparison uses the right alias.** Given an attempt whose judge alias
      (`ollama-cloud/glm-5.3`) and implementer alias (`ollama-cloud/kimi-k2.7-code`)
      name different models — this repository's own registry, `personas.yaml:271`
      and `personas.yaml:324` — and an answered model agreeing with the judge
      alias's declared upstream, assert no finding is reported. Compared against
      the row's `model_alias` this fires on every attempt on this floor.

### Implementation for this story

- [ ] T030 [US3] (FR-015, FR-017, traps 1, 2 and 15) Read the upstream the gateway
      declares for the alias that issued the completion, **in the judge activity,
      not on the recording path**. `factory/activities/verify_activities.py:430` —
      `run_judge` holds `factory/activities/verify_activities.py:420` —
      `RunJudgeInput`'s `virtual_key` and `proxy_url`, the same pair
      `factory/verify/judge.py:942` — `_complete` authenticates the completion
      with; `factory/activities/verify_activities.py:493` — `record_verification`
      holds neither, its input is only a result and a path
      (`factory/activities/verify_activities.py:467` — `RecordVerificationInput`),
      and `tests/test_verification_sweep.py:790` —
      `test_this_component_never_names_the_master_key` forbids that module from
      spelling `LITELLM_MASTER_KEY` at all. Read `/model/info` the way
      `factory/discovery/llm_enrichment.py:137` — `_fetch_litellm_model_info` does,
      but not through `factory/discovery/llm_enrichment.py:228` —
      `_records_from_litellm`, which looks the alias up as a top-level key and
      never reads `litellm_params` — the field the upstream actually lives in.
      Bound it: one attempt, no retry, a timeout no longer than the judge's, and a
      failure returns the verdict unchanged. Carry the declared upstream out on the
      verdict beside the answered model, adding it to
      `factory/verify/models.py:608` — `JudgeVerdict` and to both sides of its
      codec (`factory/verify/store.py:1238` — `_judge_to_dict` and
      `factory/verify/store.py:1261` — `_judge_from_dict`, the read side
      defaulted). **The credential is `virtual_key`, and trap 18 is why that
      matters.** It is a per-attempt virtual key, not the gateway master key that
      `factory/discovery/llm_enrichment.py:52` — `enrich_aliases` requires and
      refuses to run without (`factory/discovery/llm_enrichment.py:75` —
      `enrich_aliases`, and the "no credential to reach gateway metadata" detail at
      `factory/discovery/llm_enrichment.py:83` — `enrich_aliases`). Whether such a
      key is shown `litellm_params` at all is a fact the operator establishes
      before this story dispatches, in plan § Verification step 6; write the
      normalisation against the payload that step produced and pasted, and if it is
      not in the diff, stop and say so rather than inventing a shape. Do **not**
      improvise a second source when the field is missing: reaching for the spend
      log trap 18 names is a re-cut of FR-015 and an operator decision, and a
      silent fallback here is exactly the check that passes every test and never
      fires.
- [ ] T031 [US3] (FR-016, FR-017, traps 15 and 16) In
      `factory/activities/verify_activities.py:493` — `record_verification`,
      compare the two strings the verdict now carries — the answered model against
      the declared upstream of `factory/verify/models.py:608` — `JudgeVerdict`'s
      `model_alias`, never the row's — and report only when the answered model
      matches neither that upstream (provider prefix aside) nor the alias itself.
      Write it through `factory/doctor/store.py:137` — `report`, following the
      best-effort shape at `factory/workgraph/detector.py:636` —
      `_persist_finding`: a store that is gone leaves the row written and the
      finding unreported. No network call belongs in this function.

### Verification for this story

- [ ] T032 [US3] Paste, as committed evidence, four short blocks and no dumps:
      (1) the live `GET /model/info` response for the alias under test — **that one
      entry only, with `api_key` and `api_base` redacted**, because the whole
      payload advertises nineteen aliases with a full parameter block each, which
      is tens of KB against the 64 KiB refusal and carries upstream credential
      material into git; (2) the live completion payload this comparison was built
      against, showing its `model`; (3) the finding raised by a deliberately
      mis-mapped alias, key literal included; and (4) the silence for a correctly
      mapped one. Plan § Sizing bounds this story's evidence exactly here — it is
      the one way a story this small in code gets refused for size.

## Verification

- [ ] T033 The full gate command passes green.
- [ ] T034 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end. Step 2 — `ergane doctor` before and after — is
      the operator-visible proof of FR-010's closed client, beside the committed
      one at `tests/test_controlplane_verify.py:1147` —
      `test_verify_llm_gather_against_live_double`; run both. Step 4 — stopping an
      upstream while leaving the proxy running — is the falsifiable test of the
      preflight half, the condition that was live on this floor while the spec was
      written and that today's preflight passes cleanly; step 5, stopping the proxy
      itself, is the control that this spec did not trade a wasted ladder for a
      doubled refusal, and it expects **two** transport findings, not one. Step 6
      happens **before** US3 is dispatched, not after. Step 8 confirms what this
      spec deliberately did not fix: the canary failing with a closed-client
      `RuntimeError` rather than an `AttributeError`.
