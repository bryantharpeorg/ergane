"""Tests for `ergane init --wire` (034 US3): GitHub wired to enforce the declarations.

The spec's Independent Test names "a disposable public GitHub repo". That is not
reachable from a test suite that must be green offline, in a sandbox, on a fresh
clone — and worse, it is unprovable from a diff (constitution Principle VIII), so
a criterion resting on it can never be checked by the judge. It is reconstructed
here as a **model of a GitHub repository** driven through the real `gh` argv
surface: `FakeGitHub` below.

Why that model cannot make a vacuous test pass — the trap this repository has
paid for five times in two days:

- It is a *model*, not a recorder: reads are served from mutable state, changed
  only by a write production actually issued. Write payloads are read back off
  the temp file `GhClient` wrote for `gh api --input`, so the model learns what
  production sent, never what the test intended; an unmodelled call raises.
- The primary assertion is not on the call log. It runs the factory's own reader
  — `onboard_target_repo` -> `evaluate_repo`, the gate at every epic start — and
  requires `profile.passed`. With the wiring doing nothing the model keeps its
  fresh-repo state, so `landing_title`, `gated_landing` and `gate_check:*` fail.

**No real GitHub repository is touched by anything in this file**: every
`GhClient` here is constructed with `runner=<the model>`.

US4 LANDED MID-STORY and changed what this file can assert: FR-010 makes the
check init's automatic last act, and the check *reads* GitHub, so plain `ergane
init` is no longer silent on the wire — measured, three read-only calls. Two
consequences, fixed rather than papered over:

- `test_plain_init_wires_nothing...` asserted `github.calls == []`, now false by
  design; it asserts what it was really protecting (plain init *writes* nothing)
  and pins those three reads exactly.
- US4's check output itself says "default branch", so the divergence assertion
  was unfalsifiable against whole stdout — with `_divergence_step` deleted the
  phrase was still there, from the check. Both branch assertions now read
  `wiring_report(...)` alone, and mutant 9 kills them again.

MUTATION EVIDENCE — each production line disabled on its own, the whole module
re-run, that run's summary pasted. Command for every row:
`uv run pytest -q tests/test_ergane_init_wiring.py` (13 items). All reverted.

  1  squash-title PATCH never fires            3 failed, 10 passed
  2  merge-queue ruleset never created         4 failed,  9 passed
  3  ruleset requires one check more           3 failed, 10 passed
  4  _ruleset_satisfies -> return False        1 failed, 12 passed
  5  squash title re-PATCHed when correct      1 failed, 12 passed
  6  D-007 visibility refusal dropped          1 failed, 12 passed
  7  gh prerequisite probe dropped             2 failed, 11 passed
  8  job `name:` drifts to `<gate>-job`        2 failed, 11 passed
  9  divergence never reported                 1 failed, 12 passed
 10  existing CI never noticed                 1 failed, 12 passed
 11  gh refusals stop being caught             2 failed, 11 passed

Rows 1-3 are load-bearing: each dies on the onboarding-gate assertion, naming the
finding its missing act was meant to satisfy — 1 `('squash_title', "... is
'COMMIT_OR_PR_TITLE'")`, 2 `('merge_queue', "not enabled on the default branch
'main'")`, 3 `('unknown_check:coverage', "...not a declared gate (FR-003)")`.

REAL RUN, re-captured on the merged tree — `ergane init --wire` against a git
repo with no GitHub remote. No mutating call is reachable there, which is what
makes it safe, and it drives the real `gh` binary, client and refusal:

    $ ergane init --wire /tmp/.../smokerepo2     # answers piped to the interview
    ergane: `gh` refused while wiring this repository (GH_REFUSED): no git remotes
    found
      check the checkout has an `origin` remote on GitHub that your token can see
      (git remote -v), and
      ... [the admin-rights remedy, then the four manual steps]
    the repo-local half of init is complete and unchanged in /tmp/.../smokerepo2:
      gates workflow: applied
        wrote .github/workflows/ergane-gates.yml, one job per declared gate

FULL SUITE, after every mutation was reverted:

    $ uv run pytest -q
    2725 passed, 44 skipped, 4 warnings in 281.16s (0:04:41)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

import pytest
import yaml

import factory.cli.init as init_module
from factory.activities.merge_activities import onboard_target_repo
from factory.cli.errors import EXIT_OK, EXIT_USER
from factory.mergequeue import wiring
from factory.mergequeue.gh import GhClient
from factory.mergequeue.github_forge import GithubForge
from factory.mergequeue.forge import LandingPolicy, RepositoryDescription
from factory.mergequeue.onboard import evaluate_repo
from factory.verify.factory_yaml import _SUPPORTED_VERSION, parse_factory_config

from tests.test_ergane_init import Run, ScriptedPrompter, _invoke, make_bare_repo
from tests.test_ergane_init_check import bind_offline_seams

# The model of a GitHub repository


@dataclass
class _Result:
    """What one scripted `gh` invocation returned — the shape `GhClient` reads."""

    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


@dataclass
class FakeGitHub:
    """A mutable model of one GitHub repository, driven through the `gh` argv surface.

    Reads are served from state; writes change it. It starts as a *fresh* public
    repo: no rulesets, `squash_merge_commit_title` at GitHub's default — so three
    of `evaluate_repo`'s five checks fail until something wires them.
    """

    owner_repo: str = "acme/app"
    visibility: str = "PUBLIC"
    is_in_organization: bool = True
    default_branch: str = "main"
    squash_merge_commit_title: str = "COMMIT_OR_PR_TITLE"
    allow_auto_merge: bool = False
    refuse_allow_auto_merge_patch: bool = False
    gh_installed: bool = True
    logged_in: bool = True
    on_github: bool = True
    admin: bool = True
    rulesets: dict[int, dict[str, Any]] = field(default_factory=dict)
    calls: list[tuple[str, ...]] = field(default_factory=list)
    _next_id: int = 1

    # --- the runner seam -----------------------------------------------------

    def __call__(self, argv: Sequence[str], cwd: str) -> _Result:
        args = tuple(argv)
        self.calls.append(args)

        if not self.gh_installed:
            # What an absent binary really does to `subprocess.run`.
            raise FileNotFoundError(2, "No such file or directory: 'gh'")

        if args[:2] == ("auth", "status"):
            if self.logged_in:
                return _Result(stdout="github.com\n  Logged in to github.com\n")
            return _Result(
                stderr=(
                    "You are not logged into any GitHub hosts. "
                    "To log in, run: gh auth login"
                ),
                returncode=1,
            )

        if args[:2] == ("repo", "view"):
            if not self.on_github:
                return _Result(
                    stderr=(
                        "none of the git remotes configured for this repository "
                        "point to a known GitHub host"
                    ),
                    returncode=1,
                )
            return self._json(
                {
                    "nameWithOwner": self.owner_repo,
                    "visibility": self.visibility,
                    "isInOrganization": self.is_in_organization,
                    "defaultBranchRef": {"name": self.default_branch},
                }
            )

        if args[:1] == ("api",):
            return self._api(args)

        raise AssertionError(f"FakeGitHub does not model `gh {' '.join(args)}`")

    # --- the REST surface ----------------------------------------------------

    def _api(self, args: tuple[str, ...]) -> _Result:
        method = "GET"
        endpoint: str | None = None
        fields: dict[str, str] = {}
        body: Any = None

        index = 1
        while index < len(args):
            token = args[index]
            if token == "-X":
                method = args[index + 1]
                index += 2
            elif token == "-f":
                key, _, value = args[index + 1].partition("=")
                fields[key] = value
                index += 2
            elif token == "--input":
                # The payload is read off the file production actually wrote.
                body = json.loads(Path(args[index + 1]).read_text(encoding="utf-8"))
                index += 2
            elif token.startswith("-"):
                index += 1
            else:
                if endpoint is None:
                    endpoint = token
                index += 1

        if endpoint is None:
            raise AssertionError(f"`gh {' '.join(args)}` names no endpoint")

        if method != "GET" and not self.admin:
            return _Result(
                stderr="Resource not accessible by personal access token (HTTP 403)",
                returncode=1,
            )

        prefix = f"repos/{self.owner_repo}"
        if endpoint == prefix:
            if method == "PATCH" and "squash_merge_commit_title" in fields:
                self.squash_merge_commit_title = fields["squash_merge_commit_title"]
            if method == "PATCH" and "allow_auto_merge" in fields:
                if self.refuse_allow_auto_merge_patch:
                    return _Result(
                        stderr="Resource not accessible by personal access token (HTTP 403)",
                        returncode=1,
                    )
                value = fields["allow_auto_merge"].lower()
                self.allow_auto_merge = value in ("1", "true", "yes", "on")
            return self._json(self._repo_payload())

        if endpoint == f"{prefix}/rulesets":
            if method == "POST":
                return self._json(self._create_ruleset(body))
            return self._json(
                [
                    {"id": rid, "name": rs["name"], "target": rs.get("target", "branch")}
                    for rid, rs in sorted(self.rulesets.items())
                ]
            )

        if endpoint.startswith(f"{prefix}/rulesets/"):
            ruleset_id = int(endpoint.rsplit("/", 1)[1])
            if ruleset_id not in self.rulesets:
                return _Result(stderr="gh: Not Found (HTTP 404)", returncode=1)
            if method == "PUT":
                stored = dict(body or {})
                stored["id"] = ruleset_id
                self.rulesets[ruleset_id] = stored
            return self._json(self.rulesets[ruleset_id])

        if endpoint.startswith(f"{prefix}/rules/branches/"):
            branch = endpoint.rsplit("/", 1)[1]
            return self._json(self._rules_for_branch(branch))

        if endpoint.startswith(f"{prefix}/branches/"):
            # Classic protection: this repo configures none, and GitHub answers
            # 404 "Branch not protected" — an answer, not a failure.
            return _Result(stderr="gh: Branch not protected (HTTP 404)", returncode=1)

        raise AssertionError(f"FakeGitHub does not model the endpoint {endpoint!r}")

    def _repo_payload(self) -> dict[str, Any]:
        return {
            "visibility": self.visibility.lower(),
            "squash_merge_commit_title": self.squash_merge_commit_title,
            "allow_auto_merge": self.allow_auto_merge,
        }

    def _create_ruleset(self, body: Any) -> dict[str, Any]:
        if not isinstance(body, dict):
            raise AssertionError("ruleset creation sent no JSON body")
        ruleset_id = self._next_id
        self._next_id += 1
        stored = dict(body)
        stored["id"] = ruleset_id
        self.rulesets[ruleset_id] = stored
        return stored

    def _rules_for_branch(self, branch: str) -> list[dict[str, Any]]:
        """The flat rule list GitHub returns for one branch, across all rulesets."""
        ref = f"refs/heads/{branch}"
        rules: list[dict[str, Any]] = []
        for ruleset_id, ruleset in sorted(self.rulesets.items()):
            if str(ruleset.get("enforcement") or "") != "active":
                continue
            conditions = ruleset.get("conditions") or {}
            ref_name = conditions.get("ref_name") or {}
            include = ref_name.get("include") or []
            matched = ref in include or "~ALL" in include
            if "~DEFAULT_BRANCH" in include and branch == self.default_branch:
                matched = True
            if not matched:
                continue
            for rule in ruleset.get("rules") or []:
                entry = dict(rule)
                entry["ruleset_id"] = ruleset_id
                rules.append(entry)
        return rules

    @staticmethod
    def _json(payload: Any) -> _Result:
        return _Result(stdout=json.dumps(payload))

    def snapshot(self) -> str:
        """Every byte of repo state this model holds, order-independent."""
        return json.dumps(
            {
                "visibility": self.visibility,
                "default_branch": self.default_branch,
                "squash_merge_commit_title": self.squash_merge_commit_title,
                "allow_auto_merge": self.allow_auto_merge,
                "rulesets": {str(k): v for k, v in self.rulesets.items()},
            },
            sort_keys=True,
        )

    def mutations(self) -> list[tuple[str, ...]]:
        """Every invocation that asked GitHub to change something."""
        found: list[tuple[str, ...]] = []
        for call in self.calls:
            if "-X" not in call:
                continue
            method = call[call.index("-X") + 1]
            if method in ("POST", "PUT", "PATCH", "DELETE"):
                found.append(call)
        return found


# Fixtures

# Spec US3-S1 says "declared gates `test` and `smoke`". `smoke` cannot exist:
# manifest schema v1 fixes the legal gate names to test/lint/typecheck and the
# parser refuses anything else, so a `smoke` fixture fails at manifest load, not
# at wiring. `lint` stands in for it — the scenario's shape (two gates, two
# required checks, two jobs) is what is under test, and the spec needs the fix.
TWO_GATES = 'test: "uv run pytest -q"\nlint: "ruff check ."'


def answers(*, gates: str = TWO_GATES, landing_branch: str = "main", slug: str = "myapp") -> list[str]:
    """version, runtime, gates, timeouts, standards, landing branch, roadmap, forge, slug."""
    return [str(_SUPPORTED_VERSION), "bwrap", gates, "", "", landing_branch, "", "", slug]


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Run]:
    """Run `ergane init` with a scripted interview and an injected GitHub model."""

    def runner(*argv: str, script: list[str], github: FakeGitHub) -> Run:
        prompter = ScriptedPrompter(script)
        monkeypatch.setattr(init_module, "_prompter_factory", lambda: prompter)
        # US4's own binder, not a second copy: a full init's last act is the
        # check (FR-010), which reaches the control plane as well as GitHub, so
        # binding only the `gh` seam here would probe the operator's real one.
        # `FakeGitHub` is a `GhRunner`, exactly like the `FakeGh` it expects.
        bind_offline_seams(monkeypatch, github)
        return _invoke(list(argv))

    return runner


def onboarding_profile(repo: Path, github: FakeGitHub) -> Any:
    """`EpicWorkflow._onboard_target`'s judgment verbatim, run against the wired
    model. Nothing here knows what the wiring intended to do."""
    return onboard_target_repo(
        GithubForge(GhClient(repo=str(repo), runner=github)), str(repo)
    )


def wiring_report(stdout: str) -> str:
    """Only the `--wire` report. US4's check also says "default branch", so an
    assertion over whole stdout could pass on the check's words, proving nothing."""
    return stdout.split("wiring:", 1)[1].split("next, run:", 1)[0]


def failed(profile: Any) -> list[tuple[str, str]]:
    return [(f.check, f.detail) for f in profile.findings if not f.passed]


# T019 / spec US3-S1 — wiring produces a repo the factory will dispatch against


def test_wiring_makes_the_repo_pass_the_factorys_own_onboarding_gate(
    wired: Callable[..., Run], tmp_path: Path
) -> None:
    """S1: after wiring, the gate that runs at *every* epic start passes. All five
    of `evaluate_repo`'s checks are named, so none can be silently dropped."""
    repo = make_bare_repo(tmp_path, {"pyproject.toml": "[project]\nname='app'\n"})
    github = FakeGitHub(owner_repo="acme/app", default_branch="main")

    result = wired("init", "--wire", str(repo), script=answers(), github=github)

    assert result.code == EXIT_OK, result.stderr

    profile = onboarding_profile(repo, github)
    assert profile.passed, failed(profile)

    checks = {f.check for f in profile.findings}
    assert checks == {
        "visibility", "gated_landing", "autonomous_landing", "factory_yaml",
        "landing_title", "gate_check:test", "gate_check:lint",
    }
    assert profile.default_branch == "main"
    assert sorted(profile.required_checks) == ["lint", "test"]

    # Landing branch and default branch agree here, so the report says nothing
    # about branches: a warning that always fires is one nobody reads.
    assert "default branch" not in wiring_report(result.stdout)


def test_wiring_writes_a_workflow_whose_jobs_are_the_gates(
    wired: Callable[..., Run], tmp_path: Path
) -> None:
    """S1: the scaffolded workflow defines jobs named `test` and `lint` — the job
    `name` is what GitHub names the check run after."""
    repo = make_bare_repo(tmp_path, {"pyproject.toml": "[project]\nname='app'\n"})
    github = FakeGitHub()

    result = wired("init", "--wire", str(repo), script=answers(), github=github)
    assert result.code == EXIT_OK, result.stderr

    workflow = repo / wiring.WORKFLOW_PATH
    assert workflow.is_file()
    text = workflow.read_text(encoding="utf-8")

    parsed = yaml.safe_load(text)
    jobs = parsed["jobs"]
    assert [job["name"] for job in jobs.values()] == ["test", "lint"]

    commands = {
        job["name"]: [step["run"] for step in job["steps"] if "run" in step]
        for job in jobs.values()
    }
    assert commands == {"test": ["uv run pytest -q"], "lint": ["ruff check ."]}

    # A workflow that fires only on `pull_request` produces no check the queue
    # can wait on.
    assert "merge_group:" in text

    # One job block, rendered exactly — nothing about the output taken on trust.
    assert (
        '  test:\n    name: "test"\n    runs-on: ubuntu-latest\n    steps:\n'
        '      - uses: actions/checkout@v4\n      - name: "test"\n'
        '        run: "uv run pytest -q"\n'
    ) in text

    # And the operator is told to commit it, like everything else init writes.
    assert str(wiring.WORKFLOW_PATH) in result.stdout


# T022 / plan trap 9 — the generated workflow declares exactly the gates


def test_the_generated_jobs_produce_no_unknown_check_finding(
    wired: Callable[..., Run], tmp_path: Path
) -> None:
    """Trap 9: the generated job names, fed through the pure judgment as required
    checks. An undeclared job surfaces as `unknown_check:<name>`."""
    repo = make_bare_repo(tmp_path, {"pyproject.toml": "[project]\nname='app'\n"})
    github = FakeGitHub()
    assert wired("init", "--wire", str(repo), script=answers(), github=github).code == EXIT_OK

    parsed = yaml.safe_load((repo / wiring.WORKFLOW_PATH).read_text(encoding="utf-8"))
    job_names = [job["name"] for job in parsed["jobs"].values()]

    profile = evaluate_repo(
        repo="acme/app",
        reading=RepositoryDescription(address="acme/app", default_branch="main"),
        policy=LandingPolicy(
            branch="main", gates_on_named_checks=True, lands_without_a_human=True,
            required_checks=tuple(job_names), landing_title_from_proposal=True,
        ),
        declared_gates=["test", "lint"],
    )

    assert [f.check for f in profile.findings if f.check.startswith("unknown_check:")] == []
    assert profile.passed, failed(profile)


# T020 / spec US3-S2 — idempotence


def test_rewiring_reports_already_satisfied_and_changes_nothing(
    wired: Callable[..., Run], tmp_path: Path
) -> None:
    """S2: a re-run reports already-satisfied, issues no write, and alters no byte.

    "Changes nothing" both ways round: the model's whole state is byte-compared
    across the re-run (catching a no-op write), *and* the re-run must have issued
    no mutating call at all (catching a write GitHub would have counted).
    """
    repo = make_bare_repo(tmp_path, {"pyproject.toml": "[project]\nname='app'\n"})
    github = FakeGitHub()

    first = wired("init", "--wire", str(repo), script=answers(), github=github)
    assert first.code == EXIT_OK, first.stderr
    assert github.mutations(), "the first run must actually wire something"

    before = github.snapshot()
    workflow_before = (repo / wiring.WORKFLOW_PATH).read_text(encoding="utf-8")
    github.calls.clear()

    second = wired("init", "--wire", str(repo), script=answers(), github=github)

    assert second.code == EXIT_OK, second.stderr
    assert github.snapshot() == before
    assert github.mutations() == []
    assert (repo / wiring.WORKFLOW_PATH).read_text(encoding="utf-8") == workflow_before

    assert second.stdout.count(wiring.ALREADY_SATISFIED) >= 3
    assert onboarding_profile(repo, github).passed


# T021 / spec US3-S3 — the visibility refusal


def test_a_private_repo_is_refused_at_the_visibility_check_citing_d007(
    wired: Callable[..., Run], tmp_path: Path
) -> None:
    """S3: refused naming Enterprise Cloud and Team's insufficiency; the scaffold half is still usable."""
    repo = make_bare_repo(tmp_path, {"pyproject.toml": "[project]\nname='app'\n"})
    github = FakeGitHub(visibility="PRIVATE")

    result = wired("init", "--wire", str(repo), script=answers(), github=github)

    assert result.code == EXIT_USER
    assert "Enterprise Cloud" in result.stderr
    assert "Team" in result.stderr
    # Both remedies, named.
    assert "public" in result.stderr.lower()

    # Refused at the check, before anything was changed.
    assert github.mutations() == []

    # The scaffold half of init survives the refusal and still parses.
    manifest = repo / "ergane.yaml"
    assert manifest.is_file()
    config = parse_factory_config(manifest.read_text(encoding="utf-8"), source="ergane.yaml")
    assert sorted(config.gates) == ["lint", "test"]
    assert ".ergane/" in (repo / ".gitignore").read_text(encoding="utf-8")


# T021 / spec US3-S4 — `gh` absent or unauthenticated


@pytest.mark.parametrize(
    "flaw, expected",
    [
        # S4: `gh` absent — the prerequisite named, and the manual steps offered.
        (
            {"gh_installed": False},
            ["not installed", "gh api -X PATCH repos/", "test", "lint"],
        ),
        # S4: `gh` present but not logged in — the exact login command.
        ({"logged_in": False}, ["gh auth login", "manual"]),
        # No GitHub `origin`: what a freshly `git init`-ed repo looks like.
        ({"on_github": False}, ["git remote -v"]),
        # A 403 partway through: the cause named, the manual steps still offered.
        (
            {"admin": False},
            ["403", "gh auth login", "squash_merge_commit_title=PR_TITLE"],
        ),
    ],
    ids=["gh-absent", "gh-unauthenticated", "no-github-remote", "token-without-admin"],
)
def test_every_github_prerequisite_failure_is_a_refusal_never_a_traceback(
    wired: Callable[..., Run],
    tmp_path: Path,
    flaw: dict[str, bool],
    expected: list[str],
) -> None:
    """S4 and its neighbours: each refusal names its cause and offers a way on.

    `unexpected error` is what the CLI's boundary prints when an exception
    escapes a handler, so its absence is the assertion that tells a refusal from
    a crash. Nothing on any of these paths may change the repo.
    """
    repo = make_bare_repo(tmp_path, {"pyproject.toml": "[project]\nname='app'\n"})
    github = FakeGitHub(**flaw)
    before = github.snapshot()

    result = wired("init", "--wire", str(repo), script=answers(), github=github)

    assert result.code == EXIT_USER
    assert "unexpected error" not in result.stderr
    assert "Traceback" not in result.stderr
    for phrase in expected:
        assert phrase in result.stderr, phrase
    # Not `mutations() == []`: the 403 case *does* attempt its write and is
    # refused, which is the behaviour under test. The repo must never differ.
    assert github.snapshot() == before

    # The two prerequisite failures are caught before anything is read or
    # written, so nothing can be left half-wired behind them.
    if "gh_installed" in flaw or "logged_in" in flaw:
        assert github.mutations() == []
        assert [c for c in github.calls if c[:2] == ("repo", "view")] == []


# Plan trap 2 — the queue rule is read for GitHub's default branch


def test_a_landing_branch_that_is_not_the_default_is_wired_and_the_divergence_reported(
    wired: Callable[..., Run], tmp_path: Path
) -> None:
    """The declared landing branch is wired; the divergence is said aloud.

    `evaluate_repo` reads the queue for the *default* branch, not the manifest's
    `landing_branch`. The last assertion proves the report is true rather than a
    recited warning.
    """
    repo = make_bare_repo(tmp_path, {"pyproject.toml": "[project]\nname='app'\n"})
    github = FakeGitHub(default_branch="main")

    result = wired(
        "init", "--wire", str(repo),
        script=answers(landing_branch="release"),
        github=github,
    )

    assert result.code == EXIT_OK, result.stderr

    # Wired the declared landing branch, and only it.
    assert github._rules_for_branch("release"), "the landing branch was not wired"
    assert github._rules_for_branch("main") == []

    # Said so, with the remedy — read out of the wiring report alone.
    report = wiring_report(result.stdout)
    assert "default branch" in report
    assert "release" in report
    assert "gh repo edit --default-branch release" in report

    # And the warning is true: the factory's gate reads `main` and still fails.
    profile = onboarding_profile(repo, github)
    assert not profile.passed
    assert "gated_landing" in [check for check, _ in failed(profile)]


# The CI half: "when the repo has no CI producing those checks"


def test_existing_ci_already_producing_the_checks_is_left_alone(
    wired: Callable[..., Run], tmp_path: Path
) -> None:
    """The spec scaffolds a workflow only when the repo has no CI producing the checks."""
    existing = (
        "name: ci\non:\n  pull_request:\n  merge_group:\njobs:\n"
        "  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: make test\n"
        "  lint:\n    name: lint\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: make lint\n"
    )
    repo = make_bare_repo(
        tmp_path,
        {"pyproject.toml": "[project]\nname='app'\n", ".github/workflows/ci.yml": existing},
    )
    github = FakeGitHub()

    result = wired("init", "--wire", str(repo), script=answers(), github=github)

    assert result.code == EXIT_OK, result.stderr
    assert (repo / wiring.WORKFLOW_PATH).exists() is False
    assert (repo / ".github/workflows/ci.yml").read_text(encoding="utf-8") == existing
    assert "ci.yml" in result.stdout

    # The gate<->check contract still holds: the queue requires the gate names,
    # and the repo's own CI already produces jobs by those names.
    assert onboarding_profile(repo, github).passed


def test_a_conflicting_managed_workflow_is_reported_never_clobbered(
    wired: Callable[..., Run], tmp_path: Path
) -> None:
    """An operator's edits to the managed file are theirs; wiring reports, never overwrites."""
    hand_edited = "name: mine\non:\n  merge_group:\njobs:\n  other:\n    runs-on: ubuntu-latest\n"
    repo = make_bare_repo(
        tmp_path,
        {
            "pyproject.toml": "[project]\nname='app'\n",
            str(wiring.WORKFLOW_PATH): hand_edited,
        },
    )
    github = FakeGitHub()

    result = wired("init", "--wire", str(repo), script=answers(), github=github)

    assert result.code == EXIT_OK, result.stderr
    assert (repo / wiring.WORKFLOW_PATH).read_text(encoding="utf-8") == hand_edited
    assert wiring.ATTENTION in result.stdout
    assert str(wiring.WORKFLOW_PATH) in result.stdout


# Without `--wire`, init is exactly what US1 landed


def test_plain_init_wires_nothing_and_only_reads_for_the_check(
    wired: Callable[..., Run], tmp_path: Path
) -> None:
    """The wiring half is opt-in: plain `ergane init` changes nothing on GitHub.

    This asserted `github.calls == []` until US4 landed. It cannot any more, and
    should not: FR-010 makes the check the automatic last act of a full init, and
    the check *reads* GitHub through `onboard_target_repo`. What `--wire` owns is
    writing, so writing is what this pins — the repo model byte-identical, no
    mutating call, and the only calls made are the check's three reads, named
    exactly. A write added to the no-wire path fails here.
    """
    repo = make_bare_repo(tmp_path, {"pyproject.toml": "[project]\nname='app'\n"})
    github = FakeGitHub()
    before = github.snapshot()

    result = wired("init", str(repo), script=answers(), github=github)

    assert result.code == EXIT_OK, result.stderr
    assert github.snapshot() == before
    assert github.mutations() == []
    assert github.calls == [
        ("repo", "view", "--json", "nameWithOwner,visibility,isInOrganization,defaultBranchRef"),
        ("api", "repos/acme/app"),
        ("api", "repos/acme/app/rules/branches/main"),
    ]


# 059/US1 — the auto-merge flag the merge driver requires


def _find_patch_call(github: FakeGitHub) -> tuple[str, ...] | None:
    for call in github.calls:
        if "-X" in call and "PATCH" in call and f"repos/{github.owner_repo}" in call:
            return call
    return None


def test_wiring_enables_allow_auto_merge_against_the_fake_client() -> None:
    """US1-S1: `wire_repo` issues the PATCH that turns on `allow_auto_merge`, and
    the recorded call list contains the right slug and the right flag value.
    """
    github = FakeGitHub(owner_repo="acme/app")
    client = GhClient(repo="/srv/target", runner=github)

    steps = wiring.wire_repo(client, landing_branch="main", gates=["test"])

    auto_merge_call = _find_auto_merge_patch(github)
    assert auto_merge_call is not None
    assert f"repos/{github.owner_repo}" in auto_merge_call
    assert "allow_auto_merge=true" in auto_merge_call

    assert any(step.name == "auto-merge" for step in steps)


def _find_auto_merge_patch(github: FakeGitHub) -> tuple[str, ...] | None:
    for call in github.calls:
        if "-X" in call and "PATCH" in call and "allow_auto_merge=true" in call:
            return call
    return None


def test_manual_steps_renders_the_auto_merge_command() -> None:
    """US1-S2: the by-hand list names enabling auto-merge, with the placeholder as
    well as a resolved slug.
    """
    resolved = wiring.manual_steps(landing_branch="main", gates=["test"], owner_repo="acme/app")
    placeholder = wiring.manual_steps(landing_branch="main", gates=["test"])

    def has_auto_merge(steps: list[str]) -> bool:
        return any("allow_auto_merge=true" in step for step in steps)

    assert has_auto_merge(resolved)
    assert has_auto_merge(placeholder)
    assert any("repos/acme/app" in step and "allow_auto_merge=true" in step for step in resolved)
    assert any("repos/<owner>/<repo>" in step and "allow_auto_merge=true" in step for step in placeholder)


def test_auto_merge_step_appears_as_a_wiring_step_with_name_and_status() -> None:
    """US1-S3: the operation is reported as a named `WiringStep` like its siblings."""
    github = FakeGitHub(owner_repo="acme/app")
    client = GhClient(repo="/srv/target", runner=github)

    steps = wiring.wire_repo(client, landing_branch="main", gates=["test"])

    names = [step.name for step in steps]
    assert "auto-merge" in names
    auto_merge = next(step for step in steps if step.name == "auto-merge")
    assert auto_merge.status in {wiring.APPLIED, wiring.ALREADY_SATISFIED}


def test_allow_auto_merge_failure_is_reported_as_a_wiring_failure() -> None:
    """US1-S4: when the PATCH is refused, `wire_repo` raises a refusal naming the
    setting rather than reporting success with a missing step.
    """
    github = FakeGitHub(owner_repo="acme/app", refuse_allow_auto_merge_patch=True)
    client = GhClient(repo="/srv/target", runner=github)

    with pytest.raises(wiring.WiringRefused) as raised:
        wiring.wire_repo(client, landing_branch="main", gates=["test"])

    assert "allow_auto_merge" in str(raised.value)
    assert "403" in str(raised.value)


def test_auto_merge_step_is_idempotent_and_403_is_distinct_from_off() -> None:
    """Edge: a second run when the flag is already true reports `already satisfied`
    rather than a failure; a 403 refusal is reported as a permission condition."""
    github = FakeGitHub(owner_repo="acme/app", allow_auto_merge=True)
    client = GhClient(repo="/srv/target", runner=github)

    steps = wiring.wire_repo(client, landing_branch="main", gates=["test"])
    auto_merge = next(step for step in steps if step.name == "auto-merge")
    assert auto_merge.status == wiring.ALREADY_SATISFIED
    auto_merge_mutations = [m for m in github.mutations() if "allow_auto_merge=true" in m]
    assert auto_merge_mutations == []

    refused = FakeGitHub(owner_repo="acme/app", refuse_allow_auto_merge_patch=True)
    refused_client = GhClient(repo="/srv/target", runner=refused)
    with pytest.raises(wiring.WiringRefused) as raised:
        wiring.wire_repo(refused_client, landing_branch="main", gates=["test"])
    assert "403" in str(raised.value)
    assert "admin" in str(raised.value).lower()
