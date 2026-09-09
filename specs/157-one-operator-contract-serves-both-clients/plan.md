# Implementation Plan: one operator contract serves both clients

## Current seams

- `CLAUDE.md` is the current operator orientation and the source to preserve while making `AGENTS.md` canonical.
- `tests/test_claude_md.py:61` — `test_every_command_the_file_names_parses` and `tests/test_claude_md.py:117` — `test_every_path_the_file_cites_exists` are the existing contract tests; extend their intent without retaining a filename-specific architecture.
- `factory/workgraph/prompt.py` and `factory/activities/agent_activities.py:1043` — `resolve_standards` already deliver the binding standards explicitly to nodes. Auto-discovered orientation must not outrank them.
- `ergane.yaml` is the active manifest in this repository. Numerous historical documents still say `factory.yaml`; the orientation should explain compatibility, not rewrite landed history.
- Official Codex instruction discovery: https://learn.chatgpt.com/docs/agent-configuration/agents-md . Qualification must still record what the installed clients actually loaded.
- Subscription governance is deferred in `docs/codex-primary-governance-proposal-2026-09-09.md`; this operator-contract trio does not apply it.

## Story slices

### US1 — Canonical orientation

Create `AGENTS.md`, make `CLAUDE.md` a repository-portable compatibility entry
point, and replace filename-specific assertions with content and discovery
contracts. Commit a redacted fixture or artifact from fresh root, nested, and
worktree sessions for both clients. If a symlink is not preserved by one
supported installation shape, use the smallest explicit loader and record that
exception; do not fork the policy text.

### US2 — Workflow and capabilities

Add `docs/agents/workflow.md` and `docs/agents/capabilities.md`. Keep commands
illustrative and read-only until the guide reaches a separately authorized act.
Capability rows describe jobs—ask, delegate, recall, schedule, notify, render,
stop—and then map the available client binding. A missing binding is a valid,
visible result.

## Traps

1. **Node authority is already explicit.** Making `AGENTS.md` canonical must not make auto-discovery a new standards channel for factory nodes.
2. **A symlink is a hypothesis until both clients load it.** Test the repository object and fresh-session behavior.
3. **Ancestor policy is real but not local authority.** State Ergane's own workflow without attempting to edit files above the repository.
4. **Observation is not action.** A status paragraph containing a merge or fetch recipe can accidentally broaden a reporting request.
5. **Live state rots.** Keep status and spend out of the orientation; point to read surfaces.
6. **Hindsight is unavailable in this session.** Record the degraded state; do not claim recall or add a connection.
7. **D-053 exists.** Preserve the existing runner/route decision; this trio does not amend governance.
8. **Runner selection does not select inference.** The immediate builder path is Codex CLI on `route: gateway` to Ollama Cloud. Subscription/private-pilot requirements do not gate operator instructions.
9. **Runtime evidence costs diff bytes.** Keep the six discovery transcripts compact and redacted so US1 stays below 64 KiB.

## Verification

Run focused instruction/document tests first, then the repository gate. Inspect
the committed client-discovery artifact for secrets and host paths. Finally,
verify `git diff --check`, that no spec state changed as a side effect, and that
the constitution and decision log remain unchanged.
