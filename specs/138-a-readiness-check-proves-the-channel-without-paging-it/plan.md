# Implementation Plan: a readiness check proves the channel without paging it

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**The whole probe is fifty lines and the send is the last thing in it.**
`factory/controlplane/verify.py:925` — `EscalationProbe` opens with a docstring
that states today's contract — "Delivers a test message through the configured
Telegram transport" — and `factory/controlplane/verify.py:934` — `EscalationProbe.gather`
ends at `factory/controlplane/verify.py:963-968`:

```python
        try:
            bot = _telegram_bot_factory(config.escalation, timeout_s=config.escalation.timeout_s)
            message = await bot.send_message(
                chat_id=chat_id,
                text="ergane install --verify test message",
            )
```

Above it are three early returns and nothing else:
`factory/controlplane/verify.py:935` — `EscalationProbe.gather` (adapter
`none`), `factory/controlplane/verify.py:945` — `EscalationProbe.gather`
(non-telegram adapter), and `factory/controlplane/verify.py:956` — `EscalationProbe.gather`
(either env var unset). No state read, anywhere, before the send. That is why
FR-003 is structural: there is nothing in this function to hang a condition on.
Below it, `factory/controlplane/verify.py:977` — `EscalationProbe.gather` is a
blanket `except Exception` that turns anything raised in that block into "could
not deliver telegram test message". FR-003's record write must not land inside
it.

**The judgment reads the delivery as the verdict.**
`factory/controlplane/verify.py:984` — `EscalationProbe.evaluate` is five lines,
and `factory/controlplane/verify.py:987` — `EscalationProbe.evaluate` is the
whole problem:

```python
        passed = snapshot.delivered
```

`factory/controlplane/verify.py:119` — `EscalationSnapshot` carries
`adapter`, `delivered` and `detail` and nothing else, so there is no field for
"proved" to live in. FR-002 splits them.

**The bot seam is already the right shape, and already builds a real client.**
`factory/controlplane/verify.py:222` — `_telegram_bot_factory` builds a genuine
`telegram.Bot` with an `HTTPXRequest` whose three timeouts come from the
escalation block. It is the module's established idiom for an outward reach and
is patched by name in every test; `get_me()` and `get_chat()` are methods on the
same `Bot`, so FR-001 needs no new seam — only two more calls through the one
that exists.

**The config does not know where it came from, and one of the two ways in
defaults its label to a bare filename.**
`factory/controlplane/config.py:114` — `ControlPlaneConfig` has six fields and
no path.
`factory/controlplane/config.py:230` — `load_controlplane_config` resolves the
path at `factory/controlplane/config.py:237` — `load_controlplane_config`, keeps
it as `label` at `factory/controlplane/config.py:238` — `load_controlplane_config`,
and hands that label to `factory/controlplane/config.py:270` — `parse_controlplane_config`,
whose own signature at `factory/controlplane/config.py:271` — `parse_controlplane_config`
defaults `source` to the string `"config.toml"`. So the value FR-004 needs is
already threaded through the parser as a diagnostic label; it just never lands on
the object, and for a direct `parse_controlplane_config` call it is not a path at
all. The construction to extend is
`factory/controlplane/config.py:289-296` — `parse_controlplane_config`.

**The two public entries take one argument between them, and neither of the two
diagnostic doors passes it.**
`factory/controlplane/verify.py:1198` — `verify_controlplane_async` resolves the
config at `factory/controlplane/verify.py:1202` — `verify_controlplane_async`,
walks `REGISTRY` (`factory/controlplane/verify.py:1183-1192`) and computes its
verdict at `factory/controlplane/verify.py:1221` — `verify_controlplane_async`:

```python
    exit_code = 0 if all(f.passed for f in findings) else 1
```

`factory/controlplane/verify.py:1225` — `verify_controlplane` is a two-line sync
wrapper. Both need the new parameter; nothing else in the walk changes. The
`try` at `factory/controlplane/verify.py:1205` — `verify_controlplane_async`
wraps `probe.gather` only, not the config load above it — which is trap 12.

**Two renderers, and only one of them prints a line per probe.**
`factory/controlplane/verify.py:1230` — `render_findings` is the per-probe one:
`ergane install --verify` prints through it at
`factory/cli/nouns/install.py:43` — `_verify_command`, and the engine-upgrade
report at `factory/cli/nouns/engine.py:34` — `_upgrade` prints through it too.
`ergane init --check` does **not**: `factory/cli/init.py:2292` — `render_check`
loops over `profile.findings` at `factory/cli/init.py:2319` — `render_check` and
prints one line per *onboarding* finding, and the whole control-plane battery
reaches that loop as the single `control_plane` finding built by
`factory/mergequeue/onboard.py:577` — `_control_plane_finding`. That asymmetry is
the design FR-013 keeps: the un-run probes are named inside one line's detail,
never as new slugs (trap 11).

**The three-way label already exists and this module re-derives a two-way one.**
`factory/controlplane/verify.py:1230` — `render_findings` is
`status = "PASS" if finding.passed else "FAIL"` at
`factory/controlplane/verify.py:1234` — `render_findings`, while
`factory/mergequeue/models.py:366` — `mark` already returns `PASS`, `WARN` or
`FAIL` and says in its own docstring why it is spelled once: "a warning rendered
as `FAIL` in one of them is the report contradicting the exit code beside it".
`factory/mergequeue/models.py:351` — `Finding` already carries `severity`
defaulting to `Severity.ERROR`, and `factory/mergequeue/models.py:354` — `Finding.blocking`
is `not self.passed and self.severity == Severity.ERROR`.
FR-008, FR-009 and FR-010 are three uses of machinery that is already here.
`factory/cli/init.py:2319` — `render_check` already prints `finding.mark`, so
the init door needs no renderer edit at all.

**The six doors.** `factory/cli/nouns/install.py:40` — `_verify_command`;
`factory/cli/install.py:954` — `install_command`;
`factory/cli/install.py:1185` — `_install_non_interactive`;
`factory/cli/install.py:1279` — `_install_from_file`;
`factory/cli/init.py:170` — `_default_controlplane_probe` (bound to the seam at
`factory/cli/init.py:178`, reached from `factory/cli/init.py:2137` — `_control_plane_facts`
at `factory/cli/init.py:2146` — `_control_plane_facts`); and
`factory/supervision/engine_upgrade.py:103` — `_ComposeDockerSeam.verify`,
declared on the protocol at `factory/supervision/engine_upgrade.py:37` — `DockerSeam.verify`.
The document's prose named `repo onboard` and `repo rebuild` as two more; they
reach no `verify_controlplane` caller and are not doors. Do not go looking for
them.

**The recording doubles this spec's tests need already exist, and one of them is
one method wide.** `tests/test_controlplane_verify.py:579` — `_FakeTelegramBot`
records `send_message` kwargs and returns `SimpleNamespace(message_id=42)`; it
implements `send_message` at
`tests/test_controlplane_verify.py:585` — `_FakeTelegramBot.send_message` and
nothing else. `tests/test_controlplane_verify.py:590` — `_FakeTelegramFactory`
returns it for every escalation config, and the fixture at
`tests/test_controlplane_verify.py:609` — `fake_subsystems` binds both it and
the LLM factory. Extending the bot double is US1's first edit, not an
afterthought (trap 6).

**The live double the reversal has to be argued in front of.**
`tests/test_controlplane_verify.py:1187` — `test_verify_escalation_gather_against_live_double`
points a real `telegram.Bot` at the loopback listener built by
`tests/test_controlplane_verify.py:417` — `_loopback_telegram_listener`, and its
docstring at `tests/test_controlplane_verify.py:1191-1196` says "The real
send_message path executes, including the HTTPXRequest timeout wiring". That
listener answers Telegram's HTTP API shape, so `get_me` and `get_chat` need
routes added to it, not a second double.

**The tree's own sentence about this defect** is
`tests/test_ergane_init_check.py:193` — `bind_offline_seams`: an unbound seam
"would spawn the real `gh` and deliver a real Telegram probe". The defence is
`tests/test_ergane_init_check.py:258` — `bind_offline_seams`, which rebinds
`_controlplane_probe` for every offline test — the exact seam US2-S4 must not
rebind (trap 4), which is why US2-S4 needs trap 12's replacement instead.

## Traps

**Trap 1 — Stop sending and the probe starts FAILING, everywhere, on every
door.** `factory/controlplane/verify.py:987` — `EscalationProbe.evaluate` is
`passed = snapshot.delivered`. An implementer who does the obvious thing first —
replace the `send_message` in `gather` with `get_me`/`get_chat` — turns every
healthy install's escalation finding red, and because
`factory/controlplane/verify.py:1221` — `verify_controlplane_async` is a
conjunction, turns `ergane install --verify` non-zero on a working system. FR-002
is not a nicety: `EscalationSnapshot`
(`factory/controlplane/verify.py:119` — `EscalationSnapshot`) must gain the
proof as its own field and `evaluate` must judge on that field before `gather`
stops sending. Write those two edits in the same commit as the first.

**Trap 2 — `gather` cannot tell which install it is running against, and the
obvious fix is wrong for three of the six doors.** `gather` receives only
`ControlPlaneConfig`, which carries no path
(`factory/controlplane/config.py:114` — `ControlPlaneConfig`). The tempting
shortcut is to call `factory/controlplane/config.py:207` — `resolve_config_path`
from inside the probe. That reads the *environment*, and
`factory/cli/install.py:954` — `install_command`,
`factory/cli/install.py:1185` — `_install_non_interactive` and
`factory/cli/install.py:1279` — `_install_from_file` all call
`verify_controlplane(str(path))` with an **explicit** path — during an install,
before that path is necessarily what the environment resolves to. The record
would be read from and written to the wrong install. FR-004 requires the path to
travel on the object. US1-S4's three-run sequence is what catches this: a
`resolve_config_path()`-keyed record makes the second install's delivery vanish.

Two consequences of that same requirement. `factory/controlplane/config.py:271` — `parse_controlplane_config`
defaults `source` to the literal string `"config.toml"`, so a config built by a
direct parse carries a bare filename, not a path. Derive the record location
only from an absolute path, and when there is none report the channel as
**proven but not delivered**, naming that the config carries no path, rather
than writing a record beside the current working directory. Do not report it as
unproven: `get_me` and `get_chat` answered, so the channel *is* proved, and a
FAIL there would contradict FR-002 on a healthy install. FR-004's closing
sentence is the requirement behind this branch, US1-S9 is the scenario that
holds it and T006 is its test; this trap only says why the other two spellings
are wrong. The branch is not hypothetical: four production call sites and seven
test modules call `factory/controlplane/config.py:270` — `parse_controlplane_config`
directly with a label like `"rendered"` or `"fixture.toml"`, so it is reachable
the day this story lands and must not ship as prose in a task.
And `tests/test_container_manifest.py:45` — `_config`
and `tests/test_container_project.py:53` — `_config` both construct
`ControlPlaneConfig` directly today, so the new field must carry a default or two
unrelated test modules go red for a reason this story is not about.

**Trap 3 — Revising 033 in the wrong region reopens a landed story.** FR-006
names two edits, and both are prose. `factory/workgraph/delta.py:48` — `fingerprint_for`
computes a landed story's identity from exactly four things, listed at
`factory/workgraph/landed.py:438` — `_story_parts`: the story title, its
acceptance-scenario texts, the bodies of the FRs it implements, and its Work
Graph declaration. `specs/033-ergane-install/spec.md:211-215` is US2's
acceptance scenario 3 and it says a test message "is delivered through it" —
which is exactly the sentence an implementer will want to correct. Correcting it
changes 033-US2's fingerprint, and a delta derivation then reopens a story that
landed on 2026-08-16. Leave it as the historical record and put the reversal in
the scope note at `specs/033-ergane-install/spec.md:177-183`, which is prose no
fingerprint reads.

**And do not check this with a line-prefix grep — the obvious guard has a blind
spot shaped exactly like the tempting edit.** `specs/033-ergane-install/spec.md:211`
is `3. **Given** an escalation transport configured, **When** verify runs,`: it
begins `3. `, not `**Given**`. The sentence "a test message is delivered through
it" is on `specs/033-ergane-install/spec.md:212`, and
`specs/033-ergane-install/spec.md:212-215` begin with `**Then**` and with plain
continuation words. A rule of the form "no changed line begins `### User Story`,
`**Given**` or `- **FR-`" therefore passes an edit that rewrites the whole
scenario, because `factory/workgraph/landed.py:438` — `_story_parts` fingerprints
each scenario's *raw text*, not its first line. The check that actually guards is
the one the delta itself computes — compare digests before and after.

**And baseline the "before" on a revision that predates your own edit, never on
`HEAD`.** T015 pastes this output as committed evidence in the same diff as the
033 edit, and operator step 7 runs it after the story has landed: by then `HEAD`
*is* the edit, so a `HEAD`-baselined comparison prints `UNCHANGED` for every edit
anyone could make, including the one that reopens 033-US2. Run it against
`602a92c`, the sha this trio was drafted and anchored at:

```bash
python - <<'PY'
import pathlib, subprocess
from factory.workgraph.delta import fingerprint_for
path = "specs/033-ergane-install/spec.md"
before = subprocess.run(["git", "show", f"602a92c:{path}"],
                        capture_output=True, text=True, check=True).stdout
after = pathlib.Path(path).read_text()
for key in ("US1", "US2", "US3"):
    b, a = fingerprint_for(before, key).digest, fingerprint_for(after, key).digest
    print(key, "UNCHANGED" if a == b else "CHANGED", a)
PY
```

Three `UNCHANGED` lines is the proof; anything else means the edit landed in a
fingerprinted region and the story is about to reopen. Measured against
`602a92c`: this snippet prints `US2 CHANGED` for a rewrite of 033-US2's scenario
3 and three `UNCHANGED` lines for the scope-note edit FR-006 actually asks for,
so it discriminates rather than merely running. If another epic has edited
`specs/033-ergane-install/spec.md` between `602a92c` and this story's base,
baseline instead on this branch's merge-base with `ergane-buildout` — any
revision that predates your own edit works, and `HEAD` is the one that does not.
US1-S8, T015 and operator step 7 all name this comparison, with this baseline,
and not a grep.

**Trap 4 — The fixture that makes init's tests safe is the fixture that would
make US2-S4 vacuous.** `tests/test_ergane_init_check.py:180` — `bind_offline_seams`
ends by rebinding `_controlplane_probe` at
`tests/test_ergane_init_check.py:258` — `bind_offline_seams`. Every existing
init test therefore never executes `_default_controlplane_probe` at all. A US2
test written by importing that helper — the natural move, since forty test
modules already do — would assert that a *stub* did not page anyone. FR-011's
test must call `_default_controlplane_probe()` itself, under the seam and config
discipline trap 12 spells out, and assert on the telegram and LLM doubles' call
lists.

**Trap 5 — A `WARNING` finding fails the run until the verdict is changed, and
prints as `FAIL` until the report is.** `factory/controlplane/verify.py:1221` — `verify_controlplane_async`
is `all(f.passed for f in findings)` and
`factory/controlplane/verify.py:1234` — `render_findings` is
`"PASS" if finding.passed else "FAIL"`. A left-un-run finding is `passed=False`
with `Severity.WARNING`, so without FR-009 and FR-010 `ergane install --verify`
would exit non-zero and print `[FAIL] escalation` for a probe it deliberately
skipped — a worse report than today's. Both edits are small and neither is
optional. Do not reach for `passed=True` to dodge them: a pass is a claim the
channel was proven, and this run proved nothing.

**Trap 6 — The bot double implements one method, and every escalation test in
the file runs through it.** `tests/test_controlplane_verify.py:579` — `_FakeTelegramBot`
has `send_message` and nothing else. The moment `gather` calls `get_me`,
`tests/test_controlplane_verify.py:789` — `test_verify_escalation_probe_delivers_and_defers`
and every other test using the `fake_subsystems` fixture raises `AttributeError`
inside the probe — and one of two blanket handlers eats it before anyone sees the
word `AttributeError` in a place that suggests a double. A proof call written
inside the existing `try` is caught by `EscalationProbe.gather`'s own
`except Exception` at `factory/controlplane/verify.py:977` —
`EscalationProbe.gather` and comes back as "could not deliver telegram test
message: AttributeError: ..." — which, once FR-002 gives the proof its own
`try` so a refused credential can be named, reads instead as a bogus bad-token
verdict. A proof call written above that `try` escapes to
`factory/controlplane/verify.py:1210` — `verify_controlplane_async` and comes
back as "probe failed unexpectedly". Both spellings blame the change rather than
the double, and both cost the same attempt. Add `get_me` and `get_chat` to
the double first. The same applies to the loopback listener at
`tests/test_controlplane_verify.py:417` — `_loopback_telegram_listener`, which
serves Telegram's HTTP shape and needs the two routes for
`tests/test_controlplane_verify.py:1187` — `test_verify_escalation_gather_against_live_double`
to keep passing.

**Trap 7 — The unset-env case is guarded twice, and only one of the guards is
the one FR-005 is about.** `factory/controlplane/verify.py:956` — `EscalationProbe.gather`
returns a snapshot naming the missing variable, and
`factory/controlplane/verify.py:222` — `_telegram_bot_factory` *also* raises
`ServiceNotAnswering` when the token is unset, which
`factory/controlplane/verify.py:1207` — `verify_controlplane_async` catches into
a different finding with different text. A test for US1-S7 that asserts only
"the run fails when the token is unset" passes through either path and proves
nothing. Assert the literal detail string the early return produces, and assert
the bot factory was never called.

**Trap 8 — Do not give the probe an adapter seam, and do not touch the llm
probe.** 033's split assigned the adapter seam to 041
(`specs/033-ergane-install/spec.md:177-183`), and that half of the split still
stands; this spec reverses the delivery claim only. Likewise FR-011 leaves the
llm probe *un-run by one door*; it does not add a cheap mode to
`factory/controlplane/verify.py:428` — `LLMProbe.gather`. Editing that method
would change what `ergane install --verify` proves, which is the one thing every
door still depends on.

**Trap 9 — `getMe` exists nowhere in this tree, and the near-miss is in a test
double in another spec's history.** `grep -rn "getMe\|get_me\|getChat\|get_chat"
factory/` returns one hit, `factory/notify/redact.py:202` — `_redact_record`,
and it is `record.getMessage()` on a log record. Spec 064 (`eb23d98`) has a
`getMe` route inside a loopback double that is not in this tree. An implementer
who finds it in history will read it as production precedent; it is not one.

**Trap 10 — Four doors must keep the full battery, and the diff is how that is
proven.** FR-012's second half is a control, and the wrong move is to "tidy" the
four `install` call sites by giving them the same exclusion for consistency. If
`ergane install --verify` stops delivering, the once-per-install delivery has no
door left to happen on and the escalation channel is never exercised by anything
until a node parks — which is the failure this spec exists to prevent, arrived at
from the other side.

**Trap 11 — The finding `ergane init --check` actually renders is a COLLAPSE,
and it counts a warning as a failed probe.** This is the trap that makes the
readiness command fail on a healthy repository.
`factory/mergequeue/onboard.py:577` — `_control_plane_finding` folds all of
033's probe findings into one `control_plane` finding, and its test is
`factory/mergequeue/onboard.py:608` — `_control_plane_finding`:

```python
    for probe in facts.control_plane:
        if not probe.passed:
            failed.append(probe)
```

A probe left un-run is `passed=False` with `Severity.WARNING`, so it lands in
`failed`, the summary becomes `Finding("control_plane", False, ...)` at
`factory/mergequeue/onboard.py:628` — `_control_plane_finding` with the default
`Severity.ERROR`, and `ergane init --check` prints
`[FAIL] control_plane: 2 of 8 control-plane probes failed` and **exits non-zero
on a repository with nothing wrong with it** — `REGISTRY` holds exactly eight
probes (`factory/controlplane/verify.py:1183-1192`) and FR-011 leaves two of
them un-run. The reports a plain `ergane init` and `ergane init --wire` end with
carry the same `[FAIL]` line, though their own exit codes do not change:
`factory/cli/init.py:1355` — `init_command` reports that verdict rather than
returning it, while `factory/cli/init.py:1149` — `init_command` returns it. An
implementer who stops at FR-011 will have a green unit suite for `verify.py`, a
green judge, and a readiness command that fails on every healthy install the
first time it is run for real.

**And it stops exactly there — do not widen this trap into a dispatch story.**
`factory/mergequeue/onboard.py:417` — `evaluate_init_facts` is the only caller of
`_control_plane_finding` (the call is at `factory/mergequeue/onboard.py:438`),
and it returns `()` the moment its facts are absent
(`factory/mergequeue/onboard.py:429-430`). `InitFacts` is constructed in exactly
one place, `factory/cli/init.py:2244`, reached only through
`factory/cli/init.py:2269` — `check_repo`; the dispatch preflight
(`factory/activities/merge_activities.py:785`) and the offline `repo onboard`
command (`factory/workgraph/cli.py:532`) both call `onboard_target_repo` with no
init facts at all. So no control-plane finding of any kind reaches the profile
the roadmap parks a spec on at `factory/roadmap/workflow.py:1263`: missing FR-013
costs one command's exit code, not a halted floor. Say it that way in the PR, and
do not let the size of the word "parks" talk you into a second finding slug.
FR-013 requires the same conjunction change here
that FR-009 makes in `factory/controlplane/verify.py:1221` — `verify_controlplane_async`:
collapse over `factory/mergequeue/models.py:354` — `Finding.blocking`, and name
the un-run probes as their own list beside the proven ones at
`factory/mergequeue/onboard.py:619` — `_control_plane_finding`. The slug stays
`control_plane`, so the two tests that assert `init --check`'s exact set of
finding slugs — `tests/test_ergane_init_check.py:301` — `test_a_scaffolded_registered_wired_repo_passes_every_finding`
and `tests/test_ergane_init_check.py:490` — `test_both_doors_render_identical_parity_findings`,
both amended by 057 on 2026-09-03 — keep passing without an edit. Do not add a
new slug to make the un-run probes visible; a new slug is what breaks them, and
it is also what the operator sequence below deliberately does not ask for.

**Trap 12 — `_default_controlplane_probe` passes no config path, so a test that
binds only the two doubles it asserts on aims the whole battery at whatever
control plane the machine running it has.** This is trap 4's other half and the
one that reproduces the near-miss the spec's provenance records.
`factory/cli/init.py:174` — `_default_controlplane_probe` is
`return verify_controlplane()`, and
`factory/supervision/engine_upgrade.py:106` — `_ComposeDockerSeam.verify` is the
same line. `factory/controlplane/verify.py:1202` — `verify_controlplane_async`
therefore calls `load_controlplane_config(None)`, which at
`factory/controlplane/config.py:237` — `load_controlplane_config` falls through
to `factory/controlplane/config.py:207` — `resolve_config_path` and reads the
host's `~/.config/ergane/config.toml`. Both outcomes cost an attempt. With no
config on the node's HOME, the load raises *above* the `try` at
`factory/controlplane/verify.py:1205` — `verify_controlplane_async` — which
wraps `probe.gather` and nothing else — so the test errors on a line no task
mentions. With a config present, the walk over `REGISTRY`
(`factory/controlplane/verify.py:1183-1192`) runs the temporal, memory, forge,
host and telemetry probes for real, over the network.

So US2-S4 and US2-S5 must write a temporary config, point `ERGANE_CONFIG_PATH`
at it, and bind **every** outward seam the battery reaches, not only the two
being asserted on: `factory/controlplane/verify.py:222` — `_telegram_bot_factory`,
`factory/controlplane/verify.py:168` — `_llm_client_factory`,
`factory/controlplane/verify.py:178` — `_temporal_client_factory`,
`factory/controlplane/verify.py:216` — `_memory_client_factory`,
`factory/controlplane/verify.py:384` — `_host_seam_factory` and
`factory/controlplane/verify.py:395` — `_forge_capability_seam_factory`.
`factory/controlplane/verify.py:849` — `TelemetryProbe` has no seam — it builds
its own `httpx.AsyncClient` — so the temporary config must declare telemetry off
and let it take its `mode == "none"` early return. The idiom is already in the
file: `tests/test_controlplane_verify.py:789` — `test_verify_escalation_probe_delivers_and_defers`
writes the config, sets `ERGANE_CONFIG_PATH` and binds the temporal seam, and
`tests/test_controlplane_host_probe.py:277` — `test_module_does_not_call_real_host`
is an AST guard that already records half of this rule for that module. US2-S5
needs one thing more: its config must declare a gateway and its master-key env
var must be set, or `factory/controlplane/verify.py:428` — `LLMProbe.gather`
takes its "no credential" early return and the double records nothing, which is
the assertion US2-S5 exists to make.

## Sizing

US1 touches `factory/controlplane/verify.py` (inside `EscalationProbe` and the
`EscalationSnapshot` dataclass), `factory/controlplane/config.py` (one field and
one keyword at the construction), `specs/033-ergane-install/spec.md` (the scope
note paragraph only) and `tests/test_controlplane_verify.py` (the two doubles,
the live-double docstring, and the new tests).

US2 touches `factory/controlplane/verify.py` (the two public entries and
`render_findings`), `factory/cli/init.py` (`_default_controlplane_probe`),
`factory/supervision/engine_upgrade.py` (`_ComposeDockerSeam.verify`),
`factory/mergequeue/onboard.py` (`_control_plane_finding` alone, lines 577-635)
and its tests. It must not edit `EscalationProbe`, it must not edit
`factory/controlplane/verify.py:428` — `LLMProbe.gather`, and it must not edit
`factory/cli/init.py:2292` — `render_check`, which already prints `finding.mark`.

The two stories share exactly one production file,
`factory/controlplane/verify.py`, and touch disjoint regions of it — US1 the
`EscalationSnapshot` dataclass at `factory/controlplane/verify.py:119` — `EscalationSnapshot`
and the class body at `factory/controlplane/verify.py:925-991`, US2 lines
1183-1236. The `depends_on_merged` edge serialises them so that overlap never
becomes a merge conflict. Every other production file is named by one story only:
`factory/controlplane/config.py` by US1; `factory/cli/init.py` and
`factory/supervision/engine_upgrade.py` by US2.

**Eight other drafts name a file this spec edits**, and the survey below is over
every unlanded spec in `specs/`, not only the recent batch. They are disjoint by
line, not by file, so the risk is a merge conflict rather than a
wrong answer — an operator scheduling fact, not a requirement.
`factory/cli/init.py` has three neighbours and this spec's only edit there is
`factory/cli/init.py:170` — `_default_controlplane_probe`: spec 129's US3 works
at `factory/cli/init.py:2088` — `resolve_repo_runtime_root` and
`factory/cli/init.py:1831` inside `_write_scaffold`; spec 139's US2 and US4 work
at `factory/cli/init.py:1816` — `_write_scaffold` and the `written:` block at
`factory/cli/init.py:1326-1331`; neither comes near line 170.
`factory/mergequeue/onboard.py` has one: spec 128 edits
`factory/mergequeue/onboard.py:162` — `evaluate_repo` and
`factory/mergequeue/onboard.py:340` — `_noop_gate_finding`, some two hundred
lines above this spec's `factory/mergequeue/onboard.py:577` — `_control_plane_finding`
— but 128's US2 also *extends*
`tests/test_ergane_init_check.py:490` — `test_both_doors_render_identical_parity_findings`,
which trap 11 requires to keep passing untouched, so if both epics are in flight
read that test before assuming it still says what trap 11 quotes.
`factory/controlplane/verify.py` has four, and none of them lands on either
region this spec edits. Spec 132 edits
`factory/controlplane/verify.py:428` — `LLMProbe.gather`, which this spec is
forbidden to touch (trap 8). Spec 080 is the closest call: it cites the same
public entry, `factory/controlplane/verify.py:1198` — `verify_controlplane_async`,
that US2 changes, but only as the caller its probe must resolve *from* — its own
tasks say at `specs/080-a-probe-tests-the-endpoint-the-attempt-will-use/tasks.md:180`
that `render_findings` needs no change, and its edits are in
`factory/controlplane/verify.py:428` — `LLMProbe.gather` and the message sites
below it. Spec 112 quotes `factory/controlplane/verify.py:984` — `EscalationProbe.evaluate`
at `specs/112-a-subscription-is-a-starting-position/plan.md:434` as the *shape*
its own probe should copy, and edits the telemetry and LLM probes rather than
this one — but FR-002 changes the very `evaluate` it quotes, so if 112 is
refined after this spec lands, that citation is the line to re-read. Spec 074
migrates `factory/controlplane/verify.py:178` — `_temporal_client_factory` and a
comment inside the temporal probe's `gather`
(`specs/074-a-test-cannot-reach-the-operators-floor/plan.md:101`), several
hundred lines from both regions. `factory/controlplane/config.py` has one: spec 145's
US1 edits the comment at `factory/controlplane/config.py:41-42`, four hundred
lines from this spec's `factory/controlplane/config.py:114` — `ControlPlaneConfig`.
Spec 141 names `factory/mergequeue/onboard.py` only to forbid itself from
opening it, so it is not a neighbour at all.

Both stories are well inside the 64 KiB deterministic diff bound (D-050). US1 is
roughly seventy production lines plus two double extensions and nine tests; US2
is under forty production lines plus seven tests. The pasted evidence each
verification task asks for is two short reports, not a transcript — and note that
the `--verify` report is five lines, so pasting it twice costs nothing.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only, so
runtime evidence must be committed as pasted output. Beyond that:

1. Against the operator's own install, run `ergane install --verify` twice in a
   row. The first run may deliver one Telegram message; the second must deliver
   none, and both must report the escalation check as passing and name the bot
   and the chat. This is the eight-messages-in-thirteen-minutes measurement, run
   forwards.
2. Break the chat id (point `TELEGRAM_CHAT_ID` at a chat the bot is not in) and
   re-run `--verify`. The escalation finding must fail naming the chat id, and no
   message may arrive on the good chat.
3. Run `ergane init --check` in a repository five times in a row. No message may
   arrive and no completion may appear in the gateway's spend log.
4. Read that report. It must carry exactly one `control_plane` line, it must read
   as a **pass**, and its detail must name the probes it proved and, as a
   separate list, `escalation` and `llm` as not run. There must be no `escalation`
   line and no `llm` line: `factory/cli/init.py:2292` — `render_check` prints one
   line per onboarding finding and
   `factory/mergequeue/onboard.py:577` — `_control_plane_finding` collapses the
   whole battery into that one, so a per-probe `[WARN]` line here would mean a
   new slug was added and trap 11's two exact-slug tests are about to break. A
   `[FAIL] control_plane` line here is trap 11 the other way: the readiness
   command now exits non-zero on a repository with nothing wrong with it. It
   halts no dispatch — trap 11's closing paragraph says why — but this is the
   command an operator runs to decide whether a repository is ready, so run it
   before anything else is believed.
5. Compare the gateway's spend log across step 3 — five `init --check` runs must
   add zero entries where they previously added five. That is the half of the
   init key that is not about the phone, and it is the only step that measures
   it.
6. Run the engine-upgrade verification against a container. That report *is*
   rendered per probe, through `factory/cli/nouns/engine.py:34` — `_upgrade`, so
   a `[WARN] escalation` line is expected and correct here. No message may
   arrive, and the LLM finding must still be a real round trip — a `[WARN] llm`
   line here means FR-012 was implemented as a copy of FR-011 and the upgrade
   verdict has been hollowed out. The same per-probe shape is what step 1's
   `--verify` report prints, through
   `factory/cli/nouns/install.py:43` — `_verify_command`.
7. Re-run `ergane spec validate specs/033-ergane-install --target-repo .` after
   the 033 edit, then run trap 3's digest comparison — the fenced snippet in that
   trap, baselined on `602a92c` exactly as it is written there — and confirm it
   prints `UNCHANGED` for every one of 033's story keys. By the time you run this
   the edit is committed, so `git show HEAD:` would return the edited text and
   the comparison would read `UNCHANGED` no matter what was changed; the fixed
   baseline is the whole point. That, and not a grep, is trap 3 checked
   mechanically:
   `factory/workgraph/landed.py:438` — `_story_parts` fingerprints each
   scenario's whole raw text, and 033-US2's scenario 3 begins `3. ` while the
   sentence an implementer wants to fix sits on lines beginning `**Then**`, so
   every line-prefix rule anyone would write passes the one edit that reopens a
   landed story.

Step 1 and step 5 together are the falsifiable test of the whole spec: one
proves the channel stopped shouting, the other proves the diagnostic stopped
spending. Step 4 is the one that fails loudest if trap 11 was missed — in either
direction, a `[FAIL] control_plane` line or a new slug.
