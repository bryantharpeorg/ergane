# Implementation Plan: Codex keeps its seeded home across the worktree boundary

## Verified seams

- `factory/workgraph/adapter.py:882` — `home_path` returns the path beneath the supplied runtime root, which may be relative.
- `factory/workgraph/workflow.py:1929` — `EpicWorkflow` constructs the normal attempt's relative home; its recovery path does the same near line 4064. Inspect these callers; do not introduce filesystem operations into workflow code.
- `factory/workgraph/adapter.py:1185` — `SharedAttemptPolicy.run_attempt` creates and seeds the home before resolving the worktree and launching a child there.
- `factory/workgraph/adapter.py:1958` — `CodexAdapter._provider_env` currently passes the relative result of `codex_home_path` to CODEX_HOME.
- `factory/workgraph/adapter.py:2018` — `CodexAdapter._seed_home` owns generated gateway config and the subscription credential copy.
- `factory/workgraph/adapter.py:2076` — `codex_home_path` is the existing per-CLI path helper; inspect every caller before choosing the smallest correction.
- `factory/workgraph/adapter.py:522` — `BwrapBackend._build_argv` resolves HOME and binds that directory but passes CODEX_HOME unchanged through its allowlist.
- `factory/workgraph/adapter.py:357` — `HostAgentBackend` starts the child in the worktree and also needs a stable child-facing CODEX_HOME.
- `factory/workgraph/adapter.py:2102` — `_codex_rollouts` reads the environment's Codex home; turn detection and archive discovery reuse it.
- `tests/test_155_us1_codex_gateway.py:108` — `node_home` builds its home from an absolute temporary factory root, concealing this incident.

Symbols govern; verify each before editing. Read the full spec/plan/tasks and
declared standards. Production changes should be confined to the adapter's
existing activity-side path preparation. A dedicated small regression module
and narrowly scoped test helper are expected; do not redesign generic state
paths or modify operator-selected personas/configuration as story output.

## Repair shape

Canonicalize the existing declared per-node Codex home while still at its
seeding boundary, before child cwd changes. Ensure every relevant consumer
uses that identity. Resolving an already-declared relative seed location here
is not permission to select a different root from the worktree, operator HOME,
checkout branch, environment override, or another fallback. Keep resolution
out of deterministic workflows and preserve already-absolute inputs.

Use a real launched strict child through the shared adapter policy, not just
a unit assertion on `_provider_env`. The child must first refuse a nonexistent
home/config, then write its rollout only after successful reads. It must not
repair the missing directory on behalf of the implementation. For sandbox
tests, follow existing bubblewrap test conventions and keep the synthetic
executable and interpreter visible through current bindings. Test constructed
argv even where host policy prevents executing bubblewrap.

## Traps

1. An absolute `tmp_path / ...` fixture alone repeats the coverage gap. Change
   cwd only within a test-owned temporary worker directory, use the production
   relative root and helper, and keep the child worktree somewhere different.
2. The existing Codex stub creates descendants itself. Either add an explicit
   strict mode or use a small dedicated strict child; do not let a fake turn
   hide the exact refusal real Codex produces.
3. Fixing only the sandbox leaves the host path broken; normalizing only a
   local seed variable while constructing environment from the original
   context can leave this bug untouched. Assert what the child receives.
4. The declared home already points at the intended seed directory. Do not
   derive a new owner from the target worktree or implement spec 129 here.
5. Do not copy the operator's real auth, print an actual key, call inference,
   change subscription discovery, or add a wrapper/global CODEX_HOME export.
   Synthetic credential files and a fake gateway endpoint suffice.
6. An output log alone is not a turn. Create a synthetic rollout in the child's
   seeded Codex home and observe production classification plus its archive.
7. Sandbox unavailability must be an explicit skip, not a catch-all success.
   Unexpected execution failures remain failures. No wider writable binds.
8. Keep default and route behavior, credential discovery, timeout/termination,
   and per-node archive identity covered by existing adapter tests. No new
   dependency, runtime config dial, workflow change, or unrelated cleanup.
9. Keep code, tests and committed evidence together below 64 KiB. Paste only
   bounded command results, never the complete full-suite log or credentials.
10. Full gates and the judge remain mandatory. Report unrelated gate failures
    honestly; do not loosen deadlines or retry a rejected unchanged queue tree.

## Verification and operator follow-through

Write the host relative-home regression first and record its exact failure,
then implement and record green. Run focused gateway/subscription/refusal and
sandbox regressions and the declared full gate. Commit a compact evidence note
with commands, exact outputs and any live-path skips so the diff-only judge can
assess the evidence. The strict-child test is simulated inference, not proof
of a model response; label it accordingly.

After landing, the operator will rerun installed Codex's credential-free
home/config probe, restore the producing personas to Codex, deploy a frozen
merged revision, and restart 131/147 through normal reset/derive/start commands.
Those live steps are operator qualification, not unprovable story criteria;
the broader roadmap remains paused during this selected build sequence.
