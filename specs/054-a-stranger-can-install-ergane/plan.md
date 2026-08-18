# Implementation Plan: a stranger can install Ergane

**Spec**: `specs/054-a-stranger-can-install-ergane/spec.md`

## What already exists, and where

Every anchor below was checked against the tree on 2026-08-17. Check them again
before you rely on one; a plan that cites a function which has since moved sends
you hunting for it.

| Thing | Where | Why it matters here |
| --- | --- | --- |
| The page-holds-true pattern | `tests/test_claude_md.py`, 304 lines | US1's whole enforcement model. Do not invent a second one. |
| Command extraction + resolution | same file: `_commands()` :52, `_verbs_of()` :79, `_split()` :87, `_help()` :110, `test_every_command_the_file_names_resolves` :115 | US1 reuses this machinery rather than re-deriving it |
| Anti-vacuity assertions | same file: :160, :204, :297 | The shape US1 must copy, three times |
| Path citation sweep | same file: `_paths()` :177, test :193 | US1's second sweep |
| The probe contract | `factory/controlplane/verify.py`: `REGISTRY` :567, sweep :585 | US2's new probe joins by appending to that list |
| The five current probes | same file: `LLMProbe` :186, `TemporalProbe` :281, `MemoryProbe` :371, `TelemetryProbe` :434, `EscalationProbe` :510 | Each is `.name` + `.gather(config)` + `.evaluate(snapshot)` |
| The finding grammar | `Finding(check, passed, detail)` from `factory.mergequeue.models`, imported at `verify.py:29` | Both new checks report in it |
| The hardcoded persona | `factory/controlplane/verify.py:195` — `persona = "implementer"` | US3's single-line subject, inside `LLMProbe.gather` |
| Registry loading | `factory.config.load_personas`, `REGISTRY_FILENAME` at `factory/config.py:41`, packaging note at `:49` | US3 reads the registry through this, never by path |
| The gateway-only refusal | `factory/controlplane/config.py`, `RULE_LLM_DIRECT_NOT_SUPPORTED` :60 and the refusal text ~:340 | US1 quotes the prerequisite; nothing changes it |
| A host probe that gets it wrong | `factory/cli/install.py:248` `_systemd_user_session_available()` | The exact shape US2 must not repeat — see trap 1 |

## Traps

These are named hazards, not advice. Each has already cost this factory time.

**1. The gate and CI are different machines, and a host probe is where that
bites.** The boundary gate runs under bwrap with `--clearenv`, no D-Bus socket,
no systemd user bus, a tmpfs `/tmp`, and `USER` unset. A GitHub runner has a
working user bus, `USER` set, and a full environment. A test that consults *real*
host state therefore passes in one and fails in the other **deterministically**,
and the agent that meets it will call it flaky, because in its own sandbox it
genuinely is green.

This is not hypothetical. On 2026-08-17, 042/US3 burned four attempts on exactly
this: the refusal test called the real `_systemd_user_session_available()`
(`factory/cli/install.py:248`, which shells out to `systemctl --user
daemon-reload`), so it was green in the gate and red on every CI run. Attempt 4
re-ran 3491 tests green and declared the failure a flaky runtime condition. The
repair was one line:

```python
monkeypatch.setattr(install_module, "_systemd_user_session_available", lambda: False)
```

US2 is a story *about probing the host*. Build the seam first and simulate
through it in every test. If any test you write would give a different answer on
your machine than in the gate, you have written the 042/US3 test again.

**2. A sweep that reads nothing passes.** Four tests in this repository have been
found structurally unable to fail. `tests/test_claude_md.py` defends against it
in three separate places (:160, :204, :297) and US1 must do the same: assert the
extracted command list is non-empty *and* contains `ergane install` and
`ergane init` by name. "The test passes" is not the claim; "the test would fail
if the page were wrong" is.

**3. Do not hand-roll a second command extractor.** `_commands()`, `_verbs_of()`,
`_split()` and `_help()` already parse a markdown page into runnable argv and
resolve each against the CLI's own `--help`. Reuse them — lift them into a shared
helper if you must — but two subtly different extractors in two files is how the
two pages drift apart, and the drift will be invisible because both suites stay
green.

**4. Read the persona registry through `load_personas`, never by path.** The file
is copied to `factory/personas.yaml` at build time so `importlib.resources` finds
it inside a wheel (`factory/config.py:49` says so explicitly). Reading
`personas.yaml` from the repo root works in a checkout and fails in the installed
package — and this repository has already had to prove a defect was *not* a
packaging fault by running both, so do not introduce one that is.

**5. US3 must not multiply spend.** The registry holds more personas than models.
Probe the set of **distinct dispatchable aliases**, once each — not once per
persona. Personas declared `agent: none` have no model by construction and must
be skipped, not probed and caught. And decide the fallback-alias question in the
code and hold it with a test; an omission there reads as an oversight forever.

**6. The judge sees the diff and the criteria. Nothing else.** No base tree, no
commit message, no terminal. SC-001's transcript is runtime evidence, so it must
be *committed as pasted output inside the diff*. 053/US1 shipped attempt 1
without its transcript and had to add it in attempt 2; write it the first time.

**7. `README.md` is an entry page, not a second standards channel.** Requirements
for how code is written belong to the standards path `factory.yaml` names, and
that separation was chosen deliberately so nothing depends on a file being
auto-loaded. `tests/test_claude_md.py` holds `CLAUDE.md` to that line. Hold the
README to it too: it orients an operator and stops.

**8. No status in the page.** Spec states, story counts and spend figures all
have live sources, and a copy rots between the day it is written and the day it
is read. US1-S5 makes this testable — point the reader at
`ergane spec list specs` rather than at a number.

**9. US2 and US3 both edit `factory/controlplane/verify.py`.** The declared edge
serialises them. Do not do US3's work inside US2 to save a round; the graph is
what the next reader will believe.

**10. The probe reports; it never remediates.** FR-010. A check that installs
`bwrap` for you is a check that needs privileges it should not hold, and the
supervision probe already established this line (042/US4: "watches, reports, and
never remediates"). Follow it.

## Sizing

Three small stories. US1 is a page plus one test module built on machinery that
already exists. US2 is one probe class, one seam, and its tests. US3 is a change
to `LLMProbe.gather` from one persona to a distinct-alias set, plus tests. None
should need a second attempt if the traps above are respected; trap 1 is the one
that decides whether US2 takes one attempt or four.

## Verification the operator will run, independent of the gate

A green suite is evidence, not proof — this repository has shipped a command that
could not start on a fully green run. So:

- **Run the page.** Follow `README.md` top to bottom on a host that satisfies the
  stated prerequisites, and dispatch something. That is SC-001, and it is the
  only check that catches a page which is *accurate but insufficient*.
- **Prove US2 by control, not by assertion.** Make `bwrap` unreachable on a
  scratch host (rename it on `PATH`) and confirm `ergane install --verify` emits
  the finding; restore it and confirm the finding clears. A test asserting the
  probe works is not the same claim as the probe working.
- **Prove US3 by mutation.** Point one persona at an alias the gateway does not
  know, run `--verify`, and confirm the finding names that alias *and* that the
  others still report. Then confirm the number of live completions equals the
  number of distinct aliases, not the number of personas.
