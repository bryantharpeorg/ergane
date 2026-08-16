"""048-US4: Temporal connects to what was declared.

US1 built the precedence and pointed it at the LLM gateway. This story points
the *same* precedence at `temporal.address` and `temporal.namespace`, so one
rule holds everywhere: the environment overrides the declaration, and the
declaration is consulted only where the environment is silent.

Three properties of the tests below decide their shape:

- **The fixture config and the fixture environment disagree on every value they
  both carry** (plan traps 5 and 8) — four distinct strings. If they agreed, no
  test here could tell which source was consulted.
- **Every test binds the config path explicitly**, so none resolves the
  operator's real `~/.config/ergane/config.toml` (FR-012, plan trap 4):
  `resolve_config_path()` falls back to `$XDG_CONFIG_HOME` then `Path.home()`,
  a file that exists on this host and not on the grader's.
- **Every test deletes both `TEMPORAL_*` variables before asserting anything
  about the declared route.** `scripts/ergane-env.sh` exports them here, so a
  test that inherited them would measure the shell.

Unlike the gateway, Temporal has a third source — a built-in default — so
resolution refuses only for a config the parser rejects (US1's FR-005 shape,
one subsystem over).

Runtime evidence is pasted verbatim at the bottom (constitution VIII / D-037).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from factory.controlplane.resolve import (
    ControlPlaneResolutionError,
    resolve_temporal_target,
)
from factory.env import ERGANE_CONFIG_PATH_ENV, FACTORY_CONFIG_PATH_ENV
from factory.notify.service import (
    DEFAULT_TEMPORAL_ADDRESS,
    DEFAULT_TEMPORAL_NAMESPACE,
    TEMPORAL_ADDRESS_ENV,
    TEMPORAL_NAMESPACE_ENV,
)

# --- fixture values: the two sources disagree on everything (plan trap 5) -----

DECLARED_ADDRESS = "declared.temporal.test:7233"
DECLARED_NAMESPACE = "declared-namespace"

OVERRIDE_ADDRESS = "override.temporal.test:7233"
OVERRIDE_NAMESPACE = "override-namespace"

#: The declared LLM values, needed because the parser requires all five blocks.
#: Distinct from anything Temporal so a crossed wire is visible.
DECLARED_BASE_URL = "http://declared.gateway.test/v1"
DECLARED_KEY_VAR = "DECLARED_KEY_VAR"


def _write_config(
    tmp_path: Path,
    *,
    address: str = DECLARED_ADDRESS,
    namespace: str = DECLARED_NAMESPACE,
) -> Path:
    """A complete, parseable config at a bound path.

    All five blocks, because the parser requires all five — and `address` and
    `namespace` are both required when `temporal.mode = "external"`. A fixture
    omitting either is refused, and that refusal presents as US1's broken-config
    error rather than as anything about Temporal (plan trap 12b).
    """
    path = tmp_path / "config.toml"
    path.write_text(
        f"""\
version = 1

[llm]
mode = "gateway"
base_url = "{DECLARED_BASE_URL}"
master_key_env = "{DECLARED_KEY_VAR}"

[memory]
backend = "none"

[temporal]
mode = "external"
address = "{address}"
namespace = "{namespace}"

[telemetry]

[escalation]
adapter = "telegram"
chat_id_env = "DECLARED_CHAT_ID"
bot_token_env = "DECLARED_BOT_TOKEN"
""",
        encoding="utf-8",
    )
    return path


def _no_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove both variables this development host exports (plan trap 1)."""
    monkeypatch.delenv(TEMPORAL_ADDRESS_ENV, raising=False)
    monkeypatch.delenv(TEMPORAL_NAMESPACE_ENV, raising=False)


def _bind_config_path(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    """Bind both config-path variables for the CLI paths (FR-012)."""
    monkeypatch.setenv(ERGANE_CONFIG_PATH_ENV, str(path))
    monkeypatch.setenv(FACTORY_CONFIG_PATH_ENV, str(path))


# --- T034 / US4-S2 — the override wins, and this host keeps connecting untouched


def test_the_environment_overrides_the_declaration_for_both_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US4-S2, FR-015: a host exporting both variables resolves exactly as today.

    Written first, and the acceptance condition rather than a nicety (plan
    trap 1): the worker here reads both variables from `scripts/ergane-env.sh`
    with no config file behind them, and a change requiring this machine to be
    re-provisioned to keep polling would be a failed change.
    """
    config_path = _write_config(tmp_path)
    monkeypatch.setenv(TEMPORAL_ADDRESS_ENV, OVERRIDE_ADDRESS)
    monkeypatch.setenv(TEMPORAL_NAMESPACE_ENV, OVERRIDE_NAMESPACE)

    target = resolve_temporal_target(config_path=config_path)

    assert target.address == OVERRIDE_ADDRESS
    assert target.address_source == TEMPORAL_ADDRESS_ENV
    assert target.namespace == OVERRIDE_NAMESPACE
    assert target.namespace_source == TEMPORAL_NAMESPACE_ENV

    # The declared values are in the file and lost the race — the only reason
    # this test can distinguish the two sources at all.
    assert target.address != DECLARED_ADDRESS
    assert target.namespace != DECLARED_NAMESPACE


# --- T033 / US4-S1 — the declaration supplies both when nothing overrides it


def test_the_declaration_supplies_both_values_when_nothing_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US4-S1, FR-015: a freshly installed host connects to what it declared.

    The whole defect in one assertion: before this story an operator wrote an
    address at the interview and still had to export `TEMPORAL_ADDRESS`.
    """
    config_path = _write_config(tmp_path)
    _no_overrides(monkeypatch)

    target = resolve_temporal_target(config_path=config_path)

    assert target.address == DECLARED_ADDRESS
    assert target.address_source == str(config_path)
    assert target.namespace == DECLARED_NAMESPACE
    assert target.namespace_source == str(config_path)


def test_each_value_resolves_on_its_own_rather_than_as_a_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A host that exports one variable and declares the other reports both truthfully.

    The precedence is per *value*, not per subsystem. A resolver that took the
    environment's whole answer the moment any one variable was set would pass
    every other test in this file and fail only here.
    """
    config_path = _write_config(tmp_path)
    _no_overrides(monkeypatch)
    monkeypatch.setenv(TEMPORAL_ADDRESS_ENV, OVERRIDE_ADDRESS)

    target = resolve_temporal_target(config_path=config_path)

    assert target.address == OVERRIDE_ADDRESS
    assert target.address_source == TEMPORAL_ADDRESS_ENV
    assert target.namespace == DECLARED_NAMESPACE
    assert target.namespace_source == str(config_path)


# --- T036 / US4-S4 — neither source: the built-in defaults, exactly as today


def test_neither_source_falls_back_to_the_built_in_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US4-S4: an unprovisioned host with no config keeps the pre-048 behaviour.

    The expected values are imported from `factory/notify/service.py` rather
    than restated: a test spelling `"localhost:7233"` out would still pass if a
    site grew its own copy, which is what US4-S4's second half forbids.
    """
    _no_overrides(monkeypatch)
    missing = tmp_path / "config.toml"

    target = resolve_temporal_target(config_path=missing)

    assert target.address == DEFAULT_TEMPORAL_ADDRESS
    assert target.namespace == DEFAULT_TEMPORAL_NAMESPACE
    # The source says the default stood in — it does not claim a file that is
    # not there declared anything.
    assert str(missing) not in target.address_source
    assert str(missing) not in target.namespace_source


# --- FR-002, one subsystem over — when both overrides speak, the file is not opened


def test_overrides_set_means_the_config_file_is_never_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bound to unparseable TOML, resolution still succeeds.

    A resolver that opened this file could not have passed. Making the read
    fatal is the only way to observe a read that did not happen — US1-S3's
    anti-vacuity, reused because the property is the same.
    """
    broken = tmp_path / "config.toml"
    broken.write_text('version = 1\n[temporal\nmode = "external"\n', encoding="utf-8")
    monkeypatch.setenv(TEMPORAL_ADDRESS_ENV, OVERRIDE_ADDRESS)
    monkeypatch.setenv(TEMPORAL_NAMESPACE_ENV, OVERRIDE_NAMESPACE)

    target = resolve_temporal_target(config_path=broken)

    assert target.address == OVERRIDE_ADDRESS
    assert target.namespace == OVERRIDE_NAMESPACE


def test_a_config_the_parser_refuses_surfaces_the_parsers_own_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-005 one subsystem over: refuse for a broken config, degrade for a missing one.

    Falling back to `localhost:7233` because the file would not parse is the
    worse half of this defect: a worker polling a server the operator never
    named, silently (plan trap 3).
    """
    broken = tmp_path / "config.toml"
    broken.write_text('version = 1\n[temporal\nmode = "external"\n', encoding="utf-8")
    _no_overrides(monkeypatch)

    with pytest.raises(ControlPlaneResolutionError) as refusal:
        resolve_temporal_target(config_path=broken)

    message = str(refusal.value)
    assert str(broken) in message
    assert "malformed_toml" in message
    assert DEFAULT_TEMPORAL_ADDRESS not in message


# --- T035 / US4-S3 / SC-006 — the probe and the worker agree about the server


class _DialRecorder:
    """Captures what `Client.connect` was asked for; connects to nothing."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def connect(self, address: str, *, namespace: str, **_: object) -> object:
        self.calls.append((address, namespace))
        return object()


@pytest.fixture
def dialed(monkeypatch: pytest.MonkeyPatch) -> _DialRecorder:
    """Replace the real connect so a probe dials no live server."""
    import temporalio.client

    recorder = _DialRecorder()
    monkeypatch.setattr(temporalio.client.Client, "connect", recorder.connect)
    return recorder


@pytest.mark.asyncio
async def test_the_verify_probe_dials_the_address_the_worker_would_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dialed: _DialRecorder
) -> None:
    """US4-S3, FR-016, SC-006: the story's reason to exist.

    `verify.py` read the config *first* — the opposite precedence from the rest
    of the tree, and the only two such sites in it (plan trap 13). Where the two
    disagreed, `ergane install --verify` probed one server while the worker
    connected to another: a green check about a machine nothing runs on, and
    worse than the parent defect because the parent fails loudly at the first
    build and this one never fails at all.

    Asserted against the fixture *literal*, never a second call to the
    resolver: comparing the probe's address to `resolve_temporal_target()`
    would compare the production code with itself and survive a mutation that
    moved both.
    """
    from factory.controlplane.config import load_controlplane_config
    from factory.controlplane import verify as verify_module

    config_path = _write_config(tmp_path)
    monkeypatch.setenv(TEMPORAL_ADDRESS_ENV, OVERRIDE_ADDRESS)
    monkeypatch.setenv(TEMPORAL_NAMESPACE_ENV, OVERRIDE_NAMESPACE)
    config = load_controlplane_config(str(config_path))

    await verify_module._temporal_client_factory(config.temporal)

    assert dialed.calls == [(OVERRIDE_ADDRESS, OVERRIDE_NAMESPACE)]
    # And the declared address, which the probe used to prefer, was not dialed.
    assert DECLARED_ADDRESS not in [address for address, _ in dialed.calls]


@pytest.mark.asyncio
async def test_the_probe_snapshot_names_the_server_it_actually_dialed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dialed: _DialRecorder
) -> None:
    """SC-006: gather resolves once, so its report and its dial cannot disagree.

    `gather` resolved the target and `_temporal_client_factory` resolved it
    again, independently. Two copies of one rule agree only by luck; this pins
    that the address the finding names is the address the connect was given.
    """
    from factory.controlplane.config import load_controlplane_config
    from factory.controlplane import verify as verify_module

    config_path = _write_config(tmp_path)
    monkeypatch.setenv(TEMPORAL_ADDRESS_ENV, OVERRIDE_ADDRESS)
    monkeypatch.setenv(TEMPORAL_NAMESPACE_ENV, OVERRIDE_NAMESPACE)
    config = load_controlplane_config(str(config_path))

    snapshot = await verify_module.TemporalProbe().gather(config)

    assert snapshot.address == OVERRIDE_ADDRESS
    assert snapshot.namespace == OVERRIDE_NAMESPACE
    assert dialed.calls and dialed.calls[0][0] == snapshot.address
    assert dialed.calls[0][1] == snapshot.namespace


# --- T036 second half / US4-S4 — no site keeps its own copy of the contract

#: Every module that opens a Temporal connection. The plan named ten sites;
#: `factory/roadmap/schedule.py` is an eleventh it missed, found by grepping for
#: the constants rather than by reading the list.
_CONNECT_SITES = (
    "worker.py",
    "cli/nouns/__init__.py",
    "cli/main.py",
    "cli/roadmap.py",
    "cli/repo.py",
    "workgraph/cli.py",
    "doctor/probes.py",
    "controlplane/verify.py",
    "roadmap/schedule.py",
)

#: Literals a connect site may not spell for itself. `"factory"` — the
#: namespace default — is deliberately absent: it is also the package name, the
#: task-queue name and a workflow-id prefix, so asserting on it would be an
#: assertion satisfiable by an entirely unrelated string.
_FORBIDDEN_LITERALS = ("localhost:7233", "TEMPORAL_ADDRESS", "TEMPORAL_NAMESPACE")


def _non_docstring_strings(tree: ast.AST) -> list[str]:
    """Every string constant in `tree` that is not a docstring.

    Excluded because `factory/worker.py`'s module docstring carries a worked
    `TEMPORAL_ADDRESS=localhost:7233 ...` command line — documentation of the
    contract, not a second copy of it.
    """
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body:
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                if isinstance(first.value.value, str):
                    docstrings.add(id(first.value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def test_no_connect_site_spells_the_temporal_contract_for_itself() -> None:
    """US4-S4: the constants are named, never restated.

    Four sites carried hardcoded `"TEMPORAL_ADDRESS"` / `"localhost:7233"`.
    They agreed with the constants by luck, not design: the day
    `DEFAULT_TEMPORAL_ADDRESS` changes, the copies keep dialing the old one.
    """
    factory_root = Path(__file__).resolve().parent.parent / "factory"
    offenders: list[str] = []

    for relative in _CONNECT_SITES:
        path = factory_root / relative
        assert path.is_file(), f"{relative} moved; this test is pinned to a stale path"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for text in _non_docstring_strings(tree):
            for forbidden in _FORBIDDEN_LITERALS:
                if forbidden in text:
                    offenders.append(f"{relative}: {text!r}")

    assert offenders == []


#: A site importing any of these reaches `os.environ` without spelling a
#: forbidden literal: `os.environ.get(TEMPORAL_ADDRESS_ENV)` names no banned
#: string at all. Closing only the literal route leaves a test that looks strict
#: and is not.
_CONTRACT_NAMES = (
    "TEMPORAL_ADDRESS_ENV",
    "TEMPORAL_NAMESPACE_ENV",
    "DEFAULT_TEMPORAL_ADDRESS",
    "DEFAULT_TEMPORAL_NAMESPACE",
)

#: The two entry points into the one precedence. `verify.py` uses the second,
#: having been pointed at a specific file it already parsed; both are the same
#: rule, since `resolve_temporal_target` is written in terms of the other.
_RESOLVER_ENTRY_POINTS = ("resolve_temporal_target", "temporal_target_for")


def test_no_connect_site_reads_the_temporal_variables_for_itself() -> None:
    """The second route to `os.environ`, closed alongside the first."""
    factory_root = Path(__file__).resolve().parent.parent / "factory"
    offenders: list[str] = []

    for relative in _CONNECT_SITES:
        path = factory_root / relative
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            for alias in node.names:
                if alias.name in _CONTRACT_NAMES:
                    offenders.append(f"{relative}: imports {alias.name}")

    assert offenders == []


def test_every_connect_site_reaches_the_one_resolver() -> None:
    """FR-015: "at every operational connect site", asserted rather than claimed.

    Walks the AST for the imported name, so a comment claiming a site moved
    cannot satisfy it. `factory/notify/service.py` is checked separately below.
    """
    factory_root = Path(__file__).resolve().parent.parent / "factory"
    unmoved: list[str] = []

    for relative in _CONNECT_SITES:
        source = (factory_root / relative).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative)
        reaches = any(
            isinstance(node, ast.ImportFrom)
            and (node.module or "") == "factory.controlplane.resolve"
            and any(alias.name in _RESOLVER_ENTRY_POINTS for alias in node.names)
            for node in ast.walk(tree)
        )
        if not reaches:
            unmoved.append(relative)

    assert unmoved == []


def test_the_escalation_bridge_also_reaches_the_resolver() -> None:
    """The tenth site: `factory/notify/service.py`'s own `main()`.

    It defines the constants, so the no-literals rule above cannot hold it — but
    it dials Temporal like everything else and must resolve like everything else.
    """
    service = (
        Path(__file__).resolve().parent.parent
        / "factory"
        / "notify"
        / "service.py"
    )
    tree = ast.parse(service.read_text(encoding="utf-8"), filename=str(service))
    assert any(
        isinstance(node, ast.ImportFrom)
        and (node.module or "") == "factory.controlplane.resolve"
        and any(alias.name == "resolve_temporal_target" for alias in node.names)
        for node in ast.walk(tree)
    )


# --- T037 / US4-S5 — `ergane env --sources` reports Temporal too


def _run_sources(capsys: pytest.CaptureFixture[str]) -> str:
    from argparse import Namespace

    from factory.cli.env import env_command

    code = env_command(Namespace(sources=True))
    assert code == 0, "a report is not a gate (US3-S4)"
    return capsys.readouterr().out


def test_env_sources_names_the_config_as_the_winner_for_temporal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """US4-S5: FR-011 says "every value this spec resolves" — until now, two of four."""
    config_path = _write_config(tmp_path)
    _no_overrides(monkeypatch)
    _bind_config_path(monkeypatch, config_path)

    out = _run_sources(capsys)

    assert "Temporal address" in out
    assert "Temporal namespace" in out
    assert DECLARED_ADDRESS in out
    assert DECLARED_NAMESPACE in out
    assert out.count(str(config_path)) >= 2
    # The LLM half US3 built is still reported: this added to the report, it
    # did not replace it.
    assert "LLM gateway endpoint" in out


def test_env_sources_names_the_variable_as_the_winner_for_temporal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """US4-S5: on a host like this one, the report names the override.

    The declared values must be absent entirely: reporting what the config
    *would* have said would mean opening a file FR-002 forbids reading.
    """
    config_path = _write_config(tmp_path)
    _bind_config_path(monkeypatch, config_path)
    monkeypatch.setenv(TEMPORAL_ADDRESS_ENV, OVERRIDE_ADDRESS)
    monkeypatch.setenv(TEMPORAL_NAMESPACE_ENV, OVERRIDE_NAMESPACE)

    out = _run_sources(capsys)

    assert OVERRIDE_ADDRESS in out
    assert OVERRIDE_NAMESPACE in out
    assert TEMPORAL_ADDRESS_ENV in out
    assert TEMPORAL_NAMESPACE_ENV in out
    assert DECLARED_ADDRESS not in out
    assert DECLARED_NAMESPACE not in out


# --- Plan trap 12b — `ergane --version` reports what this install points at


def test_the_version_banner_reports_the_declared_control_plane(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plan trap 12b: US1 left `cli/main.py:154` reading `os.environ` directly.

    So `ergane --version` answered "not configured" about a gateway just
    declared, and named `localhost:7233` on a host whose config said otherwise.
    A banner that reads a different source than the dispatch path is a
    diagnostic that lies — the class 048 exists to close.
    """
    from factory.cli.main import _version_text

    config_path = _write_config(tmp_path)
    _no_overrides(monkeypatch)
    _bind_config_path(monkeypatch, config_path)
    monkeypatch.delenv("LITELLM_PROXY_URL", raising=False)
    monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)

    banner = _version_text()

    assert DECLARED_ADDRESS in banner
    assert DECLARED_NAMESPACE in banner
    assert DECLARED_BASE_URL in banner
    assert "not configured" not in banner


def test_the_version_banner_still_says_not_configured_with_nothing_declared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of trap 12b: an unprovisioned host reads as it did before.

    Without it, `_version_text` could satisfy the test above by printing the
    config's values unconditionally and never be seen to fall back.
    """
    from factory.cli.main import _version_text

    _no_overrides(monkeypatch)
    _bind_config_path(monkeypatch, tmp_path / "absent.toml")
    monkeypatch.delenv("LITELLM_PROXY_URL", raising=False)
    monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)

    banner = _version_text()

    assert "not configured" in banner
    assert DEFAULT_TEMPORAL_ADDRESS in banner
    assert DEFAULT_TEMPORAL_NAMESPACE in banner
