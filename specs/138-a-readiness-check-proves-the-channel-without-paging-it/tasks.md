# Tasks: a readiness check proves the channel without paging it

Read `plan.md` before starting. Four of its traps will cost you an attempt each
if you meet them as failures instead of as scope. Trap 1: `evaluate` passes on
`snapshot.delivered`, so the moment `gather` stops sending, every healthy
install's escalation finding goes red and `ergane install --verify` exits
non-zero on a working system — split proof from delivery in the same commit that
stops the send. Trap 2: `gather` receives a `ControlPlaneConfig` that does not
know its own path, and the obvious fix, calling `resolve_config_path()`, is wrong
for the three `install` doors that pass an explicit one. Trap 4: every existing
init test rebinds the very seam FR-011 is about, so a test that imports
`bind_offline_seams` proves nothing. Trap 12: the door FR-011 changes passes
**no** config path, so a test that binds only the two doubles it asserts on runs
the whole battery against the control plane of whatever machine it is on — write
the temporary config, point `ERGANE_CONFIG_PATH` at it, and bind all six seams.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the judge
sees; runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — The probe proves the channel instead of paging it

### Tests for this story (write FIRST, must fail)

- [ ] T001 [US1] (trap 6) **Do this one first or the next eight report the wrong
      failure.** Extend `tests/test_controlplane_verify.py:579` — `_FakeTelegramBot`
      with `get_me` and `get_chat`, recording their calls beside `send_message`,
      and add the two matching routes to
      `tests/test_controlplane_verify.py:417` — `_loopback_telegram_listener`. A
      double missing a method raises inside the probe and one of two blanket
      handlers eats it: `factory/controlplane/verify.py:977` — `EscalationProbe.gather`
      returns it as "could not deliver telegram test message", and
      `factory/controlplane/verify.py:1210` — `verify_controlplane_async` returns
      it as "probe failed unexpectedly". Either way the report blames your change
      instead of the double. Not `[P]`: every later task in this phase reads
      these two doubles.
- [ ] T002 [P] [US1] (spec US1-S1, FR-001, FR-002) Given both env vars set and no
      delivery recorded for this install, assert the bot double recorded exactly
      one `get_me`, one `get_chat` and one `send_message`, and that the finding's
      detail names the bot identity `get_me` returned and the chat `get_chat`
      resolved.
- [ ] T003 [P] [US1] (spec US1-S2, FR-003) Given the same install gathered a
      second time, assert the double recorded a `get_me` and a `get_chat` call and
      **zero** `send_message` calls, and that the finding still passes, naming the
      earlier delivery. Today's code sends on both runs; this is the assertion
      that is red before the change.
- [ ] T004 [P] [US1] (spec US1-S3, FR-001, FR-002) Two tests. Given a `get_me`
      that is refused, assert the finding fails naming the bot-token env var.
      Given a `get_me` that answers and a `get_chat` that is refused, assert the
      finding fails naming the chat-id env var. Assert in both that the double
      recorded no `send_message` call — a broken credential must be diagnosed
      without spending a message on it.
- [ ] T005 [US1] (spec US1-S4, FR-004, trap 2) Given two config files at two
      different paths, run the battery against the first, then the second, then
      the first again, and assert deliveries of one, one, zero. The third
      assertion fails a diff that wrote no record; the second fails a diff whose
      record is keyed to `factory/controlplane/config.py:207` — `resolve_config_path`
      rather than to the config the run was handed. Not `[P]`: it drives three
      runs over one shared pair of fixtures.
- [ ] T006 [P] [US1] (spec US1-S9, FR-004, trap 2) Given a `ControlPlaneConfig`
      built by calling `factory/controlplane/config.py:270` — `parse_controlplane_config`
      directly, so the value it carries is the bare default `"config.toml"` and
      not a path, assert the finding **passes**, that its detail names the channel
      as proven and not delivered because the config carries no path, that the
      double recorded a `get_me` and a `get_chat` and **zero** `send_message`
      calls, and that no record file was created anywhere beneath the test's
      working directory. This branch is reachable the day the story lands — four
      production call sites and seven test modules parse a config with a label
      that is not a path — so it may not be left to T011's prose.
- [ ] T007 [P] [US1] (spec US1-S5, FR-003) Given a `send_message` that raises,
      drive four gathers over one install: assert the first finding fails naming
      the send error, that **no** delivery record exists for that install after
      it, that the second still attempts a send, that a third — against a double
      whose send succeeds — delivers, and that a fourth sends nothing. Asserting
      only the first two of those restates what the tree already does; the third
      and fourth are what separate a record written after a successful send from
      one written before the attempt.
- [ ] T008 [P] [US1] (spec US1-S6, FR-003) Given a send that succeeds and a
      record location that cannot be written, assert the finding **passes** with a
      detail naming both the delivery and the unwritten record, and that a second
      gather sends again. The write must sit outside the blanket `except Exception`
      at `factory/controlplane/verify.py:977` — `EscalationProbe.gather`; inside
      it, a read-only config directory reports a working channel as broken and
      re-delivers forever.
- [ ] T009 [P] [US1] (spec US1-S7, FR-005, trap 7) **The control.** For each of
      the adapter-`none`, non-telegram-adapter and unset-env-var paths, compare
      the snapshot's `detail` against the literal string in the tree today and
      assert `_telegram_bot_factory` was never called. Asserting only "the run
      fails" passes through
      `factory/controlplane/verify.py:222` — `_telegram_bot_factory`'s own
      `ServiceNotAnswering` and proves nothing.

### Implementation for this story

- [ ] T010 [US1] (FR-002, trap 1) Add the proof to
      `factory/controlplane/verify.py:119` — `EscalationSnapshot` as its own
      field beside `delivered`, and change
      `factory/controlplane/verify.py:987` — `EscalationProbe.evaluate` to judge
      on it — passing on the proof when no send was attempted or the send
      succeeded, failing when an attempted send raised. Do this **before** T012:
      while `passed = snapshot.delivered` stands, a probe that stops sending is a
      probe that fails.
- [ ] T011 [US1] (FR-004, trap 2) Add the loaded path to
      `factory/controlplane/config.py:114` — `ControlPlaneConfig` with a default,
      and set it at `factory/controlplane/config.py:289-296` — `parse_controlplane_config`
      from the `source` that function already receives. Give the field a default:
      `tests/test_container_manifest.py:45` — `_config` and
      `tests/test_container_project.py:53` — `_config` construct this dataclass
      and are not this story's business. Remember that
      `factory/controlplane/config.py:271` — `parse_controlplane_config` defaults
      `source` to the bare string `"config.toml"`, so the probe derives a record
      location only from an absolute path and otherwise reports proven-but-not-
      delivered rather than writing beside the working directory — the branch
      T006 holds.
- [ ] T012 [US1] (FR-001, FR-003, FR-004, FR-005) In
      `factory/controlplane/verify.py:934` — `EscalationProbe.gather`, below the
      three early returns and leaving all three untouched, prove the token and the
      chat through the bot the existing seam at
      `factory/controlplane/verify.py:222` — `_telegram_bot_factory` already
      builds, then read the delivery record beside the config's own path, send at
      most once, and write the record after the send at
      `factory/controlplane/verify.py:963-968` — `EscalationProbe.gather`
      succeeds — outside the `except Exception` at
      `factory/controlplane/verify.py:977` — `EscalationProbe.gather`, so a write
      that fails reports "delivered, not recorded" instead of a failed delivery.
- [ ] T013 [US1] (FR-002) Update the class docstring at
      `factory/controlplane/verify.py:925` — `EscalationProbe`, which currently
      says the probe "Delivers a test message through the configured Telegram
      transport". Leave its 041 deferral sentence alone: that half of 033's split
      still stands (trap 8).
- [ ] T014 [US1] (FR-006, trap 3) Revise the scope note at
      `specs/033-ergane-install/spec.md:177-183` to state the reversal, its
      reason and this spec's number, and revise the docstring at
      `tests/test_controlplane_verify.py:1191-1196` to say what the real path now
      executes. **Change nothing else in that spec file.** A story title, an
      acceptance scenario, an FR body or the Work Graph block are the four
      regions `factory/workgraph/landed.py:438` — `_story_parts` fingerprints,
      and `specs/033-ergane-install/spec.md:211-215` — the scenario that says a
      message "is delivered through it" — is precisely the sentence you will want
      to fix. Leave it. Do not satisfy yourself with a line-prefix grep: that
      scenario's first line begins `3. ` and its tempting sentence begins
      `**Then**`, so a grep for `### User Story`, `**Given**` and `- **FR-`
      passes the exact edit that reopens the story. T015 is the check, and it is
      a digest comparison against `602a92c`, not against `HEAD`.

### Verification for this story

- [ ] T015 [US1] (spec US1-S8) Paste, as committed evidence, three things: the
      escalation finding's detail from two consecutive runs of the battery over
      one install — the first delivering, the second not — the output of
      `git diff --stat specs/033-ergane-install/spec.md`, and the output of trap
      3's digest snippet, which prints one line per 033 story key comparing
      `factory/workgraph/delta.py:48` — `fingerprint_for` over that file as
      `git show 602a92c:specs/033-ergane-install/spec.md` returns it and as it
      stands after your edit. Run the snippet exactly as trap 3 writes it, with
      that fixed baseline: `git show HEAD:` returns your own committed edit, so a
      `HEAD`-baselined comparison prints `UNCHANGED` for anything at all and this
      evidence would prove nothing. Every key must read `UNCHANGED`; a `CHANGED`
      line means the edit landed in a fingerprinted region and a story that
      landed on 2026-08-16 is about to reopen in the next delta derivation.

## Phase 2: User Story 2 — A readiness door runs the battery without the probes that act

### Tests for this story (write FIRST, must fail)

- [ ] T016 [P] [US2] (spec US2-S1, FR-007, FR-008) Given a caller naming the
      escalation probe as one to leave un-run, assert the findings still contain
      one for `escalation`, that it carries `Severity.WARNING`, that its detail
      names both the reason and `ergane install --verify` as the command that does
      prove the channel, that the exit code is 0, and that the bot double recorded
      no calls of any kind.
- [ ] T017 [P] [US2] (spec US2-S2, FR-009, trap 5) **The control that matters
      most.** Given a caller naming nothing, assert the exit code is 0 over a
      passing set and 1 over a set containing one failing probe — exactly as
      today. Then assert that a set holding a `Severity.WARNING` finding beside
      passing ones exits 0, which
      `factory/controlplane/verify.py:1221` — `verify_controlplane_async` cannot
      do today. Only the pair proves the conjunction moved without moving any
      existing verdict.
- [ ] T018 [P] [US2] (spec US2-S3, FR-010) Given one passing, one failing and one
      warning finding, assert the three report lines are labelled `[PASS]`,
      `[FAIL]` and `[WARN]`. Today
      `factory/controlplane/verify.py:1234` — `render_findings` would label the
      warning `[FAIL]`.
- [ ] T019 [US2] (spec US2-S4, FR-011, trap 4, trap 12) Write a temporary config
      declaring telemetry off, point `ERGANE_CONFIG_PATH` at it, and bind all six
      outward seams —
      `factory/controlplane/verify.py:222` — `_telegram_bot_factory`,
      `factory/controlplane/verify.py:168` — `_llm_client_factory`,
      `factory/controlplane/verify.py:178` — `_temporal_client_factory`,
      `factory/controlplane/verify.py:216` — `_memory_client_factory`,
      `factory/controlplane/verify.py:384` — `_host_seam_factory` and
      `factory/controlplane/verify.py:395` — `_forge_capability_seam_factory` —
      then call `factory/cli/init.py:170` — `_default_controlplane_probe`
      **itself** and assert both the telegram and the LLM doubles recorded zero
      calls and that the returned findings name `escalation` and `llm` as left
      un-run. That function passes no config path, so without the tmp config the
      battery reads the host's own `~/.config/ergane/config.toml` (trap 12); and
      do **not** import `tests/test_ergane_init_check.py:180` — `bind_offline_seams`,
      which rebinds `_controlplane_probe` at
      `tests/test_ergane_init_check.py:258` — `bind_offline_seams`, the seam
      under test (trap 4). The idiom to copy is
      `tests/test_controlplane_verify.py:789` — `test_verify_escalation_probe_delivers_and_defers`.
      Not `[P]`: it and T020 share the config-and-seam fixture.
- [ ] T020 [US2] (spec US2-S5, FR-012, trap 12) With the same fixture — this time
      with the config declaring a gateway and its master-key env var set, or
      `factory/controlplane/verify.py:428` — `LLMProbe.gather` takes its "no
      credential" early return and records nothing — call
      `factory/supervision/engine_upgrade.py:103` — `_ComposeDockerSeam.verify`
      and assert the telegram double recorded zero calls **and** the LLM double
      recorded at least one. An engine upgrade must stop paging without stopping
      proving; a `WARN` line for `llm` here means FR-012 was implemented as a copy
      of FR-011.
- [ ] T021 [P] [US2] (spec US2-S6, FR-007, FR-012, trap 10) **The second
      control.** Assert first that FR-007's parameter is present on
      `factory/controlplane/verify.py:1198` — `verify_controlplane_async` and
      `factory/controlplane/verify.py:1225` — `verify_controlplane` with a
      default that leaves nothing un-run — read it off the signature, so the
      assertion fails today and passes only after T023 — and then that each of
      the four `install` doors —
      `factory/cli/nouns/install.py:40` — `_verify_command`,
      `factory/cli/install.py:954` — `install_command`,
      `factory/cli/install.py:1185` — `_install_non_interactive` and
      `factory/cli/install.py:1279` — `_install_from_file` — passes it empty or
      leaves it defaulted. Asserting only the second half is a test that is green
      before the change and green after, because the parameter it is silent about
      does not exist yet. If `--verify` stops delivering, the once-per-install
      delivery has no door left to happen on.
- [ ] T022 [P] [US2] (spec US2-S7, FR-013, trap 11) **The test that decides
      whether this story is safe to land.** Given an `InitFacts` whose
      `control_plane` tuple holds passing probe findings plus two carrying
      `Severity.WARNING`, assert the summary built by
      `factory/mergequeue/onboard.py:577` — `_control_plane_finding` **passes**,
      that its slug is still `control_plane` and it is the only control-plane
      finding produced, that its detail names the proved probes and the un-run
      probes as two separate lists, and that it is not blocking. Today
      `factory/mergequeue/onboard.py:608` — `_control_plane_finding` counts any
      finding that is not `passed` as a failed probe, so this assertion is red
      before the change — and green-without-it means `ergane init --check` prints
      `[FAIL] control_plane: 2 of 8 control-plane probes failed` and exits
      non-zero on every healthy repository. No spec is parked by that and no
      repository is refused for dispatch — trap 11's closing paragraph says why —
      but it is the command that answers "is this repository ready".

### Implementation for this story

- [ ] T023 [US2] (FR-007) Add the caller-supplied collection of probe names to
      `factory/controlplane/verify.py:1198` — `verify_controlplane_async` and
      `factory/controlplane/verify.py:1225` — `verify_controlplane`, defaulting to
      none. Do not reorder or filter `REGISTRY`
      (`factory/controlplane/verify.py:1183-1192`) itself: the walk stays whole so
      a named probe still gets a finding.
- [ ] T024 [US2] (FR-008, FR-009, trap 5) Emit a `Severity.WARNING` finding for
      each probe left un-run, and change the verdict at
      `factory/controlplane/verify.py:1221` — `verify_controlplane_async` from a
      conjunction over `passed` to one over
      `factory/mergequeue/models.py:354` — `Finding.blocking`. Every finding this
      module builds today omits `severity` and so defaults to
      `Severity.ERROR` (`factory/mergequeue/models.py:351` — `Finding`), which is
      why the two conjunctions agree on everything that exists.
- [ ] T025 [US2] (FR-010) Replace the two-way label at
      `factory/controlplane/verify.py:1234` — `render_findings` with
      `factory/mergequeue/models.py:366` — `mark`, which already returns the
      three-way one and says in its own docstring why it is spelled once. Leave
      `factory/cli/init.py:2292` — `render_check` alone: it already prints
      `finding.mark`, and it is not the renderer the un-run probes reach.
- [ ] T026 [US2] (FR-013, trap 11) Make the same conjunction change in
      `factory/mergequeue/onboard.py:608` — `_control_plane_finding`, and extend
      the passing summary at
      `factory/mergequeue/onboard.py:619` — `_control_plane_finding` to name the
      un-run probes as their own list inside that one line's detail. Keep the slug
      `control_plane` and add no second finding: a new slug breaks
      `tests/test_ergane_init_check.py:301` — `test_a_scaffolded_registered_wired_repo_passes_every_finding`
      and `tests/test_ergane_init_check.py:490` — `test_both_doors_render_identical_parity_findings`,
      which assert the exact set. Do this **before** T027: FR-011 without it makes
      `ergane init --check` exit non-zero on every healthy repository.
- [ ] T027 [US2] (FR-011) Have `factory/cli/init.py:170` — `_default_controlplane_probe`
      leave both the escalation and the llm probes un-run. That one edit covers
      all three commands that reach this seam — `ergane init --check` at
      `factory/cli/init.py:1149` — `init_command`, and a plain `ergane init` or
      `ergane init --wire` at `factory/cli/init.py:1355` — `init_command`, which
      probes fresh through `factory/cli/init.py:2240` — `gather_init_facts`
      whenever the config is readable. Do **not** edit the seam binding at
      `factory/cli/init.py:178`, and do **not** add a cheap mode to
      `factory/controlplane/verify.py:428` — `LLMProbe.gather` (trap 8): this
      story changes which door runs that probe, never what it does.
- [ ] T028 [US2] (FR-012) Have `factory/supervision/engine_upgrade.py:103` — `_ComposeDockerSeam.verify`
      leave the escalation probe un-run and keep the rest, and confirm by reading
      that the four `install` doors were not touched.

### Verification for this story

- [ ] T029 [US2] Paste, as committed evidence, the full report from a battery run
      with nothing left un-run and from one with escalation and llm left un-run,
      side by side, so the `[WARN]` lines and the unchanged exit code are both
      visible in the diff, **and** the rendered `control_plane` line from
      `ergane init --check` on a healthy repository, showing it passing with the
      two un-run probes named inside that single line.

## Verification

- [ ] T030 The full gate command passes green.
- [ ] T031 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end. Steps 1 and 5 together are the falsifiable test
      of this spec: two consecutive `ergane install --verify` runs delivering
      exactly one message, and five consecutive `ergane init --check` runs adding
      zero entries to the gateway's spend log where they previously added five.
      Step 4 is trap 11 checked by hand and must be run before anything else is
      believed — expect one passing `control_plane` line naming the two un-run
      probes in its detail, and **no** per-probe `[WARN]` line from that door, a
      line whose appearance would mean a new slug was added. A `[FAIL]
      control_plane` line there means the readiness command now exits non-zero on
      a healthy repository; it parks no spec and refuses no repository for
      dispatch, and trap 11's closing paragraph says why. Per-probe `[WARN]`
      lines belong to steps 1 and 6, which render through
      `factory/controlplane/verify.py:1230` — `render_findings`. Step 7 checks
      trap 3 by comparing `factory/workgraph/delta.py:48` — `fingerprint_for`
      digests between `602a92c` and the edited file — not between `HEAD` and it,
      which by then are the same text — and must be run before the story is
      offered for landing.
