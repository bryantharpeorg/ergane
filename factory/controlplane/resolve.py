"""One precedence, consulted everywhere the control plane is needed (048-US1, US4).

Two pairs of values pass through here: the LLM gateway's endpoint and
credential variable (US1), and Temporal's address and namespace (US4). They
share the rule rather than each having one — the day before US4,
`factory/controlplane/verify.py` read Temporal's config *first*, and
`ergane install --verify` could report a clean bill of health on a server the
worker never dialed.


`ergane install` writes `~/.config/ergane/config.toml`; until this module
existed, nothing on the dispatch path read it. `LiteLLMClient.from_env` took
`LITELLM_PROXY_URL` and `LITELLM_MASTER_KEY` straight from `os.environ`, so an
operator who completed the interview was told a variable the interview never
mentioned was not set, about an endpoint they had just declared.

Three properties are worth stating because the rest of the module is their
consequence:

- **The environment overrides the declaration, not the other way round.** A
  host already exporting both variables — this development host and its running
  worker among them — resolves exactly as it did before this module existed,
  and the config file is not opened at all. Inverting that precedence once
  `ergane install` is the normal path is a migration with its own story, not a
  refactor (D-047).
- **A resolution carries the credential's variable *name*, never its value.**
  That is why `CredentialRef` exists as a separate hop: the value is fetched at
  the last possible moment by whoever needs it, so no `repr`, log line, error
  message or workflow input can spill it (FR-003, SC-005). It is true by
  construction here rather than by discipline at every call site.
- **A *missing* config degrades; a *broken* one refuses.** `factory/registry.py`
  and `factory/notify/adapter.py` swallow `ControlPlaneConfigError` wholesale,
  because a repo registration must work on an unprovisioned host. Copying that
  reflex here would tell an operator who typo'd their config that
  `LITELLM_PROXY_URL is not set` — they would export a variable instead of
  fixing the file, and conclude the config does nothing, which is exactly the
  belief 048 exists to end (FR-004, FR-005).

Resolution runs at a CLI entry point or inside an activity, never at workflow
scope: the guard 039 added catches a workflow-scope `os.environ` read and would
*not* catch a file read (constitution IV, FR-007).

`factory.usage.litellm_client` reaches this module through a function-local
import inside `from_env`, so this module may import it at module scope without
closing a cycle. `factory/controlplane/__init__.py` is 0 bytes and must stay
that way: a re-export there makes `litellm_client` → `controlplane` → `verify`
→ `litellm_client` a cycle at worker start, surfacing as an unrelated
`ImportError`.
"""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path
from typing import Mapping

from factory.controlplane.config import (
    ControlPlaneConfig,
    ControlPlaneConfigError,
    load_controlplane_config,
    resolve_config_path,
)
from factory.usage.litellm_client import MASTER_KEY_ENV, PROXY_URL_ENV


class ControlPlaneResolutionError(Exception):
    """No source supplied a value the dispatch path cannot proceed without.

    Carries a message and nothing else: callers map it to their own vocabulary
    (`OperatorError` at a CLI boundary, `LiteLLMError` inside `from_env`) so no
    caller's existing error contract moves. The message names *routes* and
    *variable names*; it never names a credential value.
    """


@dataclasses.dataclass(frozen=True)
class CredentialRef:
    """The name of the variable holding a credential, and who said so.

    Deliberately not the credential. `read` is the only way to obtain the
    value and it keeps nothing, so an instance rendered into a traceback frame
    or a log line spills a variable name at worst (FR-003).
    """

    #: The environment variable that holds the credential.
    env_name: str
    #: Where that name came from: an environment variable, or a config path.
    source: str

    def read(self, *, environ: Mapping[str, str] | None = None) -> str:
        """Fetch the credential, at the last possible moment.

        Raises `ControlPlaneResolutionError` naming the variable and the source
        that declared it — and nothing else. Offering `LITELLM_MASTER_KEY` as a
        consolation would answer a question the operator did not ask: they
        declared a variable, so the answer is about that variable (US1-S6).
        """
        env = os.environ if environ is None else environ
        value = env.get(self.env_name)
        if not value:
            raise ControlPlaneResolutionError(
                f"{self.env_name} is not set; it is the credential variable "
                f"declared by {self.source}"
            )
        return value


@dataclasses.dataclass(frozen=True)
class EndpointRef:
    """A resolved endpoint and the source that supplied it."""

    #: The URL the proxy answers on.
    url: str
    #: Where it came from: an environment variable name, or a config path.
    source: str


@dataclasses.dataclass(frozen=True)
class GatewayResolution:
    """Where the LLM gateway is, and which variable holds its credential.

    Four fields and no secret: the endpoint, the credential's variable *name*,
    and the source that won for each. FR-003 holds by construction, not care.
    """

    base_url: str
    base_url_source: str
    master_key_env: str
    master_key_source: str

    @property
    def credential(self) -> CredentialRef:
        return CredentialRef(self.master_key_env, self.master_key_source)


def resolve_llm_gateway(
    *,
    environ: Mapping[str, str] | None = None,
    config_path: str | Path | None = None,
    consult_config: bool = True,
) -> GatewayResolution:
    """Resolve the gateway's endpoint and credential variable (FR-001, FR-002).

    `consult_config=False` is the SC-004 control seam: an explicit argument, so
    that "with the declaration branch disabled" is a different code path rather
    than a differently-populated environment. A control implemented as "unset a
    variable" would be the same code path and would prove nothing.
    """
    env = os.environ if environ is None else environ
    declared, label = _declared_gateway(
        env,
        config_path,
        consult_config,
        needed=(PROXY_URL_ENV, MASTER_KEY_ENV),
    )

    endpoint = _resolve_endpoint(env, declared, label)
    credential = _resolve_credential(env, declared, label)
    return GatewayResolution(
        base_url=endpoint.url,
        base_url_source=endpoint.source,
        master_key_env=credential.env_name,
        master_key_source=credential.source,
    )


def resolve_proxy_url(
    *,
    environ: Mapping[str, str] | None = None,
    config_path: str | Path | None = None,
    consult_config: bool = True,
) -> EndpointRef:
    """Resolve only the endpoint, under the same precedence.

    The three epic/roadmap start commands need this and not the credential:
    the endpoint is a workflow *input* they thread into `EpicInput.proxy_url`,
    while the credential is read on the worker host by the activity that mints
    the key. Demanding both here refuses to start an epic on a host well able
    to run it — a regression this story's first full-suite run caught, in seven
    tests that export a proxy url and no master key.
    """
    env = os.environ if environ is None else environ
    declared, label = _declared_gateway(
        env, config_path, consult_config, needed=(PROXY_URL_ENV,)
    )
    return _resolve_endpoint(env, declared, label)


def resolve_master_key_env(
    *,
    environ: Mapping[str, str] | None = None,
    config_path: str | Path | None = None,
    consult_config: bool = True,
) -> CredentialRef:
    """Resolve only the credential's variable name, under the same precedence.

    The roadmap's preflight seam is handed its `proxy_url` as an argument, so
    demanding an endpoint here would make it refuse on a host that had already
    told it where the proxy is. Same precedence, same labels, one value.
    """
    env = os.environ if environ is None else environ
    declared, label = _declared_gateway(
        env, config_path, consult_config, needed=(MASTER_KEY_ENV,)
    )
    return _resolve_credential(env, declared, label)


# --- Temporal: the same precedence, a second pair of values (048-US4) ---------

#: The label a value carries when neither the environment nor the declaration
#: supplied it. Temporal has a third source at all, so "nothing declared" is not
#: a refusal here the way it is above.
DEFAULT_SOURCE = "built-in default"


@dataclasses.dataclass(frozen=True)
class TemporalTarget:
    """Where Temporal is, and which source won for each half.

    Address and namespace resolve *independently*: taking the environment's
    whole answer the moment either variable was set would report a namespace
    nobody chose.
    """

    address: str
    address_source: str
    namespace: str
    namespace_source: str


def resolve_temporal_target(
    *,
    environ: Mapping[str, str] | None = None,
    config_path: str | Path | None = None,
    consult_config: bool = True,
) -> TemporalTarget:
    """Resolve Temporal's address and namespace (FR-015).

    Same direction as the gateway above. Eleven operational sites read
    `os.environ` directly before this existed, so an operator who declared an
    address still had to export `TEMPORAL_ADDRESS` for anything to connect.
    """
    env = os.environ if environ is None else environ
    address_env, namespace_env = _temporal_env_names()
    declared, label = _declared_temporal(
        env, config_path, consult_config, needed=(address_env, namespace_env)
    )
    return temporal_target_for(declared, source=label, environ=env)


def temporal_target_for(
    declared: ControlPlaneConfig.Temporal | None,
    *,
    source: str,
    environ: Mapping[str, str] | None = None,
) -> TemporalTarget:
    """Apply the precedence to a declaration the caller already parsed.

    For `factory/controlplane/verify.py`, pointed at one specific file it has
    already loaded: re-reading `resolve_config_path()` there would verify a
    *different* config than the one on the command line. `resolve_temporal_target`
    is written in terms of this, so FR-016 is structural rather than promised —
    one function decides both.
    """
    env = os.environ if environ is None else environ
    address_env, namespace_env = _temporal_env_names()
    from factory.notify.service import (
        DEFAULT_TEMPORAL_ADDRESS,
        DEFAULT_TEMPORAL_NAMESPACE,
    )

    address, address_source = _one_of(
        env.get(address_env),
        address_env,
        declared.address if declared is not None else None,
        source,
        DEFAULT_TEMPORAL_ADDRESS,
    )
    namespace, namespace_source = _one_of(
        env.get(namespace_env),
        namespace_env,
        declared.namespace if declared is not None else None,
        source,
        DEFAULT_TEMPORAL_NAMESPACE,
    )
    return TemporalTarget(address, address_source, namespace, namespace_source)


def _one_of(
    override: str | None,
    override_label: str,
    declared: str | None,
    declared_label: str,
    fallback: str,
) -> tuple[str, str]:
    """One value's precedence: environment, then declaration, then default."""
    if override:
        return override, override_label
    if declared:
        return declared, declared_label
    return fallback, DEFAULT_SOURCE


def _temporal_env_names() -> tuple[str, str]:
    """The two variable names, imported from where they are defined.

    Function-local on purpose: `factory/notify/service.py` costs 250 modules
    (measured) and this module is reached from `LiteLLMClient.from_env` on every
    CLI path and activity; a module-scope import would also run
    `factory.notify.adapter`'s control-plane import during
    `factory.controlplane`'s own — plan trap 11's neighbourhood.
    """
    from factory.notify.service import TEMPORAL_ADDRESS_ENV, TEMPORAL_NAMESPACE_ENV

    return TEMPORAL_ADDRESS_ENV, TEMPORAL_NAMESPACE_ENV


def _declared_temporal(
    env: Mapping[str, str],
    config_path: str | Path | None,
    consult_config: bool,
    *,
    needed: tuple[str, ...],
) -> tuple[ControlPlaneConfig.Temporal | None, str]:
    """Read the declared Temporal block, through the shared declaration reader."""
    config, label = _declared_config(env, config_path, consult_config, needed=needed)
    return (config.temporal if config is not None else None), label


# --- the precedence, in one place --------------------------------------------


def _resolve_endpoint(
    env: Mapping[str, str],
    declared: ControlPlaneConfig.LLMGateway | None,
    label: str,
) -> EndpointRef:
    override = env.get(PROXY_URL_ENV)
    if override:
        return EndpointRef(override, PROXY_URL_ENV)
    if declared is not None and declared.base_url:
        return EndpointRef(declared.base_url, label)
    raise ControlPlaneResolutionError(_both_routes("endpoint", PROXY_URL_ENV, label))


def _resolve_credential(
    env: Mapping[str, str],
    declared: ControlPlaneConfig.LLMGateway | None,
    label: str,
) -> CredentialRef:
    # The override branch answers with the *name* of the variable, never the
    # value it happens to hold — the presence check is the whole of the read
    # that happens here (FR-003).
    if env.get(MASTER_KEY_ENV):
        return CredentialRef(MASTER_KEY_ENV, MASTER_KEY_ENV)
    if declared is not None and declared.master_key_env:
        return CredentialRef(declared.master_key_env, label)
    raise ControlPlaneResolutionError(
        _both_routes("credential", MASTER_KEY_ENV, label)
    )


def _both_routes(what: str, env_name: str, label: str) -> str:
    """FR-004: name the two ways to satisfy this, never only one.

    Hearing about one route is how an operator who completed the interview
    concludes their answers were not used.
    """
    return (
        f"no LLM gateway {what} is available: set {env_name} in the environment, "
        f"or declare the gateway in {label} (`ergane install` writes it)"
    )


# --- the declaration side -----------------------------------------------------


def _declared_gateway(
    env: Mapping[str, str],
    config_path: str | Path | None,
    consult_config: bool,
    *,
    needed: tuple[str, ...],
) -> tuple[ControlPlaneConfig.LLMGateway | None, str]:
    """Read the declared gateway, or explain why there is nothing to read."""
    config, label = _declared_config(env, config_path, consult_config, needed=needed)
    return (config.llm.gateway if config is not None else None), label


def _declared_config(
    env: Mapping[str, str],
    config_path: str | Path | None,
    consult_config: bool,
    *,
    needed: tuple[str, ...],
) -> tuple[ControlPlaneConfig | None, str]:
    """Read the declaration, or explain why there is nothing to read.

    Returns `(None, label)` when the config is absent or disabled; `label` is
    always the path the caller would have to fix, so the refusals above can
    name it either way.

    The file is opened only when at least one of `needed` is missing from the
    environment — FR-002's second half, and what makes US1-S3 a scenario a
    resolver that opened the file could not pass.

    Shared by both subsystems rather than copied for the second one: "when is
    the file read, and what happens when it is broken" is one decision, and two
    copies of it would drift the day one of them learned something.
    """
    path = Path(config_path) if config_path is not None else resolve_config_path()
    label = str(path)

    if not consult_config:
        return None, label
    if all(env.get(name) for name in needed):
        return None, label
    if not path.exists():
        # Degrade: an unprovisioned host has no file, and saying so is the
        # caller's both-routes refusal, not a parser error.
        return None, label

    try:
        config = load_controlplane_config(path)
    except ControlPlaneConfigError as error:
        # Refuse: the operator has a config and it is wrong. Surface the
        # parser's own reason and the file it names, rather than reporting an
        # environment variable that is beside the point (FR-005, plan trap 3).
        raise ControlPlaneResolutionError(
            f"the control-plane config cannot be used: {error}"
        ) from None

    return config, label
