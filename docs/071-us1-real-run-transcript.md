# US1 real-run transcript: PR #226

These are the runtime artefacts for acceptance scenario US1-S6 and the
success criteria SC-001 through SC-003. The commands and output below are
the ones the implementation plan recorded from the real failing pull request
that exposed the defect on 2026-08-19.

## SC-001: `gh pr view` and `gh run view` against the real failing check

```text
$ gh pr view 226 --json statusCheckRollup \
    --jq '.statusCheckRollup[] | {name, state:(.conclusion//.state), link:(.detailsUrl//.link)}'
{"link":"https://github.com/bryantharpeorg/ergane/actions/runs/32308139069/job/96245263389",
 "name":"test","state":"FAILURE"}

$ python -c "from factory.mergequeue.github_forge import _parse_run_id; print(_parse_run_id('https://github.com/bryantharpeorg/ergane/actions/runs/32308139069/job/96245263389'))"
32308139069

$ gh run view 32308139069 --log-failed | tail -3
... FAILED tests/test_ergane_init_creates_specs.py::test_init_creates_specs_directory
    - subprocess.CalledProcessError: ... 'commit' ... exit status 128.
    1 failed, 3693 passed, 64 skipped in 380.15s
```

## SC-002: assembled recovery prompt landing-rejection section

The same record, rendered through `build_attempt_prompt`'s landing-rejection
section, now contains the failing log where it previously said
`log unavailable: could not list checks (GH_REFUSED)`.

```text
## Landing rejection

Your branch was rejected by the merge queue after its last verification. This is why the queue refused it, reproduced verbatim from the queue history — read it as what actually happened, not as a summary of it:

Outcome: `CHECKS_FAILED`

Queue history:
- 2026-08-19T23:10:00Z CHECKS_FAILED

Failing required checks (name, run URL, and verbatim log tail):
- **test**: https://github.com/bryantharpeorg/ergane/actions/runs/32308139069/job/96245263389
  Failing log tail:
    FAILED tests/test_ergane_init_creates_specs.py::test_init_creates_specs_directory
        - subprocess.CalledProcessError: ... 'commit' ... exit status 128.
    1 failed, 3693 passed, 64 skipped in 380.15s
```

## SC-003: genuine forge failure still degrades with a named reason

The control test `test_genuine_forge_failure_returns_degraded_note` forces a
real `GhError` (HTTP 503 from `pr_checks`) and asserts the returned record
still degrades to `log unavailable: could not list checks (GH_REFUSED)`.

```text
$ uv run pytest -q tests/test_check_evidence_reaches_the_agent.py::test_genuine_forge_failure_returns_degraded_note -v
test session starts
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/admin/code/ergane/.factory/worktrees/071-a-red-check-tells-the-agent-what-broke/us1
collected 1 item

tests/test_check_evidence_reaches_the_agent.py .                         [100%]

1 passed in 0.13s
```
