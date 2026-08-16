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
- **`squash_title`** — the repo must title squash merges from the PR title
  (`squash_merge_commit_title` is `PR_TITLE`). Any other value, or an unreadable
  value, fails with the one-call remedy (`gh api -X PATCH repos/<owner_repo> -f
  squash_merge_commit_title=PR_TITLE`).
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

**034 US4 extends this judgment; it does not fork it.** `ergane init --check`
gathers four more facts and passes them as `init_facts`; the 003 dispatch path
passes nothing and sees exactly the checks it always saw, so a check added here
can never start refusing a dispatch it used to allow. Both doors share this
function, so the gate↔check parity an operator reads at their terminal is the
same `Finding`, detail and all, the interpreter reads at dispatch (FR-010). The
added checks are `runtime_root_ignored` (whose detail names the exact
`.gitignore` line, because a runtime root reaching git history is how a node
commits its own transcripts onto a landing branch), `runtime_root_migration`
(only for a repo still on legacy `.factory/`, trap 12), `registry_entry`,
`landing_branch`, and one `control_plane` summary over 033's probes — a summary
because the control plane is a property of the host rather than of this repo,
and `ergane install --verify` renders its checks individually.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from factory.mergequeue.models import Finding, TargetRepoProfile


@dataclass(frozen=True)
class InitFacts:
    """What `ergane init --check` gathered, for this module to judge (034 FR-010).

    Facts only — every field is something the CLI read from git, the registry or
    033's probes — so the judgment over them stays pure and table-testable. The
    `None` fields are "could not be determined", and each renders a *failing*
    finding: `control_plane=()` with no error fails, because unknown readiness is
    not readiness.
    """

    #: Absolute path of the repository judged; quoted in every remedy.
    repo_root: str
    #: The root this repo has — `.ergane`, or `.factory` when unmigrated.
    runtime_root: str = ".ergane"
    runtime_root_is_legacy: bool = False
    runtime_root_ignored: bool = True
    #: The `.gitignore` a remedy would edit, so the fix is copy-pasteable.
    gitignore: str = ""
    registry_path: str = ""
    #: The slug whose entry points here, or None when no entry does.
    registry_slug: str | None = None
    registry_error: str | None = None
    #: The manifest's landing branch, or None when the manifest did not load.
    landing_branch: str | None = None
    landing_branch_exists: bool = False
    #: 033's probe findings, carried through rather than re-derived.
    control_plane: tuple[Finding, ...] = field(default_factory=tuple)
    control_plane_error: str | None = None


def evaluate_repo(
    *,
    repo: str,
    default_branch: str,
    visibility: str,
    queue_enabled: bool,
    required_checks: Sequence[str],
    declared_gates: Sequence[str],
    factory_yaml_error: str | None = None,
    squash_merge_commit_title: str | None = None,
    init_facts: "InitFacts | None" = None,
) -> TargetRepoProfile:
    """Judge a target repo's facts against the factory's assumptions.

    Each argument is a *fact the activity already gathered*; this function holds
    no I/O. `required_checks` is what the queue will demand of a PR (the
    `merge_queue` rule's `required_status_checks`, or the classic-protection
    fallback), and `declared_gates` is what the repo's own `factory.yaml` names
    (`FactoryConfig.gates` keys). `factory_yaml_error`, when set, is the 002
    loader's `FactoryConfigError` message — a broken manifest is a failing
    finding, never a pass by default. `squash_merge_commit_title` is the repo's
    merge setting read via the REST repo endpoint; `None` means the setting was
    absent or unreadable, which also fails closed.

    The profile's `findings` are ordered so the operator preflight reads the
    repo's own health first (visibility, queue, manifest, squash title), then
    the gate↔check mapping, which is where a deterministic-CI repo most often
    diverges.
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

    # Squash-merge titles must come from the PR title so the landing grammar
    # survives the merge. An unreadable setting (absent in the REST payload) is
    # treated as a failure, matching the factory_yaml precedent.
    _squash_title_finding(findings, repo, squash_merge_commit_title)

    # The gate ↔ check mapping, by name (position is irrelevant).
    declared = set(declared_gates)
    required = set(required_checks)
    for gate in declared:
        _gate_check_finding(findings, gate, gate in required)
    for check in sorted(required - declared):
        _unknown_check_finding(findings, check)

    # Init's own checks, when the caller gathered them (034 FR-010). Appended
    # rather than interleaved so the 003 report an operator already knows how to
    # read does not change shape underneath them.
    findings.extend(evaluate_init_facts(init_facts))

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
        findings.append(Finding("factory_yaml", True, "manifest is valid"))
    else:
        findings.append(
            Finding(
                "factory_yaml",
                False,
                f"manifest failed to load: {factory_yaml_error} — fix the "
                "manifest so the repo declares its gates",
            )
        )


def _squash_title_finding(
    findings: list[Finding], repo: str, squash_merge_commit_title: str | None
) -> None:
    if squash_merge_commit_title == "PR_TITLE":
        findings.append(
            Finding("squash_title", True, "squash merges are titled from the PR title")
        )
        return

    if squash_merge_commit_title is None:
        observed = "unreadable"
        cause = (
            "the setting was not returned by the repo endpoint — this usually means "
            "the token lacks push permission on the repo, which is what hides GitHub's "
            "merge-settings fields"
        )
    else:
        observed = repr(squash_merge_commit_title)
        cause = f"observed value was {observed}"

    findings.append(
        Finding(
            "squash_title",
            False,
            f"squash_merge_commit_title is {observed}; {cause} — run "
            f"`gh api -X PATCH repos/{repo} -f squash_merge_commit_title=PR_TITLE`",
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


# --- 034 US4: the checks init's own facts answer -------------------------------


def evaluate_init_facts(init_facts: "InitFacts | None") -> tuple[Finding, ...]:
    """Judge the facts `ergane init --check` gathered — or nothing, when it did not.

    Split out of `evaluate_repo` for one reason: `onboard_target_repo` short
    circuits into `_profile_from_gh_failure` when `gh` cannot read the repo, and
    a repo with no GitHub remote is exactly the repo whose *local* findings
    matter most. Both paths call this, so a `gh` refusal never masks the
    gitignore check ("no failure masking another").

    Every check renders unconditionally: no early return, no exception skipping
    the rest. An unknown answer is a failing finding, never an absent one.
    """
    if init_facts is None:
        return ()

    findings: list[Finding] = []
    _runtime_root_findings(findings, init_facts)
    _registry_finding(findings, init_facts)
    _landing_branch_finding(findings, init_facts)
    _control_plane_finding(findings, init_facts)
    return tuple(findings)


def _runtime_root_findings(findings: list[Finding], facts: "InitFacts") -> None:
    """The runtime root must be ignored by git — the root this repo *has*.

    Trap 12: a repo that never ran `ergane repo migrate-runtime-root` keeps its
    state in `.factory/`. Demanding `.ergane/` there reports a failure the
    operator cannot act on while missing the directory actually holding their
    evidence, so the resolved root is judged and the legacy name earns a second
    finding naming its remedy.
    """
    root = facts.runtime_root
    if facts.runtime_root_ignored:
        findings.append(
            Finding("runtime_root_ignored", True, f"{root}/ is ignored by git")
        )
    else:
        findings.append(
            Finding(
                "runtime_root_ignored",
                False,
                f"{root}/ is not ignored by git; add the line `{root}/` to "
                f"{facts.gitignore} — the runtime root holds worktrees, session "
                "transcripts and verification evidence, and one that reaches git "
                "history lands megabytes of agent output on a landing branch",
            )
        )

    if facts.runtime_root_is_legacy:
        findings.append(
            Finding(
                "runtime_root_migration",
                False,
                f"this repository's runtime root is still the legacy {root}/; run "
                "`ergane repo migrate-runtime-root` to move it to .ergane/",
            )
        )


def _registry_finding(findings: list[Finding], facts: "InitFacts") -> None:
    """The engine must know where this repo is; the registry is how it knows."""
    if facts.registry_error is not None:
        findings.append(
            Finding(
                "registry_entry",
                False,
                f"the engine registry {facts.registry_path} could not be read: "
                f"{facts.registry_error} — it is a cache: re-derive it with "
                f"`ergane repo rebuild {facts.repo_root}`",
            )
        )
        return

    if facts.registry_slug is not None:
        findings.append(
            Finding(
                "registry_entry",
                True,
                f"registered as '{facts.registry_slug}' in {facts.registry_path}",
            )
        )
        return

    findings.append(
        Finding(
            "registry_entry",
            False,
            f"no entry in the engine registry {facts.registry_path} points at "
            f"{facts.repo_root}; run `ergane init` here to register it — the "
            "committed manifest is what makes a repo managed, but the engine "
            "cannot enumerate repos it has no pointer to",
        )
    )


def _landing_branch_finding(findings: list[Finding], facts: "InitFacts") -> None:
    """The branch the manifest declares must be a branch the repo has."""
    if facts.landing_branch is None:
        findings.append(
            Finding(
                "landing_branch",
                False,
                "the landing branch could not be judged: this repository's "
                "manifest did not load (see the factory_yaml finding)",
            )
        )
        return

    branch = facts.landing_branch
    if facts.landing_branch_exists:
        findings.append(
            Finding("landing_branch", True, f"landing branch '{branch}' exists")
        )
        return

    findings.append(
        Finding(
            "landing_branch",
            False,
            f"the manifest declares `landing_branch: {branch}` but "
            f"{facts.repo_root} has no such branch; create it with "
            f"`git -C {facts.repo_root} branch {branch}`, or declare the branch "
            "this repository actually lands on",
        )
    )


def _control_plane_finding(findings: list[Finding], facts: "InitFacts") -> None:
    """One summary finding over 033's probes, carrying their detail through.

    Fails closed three ways: the probes could not run, some probe failed, or no
    probe ran at all. The last is the one worth naming — "reachable" because
    nothing was probed would be worse than no check.
    """
    if facts.control_plane_error is not None:
        findings.append(
            Finding(
                "control_plane",
                False,
                f"the control plane could not be probed: {facts.control_plane_error}"
                " — `ergane install --verify` reports each subsystem separately",
            )
        )
        return

    if not facts.control_plane:
        findings.append(
            Finding(
                "control_plane",
                False,
                "no control-plane probe ran, so control-plane readiness is "
                "unknown; run `ergane install --verify` to see why",
            )
        )
        return

    failed: list[Finding] = []
    for probe in facts.control_plane:
        if not probe.passed:
            failed.append(probe)

    if not failed:
        names: list[str] = []
        for probe in facts.control_plane:
            names.append(probe.check)
        findings.append(
            Finding(
                "control_plane",
                True,
                f"control plane reachable: {len(names)} probes passed "
                f"({', '.join(names)})",
            )
        )
        return

    reasons: list[str] = []
    for probe in failed:
        reasons.append(f"{probe.check}: {probe.detail}")
    findings.append(
        Finding(
            "control_plane",
            False,
            f"{len(failed)} of {len(facts.control_plane)} control-plane probes "
            f"failed — {'; '.join(reasons)}",
        )
    )
