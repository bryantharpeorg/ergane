# Operator workflow

Ergane uses one client-neutral lifecycle. It does not add an issue tracker or a
scheduler. This guide states authority boundaries; it does not itself grant any
mutation authority.

The vocabulary is defined in [CONTEXT.md](../../CONTEXT.md). Decisions are
recorded in [docs/decisions.md](../decisions.md); the decision process is
immutable. `AGENTS.md` remains the canonical orientation and separates an
observation from a separately authorized action.

## Lifecycle

1. **Source verification — read-only.** Resolve each citation by the symbol it
   names, treating the line number as a hint. Ask live sources for status and
   spend rather than trusting stale prose.
2. **Optional memory recall — optional.** No memory connection is approved for
   the operator contract, so absence is reported rather than assumed. Use the
   current prompt, the declared standards, and local documents instead. Neither
   nodes nor unattended runs gain memory-write authority here.
3. **Finding-to-spec ownership — declared intent.** The findings ledger owns a
   defect until the operator explicitly promotes it into a Spec Kit story. Do
   not turn diagnosis into spec mutation by inference.
4. **Whole-trio refinement — declared intent.** Read and refine `spec.md`,
   `plan.md`, and `tasks.md` together, so acceptance, mechanism, and task order
   stay consistent.
5. **Validation — read-only.** Validate the trio and resolve its citations
   against the tree. A refusal names the unresolved citation or declaration.
6. **Readiness — read-only.** Confirm declared state and landed stories from
   Ergane's read surfaces, using the landing branch declared in `ergane.yaml`
   rather than the checked-out `HEAD`.
7. **Dispatch — declared intent.** Dispatch only after refinement, validation,
   and readiness are complete and the operator separately grants the action.
8. **Landing — declared intent.** Land only by the declared branch and merge
   process, after the node's verification has passed.
9. **Attestation — declared intent.** Attest only with the resulting evidence
   and only under an operator-granted action.

Every command named above is illustrative and read-only. An edit, dispatch,
landing, attestation, or publication still requires its own declared intent.

## Ergane authorities

- **Spec Kit trios** own runtime intent and implementation scope.
- The **findings ledger** owns observed defects, recurrence, and diagnosis.
- The **immutable decisions** own durable governance; supersede an entry with a
  new one rather than editing landed history.

## Not Ergane defaults

- Beads is not an Ergane default.
- GitHub issues are not an Ergane default.
- A mandatory push is not an Ergane default.
- Checkout cleanup is not an Ergane default.

Those mechanisms are competing queues or destructive actions unless the
operator separately authorizes the specific action. Do not create an issue
from an observation, schedule work through a vendor queue, push automatically,
or clean a checkout as part of diagnosis.
