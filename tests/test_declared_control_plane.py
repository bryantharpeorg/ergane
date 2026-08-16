"""048-US1: the build resolves its endpoint and credential from what was declared.

Every test here binds the control-plane config path explicitly — an explicit
`config_path=` argument to the resolver, or `ERGANE_CONFIG_PATH` on a
`tmp_path` for the CLI paths — so none of them can resolve the operator's real
`~/.config/ergane/config.toml` (FR-012, plan trap 4). `resolve_config_path()`
falls back to `$XDG_CONFIG_HOME` and then `Path.home()`, so a test that forgot
would read a file that exists on this host and not on the grader's.

Every test also deletes `LITELLM_PROXY_URL`/`LITELLM_MASTER_KEY` before it
asserts anything about the declared route: this repository's own worker exports
both, and a test that inherited them would be measuring the shell.

The fixture config and the fixture environment disagree on every value they
both carry (plan trap 5). If they agreed, no test below could tell which source
the resolver actually consulted.

The runtime evidence — the red run, and one mutation per behaviour — is pasted
verbatim at the bottom of this file (constitution VIII / D-037).
"""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from typing import Any

import pytest

from factory.cli.errors import OperatorError
from factory.controlplane.resolve import (
    ControlPlaneResolutionError,
    resolve_llm_gateway,
    resolve_master_key_env,
)
from factory.env import ERGANE_CONFIG_PATH_ENV, FACTORY_CONFIG_PATH_ENV
from factory.usage.litellm_client import MASTER_KEY_ENV, PROXY_URL_ENV

# --- fixture values: the two sources disagree on everything (plan trap 5) -----

DECLARED_BASE_URL = "http://declared.gateway.test/v1"
DECLARED_KEY_VAR = "DECLARED_KEY_VAR"

OVERRIDE_BASE_URL = "http://override.gateway.test/v1"

#: A credential that could leak if the resolution ever carried a value rather
#: than a variable name (plan trap 6). Distinctive on purpose: an empty or
#: absent fixture credential would make the sentinel assertions worthless.
SENTINEL_CREDENTIAL = "sk-sentinel-048-us1-must-never-be-rendered"

EPIC_ID = "048-fixture-epic"


def _write_config(tmp_path: Path) -> Path:
    """A complete, parseable config declaring a gateway, at a bound path.

    All five blocks, because the parser requires all five; only `[llm]` is what
    this story reads.
    """
    path = tmp_path / "config.toml"
    path.write_text(f"""\
version = 1

[llm]
mode = "gateway"
base_url = "{DECLARED_BASE_URL}"
master_key_env = "{DECLARED_KEY_VAR}"

[memory]
backend = "none"

[temporal]
mode = "external"
address = "declared.temporal.test:7233"
namespace = "declared"

[telemetry]

[escalation]
adapter = "telegram"
chat_id_env = "DECLARED_CHAT_ID"
bot_token_env = "DECLARED_BOT_TOKEN"
""", encoding="utf-8")
    return path


def _no_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove both legacy variables the operator's shell exports."""
    monkeypatch.delenv(PROXY_URL_ENV, raising=False)
    monkeypatch.delenv(MASTER_KEY_ENV, raising=False)


def _bind_config_path(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    """Bind both config-path variables for the CLI paths (FR-012)."""
    monkeypatch.setenv(ERGANE_CONFIG_PATH_ENV, str(path))
    monkeypatch.setenv(FACTORY_CONFIG_PATH_ENV, str(path))


# ---------------------------------------------------------------------------
# T001 / US1-S2 — the override wins, and this host keeps building untouched
# ---------------------------------------------------------------------------


def test_the_environment_overrides_the_declaration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1-S2, FR-002: a host exporting both variables resolves exactly as today.

    Written first, and it is the acceptance condition rather than a nicety: the
    worker on this development host exports both and has no config file behind
    it. A change that required re-provisioning this machine to keep building
    would be a failed change (plan trap 1).
    """
    config_path = _write_config(tmp_path)
    monkeypatch.setenv(PROXY_URL_ENV, OVERRIDE_BASE_URL)
    monkeypatch.setenv(MASTER_KEY_ENV, SENTINEL_CREDENTIAL)

    resolution = resolve_llm_gateway(config_path=config_path)

    assert resolution.base_url == OVERRIDE_BASE_URL
    assert resolution.base_url_source == PROXY_URL_ENV
    assert resolution.master_key_env == MASTER_KEY_ENV
    assert resolution.master_key_source == MASTER_KEY_ENV

    # The declared values are present in the file and lost the race — which is
    # the only reason this test can distinguish the two sources at all.
    assert resolution.base_url != DECLARED_BASE_URL
    assert resolution.master_key_env != DECLARED_KEY_VAR


# ---------------------------------------------------------------------------
# T002 / US1-S1 — the declaration supplies both when nothing overrides it
# ---------------------------------------------------------------------------


def test_the_declaration_supplies_both_values_when_nothing_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1-S1, FR-001, SC-002: a freshly installed host resolves from its config."""
    config_path = _write_config(tmp_path)
    _no_overrides(monkeypatch)
    monkeypatch.setenv(DECLARED_KEY_VAR, SENTINEL_CREDENTIAL)

    resolution = resolve_llm_gateway(config_path=config_path)

    assert resolution.base_url == DECLARED_BASE_URL
    assert resolution.base_url_source == str(config_path)
    assert resolution.master_key_env == DECLARED_KEY_VAR
    assert resolution.master_key_source == str(config_path)


def test_the_declared_credential_is_read_from_the_declared_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SC-002's second half: the credential comes from the variable the file named.

    The resolution carries the *name*; the value is fetched at the last moment
    by whoever needs it, exactly as `from_env` fetched it before this story.
    """
    config_path = _write_config(tmp_path)
    _no_overrides(monkeypatch)
    monkeypatch.setenv(DECLARED_KEY_VAR, SENTINEL_CREDENTIAL)

    resolution = resolve_llm_gateway(config_path=config_path)

    assert resolution.credential.read() == SENTINEL_CREDENTIAL


# ---------------------------------------------------------------------------
# T003 / US1-S3 — when both overrides speak, the file is never opened
# ---------------------------------------------------------------------------


def test_overrides_set_means_the_config_file_is_never_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1-S3, FR-002: bound to unparseable TOML, resolution still succeeds.

    A resolver that opened this file could not have passed: the parser refuses
    it. That is the anti-vacuity — the only way to observe a read that did not
    happen is to make the read fatal.
    """
    broken = tmp_path / "config.toml"
    broken.write_text('version = 1\n[llm\nmode = "gateway"\n', encoding="utf-8")
    monkeypatch.setenv(PROXY_URL_ENV, OVERRIDE_BASE_URL)
    monkeypatch.setenv(MASTER_KEY_ENV, SENTINEL_CREDENTIAL)

    resolution = resolve_llm_gateway(config_path=broken)

    assert resolution.base_url == OVERRIDE_BASE_URL
    assert resolution.master_key_env == MASTER_KEY_ENV


# ---------------------------------------------------------------------------
# T004 / US1-S4 — nothing declared: refuse naming both routes
# ---------------------------------------------------------------------------


def _write_graph(tmp_path: Path) -> Path:
    """A minimal compiled graph `ergane build start` will accept.

    `build._persona_registry` synthesises the registry from the graph itself.
    """
    graph_path = tmp_path / "workgraph.json"
    graph_path.write_text(
        json.dumps(
            {
                "epic_id": EPIC_ID,
                "feature": EPIC_ID,
                "specs_root": str(tmp_path / "specs"),
                "target_repo": str(tmp_path / "target"),
                "nodes": [
                    {
                        "id": "us1",
                        "story_key": "US1",
                        "persona": "implementer",
                        "spec_ref": f"{EPIC_ID}/us1",
                        "requirement_keys": ["US1", "FR-001"],
                        "depends_on": [],
                        "depends_on_merged": [],
                        "timeout_override_s": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return graph_path


def test_epic_start_with_nothing_declared_names_both_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1-S4, FR-004: the refusal names the variable *and* the config path.

    Today it names one route, which is how an operator who completed the
    interview concludes the config does nothing.
    """
    from factory.cli.nouns import build as build_module

    missing = tmp_path / "absent" / "config.toml"
    _no_overrides(monkeypatch)
    _bind_config_path(monkeypatch, missing)
    graph_path = _write_graph(tmp_path)

    with pytest.raises(OperatorError) as excinfo:
        build_module.start_command(
            Namespace(graph=str(graph_path), max_concurrent_nodes=1)
        )

    message = str(excinfo.value)
    assert PROXY_URL_ENV in message
    assert str(missing) in message
    assert SENTINEL_CREDENTIAL not in message


# ---------------------------------------------------------------------------
# T005 / US1-S5 — a broken config is refused, not degraded
# ---------------------------------------------------------------------------


def test_a_config_the_parser_refuses_surfaces_the_parsers_own_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1-S5, FR-005, plan trap 3: refuse for a broken config, degrade for a missing one.

    `registry.py` and `notify/adapter.py` swallow `ControlPlaneConfigError`
    wholesale because their callers must work unprovisioned. Copying that
    reflex here would tell an operator who typo'd their config to export a
    variable — the belief this spec exists to end.
    """
    broken = tmp_path / "config.toml"
    broken.write_text('version = 1\n[llm\nmode = "gateway"\n', encoding="utf-8")
    _no_overrides(monkeypatch)

    with pytest.raises(ControlPlaneResolutionError) as excinfo:
        resolve_llm_gateway(config_path=broken)

    message = str(excinfo.value)
    assert str(broken) in message
    # The parser's own grammar, not a story about the environment.
    assert "malformed_toml" in message
    assert PROXY_URL_ENV not in message
    assert "is not set" not in message


def test_a_missing_config_is_not_reported_as_a_broken_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of trap 3: absent degrades to the both-routes refusal."""
    missing = tmp_path / "absent" / "config.toml"
    _no_overrides(monkeypatch)

    with pytest.raises(ControlPlaneResolutionError) as excinfo:
        resolve_llm_gateway(config_path=missing)

    message = str(excinfo.value)
    assert PROXY_URL_ENV in message
    assert str(missing) in message
    assert "malformed" not in message


# ---------------------------------------------------------------------------
# T006 / US1-S6 — a declared variable that is unset names itself and the file
# ---------------------------------------------------------------------------


def test_an_unset_declared_variable_names_only_itself_and_the_config_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1-S6, FR-003: the error names `DECLARED_KEY_VAR` and the file, nothing else.

    Preserves the discipline `from_env` already kept: an error names a
    variable, never a value. And it does not offer `LITELLM_MASTER_KEY` as a
    consolation — the operator declared a variable, so the answer is about it.
    """
    config_path = _write_config(tmp_path)
    _no_overrides(monkeypatch)
    monkeypatch.delenv(DECLARED_KEY_VAR, raising=False)

    resolution = resolve_llm_gateway(config_path=config_path)

    with pytest.raises(ControlPlaneResolutionError) as excinfo:
        resolution.credential.read()

    message = str(excinfo.value)
    assert DECLARED_KEY_VAR in message
    assert str(config_path) in message
    assert MASTER_KEY_ENV not in message
    assert SENTINEL_CREDENTIAL not in message


# ---------------------------------------------------------------------------
# T007 / US1-S7 — the resolution carries a name, never a value
# ---------------------------------------------------------------------------


def test_the_resolution_never_carries_the_credential_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1-S7, FR-003, SC-005: a planted sentinel appears nowhere in the repr.

    True by construction rather than by discipline — the object holds a
    variable name and a URL — which is why this shape was chosen over returning
    a `(url, key)` pair.
    """
    config_path = _write_config(tmp_path)
    _no_overrides(monkeypatch)
    monkeypatch.setenv(DECLARED_KEY_VAR, SENTINEL_CREDENTIAL)

    resolution = resolve_llm_gateway(config_path=config_path)

    # The credential really is resolvable — a blank fixture would make this
    # assertion worthless (plan trap 6).
    assert resolution.credential.read() == SENTINEL_CREDENTIAL

    assert SENTINEL_CREDENTIAL not in repr(resolution)
    assert SENTINEL_CREDENTIAL not in repr(resolution.credential)
    assert SENTINEL_CREDENTIAL not in str(resolution)


def test_the_override_resolution_carries_the_variable_name_not_its_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same guarantee on the override branch, where the value is right there.

    `LITELLM_MASTER_KEY` is read as a *presence* test; what the resolution
    carries is the string "LITELLM_MASTER_KEY".
    """
    config_path = _write_config(tmp_path)
    monkeypatch.setenv(PROXY_URL_ENV, OVERRIDE_BASE_URL)
    monkeypatch.setenv(MASTER_KEY_ENV, SENTINEL_CREDENTIAL)

    resolution = resolve_llm_gateway(config_path=config_path)

    assert SENTINEL_CREDENTIAL not in repr(resolution)
    assert resolution.credential.read() == SENTINEL_CREDENTIAL


# ---------------------------------------------------------------------------
# T008 / US1-S8 — parity: the EpicInput this host builds does not move
# ---------------------------------------------------------------------------


class _RecordingClient:
    """Stands in for the Temporal client; records what would have been started."""

    def __init__(self) -> None:
        self.started: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def start_workflow(self, *args: Any, **kwargs: Any) -> Any:
        self.started.append((args, kwargs))
        return object()


def _start_and_capture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Drive `ergane build start` to the brink and return the `EpicInput` it built.

    No Temporal and no proxy: the seams the CLI already exposes — the
    package-level client factory and the preflight — are replaced, so what is
    measured is the input construction and nothing around it.
    """
    import factory.cli.nouns as nouns_package
    from factory.cli.nouns import build as build_module

    recorder = _RecordingClient()

    async def _open_client() -> Any:
        return recorder

    async def _no_findings(graph: Any) -> list[Any]:
        return []

    monkeypatch.setattr(nouns_package, "_open_client", _open_client)
    monkeypatch.setattr(build_module, "_run_preflight", _no_findings)

    graph_path = _write_graph(tmp_path)
    assert build_module.start_command(
        Namespace(graph=str(graph_path), max_concurrent_nodes=1)
    ) == 0
    return recorder.started[0][0][1]


def test_epic_input_is_byte_identical_under_the_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1-S8, SC-001: with both overrides exported and no config, nothing moves.

    Compared against the construction the tree performs today, through the same
    payload converter Temporal would use — so a resolver that returned a source
    label, a normalised URL or a different default fails here.
    """
    from factory.cli.nouns import build as build_module
    from factory.workgraph.workflow import EpicInput

    monkeypatch.setenv(PROXY_URL_ENV, OVERRIDE_BASE_URL)
    monkeypatch.setenv(MASTER_KEY_ENV, SENTINEL_CREDENTIAL)
    _bind_config_path(monkeypatch, tmp_path / "absent" / "config.toml")

    built = _start_and_capture(tmp_path, monkeypatch)
    expected = EpicInput(
        graph=build_module.load_workgraph(tmp_path / "workgraph.json"),
        proxy_url=OVERRIDE_BASE_URL,
        max_concurrent_nodes=1,
    )

    assert built == expected
    assert _payload_bytes(built) == _payload_bytes(expected)


def _payload_bytes(value: Any) -> bytes:
    from temporalio.converter import default as default_converter

    return default_converter().payload_converter.to_payloads([value])[0].data


# ---------------------------------------------------------------------------
# T009 / SC-004 — the control: the config branch is what changed the outcome
# ---------------------------------------------------------------------------


def test_control_with_the_config_branch_disabled_the_tree_refuses_as_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SC-004: the same fixture, one explicit seam flipped, refuses as today.

    The seam is a keyword argument, never an environment read — a control
    implemented as "unset a variable" is not a control, it is the same code
    path. With the branch off, this fixture is indistinguishable from the
    pre-048 tree: nothing in the environment, so nothing resolves.
    """
    config_path = _write_config(tmp_path)
    _no_overrides(monkeypatch)
    monkeypatch.setenv(DECLARED_KEY_VAR, SENTINEL_CREDENTIAL)

    # Treatment: the branch this story adds.
    resolved = resolve_llm_gateway(config_path=config_path)
    assert resolved.base_url == DECLARED_BASE_URL

    # Control: the identical fixture with the branch disabled.
    with pytest.raises(ControlPlaneResolutionError) as excinfo:
        resolve_llm_gateway(config_path=config_path, consult_config=False)

    message = str(excinfo.value)
    assert PROXY_URL_ENV in message
    # Nothing was read out of the file: the refusal names it as a *route* the
    # operator could take, and carries none of what it actually declares.
    assert DECLARED_BASE_URL not in message
    assert DECLARED_KEY_VAR not in message


# ---------------------------------------------------------------------------
# FR-006 — the credential half of the roadmap path resolves the same way
# ---------------------------------------------------------------------------


def test_epic_start_needs_the_endpoint_and_not_the_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A host exporting a proxy url and no master key still starts epics.

    The endpoint is a workflow *input* threaded from the CLI; the credential is
    read on the worker host by the activity that mints the key. This story's
    first full-suite run refused seven tests exporting exactly that combination,
    because the first cut of the CLI seam resolved the whole gateway.
    """
    monkeypatch.setenv(PROXY_URL_ENV, OVERRIDE_BASE_URL)
    monkeypatch.delenv(MASTER_KEY_ENV, raising=False)
    _bind_config_path(monkeypatch, tmp_path / "absent" / "config.toml")

    assert _start_and_capture(tmp_path, monkeypatch).proxy_url == OVERRIDE_BASE_URL


def test_the_endpoint_resolver_stands_alone_from_the_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same split at the resolver: an endpoint resolves with no credential anywhere."""
    from factory.controlplane.resolve import resolve_proxy_url

    config_path = _write_config(tmp_path)
    _no_overrides(monkeypatch)
    monkeypatch.delenv(DECLARED_KEY_VAR, raising=False)

    endpoint = resolve_proxy_url(config_path=config_path)

    assert endpoint.url == DECLARED_BASE_URL
    assert endpoint.source == str(config_path)


def test_the_credential_resolver_stands_alone_from_the_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_master_key_from_env` is handed its proxy url, so it resolves only the key.

    Without this, the roadmap's preflight seam — which takes `proxy_url` as an
    argument — would start demanding an endpoint it was already given.
    """
    config_path = _write_config(tmp_path)
    _no_overrides(monkeypatch)
    monkeypatch.setenv(DECLARED_KEY_VAR, SENTINEL_CREDENTIAL)

    reference = resolve_master_key_env(config_path=config_path)

    assert reference.env_name == DECLARED_KEY_VAR
    assert reference.source == str(config_path)
    assert reference.read() == SENTINEL_CREDENTIAL
    assert SENTINEL_CREDENTIAL not in repr(reference)


def test_from_env_and_the_roadmap_seam_agree_about_the_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-006: one resolver, so an epic and the roadmap cannot disagree."""
    from factory.activities import roadmap_activities
    from factory.usage.litellm_client import LiteLLMClient

    config_path = _write_config(tmp_path)
    _no_overrides(monkeypatch)
    _bind_config_path(monkeypatch, config_path)
    monkeypatch.setenv(DECLARED_KEY_VAR, SENTINEL_CREDENTIAL)

    client = LiteLLMClient.from_env()
    try:
        assert client.base_url == DECLARED_BASE_URL.rstrip("/")
    finally:
        import asyncio

        asyncio.run(client.aclose())

    assert roadmap_activities._master_key_from_env() == SENTINEL_CREDENTIAL


def test_from_env_refusal_still_names_only_variables_never_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-003: `from_env` keeps raising `LiteLLMError`, credential-free.

    The error type matters beyond tidiness: `issue_attempt_key` catches
    `LiteLLMError` and marks the failure permanent, so a new exception type
    escaping `from_env` would turn a misconfigured host into ten minutes of
    retries.
    """
    from factory.usage.litellm_client import LiteLLMError, LiteLLMClient

    missing = tmp_path / "absent" / "config.toml"
    _no_overrides(monkeypatch)
    _bind_config_path(monkeypatch, missing)

    with pytest.raises(LiteLLMError) as excinfo:
        LiteLLMClient.from_env()

    message = str(excinfo.value)
    assert PROXY_URL_ENV in message
    assert str(missing) in message


# ---------------------------------------------------------------------------
# FR-007 — resolution stays out of workflow scope
# ---------------------------------------------------------------------------


def test_no_workflow_module_imports_the_resolver() -> None:
    """FR-007, plan trap 2: workflow code may read neither the environment nor the disk.

    `tests/test_workflow_env_guard.py` catches `os.environ` at workflow scope
    and would *not* catch a config-file read, so this asserts the narrower
    property directly: no module carrying a `@workflow.defn` names the resolver
    at all. Walks the AST, so a comment cannot fail it and an alias cannot hide.
    """
    import ast

    factory_root = Path(__file__).resolve().parent.parent / "factory"
    offenders: list[str] = []

    for path in sorted(factory_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        has_workflow_defn = any(
            isinstance(node, ast.ClassDef)
            and any(
                isinstance(decorator, ast.Attribute)
                and isinstance(decorator.value, ast.Name)
                and decorator.value.id == "workflow"
                and decorator.attr == "defn"
                for decorator in node.decorator_list
            )
            for node in ast.walk(tree)
        )
        if not has_workflow_defn:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "factory.controlplane"
            ):
                offenders.append(f"{path}: from {node.module} import ...")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("factory.controlplane"):
                        offenders.append(f"{path}: import {alias.name}")

    assert offenders == []


def test_the_controlplane_package_init_stays_empty() -> None:
    """Plan trap 11: an import here closes a cycle at worker start.

    `verify.py` imports `litellm_client`, which now reaches back into
    `factory.controlplane.resolve`. Any re-export placed in this `__init__`
    makes the three a cycle, and it surfaces as an unrelated `ImportError` at
    the top of a traceback nobody connects to a package `__init__`.
    """
    init = (
        Path(__file__).resolve().parent.parent
        / "factory"
        / "controlplane"
        / "__init__.py"
    )
    assert init.read_bytes() == b""


# ===========================================================================
# Runtime evidence (constitution VIII / D-037): pasted, not described.
# ===========================================================================
#
# --- The red run, before any production code existed -----------------------
#
#   $ uv run pytest -q tests/test_declared_control_plane.py
#   ____________ ERROR collecting tests/test_declared_control_plane.py _____________
#   tests/test_declared_control_plane.py:33: in <module>
#       from factory.controlplane.resolve import (
#   E   ModuleNotFoundError: No module named 'factory.controlplane.resolve'
#   !!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
#   1 error in 0.07s
#
# A collection error is weak evidence on its own — it says the module is
# absent, not that any single assertion bites. The per-behaviour mutation
# transcripts below are the real answer to "what would make this pass if the
# production code did nothing?".
#
#
# --- Mutation testing, one mutation per behaviour --------------------------
#
# The defect pattern that has cost this repository more than any other is a
# test that cannot fail — five instances in two days, one of which seeded the
# state it then checked for, and one whose only green condition was deleting
# production data. So each behaviour below was broken on purpose in the
# production code and this file re-run. Every mutation was reverted before the
# evidence was written: `git status` was clean, so the tree these transcripts
# describe is the tree in this diff.
#
#   $ uv run pytest -q tests/test_declared_control_plane.py   # once per mutation
#
# M1  precedence inverted — the declaration beats the environment.
#     [resolve.py: drop the override short-circuit in _declared_gateway and
#     swap the branches in _resolve_endpoint and _resolve_credential]
#     3 failed, 16 passed in 0.29s
#       test_the_environment_overrides_the_declaration
#       test_overrides_set_means_the_config_file_is_never_opened
#       test_the_override_resolution_carries_the_variable_name_not_its_value
#
# M2  the declaration branch never runs — the pre-048 tree.
#     [_declared_gateway returns (None, label) unconditionally]
#     9 failed, 10 passed in 0.28s
#       test_the_declaration_supplies_both_values_when_nothing_overrides
#       test_the_declared_credential_is_read_from_the_declared_variable
#       test_a_config_the_parser_refuses_surfaces_the_parsers_own_reason
#       test_an_unset_declared_variable_names_only_itself_and_the_config_path
#       test_the_resolution_never_carries_the_credential_value
#       test_control_with_the_config_branch_disabled_the_tree_refuses_as_before
#       test_the_endpoint_resolver_stands_alone_from_the_credential
#       test_the_credential_resolver_stands_alone_from_the_endpoint
#       test_from_env_and_the_roadmap_seam_agree_about_the_host
#
# M3  sources always name the legacy variable, never the config path.
#     [the declared branches return PROXY_URL_ENV / MASTER_KEY_ENV as source]
#     4 failed, 15 passed in 0.23s
#       test_the_declaration_supplies_both_values_when_nothing_overrides
#       test_an_unset_declared_variable_names_only_itself_and_the_config_path
#       test_the_endpoint_resolver_stands_alone_from_the_credential
#       test_the_credential_resolver_stands_alone_from_the_endpoint
#
# M4  CredentialRef carries the credential value as well as its name.
#     [add a `value` field, populated from the environment]
#     1 failed, 18 passed in 0.22s
#       test_the_credential_resolver_stands_alone_from_the_endpoint
#
# M4b GatewayResolution carries the credential value alongside the name.
#     [add `master_key_value`, populated in resolve_llm_gateway]
#     2 failed, 17 passed in 0.22s
#       test_the_resolution_never_carries_the_credential_value
#       test_the_override_resolution_carries_the_variable_name_not_its_value
#     Needed as a separate mutation, and the reason is worth recording: under
#     M4 alone both sentinel assertions on `resolution` still passed, because
#     GatewayResolution is built from the CredentialRef's two *name* fields and
#     drops everything else. That is a real structural guarantee, and it is
#     also what made M4 insufficient evidence for US1-S7.
#
# M5  a config the parser refuses is swallowed (the registry.py reflex).
#     [_declared_gateway returns (None, label) on ControlPlaneConfigError]
#     1 failed, 18 passed in 0.22s
#       test_a_config_the_parser_refuses_surfaces_the_parsers_own_reason
#
# M6  the refusal names one route instead of both.
#     [_both_routes returns "<VAR> is not set in the worker environment"]
#     3 failed, 16 passed in 0.21s
#       test_epic_start_with_nothing_declared_names_both_routes
#       test_a_missing_config_is_not_reported_as_a_broken_one
#       test_from_env_refusal_still_names_only_variables_never_values
#
# M7  the config file is read even when both overrides are set.
#     [drop only the `needed` short-circuit in _declared_gateway]
#     1 failed, 18 passed in 0.22s
#       test_overrides_set_means_the_config_file_is_never_opened
#
# M8  epic start threads the resolved *source* instead of the resolved url.
#     [build.py: resolve_proxy_url().source]
#     2 failed, 17 passed in 0.21s
#       test_epic_input_is_byte_identical_under_the_overrides
#       test_epic_start_needs_the_endpoint_and_not_the_credential
#
# M9  epic start re-fuses the two halves and demands the credential too.
#     [build.py: resolve_llm_gateway().base_url]
#     1 failed, 18 passed in 0.24s
#       test_epic_start_needs_the_endpoint_and_not_the_credential
#
# M10 a workflow module imports the resolver.
#     [workflow.py: import factory.controlplane.resolve]
#     1 failed, 18 passed in 0.21s
#       test_no_workflow_module_imports_the_resolver
#
# M11 factory/controlplane/__init__.py stops being empty.
#     [one comment line written into it]
#     1 failed, 18 passed in 0.21s
#       test_the_controlplane_package_init_stays_empty
#
# Every one of the nineteen tests in this file is killed by at least one
# mutation above. The one deliberately hard to kill is
# test_epic_input_is_byte_identical_under_the_overrides: it is a parity pin
# (US1-S8 / SC-001), so a correct change must leave it green — M8 is the proof
# that it is nonetheless able to fail.
#
#
# --- The full suite, on the tree in this diff -------------------------------
#
#   $ uv run pytest -q
#   2772 passed, 44 skipped, 5 warnings in 290.75s (0:04:50)
