# Implementation Plan: install can be driven without a human

**Spec**: `specs/060-install-can-be-driven-without-a-human/spec.md`

## What already exists, and where

Most of this spec is exposing machinery that is already built and already
tested. Read these before writing anything new.

- `factory/cli/install.py:25` — the module docstring states the prompter is
  034/US1's seam (`factory.cli.init._prompter_factory`), "reused rather than
  reinvented: a second prompter convention one epic later is the drift". That
  sentence is this plan's central constraint.
- `factory/cli/install.py:169` — `_interview(path)`, which calls
  `init_module._prompter()` at :172 and then runs five sequential asks:
  `_ask_llm` (:179), `_ask_memory` (:180), `_ask_temporal` (:181),
  `_ask_telemetry` (:182), `_ask_escalation` (:183). A non-interactive path
  supplies a different prompter to the same five functions; it does not fork
  them.
- `factory/cli/install.py:118` — `add_install_arguments`, where the new flags go.
- `factory/cli/install.py:157` — `_write_config`, the single write point. FR-004
  says no partial artifact: refuse before reaching here.
- `factory/cli/init.py:273` — `_PLACEHOLDERS`, whose own comment calls these
  "Placeholder values that keep a partial manifest valid for full-parser
  checks". Note carefully: `gates: {test: "true"}` is declared a *placeholder*
  and then escapes into live manifests. This spec does not fix that (061/US3
  does), but FR-006's shared-defaults source is where the fix will attach, so do
  not build a second table that would have to be fixed twice.
- `factory/controlplane/config.py:48–51` — `KNOWN_ESC_ADAPTERS` and the comment
  describing the two-directional conformance contract with
  `factory.notify.adapter`'s registry. US3 must satisfy both directions.
- 033's scripted-prompter walkthrough harness — `tests/test_ergane_install_walkthrough.py`.
  055/US3's tests already reuse it. It is the test vehicle for US1 and US2; do
  not build a second one.

## Traps

These are named hazards, not advice.

**1. Do not fork the interview.** The temptation is a `_interview_from_file`
that mirrors `_interview`. Two interviews drift, and the drift is invisible
because both suites stay green. Supply a non-interactive *prompter* to the
existing five ask-functions. US1-S2 exists specifically to catch a fork: it
asserts both paths write identical configs from identical answers.

**2. Two defaults tables is the same bug one level down.** FR-006 and US2-S5
require one shared source. If `--non-interactive` gets its own dictionary of
defaults, it will disagree with the interactive path the first time either
changes, and no test will notice unless you write US2-S5 honestly.

**3. EOF is not consent, and this is the story that is easy to get backwards.**
Today, closing stdin accepts every default. FR-005 inverts that. Be careful that
your fix does not *also* break the legitimate non-interactive path — the
distinguishing signal is the explicit flag, not the state of stdin. Test both
combinations (US2-S1 and US2-S2) or you will ship one of them broken.

**4. The secret-shape guard must not be bypassable by file.** `_reject_secret_shape`
refuses a literal credential where an environment variable name belongs, and the
reporter called it out as one of the genuinely good guards in the system. A file
path that skips it converts a good guard into a decorative one. US1-S5 is the
test; write it early, because it is the one a reviewer will look for.

**5. A default applied silently is the defect this spec exists to fix.** FR-003
requires the applied default to be *reported*. The reporter's `/dev/null` run
"succeeded" and that success is what hid the no-op gate for the rest of the
session. Printing what was assumed is the whole difference between automation and
a silent misconfiguration.

**6. `"none"` must satisfy the conformance suite in both directions.**
`factory/controlplane/config.py:48` is explicit: a name in the config roster with
nothing registered pages nobody, and a registered name missing from the roster is
not selectable. Adding `"none"` to `KNOWN_ESC_ADAPTERS` without a corresponding
registration will fail that suite — which is the suite working correctly. Decide
whether `"none"` is a registered null adapter or an explicit exemption, and hold
whichever you choose with a test.

**7. The escalation-off finding must not fail the run.** US3-S3. It is a declared
choice. If `--verify` exits non-zero on it, an operator evaluating Ergane can
never reach a green install, which is the exact friction this story removes.

**8. Read the persona registry through `load_personas`, never by path.** Carried
forward from 054's trap 4 and still live: the file is package data
(`factory/config.py:49`), so reading it from the repo root works in a checkout
and fails in the installed package. If any part of the answer-file work touches
the registry, go through the loader. Note that 062 changes this resolution — if
062 has landed when you start, re-read `factory/config.py` before assuming.

**9. The judge sees the diff and the criteria. Nothing else.** SC-001 and SC-002
are runtime evidence and must be **committed as pasted output inside the diff**.

**10. US1 and US2 both touch the prompter seam; US3 is independent.** Declare
US1 → US2 as an edge. US3 may run in parallel with either, since it edits the
control-plane config and the notify registry rather than the CLI.

## Sizing

Three stories. US1 and US2 are each a flag, a prompter implementation, a
defaults source, and tests against a harness that already exists — small,
provided trap 1 is respected and the interview is not forked. US3 is a roster
entry, a null adapter or exemption, a verification finding, and tests.

The largest risk to sizing is trap 1: an implementer who forks the interview
will produce a large diff that fails US1-S2 and has to be rewritten.

## Verification the operator will run, independent of the gate

- **Prove US1 by doing it.** On a scratch host, write an answer file, run
  `ergane install --from-file` with `0<&-`, and then run `ergane install
  --verify`. SC-001. Paste the transcript.
- **Prove US2 by control.** Run `ergane init` with stdin closed and *no* flag;
  confirm non-zero and confirm no `ergane.yaml` exists afterwards. Then add the
  flag and confirm it completes. Same command, opposite outcomes, one flag apart.
- **Prove the documented example by using it.** SC-003. Copy the worked example
  out of the docs without editing it and drive an install with it. A documented
  format nobody has run is a documented format that is wrong.
- **Prove US3 by absence.** On a host with no Telegram token set at all, complete
  install and `--verify` to a green result. SC-004.
