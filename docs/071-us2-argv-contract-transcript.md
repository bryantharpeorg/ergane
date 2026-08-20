# US2: argv contract verification transcript

This document commits the runtime evidence for US2 acceptance scenarios SC-004
through SC-007. Nothing here carries a secret; the `gh` binary is run with
`GH_TOKEN` unset in `/tmp`, a directory that is not a git repository.

## SC-004 — the check against the tree before the fixes

With `create_pr` still calling `_run_json` and `pr_checks` already corrected by
US1, the argv contract test file was run against the pre-fix `gh.py`:

```text
$ uv run pytest -q tests/test_gh_argv_contract.py -v
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/admin/code/ergane/.factory/worktrees/071-a-red-check-tells-the-agent-what-broke/us2
configfile: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.14.2
asyncio: mode=Mode.AUTO, debug=True, asyncio_default_fixture_loop_scope=None, asyncio_default_fixture_loop_scope=function
collected 22 items

tests/test_gh_argv_contract.py ....................F..F                    [100%]

=================================== FAILURES ===================================
_________ test_gh_client_method_argv_is_accepted_by_real_gh[create_pr] _________
...
E           factory.mergequeue.gh.GhError: gh pr create --base main --head feature --title title --body-file /tmp/tmp<...>.md returned non-JSON output

factory/mergequeue/gh.py:396: GhError
________________ test_create_pr_no_longer_parses_output_as_json ________________
...
E           factory.mergequeue.gh.GhError: gh pr create --base main --head feature --title title --body-file /tmp/body.md returned non-JSON output

factory/mergequeue/gh.py:396: GhError
=========================== short test summary info ============================
FAILED tests/test_gh_argv_contract.py::test_gh_client_method_argv_is_accepted_by_real_gh[create_pr]
FAILED tests/test_gh_argv_contract.py::test_create_pr_no_longer_parses_output_as_json
=================== 2 failed, 19 passed, 1 skipped in 0.78 s ===================
```

The check fails on `create_pr` and on nothing else. `pr_checks` no longer fails
because US1 already replaced `gh pr checks --json` with `gh pr view --json
statusCheckRollup`; the old `pr_checks` argv is reproduced below for reference:

```text
$ GH_TOKEN= GH_TERMINAL_PROMPT=0 gh pr checks 1 --json name,state,link
unknown flag: --json
Usage: gh pr checks [<number> | <url> | <branch>] [flags]
...
```

## SC-005 — the check against the tree after the fixes

After `create_pr` was changed to use `_run` and parse the URL from stdout, the
same test run is green:

```text
$ uv run pytest -q tests/test_gh_argv_contract.py -v
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/admin/code/ergane/.factory/worktrees/071-a-red-check-tells-the-agent-what-broke/us2
configconfig: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.14.2
asyncio: mode=Mode.AUTO, debug=True, asyncio_default_fixture_loop_scope=None, asyncio_default_fixture_loop_scope=function
collected 22 items

tests/test_gh_argv_contract.py ....................s.                    [100%]

======================== 21 passed, 1 skipped in 0.77 s =========================
```

The single skipped test is the real guard for an absent `gh` binary (T018); `gh`
is installed here, so it skips.

## SC-006 — the mutation control

An invented flag appended to a real command makes the check fail and names the
command and the flag:

```text
$ GH_TOKEN= GH_TERMINAL_PROMPT=0 gh pr view 1 --json state --ergane-test-unknown-flag
unknown flag: --ergane-test-unknown-flag
Usage: gh pr view [<number> | <url> | <branch>] [flags]
...
```

The test that asserts this (`test_malformed_argv_is_rejected_and_names_command_and_flag`)
passes in the after-fix run.

## SC-007 — no network, no token, no repository

The check runs with `GH_TOKEN` unset outside any git repository and still
catches an unknown flag. From `/tmp`:

```text
$ GH_TOKEN= GH_TERMINAL_PROMPT=0 gh pr view 1 --json state --ergane-networkless-flag
unknown flag: --ergane-networkless-flag
Usage: gh pr view [<number> | <url> | <branch>] [flags]
...
```

The corresponding test passes:

```text
$ uv run pytest -q tests/test_gh_argv_contract.py::test_check_catches_unknown_flag_with_no_network_token_or_repository -v
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/admin/code/ergane/.factory/worktrees/071-a-red-check-tells-the-agent-what-broke/us2
configfile: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.14.2
asyncio: mode=Mode.AUTO, debug=True, asyncio_default_fixture_loop_scope=None, asyncio_default_fixture_loop_scope=function
collected 1 item

tests/test_gh_argv_contract.py .                                         [100%]

============================== 1 passed in 0.06 s ===============================
```
