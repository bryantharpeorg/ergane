# US4 evidence: the on-ramp exercise

Runtime evidence for 061/US4, pasted verbatim (constitution VIII, trap 11).

Trap 15: this sandbox has no live GitHub, `gh` credentials or gateway, so the
live run (SC-004) and the revert drill (SC-005) are the operator's verification
after landing, per `docs/onramp-exercise.md`. Here is what US4-S1 names as diff
evidence — the skip transcript (US4-S4) and the simulated per-stage drives
(US4-S2) — plus controls showing those tests fail when the property they check
is removed.

```text
$ uv run pytest -q     # the gate, before this story's first commit
4076 passed, 49 skipped, 7 warnings in 316.34s (0:05:16)

$ uv run pytest -q     # the gate, with the exercise and its simulated drives
4090 passed, 50 skipped, 6 warnings in 312.57s (0:05:12)
```

Fourteen new tests and one new skip: the live exercise skips here for the reason
transcribed below, and everything it needs to be trusted runs in the gate.

## US4-S2: each stage's failure, reported by stage name

The simulated per-stage drives, printed rather than only asserted, so the
message an operator would read is in the diff. `cleanups=1` on every line is
FR-012's other half: the scratch repository is destroyed however the run ends.

```text
US4-S2: one simulated failure per stage, and what the exercise reports
  stage=provision cleanups=1  on-ramp exercise failed at stage 'provision': RuntimeError: simulated provision failure
  stage=install   cleanups=1  on-ramp exercise failed at stage 'install': RuntimeError: simulated install failure
  stage=init      cleanups=1  on-ramp exercise failed at stage 'init': RuntimeError: simulated init failure
  stage=onboard   cleanups=1  on-ramp exercise failed at stage 'onboard': RuntimeError: simulated onboard failure
  stage=dispatch  cleanups=1  on-ramp exercise failed at stage 'dispatch': RuntimeError: simulated dispatch failure
  stage=land      cleanups=1  on-ramp exercise failed at stage 'land': RuntimeError: simulated land failure
  stage=cleanup   cleanups=1  on-ramp exercise failed at stage 'cleanup': scratch repo would not delete
```

## US4-S3: the final assertion is the outcome, not an exit status

A scripted forge reporting an `OPEN` pull request after every stage succeeded.
Every command exited zero; the exercise is red anyway, which is the whole of why
this story exists.

```text
  stage=land      cleanups=1  on-ramp exercise failed at stage 'land': pull request #61 is OPEN, not MERGED (https://github.com/ergane-scratch/onramp-61/pull/61); every command may have exited zero and the work still did not land
```

## US4-S4: the skip path, and trap 8 proved rather than assumed

The exercise on this sandbox — no scratch organization, no `gh` credentials, no
gateway, a registry still carrying `CHANGEME`:

```text
$ uv run pytest tests/test_live_onramp.py -q -rs
SKIPPED [1] tests/test_live_onramp.py:934: the on-ramp exercise needs live prerequisites this host does not have:
  - scratch organization: set ERGANE_ONRAMP_ORG to an org this run may create and delete a repository in (059 requires an org-owned target)
  - gh authentication: run `gh auth login` for that org: You are not logged into any GitHub hosts. To log in, run: gh auth login
  - gateway: export LITELLM_PROXY_URL and LITELLM_MASTER_KEY for a LiteLLM proxy with key management enabled: the epic mints a key on it
  - personas: point the registry's aliases at models this gateway serves: /…/personas.yaml still names the placeholder alias for: verifier
2 skipped in 0.14s
```

**Trap 8, verified against `127.0.0.1:1` as T028 requires.** `temporalio` raises
a bare `RuntimeError` for a dead port, so a guard written around `OSError` or
`RPCError` turns "this host has no control plane" into a failing suite:

```text
trap 8: what temporalio raises for a dead port, as the guard reports it
  RuntimeError at 127.0.0.1:1 (namespace 'default'): Failed client connect: Server connection error: tonic::transport::Error(Transport, ConnectError(ConnectError("tcp connect error", 127.0.0.1:1, Os { code: 111, kind: ConnectionRefused, message: "Connection refused" })))
```

## Controls: each property switched off, and what goes red

A green suite proves nothing about a test that cannot fail (trap 1). Each
property was removed in turn and `tests/test_onramp_exercise.py` re-run, the
module restored between mutations and `git diff --quiet` confirming the restore
after the last.

```text
ambient        (Workspace.beneath reads ERGANE_ROOT)          1 failed, 13 passed
nostage        (every failure blamed on Stage.LAND)           6 failed,  8 passed
nocleanup      (cleanup only on the success path)             8 failed,  6 passed
exitstatus     (the landed assertion returns immediately)     2 failed, 12 passed
temporalguard  (the probe catches only OSError)               1 failed, 13 passed
skipall        (every prerequisite reported absent, always)   2 failed, 12 passed
```

`ambient` is trap 9's defect and the one a presence test would miss — the helper
still derives its value from `root`, so only the drive that reads the filesystem
catches it. `temporalguard` is the one a reader would get wrong from expectation
rather than measurement. `skipall` is trap 2's cell: a guard that reports
everything missing is no better than one that reports nothing.

## What the operator runs after this lands

Recorded so the remaining tasks are not rediscovered; procedure and costs are in
`docs/onramp-exercise.md`. **T038 / SC-004**: run the exercise on a host meeting
every prerequisite, and confirm it lands a pull request with no human input.
**T039 / SC-005**: revert each of US1, US2 and US3's fixes in turn and confirm it
fails each time, at the stage that document names; US1's needs SC-001's
config-only proxy.
