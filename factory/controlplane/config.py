"""Control-plane configuration parser for Ergane (033-US1).

One file — ``~/.config/ergane/config.toml`` by default, overridable via
``ERGANE_CONFIG_PATH`` / ``FACTORY_CONFIG_PATH`` — declares the five subsystems.
This module reads it with ``tomllib``, parses it to a frozen typed shape, and
refuses every violation with the ``FactoryConfigError`` grammar the manifest
parser already established: stable rule slug, offending value ``repr``-rendered,
source file named.

The parser is deliberately pure I/O-free logic over a path; path resolution is a
thin helper so that commands needing the control plane inherit the same
fail-closed message (FR-013).
"""

from __future__ import annotations

import dataclasses
import os
import re
import tomllib
from pathlib import Path
from typing import Any, Mapping

from factory.env import (
    ERGANE_CONFIG_PATH_ENV,
    FACTORY_CONFIG_PATH_ENV,
    resolve_env_path,
)

#: Allowed values for llm.mode (FR-004).  "direct" is recognized as a token but
#: refused: dispatch has exactly one credential primitive, a LiteLLM virtual key
#: minted per attempt, and a per-persona provider endpoint has none (048-US2,
#: D-048).  It stays listed so the refusal can be specific rather than "unknown
#: mode" — the same shape as "managed" below.
KNOWN_LL_MODES = ("gateway", "direct")

#: Allowed built-in memory backends (FR-004).  Custom adapters are admitted by
#: name if registered; these two are always available.
KNOWN_MEMORY_BACKENDS = ("hindsight", "none")

#: Allowed temporal modes (FR-004).  "managed" is recognized as a token but
#: refused until 042 lands.
KNOWN_TEMPORAL_MODES = ("external", "managed")

#: Adapters registered for escalation (FR-004).  Telegram is the reference
#: transport from 008; `webhook` is 041-US4's universal glue — an outbound POST
#: to a URL the operator owns, answered with `ergane answer` — so Signal, Slack,
#: email or a wall display is a bridge the operator writes rather than a
#: transport ergane has to know about.  Kept in step with
#: `factory.notify.adapter`'s registry by
#: `tests/test_messenger_adapter.py::test_the_conformance_suite_covers_every_adapter_that_ships`,
#: in both directions: a name here with nothing registered under it pages
#: nobody, and a registered name missing here is not selectable.
KNOWN_ESC_ADAPTERS = ("telegram", "webhook")

#: Default relative path under XDG_CONFIG_HOME / HOME (FR-001).
DEFAULT_CONFIG_REL = Path("ergane") / "config.toml"

#: Stable rule slugs used in ``ControlPlaneConfigError.rule``.
RULE_VERSION = "version"
RULE_UNKNOWN_KEY = "unknown_key"
RULE_UNKNOWN_LLM_MODE = "unknown_llm_mode"
RULE_LLM_DIRECT_NOT_SUPPORTED = "llm_direct_not_supported"
RULE_UNKNOWN_MEMORY_BACKEND = "unknown_memory_backend"
RULE_UNKNOWN_TEMPORAL_MODE = "unknown_temporal_mode"
RULE_TEMPORAL_MANAGED_NOT_IMPLEMENTED = "temporal_managed_not_implemented"
RULE_TEMPORAL_NAMESPACE_NOT_SCALAR = "temporal_namespace_not_scalar"
RULE_UNKNOWN_ESCALATION_ADAPTER = "unknown_escalation_adapter"
RULE_SECRET_VALUE_NOT_REFERENCE = "secret_value_not_reference"
RULE_CONFIG_MISSING = "config_missing"
RULE_MALFORMED_TOML = "malformed_toml"
RULE_MISSING_REQUIRED = "missing_required"
RULE_FIELD_TYPE = "field_type"

#: Secret shapes the parser refuses (FR-003).  A value matching any of these is
#: treated as a credential, not an env-var name.
_SECRET_PATTERNS = (
    re.compile(r"^sk-"),  # OpenAI / LiteLLM key shape
    re.compile(r"^\d+:[A-Za-z0-9_-]+$"),  # Telegram bot token shape
)

#: Fields whose names end with this suffix must be env-var references (FR-003).
_SECRET_FIELD_SUFFIX = "_env"


class ControlPlaneConfigError(ValueError):
    """A config that cannot be trusted, rendered in the manifest-parser grammar.

    ``rule`` is the stable slug tests and callers branch on.  ``problem`` is the
    human-readable sentence, with the offending value repr-rendered.  ``source``
    names the file to fix.  ``field`` optionally names the exact key within the
    file.
    """

    def __init__(
        self,
        rule: str,
        problem: str,
        *,
        source: str,
        field: str | None = None,
    ) -> None:
        super().__init__(f"{source}: [{rule}] {problem}")
        self.rule = rule
        self.problem = problem
        self.source = source
        self.field = field


@dataclasses.dataclass(frozen=True)
class ControlPlaneConfig:
    """Typed parse of ``config.toml``: five mode-discriminated subsystems."""

    version: int
    llm: "ControlPlaneConfig.LLM"
    memory: "ControlPlaneConfig.Memory"
    temporal: "ControlPlaneConfig.Temporal"
    telemetry: "ControlPlaneConfig.Telemetry"
    escalation: "ControlPlaneConfig.Escalation"

    @dataclasses.dataclass(frozen=True)
    class LLMGateway:
        """``gateway`` mode: a LiteLLM-shaped proxy."""

        base_url: str
        master_key_env: str
        timeout_s: int = 300

    @dataclasses.dataclass(frozen=True)
    class LLM:
        """Mode-discriminated LLM block: one mode reaches this shape, `gateway`."""

        mode: str
        gateway: "ControlPlaneConfig.LLMGateway | None" = None
        timeout_s: int = 300

    @dataclasses.dataclass(frozen=True)
    class Memory:
        """Memory backend choice."""

        backend: str
        url: str | None = None
        api_key_env: str | None = None
        timeout_s: int = 5

    @dataclasses.dataclass(frozen=True)
    class Temporal:
        """Temporal orchestration block."""

        mode: str
        address: str | None = None
        namespace: str | None = None
        api_key_env: str | None = None
        tls_enabled: bool = False
        timeout_s: int = 5

    @dataclasses.dataclass(frozen=True)
    class Telemetry:
        """Telemetry block: OTLP or none."""

        mode: str
        otlp_endpoint: str | None = None
        timeout_s: int = 5

    @dataclasses.dataclass(frozen=True)
    class Escalation:
        """Escalation transport block.

        ``authorized_responders`` is the identity list an inbound reply must
        match to become an answer (041 FR-011).  Empty means unrestricted, which
        is what every 008 deployment is: Telegram never had an identity problem
        because a single chat *was* the identity, and a default that refused
        every reply would take the operator channel down on the day the second
        adapter shipped.  Declaring an empty list is refused rather than read as
        unrestricted — an operator who typed one meant to restrict something.

        The list is compared against, never resolved: the check is factory-side
        (`factory.notify.service.CallbackBridge`), because an adapter deciding
        whether a sender may answer is the one decision the messenger seam
        exists to keep out of the transport.
        """

        adapter: str
        chat_id_env: str | None = None
        bot_token_env: str | None = None
        timeout_s: int = 30
        authorized_responders: tuple[str, ...] = ()


def resolve_config_path() -> Path:
    """Return the config path: env override, then XDG_CONFIG_HOME, then HOME.

    Follows the 040 rename convention via ``resolve_env_path``: the modern
    ``ERGANE_CONFIG_PATH`` wins, the legacy ``FACTORY_CONFIG_PATH`` is honored
    with one deprecation warning per process, and the default falls back to
    ``~/.config/ergane/config.toml`` (FR-001).
    """
    default = _xdg_config_home() / DEFAULT_CONFIG_REL
    return resolve_env_path(
        ERGANE_CONFIG_PATH_ENV,
        FACTORY_CONFIG_PATH_ENV,
        default,
    )


def _xdg_config_home() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)
    return Path.home() / ".config"


def load_controlplane_config(source: str | Path | None = None) -> ControlPlaneConfig:
    """Read and parse the control-plane config at ``source``.

    If ``source`` is ``None`` the resolved default path is used.  Every failure
    leaves as a ``ControlPlaneConfigError`` with a stable rule slug, so callers
    can render one clear message (FR-013).
    """
    path = Path(source) if source is not None else resolve_config_path()
    label = str(path)

    try:
        raw = path.read_bytes()
    except FileNotFoundError as error:
        raise ControlPlaneConfigError(
            RULE_CONFIG_MISSING,
            f"cannot be read ({error.strerror or 'No such file or directory'}); "
            "run `ergane install` to create the control-plane config",
            source=label,
        ) from None
    except OSError as error:
        # Permissions or other filesystem problems fail closed naming the path.
        raise ControlPlaneConfigError(
            RULE_CONFIG_MISSING,
            f"cannot be read ({error.strerror or error}); "
            "run `ergane install` to repair the control-plane config",
            source=label,
        ) from None

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ControlPlaneConfigError(
            RULE_MALFORMED_TOML,
            f"is not valid UTF-8 ({error.reason} at byte {error.start})",
            source=label,
        ) from None

    return parse_controlplane_config(text, source=label)


def parse_controlplane_config(
    text: str, *, source: str = "config.toml"
) -> ControlPlaneConfig:
    """Parse a config document and return a typed ``ControlPlaneConfig``.

    Raises ``ControlPlaneConfigError`` on the first rule violated; a config is
    usable as a whole or not at all (FR-002).
    """
    document = _load_mapping(text, source)

    _reject_unknown_top_level_keys(document, source)
    version = _read_version(document, source)

    llm = _read_llm(document, source)
    memory = _read_memory(document, source)
    temporal = _read_temporal(document, source)
    telemetry = _read_telemetry(document, source)
    escalation = _read_escalation(document, source)

    return ControlPlaneConfig(
        version=version,
        llm=llm,
        memory=memory,
        temporal=temporal,
        telemetry=telemetry,
        escalation=escalation,
    )


def _load_mapping(text: str, source: str) -> Mapping[str, Any]:
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ControlPlaneConfigError(
            RULE_MALFORMED_TOML,
            f"is not parseable TOML: {_one_line(error)}",
            source=source,
        ) from None

    if not isinstance(document, Mapping):
        raise ControlPlaneConfigError(
            RULE_MALFORMED_TOML,
            f"must be a mapping of keys to values, not {_kind(document)}",
            source=source,
        )
    return document


_TOP_LEVEL_KEYS = {"version", "llm", "memory", "temporal", "telemetry", "escalation"}


def _reject_unknown_top_level_keys(document: Mapping[str, Any], source: str) -> None:
    unknown = sorted(set(document) - _TOP_LEVEL_KEYS)
    if unknown:
        raise ControlPlaneConfigError(
            RULE_UNKNOWN_KEY,
            f"declares {_names(unknown)} at the top level; "
            f"config schema knows only {_names(sorted(_TOP_LEVEL_KEYS))}",
            source=source,
        )


def _read_version(document: Mapping[str, Any], source: str) -> int:
    if "version" not in document:
        raise ControlPlaneConfigError(
            RULE_VERSION,
            "declares no `version`; schema requires the integer literal `version = 1`",
            source=source,
        )
    version = document["version"]
    if type(version) is not int or version != 1:
        raise ControlPlaneConfigError(
            RULE_VERSION,
            f"declares `version = {version!r}`; this factory supports only the "
            "integer literal 1",
            source=source,
        )
    return version


def _read_llm(document: Mapping[str, Any], source: str) -> ControlPlaneConfig.LLM:
    block = _expect_block(document, "llm", source)
    mode = _require_string(block, "llm.mode", source)

    if mode not in KNOWN_LL_MODES:
        raise ControlPlaneConfigError(
            RULE_UNKNOWN_LLM_MODE,
            f"declares `llm.mode = {mode!r}`; supported modes are {_names(KNOWN_LL_MODES)}",
            source=source,
        )

    if mode == "direct":
        raise ControlPlaneConfigError(
            RULE_LLM_DIRECT_NOT_SUPPORTED,
            '`llm.mode = "direct"` cannot be dispatched against: every attempt '
            "runs on its own model-constrained, TTL'd virtual key minted at the "
            "LiteLLM proxy, and a per-persona provider endpoint has no such key "
            "to mint, revoke or attribute. Put a LiteLLM-shaped gateway in front "
            'of the provider and declare `llm.mode = "gateway"`',
            source=source,
            field="llm.mode",
        )

    # gateway mode
    base_url = _require_string(block, "llm.base_url", source)
    master_key_env = _require_secret_ref(block, "master_key_env", source)
    return ControlPlaneConfig.LLM(
        mode="gateway",
        gateway=ControlPlaneConfig.LLMGateway(
            base_url=base_url,
            master_key_env=master_key_env,
        ),
    )


def _read_memory(
    document: Mapping[str, Any], source: str
) -> ControlPlaneConfig.Memory:
    block = _expect_block(document, "memory", source)
    backend = _require_string(block, "memory.backend", source)

    if backend not in KNOWN_MEMORY_BACKENDS:
        raise ControlPlaneConfigError(
            RULE_UNKNOWN_MEMORY_BACKEND,
            f"declares `memory.backend = {backend!r}`; supported backends are "
            f"{_names(KNOWN_MEMORY_BACKENDS)} plus any registered adapter name",
            source=source,
        )

    url = _optional_string(block.get("url"))
    api_key_env = _optional_secret_ref(block.get("api_key_env"), "memory.api_key_env", source)
    timeout_s = block.get("timeout_s", 5)
    _expect_int(timeout_s, "memory.timeout_s", source)
    return ControlPlaneConfig.Memory(
        backend=backend,
        url=url,
        api_key_env=api_key_env,
        timeout_s=int(timeout_s),
    )


def _read_temporal(
    document: Mapping[str, Any], source: str
) -> ControlPlaneConfig.Temporal:
    block = _expect_block(document, "temporal", source)
    mode = _require_string(block, "temporal.mode", source)

    if mode not in KNOWN_TEMPORAL_MODES:
        raise ControlPlaneConfigError(
            RULE_UNKNOWN_TEMPORAL_MODE,
            f"declares `temporal.mode = {mode!r}`; supported modes are {_names(KNOWN_TEMPORAL_MODES)}",
            source=source,
        )

    if mode == "managed":
        raise ControlPlaneConfigError(
            RULE_TEMPORAL_MANAGED_NOT_IMPLEMENTED,
            "`temporal.mode = \"managed\"` is not implemented; it arrives with "
            "epic 042 (managed Temporal + worker units)",
            source=source,
        )

    address = _require_string(block, "temporal.address", source)
    namespace = _read_namespace(block, source)
    api_key_env = _optional_secret_ref(
        block.get("api_key_env"), "temporal.api_key_env", source
    )
    tls_enabled = block.get("tls_enabled", False)
    _expect_bool(tls_enabled, "temporal.tls_enabled", source)
    timeout_s = block.get("timeout_s", 5)
    _expect_int(timeout_s, "temporal.timeout_s", source)
    return ControlPlaneConfig.Temporal(
        mode="external",
        address=address,
        namespace=namespace,
        api_key_env=api_key_env,
        tls_enabled=bool(tls_enabled),
        timeout_s=int(timeout_s),
    )


def _read_namespace(block: Mapping[str, Any], source: str) -> str:
    raw = block.get("namespace")
    if raw is None:
        raise ControlPlaneConfigError(
            RULE_MISSING_REQUIRED,
            "`temporal` block requires `namespace` (exactly one namespace: repo "
            "identity lives in workflow IDs)",
            source=source,
            field="temporal.namespace",
        )
    if not isinstance(raw, str):
        raise ControlPlaneConfigError(
            RULE_TEMPORAL_NAMESPACE_NOT_SCALAR,
            f"`temporal.namespace` must be a single string, not {_kind(raw)}; "
            "the design uses exactly one namespace because repo identity lives in "
            "workflow IDs",
            source=source,
            field="temporal.namespace",
        )
    return raw


def _read_telemetry(
    document: Mapping[str, Any], source: str
) -> ControlPlaneConfig.Telemetry:
    block = _expect_block(document, "telemetry", source)
    otlp_endpoint = _optional_string(block.get("otlp_endpoint"))
    mode = "otlp" if otlp_endpoint else "none"
    timeout_s = block.get("timeout_s", 5)
    _expect_int(timeout_s, "telemetry.timeout_s", source)
    return ControlPlaneConfig.Telemetry(
        mode=mode,
        otlp_endpoint=otlp_endpoint,
        timeout_s=int(timeout_s),
    )


def _read_escalation(
    document: Mapping[str, Any], source: str
) -> ControlPlaneConfig.Escalation:
    block = _expect_block(document, "escalation", source)
    adapter = _require_string(block, "escalation.adapter", source)

    if adapter not in KNOWN_ESC_ADAPTERS:
        raise ControlPlaneConfigError(
            RULE_UNKNOWN_ESCALATION_ADAPTER,
            f"declares `escalation.adapter = {adapter!r}`; registered adapters are "
            f"{_names(KNOWN_ESC_ADAPTERS)}",
            source=source,
        )

    chat_id_env = _optional_secret_ref(
        block.get("chat_id_env"), "escalation.chat_id_env", source
    )
    bot_token_env = _optional_secret_ref(
        block.get("bot_token_env"), "escalation.bot_token_env", source
    )
    timeout_s = block.get("timeout_s", 30)
    _expect_int(timeout_s, "escalation.timeout_s", source)
    return ControlPlaneConfig.Escalation(
        adapter=adapter,
        chat_id_env=chat_id_env,
        bot_token_env=bot_token_env,
        timeout_s=int(timeout_s),
        authorized_responders=_read_responders(block, source),
    )


def _read_responders(block: Mapping[str, Any], source: str) -> tuple[str, ...]:
    """``escalation.authorized_responders``, or ``()`` when it is not declared.

    Absent is unrestricted; declared-and-empty is refused.  The distinction is
    the whole point of the field, and coercing one into the other would silently
    grant everyone the access an operator was in the middle of restricting.

    Refused with ``field_type`` rather than a slug of its own, because that is
    the slug every other wrong-shaped value in this file already carries and an
    operator fixing a config should meet one refusal grammar.
    """
    field = "escalation.authorized_responders"
    raw = block.get("authorized_responders")
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ControlPlaneConfigError(
            RULE_FIELD_TYPE,
            f"`{field}` must be a non-empty list of identities, not {_kind(raw)}; "
            "omit the key entirely to let anyone answer",
            source=source,
            field=field,
        )
    for identity in raw:
        if not isinstance(identity, str) or not identity:
            raise ControlPlaneConfigError(
                RULE_FIELD_TYPE,
                f"`{field}` lists {_kind(identity)}; every entry must be a "
                "non-empty identity string, spelled the way the transport "
                "reports it (`@username` or a numeric id, for Telegram)",
                source=source,
                field=field,
            )
    return tuple(raw)


# ---------------------------------------------------------------------------
# Rendering (US3): the parser's inverse, deterministic by construction
# ---------------------------------------------------------------------------
#
# `tomllib` reads TOML and nothing in the standard library writes it, and US3-S2
# asks that a re-run changing one answer produce a diff touching exactly that
# block.  Parsing, mutating and re-serialising cannot promise that: a comment or
# a blank line moves the moment any writer touches the document.
#
# So the file is *rendered* from the typed shape every time, in a fixed block and
# key order.  "The diff touches exactly one block" is then true by construction,
# a re-run with unchanged answers is byte-identical for free, and no
# round-tripping dependency enters the project.
#
# The consequence, stated out loud because an operator should meet it here rather
# than in a diff: **a hand-edited config's comments, key order and blank-line
# layout are not preserved** — the first `ergane install` re-run rewrites the
# file in this canonical form.  A hand-written config remains equally valid
# input; the parser is the contract.  Optional fields sitting at their documented
# default are omitted, which is what keeps rendering a pure function of the typed
# shape rather than of the text it came from.


#: Block order in the rendered file, and the key order within each block.
_RENDER_ORDER: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("llm", ("mode", "base_url", "master_key_env", "timeout_s")),
    ("memory", ("backend", "url", "api_key_env", "timeout_s")),
    (
        "temporal",
        ("mode", "address", "namespace", "api_key_env", "tls_enabled", "timeout_s"),
    ),
    ("telemetry", ("otlp_endpoint", "timeout_s")),
    (
        "escalation",
        (
            "adapter",
            "authorized_responders",
            "bot_token_env",
            "chat_id_env",
            "timeout_s",
        ),
    ),
)


def controlplane_document(config: ControlPlaneConfig) -> dict[str, Any]:
    """Return the plain-data document for ``config``: what the renderer writes.

    Optionals at their documented default are omitted, so two configs that parse
    equal render equal.
    """
    # `llm.timeout_s` is deliberately not rendered: no reader consults it, and
    # writing a key that changes nothing is a trap for whoever reads the file
    # next. (Before 048-US2 the parser read it on a per-persona table; that mode
    # is refused now, so the key has no reader at all.)
    llm: dict[str, Any] = {"mode": config.llm.mode}
    if config.llm.mode == "gateway" and config.llm.gateway is not None:
        llm["base_url"] = config.llm.gateway.base_url
        llm["master_key_env"] = config.llm.gateway.master_key_env

    memory: dict[str, Any] = {"backend": config.memory.backend}
    _set_if(memory, "url", config.memory.url)
    _set_if(memory, "api_key_env", config.memory.api_key_env)
    if config.memory.timeout_s != 5:
        memory["timeout_s"] = config.memory.timeout_s

    temporal: dict[str, Any] = {"mode": config.temporal.mode}
    _set_if(temporal, "address", config.temporal.address)
    _set_if(temporal, "namespace", config.temporal.namespace)
    _set_if(temporal, "api_key_env", config.temporal.api_key_env)
    if config.temporal.tls_enabled:
        temporal["tls_enabled"] = True
    if config.temporal.timeout_s != 5:
        temporal["timeout_s"] = config.temporal.timeout_s

    telemetry: dict[str, Any] = {}
    _set_if(telemetry, "otlp_endpoint", config.telemetry.otlp_endpoint)
    if config.telemetry.timeout_s != 5:
        telemetry["timeout_s"] = config.telemetry.timeout_s

    escalation: dict[str, Any] = {"adapter": config.escalation.adapter}
    # Rendered as a list, and omitted when empty, so "unrestricted" stays the
    # absence of a key rather than an empty list the parser refuses. A field that
    # parses and is never written back is one `ergane install` re-run from gone —
    # `EscalationRecord.check_evidence` reached the message and never the store
    # for three weeks on exactly that asymmetry.
    if config.escalation.authorized_responders:
        escalation["authorized_responders"] = list(
            config.escalation.authorized_responders
        )
    _set_if(escalation, "bot_token_env", config.escalation.bot_token_env)
    _set_if(escalation, "chat_id_env", config.escalation.chat_id_env)
    if config.escalation.timeout_s != 30:
        escalation["timeout_s"] = config.escalation.timeout_s

    return {
        "version": config.version,
        "llm": llm,
        "memory": memory,
        "temporal": temporal,
        "telemetry": telemetry,
        "escalation": escalation,
    }


def render_controlplane_document(document: Mapping[str, Any]) -> str:
    """Render a config document to TOML text in the canonical order.

    Takes plain data rather than the typed shape so the walkthrough can render
    an in-progress answer set and hand the result straight to the parser — one
    rule table, and the text that is validated is the text that is written.
    """
    lines: list[str] = [f"version = {_toml_value(document.get('version', 1))}"]

    for block_name, key_order in _RENDER_ORDER:
        block = document.get(block_name) or {}
        if not isinstance(block, Mapping):
            block = {}
        lines.append("")
        lines.append(f"[{block_name}]")
        for key in key_order:
            if key in block and block[key] is not None:
                lines.append(f"{key} = {_toml_value(block[key])}")
        # Anything the schema does not know is still rendered, so a value the
        # operator typed is never silently dropped before the parser sees it.
        for key in sorted(set(block) - set(key_order)):
            if block[key] is not None:
                lines.append(f"{key} = {_toml_value(block[key])}")

    return "\n".join(lines) + "\n"


def render_controlplane_config(config: ControlPlaneConfig) -> str:
    """Render a typed config back to TOML text (FR-007's write path)."""
    return render_controlplane_document(controlplane_document(config))


def _set_if(block: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        block[key] = value


def _toml_value(value: Any) -> str:
    """Render one scalar or array as TOML.

    Anything else is quoted, so a shape the schema does not model reaches the
    parser as a string it can refuse rather than as TOML nobody validated.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (list, tuple)):
        # `authorized_responders` is the only array the schema has; rendered
        # inline because the renderer's contract is one key per line.
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    text = value if isinstance(value, str) else str(value)
    escaped = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


# ---------------------------------------------------------------------------
# Generic block / field helpers
# ---------------------------------------------------------------------------


def _expect_block(
    document: Mapping[str, Any], key: str, source: str
) -> Mapping[str, Any]:
    if key not in document:
        raise ControlPlaneConfigError(
            RULE_MISSING_REQUIRED,
            f"declares no `[{key}]` subsystem block",
            source=source,
            field=key,
        )
    block = document[key]
    if not isinstance(block, Mapping):
        raise ControlPlaneConfigError(
            RULE_FIELD_TYPE,
            f"`[{key}]` must be a table, not {_kind(block)}",
            source=source,
            field=key,
        )
    return block


def _require_string(block: Mapping[str, Any], field: str, source: str) -> str:
    *prefix_parts, name = field.split(".")
    prefix = ".".join(prefix_parts) if prefix_parts else None
    raw = block.get(name)
    if raw is None:
        raise ControlPlaneConfigError(
            RULE_MISSING_REQUIRED,
            f"`{field}` is required",
            source=source,
            field=field,
        )
    if not isinstance(raw, str) or not raw:
        raise ControlPlaneConfigError(
            RULE_FIELD_TYPE,
            f"`{field}` must be a non-empty string, not {_kind(raw)}",
            source=source,
            field=field,
        )
    return raw


def _optional_string(raw: Any) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw:
        return None
    return raw


def _require_secret_ref(
    block: Mapping[str, Any], name: str, source: str, prefix: str | None = None
) -> str:
    field = f"{prefix}.{name}" if prefix else name
    raw = block.get(name)
    if raw is None:
        raise ControlPlaneConfigError(
            RULE_MISSING_REQUIRED,
            f"`{field}` is required",
            source=source,
            field=field,
        )
    if not isinstance(raw, str) or not raw:
        raise ControlPlaneConfigError(
            RULE_FIELD_TYPE,
            f"`{field}` must be a non-empty string, not {_kind(raw)}",
            source=source,
            field=field,
        )
    _reject_secret_shape(raw, field, source)
    return raw


def _optional_secret_ref(
    raw: Any, field: str, source: str
) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw:
        return None
    _reject_secret_shape(raw, field, source)
    return raw


def _reject_secret_shape(value: str, field: str, source: str) -> None:
    for pattern in _SECRET_PATTERNS:
        if pattern.search(value):
            raise ControlPlaneConfigError(
                RULE_SECRET_VALUE_NOT_REFERENCE,
                f"`{field}` looks like a credential ({value!r}); "
                "it must name an environment variable, not contain the secret value",
                source=source,
                field=field,
            )


def _expect_int(raw: Any, field: str, source: str) -> None:
    if type(raw) is not int or isinstance(raw, bool):
        raise ControlPlaneConfigError(
            RULE_FIELD_TYPE,
            f"`{field}` must be an integer, not {_kind(raw)}",
            source=source,
            field=field,
        )


def _expect_bool(raw: Any, field: str, source: str) -> None:
    if type(raw) is not bool:
        raise ControlPlaneConfigError(
            RULE_FIELD_TYPE,
            f"`{field}` must be a boolean, not {_kind(raw)}",
            source=source,
            field=field,
        )


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


def _names(values: Any) -> str:
    return ", ".join(repr(value) for value in values)


def _kind(value: Any) -> str:
    return f"a {type(value).__name__} ({value!r})"


def _one_line(error: Exception) -> str:
    return " ".join(str(error).split())
