# US1 evidence

## Correct v2 declaration

```text
version: 2
runtime: bwrap
gates:
  test: "uv run pytest -q"
  lint: "uv run ruff check ."
artifacts:
  - {gate: test, path: ./coverage.xml, type: coverage}
  - {gate: lint, path: reports/../sbom.json, type: sbom}
```

```text
FactoryConfig(version=2, runtime='bwrap', gates={'test': 'uv run pytest -q', 'lint': 'uv run ruff check .'}, timeouts={}, writes={}, standards=None, landing_branch='main', roadmap=None, forge='github', ladder=VerificationConfig(max_attempts=3, max_judge_retries=2, debugger_cycles=1, gate_timeout_s=600, escalation_timeout_s=3600, promotion_persona=None, promotion_cycles=1, max_launch_retries=2, max_pre_agent_failures=4), verify_order=('gates', 'diff_check', 'judge'), diff_refusal_bytes=65536, caches=(), boundary_only_gates=(), artifacts=(ArtifactDeclaration(gate='test', path='coverage.xml', type=<ArtifactType.COVERAGE: 'coverage'>), ArtifactDeclaration(gate='lint', path='sbom.json', type=<ArtifactType.SBOM: 'sbom'>)))
```

## Parser CLI JSON

```json
{"version": 2, "runtime": "bwrap", "gates": {"test": "uv run pytest -q", "lint": "uv run ruff check ."}, "timeouts": {}, "writes": {}, "standards": null, "landing_branch": "main", "roadmap": null, "forge": "github", "ladder": {"max_attempts": 3, "max_judge_retries": 2, "debugger_cycles": 1, "gate_timeout_s": 600, "escalation_timeout_s": 3600, "promotion_persona": null, "promotion_cycles": 1, "max_launch_retries": 2, "max_pre_agent_failures": 4}, "verify_order": ["gates", "diff_check", "judge"], "diff_refusal_bytes": 65536, "caches": [], "boundary_only_gates": [], "artifacts": [{"gate": "test", "path": "coverage.xml", "type": "coverage"}, {"gate": "lint", "path": "sbom.json", "type": "sbom"}]}
```

## Refusals

```text
bad type: ergane.yaml: [artifacts] declares the artifact entry {'gate': 'test', 'path': 'coverage.xml', 'type': 'virus_scan'}, whose type 'virus_scan' is not permitted; permitted types are <ArtifactType.SBOM: 'sbom'>, <ArtifactType.COVERAGE: 'coverage'>, <ArtifactType.SCAN: 'scan'>, <ArtifactType.OPAQUE: 'opaque'>
undeclared gate: ergane.yaml: [artifacts] declares the artifact entry {'gate': 'build', 'path': 'coverage.xml', 'type': 'coverage'}, whose gate 'build' is not one this manifest declares; declared gates are 'test', 'lint'
absolute path: ergane.yaml: [artifacts] declares the absolute artifact path '/tmp/coverage.xml'; artifact paths are worktree-root-relative
escaping path: ergane.yaml: [artifacts] declares the artifact path '../coverage.xml', which escapes the worktree root
```
