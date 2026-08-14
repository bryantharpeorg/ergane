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

#: Allowed values for llm.mode (FR-004).
KNOWN_LL_MODES = ("gateway", "direct")

#: Allowed built-in memory backends (FR-004).  Custom adapters are admitted by
#: name if registered; these two are always available.
KNOWN_MEMORY_BACKENDS = ("hindsight", "none")

#: Allowed temporal modes (FR-004).  "managed" is recognized as a token but
#: refused until 042 lands.
KNOWN_TEMPORAL_MODES = ("external", "managed")

#: Adapters registered for escalation at the time of this epic (FR-004).
#: Telegram is the reference transport from 008; 041 will add the adapter seam.
KNOWN_ESC_ADAPTERS = ("telegram",)

#: Default relative path under XDG_CONFIG_HOME / HOME (FR-001).
DEFAULT_CONFIG_REL = Path("ergane") / "config.toml"

#: Stable rule slugs used in ``ControlPlaneConfigError.rule``.
RULE_VERSION = "version"
RULE_UNKNOWN_KEY = "unknown_key"
RULE_UNKNOWN_LLM_MODE = "unknown_llm_mode"
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
    class LLMDirectPersona:
        """One per-persona endpoint in ``direct`` mode."""

        name: str
        base_url: str
        model: str
        api_key_env: str
        timeout_s: int = 300

    @dataclasses.dataclass(frozen=True)
    class LLMGateway:
        """``gateway`` mode: a LiteLLM-shaped proxy."""

        base_url: str
        master_key_env: str
        timeout_s: int = 300

    @dataclasses.dataclass(frozen=True)
    class LLM:
        """Mode-discriminated LLM block."""

        mode: str
        personas: tuple["ControlPlaneConfig.LLMDirectPersona", ...] = ()
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
        """Escalation transport block."""

        adapter: str
        chat_id_env: str | None = None
        bot_token_env: str | None = None
        timeout_s: int = 30


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
        personas = _read_direct_personas(block, source)
        return ControlPlaneConfig.LLM(mode="direct", personas=personas)

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


def _read_direct_personas(
    block: Mapping[str, Any], source: str
) -> tuple[ControlPlaneConfig.LLMDirectPersona, ...]:
    raw_personas = block.get("persona")
    if raw_personas is None:
        raise ControlPlaneConfigError(
            RULE_MISSING_REQUIRED,
            "`llm.mode = \"direct\"` requires at least one `[[llm.persona]]` block",
            source=source,
            field="llm.persona",
        )
    if not isinstance(raw_personas, list):
        raise ControlPlaneConfigError(
            RULE_FIELD_TYPE,
            f"`llm.persona` must be a list of tables, not {_kind(raw_personas)}",
            source=source,
            field="llm.persona",
        )
    if not raw_personas:
        raise ControlPlaneConfigError(
            RULE_MISSING_REQUIRED,
            "`llm.mode = \"direct\"` requires at least one `[[llm.persona]]` block",
            source=source,
            field="llm.persona",
        )

    result: list[ControlPlaneConfig.LLMDirectPersona] = []
    for index, raw in enumerate(raw_personas):
        if not isinstance(raw, Mapping):
            raise ControlPlaneConfigError(
                RULE_FIELD_TYPE,
                f"`llm.persona[{index}]` must be a table, not {_kind(raw)}",
                source=source,
                field=f"llm.persona[{index}]",
            )
        field = f"llm.persona[{index}]"
        name = _require_string(raw, f"{field}.name", source)
        base_url = _require_string(raw, f"{field}.base_url", source)
        model = _require_string(raw, f"{field}.model", source)
        api_key_env = _require_secret_ref(raw, "api_key_env", source, prefix=field)
        timeout_s = raw.get("timeout_s", 300)
        _expect_int(timeout_s, f"{field}.timeout_s", source)
        result.append(
            ControlPlaneConfig.LLMDirectPersona(
                name=name,
                base_url=base_url,
                model=model,
                api_key_env=api_key_env,
                timeout_s=int(timeout_s),
            )
        )
    return tuple(result)


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
    )


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
