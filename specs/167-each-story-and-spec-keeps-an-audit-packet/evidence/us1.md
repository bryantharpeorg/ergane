# US1 evidence

## Focused controls

Command: `uv run pytest -q tests/test_attestation_identity.py tests/test_attestation_lifecycle.py tests/test_attestation_usage.py tests/test_final_sweep.py::test_no_decision_in_the_component_asks_how_much_was_spent tests/test_final_sweep.py::test_the_component_imports_only_the_approved_roster tests/test_temporal_payload_shape.py::test_every_boundary_field_has_a_default_or_is_allowlisted tests/test_workgraph_models.py::test_the_attempt_context_carries_exactly_the_adapters_inputs`

Result: `462 passed, 1 warning in 25.43s`.

Actual rows and outcomes proven by the tests:

- Four launches with two run IDs and two question launches reused the same ladder ordinal; each had a distinct invocation, key alias, and usage ID.
- One redelivered teardown returned the original ledger ID, retained one launch, and did not duplicate its `0.03` spend.
- The frozen ladder retained both rungs after the configured transition; the second invocation recorded the debugger persona, `codex`, `subscription`, and its alias.
- Terminal timeout, kill/cancel, question, and pre-agent paths each retained a launch and outcome without verification or usage.
- A failed issuance retained the launch, used no usage row, and the existing key cleanup completed without a second request.
- Schema-v2 rows read unchanged, without migration or guessed invocation attribution; gateway and CLI evidence stayed separate; a confirmed row with missing token fields remained incomplete; subscription dollars stayed unavailable; repeated equal amounts kept distinct request IDs and serving identities.

## Declared gate

Command: `uv run pytest -q`

Result: `6497 passed, 58 skipped, 15 warnings in 789.04s`.

Committed diff: 62490 bytes, below the 65536-byte ceiling.
