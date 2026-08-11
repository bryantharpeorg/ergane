# Plan: 030-test-suite-store-isolation

Scaffolded from the following ledger findings:

- `hardening/test-suite-writes-to-the-live-evidence-store` — critical: Running the test suite with the operator environment exported writes real rows into the live evidence store at FACTORY_ROOT, and the long-running notify service ferries them to the operator's real Telegram chat. A pytest run pages the operator with escalations for workflows that do not exist.

Refine the approach before the spec is readied.
