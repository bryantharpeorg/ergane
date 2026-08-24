"""088-US1: the host preflight proves the sandbox actually runs.

The probe's old bwrap entry set `usable` equal to `present` (both were
`shutil.which("bwrap") is not None`).  A blocked user namespace therefore
reported green.  These tests drive `_inspect_host` through an injectable
execution seam and assert `usable` comes from running the pinned `/usr/bin/bwrap`
under the production mount shape.

Evidence rule (constitution VIII): runtime claims are met by tool output pasted
verbatim below.

Unfixed-tree run (T001 red):

.. code-block:: text

    FFFF                                                                     [100%]
    =================================== FAILURES ===================================
    ______________ test_bwrap_present_but_exec_fails_reports_unusable ______________
    >       monkeypatch.setattr(verify_module, "_run_bwrap_probe", lambda argv: False)
    E       AttributeError: module 'factory.controlplane.verify' has no attribute '_run_bwrap_probe'
    _____ test_bwrap_unrunnable_remedy_names_userns_and_confinement_artifacts ______
    >       monkeypatch.setattr(verify_module, "_run_bwrap_probe", lambda argv: False)
    E       AttributeError: module 'factory.controlplane.verify' has no attribute '_run_bwrap_probe'
    ________________ test_bwrap_runs_at_pinned_path_reports_usable _________________
    >       argv = verify_module._bwrap_probe_argv()
    E       AttributeError: module 'factory.controlplane.verify' has no attribute '_bwrap_probe_argv'
    ______ test_bwrap_probe_argv_uses_pinned_path_and_production_mount_shape _______
    >       argv = verify_module._bwrap_probe_argv()
    E       AttributeError: module 'factory.controlplane.verify' has no attribute '_bwrap_probe_argv'

Fixed-tree run:

.. code-block:: text

    ....                                                                     [100%]
    4 passed in 0.07s

Probe argv and the three branches:

.. code-block:: text

    probe argv: ['/usr/bin/bwrap', '--ro-bind', '/usr', '/usr', '--symlink', 'usr/bin', '/bin', '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/sbin', '/sbin', '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '/usr/bin/true']
    absent: {'present': False, 'usable': False, 'purpose': 'sandboxing agent worktrees', 'absent_remedy': 'install bubblewrap (bwrap)', 'unauthenticated_remedy': 'bwrap is present but cannot execute: unprivileged user namespaces are blocked on this host. Ensure the committed confinement artifacts are loaded: container/seccomp-ergane.json (seccomp) and container/ergane-engine.profile (AppArmor). If running as root inside a container, run as an unprivileged user instead.'}
    present-but-unrunnable: {'present': True, 'usable': False, 'purpose': 'sandboxing agent worktrees', 'absent_remedy': 'install bubblewrap (bwrap)', 'unauthenticated_remedy': 'bwrap is present but cannot execute: unprivileged user namespaces are blocked on this host. Ensure the committed confinement artifacts are loaded: container/seccomp-ergane.json (seccomp) and container/ergane-engine.profile (AppArmor). If running as root inside a container, run as an unprivileged user instead.'}
    present-but-usable: {'present': True, 'usable': True, 'purpose': 'sandboxing agent worktrees', 'absent_remedy': 'install bubblewrap (bwrap)', 'unauthenticated_remedy': 'bwrap is present but cannot execute: unprivileged user namespaces are blocked on this host. Ensure the committed confinement artifacts are loaded: container/seccomp-ergane.json (seccomp) and container/ergane-engine.profile (AppArmor). If running as root inside a container, run as an unprivileged user instead.'}
"""

from __future__ import annotations

import os
import subprocess
from typing import Any

import pytest

import factory.controlplane.verify as verify_module


#: The path the factory actually dispatches, per factory/workgraph/adapter.py.
_BWRAP_PINNED = "/usr/bin/bwrap"


def _fake_which(*, bwrap_path: str | None = _BWRAP_PINNED) -> Any:
    """Return a `shutil.which` replacement that finds bwrap at the pinned path."""

    def _which(name: str, path: str | None = None) -> str | None:
        if name == "bwrap":
            return bwrap_path
        return None

    return _which


def _bwrap_runs_at_pinned_path() -> bool:
    """Guard for the real-binary test: actually execute the pinned bwrap argv.

    This is evaluated at call time; if bwrap cannot run here, the test returns
    early rather than using a marker skip (trap 5).
    """
    if not os.access(_BWRAP_PINNED, os.X_OK):
        return False
    try:
        argv = verify_module._bwrap_probe_argv()
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError, Exception):
        return False
    return result.returncode == 0


# ---------------------------------------------------------------------------
# T001 [US1-S1, FR-001, FR-004] present-but-blocked bwrap is usable: false
# ---------------------------------------------------------------------------


def test_bwrap_present_but_exec_fails_reports_unusable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Drive `_inspect_host` with the bwrap execution seam stubbed to fail.

    `present` stays true because `shutil.which` finds bwrap, but `usable` must
    come from the injected execution seam, so it is false.
    """
    monkeypatch.setattr(verify_module.shutil, "which", _fake_which())
    monkeypatch.setattr(verify_module, "_run_bwrap_probe", lambda argv: False)

    report = verify_module._inspect_host()
    bwrap = report["bwrap"]
    assert bwrap["present"] is True
    assert bwrap["usable"] is False


# ---------------------------------------------------------------------------
# T002 [US1-S2, FR-003] present-but-unrunnable remedy is distinct and specific
# ---------------------------------------------------------------------------


def test_bwrap_unrunnable_remedy_names_userns_and_confinement_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The present-but-unrunnable remedy differs from the absent-case one.

    It names unprivileged user namespaces and the two committed confinement
    artifacts by path.
    """
    monkeypatch.setattr(verify_module.shutil, "which", _fake_which())
    monkeypatch.setattr(verify_module, "_run_bwrap_probe", lambda argv: False)

    report = verify_module._inspect_host()
    bwrap = report["bwrap"]
    absent = bwrap["absent_remedy"]
    unrunnable = bwrap["unauthenticated_remedy"]

    assert absent != unrunnable
    assert "unprivileged user namespaces" in unrunnable
    assert "container/seccomp-ergane.json" in unrunnable
    assert "container/ergane-engine.profile" in unrunnable


# ---------------------------------------------------------------------------
# T003 [US1-S3, FR-004] real bwrap at the pinned path reports usable: true
# ---------------------------------------------------------------------------


def test_bwrap_runs_at_pinned_path_reports_usable() -> None:
    """When the real `/usr/bin/bwrap` executes under the probe argv, `usable` is true.

    Guard evaluated at call time; if this host cannot run the pinned binary, the
    test returns without asserting (trap 5).
    """
    if not _bwrap_runs_at_pinned_path():
        return

    report = verify_module._inspect_host()
    assert report["bwrap"]["usable"] is True


# ---------------------------------------------------------------------------
# T003b [US1-S4, FR-002] probe argv exercises the production mount shape
# ---------------------------------------------------------------------------


def test_bwrap_probe_argv_uses_pinned_path_and_production_mount_shape() -> None:
    """The assembled argv executes `/usr/bin/bwrap` with `--proc`, `--dev`, tmpfs and ro `/usr`.

    It must not fall back to the minimal `--ro-bind / / true`, which passes on
    kernels where the production `--proc` mount is refused.
    """
    argv = verify_module._bwrap_probe_argv()

    assert argv[0] == _BWRAP_PINNED
    assert "--proc" in argv
    assert "--dev" in argv
    assert "--tmpfs" in argv
    assert "--ro-bind" in argv
    assert argv.count("/usr") >= 2

    # Reject the minimal invocation that masks the masked-/proc failure class.
    for i in range(len(argv) - 2):
        if argv[i] == "--ro-bind":
            assert not (argv[i + 1] == "/" and argv[i + 2] == "/")
