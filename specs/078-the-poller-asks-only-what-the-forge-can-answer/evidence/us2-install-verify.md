# 078-US2 evidence — SC-004, SC-005, SC-006

Every block below is pasted from a run in this worktree on 2026-08-22, verbatim
and unedited. Where a binary was simulated it says so in the paste itself, not
only here.

## Where the check was built, and why there (T016, trap 11)

**`ergane install --verify`** — `factory/controlplane/verify.py`,
`ForgeCapabilityProbe`, registered in `REGISTRY` between the host probe and the
subsystem probes. The doctor was the other candidate and is not built.

The reason is what kind of defect this is. A `gh` that cannot answer the
poller's field set is true of a host *from the moment the release is installed
on it* — before any epic exists for the doctor to find wedged, and independent
of anything in flight. It becomes true again on exactly one other occasion, a
downgrade or reinstall of the CLI, after which the operator verifies again. The
doctor answers "what is wrong with the work in flight"; this question has to be
answerable when there is no work in flight, which is the only moment answering
it is cheap. US2's title is *before they dispatch*.

The check's *mechanism* lives in `factory/mergequeue/gh.py` rather than beside
the probe, for two structural reasons and no aesthetic one:

- that module owns `_VIEW_FIELDS`, so deriving rather than copying is a local
  read there and would be an import-and-restate anywhere else (trap 5);
- `tests/test_forge_sweep.py` forbids any module outside four allowlisted files
  from spelling one forge's own vocabulary, and `factory/controlplane/verify.py`
  is not one of them. The probe therefore carries no field name and no version
  number of its own. It cannot, and that is the guarantee, not a workaround.

## The `gh` this node sees, and the one the worker sees

This node's environment resolves `/usr/bin/gh` 2.45.0, which does not declare
`baseRefOid`. The operator established during US1 that the worker's own `PATH`
resolves a 2.98.0 first, and that is what `poll_landing` actually shells out to.
Both are true; they are different hosts' answers to the same question, which is
precisely the thing this probe reports and the reason it reports the resolved
path alongside the verdict. So the refusal below needed no stub — but the
**passing** case did, and that is stated in its own paste.

```
$ command -v gh; gh --version
/usr/bin/gh
gh version 2.45.0 (2026-03-17 Ubuntu 2.45.0-1ubuntu0.3+esm3)
$ cd /tmp && GH_TOKEN= gh __complete pr view --json '' | grep -c .
44
$ cd /tmp && GH_TOKEN= gh __complete pr view --json '' | grep -x baseRefOid
$ echo "EXIT=$?"
EXIT=1
```

## SC-004 / US2-S1 — verification refuses, naming the field and the version

Real `ergane install --verify`, through the CLI entry point, with the real
`/usr/bin/gh` on `PATH`. The other subsystems have nothing to answer with in
this sandbox and say so; the `forge` line is the subject. **No stub in this
run.**

```
$ env PATH=/usr/bin:/bin ERGANE_CONFIG_PATH=/tmp/078evidence/config.toml \
    .venv/bin/python3 -m factory.cli.main install --verify
[FAIL] host: gh is present but unauthenticated — needed for GitHub CLI for repository operations; remedy: run the CLI authentication command
[FAIL] forge: the gh at /usr/bin/gh (gh version 2.45.0 (2026-03-17 Ubuntu 2.45.0-1ubuntu0.3+esm3)) does not declare baseRefOid, which the landing poller sends in `gh pr view --json state,isDraft,mergedAt,closedAt,mergeStateStatus,autoMergeRequest,statusCheckRollup,baseRefOid`: a landing polled from this host fails on its first poll and the node sits in ENQUEUED until somebody looks — upgrade `gh` to a version that declares baseRefOid (run: gh --version and update from https://cli.github.com)
[FAIL] llm: ERGANE_LLM_MASTER_KEY is not set; no credential to complete a round trip
[FAIL] temporal: Temporal at 127.0.0.1:1 did not answer: RuntimeError: Failed client connect: Server connection error: tonic::transport::Error(Transport, ConnectError(ConnectError("tcp connect error", 127.0.0.1:1, Os { code: 111, kind: ConnectionRefused, message: "Connection refused" })))
[PASS] memory: skipped by declaration: memory.backend is `none`
[PASS] telemetry: skipped by declaration: telemetry has no otlp_endpoint
[PASS] escalation: escalations will be dropped: escalation.adapter is `none`; a node that would have asked a question fails instead of waiting
EXIT=1
```

The field (`baseRefOid`), the installed version (`gh version 2.45.0 (2026-03-17
Ubuntu 2.45.0-1ubuntu0.3+esm3)`), the resolved binary (`/usr/bin/gh`), the
consequence, and the remedy — all in the one line the operator reads, hours
before the epic that would otherwise have parked.

Note what the `host` line says in the same report: *present but
unauthenticated*. That check was passing on the maintainer's machine on
2026-08-20 while the epic parked. Present, authenticated and capable are three
claims and only the third is about the question this factory asks.

## SC-005 / US2-S2 — a pass that says what it verified and who answered

**This host has no `gh` that declares `baseRefOid`, so the passing case is
produced by putting a stub earlier on `PATH`** (plan trap 10's second route).
The stub answers `--version` and `__complete` and refuses to run anything else;
its declared vocabulary is `/usr/bin/gh`'s own 44 fields plus `baseRefOid`, and
**its version string says out loud that it is a stub** so no reader of this file
can mistake this for a run against a real 2.98.0.

```
$ cat /tmp/078evidence/stubbin/gh | head -6
#!/bin/sh
if [ "$1" = "--version" ]; then
  echo "gh version 2.98.0 (STUB for 078-US2 evidence; not a real GitHub CLI)"
  exit 0
fi
if [ "$1" = "__complete" ]; then

$ env PATH=/tmp/078evidence/stubbin:/usr/bin:/bin \
    ERGANE_CONFIG_PATH=/tmp/078evidence/config.toml \
    .venv/bin/python3 -m factory.cli.main install --verify
[FAIL] host: gh is present but unauthenticated — needed for GitHub CLI for repository operations; remedy: run the CLI authentication command
[PASS] forge: the gh at /tmp/078evidence/stubbin/gh (gh version 2.98.0 (STUB for 078-US2 evidence; not a real GitHub CLI)) declares all 8 of the --json fields the landing poller sends in `gh pr view --json state,isDraft,mergedAt,closedAt,mergeStateStatus,autoMergeRequest,statusCheckRollup,baseRefOid`, checked against the field vocabulary that binary itself reports
[FAIL] llm: ERGANE_LLM_MASTER_KEY is not set; no credential to complete a round trip
[FAIL] temporal: Temporal at 127.0.0.1:1 did not answer: RuntimeError: Failed client connect: Server connection error: tonic::transport::Error(Transport, ConnectError(ConnectError("tcp connect error", 127.0.0.1:1, Os { code: 111, kind: ConnectionRefused, message: "Connection refused" })))
[PASS] memory: skipped by declaration: memory.backend is `none`
[PASS] telemetry: skipped by declaration: telemetry has no otlp_endpoint
[PASS] escalation: escalations will be dropped: escalation.adapter is `none`; a node that would have asked a question fails instead of waiting
EXIT=1
```

The green line names the binary that answered, its version, the command, the
count and every field. `verify/readiness-proves-a-thing-is-declared-not-that-it-works`
is the finding that says a green line which does not say what it checked is how
three readiness defects survived; this one cannot be read without learning which
`gh` was asked.

The same pass is also available **without any stub at all**, against the real
`/usr/bin/gh`, by narrowing the poller's field set to what that binary declares
— see the mutation below, section C.

## US2-S3 — an absent `gh` is a different sentence, not the same one

Run with a `PATH` holding `git` and `bwrap` and no `gh`.

```
$ ls /tmp/078evidence/nogh
bwrap
git
$ env PATH=/tmp/078evidence/nogh ERGANE_CONFIG_PATH=/tmp/078evidence/config.toml \
    .venv/bin/python3 -m factory.cli.main install --verify
[FAIL] host: gh is absent — needed for GitHub CLI for repository operations; remedy: install gh
[FAIL] forge: the GitHub CLI (`gh`) is not on PATH: the landing poller has nothing to ask, so every epic dispatched from this host would park at its first landing — install it from https://cli.github.com, then run: gh auth login
[FAIL] llm: ERGANE_LLM_MASTER_KEY is not set; no credential to complete a round trip
[FAIL] temporal: Temporal at 127.0.0.1:1 did not answer: RuntimeError: Failed client connect: Server connection error: tonic::transport::Error(Transport, ConnectError(ConnectError("tcp connect error", 127.0.0.1:1, Os { code: 111, kind: ConnectionRefused, message: "Connection refused" })))
[PASS] memory: skipped by declaration: memory.backend is `none`
[PASS] telemetry: skipped by declaration: telemetry has no otlp_endpoint
[PASS] escalation: escalations will be dropped: escalation.adapter is `none`; a node that would have asked a question fails instead of waiting
EXIT=1
```

Absent says *install it*, and names no field and no version, because none was
read. Incapable says *upgrade it*, and names both. Different conditions,
different remedies, different sentences — FR-006.

## SC-006 / US2-S4 — the mutation: the field set moves, the probe follows

`_VIEW_FIELDS` is changed and **nothing in the probe is edited**. The binary is
the real `/usr/bin/gh` throughout, so its vocabulary is fixed and only the
poller's question moves.

```
$ uv run python /tmp/evidence_run.py            # A. unmodified
poller field set: state,isDraft,mergedAt,closedAt,mergeStateStatus,autoMergeRequest,statusCheckRollup,baseRefOid
[FAIL] forge: the gh at /usr/bin/gh (gh version 2.45.0 (2026-03-17 Ubuntu 2.45.0-1ubuntu0.3+esm3)) does not declare baseRefOid, which the landing poller sends in `gh pr view --json state,isDraft,mergedAt,closedAt,mergeStateStatus,autoMergeRequest,statusCheckRollup,baseRefOid`: a landing polled from this host fails on its first poll and the node sits in ENQUEUED until somebody looks — upgrade `gh` to a version that declares baseRefOid (run: gh --version and update from https://cli.github.com)
condition: incapable | undeclared: ('baseRefOid',)

$ uv run python /tmp/evidence_run.py "...,baseRefOid,erganeMutationOnlyField"   # B. a field added
poller field set: state,isDraft,mergedAt,closedAt,mergeStateStatus,autoMergeRequest,statusCheckRollup,baseRefOid,erganeMutationOnlyField
[FAIL] forge: the gh at /usr/bin/gh (gh version 2.45.0 (2026-03-17 Ubuntu 2.45.0-1ubuntu0.3+esm3)) does not declare baseRefOid, erganeMutationOnlyField, which the landing poller sends in `gh pr view --json state,isDraft,mergedAt,closedAt,mergeStateStatus,autoMergeRequest,statusCheckRollup,baseRefOid,erganeMutationOnlyField`: a landing polled from this host fails on its first poll and the node sits in ENQUEUED until somebody looks — upgrade `gh` to a version that declares baseRefOid, erganeMutationOnlyField (run: gh --version and update from https://cli.github.com)
condition: incapable | undeclared: ('baseRefOid', 'erganeMutationOnlyField')

$ uv run python /tmp/evidence_run.py "state,isDraft,...,statusCheckRollup"       # C. narrowed
poller field set: state,isDraft,mergedAt,closedAt,mergeStateStatus,autoMergeRequest,statusCheckRollup
[PASS] forge: the gh at /usr/bin/gh (gh version 2.45.0 (2026-03-17 Ubuntu 2.45.0-1ubuntu0.3+esm3)) declares all 7 of the --json fields the landing poller sends in `gh pr view --json state,isDraft,mergedAt,closedAt,mergeStateStatus,autoMergeRequest,statusCheckRollup`, checked against the field vocabulary that binary itself reports
condition: capable | undeclared: ()
```

(The `...` in the two command lines above is elision of the field list in the
*shell argument*; each run's full field set is printed verbatim by the run
itself on the following line. `/tmp/evidence_run.py` sets
`factory.mergequeue.gh._VIEW_FIELDS` from `argv[1]` and then calls
`ForgeCapabilityProbe().gather()` — the shipped probe, unmodified.)

Section C is also the passing case with **no stub anywhere**: the real
`/usr/bin/gh`, asked only what it declares, answers and the check says so.

## The controls: both directions of the check can fail

### The check goes red when the probe copies the field set instead of deriving it

Trap 5's mutation, applied to the shipped code and reverted: `poller_view_argv`
replaced by a hand-written list identical to today's `_VIEW_FIELDS` — the exact
defect this story exists not to rebuild, and the version of it that would pass
every other test in the file, because every other test uses the real field set
that a copy matches on the day it is written.

```
$ # poller_view_argv() replaced by a literal argv tuple
$ uv run pytest tests/test_forge_capability_probe.py -q
        assert grown.passed is False
        assert grown_snapshot.condition == FORGE_INCAPABLE
>       assert grown_snapshot.undeclared == (INVENTED_FIELD,)
E       AssertionError: assert ('mergedAt', ... 'baseRefOid') == ('erganeMutationOnlyField',)
E
E         At index 0 diff: 'mergedAt' != 'erganeMutationOnlyField'
E         Left contains 4 more items, first extra item: 'closedAt'

tests/test_forge_capability_probe.py:281: AssertionError
=========================== short test summary info ============================
FAILED tests/test_forge_capability_probe.py::test_the_probe_follows_the_pollers_field_set_without_being_edited
1 failed, 7 passed in 0.08s

$ # mutation reverted
$ uv run pytest tests/test_forge_capability_probe.py -q
........                                                                 [100%]
8 passed in 0.06s
```

### The tests were written first and were red

Written before any of the implementation existed, and red on the API that did
not:

```
$ uv run pytest tests/test_forge_capability_probe.py -q
==================================== ERRORS ====================================
____________ ERROR collecting tests/test_forge_capability_probe.py _____________
ImportError while importing test module '…/tests/test_forge_capability_probe.py'.
Traceback:
tests/test_forge_capability_probe.py:43: in <module>
    from factory.mergequeue.gh import (
E   ImportError: cannot import name 'FORGE_ABSENT' from 'factory.mergequeue.gh'
=========================== short test summary info ============================
ERROR tests/test_forge_capability_probe.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.10s
```

## What this check does not do, deliberately

- **It never runs a poll.** It asks the binary for its `--json` vocabulary,
  which needs no credential, no network and no repository — so it is answerable
  on a fresh host, which is the host that has this defect. The test asserting
  this reads the stub's own argv log: every invocation is `--version` or
  `__complete`, and a check that reached for a real `pr view` would show up
  there.
- **It pins no `gh` version.** A version number in this tree is the same
  hand-maintained fact that caused the defect. The version is reported as the
  binary spelled it and is never compared against anything.
- **It does not repair.** An unusable `gh` is reported, never installed or
  upgraded — `install --verify` reports, the operator acts.
- **It does not accuse on ignorance.** A binary that is present and will not say
  what it declares is a fourth condition, `undetermined`: it does not pass,
  because nothing was measured, and it names no field, because none was asked
  about.
