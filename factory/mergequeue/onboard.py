"""The pure onboarding judgment: what a forge reported + gates → findings.

`onboard_target_repo` (the activity half) reads a repository through a forge and
hands the two readings here: a `RepositoryDescription` — can the factory reach
this repository, by what name, and what does only this forge have to say about
it — and a `LandingPolicy` for the branch it would land on. This module turns
them into a `TargetRepoProfile` whose `findings` say, one check at a time,
whether the repo is ready for the factory to dispatch against it. It is pure —
no forge, no git, no filesystem, no clock — so it is table-tested with no fakes
at all (`tests/test_onboard.py`).

**049's US2 made the questions forge-neutral, and that is the point of the
module.** Before it, this judgment asked every repository about three settings
only GitHub has, so a target on another forge failed onboarding not because it
was unready but because the questions did not apply to it (D-046). What the
factory actually
needs from a forge is three things: propose a change, have it gated on evidence
it can name, and land it with no human. The questions below are those, and
nothing here spells one forge's configuration; `tests/test_forge_readiness.py`
reads this file's source to keep it that way (FR-006).

The checks, each one a `Finding` (check slug, passed, actionable detail):

- **`gated_landing`** (Q2) — the branch must refuse a landing until a set of
  *named* checks passes. The weight is on **named**: the factory's contract is
  that the gates its manifest declares are the gates the forge runs, and that is
  checkable only if the checks are addressable by name.
- **`autonomous_landing`** (Q3) — once those checks pass, the forge must
  complete the merge on its own. Separate from Q2 because they are separately
  actionable: a branch that gates correctly and then waits for a click is one
  this factory cannot land through (D-024), and saying which of the two is
  missing is the difference between a report and a riddle.
- **`factory_yaml`** — the repo must commit a valid, non-empty-gated
  `factory.yaml`. A missing or malformed manifest is a failing finding carrying
  the 002 loader's error, never a pass by default: a verifier that shrugged at
  a broken manifest would find no gates, therefore see nothing fail.
- **`landing_title`** (Q5) — the commit the forge writes when it lands must
  carry the proposal's title verbatim, because `ergane spec landed` reads the
  story out of that subject line (`factory/workgraph/landed.py`). The forge's
  own spelling of the setting behind it travels as evidence, and its own remedy
  as the fix; neither is decided from here.
- **`gate_check:<gate>`** (Q4) — every declared gate must have a required check
  named *exactly* after it. The naming convention is the contract between
  `factory.yaml` and the repo's CI; a declared gate with no matching check
  would land a change that never runs that gate.
- **`unknown_check:<name>`** (Q4) — every required check must map back to a
  declared gate. Deterministic gates only is FR-003 made structural: a required
  check that is not a declared gate is a check the factory does not control, and
  this is precisely what keeps the LLM judge out of CI.

Q1 — reachability and identity — is answered before this module runs: a
repository nobody can read yields a `repo_read` finding from the activity, since
nothing else about it is judgeable. What a forge alone knows arrives on
`RepositoryDescription.findings` and is appended here without this module
knowing what it means (FR-007). That is what lets a forge-specific rule fail a
repository without the shared judgment learning that forge's vocabulary — and it
is where the rule that a GitHub repository must be public now lives.

Each check fails closed: `passed` is the conjunction, and a repo that fails any
check is rejected for dispatch with instructions for the operator (spec US3 AS2).
`evaluate_repo` is deliberately handed already-loaded readings (the activity owns
the forge calls and the `factory.yaml` read) so the judgment here can be proven
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

**034 US6 adds one more**: `roadmap_schedule`, failing when the repo has no
Temporal schedule, when the one it has is paused, and when that schedule's
arguments disagree with the committed manifest. Here rather than in a second
judgment for the reason the rest of this module exists — "ready" is decided in
exactly one place, and a joined repo with no scheduler is not ready.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from factory.mergequeue.forge import LandingPolicy, RepositoryDescription
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
    #: 034 US6.  The schedule this repo's slug names, and what is wrong with it.
    #: The defaults fail closed on purpose: a caller that gathered nothing has
    #: not established that a scheduler exists, and a repo with no scheduler is
    #: one whose `ready` specs dispatch nothing.
    schedule_id: str = ""
    schedule_present: bool = False
    schedule_paused: bool = False
    #: One line per declared field the live schedule states differently.
    schedule_drift: tuple[str, ...] = field(default_factory=tuple)
    #: Why the schedule could not be read at all — unreachable engine, or no
    #: registry entry naming the slug that would identify it.
    schedule_error: str | None = None


def evaluate_repo(
    *,
    repo: str,
    reading: "RepositoryDescription",
    policy: "LandingPolicy",
    declared_gates: Sequence[str],
    factory_yaml_error: str | None = None,
    init_facts: "InitFacts | None" = None,
) -> TargetRepoProfile:
    """Judge a repository's two readings against what the factory needs.

    Every argument is something a caller already read; this function holds no
    I/O. `reading` answers Q1 — the repository's address, the branch it defaults
    to, and whatever only its own forge can say about it. `policy` answers Q2,
    Q3 and Q5 for the branch a landing would go into, and carries the checks
    that branch will require, so Q4 can be asked here without this function
    knowing where a forge keeps them. `declared_gates` is what the repo's own
    `factory.yaml` names (`FactoryConfig.gates` keys). `factory_yaml_error`,
    when set, is the 002 loader's `FactoryConfigError` message — a broken
    manifest is a failing finding, never a pass by default.

    `reading.findings` is what the forge answered about facts only it has (049
    FR-007), appended without this function knowing what they mean, and read
    *first* so a forge-authored refusal lands where an operator has always found
    the repository's own health.

    The profile's `findings` are ordered so the operator preflight reads that
    health first, then the gate↔check mapping, which is where a
    deterministic-CI repo most often diverges.
    """

    findings: list[Finding] = list(reading.findings)

    # Q2: the branch must refuse a landing until named checks pass, and Q3: it
    # must then finish the job itself. One forge may answer both from one
    # setting; that is its coincidence, not a property of forges, so they are
    # two findings and an operator is told which one is missing.
    _gated_landing_finding(findings, policy)
    _autonomous_landing_finding(findings, policy)

    # The manifest must be present, valid, and declare gates. A broken manifest
    # is a failing finding carrying the loader's error — never a shrug that
    # would read as "no gates, so nothing to fail".
    _manifest_finding(findings, factory_yaml_error)

    # Q5: the landing commit must carry the proposal's title, so the landing
    # grammar survives the merge. A forge that would not say fails closed,
    # matching the factory_yaml precedent.
    _landing_title_finding(findings, policy)

    # Q4: the gate ↔ check mapping, by name (position is irrelevant).
    declared = set(declared_gates)
    required = set(policy.required_checks)
    for gate in declared:
        _gate_check_finding(findings, gate, gate in required)
    for check in sorted(required - declared):
        _unknown_check_finding(findings, check)

    # Init's own checks, when the caller gathered them (034 FR-010). Appended
    # rather than interleaved so the 003 report an operator already knows how to
    # read does not change shape underneath them.
    findings.extend(evaluate_init_facts(init_facts))

    return TargetRepoProfile.from_readiness(
        repo=repo,
        reading=reading,
        policy=policy,
        declared_gates=tuple(declared_gates),
        findings=tuple(findings),
        passed=all(f.passed for f in findings),
    )


# --- the checks ----------------------------------------------------------------


def _gated_landing_finding(findings: list[Finding], policy: "LandingPolicy") -> None:
    """Q2. A branch that lands a change no check ran against gates nothing."""
    if policy.gates_on_named_checks:
        findings.append(
            Finding(
                "gated_landing",
                True,
                f"{policy.branch} refuses a landing until its named checks pass",
            )
        )
        return

    findings.append(
        Finding(
            "gated_landing",
            False,
            f"{policy.branch!r} does not refuse a landing until named checks "
            "pass, so a change could land with no gate having run; configure "
            "the branch to require the gates this repository declares"
            f"{_remedy(policy.gating_remedy)}",
        )
    )


def _autonomous_landing_finding(
    findings: list[Finding], policy: "LandingPolicy"
) -> None:
    """Q3, and its own finding on purpose: gating right and landing wrong is a
    different repair from gating wrong, and one finding for both would tell an
    operator to fix the half that already works."""
    if policy.lands_without_a_human:
        findings.append(
            Finding(
                "autonomous_landing",
                True,
                f"{policy.branch} completes a landing without a human",
            )
        )
        return

    findings.append(
        Finding(
            "autonomous_landing",
            False,
            f"{policy.branch!r} will not complete a landing without a human; "
            "this factory has no human in the loop by construction (D-024), so "
            "configure the branch to land a proposal itself once its named "
            f"checks pass{_remedy(policy.gating_remedy)}",
        )
    )


def _remedy(remedy: str) -> str:
    """A forge's own fix, appended when it offered one (FR-007).

    Not every forge will, and a judgment that required one would be a judgment
    that could not read a forge which stayed silent. What is wrong is always
    said; how to fix it is said when somebody knew.
    """
    return f" — {remedy}" if remedy else ""


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


def _landing_title_finding(findings: list[Finding], policy: "LandingPolicy") -> None:
    """Q5. `ergane spec landed` reads the story off the landed subject line, so a
    landing titled from anything but the proposal is a story this factory built
    and cannot see it built."""
    if policy.landing_title_from_proposal:
        findings.append(
            Finding(
                "landing_title",
                True,
                "a landing commit takes the proposal's title",
            )
        )
        return

    if policy.landing_title_source is None:
        observed = "the forge would not report its title source, so it is unreadable"
    else:
        observed = f"the forge reports its title source as {policy.landing_title_source!r}"

    findings.append(
        Finding(
            "landing_title",
            False,
            f"a landing commit will not take the proposal's title — {observed}; "
            "`ergane spec landed` reads a story out of the landed subject line, "
            "so a landing titled from anything else is work this factory cannot "
            f"see it did{_remedy(policy.landing_title_remedy)}",
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
                f"gate '{gate}' is declared in factory.yaml but the landing "
                f"branch requires no check named '{gate}' — add it to the "
                "branch's required checks so the forge runs the gate the "
                "factory declares",
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
    _roadmap_schedule_finding(findings, init_facts)
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


def _roadmap_schedule_finding(findings: list[Finding], facts: "InitFacts") -> None:
    """The repo must have a scheduler, running, pointed here (034 FR-016).

    One finding whose detail names *every* problem found rather than the first:
    a schedule both paused and drifted has two things wrong with it, and naming
    only one would be the masking this judgment forbids.  Each failure ends in
    the command that fixes it — the operator reading it is at a terminal.
    """
    if facts.schedule_error is not None:
        findings.append(
            Finding(
                "roadmap_schedule",
                False,
                "this repository's roadmap schedule could not be judged: "
                f"{facts.schedule_error}",
            )
        )
        return

    if not facts.schedule_present:
        findings.append(
            Finding(
                "roadmap_schedule",
                False,
                f"no roadmap schedule '{facts.schedule_id}' exists on the control "
                f"plane, so no tick will ever dispatch {facts.repo_root}'s specs — "
                f"run `ergane init {facts.repo_root}` to create it; flipping a spec "
                "to `ready` without one does nothing, with no error",
            )
        )
        return

    problems: list[str] = []
    if facts.schedule_paused:
        problems.append(
            "it is paused, so no tick will start a run — resume it with "
            "`ergane roadmap resume <specs root>` when you mean dispatch to run"
        )
    for line in facts.schedule_drift:
        problems.append(line)

    if not problems:
        findings.append(
            Finding(
                "roadmap_schedule",
                True,
                f"roadmap schedule '{facts.schedule_id}' is running and matches "
                "the manifest",
            )
        )
        return

    remedy = f" — re-run `ergane init {facts.repo_root}`" if facts.schedule_drift else ""
    findings.append(
        Finding(
            "roadmap_schedule",
            False,
            f"roadmap schedule '{facts.schedule_id}' disagrees with this "
            f"repository: {'; '.join(problems)}{remedy}",
        )
    )
