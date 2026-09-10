# 164-US1 evidence — the seeded home survives the launch boundary, red then green

The story's regression red-first, exact commands and outputs pasted
(constitution VIII / D-037: the judge sees this diff and nothing else). The
tests drive the real `CodexAdapter.run_attempt` policy with
`tests/strict_codex_child.py` as the CLI — a child that refuses a missing
`CODEX_HOME`/config rather than manufacturing one, and writes its synthetic
rollout only after successful reads. **Simulated inference: no model, gateway
service, or installed Codex is involved; this is not proof of a model
response.** No live credentials were touched (synthetic key, planted
`auth.json` under a test-owned operator home).

## Red (the repair reverted; the pre-story adapter from 63d97d5)

    $ git show 63d97d5:factory/workgraph/adapter.py > factory/workgraph/adapter.py
    $ uv run pytest tests/test_164_us1_relative_home.py tests/test_164_us3_two_node_controls.py tests/test_164_us4_route_isolation.py -q --no-header
    FAILED ... test_the_child_receives_the_absolute_seeded_home_across_the_cwd_change
    FAILED ... test_the_production_seam_canonicalises_the_relative_home
    FAILED ... test_two_nodes_each_find_their_own_rollout_and_their_homes_stay_distinct
    FAILED ... test_the_relative_home_launch_still_carries_no_worker_credential
    FAILED ... test_two_nodes_keep_distinct_homes_and_each_archive_holds_its_own_rollout
    FAILED ... test_the_gateway_relative_home_names_the_key_variable_without_its_value
    FAILED ... test_the_subscription_relative_home_carries_the_isolated_credential_copy_alone
    ========================= 7 failed, 4 passed in 1.17s ==========================

The S1 launch failure, with the archived log and the incident's own refusal
(production-shaped: relative home from the real `home_path` helper on
`DEFAULT_RUNTIME_ROOT`, cwd a test-owned worker directory, worktree
elsewhere):

    E  assert result.termination == Termination.COMPLETED
    E    - completed
    E    + pre_agent_failure
    # the archived stdout.log, verbatim:
    CODEX_HOME points to ".ergane/homes/164-codex-keeps-its-seeded-home-across-the-worktree-boundary/us1/.codex", but that path does not exist

while the seeded directory existed beneath the worker directory
(`worker-host/.ergane/homes/…/us1/.codex/config.toml` present) — the
directory DID exist; the child's cwd change broke it. The seam assertion:

    E  assert '.ergane/home...ry/us1/.codex' == '/tmp/pytest-...ry/us1/.codex'
    E    - /tmp/…/worker-host/.ergane/homes/164-…/us1/.codex   (expected, resolved)
    E    + .ergane/homes/164-…/us1/.codex                      (received, relative)

The 4 passing in red are the controls: the already-absolute home retains its
location, the sandbox construction pair (absolute env in, identity out), and
the registry pin.

## Green (same suites, after the T005 repair)

    $ uv run pytest tests/test_164_us1_relative_home.py tests/test_164_us2_sandbox_launch.py tests/test_164_us3_two_node_controls.py tests/test_164_us4_route_isolation.py -q --no-header
    ============================== 14 passed in 0.54s ==============================

    $ uv run pytest tests/test_164_us2_sandbox_launch.py -q --no-header
    ============================== 3 passed in 0.13s ==============================

The execution test ran the real `BwrapBackend.launch` (bwrap 0.9.0 on this
host): the sandboxed strict child read the seeded `config.toml` and wrote its
rollout into the per-node home through the existing bind, cwd the worktree.
No skip fired here; on a host without bwrap the execution test skips with its
own named reason (`bwrap not installed on this host …`).

## Focused neighbours (unchanged contracts)

    $ uv run pytest tests/test_155_us1_codex_gateway.py tests/test_155_us2_codex_refusal.py tests/test_155_us3_codex_subscription.py tests/test_155_us4_codex_toolchain.py tests/test_adapter.py tests/test_agent_activities.py tests/test_095_pre_agent_failure.py tests/test_154_us1_cli_and_route.py tests/test_toolchain_discovery.py tests/test_sandbox_mount_set.py -q --no-header
    ======================= 190 passed, 1 warning in 27.51s ========================

## The declared full gate

    $ uv run pytest -q
    ========== 5973 passed, 58 skipped, 15 warnings in 601.35s (0:10:01) ===========

(exit 0, on the final tree including the strengthened child-env assertions.
The 58 skips are the standing live tiers — capacity/epic/merge/onramp/proxy/
telegram — each printing its own `did not run — runs when …` reason, unchanged
by this story. Temporal gRPC connect errors after the run's last line are the
live-tier teardown's own noise, after `pytest` exited 0.)