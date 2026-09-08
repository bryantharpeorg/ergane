"""110-US1: first boot leaves the demo project dispatchable (T001-T005).

Every test here drives seams: the supervisor runs with stub children and a stub
demo-driver starter, and the driver's prepare phase runs against scratch
directories with an injected CLI runner or an injected sandbox probe.  No real
Temporal server, worker, bridge, gateway or dispatch is started anywhere in this
file (plan T8).

Two tests do run the real thing where the real thing is free and offline: T002
drives `ergane install --from-file` through the CLI seam against a scratch
config path, and T003 runs `spec validate` and `spec derive` through the same
seam.  Both are local, deterministic and spend nothing.

## Evidence (T008)

The prepare phase T002 asserts on, run for real against scratch paths with the
same steps and the same seams (`python3 -m factory.supervision.demo_driver
--state-home … --repo … --answers-file container/ergane-install-answer.demo.toml`,
2026-08-26), transcript trimmed only where install's own findings repeat:

    ergane demo: first boot preparing the demonstration project
    ergane demo: step 1/5 ergane install --from-file container/ergane-install-answer.demo.toml
    applied default: temporal.tls_enabled = false
    wrote /tmp/demo-drive/config.toml
    wrote /tmp/demo-drive/home/.config/ergane/personas.yaml

    verifying the control plane...
    [FAIL] host: gh is present but unauthenticated ...
    [PASS] engine: no engine identity record ...; the version handshake activates only on evidence
    [FAIL] llm: ERGANE_LLM_MASTER_KEY is not set; no credential to complete a round trip
    [FAIL] temporal: Temporal at 127.0.0.1:7233 does not have namespace `ergane` ...
    [PASS] memory / [PASS] telemetry / [PASS] escalation
    ergane demo: control-plane verification reported findings (exit 1); the configuration was written, so preparation continues
    ergane demo: step 2/5 git init -b main /tmp/demo-drive/repo
    ergane demo: step 3/5 wrote /tmp/demo-drive/repo/ergane.yaml
    ergane demo: step 4/5 wrote /tmp/demo-drive/repo/specs/001-demo
    ergane demo: step 5/5 committed the demonstration project as Ergane Demo <demo@ergane.invalid>
    ergane demo: agent sandbox probe succeeded
    ergane demo: first boot complete; /tmp/demo-drive/state/demo/prepared
    EXIT=0

    $ git -C /tmp/demo-drive/repo log --format='%an <%ae> | %s'
    Ergane Demo <demo@ergane.invalid> | The demonstration project, prepared on first boot

The second run's line (T005(a)), verbatim and alone:

    ergane demo: first boot already happened (/tmp/demo-drive/state/demo/prepared); nothing to prepare
    EXIT=0

Full suite on this tree with this file ignored: 4994 passed, 57 skipped in 358.29s.
Full suite on this tree with this file:         5006 passed, 57 skipped in 356.15s.
The delta is this file's twelve tests and nothing else (`--collect-only`: 5051
without it, 5063 with it).
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
from pathlib import Path
from typing import Callable, Sequence

import pytest

from factory.supervision.container_supervisor import ChildController
from tests.test_container_supervisor import ChildStub


# -----------------------------------------------------------------------------
# fixtures and helpers
# -----------------------------------------------------------------------------


@pytest.fixture
def driver_mod():
    """Import the demo driver; tests fail cleanly until it exists."""
    from factory.supervision import demo_driver

    return demo_driver


@pytest.fixture
def supervisor_mod():
    from factory.supervision import container_supervisor

    return container_supervisor


@pytest.fixture
def config(tmp_path: Path) -> dict:
    """Supervisor configuration for stub runs (mirrors 088's own fixture).

    The token is here because these tests assert the three-child set, and the
    bridge has been conditional on its credential since 2026-08-26 — absent the
    key, the scripted `bridge` child is never requested and the started-order
    waits spin forever. tests/test_container_bridge_optional.py owns the
    token-absent path.
    """
    return {
        "temporal_address": "127.0.0.1",
        "temporal_port": 7233,
        "readiness_timeout_s": 0.5,
        "grace_period_s": 0.2,
        "state_home": str(tmp_path / "supervisor-state"),
        "db_filename": str(tmp_path / "temporal.sqlite"),
        "telegram_bot_token": "123:stub-token-for-the-three-child-contract",
    }


class DemoPaths:
    """The scratch paths one prepare-phase run is driven against."""

    def __init__(self, tmp_path: Path) -> None:
        self.home = tmp_path / "home"
        self.state = tmp_path / "state"
        self.repo = tmp_path / "repo"
        self.config = tmp_path / "config.toml"
        self.answers = (
            Path(__file__).resolve().parents[1]
            / "container"
            / "ergane-install-answer.demo.toml"
        )


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> DemoPaths:
    """Point config, state and git identity resolution at scratch directories.

    `HOME` and both git config paths are scratch and absent, so the process has
    **no** global git identity: a commit that carries one carries it because the
    driver supplied it (US1-S2, FR-003).
    """
    paths = DemoPaths(tmp_path)
    paths.home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(paths.home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(paths.home / ".config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(paths.home / ".local" / "state"))
    monkeypatch.setenv("ERGANE_CONFIG_PATH", str(paths.config))
    monkeypatch.setenv("ERGANE_STATE_HOME", str(paths.state))
    monkeypatch.delenv("FACTORY_CONFIG_PATH", raising=False)
    monkeypatch.delenv("FACTORY_STATE_HOME", raising=False)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "absent-gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(tmp_path / "absent-gitconfig-system"))
    for name in (
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
    ):
        monkeypatch.delenv(name, raising=False)
    return paths


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
    )


class ScriptedProbe:
    """A stand-in for the bwrap probe that records the argv it was handed."""

    def __init__(self, driver_mod, *, ok: bool, stderr: str = "") -> None:
        self._driver_mod = driver_mod
        self.ok = ok
        self.stderr = stderr
        self.calls: list[list[str]] = []

    def __call__(self, argv: Sequence[str]):
        self.calls.append(list(argv))
        return self._driver_mod.ProbeOutcome(ok=self.ok, stderr=self.stderr)


class FakeCli:
    """A stand-in for `_run_cli` that records argv and fakes install's writes."""

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.calls: list[list[str]] = []

    def __call__(self, argv: Sequence[str]) -> int:
        self.calls.append(list(argv))
        if list(argv[:1]) == ["install"]:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text("version = 1\n", encoding="utf-8")
        return 0


async def _wait_until(predicate: Callable[[], bool], timeout: float = 2.0) -> bool:
    """Poll `predicate` on the event loop until true or the timeout elapses."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return predicate()


async def _run_supervisor_with_demo(
    supervisor_mod,
    config: dict,
    *,
    demo: ChildStub | None,
) -> tuple[asyncio.Task, dict[str, ChildStub], list[str], list[str]]:
    """Start the supervisor with stub children and (optionally) a demo starter."""
    children = {name: ChildStub(name) for name in ("temporal", "worker", "bridge")}
    started: list[str] = []
    demo_starts: list[str] = []

    async def start_child(name: str, argv: list[str]) -> ChildController:
        started.append(name)
        return children[name]

    async def always_ready(address: str, timeout: float) -> bool:
        return True

    async def start_demo_driver() -> ChildController:
        demo_starts.append("demo")
        assert demo is not None
        return demo

    run_task = asyncio.create_task(
        supervisor_mod._run_supervisor(
            config,
            start_child=start_child,
            probe_address=always_ready,
            start_demo_driver=start_demo_driver,
        )
    )
    return run_task, children, started, demo_starts


async def _shutdown(run_task: asyncio.Task) -> int:
    os.kill(os.getpid(), signal.SIGTERM)
    return await asyncio.wait_for(run_task, timeout=2.0)


# -----------------------------------------------------------------------------
# T001 [US1-S1, FR-001] the driver is spawned beside the supervised set
# -----------------------------------------------------------------------------


async def test_demo_flag_spawns_driver_outside_the_supervised_maps(
    supervisor_mod, config: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ERGANE_DEMO=1` spawns the driver after worker and bridge, unsupervised.

    The driver is proven absent from the `controllers`/`tasks` maps two ways:
    the declarations those maps are built from name only the three children, and
    a driver exiting nonzero — which for a supervised child is a fault that stops
    the container — leaves all three running and the return value unchanged.
    """
    monkeypatch.setenv("ERGANE_DEMO", "1")
    demo = ChildStub("demo")

    run_task, children, started, demo_starts = await _run_supervisor_with_demo(
        supervisor_mod, config, demo=demo
    )
    assert await _wait_until(lambda: bool(demo_starts))

    # Spawned only after worker and bridge are up.
    assert started == ["temporal", "worker", "bridge"]

    # The maps the supervised set is built from name the three children only.
    assert set(supervisor_mod._CHILDREN) == {"temporal", "worker", "bridge"}
    assert supervisor_mod.DEMO_DRIVER_MODULE not in supervisor_mod._CHILDREN.values()
    argv_map = supervisor_mod._child_argv(
        temporal_address="127.0.0.1:7233", db_filename="/tmp/temporal.sqlite"
    )
    assert set(argv_map) == {"temporal", "worker", "bridge"}

    # A nonzero driver exit is not a fault: nothing is stopped, nothing returns.
    demo.finish(3)
    assert await _wait_until(lambda: demo._exit_event.is_set())
    await asyncio.sleep(0.05)
    assert not run_task.done()
    for child in children.values():
        assert not child.stopped
        assert not child.killed

    assert await _shutdown(run_task) == 0


async def test_without_the_demo_flag_nothing_extra_is_spawned(
    supervisor_mod, config: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without `ERGANE_DEMO`, the supervised set is exactly today's three."""
    monkeypatch.delenv("ERGANE_DEMO", raising=False)

    run_task, children, started, demo_starts = await _run_supervisor_with_demo(
        supervisor_mod, config, demo=None
    )
    for child in children.values():
        assert await _wait_until(lambda child=child: child._started_event.is_set())

    assert started == ["temporal", "worker", "bridge"]
    assert demo_starts == []
    assert await _shutdown(run_task) == 0


def test_demo_driver_argv_avoids_the_pkill_substring(supervisor_mod) -> None:
    """The spawned command line carries no `python -` (module docstring, :8-12)."""
    argv = supervisor_mod._demo_driver_argv()
    joined = " ".join(argv)
    assert "python -" not in joined, joined
    assert supervisor_mod.DEMO_DRIVER_MODULE in argv


async def test_the_real_spawn_is_a_plain_module_subprocess(
    supervisor_mod, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The driver is spawned as `<interpreter> -m <module>`, with no shell."""
    import sys

    seen: list[tuple] = []

    async def fake_exec(*cmd, **kwargs):
        seen.append((cmd, kwargs))

        class _Proc:
            pid = 4321
            returncode = None

        return _Proc()

    monkeypatch.setattr(supervisor_mod.asyncio, "create_subprocess_exec", fake_exec)
    controller = await supervisor_mod._start_real_demo_driver()

    assert seen and list(seen[0][0]) == [
        sys.executable,
        "-m",
        supervisor_mod.DEMO_DRIVER_MODULE,
    ]
    assert controller.name == "demo"


# -----------------------------------------------------------------------------
# T002 [US1-S2, FR-002, FR-003] the prepare phase, driven offline
# -----------------------------------------------------------------------------


def _passing_preflight() -> "Finding":
    """A preflight finding that lets the prepare phase continue."""
    from factory.mergequeue.models import Finding

    return Finding(check="llm", passed=True, detail="probe ok")


def _prepare_for_real(driver_mod, paths: DemoPaths, probe: ScriptedProbe) -> int:
    """Run the prepare phase with the real CLI seam and a scripted probe."""
    return driver_mod.run_prepare_phase(
        state_home=paths.state,
        repo_root=paths.repo,
        answers_path=paths.answers,
        probe=probe,
        preflight=_passing_preflight,
    )


def test_prepare_phase_writes_config_repo_spec_and_one_identified_commit(
    driver_mod, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    """Config, repo, manifest, spec trio and one commit under the demo identity."""
    from factory.cli import init as init_module
    from factory.cli.install import _demo_manifest_text

    paths = _isolate(monkeypatch, tmp_path)
    probe = ScriptedProbe(driver_mod, ok=True)

    # The environment genuinely has no global git identity.
    identity = subprocess.run(
        ["git", "config", "--global", "user.name"], capture_output=True, text=True
    )
    assert identity.returncode != 0 or not identity.stdout.strip()

    status = _prepare_for_real(driver_mod, paths, probe)
    transcript = capsys.readouterr().out

    assert status == 0, transcript
    assert paths.config.is_file()

    assert (paths.repo / ".git").is_dir()
    assert _git(paths.repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "main"

    manifest = paths.repo / init_module.MANIFEST_NAME
    assert manifest.read_text(encoding="utf-8") == _demo_manifest_text()

    spec_dir = paths.repo / "specs" / "001-demo"
    for name in ("spec.md", "plan.md", "tasks.md"):
        assert (spec_dir / name).is_file(), name

    assert _git(paths.repo, "rev-list", "--count", "HEAD").stdout.strip() == "1"
    author = _git(paths.repo, "log", "-1", "--format=%an <%ae>").stdout.strip()
    assert author == f"{driver_mod.DEMO_GIT_NAME} <{driver_mod.DEMO_GIT_EMAIL}>"

    # The spec trio is committed, not merely written.
    tracked = _git(paths.repo, "ls-files").stdout.split()
    assert "specs/001-demo/spec.md" in tracked
    assert init_module.MANIFEST_NAME in tracked

    assert probe.calls, "the sandbox probe never ran"
    assert (paths.state / "demo" / driver_mod.PREPARED_SENTINEL).is_file()


# -----------------------------------------------------------------------------
# T003 [US1-S3, FR-004] the prepared repository validates and derives
# -----------------------------------------------------------------------------


def test_prepared_repository_validates_and_derives(
    driver_mod, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`spec validate` and `spec derive` both return 0 and compile a workgraph.

    The validate stage reaches the library form through `_demo_validate` since
    133-US9 (FR-013); the assertion that the stage returns 0 stays what it was.
    """
    from factory.cli.install import _demo_validate, _run_cli, _spec_derive_argv

    paths = _isolate(monkeypatch, tmp_path)
    assert _prepare_for_real(driver_mod, paths, ScriptedProbe(driver_mod, ok=True)) == 0

    spec_dir = paths.repo / "specs" / "001-demo"
    assert _demo_validate(spec_dir, paths.repo) == 0
    assert _run_cli(_spec_derive_argv(spec_dir, paths.repo)) == 0

    artifact = spec_dir / "workgraph.json"
    assert artifact.is_file()

    graph = json.loads(artifact.read_text(encoding="utf-8"))
    assert graph["nodes"], graph


# -----------------------------------------------------------------------------
# T004 [US1-S4, FR-005] a refused sandbox stops the driver, not the container
# -----------------------------------------------------------------------------


def test_probe_refusal_prints_stderr_and_a_remedy_and_dispatches_nothing(
    driver_mod, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    """The probe's own stderr, one named remedy, no dispatch, nonzero exit."""
    paths = _isolate(monkeypatch, tmp_path)
    cli = FakeCli(paths.config)
    probe = ScriptedProbe(
        driver_mod, ok=False, stderr="bwrap: Can't mount proc on /newroot/proc"
    )

    status = driver_mod.run_prepare_phase(
        state_home=paths.state,
        repo_root=paths.repo,
        answers_path=paths.answers,
        run_cli=cli,
        probe=probe,
        preflight=_passing_preflight,
    )
    printed = capsys.readouterr().out

    assert status != 0
    assert "bwrap: Can't mount proc on /newroot/proc" in printed
    assert "systempaths=unconfined" in printed
    assert "apparmor_restrict_unprivileged_userns" not in printed

    # No dispatch step was taken: the CLI seam saw install and nothing else.
    verbs = [call[0] for call in cli.calls]
    assert verbs == ["install"], cli.calls
    assert not any("ship" in " ".join(call) for call in cli.calls)

    # No sentinel of either kind was written (FR-006).
    assert not (paths.state / "demo" / driver_mod.PREPARED_SENTINEL).exists()
    assert not (paths.state / "demo" / driver_mod.DISPATCH_SENTINEL).exists()


def test_probe_argv_carries_unshare_pid_and_proc(driver_mod) -> None:
    """The probe mirrors the adapter's shape; without these it lies (plan T5)."""
    argv = driver_mod.sandbox_probe_argv()

    assert "--unshare-pid" in argv
    assert "--die-with-parent" in argv
    assert "--proc" in argv
    assert argv[argv.index("--proc") + 1] == "/proc"
    assert "--dev" in argv
    assert argv[argv.index("--dev") + 1] == "/dev"
    assert "--ro-bind" in argv


async def test_driver_refusal_leaves_all_three_children_running(
    driver_mod,
    supervisor_mod,
    config: dict,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys,
) -> None:
    """The refusal's own exit status, fed through the supervisor seam, is survivable.

    The status is not invented: the prepare phase is run for real against a
    failing probe, and *that* nonzero status is what the stub driver exits with.
    The assertion is on the three supervised children directly — still up, never
    stopped, never killed — not on the absence of a sentinel.
    """
    paths = _isolate(monkeypatch, tmp_path)
    refusal_status = driver_mod.run_prepare_phase(
        state_home=paths.state,
        repo_root=paths.repo,
        answers_path=paths.answers,
        run_cli=FakeCli(paths.config),
        probe=ScriptedProbe(driver_mod, ok=False, stderr="bwrap: Can't mount proc"),
        preflight=_passing_preflight,
    )
    capsys.readouterr()
    assert refusal_status != 0

    monkeypatch.setenv("ERGANE_DEMO", "1")
    demo = ChildStub("demo")
    run_task, children, _started, demo_starts = await _run_supervisor_with_demo(
        supervisor_mod, config, demo=demo
    )
    assert await _wait_until(lambda: bool(demo_starts))

    demo.finish(refusal_status)
    assert await _wait_until(lambda: demo._exit_event.is_set())
    await asyncio.sleep(0.05)

    assert not run_task.done()
    for name, child in children.items():
        assert not child.stopped, name
        assert not child.killed, name
        assert child.returncode is None, name

    assert await _shutdown(run_task) == 0


# -----------------------------------------------------------------------------
# T005 [US1-S5, FR-006] two sentinels, two promises
# -----------------------------------------------------------------------------


def test_second_run_after_a_successful_first_boot_is_a_one_line_no_op(
    driver_mod, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    """A completed prepare with a passing probe makes the next run a no-op."""
    paths = _isolate(monkeypatch, tmp_path)
    first_cli = FakeCli(paths.config)
    first_probe = ScriptedProbe(driver_mod, ok=True)

    assert (
        driver_mod.run_prepare_phase(
            state_home=paths.state,
            repo_root=paths.repo,
            answers_path=paths.answers,
            run_cli=first_cli,
            probe=first_probe,
            preflight=_passing_preflight,
        )
        == 0
    )
    capsys.readouterr()
    assert (paths.state / "demo" / driver_mod.PREPARED_SENTINEL).is_file()

    second_cli = FakeCli(paths.config)
    second_probe = ScriptedProbe(driver_mod, ok=True)
    status = driver_mod.run_prepare_phase(
        state_home=paths.state,
        repo_root=paths.repo,
        answers_path=paths.answers,
        run_cli=second_cli,
        probe=second_probe,
        preflight=_passing_preflight,
    )
    printed = capsys.readouterr().out.strip()

    assert status == 0
    assert second_cli.calls == []
    assert second_probe.calls == []
    assert len(printed.splitlines()) == 1, printed
    assert "already" in printed


def test_a_failing_step_leaves_as_a_named_line_not_a_traceback(
    driver_mod, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    """`main` turns any failure into one line and a nonzero status (FR-001)."""
    paths = _isolate(monkeypatch, tmp_path)

    def explode(**kwargs):
        raise subprocess.CalledProcessError(128, ["git", "init"])

    monkeypatch.setattr(driver_mod, "run_prepare_phase", explode)
    status = driver_mod.main(
        ["--state-home", str(paths.state), "--repo", str(paths.repo)]
    )
    printed = capsys.readouterr().out

    assert status == 1
    assert "first boot failed" in printed
    assert "CalledProcessError" in printed


def test_second_run_after_a_probe_refusal_retries_the_probe(
    driver_mod, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    """A refusal leaves no sentinel, so a stranger who fixes the host retries."""
    paths = _isolate(monkeypatch, tmp_path)
    refused = ScriptedProbe(driver_mod, ok=False, stderr="bwrap: Can't mount proc")

    assert (
        driver_mod.run_prepare_phase(
            state_home=paths.state,
            repo_root=paths.repo,
            answers_path=paths.answers,
            run_cli=FakeCli(paths.config),
            probe=refused,
            preflight=_passing_preflight,
        )
        != 0
    )
    capsys.readouterr()
    assert len(refused.calls) == 1
    assert not (paths.state / "demo" / driver_mod.PREPARED_SENTINEL).exists()

    retried = ScriptedProbe(driver_mod, ok=True)
    status = driver_mod.run_prepare_phase(
        state_home=paths.state,
        repo_root=paths.repo,
        answers_path=paths.answers,
        run_cli=FakeCli(paths.config),
        probe=retried,
        preflight=_passing_preflight,
    )
    capsys.readouterr()

    assert len(retried.calls) == 1, "the probe was not retried after a refusal"
    assert status == 0
    assert (paths.state / "demo" / driver_mod.PREPARED_SENTINEL).is_file()
