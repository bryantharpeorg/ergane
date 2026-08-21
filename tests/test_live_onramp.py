"""The on-ramp, end to end, against a scratch repository (061 US4, FR-011).

The check whose absence let 061's other three stories ship: `ergane install
--verify` reported `11/11`, `ergane init --check` reported `6/6`, and the machine
those checks pronounced ready could not dispatch and could not land.

This measures the composition by being it — a scratch organization-owned
repository created, `ergane install --from-file`, `ergane init --wire
--non-interactive`, `ergane repo onboard`, one trivial epic dispatched at a real
gateway with a real agent, and a pull request read back from GitHub and asserted
`MERGED`. The outcome, never an exit status (US4-S3, trap 7).

The `live_onramp` marker selects this and does not guard it, because nothing
passes `-m` in CI or in the gate: `missing_prerequisites` runs on collection and
skips naming what is absent (US4-S4). Stage naming (US4-S2), path containment
(US4-S5) and cleanup on both paths (FR-012) belong to the orchestration below
and are proven in `tests/test_onramp_exercise.py`, since a live run that passes
proves nothing about how it would have failed. `_git` supplies the git identity
itself, because a runner has none and this epic has died twice on a fixture that
assumed one (trap 14). No Temporal schedule is created — init tries, D-045's
guards refuse under `PYTEST_CURRENT_TEST`, and that refusal is asserted rather
than tolerated — and the worker runs on a run-scoped queue, since two on the
production queue would split this epic's activities out of sight.

Cost, prerequisites and the SC-005 drill: `docs/onramp-exercise.md`. Trap 15:
this sandbox has no live prerequisites, so the module is committed under its own
skip and the in-diff evidence is that skip plus the simulated drives, in this
spec's `evidence/us4-onramp-exercise.md`.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import io
import os
import shutil
import subprocess
import time
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

import pytest

from factory import worker as factory_worker
from factory.cli.main import main as ergane_main
from factory.mergequeue.gh import GhClient
from factory.mergequeue.models import LandingConfig, LandingState
from factory.verify.models import VerificationConfig
from factory.workgraph import cli as workgraph_cli
from factory.workgraph.models import EpicState
from factory.workgraph.workflow import EpicInput, EpicWorkflow
from tests.target_repo import git_env

pytestmark = pytest.mark.live_onramp


# --- the orchestration, driven offline by tests/test_onramp_exercise.py ------

#: The forge's own word for a landing: "did it merge?" is GitHub's answer.
MERGED = "MERGED"

#: Organization-owned, because 059's eligibility rule requires it.
ORG_ENV = "ERGANE_ONRAMP_ORG"

PROXY_URL_ENV = "LITELLM_PROXY_URL"
MASTER_KEY_ENV = "LITELLM_MASTER_KEY"
TEMPORAL_ADDRESS_ENV = "TEMPORAL_ADDRESS"
TEMPORAL_NAMESPACE_ENV = "TEMPORAL_NAMESPACE"
DEFAULT_TEMPORAL_ADDRESS = "127.0.0.1:7233"
DEFAULT_TEMPORAL_NAMESPACE = "ergane"

#: The agent this factory dispatches (D-018), and the forge a landing uses.
AGENT_EXECUTABLE = "claude"
FORGE_EXECUTABLE = "gh"

#: The alias the shipped registry carries: dispatching with it asks for a model
#: nobody configured.
PLACEHOLDER_ALIAS = "CHANGEME"

#: The name every workspace root carries. Cleanup checks it, and that the tree
#: is under the temporary directory, before removing anything: either alone is a
#: convention, not a boundary for an act that deletes (`factory/cli/repo.py:465`,
#: written after a test emptied the live runtime root).
ROOT_DIR_NAME = "onramp"


class Stage(str, Enum):
    """One step, named so a failure can be attributed to it; the order is the
    operator's, and `CLEANUP` is outside it."""

    PROVISION = "provision"
    INSTALL = "install"
    INIT = "init"
    ONBOARD = "onboard"
    DISPATCH = "dispatch"
    LAND = "land"
    CLEANUP = "cleanup"

    def __str__(self) -> str:  # pragma: no cover - display only
        return self.value


class StageFailed(Exception):
    """A stage failed, and this says which one (US4-S2): `stage` is what an
    operator greps for, and the message repeats it for the pytest tail."""

    def __init__(self, stage: Stage, detail: str) -> None:
        self.stage = stage
        self.detail = detail
        super().__init__(f"on-ramp exercise failed at stage '{stage.value}': {detail}")


@dataclasses.dataclass(frozen=True)
class PullRequest:
    """The forge's account, off `gh pr view --json state,mergedAt,number,url`;
    both fields, because a state without an instant is a label, not an event.
    """

    number: int
    state: str
    merged_at: str | None
    url: str


@dataclasses.dataclass(frozen=True)
class Prerequisite:
    """One live thing the exercise needs; `detail` names the remedy."""

    name: str
    detail: str


# --- where the exercise is allowed to write ---


@dataclasses.dataclass(frozen=True)
class Workspace:
    """Every path this run may touch, derived from one root it was handed."""

    root: Path
    epic_id: str
    repo_name: str
    home: Path
    config_home: Path
    state_home: Path
    registry_path: Path
    config_path: Path
    personas_path: Path
    runtime_root: Path
    ledger_path: Path
    verification_db: Path
    answer_file: Path
    clone: Path
    specs_root: Path
    spec_dir: Path

    @classmethod
    def beneath(
        cls, root: Path, *, epic_id: str, repo_name: str | None = None
    ) -> "Workspace":
        """Lay a whole Ergane host out beneath `root`, consulting nothing else;
        `epic_id` is supplied rather than minted so the same root twice is the
        same workspace."""
        root = Path(root)
        config_home = root / "config"
        state_home = root / "state"
        runtime_root = root / "runtime"
        clone = root / "target-repo"
        specs_root = clone / "specs"
        return cls(
            root=root,
            epic_id=epic_id,
            repo_name=repo_name if repo_name is not None else epic_id,
            home=root / "home",
            config_home=config_home,
            state_home=state_home,
            registry_path=state_home / "ergane" / "repos.json",
            config_path=config_home / "ergane" / "config.toml",
            personas_path=config_home / "ergane" / "personas.yaml",
            runtime_root=runtime_root,
            ledger_path=runtime_root / "ledger.db",
            verification_db=runtime_root / "verification.db",
            answer_file=root / "install-answers.toml",
            clone=clone,
            specs_root=specs_root,
            spec_dir=specs_root / epic_id,
        )

    def written_paths(self) -> tuple[Path, ...]:
        """Every path this may be written to (US4-S5), derived from the fields
        so one added later is covered without anyone listing it here."""
        return tuple(
            value
            for field in dataclasses.fields(self)
            if field.name != "root"
            and isinstance(value := getattr(self, field.name), Path)
        )

    def environment(self) -> dict[str, str]:
        """The overrides that keep the real CLI verbs inside this root."""
        environment = {
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.config_home),
            "XDG_STATE_HOME": str(self.state_home),
        }
        for suffix, path in {
            "CONFIG_PATH": self.config_path,
            "PERSONAS_PATH": self.personas_path,
            "STATE_HOME": self.state_home,
            "ROOT": self.runtime_root,
            "LEDGER_PATH": self.ledger_path,
            "VERIFICATION_DB_PATH": self.verification_db,
        }.items():
            for prefix in ("ERGANE", "FACTORY"):
                environment[f"{prefix}_{suffix}"] = str(path)
        return environment


# --- the driver seam ---


#: What `run_exercise` drives: one method per stage, so a simulated failure is
#: which method raises rather than which subprocess is mocked. `dispatch`
#: returns the PR number its epic opened, `land(workspace, number)` reads it
#: back, and `cleanup` runs however the drive ended.
Driver = Any


def run_exercise(driver: Driver, workspace: Workspace) -> PullRequest:
    """Drive the whole on-ramp and return the pull request that landed.

    Raises `StageFailed` naming the stage that stopped it, and cleans up however
    this ends — including when the landed assertion is what failed, the failure
    the exercise exists to produce and so the one whose cleanup is forgotten.
    """
    failure: BaseException | None = None
    try:
        _drive(Stage.PROVISION, driver.provision, workspace)
        _drive(Stage.INSTALL, driver.install, workspace)
        _drive(Stage.INIT, driver.init, workspace)
        _drive(Stage.ONBOARD, driver.onboard, workspace)
        pr_number = _drive(Stage.DISPATCH, driver.dispatch, workspace)
        pull_request = _drive(
            Stage.LAND, lambda ws: driver.land(ws, pr_number), workspace
        )
        # The one assertion the run is for, inside the try so its failure is
        # cleaned up after like any other (FR-012).
        assert_pull_request_landed(pull_request)
        return pull_request
    except BaseException as error:
        failure = error
        raise
    finally:
        try:
            driver.cleanup(workspace)
        except Exception as cleanup_error:  # noqa: BLE001 - reported, never swallowed
            if failure is None:
                raise StageFailed(Stage.CLEANUP, str(cleanup_error)) from cleanup_error
            # A cleanup failure must not replace the failure that caused it: the
            # news is that dispatch produced no pull request, not that the
            # scratch repository outlived the attempt. Both are reported.
            failure.add_note(
                f"cleanup also failed ({Stage.CLEANUP.value}): {cleanup_error} — "
                "the scratch repository or the temporary root may have survived"
            )


def _drive(stage: Stage, step: Callable[[Workspace], Any], workspace: Workspace) -> Any:
    """Run one stage, converting whatever it raises into a named failure."""
    try:
        return step(workspace)
    except StageFailed:
        raise
    except Exception as error:  # noqa: BLE001 - every stage failure reads alike
        raise StageFailed(stage, f"{type(error).__name__}: {error}") from error


def assert_pull_request_landed(pull_request: PullRequest | None) -> None:
    """The exercise's final assertion: the outcome, never an exit status.

    US4-S3, trap 7. Both of GitHub's fields are read: `state` is a label the
    forge reports on a record whose merge has not happened, `merged_at` the
    event.
    """
    if pull_request is None:
        raise StageFailed(
            Stage.LAND,
            "the dispatch produced no pull request to read back: the epic "
            "finished without opening one, so there is no outcome",
        )
    if pull_request.state != MERGED:
        raise StageFailed(
            Stage.LAND,
            f"pull request #{pull_request.number} is {pull_request.state}, not "
            f"{MERGED} ({pull_request.url}); every command may have exited zero "
            "and the work still did not land",
        )
    if not pull_request.merged_at:
        raise StageFailed(
            Stage.LAND,
            f"pull request #{pull_request.number} reports {MERGED} with no "
            "merged_at instant; a state without an event is not a landing",
        )


# --- the live-tier guard (US4-S4) ---


def probe_temporal(address: str, namespace: str) -> str | None:
    """Return `None` when a Temporal server answers, else why it did not."""

    async def connect() -> None:
        from temporalio.client import Client

        await Client.connect(address, namespace=namespace)

    try:
        asyncio.run(connect())
    except Exception as error:  # noqa: BLE001 - see the docstring
        return f"{type(error).__name__} at {address} (namespace {namespace!r}): {error}"
    return None


def probe_gh_auth() -> str | None:
    """Return `None` when `gh` is authenticated for github.com, else why not."""
    try:
        completed = subprocess.run(
            [FORGE_EXECUTABLE, "auth", "status", "--hostname", "github.com"],
            capture_output=True,
            text=True,
        )
    except OSError as error:
        return f"could not run `{FORGE_EXECUTABLE} auth status`: {error}"
    if completed.returncode != 0:
        return (completed.stderr or completed.stdout).strip() or "not authenticated"
    return None


def probe_personas() -> str | None:
    """Return `None` when the host's registry names real aliases: one still
    carrying `CHANGEME` fails four stages later wearing a dispatch error."""
    try:
        from factory.config import load_personas, resolve_default_registry_path

        path = resolve_default_registry_path()
        registry = load_personas(path)
    except Exception as error:  # noqa: BLE001 - an unreadable registry is a no
        return f"cannot read the persona registry: {error}"

    placeholders = sorted(
        name
        for name, persona in registry.items()
        if not persona.model or PLACEHOLDER_ALIAS in persona.model
    )
    if placeholders:
        return f"{path} still names the placeholder alias for: {', '.join(placeholders)}"
    return None


def missing_prerequisites(
    environ: Mapping[str, str],
    *,
    probe_temporal: Callable[[str, str], str | None] = probe_temporal,
    probe_gh_auth: Callable[[], str | None] = probe_gh_auth,
    probe_personas: Callable[[], str | None] = probe_personas,
) -> tuple[Prerequisite, ...]:
    """Everything this host lacks, named, in the order it would be needed."""
    path = environ.get("PATH")
    address = environ.get(TEMPORAL_ADDRESS_ENV) or DEFAULT_TEMPORAL_ADDRESS
    namespace = environ.get(TEMPORAL_NAMESPACE_ENV) or DEFAULT_TEMPORAL_NAMESPACE
    auth, personas = probe_gh_auth(), probe_personas()
    temporal = probe_temporal(address, namespace)

    checks: tuple[tuple[str, object, str], ...] = (
        ("scratch organization", not environ.get(ORG_ENV),
         f"set {ORG_ENV} to an org this run may create and delete a repository "
         "in (059 requires an org-owned target)"),
        (FORGE_EXECUTABLE, shutil.which(FORGE_EXECUTABLE, path=path) is None,
         f"put the `{FORGE_EXECUTABLE}` CLI on PATH; the landing goes via it"),
        ("gh authentication", auth,
         f"run `{FORGE_EXECUTABLE} auth login` for that org: {auth}"),
        (AGENT_EXECUTABLE, shutil.which(AGENT_EXECUTABLE, path=path) is None,
         f"put the `{AGENT_EXECUTABLE}` CLI on PATH; the epic runs it (D-018)"),
        ("gateway",
         not (environ.get(PROXY_URL_ENV) and environ.get(MASTER_KEY_ENV)),
         f"export {PROXY_URL_ENV} and {MASTER_KEY_ENV} for a LiteLLM proxy with "
         "key management enabled: the epic mints a key on it"),
        ("personas", personas,
         f"point the registry's aliases at models this gateway serves: {personas}"),
        ("temporal", temporal,
         f"start a Temporal the worker can reach at {address} in "
         f"{namespace!r}: {temporal}"),
    )
    return tuple(Prerequisite(name, detail) for name, absent, detail in checks if absent)


def skip_message(missing: Sequence[Prerequisite]) -> str:
    """The skip an operator reads: the things that are absent, named rather
    than counted, because "3 prerequisites missing" sends them back to the
    source."""
    lines = ["the on-ramp exercise needs live prerequisites this host does not have:"]
    lines += [f"  - {item.name}: {item.detail}" for item in missing]
    return "\n".join(lines)


#: The answers `ergane install --from-file` is driven with.
#: `escalation.adapter = "none"` deliberately: the run is capped at one attempt
#: with no debugger cycle, so nothing an operator could answer is pending, and a
#: live smoke that pages a human is a filed defect here.
_ANSWER_FILE_TEMPLATE = """\
version = 1

[llm]
mode = "gateway"
base_url = "{proxy_url}"
master_key_env = "{master_key_env}"

[memory]
backend = "none"

[temporal]
mode = "external"
address = "{address}"
namespace = "{namespace}"

[escalation]
adapter = "none"
"""


# --- the scratch target repository ---

#: The scratch epic's story and node, the branch `gh repo create` leaves a
#: repository on, and the gate its CI produces.
STORY_KEY, NODE_ID, LANDING_BRANCH, GATE_NAME = "US1", "us1", "main", "test"

ATTEMPT_TIMEOUT_ENV = "ERGANE_ONRAMP_TIMEOUT_S"
DEFAULT_ATTEMPT_TIMEOUT_S = 1200

#: Room on top of the attempt for provisioning, wiring, CI and the queue.
RUN_GRACE_S = 2400
POLL_INTERVAL_S = 20
STALL_AFTER_S = 1800

#: One attempt, no debugger cycle: a broken composition should report in minutes
#: rather than spend three attempts discovering the same thing.
EXERCISE_LADDER = VerificationConfig(
    max_attempts=1, debugger_cycles=0, gate_timeout_s=600, escalation_timeout_s=60
)

#
# A minimal Python project, because `ergane init` reads the tree to decide the
# gate: a `pyproject.toml` makes it offer `uv run pytest -q`, one that can fail.
# Without that signal it gets 061/US3's placeholder — always exits 1 — and the
# exercise would be measuring an unconfigured repository.

WORK_FILE = "greet.py"
GREETED = "Ergane"
GREETING = f"Hello, {GREETED}!"

PYPROJECT_SOURCE = """\
[project]
name = "ergane-onramp-scratch"
version = "0.0.0"
requires-python = ">=3.11"
"""

CHECK_SOURCE = f'''"""The gate this epic's node has to turn green (see ergane.yaml)."""


def test_greets_by_name() -> None:
    # Imported inside the test so a missing module fails this check rather than
    # breaking collection.
    from {WORK_FILE.removesuffix(".py")} import greet

    assert greet({GREETED!r}) == {GREETING!r}
'''

#: The committed CI, because init's scaffold runs the gate on a bare checkout
#: while `uv run pytest -q` needs `uv`. `merge_group` is not optional: the queue
#: runs its checks against the merge group, and a workflow firing only on
#: `pull_request` leaves the landing waiting forever.
GATES_WORKFLOW_SOURCE = f"""\
name: gates

on:
  pull_request:
  merge_group:

jobs:
  {GATE_NAME}:
    name: "{GATE_NAME}"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv run --with pytest pytest -q
"""

#: One story, one requirement, one acceptance scenario — the smallest spec that
#: derives, verified in-sandbox (the derived graph is in the evidence file).
SPEC_SOURCE = f"""# Feature Specification: Greeting

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Greet by name (Priority: P1)

As this repository's caller, I can ask for a greeting by name and get one back.

**Acceptance Scenarios**:

1. **Given** this repository, **When** `greet({GREETED!r})` is called, **Then** it returns `{GREETING}`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The repository MUST provide `{WORK_FILE}` at its root, exposing
  `greet(name)` returning `Hello, <name>!`, so `test_greet.py` passes unchanged.

## Work Graph

```yaml
{STORY_KEY}:
  depends_on: []
  implements: [FR-001]
  timeout: <TIMEOUT>
```
"""

PLAN_SOURCE = f"""# Implementation Plan: Greeting

One module at the repository root, standard library only, no file beyond
`{WORK_FILE}`, no dependency. `test_greet.py` is the acceptance check and is not
to be edited.
"""

TASKS_SOURCE = f"""# Tasks: Greeting

## Phase 3: User Story 1 - Greet by name (Priority: P1)

- [ ] T001 Create `{WORK_FILE}` at the root with a `greet(name)` function
  returning `Hello, ` followed by the name and `!`.
- [ ] T002 Run the gate `ergane.yaml` declares and leave it green. Do not edit
  `test_greet.py`.
"""


# --- the live driver ---


@dataclasses.dataclass(frozen=True)
class LiveOnRamp:
    """One complete run, and everything the assertions below read it through."""

    workspace: Workspace
    pull_request: PullRequest
    transcripts: dict[Stage, str]
    epic_status: Any


class LiveDriver:
    """Each stage, driven through the verbs an operator runs — `ergane` in
    process through the entry point the console script dispatches, with the
    workspace's environment applied."""

    def __init__(self, org: str, host_registry: Path) -> None:
        self.org = org
        #: The operator's registry, resolved before the workspace's environment
        #: hid it. Read and copied; never written.
        self.host_registry = host_registry
        #: What each stage printed; a live run is expensive to reproduce.
        self.transcripts: dict[Stage, str] = {}
        self.epic_status: Any = None
        #: Set once `gh repo create` has answered, so cleanup deletes only a
        #: repository this run actually made.
        self.created_repo: str | None = None

    def _run_cli(self, stage: Stage, argv: list[str]) -> str:
        """One `ergane` invocation; returns its output, raises on a refusal."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = ergane_main(argv)
        text = out.getvalue() + err.getvalue()
        self.transcripts[stage] = self.transcripts.get(stage, "") + text
        if status != 0:
            raise StageFailed(stage, f"`ergane {' '.join(argv)}` exited {status}:\n{text}")
        return text

    def _gh(self, *args: str) -> str:
        """One `gh` invocation, raising with its stderr when it refuses."""
        return _checked(["gh", *args], None)

    def _git(self, repo: Path, *args: str) -> str:
        """One `git` invocation in `repo`, with an explicit identity."""
        environment = git_env()
        for name in ("GH_TOKEN", "GITHUB_TOKEN", "SSH_AUTH_SOCK"):
            if value := os.environ.get(name):
                environment[name] = value
        return _checked(["git", "-C", str(repo), *args], environment)

    # -- the stages --

    def provision(self, workspace: Workspace) -> None:
        """Create the scratch repository and seed it — organization-owned,
        because 059's rule requires it: a user-owned repository cannot carry
        the merge-queue ruleset the landing depends on, so an exercise quietly
        using a personal one would pass while proving nothing."""
        slug = f"{self.org}/{workspace.repo_name}"
        self._gh("repo", "create", slug, "--public", "--add-readme")
        # Recorded only once the forge has answered: cleanup deletes what this
        # run made and nothing else.
        self.created_repo = slug
        self._gh("repo", "clone", slug, str(workspace.clone), "--", "--quiet")

        for name, source in (
            ("pyproject.toml", PYPROJECT_SOURCE),
            ("test_greet.py", CHECK_SOURCE),
            # Generated noise stays out of the diff the judge scores.
            (".gitignore", "__pycache__/\n*.pyc\n.pytest_cache/\n"),
            (".github/workflows/gates.yml", GATES_WORKFLOW_SOURCE),
        ):
            path = workspace.clone / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding="utf-8")

        self._git(workspace.clone, "add", "-A")
        self._git(workspace.clone, "commit", "--quiet", "-m", "seed the scratch target")
        self._git(workspace.clone, "push", "--quiet", "origin", LANDING_BRANCH)

        _require(
            (workspace.clone / "test_greet.py").is_file(),
            "the seeded acceptance check is not in the clone",
        )

    def install(self, workspace: Workspace) -> None:
        """`ergane install --from-file`, and its own verification must be
        clean."""
        # The operator's registry goes in *before* install runs, never after:
        # install seeds the shipped example into an empty path and verifies what
        # it just seeded, and those aliases are `CHANGEME`, so a seeded install
        # fails its own `llm` check on a perfectly good gateway. Copied, never
        # written back.
        workspace.personas_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.host_registry, workspace.personas_path)

        workspace.answer_file.parent.mkdir(parents=True, exist_ok=True)
        workspace.answer_file.write_text(
            # The gateway and the Temporal the guard just proved, not a default.
            _ANSWER_FILE_TEMPLATE.format(
                proxy_url=os.environ[PROXY_URL_ENV],
                master_key_env=MASTER_KEY_ENV,
                address=os.environ.get(TEMPORAL_ADDRESS_ENV, DEFAULT_TEMPORAL_ADDRESS),
                namespace=os.environ.get(
                    TEMPORAL_NAMESPACE_ENV, DEFAULT_TEMPORAL_NAMESPACE
                ),
            ),
            encoding="utf-8",
        )

        text = self._run_cli(
            Stage.INSTALL, ["install", "--from-file", str(workspace.answer_file)]
        )

        from factory.config import resolve_default_registry_path

        _require(
            workspace.config_path.is_file(),
            f"install exited zero and wrote no {workspace.config_path}",
        )
        _require("[FAIL]" not in text, "install's own verification failed:\n" + text)
        _require(
            resolve_default_registry_path() == workspace.personas_path,
            f"the run resolved its registry to {resolve_default_registry_path()}, "
            f"not to {workspace.personas_path}",
        )

    def init(self, workspace: Workspace) -> None:
        """`ergane init --wire --non-interactive`, then commit and push it."""
        text = self._run_cli(
            Stage.INIT, ["init", "--wire", "--non-interactive", str(workspace.clone)]
        )

        manifest = workspace.clone / "ergane.yaml"
        _require(manifest.is_file(), f"init exited zero and wrote no {manifest}")

        # The repository's one classifier for "this gate cannot fail", imported
        # rather than restated: a second copy would drift and both suites would
        # stay green (trap 1).
        from factory.mergequeue.onboard import _is_noop_gate_command
        from factory.verify.factory_yaml import load_factory_config

        config = load_factory_config(manifest)
        noop = [g for g, c in config.gates.items() if _is_noop_gate_command(c)]
        _require(
            not noop,
            f"init declared a gate that cannot fail ({noop}); a factory whose only "
            "gate always exits zero lands whatever an agent writes",
        )
        _require(
            workspace.specs_root.is_dir(),
            f"init created no {workspace.specs_root}; the roadmap schedule would "
            "poll a directory that does not exist",
        )
        _require(
            "PYTEST_CURRENT_TEST" in text,
            "init did not report the schedule refusal:\n" + text,
        )

        self._git(workspace.clone, "add", "-A")
        self._git(workspace.clone, "commit", "--quiet", "-m", "join ergane")
        self._git(workspace.clone, "push", "--quiet", "origin", LANDING_BRANCH)

    def onboard(self, workspace: Workspace) -> None:
        """`ergane repo onboard` (FR-010), against the wired repository, so a
        queue `init --wire` failed to enable is reported here rather than
        discovered by a landing that never merges."""
        self._run_cli(Stage.ONBOARD, ["repo", "onboard", str(workspace.clone)])

    def dispatch(self, workspace: Workspace) -> int:
        """Write the scratch epic, derive its graph, run it, return its PR number."""
        raw = os.environ.get(ATTEMPT_TIMEOUT_ENV) or ""
        timeout_s = int(raw) if raw.isdigit() and raw != "0" else DEFAULT_ATTEMPT_TIMEOUT_S

        workspace.spec_dir.mkdir(parents=True, exist_ok=True)
        for name, source in (
            ("spec.md", SPEC_SOURCE.replace("<TIMEOUT>", str(timeout_s))),
            ("plan.md", PLAN_SOURCE),
            ("tasks.md", TASKS_SOURCE),
        ):
            (workspace.spec_dir / name).write_text(source, encoding="utf-8")

        self._run_cli(
            Stage.DISPATCH,
            [
                "spec",
                "derive",
                str(workspace.spec_dir),
                "--target-repo",
                str(workspace.clone),
                "--specs-root",
                str(workspace.specs_root),
            ],
        )

        self.epic_status = asyncio.run(_run_epic(workspace, timeout_s=timeout_s))
        node = self.epic_status.nodes.get(NODE_ID)
        _require(
            node is not None,
            f"the epic reported no node {NODE_ID}, only "
            f"{sorted(self.epic_status.nodes)}",
        )
        _require(
            node.pr_number is not None,
            f"node {NODE_ID} finished {node.state} with landing state "
            f"{node.landing_state} and opened no pull request",
        )
        return int(node.pr_number)

    def land(self, workspace: Workspace, pr_number: int) -> PullRequest:
        """Read the pull request back from GitHub — the run's only verdict."""
        snapshot = GhClient(repo=str(workspace.clone)).poll_pr(pr_number)
        return PullRequest(
            number=pr_number,
            state=snapshot.state,
            merged_at=snapshot.merged_at,
            url=f"https://github.com/{self.created_repo}/pull/{pr_number}",
        )

    def cleanup(self, workspace: Workspace) -> None:
        """Destroy the scratch repository and the temporary root, both paths."""
        errors: list[str] = []

        if self.created_repo is not None:
            try:
                self._gh("repo", "delete", self.created_repo, "--yes")
            except Exception as error:  # noqa: BLE001 - reported, not swallowed
                errors.append(f"scratch repository {self.created_repo}: {error}")
            else:
                self.created_repo = None

        root = workspace.root
        if root.exists():
            temporary = Path(os.environ.get("TMPDIR") or "/tmp").resolve()
            own = root.resolve().is_relative_to(temporary)
            if not (own and root.name == ROOT_DIR_NAME):
                errors.append(f"refusing to remove {root}: not this run's own root")
            else:
                shutil.rmtree(root, ignore_errors=True)

        if errors:
            raise RuntimeError("; ".join(errors))


def _require(condition: object, message: str) -> None:
    """Assert the artifact a stage promised, not the exit status it returned."""
    if not condition:
        raise RuntimeError(message)


def _checked(argv: list[str], env: dict[str, str] | None) -> str:
    """Run `argv`, returning stdout and raising with stderr when it refuses."""
    done = subprocess.run(argv, capture_output=True, text=True, env=env)
    if done.returncode != 0:
        raise RuntimeError(
            f"`{' '.join(argv[:3])}…` exited {done.returncode}: "
            f"{(done.stderr or done.stdout).strip()}"
        )
    return done.stdout


async def _run_epic(workspace: Workspace, *, timeout_s: int) -> Any:
    """Run the derived graph to completion on a worker scoped to this run."""
    from temporalio.client import Client
    from temporalio.worker import Worker

    from factory.controlplane.resolve import resolve_temporal_target

    target = resolve_temporal_target()
    client = await Client.connect(target.address, namespace=target.namespace)
    graph = workgraph_cli.load_workgraph(
        workspace.spec_dir / workgraph_cli.ARTIFACT_NAME
    )
    queue = f"onramp-{workspace.epic_id}"
    deadline = timeout_s + RUN_GRACE_S

    async with Worker(
        client,
        task_queue=queue,
        workflows=factory_worker.WORKFLOWS,
        activities=factory_worker.ACTIVITIES,
    ):
        handle = await client.start_workflow(
            EpicWorkflow.run,
            EpicInput(
                graph=graph,
                proxy_url=os.environ[PROXY_URL_ENV],
                config=EXERCISE_LADDER,
                poll_interval_s=POLL_INTERVAL_S,
                landing_config=LandingConfig(
                    merge_method="squash",
                    poll_interval_s=POLL_INTERVAL_S,
                    stall_after_s=STALL_AFTER_S,
                ),
            ),
            id=workgraph_cli.workflow_id(workspace.epic_id),
            task_queue=queue,
        )
        try:
            return await asyncio.wait_for(handle.result(), timeout=deadline)
        except (asyncio.TimeoutError, TimeoutError):
            # Leaving it running would go on spending against the operator's
            # gateway long after this terminal has closed.
            await handle.terminate("on-ramp exercise exceeded its own deadline")
            raise RuntimeError(
                f"the epic did not finish within {deadline}s and was terminated "
                f"(raise {ATTEMPT_TIMEOUT_ENV})"
            ) from None


# --- the run ---


@pytest.fixture(scope="module")
def live_onramp(tmp_path_factory: pytest.TempPathFactory) -> Iterator[LiveOnRamp]:
    """Drive the on-ramp once, or skip naming the prerequisite that is absent."""
    missing = missing_prerequisites(os.environ)
    if missing:
        pytest.skip(skip_message(missing))

    from factory.config import resolve_default_registry_path

    host_registry = resolve_default_registry_path()

    workspace = Workspace.beneath(
        tmp_path_factory.mktemp("live-onramp") / ROOT_DIR_NAME,
        epic_id=f"onramp-{int(time.time())}",
    )
    for path in (workspace.home, workspace.config_home, workspace.state_home):
        path.mkdir(parents=True, exist_ok=True)

    driver = LiveDriver(org=os.environ[ORG_ENV], host_registry=host_registry)

    with pytest.MonkeyPatch.context() as patch:
        for name, value in workspace.environment().items():
            patch.setenv(name, value)
        pull_request = run_exercise(driver, workspace)

    yield LiveOnRamp(
        workspace=workspace,
        pull_request=pull_request,
        transcripts=dict(driver.transcripts),
        epic_status=driver.epic_status,
    )


def test_the_on_ramp_landed_a_pull_request(live_onramp: LiveOnRamp) -> None:
    """FR-011, and the only verdict this exercise has (US4-S3): GitHub's own
    state and instant, plus the factory's own account of the same event, which
    a composition defect would make disagree."""
    pull_request = live_onramp.pull_request

    assert pull_request.state == "MERGED", pull_request
    assert pull_request.merged_at, pull_request

    status = live_onramp.epic_status
    assert status.epic_state == EpicState.COMPLETED
    node = status.nodes[NODE_ID]
    assert node.landing_state == LandingState.MERGED, node
    assert node.pr_number == pull_request.number

    # The composition, not a subset of it — and constitution V: the gateway's
    # master key never left the environment.
    secret = os.environ.get(MASTER_KEY_ENV, "")
    assert secret, "the prerequisite guard admitted a run with no master key"
    for stage in (Stage.INSTALL, Stage.INIT, Stage.ONBOARD, Stage.DISPATCH):
        assert live_onramp.transcripts.get(stage), f"stage {stage} printed nothing"
    for stage, text in live_onramp.transcripts.items():
        assert secret not in text, f"the master key is in the {stage} transcript"

    # FR-012 and US4-S5's live half: the scratch repository and the temporary
    # root are gone, and every path this run resolved was its own. The
    # filesystem half is `tests/test_onramp_exercise.py`'s poisoned drive.
    workspace = live_onramp.workspace
    for path in workspace.written_paths():
        assert path.is_relative_to(workspace.root)
    for value in workspace.environment().values():
        assert Path(value).is_relative_to(workspace.root)
    assert not workspace.root.exists()
