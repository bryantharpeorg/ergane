---
state: draft
fixes:
  - notify/every-control-plane-readiness-check-delivers-a-real-escalation-message
  - init/check-spends-a-token-and-pages-the-operator-every-run
# DRAFTED 2026-09-04 by the refinement workflow (refinement-2026-09-04) from
# docs/triage-2026-09-03-ergane-web-round3.md § "a-readiness-check-proves-the-
# channel-without-paging-it" (lines 149-166), against ergane-buildout at 602a92c.
# Every `file:line` in spec.md and plan.md was read from that commit with `sed`
# and verified to resolve to the symbol named, not recalled.
#
# WHERE THIS CAME FROM. N7 of the `ergane-web` round-3 hand-over
# (`ergane-findings-ergane-web-2026-09-03.md`), a consumer repository that is
# itself a target of this factory. The reporter measured eight escalation
# messages in thirteen minutes while fixing one broken install. The second key,
# `init/check-spends-a-token-and-pages-the-operator-every-run`, was raised
# independently by the 034/US4 session on 2026-08-16 and confirmed by the
# operator; it names the same probe registry from the other door and adds the
# LLM completion beside the Telegram message.
#
# WHAT IT COST, MEASURED. Eight delivered messages in thirteen minutes, from a
# verb an operator runs repeatedly while fixing things. The cost is not the
# messages: it is that the channel a parked node's question expires on is the
# channel the operator learns to mute. The 2026-08-16 row records the same
# design nearly costing more — 034/US3's fixture left `_controlplane_probe`
# unbound and its unit tests probed the real control plane, which on a
# provisioned host would have been live network I/O, a delivered message and a
# spent token from a unit test.
#
# THE TWO KEYS AND THE FRs THAT FINISH THEM, CHECKED AGAINST THE HALF-FIX
# LESSON. N7 asks for three things and each has its own requirement: prove the
# token and chat id without delivering (FR-001), deliver at most once per
# install (FR-003), and stop the readiness doors delivering at all (FR-011,
# FR-012). The init key names TWO side effects, a delivered message AND a
# completed LLM token, and its ledger note prescribes "a cheaper probe set for
# this door ... with the check reporting 'control plane not probed' rather than
# silently omitting the finding". A spec that only stopped the paging would be
# the shape this floor has now recorded three times: a `fixes:` list longer than
# the FRs justify. So FR-011 leaves BOTH the escalation and the llm probes
# un-run for the init seam, and FR-008 makes the omission a reported WARN
# finding rather than a silent absence. Both keys are open at 602a92c and
# neither is declared by any landed spec.
#
# ONE REQUIREMENT THE SOURCE ENTRY DID NOT HAVE, AND IT IS THE ONE THAT WOULD
# HAVE MADE A HEALTHY REPOSITORY READ FAIL. `factory/mergequeue/onboard.py:608`
# collapses 033's probe findings into `ergane init --check`'s single
# `control_plane` finding with `if not probe.passed`. A probe left un-run is
# `passed=False` with `Severity.WARNING`, so FR-011 as the entry scoped it would
# have turned that summary into a blocking finding and made `ergane init --check`
# print `[FAIL] control_plane: 2 of 8 control-plane probes failed` and exit
# non-zero on a repository with nothing wrong with it. It stops there, at one
# command's exit code: the third REPAIRED entry below corrects an overstatement
# this paragraph carried when it was first written. FR-013 and trap 11 exist
# because of that read; the entry's scope did not name the file.
#
# NOT IN SCOPE. This spec does not change the escalation delivery path the
# factory itself pages on, the adapter registry, or the doctor's probe registry
# (which correctly has no escalation probe). It does not add an adapter seam to
# the probe — 033's split gave that to 041 and that half stands. It does not
# change what any probe other than escalation gathers; the llm probe is left
# un-run by one door, never altered.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), against the same 602a92c: every
# anchor re-read, none had moved, no key added or removed. Instructions
# corrected — plan.md's operator step 3 demanded `[WARN] escalation` and
# `[WARN] llm` lines that `ergane init --check` structurally cannot print, since
# `factory/cli/init.py:2292` — `render_check` prints one line per onboarding
# finding and `factory/mergequeue/onboard.py:577` — `_control_plane_finding`
# collapses every probe into one `control_plane` line; the only way to satisfy
# it was the new slug trap 11 forbids. Unbound battery corrected — US2-S4 and
# US2-S5 asked for `_default_controlplane_probe()` with only two seams bound,
# and that function passes no config path, so the test would have reached the
# operator's own control plane: exactly the 034/US3 near-miss this block already
# records. New trap 12 carries the mechanism; both scenarios now require the
# temporary config and the full seam binding. Criteria hardened — US1-S5 was
# satisfiable by a test-only diff and now asserts the record's absence and a
# fourth run that must not send. Requirements completed — FR-002 carries the
# send-raises exception its own truth table states, FR-003 says where the record
# lives and what an unwritable record reports, FR-004 governs the no-absolute-
# path branch that trap 2 previously answered in contradiction of FR-002.
#
# REPAIRED AGAIN 2026-09-04 (refinement-2026-09-04), second pass, answering an
# adversarial review of the trio; same 602a92c, no anchor moved, no key added or
# removed, `state` unchanged. A guard that did not guard was replaced: US1-S8,
# T015 and operator step 7 checked trap 3 by grepping for lines beginning
# `### User Story`, `**Given**` or `- **FR-`, and 033-US2's scenario 3 at
# `specs/033-ergane-install/spec.md:211-215` puts the tempting sentence on lines
# beginning `**Then**` and plain continuation words — an edit that reopens a
# story landed 2026-08-16 passed all three checks. All three now compare
# `factory/workgraph/delta.py:48` — `fingerprint_for` digests before and after
# the edit, which is the function the delta actually computes identity with. A
# requirement gained the scenario it lacked: FR-004's non-absolute-path branch
# is reachable the day it lands and had no test, so US1-S9 and T006 exist. Two
# statements were made true rather than nearly true: trap 6 now names both
# blanket handlers the missing double method can be swallowed by, and the
# neighbour survey names 074, 080 and 112 beside 132 on
# `factory/controlplane/verify.py`. And the doors are named as they are: the init
# seam is reached by `ergane init` and `ergane init --wire` as well as by
# `ergane init --check`, which is what the notify key's own summary says.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), third pass, answering a second
# adversarial review; same 602a92c, no anchor moved, no key added or removed,
# `state` unchanged. A guard that could not fail was given a baseline: trap 3's
# digest snippet, T015 and operator step 7 compared the working tree against
# `git show HEAD:` — and the moment the story's own 033 edit is committed, HEAD
# *is* that edit, so all three print `UNCHANGED` for any edit whatsoever. Run
# verbatim on the clean tree it printed three `UNCHANGED` lines with no edit made
# at all. All three now baseline on `602a92c`, the sha this trio was drafted at,
# which does catch the tempting rewrite of 033-US2's scenario 3 (`US2 CHANGED`)
# while passing the scope-note edit FR-006 asks for. An overstated consequence
# was corrected wherever it appeared — the paragraph above, FR-013, US2-S7,
# trap 11, operator step 4, T022, T026 and T031 said an un-run probe would park
# every spec in the repository. It cannot.
# `factory/mergequeue/onboard.py:417` — `evaluate_init_facts` is the only caller
# of `_control_plane_finding` and returns `()` for absent facts
# (`factory/mergequeue/onboard.py:429-430`); `InitFacts` is built in exactly one
# place, `factory/cli/init.py:2244`, reached only through
# `factory/cli/init.py:2269` — `check_repo`; and the dispatch preflight
# (`factory/activities/merge_activities.py:785`) and `repo onboard`
# (`factory/workgraph/cli.py:532`) pass no init facts, so no control-plane
# finding reaches the profile the roadmap parks a spec on at
# `factory/roadmap/workflow.py:1263`. The collapse mechanism trap 11 reads is
# real; its blast radius is one command's exit code. And a control was made able
# to fail: US2-S6 and T021 asserted only that the four `install` doors leave
# nothing un-run, which a test-only diff satisfies today, so both now also pin
# FR-007's new parameter and its default.
---

# Feature Specification: a readiness check proves the channel without paging it

**Created**: 2026-09-04
**Depends on**: nothing — no unlanded spec, and no frontmatter `depends_on_landed`.
Eight other drafts name a file this spec also edits, in disjoint regions: see
plan.md § Sizing.

## The gap, stated precisely

The escalation probe has exactly one way to say the channel works, and that way
is to page a human. Six call sites reach it and two of them are diagnostics an
operator is expected to run over and over.

1. The proof **is** the delivery. `factory/controlplane/verify.py:963-968` —
   `EscalationProbe.gather` builds a real bot and awaits
   `bot.send_message(chat_id=..., text="ergane install --verify test message")`.
   That send is the probe's entire evidence.
2. **Nothing is read before it.** The only guards above the send are three early
   returns: adapter `none` at `factory/controlplane/verify.py:935` — `EscalationProbe.gather`,
   a non-telegram adapter at `factory/controlplane/verify.py:945` — `EscalationProbe.gather`,
   and either env var unset at `factory/controlplane/verify.py:956` — `EscalationProbe.gather`.
   None consults state. For a configured install the send is unconditional, so
   "at most once" cannot be expressed as a condition on the code that exists —
   the function has nothing to condition on.
3. **The judgment has no third answer.** `factory/controlplane/verify.py:987` —
   `EscalationProbe.evaluate` is `passed = snapshot.delivered`, and
   `factory/controlplane/verify.py:119` — `EscalationSnapshot` carries
   `delivered` and no separate proof. "Did not deliver" and "is not working" are
   the same value, so a probe that stopped sending would start failing.
4. **No caller can opt out.** `factory/controlplane/verify.py:1225` —
   `verify_controlplane` calls `factory/controlplane/verify.py:1198` —
   `verify_controlplane_async`, which walks `REGISTRY`
   (`factory/controlplane/verify.py:1183-1192`) start to finish. Neither entry
   takes a parameter naming a probe, so "run the battery but not that probe" is
   not sayable.
5. **Six call sites, and two of them are doors an operator opens repeatedly.**
   `factory/cli/nouns/install.py:40` — `_verify_command`;
   `factory/cli/install.py:954` — `install_command`;
   `factory/cli/install.py:1185` — `_install_non_interactive`;
   `factory/cli/install.py:1279` — `_install_from_file`;
   `factory/cli/init.py:174` — `_default_controlplane_probe`, bound to the seam
   at `factory/cli/init.py:178` and reached from `factory/cli/init.py:2146` —
   `_control_plane_facts`; and `factory/supervision/engine_upgrade.py:106` —
   `_ComposeDockerSeam.verify`. The last two run on a schedule of the operator's
   frustration, not of their intent. **Three commands share that init seam, not
   one.** `ergane init --check` reaches it at `factory/cli/init.py:1149` —
   `init_command`; a plain `ergane init` and `ergane init --wire` reach it at
   `factory/cli/init.py:1355` — `init_command`, which hands `run_check` a
   `control_plane` of `None` whenever the config is readable, so
   `factory/cli/init.py:2240` — `gather_init_facts` probes fresh. The ledger row
   for the notify key names `init --wire` among the delivering doors for exactly
   that reason. FR-011 closes all three, because all three are one seam.
6. **The tree already knows the hazard and defends only its own tests from it.**
   `tests/test_ergane_init_check.py:193` — `bind_offline_seams` says in its own
   words that an unbound seam "would spawn the real `gh` and deliver a real
   Telegram probe", and `tests/test_ergane_init_check.py:258` —
   `bind_offline_seams` rebinds `_controlplane_probe` for every offline test.
   Production has no equivalent, and the ledger row for the init key records
   what that asymmetry nearly cost.
7. **And the cheap proof does not exist anywhere.** `getMe` and `getChat` are
   absent from the tree: the only hit for that grep is
   `factory/notify/redact.py:202` — `_redact_record`, which is
   `record.getMessage()` on a log record. Spec 064 has a `getMe` inside a
   loopback test double that is not in this tree; it is not production code and
   must not be mistaken for one.

**The delivery is deliberate, and that is why this is a design change rather
than a patch-out.** `specs/033-ergane-install/spec.md:177-183` says the probe
"proves *delivery*" and tells its implementer to build against the transport
that exists. `tests/test_controlplane_verify.py:1187` —
`test_verify_escalation_gather_against_live_double` is a live-double test whose
docstring at `tests/test_controlplane_verify.py:1191-1196` says "The real
send_message path executes". Both were right when the only Telegram fact
reachable was a sent message. Neither anticipated a diagnostic verb.

## The rule this spec is asking for

**A readiness check proves the escalation channel by asking Telegram who the bot
is and which chat that id names, delivers a real message at most once per
install, and never delivers at all from a door whose whole purpose is to be run
again in a minute.**

What the probe does, given the two facts it can now read:

| `getMe` / `getChat` | a delivery already recorded for this install | result |
|---|---|---|
| both answer | no | passes; names the bot and the chat; sends one message; records it |
| both answer | yes | passes; names the bot and the chat; sends nothing |
| `getMe` refuses | — | fails naming the bot-token env var; sends nothing |
| `getMe` answers, `getChat` refuses | — | fails naming the chat-id env var; sends nothing |
| the send itself raises | no | fails; **no record written**, so the one delivery is not consumed |
| both answer; the record cannot be written | no | passes; sends one message; reports "delivered, not recorded" |
| both answer; the config carries no path to key a record to | — | passes; sends nothing; reports proven, not delivered |

What each door asks the battery for:

| door | escalation probe | llm probe | can it page the operator |
|---|---|---|---|
| `ergane install --verify` and the three `install` write paths | runs | runs | yes — once per install |
| `ergane init --check`, `ergane init` and `ergane init --wire` — one seam | left un-run, reported `WARN` | left un-run, reported `WARN` | never |
| the engine-upgrade verification | left un-run, reported `WARN` | runs | never |

### What this spec is not

It is not a weakening of `ergane install --verify`. That door still proves every
subsystem and still delivers a real message the first time an install is
verified, which is the run where a human is watching for it.

It is not a change to how the factory escalates. The delivery path a parked node
uses is untouched; this spec only stops a *diagnostic* from borrowing it.

It is not a silent skip. A probe a door does not run produces a finding for that
probe naming the door's reason and the command that does prove it. The failure
this spec exists to prevent — a report that looks complete and is not — is not
one it may commit itself.

It is not a new finding slug on `ergane init --check`. That report renders one
line per onboarding finding at `factory/cli/init.py:2292` — `render_check`, and
the whole control-plane battery reaches it as the single `control_plane` line
that `factory/mergequeue/onboard.py:577` — `_control_plane_finding` builds. The
un-run probes are named *inside* that line's detail. Per-probe `[WARN]` lines
are what `ergane install --verify` prints, through
`factory/controlplane/verify.py:1230` — `render_findings`.

## User Scenarios & Testing

### User Story 1 - The probe proves the channel instead of paging it (Priority: P1)

As an operator repairing a broken install, I run `ergane install --verify` as
many times as it takes and my phone stays quiet after the first one, while every
run still tells me the bot token and the chat id are good.

**Why this priority**: P1 and it depends on nothing. It is the half that reaches
the door the ledger row measured — eight messages in thirteen minutes came from
`--verify`, not from `init --check`. It also has to land first: US2's exclusion
is meaningless while the probe's only verdict is a delivery.

**Independent Test**: drive `EscalationProbe.gather` against a recording bot
double twice over one install and read what the bot was asked to do each time.

**Acceptance Scenarios**:

1. **Given** a telegram escalation with both env vars set and no delivery
   recorded for this install, **When** the probe gathers, **Then** a committed
   test asserts the bot double recorded one `get_me` call, one `get_chat` call
   and exactly one `send_message`, and asserts the finding's detail names the bot
   identity `get_me` returned and the chat `get_chat` resolved.
2. **Given** the same install gathered a second time, **When** the probe
   gathers, **Then** a committed test asserts the bot double recorded a `get_me`
   and a `get_chat` call and **zero** `send_message` calls, and that the finding
   still passes, naming the earlier delivery. Today's code sends on both runs, so
   this assertion is red before the change and cannot be satisfied by a test-only
   diff.
3. **Given** an install whose `get_me` is refused, and separately one whose
   `get_me` answers while `get_chat` is refused, **When** the probe gathers,
   **Then** committed tests assert each finding fails naming the env var at
   fault — the bot-token one in the first case, the chat-id one in the second —
   and assert the bot double recorded no `send_message` call in either, so a
   broken credential is diagnosed without spending a message on it.
4. **Given** two installs whose config files sit at two different paths,
   **When** the battery is run against the first, then the second, then the first
   again, **Then** a committed test asserts a delivery on each of the first two
   runs and **none** on the third. The third assertion fails a diff that never
   wrote a record; the second fails a diff whose record is keyed to
   `resolve_config_path()` instead of to the config the run was handed.
5. **Given** an install with no delivery recorded and a bot double whose
   `send_message` raises, **When** the probe gathers, gathers a second time, and
   is then gathered twice more against a double whose `send_message` succeeds,
   **Then** a committed test asserts the first finding fails naming the send
   error, that **no** delivery record exists for that install after it, that the
   second run still attempts a send, that the third run delivers, and that the
   fourth sends nothing. Today's code has no record at all and fails the fourth
   assertion; a diff that writes the record before the send passes the first and
   third and fails the second.
6. **Given** an install whose send succeeds but whose delivery record cannot be
   written, **When** the probe gathers and is then gathered again, **Then** a
   committed test asserts the first finding **passes** with a detail naming the
   delivery and the unwritten record, and that the second run sends again — the
   record write is outside the send's exception boundary, so an unwritable
   config directory is reported as itself rather than as a failed channel.
7. **Given** the adapter `none` case, the non-telegram-adapter case and the
   unset-env-var case, **When** the probe gathers, **Then** a committed test
   compares each snapshot's `detail` against the literal string in the tree today
   and asserts the bot factory was never called. These three paths are the
   control: they are what proves the new proof was added above them rather than
   in place of them.
8. **Given** the two documents that state the opposite of this rule, **When**
   the story lands, **Then** the diff shows `specs/033-ergane-install/spec.md`'s
   scope note and the live-double test's docstring revised to state the reversal
   and its reason, **and** pasted output committed in the same diff shows
   `factory/workgraph/delta.py:48` — `fingerprint_for` returning an identical
   digest for every one of 033's story keys over that file's text as of `602a92c`
   and as it stands after the edit. The baseline may not be `HEAD`: HEAD carries
   the edit under test the moment it is committed, and this evidence is pasted
   into the same diff as the edit, so a comparison against `HEAD` reads
   `UNCHANGED` for every edit anyone could make. A line-prefix grep is not this
   check either, and may not be substituted for it: 033-US2's scenario 3 is `specs/033-ergane-install/spec.md:211-215`,
   and the sentence an implementer will want to correct sits on lines beginning
   `**Then**` and on plain continuation words, so an edit that changes the
   fingerprint and reopens a story landed on 2026-08-16 satisfies every prefix
   rule anyone would write.
9. **Given** a `ControlPlaneConfig` produced by a direct
   `parse_controlplane_config` call — the case where the value the config
   carries is the bare default `"config.toml"` and not a path at all — **When**
   the probe gathers, **Then** a committed test asserts the finding **passes**,
   that its detail names the channel as proven and not delivered because the
   config carries no path, that the bot double recorded a `get_me` and a
   `get_chat` call and **zero** `send_message` calls, and that no delivery
   record file was created anywhere under the directory the test ran in.
   `factory/controlplane/config.py:271` — `parse_controlplane_config` and the two
   modules that construct the dataclass directly make this branch reachable the
   day the story lands, so it may not ship as prose in a task.

### User Story 2 - A readiness door runs the battery without the probes that act (Priority: P2)

As an operator, the two verbs I run to ask "is this thing ready" tell me what
they did not check instead of paging me and spending a token to find out.

**Why this priority**: P2, and it needs US1's third answer to exist first —
until a probe can be reported as proven-but-not-delivered, "left un-run" has no
grammar to be reported in either. This is the story that closes the init key: it
is the only place the LLM completion stops.

**Independent Test**: write a temporary config, point `ERGANE_CONFIG_PATH` at
it, bind every outward seam the battery reaches, call
`_default_controlplane_probe()` itself, and read the telegram and LLM doubles'
call lists.

**Acceptance Scenarios**:

1. **Given** a caller that names the escalation probe as one to leave un-run,
   **When** the battery runs, **Then** a committed test asserts the returned
   findings still contain one for `escalation`, that it carries
   `Severity.WARNING` and a detail naming both the reason and
   `ergane install --verify` as the command that does prove the channel, that the
   exit code is 0, and that the bot double recorded no calls of any kind.
2. **Given** a caller that names nothing, **When** the battery runs over a
   passing set and then over a set containing one failing probe, **Then** a
   committed test asserts the exit codes are 0 and 1 exactly as today, **and**
   asserts that a battery containing a `Severity.WARNING` finding beside passing
   ones exits 0 — which the present conjunction over `passed` cannot do.
3. **Given** a findings list holding one passing, one failing and one warning
   finding, **When** the report is built, **Then** a committed test asserts the
   three lines are labelled `[PASS]`, `[FAIL]` and `[WARN]`, so a warning is not
   printed under the same label as a proof.
4. **Given** a temporary config file the test wrote itself, with telemetry
   declared off and `ERGANE_CONFIG_PATH` pointed at it, and every outward seam
   the battery reaches bound to a double — the telegram bot factory, the LLM
   client factory, the temporal client factory, the memory client factory, the
   host seam and the forge capability seam — **When** `_default_controlplane_probe()`
   is called itself, **Then** a committed test asserts **both** the telegram and
   the LLM doubles recorded zero calls and that the returned findings name
   `escalation` and `llm` as left un-run. The test may not rebind
   `factory/cli/init.py:178` — that seam is what
   `tests/test_ergane_init_check.py:258` — `bind_offline_seams` replaces for
   every offline test, and replacing it here would prove nothing about the door
   under test. Nor may it leave the config to the host: this door passes no
   config path, so a test that does not set `ERGANE_CONFIG_PATH` aims the whole
   battery at whatever control plane the machine running it happens to have.
5. **Given** that same temporary config, this one declaring a gateway with its
   master-key env var set so the llm probe has a credential to complete through,
   and the same six seams bound, **When** `_ComposeDockerSeam.verify()` is
   called, **Then** a committed test asserts the telegram double recorded zero
   calls **and** the LLM double recorded at least one — an engine upgrade must
   stop paging without stopping proving.
6. **Given** the four `install` doors, **When** each runs, **Then** a committed
   test asserts FR-007's parameter is present on both public entries with a
   default that leaves nothing un-run, **and** that each of those four doors
   passes it empty or leaves it defaulted, so `ergane install --verify` remains
   the one door that can deliver. The first half is what keeps this from being
   green on a test-only diff: the parameter does not exist today, so a test that
   reads it off the signature fails before the change and passes after.
7. **Given** a repository whose `ergane init --check` battery left the escalation
   and llm probes un-run and whose every other probe passed, **When** the check's
   one-line control-plane summary is built, **Then** a committed test asserts the
   summary finding **passes**, names the probes it proved and the probes it did
   not run as two separate lists under the unchanged `control_plane` slug, and
   that the finding is **not blocking**. Today that summary counts any finding
   that is not `passed` as a failed probe, so a diff that stops at FR-011 makes
   `ergane init --check` print `[FAIL] control_plane: 2 of 8 control-plane probes
   failed` and exit non-zero on a repository with nothing wrong with it.

## Functional Requirements

- **FR-001**: `EscalationProbe.gather` MUST prove the bot token by asking
  Telegram which bot it names and prove the chat id by resolving that chat, and
  MUST NOT send a message in order to establish either fact.
- **FR-002**: `EscalationSnapshot` MUST carry the proof separately from
  delivery, and `EscalationProbe.evaluate` MUST pass on the proof rather than on
  `delivered`, so a proven channel that was not paged is a pass. The proof is the
  verdict only when no send was attempted or the attempted send succeeded: a run
  whose send raised MUST fail, naming the send error, which is the truth table's
  fifth row. The detail MUST name the bot identity, the resolved chat, and
  whether this run delivered.
- **FR-003**: A test message MUST be delivered at most once per install. The
  decision MUST be made from a record read before the send, and the record MUST
  be written only after a send succeeds, so a failed send does not consume the
  one delivery. The write MUST sit outside the send's own exception boundary: a
  run that delivered but could not write its record MUST pass, reporting
  "delivered, not recorded" in its detail. Folding the write into the blanket
  `except Exception` at `factory/controlplane/verify.py:977` —
  `EscalationProbe.gather` would report a working channel as failed and then
  re-deliver on every later run, which is this spec's own defect rebuilt inside
  its fix.
- **FR-004**: The record MUST be keyed to the install whose config the battery
  was handed. `ControlPlaneConfig` MUST carry the path it was loaded from, and
  the probe MUST derive the record's location from that path — beside the config
  file it names — so a run against an explicitly passed config neither reads nor
  writes another install's record. When that value is not an absolute path — the
  case `parse_controlplane_config` leaves behind by defaulting `source` to the
  bare string `"config.toml"` — the probe MUST report the channel as proven but
  not delivered, naming that the config carries no path, and MUST NOT write a
  record beside the current working directory.
- **FR-005**: The adapter-`none`, non-telegram-adapter and unset-env-var early
  returns MUST keep their present outcomes and their detail strings unchanged,
  and none of them may reach the new proof.
- **FR-006**: The reversal MUST be recorded where the tree states the opposite:
  the scope note at `specs/033-ergane-install/spec.md:177-183` and the docstring
  at `tests/test_controlplane_verify.py:1191-1196`. The edit MUST leave every
  digest `factory/workgraph/delta.py:48` — `fingerprint_for` computes over
  `specs/033-ergane-install/spec.md` unchanged, and that equality — not a
  line-prefix grep — is what MUST be shown as evidence.
- **FR-007**: `verify_controlplane_async` and `verify_controlplane` MUST accept
  a caller-supplied collection of probe names to leave un-run, defaulting to
  none, and MUST NOT reorder or otherwise change `REGISTRY`.
- **FR-008**: A probe left un-run MUST still yield a finding under its own name,
  carrying `Severity.WARNING` and a detail naming why this door did not run it
  and which command does. It MUST NOT be silently absent from the report.
- **FR-009**: The battery's exit code MUST become a conjunction over `blocking`
  rather than over `passed`, so a `Severity.WARNING` finding does not fail the
  run; with nothing left un-run, every probe outcome reachable today MUST
  produce the same exit code it produces today.
- **FR-010**: `render_findings` MUST label each line with
  `factory/mergequeue/models.py:366` — `mark` rather than re-deriving a two-way
  PASS/FAIL, so a warning is not printed under the same label as a proof.
- **FR-011**: `_default_controlplane_probe` MUST leave both the escalation and
  the llm probes un-run, so no command reaching that seam — `ergane init
  --check`, a plain `ergane init`, or `ergane init --wire` — pages the operator
  or completes a token on any run.
- **FR-012**: `_ComposeDockerSeam.verify` MUST leave the escalation probe un-run
  and keep the rest of the battery, and the four `install` doors MUST continue to
  leave nothing un-run.
- **FR-013**: The one-line control-plane summary that `ergane init --check`
  renders MUST collapse the probe findings over `blocking` rather than over
  `passed`, and MUST name the probes it proved and the probes left un-run as two
  distinct lists inside that one line's detail. The slug MUST stay
  `control_plane`; no new onboarding finding may be introduced for the un-run
  probes. A probe left un-run MUST NOT fail the check: `ergane init --check` MUST
  still exit 0 on a repository whose only non-passing probes are ones a door
  deliberately left un-run.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-007, FR-008, FR-009, FR-010, FR-011, FR-012, FR-013]
```

One `depends_on_merged` edge, declared rather than left to be inferred
(069-US2 FR-007). It buys two things. First, correctness of sequencing: FR-008's
"left un-run" finding is a third answer in a grammar that has only two until
FR-002 splits proof from delivery, and FR-011 would otherwise have to invent the
same distinction twice. Second, freedom from contention: both stories edit
`factory/controlplane/verify.py` — US1 inside `EscalationProbe`, US2 inside the
two public entries and `render_findings` — and that is the only production file
they share, so serialising them costs one merge wait and removes the only
overlap. Everything else is disjoint: US1 also touches
`factory/controlplane/config.py`, US2 also touches `factory/cli/init.py`,
`factory/supervision/engine_upgrade.py` and `factory/mergequeue/onboard.py`.
