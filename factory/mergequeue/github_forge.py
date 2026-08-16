"""GitHub as the reference implementation of the forge seam (049-US1, D-046 §4).

Everything GitHub-shaped about reading a target repository lives here: the
rulesets payload, the classic branch-protection fallback, the repo-level merge
settings, and `nameWithOwner`. `factory/mergequeue/gh.py` stays exactly what it
was — the one place this component spawns `gh` — and this module sits *above* it
rather than through it, which is why nothing in `gh.py` had to move.

Two payload parsers came here verbatim from
`factory/activities/merge_activities.py`, where they were GitHub implementation
detail in a shared activity module. Both carry facts proved live on 2026-08-07
and easy to lose in a rewrite: the required checks ride a *sibling*
`required_status_checks` rule rather than the queue rule, and "Branch not
protected" is an answer rather than a failure.

A seam needing this repository re-provisioned would be a failed seam (FR-003),
so a GitHub target's judgment is byte-identical to the one it got before this
module existed: same commands, same order, same findings.
"""

from __future__ import annotations

from typing import Any

from factory.mergequeue.forge import (
    DEFAULT_FORGE,
    ForgeError,
    LandingPolicy,
    RepositoryDescription,
    register_forge,
)
from factory.mergequeue.gh import GH_NOT_FOUND, GhClient, GhError

#: What GitHub calls "title this landing from the proposal" (D-041). Spelled
#: once, here, where it is true — the shared judgment is US2's to free of it.
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
        self._description = RepositoryDescription(
            address=str(payload.get("nameWithOwner") or ""),
            default_branch=default_branch,
            visibility=str(payload.get("visibility") or ""),
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
        )


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
