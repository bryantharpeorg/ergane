"""One precedence, consulted everywhere the LLM gateway is needed (048-US1).

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
    and the source that won for each — an environment variable name, or the
    control-plane config's path. Everything US1 needs is here, and FR-003 holds
    by construction rather than by care.
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

    Being told about one route is how an operator who completed the interview
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
    """Read the declared gateway, or explain why there is nothing to read.

    Returns `(None, label)` when the config is absent, disabled or declares no
    gateway; `label` is always the path the caller would have to fix, so the
    refusals above can name it either way.

    The file is opened only when at least one of `needed` is missing from the
    environment. That is FR-002's second half — "when an override is set the
    config file MUST NOT be read for that value" — and it is what makes
    US1-S3 (both overrides set, config path bound to unparseable TOML) a
    scenario a resolver that opened the file could not pass.
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

    return config.llm.gateway, label
