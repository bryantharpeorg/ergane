---
state: draft
depends_on_landed:
  - 157-one-operator-contract-serves-both-clients
fixes:
  - init/the-init-verb-ships-a-spec-driven-factory-with-an-empty-specs-directory-and-no-agent-context
---

# Feature Specification: a scaffolded repo arrives with the context its agents need

## Provenance and corrected boundary

The original trio established a manifest-derived guard for production paths,
but it described only Claude's project layout and hook payload. The Codex-primary
audit requires one target-context unit with explicit client bindings. Shared
operator orientation belongs to spec 157 and operator skill installation belongs
to spec 087; this spec neither reads nor writes repository `AGENTS.md` or
`CLAUDE.md`.

The guard is advisory defense in depth, not a sandbox. It covers only the file
mutation tools whose official hook contracts are qualified here: Claude
`Write`/`Edit` and Codex `apply_patch`. Shell commands, MCP tools, client bugs,
untrusted project definitions, and absent hook support remain outside that
claim. No task in this trio may grant trust or use a trust-bypass option.

### User Story 1 - The target-context unit is one declared package (Priority: P1)

As an operator, I can inspect one versioned declaration of every target-context
file before `init` offers to install it.

**Acceptance Scenarios**:

1. **Given** the package declaration, **When** it is resolved, **Then** it names one canonical target-safety skill, the Claude compatibility entry point, `.claude/settings.json`, and `.codex/hooks.json`, with bytes and digests derived from package resources — proven by a resolver test.
2. **Given** the resolved payload, **When** every entry is inspected, **Then** it contains client configuration and Markdown context only, and no copied `.py`, executable checker, credential, absolute host path, `AGENTS.md`, or `CLAUDE.md` — proven by an allowlisted-path/type test.
3. **Given** the canonical target-safety context, **When** either client loads its binding, **Then** it explains protected-path derivation, supported tool scope, operator/node distinction, trust state, unreadable-input behavior, and the visible escape without claiming total write prevention — proven by semantic document tests.

**Why this priority**: Installation cannot be made collision-safe until the exact owned payload is finite and inspectable.

**Independent Test**: Resolve the package without a target repository and assert every relative path, digest, type, and required warning.

### User Story 2 - Init owns only bytes it previously installed (Priority: P1)

As an operator, I can rerun `ergane init` without losing target-specific client
configuration or context.

**Acceptance Scenarios**:

1. **Given** no payload collision, **When** init runs, **Then** it writes the declared relative paths and a versioned digest record, reports each file, and includes each installed file plus the record in its exact staging guidance — proven by a scratch-repository test.
2. **Given** a previously recorded file whose bytes still match its digest, **When** the package version changes, **Then** init updates it and records the new digest — proven by an upgrade fixture.
3. **Given** a payload-path file whose bytes differ from the recorded digest or have never been recorded, **When** init runs, **Then** it preserves the file byte-for-byte, records no ownership over it, and reports a collision while updating independent siblings — proven by both modified-owned and pre-existing-unowned fixtures.
4. **Given** effective git-ignore rules hide an installed path, **When** init reports the package, **Then** it names the hidden path and says it cannot reach a dispatched worktree until staged; init does not add a blanket client-directory ignore — proven with `git check-ignore` fixtures.

**Why this priority**: Both clients keep legitimate project data in the same directories as the package.

**Independent Test**: Exercise first install, clean upgrade, modified collision, unowned collision, and ignored-path cases in isolated repositories.

### User Story 3 - Protected paths come from the target manifest and stack pack (Priority: P1)

As an operator, I can see exactly which existing paths the target's declared
gates make production-sensitive.

**Acceptance Scenarios**:

1. **Given** a Python pack declaring `src` and `tests` and gates such as `uv run pytest -q`, **When** protection is derived, **Then** existing declared roots are included, absent roots and the repository root are excluded, and every included path names its source gate or pack declaration — proven by exact path/origin assertions.
2. **Given** `npm --prefix web run build`, **When** the command is parsed, **Then** existing `web` is included while command words such as `run` and `build` are not inferred as paths — proven by an ordered-token fixture.
3. **Given** no existing declared root and no path-shaped gate argument, **When** derivation runs, **Then** the set is empty and the report says why; it never falls back to `.` — proven by an empty-result test.
4. **Given** `ergane repo gate-paths`, **When** it runs twice against unchanged bytes, **Then** it prints the same sorted path/origin rows and does not mutate the repository — proven by transcript and status assertions.

**Why this priority**: A guard rooted at `.` locks out spec work; a guessed root misrepresents protection.

**Independent Test**: Derive and print paths from synthetic Python, Node, agnostic, missing-root, and path-flag manifests.

### User Story 5 - One installed checker normalizes paths and decodes Claude events (Priority: P1)

As an operator, I can reuse one canonical path decision and Ergane's installed
Python checker for Claude's documented file-edit events.

**Acceptance Scenarios**:

1. **Given** a Claude `Write` or `Edit` PreToolUse fixture, **When** the adapter reads `tool_input.file_path`, **Then** a protected operator target returns Ergane's dedicated refusal result and an unprotected target allows — proven with exact external-contract fixtures.
2. **Given** absolute in-repository paths, `./`, resolving `..`, repeated separators, spaces/quoting, and existing symlink aliases, **When** a target is classified, **Then** every canonically equivalent path is reduced to one repository-root-relative identity before protected-prefix comparison; ambiguous, unresolved, or escaping forms return a loud not-enforced result rather than a false protection claim — proven by path-table tests.
3. **Given** a dispatched node identified by its factory-owned home, worktree, or branch shape under either default or relocated runtime roots, **When** its supported payload targets a protected path, **Then** the checker allows it and visibly names the node exemption — proven by path-shape fixtures independent of `.ergane` or `.factory` directory names.
4. **Given** an unreadable manifest, unknown event/tool, malformed Claude payload, or unavailable CLI verb, **When** the binding runs, **Then** it avoids operator lockout, emits a visible not-enforced diagnostic, and never reports active protection — proven by a matrix including the CLI parser's ordinary status.
5. **Given** `ERGANE_SKIP_GATE_PATH_CHECK=1` in an interactive operator invocation, **When** a protected target is checked, **Then** it allows with an explicit escape-used diagnostic; the variable is neither written by init nor delivered to dispatched nodes — proven by environment and child-environment tests.

**Why this priority**: A literal prefix check can be bypassed by an equivalent path spelling even when the event decoder is otherwise correct.

**Independent Test**: Feed committed Claude fixtures and canonicalization tables to the installed CLI with no real client process.

### User Story 6 - A Codex patch decision checks every canonical target (Priority: P1)

As an operator, I receive one atomic safety decision for every path a Codex
`apply_patch` event can add, update, delete, or move.

**Acceptance Scenarios**:

1. **Given** exact Codex `apply_patch` PreToolUse fixtures, **When** the adapter reads `tool_input.command`, **Then** it extracts every `Add File`, `Update File`, `Delete File`, source, and `Move to` destination before deciding — proven by one fixture for each documented header.
2. **Given** patch targets using the equivalent path spellings from US5, **When** they are decoded, **Then** the shared canonicalizer produces the same identities and decisions as Claude; an ambiguous, unresolved, or escaping target makes the whole patch not enforced — proven by cross-client tables.
3. **Given** a multi-file patch with any protected source or destination, **When** the decision runs, **Then** the whole recognized patch returns the dedicated refusal and names every covered target; only an all-unprotected patch allows — proven by mixed-order fixtures.
4. **Given** a malformed or unknown patch header, **When** parsing runs, **Then** no partial target set is checked and the whole event returns a visible not-enforced result — proven by prefix-valid/suffix-invalid controls.

**Why this priority**: Checking a first path or only destination paths allows protected changes to hide later in one atomic patch.

**Independent Test**: Feed committed Codex patch fixtures to the pure decoder/canonicalizer/decision boundary.

### User Story 4 - Installation reports trust and proves active enforcement (Priority: P2)

As an operator, I can distinguish files written from hooks the installed client
has actually trusted and enforced.

**Acceptance Scenarios**:

1. **Given** no collisions, **When** init installs both hook bindings, **Then** its report distinguishes `installed`, `preserved collision`, `trust required`, and `verified active enforcement` per client; writing a hook file alone never produces the last state — proven by report-model tests.
2. **Given** Claude returns its ordinary CLI-parser status from an older or missing verb, **When** the wrapper runs, **Then** it reports not enforced and allows rather than translating that status into a write refusal; only Ergane's dedicated refusal result becomes Claude's documented blocking response — proven by status-composition tests.
3. **Given** Ergane returns its dedicated refusal to the Codex binding, **When** the synchronous response is rendered, **Then** it uses the documented `hookSpecificOutput` for `PreToolUse` with `permissionDecision: deny` and a redacted `permissionDecisionReason` naming the covered path/rule, while ordinary CLI parser status remains not enforced — proven by exact response fixtures.
4. **Given** a non-managed Codex project hook whose exact definition hash is not trusted, **When** init completes, **Then** it reports trust required and does not grant trust, start a client, or invoke a trust-bypass option — proven by an invocation-boundary test.
5. **Given** disposable repositories and freshly started supported clients, **When** an operator separately authorizes qualification, **Then** committed redacted evidence shows one unprotected allow and one protected refusal through Claude `Write`/`Edit` and Codex `apply_patch`, plus the client versions and exact trusted definition hash — proven by an evidence parser and digest check.
6. **Given** shell execution, MCP mutation, an unsupported tool, or an untrusted/disabled hook, **When** coverage is reported, **Then** it is explicitly outside verified enforcement — proven by negative capability rows.
7. **Given** previously verified evidence, **When** the client version, hook bytes/hash, trust state, or enabled state changes, **Then** `verified active enforcement` is invalidated and reverts to the applicable installed/trust-required state until requalified — proven by state-transition tests.

**Why this priority**: Installed configuration is not evidence that a client loaded, trusted, or applied it.

**Independent Test**: Test state transitions with fakes; reserve real-client qualification for a separately authorized disposable repository.

## Functional Requirements

- **FR-001**: One package declaration MUST own the finite target-context payload and its version.
- **FR-002**: The canonical target-safety context MUST have bindings discoverable by both supported clients.
- **FR-003**: The payload MUST contain no copied Python checker, credential, absolute host path, root `AGENTS.md`, or root `CLAUDE.md`.
- **FR-004**: The checker MUST execute from the installed Ergane Python package through a public CLI verb.
- **FR-005**: Init MUST write absent payload files and record their installed digests.
- **FR-006**: Init MUST update only files whose current bytes match their recorded installed digest.
- **FR-007**: Init MUST preserve and disclaim ownership of modified or never-recorded collisions while continuing independent files.
- **FR-008**: Reports and staging guidance MUST enumerate exact installed paths and the ownership record.
- **FR-009**: Effective ignore coverage MUST be reported per path; init MUST NOT ignore an entire client directory.
- **FR-010**: Stack-pack source roots MUST be declarative and client-neutral.
- **FR-011**: Protected-path derivation MUST use ordered gate tokens and existing declared roots, attribute origins, exclude the repository root, and never guess.
- **FR-012**: `ergane repo gate-paths` MUST be deterministic, read-only, and explicit about an empty set.
- **FR-013**: Claude support MUST be limited to documented `Write` and `Edit` PreToolUse payloads and their `tool_input.file_path`.
- **FR-014**: Codex support MUST be limited to documented `apply_patch` PreToolUse payloads and patch text in `tool_input.command`.
- **FR-015**: Codex patch parsing MUST account for every added, updated, deleted, source, and moved-to path and refuse the whole patch if any target is protected.
- **FR-016**: The core checker MUST return a dedicated refusal result distinct from ordinary CLI parsing or capability failure.
- **FR-017**: Client bindings MUST translate only that dedicated result into the client's documented blocking response; the Codex response MUST include `hookSpecificOutput`, `hookEventName: PreToolUse`, `permissionDecision: deny`, and a redacted `permissionDecisionReason`.
- **FR-018**: Malformed, unreadable, unknown, unavailable, and unsupported cases MUST allow with a visible not-enforced diagnostic to avoid operator lockout.
- **FR-019**: Node exemption MUST derive from factory-owned home/worktree/branch shapes and MUST survive runtime-root relocation.
- **FR-020**: The named operator escape MUST be visible, MUST NOT be installed as ambient configuration, and MUST NOT enter a node environment.
- **FR-021**: Init MUST report hook state per client using the exact states `installed`, `preserved collision`, `trust required`, and `verified active enforcement`.
- **FR-022**: Only a separately authorized real-client qualification MUST be permitted to produce `verified active enforcement`.
- **FR-023**: Qualification MUST pin client versions, exact definition bytes/hash, target classification, allow/refuse outcome, and redaction.
- **FR-024**: Init and qualification MUST NOT grant trust or invoke `--dangerously-bypass-hook-trust` or an equivalent override.
- **FR-025**: Coverage claims MUST exclude shell, MCP, unsupported tools, disabled hooks, untrusted definitions, and client behavior not present in committed evidence.
- **FR-026**: Every client path MUST be canonicalized to a repository-root-relative identity before comparison; canonically equivalent paths MUST decide identically, while ambiguous, unresolved, escaping, or outside-root inputs MUST return visible not-enforced rather than false protection.
- **FR-027**: Verified enforcement MUST be invalidated by any change to client version, hook bytes/hash, trust state, or enabled state.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005, FR-006, FR-007, FR-008, FR-009]
US3:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-010, FR-011, FR-012]
US5:
  depends_on: []
  depends_on_merged: [US3]
  implements: [FR-013, FR-016, FR-018, FR-019, FR-020, FR-026]
US6:
  depends_on: []
  depends_on_merged: [US5]
  implements: [FR-014, FR-015]
US4:
  depends_on: []
  depends_on_merged: [US2, US5, US6]
  implements: [FR-017, FR-021, FR-022, FR-023, FR-024, FR-025, FR-027]
```
