"""GitHub as the reference implementation of the forge seam (049-US1, D-046 §4).

Everything GitHub-shaped about reading a target repository lives here: the
rulesets payload, the classic branch-protection fallback, the repo-level merge
settings, and `nameWithOwner` — and, since US3, the landing half beside it.
`factory/mergequeue/gh.py` stays exactly what it was — the one place this
component spawns `gh` — and this module sits *above* it rather than through it,
which is why nothing in `gh.py` had to move.

Two payload parsers came here verbatim from
`factory/activities/merge_activities.py`, where they were GitHub implementation
detail in a shared activity module. Both carry facts proved live on 2026-08-07
and easy to lose in a rewrite: the required checks ride a *sibling*
`required_status_checks` rule rather than the queue rule, and "Branch not
protected" is an answer rather than a failure.

A seam needing this repository re-provisioned would be a failed seam (FR-003),
so a GitHub target sees the same commands in the same order as before the seam.

049's US2 moved D-007 here, where it is true: "the repo must be public" is a
GitHub billing constraint, not a readiness question, so it arrives as a finding
on `RepositoryDescription` instead of being asked of forges with no notion of
visibility (FR-007) — as does `landing_title_remedy`.
"""

from __future__ import annotations

from typing import Any

from factory.mergequeue.forge import (
    DEFAULT_FORGE,
    ForgeError,
    LandingPolicy,
    Proposal,
    RepositoryDescription,
    register_forge,
)
from factory.mergequeue.gh import (
    GH_NOT_FOUND,
    GhClient,
    GhError,
    _FAILED_LOG_TOTAL_LIMIT,
    _parse_run_id,
    _tail,
)
from factory.mergequeue.models import CheckFailure, Finding, PrSnapshot

#: What GitHub calls "title this landing from the proposal" (D-041), spelled
#: once, here, where it is true.
_TITLE_FROM_PROPOSAL = "PR_TITLE"


class GithubForge:
    """Reads a GitHub repository through `client`, and answers in neutral terms."""

    def __init__(self, client: GhClient) -> None:
        self.client = client
        self._description: RepositoryDescription | None = None

    def describe_repository(self) -> RepositoryDescription:
        """One `gh repo view`, cached: the address every later call addresses."""
        if self._description is not None:
            return self._description
        try:
            payload = self.client.repo_view()
        except GhError as error:
            raise _refused(error) from error

        # `defaultBranchRef` is an object (`{"name": ...}`), not a bare string —
        # stringifying the dict sent the rules query to a branch named
        # "{'name': 'ergane-buildout'}" on the first real onboarding run.
        default_ref = payload.get("defaultBranchRef") or {}
        default_branch = (
            str(default_ref.get("name") or "")
            if isinstance(default_ref, dict)
            else str(default_ref)
        )
        visibility = str(payload.get("visibility") or "")
        self._description = RepositoryDescription(
            address=str(payload.get("nameWithOwner") or ""),
            default_branch=default_branch,
            visibility=visibility,
            # D-007 is GitHub's own answer about whether this repository can be
            # gated and landed at all, so GitHub is where it is stated (FR-007).
            findings=(_readiness_visibility_finding(visibility),),
        )
        return self._description

    def landing_policy(self, branch: str) -> LandingPolicy:
        """GitHub's answer to Q2, Q3 and Q5 for one branch.

        The merge queue answers Q2 and Q3 together — a branch it governs refuses
        a landing until the required checks pass, then lands it with no human in
        the loop — so both come off the same rule. They stay separate fields
        because that is GitHub's coincidence, not a property of forges.
        """
        address = self.describe_repository().address
        try:
            settings = self.client.merge_settings(address)
            title_source = settings.get("squash_merge_commit_title")
            if title_source is not None:
                title_source = str(title_source)

            gated, checks = _queue_from_rules(
                self.client.rules_for_branch(address, branch)
            )
            if checks is None:
                # The queue is on but names no check in the rules payload: the
                # repository may configure them through classic protection.
                try:
                    checks = _classic_contexts(
                        self.client.classic_branch_protection(address, branch)
                    )
                except GhError as error:
                    if error.kind != GH_NOT_FOUND:
                        raise
                    # "Branch not protected" is an answer, not a failure (proved
                    # live 2026-08-07): the repo configures no checks there.
                    checks = []
        except GhError as error:
            raise _refused(error) from error

        return LandingPolicy(
            branch=branch,
            gates_on_named_checks=gated,
            required_checks=tuple(checks or ()),
            lands_without_a_human=gated,
            landing_title_from_proposal=title_source == _TITLE_FROM_PROPOSAL,
            landing_title_source=title_source,
            # GitHub's own one-call fix, which no neutral sentence can express.
            landing_title_remedy=_readiness_title_remedy(address, title_source),
        )

    # --- the landing half (049-US3, FR-009) ----------------------------------
    #
    # One `GhClient` call each, plus a translation into a neutral record: this
    # class is all that stands between `gh.py` and the activities.

    def find_proposal(self, head: str) -> Proposal | None:
        """`gh pr list --head <head> --state open`, as a proposal or nothing."""
        try:
            found = self.client.find_existing_pr(head)
        except GhError as error:
            raise _refused(error) from error
        return None if found is None else Proposal(found.number, found.url)

    def open_proposal(
        self, *, base: str, head: str, title: str, body_file: str
    ) -> Proposal:
        """`gh pr create` — ready, never `--draft`: a draft never enters the queue."""
        try:
            made = self.client.create_pr(
                base=base, head=head, title=title, body_file=body_file
            )
        except GhError as error:
            raise _refused(error) from error
        return Proposal(made.number, made.url)

    def request_landing(self, proposal: int, *, declared_method: str = "") -> None:
        """`gh pr merge <n> --auto` — the factory's only merge invocation.
        `declared_method` crosses the seam and stops here, proved live
        2026-08-07: a branch governed by a merge-queue ruleset owns its merge
        method and `gh` refuses the flag outright ("The merge strategy for
        <branch> is set by the merge queue"), so the operator's declared intent
        is something their configuration must agree with, not a flag sent."""
        try:
            self.client.enqueue_pr(proposal, merge_method=declared_method)
        except GhError as error:
            raise _refused(error) from error

    def observe_proposal(self, proposal: int) -> PrSnapshot:
        """One `gh pr view`. `from_gh_json` is GitHub's own payload reader and the
        record's constructor is where `mergeStateStatus` becomes the neutral
        conflict fact (FR-010), so this is a call and a translation."""
        try:
            return self.client.poll_pr(proposal)
        except GhError as error:
            raise _refused(error) from error

    def withdraw_landing(self, proposal: int) -> None:
        """`gh pr merge <n> --disable-auto` — the kill path's half of FR-008."""
        try:
            self.client.disable_auto_merge(proposal)
        except GhError as error:
            raise _refused(error) from error

    def failing_check_evidence(
        self, proposal: int, check_names: tuple[str, ...]
    ) -> tuple[CheckFailure, ...]:
        """`gh pr checks` plus one `gh run view --log-failed` per named check.
        Came here whole from `merge_activities.py`, where the run-id parsing and
        log bounds were GitHub detail in an activity module. Every `gh` failure
        returns degraded evidence stating the absence, never a raise."""
        try:
            entries = {entry.name: entry for entry in self.client.pr_checks(proposal)}
        except GhError as error:
            note = f"log unavailable: could not list checks ({error.kind})"
            return tuple(CheckFailure(name, "", "", note) for name in check_names)

        results: list[CheckFailure] = []
        spent = 0
        for name in check_names:
            entry = entries.get(name)
            if entry is None:
                results.append(CheckFailure(
                    name, "", "",
                    "log unavailable: check not present in gh pr checks",
                ))
                continue
            run_id = _parse_run_id(entry.link)
            if run_id is None:
                results.append(CheckFailure(
                    name, entry.link, "",
                    "log unavailable: could not resolve run id from check link",
                ))
                continue
            try:
                log = self.client.run_failed_log(run_id)
            except GhError as error:
                results.append(CheckFailure(
                    name, entry.link, "",
                    f"log unavailable: could not fetch run log ({error.kind})",
                ))
                continue
            if spent + len(log.encode("utf-8")) > _FAILED_LOG_TOTAL_LIMIT:
                log = _tail(log, max(_FAILED_LOG_TOTAL_LIMIT - spent, 0))
            spent += len(log.encode("utf-8"))
            results.append(CheckFailure(name, entry.link, log, ""))
        return tuple(results)


def _readiness_visibility_finding(visibility: str) -> Finding:
    """D-007 as GitHub's own finding, verbatim from the judgment it left.

    It did not soften crossing the seam — still *failing*, because
    private-on-Free cannot ever enqueue and advice is what nobody acts on.
    """
    if str(visibility).strip().lower() == "public":
        return Finding("visibility", True, "repo is public")
    return Finding(
        "visibility",
        False,
        f"repo is {visibility!r}; the merge queue is available on any "
        "plan only for public repos — make the repo public, or dispatch "
        "against a public target (D-007)",
    )


def _readiness_title_remedy(address: str, title_source: str | None) -> str:
    """How to make GitHub title a landing from the proposal — one `gh` call.

    An absent setting gets the cause too: GitHub hides these fields from a token
    without push permission, so PATCH alone would be run and watched to fail.
    """
    call = (
        f"run `gh api -X PATCH repos/{address} "
        "-f squash_merge_commit_title=PR_TITLE`"
    )
    if title_source is None:
        return (
            "the setting was not returned by the repo endpoint — this usually "
            "means the token lacks push permission on the repo, which is what "
            f"hides GitHub's merge-settings fields — {call}"
        )
    return call


def _refused(error: GhError) -> ForgeError:
    """Carry `gh`'s own taxonomy across the seam rather than flattening it."""
    return ForgeError(error.kind, str(error), error.stderr_tail)


def _queue_from_rules(rules: list[dict[str, Any]]) -> tuple[bool, list[str] | None]:
    """The merge-queue rule from a branch-rules list, and its required checks.

    Returns `(queue_enabled, required_checks)`. In the real rulesets payload
    the required checks ride a *sibling* `required_status_checks` rule (proved
    live 2026-08-07); a queue rule may also embed them, and both places are
    read. `required_checks` is `None` when the queue is enabled but no rule
    names a check (so the caller falls back to classic protection); it is `[]`
    when the queue rule is absent.
    """
    queue_enabled = False
    contexts: list[str] = []
    for rule in rules:
        rule_type = str(rule.get("type") or "")
        parameters = rule.get("parameters")
        if rule_type == "merge_queue":
            queue_enabled = True
        elif rule_type != "required_status_checks":
            continue
        if not isinstance(parameters, dict):
            continue
        checks = parameters.get("required_status_checks")
        if isinstance(checks, list):
            contexts += [
                str(c.get("context") or "") for c in checks if isinstance(c, dict)
            ]
    if not queue_enabled:
        return False, []
    return True, [c for c in contexts if c] or None


def _classic_contexts(protection: dict[str, Any]) -> list[str]:
    """The required-check contexts a classic branch-protection payload names."""
    checks = protection.get("required_status_checks")
    if isinstance(checks, dict):
        contexts = checks.get("contexts")
        if isinstance(contexts, list):
            return [str(c) for c in contexts]
    return []


def _build_github(
    *, repo_path: str = "", client: Any = None, **_unused: Any
) -> GithubForge:
    """The registered builder: a forge over the clone at `repo_path`.

    `client` is the seam beneath the seam — tests that script `gh` hand one in,
    so no test reaches the default and spawns a subprocess.
    """
    return GithubForge(client if client is not None else GhClient(repo=repo_path))


register_forge(DEFAULT_FORGE, _build_github)
