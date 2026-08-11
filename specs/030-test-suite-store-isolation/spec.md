---
state: draft
# specs_root: specs
# target_repo: /home/admin/code/ergane
# Auto-scaffolded by ergane findings promote; review before flipping to ready.
---

# Feature Specification: 030-test-suite-store-isolation

This spec was scaffolded from accepted findings in the ergane findings ledger. Each user story below carries the original finding's evidence verbatim; the operator or an architect session refines the prose before flipping `state` to `ready`.

### User Story 1 - Running the test suite with the operator environment exported writes real rows into the live evidence store at FACTORY_ROOT, and the long-running notify service ferries them to the operator's real Telegram chat. A pytest run pages the operator with escalations for workflows that do not exist. (Priority: P2)

Running the test suite with the operator environment exported writes real rows into the live evidence store at FACTORY_ROOT, and the long-running notify service ferries them to the operator's real Telegram chat. A pytest run pages the operator with escalations for workflows that do not exist.

**Acceptance Scenarios**:

1. **Given** the finding `hardening/test-suite-writes-to-the-live-evidence-store`, **When** the work scoped here is implemented, **Then** the ledger records a resolution tied to this spec.

**Why this priority**: Promoted from the doctor ledger; the recurrence count motivates building the fix.

**Independent Test**: Verify the fix closes the finding and the scaffold compiles with zero rejections.

**Evidence**:
- `tests/test_roadmap_failure_notifications.py:188`
- `factory/notify/service.py:175`
- Fired 2026-08-09 19:55Z. 'uv run pytest -q' in a shell that had sourced scripts/ergane-env.sh (FACTORY_ROOT, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID) inserted three escalation rows with workflow_id 'roadmap-specs' -- a fixture, no such workflow -- into .factory/verification.db. Two were delivered=1: 'max_concurrent_nodes must be a positive integer, got 0' and 'got -1', each with live RETRY / KILL buttons and a real 1h expiry defaulting to KILL. The test file is not at fault: it correctly stubs its own send activity at :188. The leak is that it writes to the REAL store, and factory/notify/service.py has been running since Aug 6 polling that store and shipping whatever it finds. So the isolation boundary the test thinks it has (stub the sender) is not the boundary that matters (own the store). Blast radius: the live escalation table now holds 3 fixture rows among 7 total, indistinguishable from genuine pages, and any operator who presses a button signals a nonexistent workflow. Worse in the other direction -- a real escalation arriving during a test run is now noise the operator has been trained to ignore. Fixes, ranked: (1) a session-scoped pytest fixture that points FACTORY_ROOT at tmp_path unconditionally, so no test can reach the real store no matter what the shell exported; (2) refuse to construct the evidence store when a pytest sentinel is set and the path is not under tmp; (3) make scripts/ergane-env.sh not export the Telegram credentials, which narrows the blast radius but leaves the store poisoned. (1) is the only one that closes it.

## Functional Requirements

- **FR-001**: The factory MUST address `hardening/test-suite-writes-to-the-live-evidence-store`: Running the test suite with the operator environment exported writes real rows into the live evidence store at FACTORY_ROOT, and the long-running notify service ferries them to the operator's real Telegram chat. A pytest run pages the operator with escalations for workflows that do not exist.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001]
```
