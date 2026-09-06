# 128-US1 — `boundary_only_gates` parses, and refuses what it must

Committed evidence for epic 128's T008. Every line below is the pasted output
of `python -m factory.verify.factory_yaml <path>` — the same parser CLI the
config gate drives — run in this worktree against three manifest bodies on
disk. Nothing is described that was not printed.

**The refusal (US1-S2, FR-002).** The manifest declares `boundary_only_gates:
[typecheck]` and its `gates:` block declares only `test`:

```text
$ python -m factory.verify.factory_yaml refused.yaml
/tmp/128-us1-evidence/refused.yaml: [boundary_only_gates] declares boundary-only gate 'typecheck', which this manifest does not declare as a gate; declared gates are 'test'
EXIT=65
```

```yaml
# refused.yaml
version: 2
runtime: bwrap
gates:
  test: "uv run pytest -q"
boundary_only_gates: [typecheck]
```

Exit 65 is `PARSE_CLI_REJECTED` — the rejection path, not a crash — and the
message names the entry (`'typecheck'`), the rule slug
(`[boundary_only_gates]`), and what *is* declared (`'test'`).

**The successful parse (US1-S1, FR-001).** The same body shape with the list
naming a gate the manifest declares:

```text
$ python -m factory.verify.factory_yaml correct.yaml
{"version": 2, "runtime": "bwrap", "gates": {"audit": "uv run pytest tests/audit -q", "test": "uv run pytest -q"}, "timeouts": {}, "writes": {}, "standards": null, "landing_branch": "main", "roadmap": null, "forge": "github", "ladder": {"max_attempts": 3, "max_judge_retries": 2, "debugger_cycles": 1, "gate_timeout_s": 600, "escalation_timeout_s": 3600, "promotion_persona": null, "promotion_cycles": 1, "max_launch_retries": 2, "max_pre_agent_failures": 4}, "verify_order": ["gates", "diff_check", "judge"], "diff_refusal_bytes": 65536, "caches": [], "boundary_only_gates": ["audit"]}
EXIT=0
```

```yaml
# correct.yaml
version: 2
runtime: bwrap
gates:
  audit: "uv run pytest tests/audit -q"
  test: "uv run pytest -q"
boundary_only_gates: [audit]
```

Exit 0, and the emitted config ends with `"boundary_only_gates": ["audit"]` —
the list, carried in the order the manifest wrote it.

**The v1 refusal (US1-S4, FR-004).** The same body under `version: 1`:

```text
$ python -m factory.verify.factory_yaml v1.yaml
/tmp/128-us1-evidence/v1.yaml: [unknown_key] declares 'boundary_only_gates' at the top level; schema v1 knows only 'version', 'runtime', 'gates', 'timeouts', 'standards', 'landing_branch', 'roadmap', 'forge', 'writes', 'caches', 'diff_refusal_bytes'
EXIT=65
```

```yaml
# v1.yaml
version: 1
runtime: bwrap
gates:
  audit: "uv run pytest tests/audit -q"
boundary_only_gates: [audit]
```

The same `unknown_key` refusal every other v2-only key gets, naming the key —
the differential pair is asserted in
`tests/test_a_manifest_may_say_a_gate_binds_the_boundary_alone.py`.