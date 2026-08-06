"""US3's pure onboarding judgment: repo facts + gates → findings (FR-010).

`validate_target_repo` (the activity) gathers *facts*: repo visibility, whether
the merge queue is enabled on the default branch, the queue's required checks,
and the clone's committed `factory.yaml`. This module turns those facts into a
`TargetRepoProfile` whose `findings` say, one check at a time, whether the repo
is ready for the factory to dispatch against it. It is pure — no `gh`, no git,
no filesystem, no clock — so it is table-tested with no fakes at all
(plan.md § US3, T036).

The checks, each one a `Finding` (check slug, passed, actionable detail):

- **`visibility`** — the repo must be public, because the merge queue is
  available on any plan only for public repos (D-007). Private-on-Free cannot
  queue, so a private repo is rejected for dispatch.
- **`merge_queue`** — the merge queue must be enabled on the default branch. A
  queue that is not enabled cannot ever accept an enqueue.
- **`factory_yaml`** — the repo must commit a valid, non-empty-gated
  `factory.yaml`. A missing or malformed manifest is a failing finding carrying
  the 002 loader's error, never a pass by default: a verifier that shrugged at
  a broken manifest would find no gates, therefore see nothing fail.
- **`gate_check:<gate>`** — every declared gate must have a required check
  named *exactly* after it. The naming convention is the contract between
  `factory.yaml` and the repo's CI; a declared gate with no matching check
  would land a PR that never runs that gate.
- **`unknown_check:<name>`** — every required check must map back to a declared
  gate. Deterministic gates only is FR-003 made structural: a required check
  that is not a declared gate is a check the factory does not control, and this
  is precisely what keeps the LLM judge out of CI.

Each check fails closed: `passed` is the conjunction, and a repo that fails any
check is rejected for dispatch with instructions for the operator (spec US3 AS2).
`evaluate_repo` is deliberately handed already-loaded facts (the activity owns
the `gh` calls and the `factory.yaml` read) so the judgment here can be proven
in isolation.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from factory.mergequeue.models import Finding, TargetRepoProfile


def evaluate_repo(
    *,
    repo: str,
    default_branch: str,
    visibility: str,
    queue_enabled: bool,
    required_checks: Sequence[str],
    declared_gates: Sequence[str],
    factory_yaml_error: str | None = None,
) -> TargetRepoProfile:
    """Judge a target repo's facts against the factory's assumptions.

    Each argument is a *fact the activity already gathered*; this function holds
    no I/O. `required_checks` is what the queue will demand of a PR (the
    `merge_queue` rule's `required_status_checks`, or the classic-protection
    fallback), and `declared_gates` is what the repo's own `factory.yaml` names
    (`FactoryConfig.gates` keys). `factory_yaml_error`, when set, is the 002
    loader's `FactoryConfigError` message — a broken manifest is a failing
    finding, never a pass by default.

    The profile's `findings` are ordered so the operator preflight reads the
    repo's own health first (visibility, queue, manifest), then the gate↔check
    mapping, which is where a deterministic-CI repo most often diverges.
    """

    findings: list[Finding] = []

    # The repo must be public: the queue is available on any plan only for
    # public repos (D-007). Private-on-Free cannot ever enqueue, so this fails
    # closed regardless of the queue flag.
    _visibility_finding(findings, visibility)

    # The queue must be enabled on the default branch; the activity read the
    # merge-queue rule for exactly that branch.
    _queue_finding(findings, default_branch, queue_enabled)

    # The manifest must be present, valid, and declare gates. A broken manifest
    # is a failing finding carrying the loader's error — never a shrug that
    # would read as "no gates, so nothing to fail".
    _manifest_finding(findings, factory_yaml_error)

    # The gate ↔ check mapping, by name (position is irrelevant).
    declared = set(declared_gates)
    required = set(required_checks)
    for gate in declared:
        _gate_check_finding(findings, gate, gate in required)
    for check in sorted(required - declared):
        _unknown_check_finding(findings, check)

    return TargetRepoProfile(
        repo=repo,
        default_branch=default_branch,
        visibility=visibility,
        queue_enabled=queue_enabled,
        required_checks=tuple(required_checks),
        declared_gates=tuple(declared_gates),
        findings=tuple(findings),
        passed=all(f.passed for f in findings),
    )


# --- the checks ----------------------------------------------------------------


def _visibility_finding(findings: list[Finding], visibility: str) -> None:
    public = str(visibility).strip().lower() == "public"
    if public:
        findings.append(Finding("visibility", True, "repo is public"))
    else:
        findings.append(
            Finding(
                "visibility",
                False,
                f"repo is {visibility!r}; the merge queue is available on any "
                "plan only for public repos — make the repo public, or dispatch "
                "against a public target (D-007)",
            )
        )


def _queue_finding(
    findings: list[Finding], default_branch: str, queue_enabled: bool
) -> None:
    if queue_enabled:
        findings.append(
            Finding("merge_queue", True, f"merge queue enabled on {default_branch}")
        )
    else:
        findings.append(
            Finding(
                "merge_queue",
                False,
                f"merge queue is not enabled on the default branch "
                f"{default_branch!r}; enable the `merge_queue` branch rule there "
                "so a landing can enqueue",
            )
        )


def _manifest_finding(
    findings: list[Finding], factory_yaml_error: str | None
) -> None:
    if factory_yaml_error is None:
        findings.append(Finding("factory_yaml", True, "factory.yaml is valid"))
    else:
        findings.append(
            Finding(
                "factory_yaml",
                False,
                f"factory.yaml failed to load: {factory_yaml_error} — fix the "
                "manifest so the repo declares its gates",
            )
        )


def _gate_check_finding(findings: list[Finding], gate: str, matched: bool) -> None:
    if matched:
        findings.append(
            Finding(f"gate_check:{gate}", True, f"required check '{gate}' exists")
        )
    else:
        findings.append(
            Finding(
                f"gate_check:{gate}",
                False,
                f"gate '{gate}' is declared in factory.yaml but the merge queue "
                f"requires no check named '{gate}' — add it to the required "
                "checks so the queue runs the gate the factory declares",
            )
        )


def _unknown_check_finding(findings: list[Finding], check: str) -> None:
    findings.append(
        Finding(
            f"unknown_check:{check}",
            False,
            f"required check '{check}' is not a declared gate in factory.yaml — "
            "deterministic gates only (FR-003): a required check must map to a "
            "declared gate, so the LLM judge can never be a CI check",
        )
    )
