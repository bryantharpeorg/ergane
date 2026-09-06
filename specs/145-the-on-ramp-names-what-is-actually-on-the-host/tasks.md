# Tasks: the on-ramp names what is actually on the host

Read `plan.md` before starting. Five traps decide whether this spec is worth its
dispatch. Trap 4: the tree's own comment at
`factory/controlplane/config.py:41-42` says managed Temporal is refused, and it
is wrong — believing it produces a README sentence that is newly false and passes
every guard here. Trap 1: the README guard is **four** edits, and an implementer
who makes one leaves a test that passes forever on a page nobody edits. Trap 11:
fixing the scanner alone makes the interview scenario pass for the wrong reason,
because the default candidate order already puts the gateway first. Trap 14: a
landed test asserts the classification enum has exactly two members, so US3's
first production line turns a committed test red in a module nothing else in this
spec points at. Trap 16 is that same shape arriving in US1: a fenced `bash` block
added to `README.md` above `README.md:83` turns
`tests/test_113_us2_docs_drift.py:91` —
`test_readme_procedure_matches_shipped_profile` red with a message about the
AppArmor profile, and that module may not be edited to repair it.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the judge
sees; runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — The page names the Temporal server, and cannot lose it again

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-003, traps 1 and 2) Add a Temporal entry to
      `tests/test_readme.py:199-207` and a check inside
      `tests/test_readme.py:210` — `missing_readme_concepts` that reads the
      **prerequisites** slice (`"## What you must already have"` up to
      `"## Installing Ergane"`), then add a mutation to
      `tests/test_readme.py:301` — `_mutations` so
      `tests/test_readme.py:387` — `test_missing_concept_is_detected` sweeps it.
      Write the required token sets the way the seven existing checks do —
      `tests/test_readme.py:189` — `_lower_words` splits `temporal.mode` into
      `temporal` and `mode`, so a set naming `temporal.mode` can never match.
- [ ] T002 [P] [US1] (spec US1-S2, FR-001, FR-002) Assert that
      `missing_readme_concepts` reports nothing missing for the committed
      `README.md` — the half that fails until the prose exists, so the guard and
      the page cannot land separately. `tests/test_readme.py:291` —
      `test_the_page_states_all_required_concepts` is that assertion for the
      existing seven and turns red the moment T001's entry lands without T005's
      prose; satisfy this task by pointing at it rather than by writing a second
      copy of it.
- [ ] T003 [P] [US1] (spec US1-S3, FR-003, trap 1) Add a **rewording** of the new
      Temporal prose inside `tests/test_readme.py:396` —
      `test_reworded_equivalent_page_passes`. This is the edit that gets skipped,
      and it is the one that stops the guard being a literal-string match.
- [ ] T004 [P] [US1] (spec US1-S5, FR-005) **The control — expected to pass on
      its first run, unlike every other task in this section.** In
      `tests/test_controlplane_config.py`, modelled on
      `tests/test_controlplane_config.py:122` — `test_happy_parse`, assert that a
      config declaring `temporal.mode = "managed"` parses and that the parsed
      `Temporal` carries `mode == "managed"`. It is green the moment it is
      written because 119 already removed the parse-time refusal, and
      `tests/test_supervision_managed_temporal.py:131` —
      `test_temporal_managed_mode_parses_without_refusal` is 119's own proof of
      exactly that. Do not hunt for why it is not red: its job is to pin the
      sentence T007 corrects to the behaviour that sentence describes, in the
      parser's own module, so the two cannot drift apart a fourth time. Measured
      at `602a92c` that module contains no occurrence of `managed`. Do not delete
      or move 119's test.

### Implementation for this story

- [ ] T005 [US1] (FR-001, FR-002, traps 2, 3 and 4) Add the prerequisite to
      `README.md` **inside** the section beginning at `README.md:17` and ending
      at `README.md:97` — that line is the `## Installing Ergane` heading, the
      closing boundary, so the prose goes above it. State that a reachable
      Temporal server is required
      because the control plane refuses a config with no `[temporal]` block
      (`factory/controlplane/config.py:437`), and name both ways to have one: an
      external server declared `temporal.mode = "external"` with an address, and
      the engine's own, declared `temporal.mode = "managed"` and written as a
      systemd user unit by `ergane worker install`
      (`factory/supervision/units.py:495-497`, reached from
      `factory/cli/nouns/worker.py:53`). Managed is **live**, not refused — do
      not repeat the stale comment. Cite no tilde-prefixed path in a backtick:
      `tests/page_holds_true.py:388` — `extract_paths` resolves such a span
      against the repository root and `tests/test_readme.py:107` —
      `test_every_path_the_file_cites_exists` then fails on it. Name no spec
      number anywhere in the prose — say what managed mode does, never that it
      "landed with 042" — or `tests/test_readme.py:140` —
      `test_the_file_names_no_spec_status` refuses the page. And add **no fenced
      `bash` block above `README.md:83`** (trap 16):
      `tests/test_113_us2_docs_drift.py:53` — `_extract_readme_procedure` reads
      the page's first such block and `tests/test_113_us2_docs_drift.py:91` —
      `test_readme_procedure_matches_shipped_profile` fails when it is not the
      AppArmor one, with a message naming the profile rather than this paragraph.
      Name `ergane worker install` in inline backticks the way `README.md:70`
      already does, or open the fence with `toml`, or put a `bash` fence below
      `README.md:92`. Do **not** edit `tests/test_113_us2_docs_drift.py` to make
      it pass; no hunk of this story's diff may land there.
- [ ] T006 [US1] (spec US1-S4, FR-004) Confirm by running the page's own three
      sweeps, each of which is a different asserter: `tests/test_readme.py:50` —
      `test_every_command_the_file_names_parses` for the invocations,
      `tests/test_readme.py:107` — `test_every_path_the_file_cites_exists` for
      the cited paths, and `tests/test_readme.py:140` —
      `test_the_file_names_no_spec_status` for the silence about status. The path
      sweep does not read commands and the command sweep does not resolve paths,
      so naming only one of them leaves half the criterion unasserted.
      `tests/page_holds_true.py:258` — `_is_command_shaped` keeps a span only when
      it has at least two words, no leading `-`, and none of `/`, `=` or `.` in
      the joined span, so `temporal.mode = "managed"` is excluded three times
      over, but `ergane worker install` is extracted and must parse. Then
      confirm the fourth asserter, which lives in another module:
      `tests/test_113_us2_docs_drift.py:91` —
      `test_readme_procedure_matches_shipped_profile` still extracts a procedure,
      which it does only while the page's first fenced `bash` block is the
      AppArmor one at `README.md:83` (trap 16). Two more page-level guards exist
      that this criterion does not bind — `tests/test_readme.py:123` —
      `test_the_file_contains_no_secret_value` and `tests/test_readme.py:156` —
      `test_the_file_names_no_spend_figure` — so do not read the four named here
      as `tests/test_readme.py`'s whole guard.
- [ ] T007 [US1] (FR-005, trap 4) Rewrite the comment at
      `factory/controlplane/config.py:41-42` so it states what `managed` does now
      — the engine installs and supervises a Temporal server of its own — instead
      of that it is refused. Do **not** delete
      `factory/controlplane/config.py:69`; it is a stable rule slug named by
      `docs/decisions.md`, and removing it is a wider act than this story.
      Do **not** touch `tests/test_ergane_install_walkthrough.py:137` (trap 5):
      it is a labelled historical transcript inside a module docstring, not an
      assertion.

### Verification for this story

- [ ] T008 [US1] Paste, as committed evidence, two things, both produced inside
      the worktree: the output of `grep -c -i temporal README.md` before and
      after the change, and the unit names a managed layout **generates** —
      build an `InstallLayout` with `temporal_mode="managed"` the way
      `tests/test_supervision_managed_temporal.py:84` — `managed_layout` does,
      hand it to `factory/supervision/units.py:473` — `generated_files`, and
      paste the resulting names with `ergane-temporal.service` among them.
      Do **NOT** run `ergane worker install` to produce this:
      `factory/supervision/units.py:946` — `install` writes unit files and then
      runs `systemctl --user daemon-reload`, `loginctl enable-linger` and
      `systemctl --user enable --now`, mutating the host the attempt is running
      on, and `factory/cli/nouns/worker.py:32` —
      `_require_systemd_user_session` refuses outright where there is no user
      bus. No gate can produce that transcript because it needs systemd and a
      real host; it is step 2 of `plan.md` § "Verification the operator will
      run" and belongs to the operator, not to this node.

## Phase 2: User Story 2 — The requirements refusal names a file the operator can create

### Tests for this story (write FIRST, must fail)

- [ ] T009 [P] [US2] (spec US2-S1, FR-006, trap 8) Reach the packaged-copy case
      by rebinding `factory/config.py:81` — `_resolve_default_registry_path` to
      an example registry written under `tmp_path`, with both
      `ERGANE_PERSONAS_PATH` and `FACTORY_PERSONAS_PATH` cleared and
      `XDG_CONFIG_HOME` pointed at a directory holding no
      `ergane/personas.yaml`. Do **not** merely clear the env vars: this
      repository has no `factory/personas.yaml` — `pyproject.toml` force-includes
      it only at wheel build time — so the resolver falls through to the
      repository root's own **configured** 26 KiB registry and the verb exits
      zero with a full listing instead of refusing (trap 8). Then run
      `ergane install --requirements` and assert the refusal names the resolved
      registry as the file being **read** and names a concrete override path to
      **create** — and assert it does not tell the operator to edit the copy
      inside the installed distribution.
- [ ] T010 [P] [US2] (spec US2-S2, FR-007, traps 6 and 15) Assert on the
      captured output of **both** refusal branches — that
      `~/.config/ergane/personas.yaml` is present and
      `~/.config/ergane/ergane/` is absent. Two branches, two tests: the
      resolution-order strings at `factory/cli/nouns/install.py:95` and
      `factory/cli/nouns/install.py:106` are identical and the conditions that
      reach them are not, so one test cannot prove both. **Name each route
      explicitly.** The all-example branch at
      `factory/cli/nouns/install.py:101-108` is reached the way
      `tests/test_ergane_install_requirements.py:240` —
      `test_requirements_with_example_registry_prints_configuration_guidance`
      reaches it, with a registry of `example/` aliases. The no-aliases branch at
      `factory/cli/nouns/install.py:89-97` is reached with a registry that
      **loads** and yields no gateway alias — every persona declared
      `agent: subscription` or `agent: none`, because `factory/config.py:203` —
      `routes_through_gateway` is False for both and
      `factory/controlplane/verify.py:400` — `gather_gateway_aliases` skips them.
      Do **not** use an empty file: `factory/config.py:219` — `load_personas`
      refuses it at `factory/config.py:242-246` and the verb answers with the
      load-failure refusal at `factory/cli/nouns/install.py:82-85`, which prints
      no resolution order and no tilde path at all, so the assertion has nothing
      to find (trap 15).
- [ ] T011 [P] [US2] (spec US2-S4, FR-008) **The control.** Assert a registry
      that **is** configured still exits zero and still prints the alias listing
      and the three key-management endpoints exactly as today, so a message edit
      cannot have reached the success path.

### Implementation for this story

- [ ] T012 [US2] (FR-006, trap 8) Export one public helper from
      `factory/config.py` beside `factory/config.py:111` —
      `resolve_default_registry_path` returning the XDG/HOME override path it
      already computes at `factory/config.py:124`. Do **not** import
      `factory/config.py:104` — `_xdg_config_home` or `factory/config.py:81` —
      `_resolve_default_registry_path` into the CLI; both are private to the
      resolver and will drift.
- [ ] T013 [US2] (FR-006, FR-007, trap 6) Rewrite **both** messages in
      `factory/cli/nouns/install.py:62` — `_requirements_command`: name the
      resolved registry as what is being read, name the override path to create,
      and drop the duplicated `ergane/` segment from the tilde spelling on
      `factory/cli/nouns/install.py:95` and `factory/cli/nouns/install.py:106`.
      `factory/config.py:47` already carries that segment. Do not find the two
      branches by greping the message wording:
      `grep -rn 'replace the example/ placeholder aliases' factory/` returns
      **two** hits at `602a92c`, and they are the all-example branch here plus
      `factory/controlplane/verify.py:462-463`, the doctor's LLM probe — a
      different verb that prints no resolution order and must be left untouched,
      because editing it makes this story a two-module diff for no reader's
      benefit. The no-aliases branch says something else entirely
      (`factory/cli/nouns/install.py:92`: "declare at least one persona with a
      gateway model alias"), so that grep misses one of the two lines this task
      must change. The grep that finds exactly the pair is
      `grep -rn 'config/ergane/{' factory/`, which returns
      `factory/cli/nouns/install.py:95` and `factory/cli/nouns/install.py:106`
      and nothing else.
- [ ] T014 [US2] (spec US2-S3, FR-008, trap 7) Confirm by reading the diff that
      **no hunk modifies**
      `tests/test_ergane_install_requirements.py:240` —
      `test_requirements_with_example_registry_prints_configuration_guidance`,
      and that the declared `test` gate is green over it. **If it needed an
      edit, the design is wrong**: the refusal and its non-zero exit are a landed
      063-US3 acceptance criterion, and making the verb print an all-example
      registry instead is out of scope for this spec.

### Verification for this story

- [ ] T015 [US2] Paste, as committed evidence, the full refusal text from both
      branches, each showing the single-segment tilde path, the create-not-edit
      wording, and the non-zero exit code. The two registries that reach them are
      an all-example one and one whose personas are **all** `agent: subscription`
      or `agent: none` — **not** an empty file, which never reaches either branch
      (trap 15): it is refused by `factory/config.py:219` — `load_personas` and
      surfaces as `cannot load persona registry: ConfigError: …` from
      `factory/cli/nouns/install.py:82-85`, a message with no tilde path in it to
      show. Both registries are `tmp_path` files driven through
      `ERGANE_PERSONAS_PATH`; nothing here needs a wheel or a real `HOME`, and
      the fresh-`HOME` wheel run stays where `plan.md` has it, as operator
      step 3.

## Phase 3: User Story 3 — A secured endpoint scans as secured, and the interview prefers it

No task in this phase carries `[P]`, and that is measured rather than cautious.
T016 through T018 and T021 all edit `tests/test_llm_discovery.py` and all four
depend on the status dimension T016 threads through
`tests/test_llm_discovery.py:38` — `FakeTransport` and its factory at
`tests/test_llm_discovery.py:103-111`; T019 and T020 both edit
`tests/test_install_mode_routing.py` and share the result-list helper T019
introduces. Write each chain in order.

### Tests for this story (write FIRST, must fail)

- [ ] T016 [US3] (spec US3-S1, FR-009, trap 9) Give
      `tests/test_llm_discovery.py:38` — `FakeTransport` and its factory at
      `tests/test_llm_discovery.py:103-111` a way to answer a status code, then
      assert an endpoint whose `GET /v1/models` answers 401 comes back reachable,
      classified authentication-required, with a detail naming that a credential
      is required and that the scan presented none. Extend that fake — it is the
      only live one. `tests/test_install_mode_routing.py:53` — `FakeTransport`
      has zero call sites in its own module; widening it changes nothing any test
      runs.
- [ ] T017 [US3] (spec US3-S2, FR-010) Assert an endpoint whose
      `GET /v1/models` answers 200 and whose `POST /key/generate` answers 403 is
      authentication-required and **not** inference-only, and that a 404 on
      `/key/generate` still yields inference-only. A protected route is evidence
      the route exists; an absent one answers 404. Follows T016: same file, same
      fake.
- [ ] T018 [US3] (spec US3-S3, FR-011, trap 10) **The control.** Assert 404,
      500 and a refused connection on `GET /v1/models` all stay unreachable with
      no classification and with their detail text byte-identical to today's, and
      that a transport error on `POST /key/generate` still yields the reachable
      inference-only result it yields today. Do not assert
      `render_scan_results`' "no reachable LLM endpoint" tail on a 401 host —
      that tail correctly stops firing, and asserting it is asserting the bug.
      Follows T016: same file, same fake.
- [ ] T019 [US3] (spec US3-S4, FR-012, FR-013, traps 11 and 12) Drive the
      interview with an inference-only endpoint listed **FIRST** and a secured
      401 gateway second, and assert the offered mode is `gateway` and the
      defaulted `llm.base_url` is the gateway's address. The order matters:
      `factory/discovery/llm_scanner.py:40-43` probes 4000 before 11434, so a
      gateway-first test would pass on candidate position alone and prove nothing
      about FR-012. The seam is `tests/test_install_mode_routing.py:111` —
      `_run_with_scan_result`, whose injected scan returns a one-element list
      today; give it a two-element list in the order the story wants. Seed the
      document the way the interview does, from
      `factory/cli/install.py:242-249` — a fixture that has touched the seeded
      `llm` block is read as a **re-run** by
      `factory/cli/install.py:2166` and the scan is ignored. Model it on
      `tests/test_install_mode_routing.py:174` —
      `test_dispatchable_scan_offers_gateway_with_address_defaulted`.
- [ ] T020 [US3] (spec US3-S5, FR-013, trap 12) **The control.** Assert an
      inference-only-only host still offers `direct` with that address and the
      same unavailable-reason text as today
      (`tests/test_install_mode_routing.py:200` —
      `test_inference_only_scan_offers_direct_and_names_missing_capability`), and
      that a mode already declared on a re-run still wins over the scan. Drive
      that second half with an **authentication-required** result and a document
      whose `llm` block differs from `BLANK_DOCUMENT["llm"]` and whose
      `llm.mode` is `"direct"` — the cheapest shape is calling
      `factory/cli/install.py:2149` — `_offered_llm_mode` directly; the harness
      that seeds an existing config file is
      `tests/test_ergane_install_walkthrough.py:644` —
      `test_rerun_offers_the_existing_file_as_defaults_and_touches_only_telemetry`
      — **read** that one for its shape; this story's new assertion belongs in
      `tests/test_install_mode_routing.py` beside its siblings, and no hunk of
      US3's diff may land in the walkthrough module, which US1 also names (as a
      prohibition, trap 5).
      Do **not** model it on `tests/test_install_mode_routing.py:306` —
      `test_operator_declared_address_overrides_scan_result`: that test declares
      nothing in the document, starts from a blank host and drives the operator's
      typed answers, so it never reaches the re-run branch at
      `factory/cli/install.py:2166`. And do not drive it with an inference-only
      result: that falls through to the untouched tail at
      `factory/cli/install.py:2185-2193`, so the control would pass over an
      implementation that copied the dispatchable branch without its
      `if blank_host or existing_mode != "direct"` guard at
      `factory/cli/install.py:2176` and flipped every re-run to `gateway`.
      Follows T019: same file, same helper.
- [ ] T021 [US3] (spec US3-S6, FR-014, trap 13) **The security control.**
      Widen the fixture of `tests/test_llm_discovery.py:159` —
      `test_scan_sends_no_authorization_header` to cover a 401-answering and a
      403-answering endpoint, leaving its assertion unchanged. Do **not** add a
      key parameter to `factory/discovery/llm_scanner.py:64` — `scan_endpoints`;
      its signature closes at `factory/discovery/llm_scanner.py:69` with none by
      design (055 FR-003/SC-002). Follows T016: same file, same fake.

### Implementation for this story

- [ ] T022 [US3] (FR-009, FR-010, FR-011, trap 10) Add the third member to
      `factory/discovery/llm_scanner.py:20` — `EndpointClassification` beside
      `factory/discovery/llm_scanner.py:23-24`, and branch in
      `factory/discovery/llm_scanner.py:90` — `_probe_one`: a 401 or 403 at
      `factory/discovery/llm_scanner.py:118-125` returns reachable and
      authentication-required, and a 401 or 403 from the second probe at
      `factory/discovery/llm_scanner.py:127-131` classifies
      authentication-required at `factory/discovery/llm_scanner.py:135-143`
      instead of inference-only. Every other status keeps its current result and
      its current detail string, and so does every transport error — including
      the second probe's, which today leaves the endpoint reachable and
      inference-only because `/v1/models` has already answered 200. The member's
      value is operator-visible text: `factory/discovery/llm_scanner.py:154` —
      `render_scan_results` prints it.
- [ ] T023 [US3] (FR-012, trap 11) Make the preference order explicit in
      `factory/cli/install.py:2132` — `_llm_scan`: dispatchable, then
      authentication-required, then inference-only. Today it returns the first
      dispatchable and otherwise the first reachable in candidate order, which is
      position, not preference.
- [ ] T024 [US3] (FR-013, traps 11 and 12) In `factory/cli/install.py:2149` —
      `_offered_llm_mode`, branch on authentication-required beside the
      dispatchable branch at `factory/cli/install.py:2173` so a blank host is
      offered `gateway` with that address. Without this the story lands a scanner
      that is right and an interview that still routes the operator to `direct`
      with the gateway's address at `factory/cli/install.py:2185-2193` — a
      subtler wrong answer than today's. Leave the inference-only tail and its
      unavailable-reason text alone, and do not touch
      `factory/cli/install.py:2166` — the blank-host predicate is correct and the
      landed dispatchable behaviour depends on it.
- [ ] T025 [US3] (FR-009, trap 14) Widen the landed membership assertion at
      `tests/test_controlplane_verify_us1.py:484` —
      `test_llm_verify_imports_classification_from_scanner` to include the new
      member. T022 turns it red the moment it lands, and that test is 055 US1-S4's
      control that `verify.py` imports the enum rather than redefining it: keep
      the two `is` identity assertions above it exactly as they are, do not
      delete the membership assertion, and do not edit
      `factory/controlplane/verify.py` itself — `factory/controlplane/verify.py:634`
      constructing `INFERENCE_ONLY` for its own message is still correct.

### Verification for this story

- [ ] T026 [US3] Paste, as committed evidence, two things, both produced inside
      the worktree with no network and no TTY. First, the string
      `factory/discovery/llm_scanner.py:154` — `render_scan_results` returns for a
      scan driven through the extended `tests/test_llm_discovery.py:38` —
      `FakeTransport` over two addresses — one answering 401 to `GET /v1/models`,
      one answering 200 with no key-management route — showing the first as
      reachable and authentication-required and the second as inference-only.
      Second, the `_OfferedLLM` that `factory/cli/install.py:2149` —
      `_offered_llm_mode` returns when handed that inference-only result first and
      that authentication-required result second, over a document seeded exactly
      as `factory/cli/install.py:242-249` — `BLANK_DOCUMENT` seeds it: paste both
      the returned mode and the `llm.base_url` the call wrote into the document.
      Do **NOT** run this against a real proxy or a real interview. A node's
      worktree has no master-keyed LiteLLM proxy on the first default loopback
      candidate, no Ollama on the second, and no terminal — the interview's
      offered default is only visible interactively, at
      `factory/cli/install.py:1560` where `default=offered.mode` is handed to the
      prompter, and the non-interactive path takes `--from-file` and renders no
      default at all. Those two runs are steps 5 and 6 of `plan.md`
      § "Verification the operator will run"; they need a real host and belong to
      the operator, not to this node.

## Verification

- [ ] T027 The full gate command passes green.
- [ ] T028 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end, including step 2's `ergane worker install` on
      a real host — which no node may run — and step 4's second refusal branch,
      which no committed test drove before this spec. Step 6 — pressing Enter at
      the interview's first question on a host running both a secured gateway and
      an Ollama — is the falsifiable test of the whole spec, because it is the
      stranger's first hour the hand-over was written from.
