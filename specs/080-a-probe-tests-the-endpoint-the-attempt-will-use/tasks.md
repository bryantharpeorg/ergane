# Tasks: a probe tests the endpoint the attempt will use

Read `plan.md` before the first task. Four traps decide whether an attempt lands.
Trap 3 (**two variables assigned from one source is not FR-002**) is the one that
produces a diff which passes every other scenario and comes apart at the next
edit. Trap 4 (**the existing suite fakes the very seam under test at
`tests/test_controlplane_llm_probe.py:172`, and a from-scratch fake client fakes
it a second way**) is the one that produces a green test file proving nothing:
any double for the admin client must *subclass*
`factory/usage/litellm_client.py:108` — `LiteLLMClient`, or US1-S5 and US1-S1's
before-transcript are satisfied by a diff that changed no production line. Trap 2 (**`factory/controlplane/verify.py:560-566` is
the only completion path production takes**, because the real client defines no
`chat_completion`) is the one that produces a fix which works in the suite and
not on a host. Trap 12 (**the probe cannot know the config file's path**) is the
one that sends a US2 implementer either into a protocol change across 43 call
sites or into the `resolve_config_path()` call FR-007 forbids; what a detail
names is the source the resolution carries.

Two more traps exist because a review found tasks here asking for the impossible.
Trap 15 (**`factory/controlplane/verify.py:544` renders on no input**) is why
T016 drives six branches and not seven. Trap 16 (**the new sibling is one
function with two bindings**) is why T004 says "by name in every module that
binds it" rather than "one `setattr`". Both were written after an earlier version
of this file sent an implementer hunting for something that is not there.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the judge
sees; runtime evidence is committed as pasted output, never described and never
demonstrated by a revert.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — The probe mints where the attempt will run

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001, trap 4) In
      `tests/test_080_us1_probe_mints_where_the_attempt_runs.py`, gather the probe
      against a declaration naming gateway A **and the credential variable
      `ERGANE_LLM_MASTER_KEY`**, with `LITELLM_PROXY_URL` naming gateway B and
      `LITELLM_MASTER_KEY` holding a different value, and assert that both the
      key-management client and the completion request address B, that nothing
      addresses A, **and that both authenticate with the resolved credential
      (`LITELLM_MASTER_KEY`) rather than the declared one**. Record the base URL
      **and the `Authorization` header** of every request each half issues. FR-001
      has two clauses and only the address one was ever asserted here: pick a
      `master_key_env` the environment does not name, or the credential clause is
      untested and a diff that leaves `api_key_env` bound at
      `factory/controlplane/verify.py:433` passes. Do **not** patch
      `factory/controlplane/verify.py:168` — `_llm_client_factory`, and do **not**
      substitute a from-scratch fake client: the double MUST subclass
      `factory/usage/litellm_client.py:108` — `LiteLLMClient` (so
      `factory/usage/litellm_client.py:136` — `from_env` still runs the real
      resolution on the before-run), or be the real class handed an `httpx`
      transport. Extend the loopback double at
      `tests/test_controlplane_verify.py:320` — `_loopback_llm_listener` to record
      the base URL **and the `Authorization` header** of every request rather than
      writing a second five-endpoint admin double; its header loop at
      `tests/test_controlplane_verify.py:343-354` keeps `Content-Length` and drops
      everything else today, which is why no existing test can see the credential
      half of this scenario.
- [ ] T002 [P] [US1] (spec US1-S2, FR-003, trap 1) **The control against the
      opposite error.** With a declaration naming gateway A and neither
      `LITELLM_PROXY_URL` nor `LITELLM_MASTER_KEY` set — cleared with
      `monkeypatch.delenv(..., raising=False)`, because no probe-level test can
      hand the resolver a mapping (trap 5) and the gate's own shell exports both
      (`scripts/ergane-env.sh:72-73`) — assert both halves address A and read the
      credential variable the declaration names. A fix that reads the declaration everywhere inverts the
      defect; `factory/controlplane/resolve.py:334` — `_resolve_endpoint` is where
      the order is written down.
- [ ] T003 [P] [US1] (spec US1-S3, FR-003, trap 11) **The second control, and the
      one that covers every real install.** With the declaration and the
      environment agreeing on the address and on the credential variable, pin the
      snapshot's detail string character-for-character against what today's tree
      produces for the same inputs, and record that both halves addressed the one
      agreed gateway. US1 changes no rendered text, so if this pin has to move for
      **US1** to pass, US1 is wrong. Name US2 in the test's own comment as the
      story that will move it (trap 11), so the next reader does not take a red
      bar there for a regression.
- [ ] T004 [P] [US1] (spec US1-S4, FR-002, trap 3, trap 16) Replace **one
      function — the new `llm_gateway_for` sibling — by name in every module that
      binds it**, answering gateway C, then assert two things in one test: that the key-management client and the completion request
      both address C, and that `factory/controlplane/resolve.py:137` —
      `resolve_llm_gateway` now answers C too. The first half proves neither half
      of the probe re-derives the address from the parsed declaration; the second
      half is the only criterion covering FR-002's structural clause, and a diff
      that adds the sibling while leaving `resolve_llm_gateway` writing its own
      `GatewayResolution` fails it. Do not claim this test discriminates against
      two reads of the same function — replacing the one function moves both of
      those too; US1-S1 is what catches a half that reads the declaration.
      **How many `setattr` lines that takes is a consequence of T007 and T008, not
      a criterion** (trap 16): under the from-import shape at
      `factory/controlplane/verify.py:32` the one function holds two bindings and
      you patch both — still one symbol replaced — while a module-qualified call in
      `verify.py` needs one. Do not weaken the second assertion to whichever single
      patch you tried first.
- [ ] T005 [P] [US1] (spec US1-S5, FR-007, trap 13) Parse a config from a file
      that is **not** the default path, with a different gateway declared in the
      file at the default path, then construct `LLMProbe()` and await `gather` on
      that parsed config — copying the *shape* at
      `tests/test_controlplane_llm_probe.py:207-208` and **not** that file's autouse
      fixture at `tests/test_controlplane_llm_probe.py:172` — and assert both halves
      address the gateway the parsed declaration names. Make the test fail if
      `resolve_config_path` is consulted during the probe at all:
      `factory/controlplane/resolve.py:412` is the fallback that makes a second read
      a different file. **This criterion is vacuous unless the admin client's double
      subclasses `factory/usage/litellm_client.py:108` — `LiteLLMClient`** (trap 4):
      a fake with its own `from_env`, or a patched `_llm_client_factory`, never
      reaches `resolve_config_path` on today's tree either, so the test would pass
      before the change. Paste it failing against today's tree, with the consult
      recorded, so a vacuous version is visible in the diff. Do **not** drive
      `factory/controlplane/verify.py:1198` — `verify_controlplane_async` here; it
      runs all eight probes in `factory/controlplane/verify.py:1183-1192` and the
      host-probe meta-test at `tests/test_controlplane_host_probe.py:277-306`
      records why that is a hazard.
- [ ] T006 [P] [US1] (spec US1-S6, FR-008, trap 5) **The third control.** Build a
      client through `factory/usage/litellm_client.py:136` — `from_env` with
      `LITELLM_PROXY_URL` naming gateway B and assert its `base_url` is B, so the
      probe's new construction path is shown not to have been bought by changing the
      constructor six call sites in five other modules depend on. `from_env` takes
      only `transport` and `timeout` and FR-008 forbids widening it, so set the
      variable with `monkeypatch.setenv` and clear `LITELLM_MASTER_KEY` with
      `monkeypatch.delenv(..., raising=False)` first; never rely on the operator's
      shell, which `scripts/ergane-env.sh:72-73` has already exported into.

### Implementation for this story

- [ ] T007 [US1] (FR-002, FR-003, trap 5) Add a sibling to
      `factory/controlplane/resolve.py:137` — `resolve_llm_gateway` that takes an
      already-parsed declaration and returns a `GatewayResolution`, with an
      `environ=` parameter and a `source=` parameter, exactly as
      `factory/controlplane/resolve.py:252` — `temporal_target_for` does. Then
      rewrite `resolve_llm_gateway` so its last statement is a call to it — the
      shape `factory/controlplane/resolve.py:232` — `resolve_temporal_target`
      already has at `factory/controlplane/resolve.py:249`. Move no branch inside
      `factory/controlplane/resolve.py:334` — `_resolve_endpoint` or
      `factory/controlplane/resolve.py:347` — `_resolve_credential`.
- [ ] T008 [US1] (FR-001, FR-007, trap 1) Change
      `factory/controlplane/verify.py:168` — `_llm_client_factory` to build the
      admin client from that resolution, applied to the declaration it was already
      handed, instead of calling `from_env` at
      `factory/controlplane/verify.py:175`.
      `factory/controlplane/verify.py:192-193` is the same move already made for
      Temporal, and `_DECLARED_SOURCE` at `factory/controlplane/verify.py:46` is
      the source label to pass — a label, not a path (trap 12).
- [ ] T009 [US1] (FR-001, trap 6) Change
      `factory/controlplane/verify.py:432-434` to read the address and the
      credential variable from the same resolution. Resolve the *names* there; read
      the credential's value no earlier than today does, so
      `factory/controlplane/verify.py:437-443`'s "X is not set" answer survives
      instead of becoming `probe failed unexpectedly`. Rebinding `base_url` here
      is also what makes the *address* correct at all seven message sites below;
      leave their text alone, it is US2's (FR-005).
- [ ] T010 [US1] (FR-008, trap 2) Leave `factory/usage/litellm_client.py:136` —
      `from_env` alone, and leave its call sites outside
      `factory/controlplane/verify.py` untouched. There are six, in five modules,
      enumerated in plan.md § Sizing — check them rather than counting from
      `from_env`'s own docstring at `factory/usage/litellm_client.py:144-147`,
      which says "five" and is stale.
      `factory/usage/litellm_client.py:118` — `__init__` already accepts `base_url`
      and `master_key` directly (`factory/usage/litellm_client.py:118-133`), so no
      new constructor is needed; if you add one anyway, say why in the diff.
- [ ] T011 [US1] (trap 7) Leave the five-step key sequence at
      `factory/controlplane/verify.py:467-537` untouched, including the `finally`
      at `factory/controlplane/verify.py:528-537`.

### Verification for this story

- [ ] T012 [US1] (spec US1-S1) Paste, as committed evidence, both recordings of
      the disagreeing configuration, each carrying the address **and the
      credential** every request went out with: the run against today's tree
      showing the mint at B under the resolved `LITELLM_MASTER_KEY` and the
      completion at A under the declared `ERGANE_LLM_MASTER_KEY`, and the run after
      the change showing both at B under the resolved credential.
      The before-run is what makes the fix legible to a reader holding only the
      diff (trap 10).
- [ ] T013 [US1] (spec US1-S2, spec US1-S3) Paste, as committed evidence, the two
      controls — declaration-only, and declaration-and-environment-agreeing — with
      the pinned detail string shown unchanged by US1.
- [ ] T014 [US1] (spec US1-S5, spec US1-S6) Paste, as committed evidence, the
      non-default-config-path gather naming the parsed file's gateway, and the
      `from_env` characterisation showing the six other call sites unaffected.

## Phase 2: User Story 2 — A verdict names the endpoint and the source that chose it

**Depends on US1 having merged** (`depends_on_merged`). Both stories edit
`factory/controlplane/verify.py`. Two things are already true when this phase
starts, and neither is a reason to skip work: US1 has bound `base_url` to the
resolved address, so every message already names the address the call was issued
to and what FR-005 still wants is the **source** beside it; and US1's pinned
detail test will go red the moment T019 lands, which is expected, is not a
regression, and is T022's job to update (trap 11).

### Tests for this story (write FIRST, must fail)

- [ ] T015 [P] [US2] (spec US2-S1, FR-004, trap 12) In
      `tests/test_080_us2_probe_names_the_endpoint_it_used.py`, assert a passing
      probe's detail names the gateway address that answered and the source the
      resolution carries for it. `factory/controlplane/resolve.py:120` —
      `GatewayResolution` already carries both the address and that source; it does
      not carry a file path and neither does the probe, so assert on the variable
      name or the declaration label — never on a path. Today's passing text at
      `factory/controlplane/verify.py:523-526` names neither.
- [ ] T016 [P] [US2] (spec US2-S2, FR-005) Fail the key-management call against the
      address the resolution chose while a different address is declared, and assert
      the failure detail contains the address the call was issued to **and** the
      source that chose it, and does **not** contain the other address. The address
      half is already true after US1, so a test that asserts only the address
      passes on US1's diff alone and proves nothing; the source assertion is what
      makes this scenario fail before T020. Then **parametrise it over the six
      reachable sites**, driving each branch and asserting the source clause at
      every one: `issue_key` raising reaches
      `factory/controlplane/verify.py:625` — `_classify_key_failure` (a
      404-flavoured message for `factory/controlplane/verify.py:637` and any other
      for `factory/controlplane/verify.py:641`); `get_key_info` raising reaches
      `factory/controlplane/verify.py:493`; a spend-log failure reaches
      `factory/controlplane/verify.py:519`; an `httpx.TimeoutException` on the
      completion reaches `factory/controlplane/verify.py:577`; any other completion
      exception reaches `factory/controlplane/verify.py:582`. **Do not write a
      seventh case.** `factory/controlplane/verify.py:544` renders on no input —
      trap 15 traces every assignment — and the driver an earlier version of this
      task named for it, "an unconstrained key with no detail", is not one: an
      unconstrained key sets the message at
      `factory/controlplane/verify.py:500-504`, which names no gateway address and
      is outside FR-005. T020 still edits :544's source clause and the diff is what
      proves it. Four scenarios reaching three sites is how the old five-site
      enumeration shipped two messages nobody had touched (trap 8).
- [ ] T017 [P] [US2] (spec US2-S3, FR-009) With `LITELLM_PROXY_URL` naming an
      address the declaration does not carry, assert the detail states that the
      variable overrode the declaration and names both the variable that won and
      the declaration label the probe passed in — when the environment wins,
      `factory/controlplane/resolve.py:334` — `_resolve_endpoint` answers
      `EndpointRef(override, PROXY_URL_ENV)`, so the resolution carries only the
      variable's name and the declaration label is the `source=` argument.
- [ ] T018 [P] [US2] (spec US2-S4, FR-006) With the resolved credential variable
      holding `sk-must-not-be-printed`, assert that neither a passing detail nor a
      failing one contains that value and that both name the variable.
      `factory/controlplane/resolve.py:78` — `CredentialRef` exists so a rendering
      carries the name and never the value.

### Implementation for this story

- [ ] T019 [US2] (FR-004, FR-009, trap 12) Render the resolved address and its
      source into the probe's detail, including the passing text at
      `factory/controlplane/verify.py:523-526`, and say when the environment
      overrode the declaration. The source is
      `GatewayResolution.base_url_source`: the variable's name when the variable
      won, the label the probe passed when the declaration won. Update the comment
      at `factory/controlplane/verify.py:44-45` — *"Nothing renders it"* — in the
      same diff, because this task makes it false.
      `factory/controlplane/verify.py:662` — `evaluate` and
      `factory/controlplane/verify.py:1230` — `render_findings` need no change:
      the detail string is the whole surface.
- [ ] T020 [US2] (FR-005, trap 8) Carry the source beside the address at all
      **seven** message sites: `factory/controlplane/verify.py:493`,
      `factory/controlplane/verify.py:519`,
      `factory/controlplane/verify.py:544`,
      `factory/controlplane/verify.py:577`,
      `factory/controlplane/verify.py:582`, and the two reached through the
      `base_url` parameter of
      `factory/controlplane/verify.py:625` — `_classify_key_failure` at
      `factory/controlplane/verify.py:637` and
      `factory/controlplane/verify.py:641`. US1 already made the *address* right
      at every one of them by rebinding `base_url` at
      `factory/controlplane/verify.py:432`; do not go looking for an address bug
      here and do not claim one in the PR. What changes is the text and, for the
      last two, the signature that carries the source into the helper — fixing the
      caller at `factory/controlplane/verify.py:486` covers both.
      `factory/controlplane/verify.py:544` is edited like the other six and is the
      one site no test drives: it renders on no input (trap 15), so the diff is its
      only evidence and T016 must not grow a case for it.
- [ ] T021 [US2] (FR-006, trap 9) Print variable names, never credential values,
      and leave three regions exactly as they are, because all three belong to spec
      132: the `hasattr` guard at `factory/controlplane/verify.py:556` (132's
      FR-003 defines `chat_completion` on
      `factory/usage/litellm_client.py:108` — `LiteLLMClient` and flips that guard
      true), the `LLMAliasResult` construction at
      `factory/controlplane/verify.py:585-591` (132's FR-009), and the `finally` at
      `factory/controlplane/verify.py:528-537` including the `aclose()` at
      `factory/controlplane/verify.py:535` (132's FR-010 restructures the client's
      lifetime there; trap 7 forbids you touching it from this side).
- [ ] T022 [US2] (spec US2-S1, FR-004, trap 11) Update the pinned detail string in
      `tests/test_080_us1_probe_mints_where_the_attempt_runs.py` to the text T019
      now produces, showing the old and the new string in the same diff and
      asserting nothing else in that test moved. This is US2 legitimately editing
      a file US1 owns, and it is the only such edit permitted. Weakening FR-004's
      rendering to keep the old pin green, or deleting the pin instead of updating
      it, are both wrong.

### Verification for this story

- [ ] T023 [US2] (spec US2-S1, spec US2-S3) Paste, as committed evidence, a
      passing report showing the address and the source, and a second one taken
      with `LITELLM_PROXY_URL` set, showing the override clause.
- [ ] T024 [US2] (spec US2-S2) Paste, as committed evidence, a failing report
      showing that the address it names is the address the call was issued to and
      that the source is named beside it, with the declared address absent.
- [ ] T025 [US2] (spec US2-S4) Paste, as committed evidence, a report rendered
      with the credential variable holding a recognisable value, showing the value
      absent and the variable's name present.

## Verification

- [ ] T026 The full gate command passes green.
- [ ] T027 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end. Step 1 — two servers, two access logs, one of
      them empty afterwards — is the falsifiable test of this whole spec, because
      it is the configuration that reported "minted, constrained and revoked" about
      a gateway it never called on 2026-08-20. Step 3 is a direct call, not a
      flag: `ergane install` has no `--config`, and the divergence FR-007 closes
      is latent until some caller hands a non-default path.
