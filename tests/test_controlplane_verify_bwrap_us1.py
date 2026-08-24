"""US1 of 088: `ergane install --verify` proves the sandbox runs.

These tests drive `factory.controlplane.verify._inspect_host` through its
injected bwrap execution seam and assert the three host-probe branches for
`bwrap`: absent, present-but-unrunnable, and usable. Runtime claims are
met by tool output pasted verbatim below (constitution VIII).

T001 red output (before fix):

.. code-block:: text

    _________ test_inspect_host_reports_bwrap_unusable_when_run_seam_fails _________

        assert bwrap["present"] is True
    >   assert bwrap["usable"] is False
    E   assert True is False

    tests/test_controlplane_verify_bwrap_us1.py:61: AssertionError
    =========================== short test summary info ============================
    FAILED tests/test_controlplane_verify_bwrap_us1.py::test_inspect_host_reports_bwrap_unusable_when_run_seam_fails
    1 failed in 0.11s

Probe branches on this host after implementation:

.. code-block:: text

    present: True
    usable: True
    absent_remedy: install bubblewrap (bwrap)
    unrunnable_remedy: bwrap is present at /usr/bin/bwrap but cannot start a sandbox; unprivileged user namespaces are likely disabled. If you are running as root inside a container, the uid-0 path needs the SYS_ADMIN Linux privilege that unprivileged containers lack. Ensure the committed confinement artifacts are installed: container/seccomp-ergane.json and container/ergane-engine.profile.
    argv: ('/usr/bin/bwrap', '--ro-bind', '/usr', '/usr', '--symlink', 'usr/bin', '/bin', '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/sbin', '/sbin', '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', 'true')

Suite output after implementation:

.. code-block:: text

    ....
    4 passed in 0.23s

"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

import factory.controlplane.verify as verify_module


# ---------------------------------------------------------------------------
# T001 [US1-S1, FR-001, FR-004] stubbed failure makes bwrap unusable
# ---------------------------------------------------------------------------


def test_inspect_host_reports_bwrap_unusable_when_run_seam_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the bwrap execution seam reports failure, usable is false.

    The runner's PATH may or may not carry bwrap; patch discovery so the
    test is about the execution branch, not the host's own layout.
    """
    monkeypatch.setattr(verify_module.shutil, "which", lambda name: "/usr/bin/bwrap")

    def _failing_run(argv: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=argv,
            returncode=1,
            stdout="",
            stderr="bwrap: setting up uid map: Permission denied",
        )

    monkeypatch.setattr(verify_module, "_run_bwrap_probe", _failing_run)

    report = verify_module._inspect_host()
    bwrap = report["bwrap"]
    assert bwrap["present"] is True
    assert bwrap["usable"] is False


# ---------------------------------------------------------------------------
# T002 [US1-S2, FR-003] present-but-unrunnable remedy is distinct
# ---------------------------------------------------------------------------


def test_present_but_unrunnable_remedy_names_user_namespaces_and_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A blocked bwrap names a remedy distinct from the absent-case one."""
    monkeypatch.setattr(verify_module.shutil, "which", lambda name: "/usr/bin/bwrap")

    def _oserror_run(argv: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        raise OSError("bwrap: Can't create new user namespace")

    monkeypatch.setattr(verify_module, "_run_bwrap_probe", _oserror_run)

    report = verify_module._inspect_host()
    bwrap = report["bwrap"]
    absent_remedy = bwrap["remedy"]
    unrunnable_remedy = bwrap.get("unauthenticated_remedy")

    assert unrunnable_remedy is not None
    assert unrunnable_remedy != absent_remedy
    assert "user namespaces" in unrunnable_remedy.lower()
    assert "container/seccomp-ergane.json" in unrunnable_remedy
    assert "container/ergane-engine.profile" in unrunnable_remedy


# ---------------------------------------------------------------------------
# T003 [US1-S3, FR-004] real-binary case: usable true when bwrap executes
# ---------------------------------------------------------------------------


def test_real_bwrap_reports_usable_when_it_executes() -> None:
    """On a host where the probe's bwrap argv actually runs, usable is true.

    Skip by a guard evaluated at call time: if the pinned binary cannot execute
    the production-shape argv, the test is not applicable here. Never by a
    marker.
    """
    argv = verify_module._bwrap_probe_argv()
    try:
        result = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        pytest.skip(f"{argv[0]} is not runnable on this host")
    if result.returncode != 0:
        pytest.skip(f"{argv[0]} probe argv failed on this host: {result.stderr}")

    report = verify_module._inspect_host()
    assert report["bwrap"]["present"] is True
    assert report["bwrap"]["usable"] is True


# ---------------------------------------------------------------------------
# T003b [US1-S4, FR-002] probe argv exercises the production mount shape
# ---------------------------------------------------------------------------


def test_bwrap_probe_argv_has_production_mount_shape() -> None:
    """The probe's bwrap invocation matches the production sandbox shape."""
    argv = verify_module._bwrap_probe_argv()
    assert argv[0] == str(verify_module._BWRAP_PINNED_PATH)
    assert "--proc" in argv and "/proc" in argv
    assert "--dev" in argv and "/dev" in argv
    assert "--tmpfs" in argv and "/tmp" in argv
    assert "--ro-bind" in argv and "/usr" in argv
    assert argv[-1] == "true"
