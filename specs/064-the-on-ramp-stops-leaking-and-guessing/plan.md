# Implementation Plan: the on-ramp stops leaking and guessing

**Spec**: `specs/064-the-on-ramp-stops-leaking-and-guessing/spec.md`

## What already exists, and where

- `factory/supervision/units.py:425` — `_wrapper_text`, whose docstring states
  the design goal US1 restores. Read it before writing anything; it is the
  clearest statement in the tree of what this story protects.
- `factory/notify/adapter.py`, `factory/notify/service.py`,
  `factory/notify/messages.py` — the escalation adapters. Find where the httpx
  client is constructed; that is where a redacting event hook attaches.
- `factory/notify/webhook.py` — the second adapter, covered by FR-004.
- The worker and operator-bridge entry points — both need FR-003. Find them
  before deciding the mechanism; if they share a startup path, attach there.
- `factory/cli/init.py:165` — `resolve_repo_root`, and `:172` where its docstring
  already documents worktree handling via `--git-common-dir`. US2 must not fire a
  confirmation for a legitimate worktree invocation.
- `factory/cli/init.py:478` — the `--check` call site, where FR-008's finding
  attaches.
- `factory/usage/litellm_client.py:246` and `:339` — the two `revoke_key`
  definitions; `:255` is `revoke_key_by_tokens`, the delegation target.

## Traps

**1. Do not fix the leak by deleting the observability.** US1-S2. Setting the
`httpx` logger to WARNING is the obvious fix and it removes every request line,
including the ones an operator debugging a delivery failure needs. A redacting
event hook on the client keeps the line and removes the secret. Prefer it; if you
choose the logger level anyway, you still owe a redacted observability line.

**2. A vacuous secret-absence assertion always passes.** Asserting "the token is
not in the logs" passes trivially if nothing was logged, if the send never
happened, or if the token variable was empty. Use a distinctive fake token,
assert the send occurred, *and* assert the token is absent. All three, or the
test proves nothing. This repository has four tests already found structurally
unable to fail.

**3. The webhook adapter is the next instance, not a nice-to-have.** FR-004.
`factory/notify/webhook.py` has the same shape and a secret-bearing URL is a
normal webhook configuration. Fixing telegram alone means this spec gets written
again.

**4. Tracebacks carry the URL too.** httpx attaches the request to the exception
it raises. A redaction that covers log records and not exception rendering leaks
on exactly the path an operator is most likely to paste into a chat window.

**5. The common case must not acquire a prompt.** US2-S2. `ergane init` run at a
repository root is the overwhelmingly normal invocation. If your confirmation
fires there, operators will learn to pass whatever suppresses it and US2 will
have made things worse.

**6. Worktrees legitimately resolve to a different path.** `resolve_repo_root`
already names the primary checkout as the parent of `--git-common-dir`
(`factory/cli/init.py:172`). That is correct behaviour, not the ambiguity US2 is
about. Distinguish "resolved somewhere else because worktree" from "resolved
somewhere else because we walked up out of a non-repository".

**7. `--non-interactive` must refuse, not assume.** US2-S4, and it is the same
rule 060 establishes: an absent answer is not consent. If 060 has not landed when
you start, attach to whatever non-interactive signal exists and note it for
re-check.

**8. Assert the delegation by observing it, not by reading the source.** US3-S2.
A test that greps for `revoke_key_by_tokens` in the method body passes on a
comment mentioning it. Patch `revoke_key_by_tokens` and assert `revoke_key`'s
behaviour changes.

**9. Do not modify factory code while an attempt is in flight.** The worker
imports `factory/notify/` and `factory/usage/` live. US1 and US3 both touch
modules the running worker holds.

**10. The judge sees the diff and the criteria. Nothing else.** SC-001 is a live
journal observation — **paste the output into the diff**, including evidence the
send occurred, so the absence is meaningful (trap 2).

**11. Story edges.** All three stories are independent and touch different
modules: US1 in `factory/notify/`, US2 in `factory/cli/init.py`, US3 in
`factory/usage/litellm_client.py`. Declare no edges between them; they can run in
parallel.

## Sizing

Three small, genuinely independent stories — the most parallelisable spec in this
set. US1 is an event hook plus tests, with the care in trap 2. US2 is a
comparison, a prompt, a finding, and tests. US3 is deleting nine lines and adding
a guard.

US1 is the only one with real design content (hook versus logger level, and
covering tracebacks). US3 should be a single small attempt.

## Verification the operator will run, independent of the gate

- **Prove US1 on the real journal.** Trigger a live escalation, then run
  `journalctl --user -u ergane-worker | grep -c "<token prefix>"` and confirm
  zero — while confirming from the same journal that the send happened. SC-001.
  A grep returning nothing because nothing ran is not evidence.
- **Prove US1's observability half.** Read the journal for the same send and
  confirm you can still tell that a Telegram request occurred and whether it
  succeeded. If you cannot, trap 1 has bitten.
- **Prove US2 by doing what the reporter did.** `mkdir ~/scratch/not-a-repo`
  beneath a repository, run `ergane init` there, and confirm you are asked.
  Decline, and confirm nothing was written.
- **Prove US3 by counting.** `grep -c "async def revoke_key"
  factory/usage/litellm_client.py` returns 1. SC-003.
