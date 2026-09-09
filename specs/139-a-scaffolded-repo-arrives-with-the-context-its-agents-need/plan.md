# Implementation Plan: a scaffolded repo arrives with the context its agents need

## Current seams and external contracts

- `factory/cli/init.py:1134` — `init_command` owns repository initialization; install the target unit only in this path, not in demo scaffolds.
- `factory/stack_packs.py:50` — `StackPack` and `factory/stack_packs.py:141` — `_pack_from_data` are the declarative source-root seams.
- `factory/stack_packs.py:253` — `_leading_executable` demonstrates ordered shell parsing; protected-path derivation must not use an unordered word set.
- `factory/verify/models.py:291` — `FactoryConfig` owns the target manifest's gates.
- `factory/cli/repo.py:105` — `add_repo_parser` is the installed-package CLI boundary for listing and checking paths.
- `factory/workgraph/worktree.py:191` — `resolve_factory_root` proves the runtime root may be relocated; node detection cannot key on one directory name.
- Official Codex hook contract and trust model: https://learn.chatgpt.com/docs/hooks . For the qualified event, `apply_patch` supplies patch text in `tool_input.command`; non-managed project hooks load only after the exact definition is trusted.
- Claude's supported binding is its documented PreToolUse `Write`/`Edit` event with `tool_input.file_path`. Freeze exact JSON fixtures from the supported installed version instead of inventing a shared schema.

## Package boundary

Use a typed package declaration in Ergane source. Its payload consists only of:

- one canonical `.agents/skills/ergane-target-safety/SKILL.md`;
- the smallest tested Claude compatibility entry point under `.claude/skills/`;
- `.claude/settings.json` with the Claude binding; and
- `.codex/hooks.json` with the Codex binding.

If client discovery proves the compatibility entry point cannot be a link in a
supported checkout, preserve one canonical generated source and byte-equivalence
tests. Do not move shared operator workflow or repository orientation into this
unit.

## Story slices

### US1 — Declare and resolve

Add an immutable package model, resource resolver, digest calculation, and
semantic tests for the target-safety context. All executable policy remains in
the installed Python package; the repository payload contains configuration and
context only.

### US2 — Collision-safe install

Record unit version and per-file installed digests. Treat absence, clean-owned,
and collision as three different states. Query effective ignore rules and
construct the exact staging list from recorded owned paths rather than naming a
whole client directory.

### US3 — Derive and display protected paths

Add optional source roots to stack packs. Derive existing roots and explicitly
path-shaped ordered gate arguments, excluding the repository root and absent
paths. Preserve origin metadata and expose a deterministic read-only listing.

### US5 — Canonicalize, decode Claude, and decide

Resolve supported path spellings and existing symlink aliases against an explicit
repository root, then compare one normalized relative identity. Ambiguous,
unresolved, escaping, or outside-root forms return visible not-enforced. Decode
Claude's one file path from committed fixtures and apply the operator/node/escape
policy once, returning typed allow, refuse, or not-enforced results. Do not let
argparse status double as policy.

### US6 — Decode complete Codex patches

Codex `apply_patch` may have many source and destination paths. Parse the entire
documented header grammar and canonicalize every Add/Update/Delete/source/Move-to
path before deciding. An unknown header makes the whole event unsupported/not
enforced rather than partially checked; any protected path refuses the whole
recognized patch.

### US4 — Bind, report trust, and qualify

The Claude wrapper maps only the dedicated internal refusal to Claude's documented
block response and treats an older CLI's parser failure as visible not-enforced.
The synchronous Codex deny response uses `hookSpecificOutput` with
`hookEventName: PreToolUse`, `permissionDecision: deny`, and a redacted
`permissionDecisionReason` naming the covered path/rule; retain exit status 2
only as the documented alternative, not the ordinary parser status. Init can
report files installed and trust required, but only a separately authorized
fresh-client run in a disposable repository can record verified active
enforcement. Record exact definition bytes/hash because Codex trust is bound to
that definition, and invalidate qualification when version, bytes/hash, trust,
or enabled state changes.

## Traps

1. **This is target context, not operator orientation.** Never read or write root `AGENTS.md` or `CLAUDE.md` here.
2. **No copied checker.** A `.py` payload falls outside repository gates and forks implementation.
3. **`.` is not a safe fallback.** It converts a production guard into a repository-wide write lock.
4. **Token order matters.** `--prefix web` is a path relation; unordered command words cannot express it.
5. **A Codex patch is atomic for policy.** Checking only the first file allows a protected second target or move destination.
6. **Refusal is not parser failure.** Only Ergane's dedicated result is translated into a client block.
7. **Fail-open must be loud.** Unreadable or unsupported input reports not enforced; it never claims protection.
8. **Node detection cannot use `.factory` as identity.** The runtime root is configurable.
9. **The escape is operator-visible and non-ambient.** Init never writes it and the adapter never propagates it.
10. **Written is not trusted.** Non-managed Codex project hooks require trust of the exact definition.
11. **No trust bypass.** Qualification uses normal client trust and separate operator authority, never a bypass option.
12. **Coverage is narrow.** Shell and MCP mutations are outside the qualified tool set.
13. **Collision handling is per file.** One operator-owned settings file must not prevent safe siblings from updating.
14. **Evidence is not a credential dump.** Redact host paths, prompts, tokens, account identifiers, and unrelated transcript content.
15. **Path spelling is adversarial input.** Normalize against the declared repository root before any prefix comparison.
16. **Qualification is per exact state.** Version, definition, trust, or enabled-state drift removes the verified label.

## Verification

Run resolver, installer, path-derivation, fixture-decoder, decision, wrapper,
report-state, and discovery-evidence tests; then the declared repository gate.
Inspect payload paths and evidence for secrets and absolute home paths. A real
client run remains held until separately authorized. Finally run
`git diff --check` and confirm no trust store, client config outside the
disposable repository, runtime store, service, or spec state changed.
