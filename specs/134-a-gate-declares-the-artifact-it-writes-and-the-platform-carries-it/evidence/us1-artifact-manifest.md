# US1 manifest artifact evidence

Generated with the worktree's parser for four deliberately malformed
`ergane.yaml` fixtures and one valid declaration.

## Bad type

```text
ergane.yaml: [artifacts] gives the artifact entry {'gate': 'test', 'path': 'report.txt', 'type': 'manifest'} the type 'manifest'; the permitted types are <ArtifactType.SBOM: 'sbom'>, <ArtifactType.COVERAGE: 'coverage'>, <ArtifactType.SCAN: 'scan'>, <ArtifactType.OPAQUE: 'opaque'>
```

## Undeclared gate

```text
ergane.yaml: [artifacts] declares an artifact for 'lint', which this manifest does not declare as a gate; declared gates are 'test'
```

## Absolute path

```text
ergane.yaml: [artifacts] declares the artifact path '/coverage.xml', which is absolute; it must be repository-relative
```

## Escaping path

```text
ergane.yaml: [artifacts] declares the artifact path '../coverage.xml', which escapes the repository root; it must remain repository-relative
```

## Successful parse

```python
(ArtifactDeclaration(gate='test', path='coverage.xml', type=<ArtifactType.COVERAGE: 'coverage'>),)
```

## Parser CLI JSON

```json
{"version": 2, "runtime": "bwrap", "gates": {"test": "uv run pytest -q"}, "timeouts": {}, "writes": {}, "standards": null, "landing_branch": "main", "roadmap": null, "forge": "github", "ladder": {"max_attempts": 3, "max_judge_retries": 2, "debugger_cycles": 1, "gate_timeout_s": 600, "escalation_timeout_s": 3600, "promotion_persona": null, "promotion_cycles": 1, "max_launch_retries": 2, "max_pre_agent_failures": 4}, "verify_order": ["gates", "diff_check", "judge"], "diff_refusal_bytes": 65536, "caches": [], "boundary_only_gates": [], "artifacts": [{"gate": "test", "path": "coverage.xml", "type": "coverage"}]}
```
