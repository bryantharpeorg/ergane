---
state: ready
# Flipped draft -> ready 2026-08-19 ~12:15 AM CT at the operator's instruction.
# Ready is eligibility, not dispatch. No dependencies in either direction, and
# no internal edges -- the most parallelisable spec in the on-ramp set. US1 is a
# live credential leak, which is why this spec is not ranked last despite
# reading as cleanup.
#
# Drafted 2026-08-19 ~12:35 AM CT by an operator session, from a first-time
# install report filed by an agent installing `ergane-cli 0.1.0` from PyPI.
#
# Three independent hygiene defects, grouped because each is small and none
# blocks another. US1 is a credential leak and is the reason this spec is not
# ranked last.
#
# Verified against the tree before drafting:
#
#   - `factory/supervision/units.py:425` (`_wrapper_text`) documents, correctly
#     and at length, that credentials go through `--env-command` rather than
#     systemd `Environment=` lines because the latter "would write their
#     credentials to disk in a file the journal echoes back". No httpx logger
#     level suppression exists anywhere in `factory/` -- verified by grep. httpx
#     logs request URLs at INFO, and the Telegram API carries the bot token in
#     the URL PATH, so the journal receives the token from the other direction.
#   - `factory/cli/init.py:165` `resolve_repo_root` resolves through
#     `git rev-parse --show-toplevel`, so an invocation from a non-repo
#     directory walks upward to the nearest ancestor containing `.git`. The
#     reporter ran from `~/code/ergane-test` and was resolved to `~/code`,
#     catching it only because the path was printed.
#   - `factory/usage/litellm_client.py` defines `async def revoke_key` twice, at
#     :246 and :339. The second shadows the first. The first delegates to
#     `revoke_key_by_tokens` (:255); the second reimplements the call inline.
#
# Filed as findings before drafting:
#   notify/telegram-bot-token-is-written-to-the-journal-in-cleartext
#   cli/init-silently-resolves-to-a-parent-git-repository
#   interpreter/revoke-key-is-defined-twice-and-the-first-is-dead
---

# Feature Specification: the on-ramp stops leaking and guessing

**Created**: 2026-08-19

## The gap, stated precisely

Three defects that share no mechanism and no module, grouped because each is
small, independent, and lands on a new operator. One of them is a credential
leak.

## US1: the credential design is right, and the credential leaks anyway

`factory/supervision/units.py:425` explains why systemd `Environment=` lines
were rejected: they "would write their credentials to disk in a file the journal
echoes back". That reasoning is correct, the `--env-command` indirection it
justifies is a good design, and the reporter singled it out as one of the best
decisions in the system.

The journal gets the token anyway, from the other direction. `httpx` logs request
URLs at INFO, and the Telegram Bot API carries the token **in the URL path**:

```
INFO:httpx:HTTP Request: POST https://api.telegram.org/bot<FULL_TOKEN>/sendMessage "HTTP/1.1 200 OK"
```

Readable by anyone who runs `journalctl --user -u ergane-worker`, and captured in
any log bundle an operator shares while debugging — which is precisely the
situation in which an operator shares a log bundle.

This is not a flaw in the `--env-command` design. It is a leak around it, and it
defeats the design's stated goal completely.

## US2: init guesses which repository you meant

`resolve_repo_root` (`factory/cli/init.py:165`) resolves through `git rev-parse
--show-toplevel`. Run from a directory that is not itself a repository, it walks
upward to the nearest ancestor that is one.

The reporter ran `ergane init --check` from `~/code/ergane-test`, which was not a
repository, and was silently resolved to `~/code`, which was. They caught it only
because the readiness header printed the resolved path.

Unnoticed, `ergane init` would have written `ergane.yaml` into that parent, added
`.ergane/` to its `.gitignore`, and registered roughly twenty-five unrelated
projects as one managed repository.

Walking upward is correct behaviour when the operator is *inside* a repository —
running from a subdirectory should find its root. What is wrong is doing it
silently when the invocation directory is not itself the repository root.

## US3: `revoke_key` is defined twice

`factory/usage/litellm_client.py` defines `async def revoke_key` at :246 and
again at :339, with identical docstrings. Python keeps the second; the first is
dead. Behaviour is equivalent today, so nothing is broken — but the surviving
definition reimplements the call inline rather than delegating to
`revoke_key_by_tokens`, so a future change to that method (batching, retries,
auditing) will not reach the code that actually runs.

This matters slightly more than a normal duplicate because 061/US1 adds a
revoke call on the verification path, and an implementer reading this module
needs to know which definition wins.

## User Scenarios & Testing

### User Story 1 - The bot token never reaches the journal (Priority: P1)

As an operator, I can share a worker log bundle without sharing my Telegram bot
token.

**Why this priority**: P1. It is a live credential leak that contradicts an
explicit, documented design commitment.

**Independent Test**: drive the adapter against a stub transport with logging at
INFO and assert no token-shaped substring appears in captured log records.

**Acceptance Scenarios**:

1. **Given** logging configured at INFO and a stub transport, **When** the
   Telegram adapter sends a message, **Then** no captured log record contains the
   bot token — proven by a committed test asserting over captured records, using
   a distinctive fake token so the assertion cannot pass vacuously.
2. **Given** the same, **When** the records are inspected, **Then** the request
   is still observable — a redacted URL, or a log line naming the operation —
   proven by a committed test. Silencing the leak by silencing all observability
   trades one operational problem for another.
3. **Given** the diff, **When** the worker and bridge entry points are
   inspected, **Then** the suppression or redaction is applied at both — proven
   by a committed test asserting each entry point's logging configuration. A fix
   applied at one entry point leaks from the other.
4. **Given** the diff, **When** the mechanism is inspected, **Then** it does not
   depend on the caller remembering to configure logging — proven by a committed
   test asserting the behaviour holds when the adapter is constructed directly.
   A convention that must be remembered will be forgotten by the next adapter.
5. **Given** a webhook escalation adapter configured with a secret in its URL,
   **When** it sends, **Then** the same protection applies — proven by a
   committed test. `factory/notify/webhook.py` has the same shape and would
   otherwise become the next instance.

---

### User Story 2 - Init names the repository it resolved and asks before enrolling a parent (Priority: P2)

As an operator running `ergane init` from the wrong directory, I am asked to
confirm before a repository I did not name is enrolled.

**Why this priority**: P2. It is a near-miss rather than a defect — the path was
printed and the reporter caught it — but the unnoticed outcome is enrolling
twenty-five unrelated projects as one managed repository.

**Independent Test**: invoke the resolver from a non-repository directory beneath
a repository and assert a confirmation is required.

**Acceptance Scenarios**:

1. **Given** an invocation directory that is not itself the repository root,
   **When** `ergane init` runs, **Then** it states the resolved root and requires
   confirmation before writing anything — proven by a committed test asserting
   the prompt and that no manifest is written when confirmation is declined.
2. **Given** an invocation from the repository root itself, **When** init runs,
   **Then** no confirmation is required — proven by a committed test. The common
   case must not acquire a prompt.
3. **Given** an invocation from a subdirectory *of* the repository, **When** init
   runs, **Then** the resolved root is stated and confirmation is required —
   proven by a committed test. This is the ambiguous case: walking up is
   plausibly what the operator wanted, and naming it costs one keystroke.
4. **Given** `--non-interactive`, **When** the resolved root differs from the
   invocation directory, **Then** init refuses rather than assuming consent —
   proven by a committed test. 060 establishes that an absent answer is not an
   answer; this is the same rule.
5. **Given** the diff, **When** `--check` runs in the same situation, **Then** it
   reports the resolved root as a finding rather than only in a header line —
   proven by a committed test. The reporter caught this from a header they
   happened to read; a finding is the surface an operator is looking at.

---

### User Story 3 - `revoke_key` is defined once (Priority: P3)

As a maintainer, the revocation method I read is the one that runs.

**Why this priority**: P3. Nothing is broken today. It is a merge artifact whose
cost is entirely future.

**Independent Test**: assert the class defines the method once and that it
delegates.

**Acceptance Scenarios**:

1. **Given** the diff, **When** `LiteLLMClient` is inspected, **Then**
   `revoke_key` is defined exactly once — proven by a committed test asserting
   the count from the class body or module source.
2. **Given** the diff, **When** the surviving definition is inspected, **Then**
   it delegates to `revoke_key_by_tokens` rather than reimplementing the call —
   proven by a committed test asserting that patching `revoke_key_by_tokens`
   changes `revoke_key`'s behaviour. A test asserting the source text would pass
   on a comment; assert the delegation by observing it.
3. **Given** the diff, **When** the module is inspected for other redefinitions,
   **Then** there are none — proven by a committed test that would catch any
   redefined class member, not just this one. The class of defect is "a merge
   put two definitions in one class"; a guard against the instance catches it
   once.

### Edge Cases

- **A token that appears in an exception traceback rather than a log record.**
  httpx raises with the request URL attached; the redaction must cover it.
- **Third-party libraries logging the same URL.** Redaction attached to the
  client covers more than a logger level does; prefer it where both are possible.
- **A repository root resolved through a worktree.** `resolve_repo_root` already
  handles the `--git-common-dir` case (`factory/cli/init.py:172`); confirmation
  must not fire spuriously for a legitimate worktree invocation.
- **A bare `git init` repository with no commits.** Already handled by 051's
  work; this story must not regress it.

## Requirements

### Functional Requirements

- **FR-001**: The Telegram bot token MUST NOT appear in any log record or
  traceback emitted by the worker or the operator bridge.
- **FR-002**: Requests MUST remain observable in redacted form.
- **FR-003**: The protection MUST be applied at both entry points and MUST NOT
  depend on the caller configuring logging.
- **FR-004**: The webhook adapter MUST receive the same protection.
- **FR-005**: `ergane init` MUST state the resolved repository root and require
  confirmation when it differs from the invocation directory.
- **FR-006**: `ergane init` MUST NOT require confirmation when invoked at the
  repository root.
- **FR-007**: Under `--non-interactive`, a differing resolved root MUST cause a
  refusal, not an assumption.
- **FR-008**: `ergane init --check` MUST report the resolved root as a finding.
- **FR-009**: `revoke_key` MUST be defined once and MUST delegate to
  `revoke_key_by_tokens`.
- **FR-010**: A committed guard MUST catch redefined class members in
  `factory/usage/litellm_client.py`.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  implements: [FR-005, FR-006, FR-007, FR-008]
US3:
  depends_on: []
  implements: [FR-009, FR-010]
```

No edges, in either direction. This is the most parallelisable spec in the
on-ramp set: US1 edits `factory/notify/`, US2 edits `factory/cli/init.py`, US3
edits `factory/usage/litellm_client.py`, and the three share no file, no fixture
and no seam. Declaring an edge here would serialise three stories for no reason,
and an edge declared out of caution is indistinguishable to the next reader from
an edge declared for correctness.

## Success Criteria

### Measurable Outcomes

- **SC-001**: After sending a live escalation, `journalctl --user -u
  ergane-worker` contains no substring of the bot token — evidenced by committed
  output of a search that returns nothing, alongside evidence the send occurred.
- **SC-002**: Running `ergane init` from a non-repository directory beneath a
  repository does not write a manifest without an explicit confirmation.
- **SC-003**: `grep -c "async def revoke_key"` over
  `factory/usage/litellm_client.py` returns 1.
- **SC-004**: No existing escalation or notification behaviour regresses; the
  operator still receives messages.

## Assumptions

- Redacting at the client is preferable to setting a logger level, because it
  survives a third-party library logging the same URL and it does not suppress
  unrelated diagnostics. Where only the logger level is practical, US1-S2's
  observability requirement still binds.
- 060 may land before this spec; if it has, US2-S4's `--non-interactive`
  behaviour attaches to the flag it introduced. If it has not, that scenario
  attaches to whatever non-interactive signal exists at implementation time and
  is re-checked when 060 lands.
- US3 is cosmetic today. It is included because 061/US1 adds a revoke call on the
  verification path and an implementer there needs to know which definition wins.
