# 154-US4 evidence — the shared attempt policy and the registry-swept conformance suite

Pasted tool output, per constitution VIII (diff-provable, within the 64 KiB
budget shared with the code). The story's tests were written first and
observed red before the implementation existed (T016/T017 → T018).

## 1. The tests were observed red against the pre-story module

The red state is committed as `31ed154` (tests only). Running the new tests
against it fails at import, because the module did not yet declare the seam:

```
$ git checkout 31ed154 && uv run pytest -q tests/test_adapter.py -x \
    -k "shared_policy or second_adapter or conformance or registered_adapter or one_method_protocol or per_cli"
...
tests/test_adapter.py:77: in <module>
    from factory.workgraph.adapter import (
E   ImportError: cannot import name 'SharedAttemptPolicy' from 'factory.workgraph.adapter' (.../factory/workgraph/adapter.py)
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
1 error in 0.15s
```

Module state on the red commit, read from git:

```
pre-story adapter defines SharedAttemptPolicy: False
pre-story adapter defines CredentialStage: False
committed red tests import SharedAttemptPolicy: True
```

## 2. The hoist (T018) — green

The full adapter suite after the hoist:

```
$ uv run pytest -q tests/test_adapter.py --no-header
60 passed in 22.13s
```

The story's own tests, selected (US4-S1 second-adapter end-to-end, deadline,
orphan reap, ferry; US4-S2 protocol; the per-CLI surface bound):

```
$ uv run pytest -q tests/test_adapter.py -k "shared_policy or second_adapter or one_method_protocol or per_cli_surface or registered_adapter or reaps_a_previous or ferries_an_operator or ends_its_process_tree or runs_the_shared" --no-header
8 passed, 52 deselected in 5.74s
```

## 3. The conformance sweep reads the registry, not a literal (US4-S3 / FR-008)

Parametrization at collection, read off `_ADAPTERS`:

```
$ uv run pytest -q tests/test_adapter.py -k "conformance or registered or one_method or per_cli or second or shared" --no-header --collect-only
tests/test_adapter.py::test_every_registered_adapter_resolves_by_its_own_name[claude-code]
tests/test_adapter.py::test_every_registered_adapter_keeps_the_one_method_protocol[claude-code]
```

Mutation check (run in-session, not committed): registering a second adapter
under the name `broken` puts it in the sweep without touching the suite:

```
registry swept: ['broken', 'claude-code']
```

The half a name sweep cannot see — shared policy hidden *inside*
`run_attempt` — is held by the class-source scan
(`test_the_second_class_contains_none_of_the_shared_policy`), which reads the
second adapter's source and fails on any spelling of pid file, reap, killpg,
archive, monitor, ferry, wait_for, heartbeat or usage-read:

```
5 passed in 0.11s   # resolves_by_its_own_name / one_method_protocol (registry-parametrized),
                    # outer_protocol_is_one_method_still, contains_none_of_the_shared_policy,
                    # per_cli_surface_is_all_the_shared_policy_takes
```

## 4. Full gate (T019 / T020)

```
$ uv run pytest -q --no-header
5816 passed, 58 skipped, 11 warnings in 512.23s (0:08:32)
```

(The live-tier probes — `live_capacity`, `live_epic`, `live_merge`,
`live_onramp`, `live_proxy`, `live_telegram` — skip when their server or
credential is absent, as on this host. No `FAILED` lines.)

## 5. Diff budget

```
$ git diff --stat e5a3862..HEAD
 factory/workgraph/adapter.py | 384 +++++++++++++++++++++++++++++--------------
 tests/test_062_us3_skills.py |   9 +-
 tests/test_adapter.py        | 382 +++++++++++++++++++++++++++++++++++++++++-
 tests/test_us2_seam.py       |   6 +-
 4 files changed, 650 insertions(+), 131 deletions(-)
$ git diff e5a3862..HEAD | wc -c
44248
```

44,248 bytes, inside the 64 KiB `DIFF_INPUT_LIMIT` ceiling.

## 6. Fidelity of the moved policy

The moved method bodies were compared against the pre-story module
(`git show e5a3862:factory/workgraph/adapter.py`), whitespace-normalized.
Only intended differences appear — the policy reads its launch configuration
from the per-CLI adapter it is constructed around:

- `self.grace_s` → `self._cli.grace_s` (in `_reclaim`, `_reap`)
- `self._backend` → `self._cli._backend`, `self.executable` →
  `self._cli.executable` (in `_resolve_backend`)

`_archive_session` is byte-identical. `_monitor`, `_ferry_once`, `_reclaim`,
`_reap`, `_resolve_backend`, `_standards_path` differ only by those rewrites.
The dead `_launch` (superseded by the backend seam in 011-US2, zero callers)
was dropped, not moved.
