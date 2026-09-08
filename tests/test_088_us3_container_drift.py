"""088-US3: drift tests over committed container artifacts.

These tests parse the Dockerfile, confinement profiles and reference compose
and fail when a required element is removed.  Required names are derived from
the host probe and the sandbox toolchain resolution, never restated.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from factory.controlplane.verify import _inspect_host
from factory.registry import resolve_state_home
from factory.supervision.container_project import derived_environment_names
from factory.supervision.units import supervision_home
from factory.verify.toolchain import CODEX_RUNNER, GIT, NODE, UV
from factory.workgraph.adapter import DEFAULT_EXECUTABLE


#: The seccomp profile delta: syscalls unconditionally allowed beyond the
#: vendored moby baseline.  The committed artifact comment names this same set
#: (trap 9).
SECCOMP_EXTRA_SYSCALLS: tuple[str, ...] = (
    "unshare",
    "clone",
    "clone3",
    "mount",
    "umount2",
    "pivot_root",
    "setns",
)

#: Docker/AppArmor profile paths under the repo root.
CONTAINER_DIR = Path("container")
DOCKERFILE = Path("Dockerfile")
SECCOMP_PROFILE = CONTAINER_DIR / "seccomp-ergane.json"
APPARMOR_PROFILE = CONTAINER_DIR / "ergane-engine.profile"
COMPOSE_FILE = CONTAINER_DIR / "compose.reference.yaml"


def _repo_root() -> Path:
    """Return the repository root: the directory holding the Dockerfile."""
    return Path(__file__).resolve().parent.parent


# -----------------------------------------------------------------------------
# T010 [US3-S1, FR-013] Dockerfile drift test
# -----------------------------------------------------------------------------


def _required_container_binaries() -> set[str]:
    """Return the binary names the image must ship.

    Sources:
    - `_inspect_host` probes bwrap, git, gh.
    - `BwrapBackend._toolchain` resolves the agent runners, uv, node, git.
    - FR-010 also requires python.
    The runners' names are `DEFAULT_EXECUTABLE` and `CODEX_RUNNER` (155-US4);
    git appears in both lists and is kept once.
    """
    host_probe = set(_inspect_host().keys())
    toolchain = {DEFAULT_EXECUTABLE, CODEX_RUNNER, UV, NODE, GIT}
    return host_probe | toolchain | {"python"}


def _parse_dockerfile() -> str:
    path = _repo_root() / DOCKERFILE
    if not path.is_file():
        pytest.fail(f"{DOCKERFILE} does not exist")
    return path.read_text(encoding="utf-8")


def test_dockerfile_exists_and_installs_required_binaries() -> None:
    """Every probed/toolchain binary is named in the Dockerfile."""
    text = _parse_dockerfile()
    lower = text.lower()
    missing = [name for name in _required_container_binaries() if name not in lower]
    assert not missing, f"Dockerfile missing required binaries: {missing}"


def test_dockerfile_installs_bwrap_at_pinned_path() -> None:
    """bwrap lands at /usr/bin/bwrap, the path both consumers pin."""
    text = _parse_dockerfile()
    assert "/usr/bin/bwrap" in text, "Dockerfile must place bwrap at /usr/bin/bwrap"


def test_dockerfile_runs_as_non_root() -> None:
    """The runtime user directive is present and not root."""
    text = _parse_dockerfile()
    match = re.search(r"^USER\s+(\S+)", text, re.MULTILINE | re.IGNORECASE)
    assert match is not None, "Dockerfile must declare a USER directive"
    user = match.group(1)
    assert user not in {"root", "0", "0:0"}, f"Dockerfile USER must be non-root, got {user}"


def test_dockerfile_entrypoint_is_us2_supervisor() -> None:
    """ENTRYPOINT starts the US2 container supervisor."""
    text = _parse_dockerfile()
    assert "ENTRYPOINT" in text.upper(), "Dockerfile must declare an ENTRYPOINT"
    assert "factory.supervision.container_supervisor" in text, (
        "ENTRYPOINT must run factory.supervision.container_supervisor"
    )


def test_dockerfile_installs_ergane_cli_distribution() -> None:
    """The image installs the ergane-cli distribution."""
    text = _parse_dockerfile()
    assert re.search(r"ergane[\s\-]?cli|pip\s+install.*ergane|uv\s+pip\s+install", text, re.IGNORECASE), (
        "Dockerfile must install the ergane-cli distribution"
    )


# -----------------------------------------------------------------------------
# T010b [US3-S2, US3-S3, FR-011, FR-013] Confinement drift tests
# -----------------------------------------------------------------------------


def _load_seccomp() -> dict[str, Any]:
    path = _repo_root() / SECCOMP_PROFILE
    if not path.is_file():
        pytest.fail(f"{SECCOMP_PROFILE} does not exist")
    return json.loads(path.read_text(encoding="utf-8"))


def test_seccomp_parses_and_allows_exactly_extra_syscalls() -> None:
    """The Ergane delta unconditionally allows exactly the seven syscalls."""
    profile = _load_seccomp()
    syscalls = profile.get("syscalls", [])

    def _is_unconditional_allow(rule: dict[str, Any]) -> bool:
        return (
            rule.get("action") == "SCMP_ACT_ALLOW"
            and not rule.get("includes")
            and not rule.get("excludes")
            and not rule.get("args")
            and not rule.get("errnoRet")
        )

    extra_allow_rules = [
        rule
        for rule in syscalls
        if _is_unconditional_allow(rule)
        and set(rule.get("names", [])) & set(SECCOMP_EXTRA_SYSCALLS)
    ]
    assert extra_allow_rules, (
        f"expected an unconditional allow rule for {SECCOMP_EXTRA_SYSCALLS}"
    )
    allowed_by_extra = set()
    for rule in extra_allow_rules:
        allowed_by_extra.update(rule.get("names", []))
    assert allowed_by_extra >= set(SECCOMP_EXTRA_SYSCALLS), (
        f"unconditional allow rules cover {allowed_by_extra}, missing "
        f"{set(SECCOMP_EXTRA_SYSCALLS) - allowed_by_extra}"
    )
    # The delta should not silently widen to additional syscalls.
    assert allowed_by_extra == set(SECCOMP_EXTRA_SYSCALLS), (
        f"unconditional allow rules cover {allowed_by_extra}, expected exactly "
        f"{set(SECCOMP_EXTRA_SYSCALLS)}"
    )


def test_seccomp_has_no_clone3_errno_rule() -> None:
    """No rule returns ERRNO for clone3 — the old filterable fallback is gone."""
    profile = _load_seccomp()
    for rule in profile.get("syscalls", []):
        names = rule.get("names") or []
        action = rule.get("action", "")
        if "clone3" in names and "ERRNO" in action.upper():
            pytest.fail(f"found clone3 ERRNO rule: {rule}")


def _load_apparmor() -> str:
    path = _repo_root() / APPARMOR_PROFILE
    if not path.is_file():
        pytest.fail(f"{APPARMOR_PROFILE} does not exist")
    return path.read_text(encoding="utf-8")


#: Deny lines carried over from the docker-default template.  These are the
#: `/proc` and `/sys` write masks the profile must retain.
APPARMOR_REQUIRED_DENIES: tuple[str, ...] = (
    "deny @{PROC}/* w,",
    "deny @{PROC}/{[^1-9],[^1-9][^0-9],[^1-9s][^0-9y][^0-9s],[^1-9][^0-9][^0-9][^0-9/]*}/** w,",
    "deny @{PROC}/sys/[^k]** w,",
    "deny @{PROC}/sys/kernel/{?,??,[^s][^h][^m]**} w,",
    "deny @{PROC}/sysrq-trigger rwklx,",
    "deny @{PROC}/kcore rwklx,",
    "deny /sys/[^f]*/** wklx,",
    "deny /sys/f[^s]*/** wklx,",
    "deny /sys/fs/[^c]*/** wklx,",
    "deny /sys/fs/c[^g]*/** wklx,",
    "deny /sys/fs/cg[^r]*/** wklx,",
    "deny /sys/firmware/** rwklx,",
    "deny /sys/devices/virtual/powercap/** rwklx,",
    "deny /sys/kernel/security/** rwklx,",
)


def test_apparmor_contains_required_allows_and_retains_denies() -> None:
    """The AppArmor profile has the three deltas and keeps every docker-default deny."""
    text = _load_apparmor()
    lines = text.splitlines()
    for syscall in ("userns,", "mount,", "pivot_root,"):
        assert any(line.strip() == syscall for line in lines), (
            f"AppArmor profile missing required allow rule line: {syscall}"
        )
    for deny in APPARMOR_REQUIRED_DENIES:
        assert deny in text, f"AppArmor profile missing required deny line: {deny}"


def test_apparmor_has_no_unconfined_flag() -> None:
    """The committed profile never relaxes confinement with unconfined."""
    text = _load_apparmor()
    assert "flags=(unconfined)" not in text, "AppArmor profile must not contain flags=(unconfined)"


# -----------------------------------------------------------------------------
# T011 [US3-S4, FR-012, FR-013] Reference compose drift test
# -----------------------------------------------------------------------------


def _load_compose() -> dict[str, Any]:
    path = _repo_root() / COMPOSE_FILE
    if not path.is_file():
        pytest.fail(f"{COMPOSE_FILE} does not exist")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _compose_environment_variable_names() -> set[str]:
    """Return the env-var names the five subsystem blocks name by default.

    The derivation itself moved to `factory.supervision.container_project`
    (104-US2, T021): the generator emits this same passthrough list, so a second
    copy of the rule here is how the reference file and the file `ergane install`
    writes would stop agreeing. This test reads it from the one source.
    """
    return derived_environment_names()


def test_compose_declares_exactly_one_service() -> None:
    """The reference compose declares exactly one engine service."""
    compose = _load_compose()
    services = compose.get("services", {})
    assert isinstance(services, dict)
    assert len(services) == 1, f"expected exactly one service, got {len(services)}"


@pytest.fixture
def service() -> dict[str, Any]:
    compose = _load_compose()
    services = compose.get("services", {})
    return next(iter(services.values()))


def test_compose_service_has_init_and_non_root_user(service: dict[str, Any]) -> None:
    assert service.get("init") is True, "service must set init: true"
    user = service.get("user")
    assert user is not None, "service must declare a non-root user"
    assert str(user) not in {"root", "0", "0:0"}, f"service user must be non-root, got {user}"


def test_compose_service_drops_capabilities_and_new_privileges(service: dict[str, Any]) -> None:
    assert service.get("cap_drop") == ["ALL"], "service must cap_drop: [ALL]"
    security_opt = service.get("security_opt", [])
    assert any("no-new-privileges" in str(entry) for entry in security_opt), (
        "security_opt must contain no-new-privileges"
    )


def test_compose_service_uses_committed_confinement_artifacts(service: dict[str, Any]) -> None:
    security_opt = [str(entry) for entry in service.get("security_opt", [])]
    assert any("seccomp" in entry and "seccomp-ergane.json" in entry for entry in security_opt), (
        "security_opt must reference container/seccomp-ergane.json by path"
    )
    assert any("apparmor=ergane-engine" in entry for entry in security_opt), (
        "security_opt must contain apparmor=ergane-engine"
    )


def test_compose_service_has_same_path_state_and_supervision_mounts(service: dict[str, Any]) -> None:
    """State root and supervision home are bound same-path into the container."""
    state_root = resolve_state_home() / "ergane"
    supe_home = supervision_home()

    def _same_path_mount(source: str, target: str) -> bool:
        return source.rstrip("/") == target.rstrip("/")

    mounts = service.get("volumes", [])
    state_mounted = False
    supervision_mounted = False
    for entry in mounts:
        if isinstance(entry, str):
            if ":" not in entry:
                continue
            source, target = entry.split(":", 1)
            target = target.rsplit(":", 1)[0]  # strip bind/rw suffix
        elif isinstance(entry, dict):
            source = str(entry.get("source", ""))
            target = str(entry.get("target", ""))
            if entry.get("type") != "bind":
                continue
        else:
            continue
        if _same_path_mount(source, target):
            if str(state_root) in source or source.endswith("/ergane"):
                state_mounted = True
            if str(supe_home) in source or source.endswith("/supervision"):
                supervision_mounted = True

    assert state_mounted, (
        f"service must bind-mount the state root same-path (expected under {state_root})"
    )
    assert supervision_mounted, (
        f"service must bind-mount the supervision home same-path (expected under {supe_home})"
    )


def test_compose_service_passes_through_subsystem_environment_variables(service: dict[str, Any]) -> None:
    """Every variable the five subsystem blocks name is passed through."""
    env = service.get("environment", [])
    env_names = {str(e) for e in env}
    required = _compose_environment_variable_names()
    missing = required - env_names
    assert not missing, f"service environment missing passthrough for: {sorted(missing)}"


def test_compose_has_same_path_repo_mount_list() -> None:
    """A per-repo source-mount list exists and every entry is same-path."""
    compose = _load_compose()
    repo_mounts = compose.get("x-ergane-repos", [])
    assert isinstance(repo_mounts, list), "compose must declare x-ergane-repos as a per-repo mount list"
    for entry in repo_mounts:
        source = str(entry.get("source", ""))
        target = str(entry.get("target", ""))
        assert source and source == target, (
            f"repo mount must be same-path, got source={source!r} target={target!r}"
        )


def test_compose_contains_no_unconfined_token() -> None:
    """No unconfined token appears anywhere in the reference compose."""
    text = (_repo_root() / COMPOSE_FILE).read_text(encoding="utf-8")
    assert "unconfined" not in text.lower(), "reference compose must not contain the unconfined token"
