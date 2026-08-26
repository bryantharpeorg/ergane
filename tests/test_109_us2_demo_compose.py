"""109-US2: drift tests over the demo compose project.

The demo project is a one-file Compose project intended for a stranger with
Docker and one API key. It is deliberately *not* the operational project:
its volumes are named, not same-path binds, and it does not share the host's
state. These tests fail if any of those invariants erode.

A live integration test at the bottom of this file brings the project up and
runs `ergane install --verify --from-file` inside it when a Docker daemon and a
real upstream model credential are available; otherwise it skips.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml

from factory.config import EXAMPLE_ALIAS_PREFIXES, is_example_alias
from factory.controlplane.verify import LLMProbe


#: The committed demo compose path.
DEMO_COMPOSE = Path("container") / "compose.demo.yaml"

#: The committed reference compose path whose image version source we reuse.
REFERENCE_COMPOSE = Path("container") / "compose.reference.yaml"

#: Service names the demo must declare.
DEMO_SERVICES: frozenset[str] = {"ergane", "gateway", "postgres"}

#: Reason the demo deliberately inverts the operational same-path rule.
INVERSE_MOUNT_REASON = (
    "the operational project binds host paths same-path because git records absolute "
    "paths in its worktree files, and a rewritten one breaks on the other side "
    "(container_project.py:318-329); the demo has no host side, so its volumes are "
    "named and no mount pair is same-path"
)

#: Required header content.
HEADER_PHRASES: tuple[str, ...] = (
    "demonstration",
    "volume-local state",
    "does not land",
    "ergane install --engine=container",
)


#: Single phrase that must appear literally, even if split across lines.
HEADER_DOES_NOT_LAND: str = "does not land"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        pytest.fail(f"{path} does not exist")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# -----------------------------------------------------------------------------
# T008 [US2-S1, FR-007] three services and shared image version source
# -----------------------------------------------------------------------------


def test_demo_compose_declares_exactly_three_services() -> None:
    """FR-007: exactly three services — engine, gateway, Postgres."""
    compose = _load_yaml(_repo_root() / DEMO_COMPOSE)
    services = compose.get("services", {})
    assert isinstance(services, dict), f"services must be a mapping, got {type(services).__name__}"
    names = set(services)
    assert names == DEMO_SERVICES, (
        f"expected services {sorted(DEMO_SERVICES)}, got {sorted(names)}"
    )


def test_demo_engine_image_derives_from_reference_version_source() -> None:
    """The engine image reference uses the same version source as the reference."""
    reference = _load_yaml(_repo_root() / REFERENCE_COMPOSE)
    demo = _load_yaml(_repo_root() / DEMO_COMPOSE)

    ref_image = reference["services"]["ergane"]["image"]
    demo_image = demo["services"]["ergane"]["image"]

    # The reference at compose.reference.yaml:10 is
    #   ghcr.io/bryantharpeorg/ergane:${ERGANE_VERSION}
    # The demo must derive from the same source, not hardcode a tag.
    assert "${ERGANE_VERSION}" in demo_image or "${ERGANE_IMAGE_TAG}" in demo_image, (
        f"demo engine image must derive from the same version source as the reference "
        f"({ref_image!r}), got {demo_image!r}"
    )


# -----------------------------------------------------------------------------
# T009 [P] [US2-S2, FR-008] named volumes and no same-path mount
# -----------------------------------------------------------------------------


def _mount_pairs(service: dict[str, Any]) -> list[tuple[str, str, bool]]:
    """Return (source, target, is_named_volume) for every mount entry.

    A bind mount that carries the gateway's static config file is allowed: it is
    a bundled artifact, not a host path, and is read-only. It is identified by a
    dict `type: bind` entry with a relative `source` starting with `./`.
    """
    pairs: list[tuple[str, str, bool]] = []
    for entry in service.get("volumes", []):
        if isinstance(entry, dict):
            source = str(entry.get("source", ""))
            target = str(entry.get("target", ""))
            mount_type = entry.get("type", "volume")
            is_named = mount_type == "volume"
            is_bundled_config = mount_type == "bind" and source.startswith("./")
            pairs.append((source, target, is_named or is_bundled_config))
        elif isinstance(entry, str):
            spec = entry.split(":")
            source = spec[0]
            target = spec[1] if len(spec) > 1 else source
            # A short form with no colon or a named volume has no leading host path.
            is_named = len(spec) <= 2 and not source.startswith("/") and not source.startswith(".")
            pairs.append((source, target, is_named))
        else:
            pytest.fail(f"unsupported mount entry type: {entry!r}")
    return pairs


def test_demo_compose_volumes_are_named_and_not_same_path() -> None:
    """FR-008: every volume is named, and no mount pair is same-path.

    The failure message carries the reason, because a reader coming from
    `container_project.py:326` will otherwise "fix" the demo into same-path
    binds. The bundled gateway config file is a read-only bind of a committed
    artifact, not a host path, and is therefore exempt from the named-volume rule.
    """
    compose = _load_yaml(_repo_root() / DEMO_COMPOSE)
    services = compose.get("services", {})

    bad: list[tuple[str, str, str, str]] = []
    for name, service in services.items():
        for source, target, is_named in _mount_pairs(service):
            if not is_named:
                bad.append((name, source, target, "not a named volume"))
            if source.rstrip("/") == target.rstrip("/"):
                bad.append((name, source, target, "same-path mount"))

    assert not bad, (
        f"demo compose violates its named-volume, not-same-path contract: {bad}. "
        f"Reason: {INVERSE_MOUNT_REASON}"
    )


# -----------------------------------------------------------------------------
# T010 [P] [US2-S3, FR-009] exactly one mandatory environment variable
# -----------------------------------------------------------------------------


def _env_entries(service: dict[str, Any]) -> dict[str, str]:
    """Return NAME -> raw value for every environment entry in the service."""
    entries: dict[str, str] = {}
    for entry in service.get("environment", []):
        if isinstance(entry, str):
            if "=" in entry:
                name, _, value = entry.partition("=")
                entries[name] = value
            else:
                entries[entry] = ""
        elif isinstance(entry, dict):
            entries.update({str(k): str(v) for k, v in entry.items()})
    return entries


def _is_mandatory(value: str) -> bool:
    """A value is mandatory if it has no default and no shell fallback.

    Examples:
      - "" (empty default) is not mandatory.
      - "${UPSTREAM_MODEL_API_KEY}" is mandatory.
      - "${ERGANE_LLM_MASTER_KEY:-sk-dummy-master}" is not mandatory.
    """
    if not value:
        return False
    if value.startswith("${") and value.endswith("}") and ":-" not in value:
        return True
    return False


#: Variables the release workflow substitutes; the operator is not required to set them.
SUBSTITUTED_AT_RELEASE: frozenset[str] = {"ERGANE_VERSION"}


def test_demo_compose_references_no_relative_paths() -> None:
    """The demo compose file must be self-contained. It has no siblings.

    This is the invariant the *delivery mechanism* demands, and it is the one
    the other drift tests here did not cover. The advertised install is

        curl -fsSL …/releases/latest/download/compose.yaml | docker compose -f - up

    which fetches exactly one file and pipes it to stdin. With `-f -`, Compose
    sets the project directory to the caller's working directory, so every
    relative path resolves against a directory that contains nothing.

    Both ways this failed were found live on 2026-08-26, and they fail
    differently, which is why neither `docker compose config` nor a green gate
    caught them:

      * `security_opt: seccomp:./seccomp-ergane.json` is a HARD failure --
        "opening seccomp profile (./seccomp-ergane.json) failed: … no such file
        or directory" -- and no container starts.
      * A long-form bind whose `source` is missing is NOT an error. Docker
        silently creates it as a root-owned empty DIRECTORY, so the service
        finds a directory where its config file should be and fails without
        naming the cause.

    `docker compose config` renders cleanly in both cases: it does not check
    that referenced paths exist. So this assertion is textual on purpose --
    there is no rendering step that would reveal the problem.

    The operational project (`compose.reference.yaml`) is exempt and keeps its
    relative paths: it is generated into a directory alongside its artifacts by
    `ergane install --engine=container`, so its siblings are really there.
    """
    text = (_repo_root() / DEMO_COMPOSE).read_text(encoding="utf-8")

    offenders: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        without_comment = line.split("#", 1)[0]
        if "./" in without_comment or "../" in without_comment:
            offenders.append((number, line.strip()))

    assert not offenders, (
        f"{DEMO_COMPOSE} must contain no relative path reference — it is "
        "delivered on its own by `curl … | docker compose -f -` and has no "
        "sibling files on the far side. Inline the content (see "
        "configs.gateway_config_file) or drop the reference. Offending lines: "
        + "; ".join(f"{number}: {body}" for number, body in offenders)
    )


def test_demo_compose_mounts_no_bind_sources() -> None:
    """No service may bind-mount a host path, under either mount syntax.

    The sibling of the test above, at the parsed layer rather than the textual
    one: an absolute bind source would slip past the relative-path check and
    still assume something exists on a stranger's machine.
    """
    compose = _load_yaml(_repo_root() / DEMO_COMPOSE)

    offenders: list[str] = []
    for name, service in (compose.get("services") or {}).items():
        for mount in service.get("volumes") or []:
            if isinstance(mount, dict):
                if mount.get("type") == "bind":
                    offenders.append(f"{name}: bind -> {mount.get('source')}")
            elif isinstance(mount, str):
                source = mount.split(":", 1)[0]
                if source.startswith((".", "/", "~")):
                    offenders.append(f"{name}: bind -> {source}")

    assert not offenders, (
        "the demo project may not bind-mount host paths; every mount is a named "
        f"volume or an inline config. Offenders: {offenders}"
    )


def test_demo_compose_requires_exactly_one_mandatory_env_var() -> None:
    """FR-009: only the upstream model credential is mandatory; all else defaults.

    `ERGANE_VERSION` is the version-source placeholder the release workflow
    resolves (FR-017/FR-018); the fetched file has the real tag baked in, so it
    is not an operator-required variable.
    """
    compose = _load_yaml(_repo_root() / DEMO_COMPOSE)
    services = compose.get("services", {})

    mandatory: set[str] = set()
    for service in services.values():
        for name, value in _env_entries(service).items():
            if _is_mandatory(value) and name not in SUBSTITUTED_AT_RELEASE:
                mandatory.add(name)

    assert len(mandatory) == 1, (
        f"expected exactly one mandatory environment variable across the demo, "
        f"got {len(mandatory)}: {sorted(mandatory)}"
    )
    # The single mandatory variable must be the upstream credential.
    required_name = mandatory.pop()
    assert required_name.endswith("_API_KEY"), (
        f"the single mandatory variable must be the upstream model credential, got {required_name!r}"
    )


# -----------------------------------------------------------------------------
# T011 [P] [US2-S4, FR-010] bundled registry has no example/ aliases
# -----------------------------------------------------------------------------


@pytest.fixture
def demo_registry_path() -> Path:
    return _repo_root() / "container" / "personas.demo.yaml"


@pytest.fixture
def demo_answers_path() -> Path:
    return _repo_root() / "container" / "ergane-install-answer.demo.toml"


def _load_registry_aliases(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    raw = yaml.safe_load(text)
    assert isinstance(raw, dict), f"{path} must be a mapping of persona names"
    aliases: set[str] = set()
    for _name, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        for value in (entry.get("model"), entry.get("fallback")):
            if isinstance(value, str) and value and value != "null":
                aliases.add(value)
    return aliases


def test_demo_registry_aliases_carry_no_example_prefix(
    demo_registry_path: Path,
) -> None:
    """FR-010: the bundled demo registry's aliases carry no example/ prefix.

    The demo satisfies `verify.py:441`; it does not bypass it.
    """
    if not demo_registry_path.is_file():
        pytest.fail(f"{demo_registry_path} does not exist")
    aliases = _load_registry_aliases(demo_registry_path)
    example_aliases = {a for a in aliases if is_example_alias(a)}
    assert not example_aliases, (
        f"demo registry contains example/ aliases: {sorted(example_aliases)}; "
        f"EXAMPLE_ALIAS_PREFIXES={EXAMPLE_ALIAS_PREFIXES}"
    )


def _inline_gateway_config() -> dict[str, Any]:
    """The gateway config as it actually ships — inline in the compose file.

    Read from `configs.gateway_config_file.content` rather than from
    `container/gateway-config.yaml`, because the inline copy is the one a
    stranger receives. The file on disk is the readable copy and is held equal
    to this by `test_demo_inline_gateway_config_matches_committed_copy`.
    """
    compose = _load_yaml(_repo_root() / DEMO_COMPOSE)
    content = compose["configs"]["gateway_config_file"]["content"]
    parsed = yaml.safe_load(content)
    assert isinstance(parsed, dict), "inline gateway config must parse to a mapping"
    return parsed


def test_demo_inline_gateway_config_matches_committed_copy() -> None:
    """The inline gateway config and its readable copy may never diverge.

    `container/gateway-config.yaml` stays in the tree because it is far easier
    to read and diff than a block scalar, and `personas.demo.yaml` names it. But
    only the inline copy ships, so a silent divergence would mean the file every
    reviewer reads is not the file the demo runs.
    """
    inline = _load_yaml(_repo_root() / DEMO_COMPOSE)["configs"]["gateway_config_file"][
        "content"
    ]
    committed = (_repo_root() / "container" / "gateway-config.yaml").read_text(
        encoding="utf-8"
    )
    assert inline == committed, (
        "container/gateway-config.yaml and the inline "
        "configs.gateway_config_file.content in container/compose.demo.yaml have "
        "diverged. They are byte-identical by contract: edit both, or neither."
    )


def test_demo_registry_aliases_match_gateway_config() -> None:
    """FR-010: every alias the registry dispatches must be served by the gateway.

    A registry naming an alias the bundled gateway does not serve would fail
    FR-005's probe three stages later wearing a different error. The gateway's
    config is the authority for what it serves.
    """
    registry = _load_yaml(_repo_root() / "container" / "personas.demo.yaml")
    gateway = _inline_gateway_config()

    gateway_aliases = {
        entry["model_name"]
        for entry in gateway.get("model_list", [])
        if isinstance(entry, dict) and isinstance(entry.get("model_name"), str)
    }
    registry_aliases: set[str] = set()
    for entry in registry.values():
        if not isinstance(entry, dict):
            continue
        for value in (entry.get("model"), entry.get("fallback")):
            if isinstance(value, str) and value and value != "null":
                registry_aliases.add(value)

    unserved = registry_aliases - gateway_aliases
    assert not unserved, (
        f"demo registry aliases not served by gateway config: {sorted(unserved)}; "
        f"gateway serves: {sorted(gateway_aliases)}"
    )


def test_verify_refusal_for_all_example_registry_is_untouched() -> None:
    """FR-010: the shipped refusal at verify.py:441 still exists and still fires.

    This asserts the guard is alive, not that the demo uses it.
    """
    import factory.controlplane.verify as verify_module

    all_example = {
        "implementer": type("P", (), {
            "model": "example/implementer",
            "fallback": "example/fallback",
            "routes_through_gateway": True,
        })(),
    }

    async def _gather() -> Any:
        return await LLMProbe().gather(
            type(
                "Cfg",
                (),
                {
                    "llm": type(
                        "LLM",
                        (),
                        {
                            "mode": "gateway",
                            "gateway": type(
                                "GW",
                                (),
                                {
                                    "base_url": "http://gateway:4000",
                                    "master_key_env": "ERGANE_LLM_MASTER_KEY",
                                    "gateway_mode": "managed",
                                    "timeout_s": 30,
                                },
                            )(),
                            "timeout_s": 30,
                        },
                    )(),
                },
            )()
        )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(verify_module, "_load_personas_for_probe", lambda: all_example)
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake")
    try:
        import asyncio

        snapshot = asyncio.run(_gather())
    finally:
        monkeypatch.undo()

    assert "not been configured" in snapshot.detail, (
        f"expected the example-alias refusal, got {snapshot.detail!r}"
    )


# -----------------------------------------------------------------------------
# T012 [P] [US2-S5, FR-011] header comment states what the project is not
# -----------------------------------------------------------------------------


def test_demo_compose_opens_with_disclaimer_header() -> None:
    """FR-011: the file opens with a comment explaining it is a demo."""
    path = _repo_root() / DEMO_COMPOSE
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines and lines[0].startswith("#"), "demo compose must open with a comment header"

    header = "\n".join(lines[:12])
    # Normalize `# ` comment markers and line breaks so a phrase split across
    # comment lines is still detected.
    normalized_header = re.sub(r"# ?", " ", header).replace("\n", " ").lower()
    normalized_header = re.sub(r"\s+", " ", normalized_header)
    missing = [phrase for phrase in HEADER_PHRASES if phrase.lower() not in normalized_header]
    assert not missing, (
        f"demo compose header missing required phrases: {missing}; "
        f"header was:\n{header}"
    )


# -----------------------------------------------------------------------------
# T015 [US3-S1, FR-011] demo flag and gateway endpoint are literal env values
# -----------------------------------------------------------------------------


DEMO_FLAG_LITERAL: str = "ERGANE_DEMO=1"
GATEWAY_URL_LITERAL: str = "LITELLM_PROXY_URL=http://gateway:4000"


def test_demo_compose_engine_env_carries_demo_flag_and_gateway_url() -> None:
    """FR-011: the engine service environment carries two literal demo values."""
    compose = _load_yaml(_repo_root() / DEMO_COMPOSE)
    ergane = compose.get("services", {}).get("ergane", {})
    raw_env = ergane.get("environment", [])

    assert DEMO_FLAG_LITERAL in raw_env, (
        f"engine environment must contain literal {DEMO_FLAG_LITERAL!r}"
    )
    assert GATEWAY_URL_LITERAL in raw_env, (
        f"engine environment must contain literal {GATEWAY_URL_LITERAL!r}"
    )
    # Literal values contain no `${`, so the mandatory-count test continues to
    # see exactly one required variable (UPSTREAM_MODEL_API_KEY).
    assert not any("${" in entry for entry in (DEMO_FLAG_LITERAL, GATEWAY_URL_LITERAL))


def test_demo_compose_requires_exactly_one_mandatory_env_var_extended() -> None:
    """T015: the literal additions do not introduce a second mandatory variable."""
    compose = _load_yaml(_repo_root() / DEMO_COMPOSE)
    services = compose.get("services", {})

    mandatory: set[str] = set()
    for service in services.values():
        for name, value in _env_entries(service).items():
            if _is_mandatory(value) and name not in SUBSTITUTED_AT_RELEASE:
                mandatory.add(name)

    assert len(mandatory) == 1, (
        f"expected exactly one mandatory environment variable across the demo, "
        f"got {len(mandatory)}: {sorted(mandatory)}"
    )
    required_name = mandatory.pop()
    assert required_name.endswith("_API_KEY"), (
        f"the single mandatory variable must be the upstream model credential, got {required_name!r}"
    )


# -----------------------------------------------------------------------------
# T016 [P] [US3-S2, FR-012] systempaths=unconfined with its mechanism comment
# -----------------------------------------------------------------------------


def test_demo_compose_security_opt_systempaths_has_mechanism_comment() -> None:
    """FR-012: systempaths=unconfined is present and the comment names the bug."""
    text = (_repo_root() / DEMO_COMPOSE).read_text(encoding="utf-8")
    lines = text.splitlines()

    # Find the engine service's security_opt block and its leading comment.
    in_ergane = False
    in_security_opt = False
    block_start = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "ergane:":
            in_ergane = True
        elif in_ergane and stripped.startswith("services:"):
            # Safety: do not walk into the next service definition.
            in_ergane = False
        elif in_ergane and stripped == "security_opt:":
            in_security_opt = True
            block_start = i
            break

    assert in_security_opt and block_start >= 0, "engine security_opt block not found"

    # The security_opt list is indented six spaces (`      - item`). Collect all
    # lines belonging to the list: entries, blank lines, and comments at that
    # indentation or deeper, stopping at the next service-level key.
    block_lines: list[str] = []
    for j in range(block_start + 1, len(lines)):
        line = lines[j]
        if not line.strip():
            block_lines.append(line)
            continue
        # List items (`      - ...`) and comments (`      # ...`) belong to the
        # block; any other non-blank line at the service indentation ends it.
        if line.startswith(("      -", "      #")):
            block_lines.append(line)
            continue
        if not line.startswith("        "):
            break
        block_lines.append(line)

    full_block = "\n".join(block_lines)
    assert "systempaths:unconfined" in full_block, (
        f"security_opt must contain 'systempaths:unconfined'; block was:\n{full_block}"
    )
    assert "bubblewrap#284" in full_block, (
        f"systempaths comment must name the mechanism via bubblewrap#284; block was:\n{full_block}"
    )


# -----------------------------------------------------------------------------
# T013+ implementation tests (turned green by the files this story writes)
# -----------------------------------------------------------------------------


def test_demo_compose_file_exists() -> None:
    """T008 is red until this file exists; keep a sentinel that stays green."""
    assert (_repo_root() / DEMO_COMPOSE).is_file(), f"{DEMO_COMPOSE} must exist"


def test_bundled_demo_registry_exists(demo_registry_path: Path) -> None:
    assert demo_registry_path.is_file(), f"{demo_registry_path} must exist"


def test_bundled_demo_answers_exists(demo_answers_path: Path) -> None:
    assert demo_answers_path.is_file(), f"{demo_answers_path} must exist"


# -----------------------------------------------------------------------------
# T015 [US2-S4, SC-002] live integration: the project comes up and verifies
# -----------------------------------------------------------------------------


def _docker_binary() -> str | None:
    """Return the docker binary path only when a daemon actually answers."""
    binary = shutil.which("docker")
    if binary is None:
        return None
    probe = subprocess.run(
        [binary, "version", "--format", "{{.Server.Version}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return binary if probe.returncode == 0 else None


DOCKER = _docker_binary()


@pytest.mark.skipif(
    DOCKER is None, reason="docker daemon is not reachable; integration test skipped"
)
@pytest.mark.live_proxy
def test_demo_project_comes_up_and_install_verify_passes_inside_it() -> None:
    """Bring up the demo project and run `ergane install --verify` inside it.

    This is the evidence for US2-S4/SC-002: the bundled gateway and persona
    registry satisfy the shipped refusal at verify.py:441, and the key-management
    probe (mint, constrain, spend logs, revoke) passes end-to-end.

    Requires:
      - a Docker daemon (skipped otherwise),
      - UPSTREAM_MODEL_API_KEY set to a real provider credential,
      - the engine image referenced by ERGANE_VERSION to be pullable or built.
    """
    upstream_key = os.environ.get("UPSTREAM_MODEL_API_KEY")
    if not upstream_key:
        pytest.skip("UPSTREAM_MODEL_API_KEY is not set; cannot run live integration")

    # The shipped HostProbe requires `gh` to be authenticated; GH_TOKEN is the
    # optional credential the compose file forwards into the engine.
    gh_token = os.environ.get("GH_TOKEN")
    if not gh_token:
        pytest.skip("GH_TOKEN is not set; cannot run live integration")

    repo_root = _repo_root()
    compose_path = repo_root / DEMO_COMPOSE
    answers_path = repo_root / "container" / "ergane-install-answer.demo.toml"

    assert compose_path.is_file()
    assert answers_path.is_file()

    env = os.environ.copy()
    env["UPSTREAM_MODEL_API_KEY"] = upstream_key
    env["GH_TOKEN"] = gh_token
    # Allow the operator to pin the image tag; otherwise use the CLI version so
    # the local build/tag path works.
    env.setdefault(
        "ERGANE_VERSION",
        __import__("factory.supervision.engine_identity", fromlist=["cli_version"]).cli_version(),
    )

    project_name = f"ergane-demo-verify-{uuid.uuid4().hex[:8]}"
    compose_argv = [
        str(DOCKER),
        "compose",
        "-f",
        str(compose_path),
        "-p",
        project_name,
    ]

    def _compose_run(argv: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*compose_argv, *argv],
            check=check,
            env=env,
            capture_output=True,
            text=True,
        )

    def _compose_exec(argv: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        return _compose_run(["exec", "-T", "ergane", *argv], check=check)

    # Validate the compose file before touching the daemon.
    _compose_run(["config"], check=True)

    try:
        # Bring the stack up. The gateway and postgres healthchecks gate ergane.
        up = _compose_run(["up", "-d"], check=False)
        assert up.returncode == 0, (
            f"docker compose up failed:\nstdout={up.stdout}\nstderr={up.stderr}"
        )

        # Wait long enough for the engine to finish its own readiness wait.
        _compose_run(["ps"], check=True)

        # Run the verification inside the engine, using the bundled answers file.
        verify = _compose_exec(
            [
                "ergane",
                "install",
                "--verify",
                "--from-file",
                "/opt/ergane/container/ergane-install-answer.demo.toml",
            ],
            check=False,
        )
        output = verify.stdout + verify.stderr

        assert verify.returncode == 0, (
            f"ergane install --verify failed inside the demo engine:\n{output}"
        )

        # The key-management probe must leave its own evidence in the output.
        output_lower = output.lower()
        assert "mint" in output_lower or "constrain" in output_lower, (
            f"key-management probe evidence (mint/constrain) missing:\n{output}"
        )
        assert "spend logs" in output_lower, (
            f"key-management probe evidence (spend logs) missing:\n{output}"
        )
        assert "revoke" in output_lower, (
            f"key-management probe evidence (revoke) missing:\n{output}"
        )
    finally:
        # Tear the stack down and discard the named volumes.
        subprocess.run(
            [*compose_argv, "down", "-v"],
            check=False,
            env=env,
            capture_output=True,
            text=True,
        )


# --- the documented command must name the variable the file actually needs ----


#: The three documents that carry the one-command install verbatim. A reader
#: copies whichever they land on first, so all three must agree with the file.
INSTALL_DOCS = (
    Path("specs") / "109-a-stranger-runs-the-factory-in-one-command" / "spec.md",
    Path("specs") / "109-a-stranger-runs-the-factory-in-one-command" / "plan.md",
    Path("specs") / "109-a-stranger-runs-the-factory-in-one-command" / "tasks.md",
)


def _documented_exports(text: str) -> set[str]:
    """Every variable the documented install tells a reader to export."""
    return set(re.findall(r"^export ([A-Z][A-Z0-9_]*)=", text, re.MULTILINE))


def _mandatory_compose_vars() -> set[str]:
    """The compose file's operator-required variables (the T010 computation)."""
    compose = _load_yaml(_repo_root() / DEMO_COMPOSE)
    mandatory: set[str] = set()
    for service in compose.get("services", {}).values():
        for name, value in _env_entries(service).items():
            if _is_mandatory(value) and name not in SUBSTITUTED_AT_RELEASE:
                mandatory.add(name)
    return mandatory


def test_documented_install_exports_the_variable_the_compose_file_needs() -> None:
    """The documented command and the file it fetches must name the same variable.

    This is the check whose absence let a real defect ship. T010 counts the
    compose file's mandatory variables and never compares them to the command a
    reader is told to run, so on 2026-08-26 all three documents said

        export ANTHROPIC_API_KEY=...

    while the file required `UPSTREAM_MODEL_API_KEY`. `ANTHROPIC_API_KEY`
    appeared zero times in the compose file.

    The failure shape is why this is worth a test rather than a proofread: the
    stack still comes up. Postgres reports healthy, LiteLLM's liveliness probe
    does not validate upstream credentials, and every one of the six demo
    aliases silently resolves its key to the empty string. The demo looks like
    it worked and dies at the first agent call with a 401 that does not name its
    cause — which is the exact experience this spec exists to prevent.
    """
    mandatory = _mandatory_compose_vars()
    root = _repo_root()

    for doc in INSTALL_DOCS:
        path = root / doc
        if not path.exists():  # pragma: no cover - the spec set is in the tree
            continue
        exported = _documented_exports(path.read_text(encoding="utf-8"))
        if not exported:
            continue
        missing = mandatory - exported
        assert not missing, (
            f"{doc} documents `export {sorted(exported)}` but the demo compose "
            f"file requires {sorted(missing)}. A reader following this command "
            f"gets an empty credential and a stack that looks healthy."
        )
        stray = exported - mandatory
        assert not stray, (
            f"{doc} tells the reader to export {sorted(stray)}, which "
            f"{DEMO_COMPOSE} never reads. The file's mandatory variables are "
            f"{sorted(mandatory)}."
        )
