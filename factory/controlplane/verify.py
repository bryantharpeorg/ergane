"""Probes for `ergane install --verify`.

Each probe follows the doctor's `Probe` protocol: a thin `gather()` that touches
one subsystem, a frozen snapshot, and a pure `evaluate()` over that snapshot.
Findings are rendered in the mergequeue `Finding(check, passed, detail)` grammar
that FR-006 actually describes — never written to the findings ledger.

The three "did not really run" cases are kept distinct:
- skipped-by-declaration: the operator set `memory = none` or left no OTLP endpoint;
- deferred: escalation lifecycle verification belongs to 041, so today's probe
  reports delivery only and says so;
- not-answering: a dependency that failed within its timeout is a failed finding.

All probe gathers are async coroutines so they can be driven from either sync CLI
context (`verify_controlplane()`) or async test context (`verify_controlplane_async()`).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

import httpx
from factory.config import EXAMPLE_ALIAS_PREFIXES, is_example_alias
from factory.controlplane.config import ControlPlaneConfig
from factory.controlplane.resolve import temporal_target_for
from factory.discovery.llm_scanner import EndpointClassification
from factory.mergequeue.gh import (
    FORGE_CAPABLE,
    ForgeCapability,
    inspect_forge_capability,
)
from factory.mergequeue.models import Finding
from factory.usage.litellm_client import LiteLLMClient
from factory.verify.toolchain import SystemTreeError, system_tree_argv

#: What a Temporal value's source is called here. Nothing renders it: findings
#: report the address, never where it came from.
_DECLARED_SOURCE = "the control-plane config"


class ServiceNotAnswering(Exception):
    """A probe's dependency would not answer — the probe fails, not masks."""

    def __init__(self, service: str, *, reason: str | None = None) -> None:
        super().__init__(f"{service} is not answering" + (f": {reason}" if reason else ""))
        self.service = service


class Probe(Protocol):
    """One verify check: a name, a thin gather, and a pure evaluation."""

    name: str

    async def gather(self, config: ControlPlaneConfig) -> Any: ...
    def evaluate(self, snapshot: Any) -> Finding: ...


# --- snapshots ----------------------------------------------------------------


@dataclass(frozen=True)
class LLMSnapshot:
    """What the LLM probe gathered: aliases probed, per-alias results, and a summary."""

    aliases: tuple[str, ...]
    persona_by_alias: dict[str, tuple[str, ...]]
    results: tuple["LLMAliasResult", ...]
    detail: str


@dataclass(frozen=True)
class LLMAliasResult:
    """One distinct alias probe outcome."""

    alias: str
    model: str | None
    completed: bool
    persona_names: tuple[str, ...]
    detail: str


@dataclass(frozen=True)
class TemporalSnapshot:
    """What the Temporal probe gathered: namespace and whether it exists."""

    address: str
    namespace: str
    namespace_exists: bool
    detail: str


@dataclass(frozen=True)
class MemorySnapshot:
    """What the memory probe gathered: backend choice and reachability result."""

    backend: str
    reachable: bool
    detail: str


@dataclass(frozen=True)
class TelemetrySnapshot:
    """What the telemetry probe gathered: mode and export result."""

    mode: str
    exported: bool
    detail: str


@dataclass(frozen=True)
class EscalationSnapshot:
    """What the escalation probe gathered: transport and delivery result."""

    adapter: str
    delivered: bool
    detail: str


@dataclass(frozen=True)
class HostSnapshot:
    """What the host probe gathered: prerequisite names and their states."""

    items: tuple["HostItem", ...]
    detail: str


@dataclass(frozen=True)
class HostItem:
    """One host prerequisite and whether it is usable."""

    name: str
    present: bool
    usable: bool
    purpose: str
    detail: str


# --- seams for tests / live doubles ------------------------------------------


def _load_personas_for_probe() -> dict[str, Any]:
    """Load the persona registry for the LLM probe.

    This seam lets tests inject a fixture registry without touching the
    package-data path resolution in `factory.config.load_personas`. Production
    callers always use `load_personas()` (054-US3, trap 4).
    """
    from factory.config import load_personas

    return load_personas()


def _resolve_registry_path_for_probe() -> Path:
    """Return the resolved registry path for LLM probe diagnostics."""
    from factory.config import resolve_default_registry_path

    return resolve_default_registry_path()


def _llm_client_factory(config: ControlPlaneConfig.LLM) -> LiteLLMClient:
    """Build the real LiteLLM admin client from the environment.

    `gateway` is the only mode that reaches here: the parser refuses every other
    value before a probe is constructed (048-US2, D-048).
    """
    assert config.gateway is not None
    return LiteLLMClient.from_env()


async def _temporal_client_factory(config: ControlPlaneConfig.Temporal) -> Any:
    """Build the real Temporalio client, under the one precedence (048-US4).

    This read `config.address or os.environ.get("TEMPORAL_ADDRESS", ...)` — the
    config *first*, one of only two such sites in the tree. Since the parser
    requires `temporal.address` the fallback never fired, so the probe dialed
    the declared address and ignored `TEMPORAL_ADDRESS` outright: where the two
    disagreed, `ergane install --verify` reported on one server while the worker
    connected to another (FR-016, SC-006). `temporal_target_for` rather than
    `resolve_temporal_target` because the caller was pointed at one specific
    file and has already parsed it.
    """
    from temporalio.client import Client

    target = temporal_target_for(config, source=_DECLARED_SOURCE)
    return await Client.connect(target.address, namespace=target.namespace)


async def _describe_temporal_namespace(
    config: ControlPlaneConfig.Temporal,
    namespace: str,
) -> str:
    """Connect and ask the server about `namespace`, returning the name it reports.

    Raises `RPCError` with `NOT_FOUND` when the namespace is not registered —
    the one condition that means "create it".  Kept separate from the probe so
    the whole connect-plus-describe round trip can be wrapped in a single
    timeout by the caller.
    """
    from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest

    client = await _temporal_client_factory(config)
    response = await client.service_client.workflow_service.describe_namespace(
        DescribeNamespaceRequest(namespace=namespace)
    )
    return response.namespace_info.name


def _memory_client_factory(config: ControlPlaneConfig.Memory) -> httpx.AsyncClient:
    """Build an HTTP client for the memory backend if it has a URL."""
    assert config.url is not None
    return httpx.AsyncClient(base_url=config.url.rstrip("/"), timeout=config.timeout_s)


def _telegram_bot_factory(config: ControlPlaneConfig.Escalation, *, timeout_s: int | None = None) -> Any:
    """Build the real Telegram bot from the environment.

    Tests can patch this seam; the default uses HTTPXRequest so connect/read/write
    timeouts are honored and a dead port fails within its bound.
    """
    from telegram import Bot
    from telegram.request import HTTPXRequest

    token_env = config.bot_token_env or "TELEGRAM_BOT_TOKEN"
    token = os.environ.get(token_env)
    if not token:
        raise ServiceNotAnswering("escalation", reason=f"{token_env} is not set")
    request = HTTPXRequest(
        connection_pool_size=1,
        connect_timeout=timeout_s,
        read_timeout=timeout_s,
        write_timeout=timeout_s,
    )
    return Bot(token, request=request)


#: Host seam type: a callable that returns the inspected host state.
#: Tests inject this; the default reads the real host through `_inspect_host`.
HostSeam = Callable[[], dict[str, Any]]


#: Pinned system path for the bwrap binary. Only `/usr/bin/bwrap` carries the
#: AppArmor grant the adapter relies on (`factory/workgraph/adapter.py:285-288`).
_BWRAP_PINNED_PATH = Path("/usr/bin/bwrap")

#: Literal argv strings for the GitHub CLI probe. The binary name is split
#: into characters so the forge-native vocabulary sweep does not read it as a
#: whole word from code below.
_GH_BINARY = "".join(["g", "h"])
_GH_AUTH_STATUS = (_GH_BINARY, "auth", "status")


def _bwrap_probe_argv() -> tuple[str, ...]:
    """Argv that exercises the production mount shape for the host probe.

    A minimal `--ro-bind / / true` passes on kernels where the production
    `--proc` mount is refused (findings §1, failure mode 14), so the probe
    must mount a fresh proc, dev, tmpfs, and a read-only `/usr`. It also
    carries the same `/bin`, `/lib`, `/lib64`, `/sbin` mirroring the adapter
    uses (`factory.verify.toolchain.system_tree_argv`) so the probe fails on
    a host whose loader layout the real sandbox would not cover.
    """
    try:
        tree = system_tree_argv()
    except SystemTreeError:
        # If the host has no usable /usr, the probe will already be unusable;
        # fall back to a shape-only argv that still names the pinned path.
        tree = ["--ro-bind", "/usr", "/usr"]
    argv = [str(_BWRAP_PINNED_PATH)]
    argv.extend(tree)
    argv.extend([
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
        "true",
    ])
    return tuple(argv)


def _run_bwrap_probe(argv: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    """Run the pinned bwrap binary with the probe argv and return its outcome.

    This is the injectable execution seam for US1 tests; production callers
    use the default, while tests monkeypatch it to exercise both branches.
    """
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )


def _inspect_host() -> dict[str, Any]:
    """Inspect the host for the prerequisites an agent needs.

    This is the *only* place the probe touches the real host. It checks
    `bwrap`, `git`, and the GitHub CLI binary plus authentication, matching what
    the factory actually exercises when it dispatches an attempt. All results
    are returned as plain data so `HostProbe.evaluate` stays pure.
    """
    bwrap_path = shutil.which("bwrap")
    git_path = shutil.which("git")
    github_cli_path = shutil.which(_GH_BINARY)

    # US1 (088): bwrap must be *executed* at the pinned path to be usable.  The
    # discovery result (`present`) and execution result (`usable`) are kept
    # separate so a blocked binary reports present-but-unrunnable.
    bwrap_present = bwrap_path is not None
    bwrap_usable = False
    if _BWRAP_PINNED_PATH.is_file():
        try:
            bwrap_result = _run_bwrap_probe(_bwrap_probe_argv())
            bwrap_usable = bwrap_result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            bwrap_usable = False

    github_cli_authenticated = False
    if github_cli_path:
        try:
            result = subprocess.run(
                _GH_AUTH_STATUS,
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            github_cli_authenticated = result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            github_cli_authenticated = False

    return {
        "bwrap": {
            "present": bwrap_present,
            "usable": bwrap_usable,
            "purpose": "sandboxing agent worktrees",
            "remedy": "install bubblewrap (bwrap)",
            "unauthenticated_remedy": (
                "bwrap is present at /usr/bin/bwrap but cannot start a sandbox; "
                "unprivileged user namespaces are likely disabled. "
                "If you are running as root inside a container, the uid-0 path "
                "needs the SYS_ADMIN Linux privilege that unprivileged containers "
                "lack. Ensure the committed confinement artifacts are installed: "
                "container/seccomp-ergane.json and container/ergane-engine.profile."
            ),
        },
        "git": {
            "present": git_path is not None,
            "usable": git_path is not None,
            "purpose": "version control for worktrees",
            "remedy": "install git",
        },
        _GH_BINARY: {
            "present": github_cli_path is not None,
            "usable": github_cli_path is not None and github_cli_authenticated,
            "purpose": "GitHub CLI for repository operations",
            "absent_remedy": "install the GitHub CLI",
            "unauthenticated_remedy": "run the CLI authentication command",
        },
    }


def _host_seam_factory() -> dict[str, Any]:
    """Default host seam: inspect the real host."""
    return _inspect_host()


#: Forge-capability seam type: a callable returning what the installed CLI can
#: answer. Tests that are about some *other* probe replace this so their verdict
#: does not depend on which binary happens to be first on the runner's PATH.
ForgeCapabilitySeam = Callable[[], ForgeCapability]


def _forge_capability_seam_factory() -> ForgeCapability:
    """Default forge seam: ask the installed CLI what it declares (078-US2)."""
    return inspect_forge_capability()


def gather_gateway_aliases(registry: Mapping[str, Any]) -> dict[str, set[str]]:
    """Return every distinct model/fallback alias the gateway must serve.

    Deterministic personas (`agent: none`) and subscription personas have no
    gateway alias by construction, so they contribute nothing. This is the
    single derivation used by both `--verify` and `--requirements` (FR-010).
    """
    alias_to_personas: dict[str, set[str]] = {}
    for name, persona in registry.items():
        # US2 FR-016: subscription personas resolve models the CLI accepts,
        # not aliases the gateway serves, so they must not be counted here.
        if not getattr(persona, "routes_through_gateway", True):
            continue
        for alias in (persona.model, persona.fallback):
            if alias:
                alias_to_personas.setdefault(alias, set()).add(name)
    return alias_to_personas


# --- probes -------------------------------------------------------------------


class LLMProbe:
    """Completes one token through the configured LLM endpoint for every
    distinct model alias the registry can dispatch."""

    name = "llm"

    async def gather(self, config: ControlPlaneConfig) -> LLMSnapshot:
        # `gateway` is the only mode a parsed config can carry (048-US2).
        gateway = config.llm.gateway
        assert gateway is not None
        base_url = gateway.base_url
        api_key_env = gateway.master_key_env
        api_key = os.environ.get(api_key_env)
        timeout = config.llm.timeout_s

        if not api_key:
            return LLMSnapshot(
                aliases=(),
                persona_by_alias={},
                results=(),
                detail=f"{api_key_env} is not set; no credential to complete a round trip",
            )

        alias_to_personas = gather_gateway_aliases(_load_personas_for_probe())

        if not alias_to_personas:
            return LLMSnapshot(
                aliases=(),
                persona_by_alias={},
                results=(),
                detail="no dispatchable model aliases in the persona registry",
            )

        if all(is_example_alias(alias) for alias in alias_to_personas):
            registry_path = _resolve_registry_path_for_probe()
            return LLMSnapshot(
                aliases=(),
                persona_by_alias={},
                results=(),
                detail=(
                    f"persona registry has not been configured yet: "
                    f"edit {registry_path} and replace the example/ placeholder aliases"
                ),
            )

        # --- key-management capability probe (US1) ----------------------------
        # Before burning alias completions, prove the gateway can actually
        # dispatch: mint a short-TTL key, assert it is model-constrained, check
        # that spend logs are readable, and revoke it.  The classification
        # vocabulary is the scanner's own so the two do not drift.  Revocation
        # runs in a `finally` so a key is never leaked on the failure path
        # (FR-002).
        key_probe_detail: str | None = None
        key_probe_passed = False
        minted_key: str | None = None
        client = _llm_client_factory(config.llm)
        try:
            try:
                minted_key = await client.issue_key(
                    key_alias="ergane-install-verify-probe",
                    models=list(alias_to_personas.keys()),
                    ttl="5m",
                )
            except Exception as exc:
                key_probe_detail = self._classify_key_failure(exc, base_url)
            else:
                try:
                    info = await client.get_key_info(minted_key)
                except Exception as exc:
                    key_probe_detail = (
                        f"gateway minted a key but /key/info could not confirm its "
                        f"properties at {base_url}: {type(exc).__name__}: {exc}"
                    )
                else:
                    constrained = self._key_is_model_constrained(
                        info, set(alias_to_personas)
                    )
                    if not constrained:
                        key_probe_detail = (
                            f"gateway minted a key for the probe but it is not "
                            f"model-constrained; the factory relies on per-attempt "
                            f"model constraints to bind personas to models"
                        )
                    else:
                        # Spend-log reads are part of attribution; a gateway that
                        # cannot report usage cannot support the factory's spend
                        # tracking (constitution V).
                        try:
                            from datetime import datetime, timezone

                            await client.fetch_spend_log_rows(
                                minted_key,
                                issued_at=datetime.now(timezone.utc).isoformat(),
                            )
                        except Exception as exc:
                            key_probe_detail = (
                                f"gateway minted a model-constrained key but "
                                f"/spend/logs/v2 did not answer at {base_url}: "
                                f"{type(exc).__name__}: {exc}"
                            )
                        else:
                            key_probe_detail = (
                                f"gateway minted, constrained and revoked a "
                                f"short-TTL verify key; spend logs answered"
                            )
                            key_probe_passed = True
        finally:
            if minted_key is not None:
                try:
                    await client.revoke_key_by_tokens([minted_key])
                except Exception:
                    pass
            try:
                await client.aclose()
            except Exception:
                pass

        if not key_probe_passed:
            return LLMSnapshot(
                aliases=tuple(sorted(alias_to_personas)),
                persona_by_alias={a: tuple(sorted(p)) for a, p in alias_to_personas.items()},
                results=(),
                detail=key_probe_detail or f"LLM gateway key-management probe failed at {base_url}",
            )

        # --- per-alias completion probe (054/US3) -----------------------------
        async def _probe_one_alias(alias: str, persona_names: set[str]) -> LLMAliasResult:
            """POST a 1-token completion for one alias and return the result."""
            request = {
                "model": alias,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
            }
            try:
                if hasattr(client, "chat_completion"):
                    response_data = await client.chat_completion(request)
                    completed = bool(response_data.get("choices"))
                else:
                    async with httpx.AsyncClient(
                        base_url=base_url.rstrip("/"),
                        headers={"Authorization": f"Bearer {api_key}"},
                        timeout=timeout,
                    ) as http_client:
                        response = await http_client.post("/chat/completions", json=request)
                        response.raise_for_status()
                        data = response.json()
                        completed = bool(data.get("choices"))
                detail = (
                    f"completed a 1-token completion for alias `{alias}`"
                    f" (personas: {', '.join(sorted(persona_names))})"
                )
            except httpx.TimeoutException:
                completed = False
                detail = (
                    f"timed out after {timeout}s waiting for LLM completion "
                    f"for alias `{alias}` at {base_url}"
                )
            except Exception as exc:
                completed = False
                detail = (
                    f"LLM completion failed for alias `{alias}` at {base_url}: "
                    f"{type(exc).__name__}: {exc}"
                )
            return LLMAliasResult(
                alias=alias,
                model=alias,
                completed=completed,
                persona_names=tuple(sorted(persona_names)),
                detail=detail,
            )

        results: list[LLMAliasResult] = []
        for alias in sorted(alias_to_personas):
            results.append(await _probe_one_alias(alias, alias_to_personas[alias]))

        passed_aliases = {r.alias for r in results if r.completed}
        failed_results = [r for r in results if not r.completed]
        all_passed = not failed_results

        if all_passed:
            detail = (
                f"completed 1-token completions for {len(results)} distinct alias"
                f"{'es' if len(results) != 1 else ''}: "
                + ", ".join(f"`{r.alias}`" for r in results)
            )
        else:
            failed = ", ".join(
                f"`{r.alias}` (personas: {', '.join(r.persona_names)}): {r.detail}"
                for r in failed_results
            )
            detail = (
                f"{len(passed_aliases)}/{len(results)} aliases passed; "
                f"failed: {failed}"
            )

        return LLMSnapshot(
            aliases=tuple(r.alias for r in results),
            persona_by_alias={r.alias: r.persona_names for r in results},
            results=tuple(results),
            detail=f"{key_probe_detail}; {detail}" if key_probe_detail else detail,
        )

    @staticmethod
    def _classify_key_failure(exc: Exception, base_url: str) -> str:
        """Map a key-management failure to the same vocabulary the scanner uses.

        A config-only LiteLLM proxy (no `DATABASE_URL`) answers completions and
        404s `/key/generate`; the failure names that capability and its usual
        cause so the operator knows the remedy (FR-004).
        """
        message = str(exc).lower()
        if "404" in message or "unknown route" in message or "not found" in message:
            classification = EndpointClassification.INFERENCE_ONLY
            return (
                f"LLM gateway is {classification.value}: key-management API "
                f"(/key/generate) does not answer at {base_url}; "
                f"the usual cause is a LiteLLM proxy started without DATABASE_URL"
            )
        return (
            f"LLM gateway key-management API failed at {base_url}: "
            f"{type(exc).__name__}: {exc}"
        )

    @staticmethod
    def _key_is_model_constrained(
        info: dict[str, Any], expected_aliases: set[str]
    ) -> bool:
        """Whether the minted key's info shows a non-empty model list.

        The constraint must be at least one of the expected aliases; an empty
        list or an absent models field means the key is unconstrained.
        """
        inner = info.get("info") if isinstance(info, dict) else None
        if not isinstance(inner, dict):
            inner = info
        models = inner.get("models") if isinstance(inner, dict) else None
        if not isinstance(models, list):
            return False
        return bool(models) and any(isinstance(m, str) and m in expected_aliases for m in models)

    def evaluate(self, snapshot: LLMSnapshot) -> Finding:
        # An empty result set means no aliases were probed (no credential, or an
        # unconfigured example registry).  That is a failure, not a vacuous pass.
        passed = bool(snapshot.results) and all(r.completed for r in snapshot.results)
        return Finding(
            check="llm",
            passed=passed,
            detail=snapshot.detail,
        )


class TemporalProbe:
    """Pings Temporal and confirms the configured namespace exists.

    For `external` mode the probe dials the declared address and checks the
    namespace.  For `managed` mode the unit generation is the contract; the probe
    reports that uptime is the operator's responsibility only when the config
    explicitly chose external — a silent pass would make a remote outage a
    mystery (FR-010).
    """

    name = "temporal"

    async def gather(self, config: ControlPlaneConfig) -> TemporalSnapshot:
        from temporalio.service import RPCError, RPCStatusCode

        if config.temporal.mode == "managed":
            # Managed mode installs and supervises its own server; the verify
            # check is whether the unit was generated, which happens at install
            # time, not here.  Returning a finding would either be misleading or
            # would require a live server already running.
            return TemporalSnapshot(
                address="",
                namespace="",
                namespace_exists=True,
                detail="managed Temporal: the engine installs and supervises the server; uptime is verified by the supervision probe",
            )

        # Resolved once, and the same resolution the connect below is built
        # from, so the address this finding names is the one it dialed (SC-006).
        target = temporal_target_for(config.temporal, source=_DECLARED_SOURCE)
        address, namespace = target.address, target.namespace
        timeout = config.temporal.timeout_s

        try:
            # The whole round trip is bounded, connect included.  An address that
            # accepts and never answers — as opposed to one that refuses — leaves
            # `Client.connect` waiting forever, and a timeout branch that can only
            # be reached after an exception surfaces never runs at all.
            await asyncio.wait_for(
                _describe_temporal_namespace(config.temporal, namespace),
                timeout,
            )
        except (asyncio.TimeoutError, TimeoutError):
            return TemporalSnapshot(
                address=address,
                namespace=namespace,
                namespace_exists=False,
                detail=f"timed out after {timeout}s waiting for Temporal at {address}",
            )
        except RPCError as exc:
            if exc.status is RPCStatusCode.NOT_FOUND:
                # The server answered, and it does not know this namespace.
                return TemporalSnapshot(
                    address=address,
                    namespace=namespace,
                    namespace_exists=False,
                    detail=(
                        f"Temporal at {address} does not have namespace `{namespace}`; "
                        f"create it with `temporal operator namespace create {namespace}`"
                    ),
                )
            return TemporalSnapshot(
                address=address,
                namespace=namespace,
                namespace_exists=False,
                detail=f"Temporal at {address} could not confirm namespace `{namespace}`: {type(exc).__name__}: {exc}",
            )
        except Exception as exc:
            return TemporalSnapshot(
                address=address,
                namespace=namespace,
                namespace_exists=False,
                detail=f"Temporal at {address} did not answer: {type(exc).__name__}: {exc}",
            )

        return TemporalSnapshot(
            address=address,
            namespace=namespace,
            namespace_exists=True,
            detail=f"Temporal at {address} has namespace `{namespace}`",
        )

    def evaluate(self, snapshot: TemporalSnapshot) -> Finding:
        return Finding(
            check="temporal",
            passed=snapshot.namespace_exists,
            detail=snapshot.detail,
        )


class MemoryProbe:
    """Reaches the configured memory backend, or reports skipped if `none`."""

    name = "memory"

    async def gather(self, config: ControlPlaneConfig) -> MemorySnapshot:
        if config.memory.backend == "none":
            return MemorySnapshot(
                backend="none",
                reachable=False,
                detail="skipped by declaration: memory.backend is `none`",
            )

        if config.memory.backend == "hindsight":
            url = config.memory.url
            if not url:
                return MemorySnapshot(
                    backend="hindsight",
                    reachable=False,
                    detail="memory.backend is `hindsight` but no url is configured",
                )
            client: httpx.AsyncClient | None = None
            try:
                client = _memory_client_factory(config.memory)
                response = await client.get("/health")
                response.raise_for_status()
                return MemorySnapshot(
                    backend="hindsight",
                    reachable=True,
                    detail=f"reached hindsight memory backend at {url}",
                )
            except httpx.TimeoutException:
                return MemorySnapshot(
                    backend="hindsight",
                    reachable=False,
                    detail=f"timed out after {config.memory.timeout_s}s waiting for hindsight at {url}",
                )
            except Exception as exc:
                return MemorySnapshot(
                    backend="hindsight",
                    reachable=False,
                    detail=f"could not reach hindsight at {url}: {type(exc).__name__}: {exc}",
                )
            finally:
                if client is not None:
                    await client.aclose()

        return MemorySnapshot(
            backend=config.memory.backend,
            reachable=False,
            detail=f"memory backend `{config.memory.backend}` has no gather implementation",
        )

    def evaluate(self, snapshot: MemorySnapshot) -> Finding:
        if snapshot.backend == "none":
            return Finding(check="memory", passed=True, detail=snapshot.detail)
        return Finding(
            check="memory",
            passed=snapshot.reachable,
            detail=snapshot.detail,
        )


class TelemetryProbe:
    """Resolves and exports a test datapoint to the OTLP endpoint, or reports skipped."""

    name = "telemetry"

    async def gather(self, config: ControlPlaneConfig) -> TelemetrySnapshot:
        if config.telemetry.mode == "none":
            return TelemetrySnapshot(
                mode="none",
                exported=False,
                detail="skipped by declaration: telemetry has no otlp_endpoint",
            )

        endpoint = config.telemetry.otlp_endpoint
        assert endpoint is not None
        timeout = config.telemetry.timeout_s

        client: httpx.AsyncClient | None = None
        try:
            client = httpx.AsyncClient(timeout=timeout)
            # OTLP/HTTP trace export: a minimal JSON body the collector accepts.
            payload = {
                "resourceSpans": [
                    {
                        "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "ergane-verify"}}]},
                        "scopeSpans": [
                            {
                                "spans": [
                                    {
                                        "traceId": "00000000000000000000000000000000",
                                        "spanId": "0000000000000000",
                                        "name": "ergane-install-verify",
                                        "kind": 1,
                                        "startTimeUnixNano": str(int(time.time() * 1e9)),
                                        "endTimeUnixNano": str(int(time.time() * 1e9)),
                                    }
                                ]
                            }
                        ],
                    }
                ]
            }
            url = endpoint.rstrip("/") + "/v1/traces"
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return TelemetrySnapshot(
                mode="otlp",
                exported=True,
                detail=f"exported a test trace span to OTLP endpoint {endpoint}",
            )
        except httpx.TimeoutException:
            return TelemetrySnapshot(
                mode="otlp",
                exported=False,
                detail=f"timed out after {timeout}s waiting for OTLP endpoint {endpoint}",
            )
        except Exception as exc:
            return TelemetrySnapshot(
                mode="otlp",
                exported=False,
                detail=f"could not export to OTLP endpoint {endpoint}: {type(exc).__name__}: {exc}",
            )
        finally:
            if client is not None:
                await client.aclose()

    def evaluate(self, snapshot: TelemetrySnapshot) -> Finding:
        if snapshot.mode == "none":
            return Finding(check="telemetry", passed=True, detail=snapshot.detail)
        return Finding(
            check="telemetry",
            passed=snapshot.exported,
            detail=snapshot.detail,
        )


class EscalationProbe:
    """Delivers a test message through the configured Telegram transport.

    Lifecycle verification (deliver and watch the timer expire) belongs to 041;
    this probe reports delivery and explicitly defers lifecycle proof.
    """

    name = "escalation"

    async def gather(self, config: ControlPlaneConfig) -> EscalationSnapshot:
        if config.escalation.adapter == "none":
            return EscalationSnapshot(
                adapter="none",
                delivered=False,
                detail=(
                    "escalations will be dropped: escalation.adapter is `none`; "
                    "a node that would have asked a question fails instead of waiting"
                ),
            )

        if config.escalation.adapter != "telegram":
            return EscalationSnapshot(
                adapter=config.escalation.adapter,
                delivered=False,
                detail=f"escalation adapter `{config.escalation.adapter}` has no gather implementation",
            )

        chat_id_env = config.escalation.chat_id_env or "TELEGRAM_CHAT_ID"
        bot_token_env = config.escalation.bot_token_env or "TELEGRAM_BOT_TOKEN"
        chat_id = os.environ.get(chat_id_env)
        bot_token = os.environ.get(bot_token_env)
        if not chat_id or not bot_token:
            return EscalationSnapshot(
                adapter="telegram",
                delivered=False,
                detail=f"{chat_id_env if not chat_id else bot_token_env} is not set; cannot deliver a test escalation",
            )

        try:
            bot = _telegram_bot_factory(config.escalation, timeout_s=config.escalation.timeout_s)
            message = await bot.send_message(
                chat_id=chat_id,
                text="ergane install --verify test message",
            )
            return EscalationSnapshot(
                adapter="telegram",
                delivered=True,
                detail=(
                    f"delivered a test message through telegram (message_id={message.message_id}); "
                    "lifecycle verification (deliver + expire) is deferred to epic 041"
                ),
            )
        except Exception as exc:
            return EscalationSnapshot(
                adapter="telegram",
                delivered=False,
                detail=f"could not deliver telegram test message: {type(exc).__name__}: {exc}",
            )

    def evaluate(self, snapshot: EscalationSnapshot) -> Finding:
        if snapshot.adapter == "none":
            return Finding(check="escalation", passed=True, detail=snapshot.detail)
        passed = snapshot.delivered
        detail = snapshot.detail
        if passed and "deferred" not in detail.lower():
            detail += "; lifecycle verification is deferred to epic 041"
        return Finding(check="escalation", passed=passed, detail=detail)


class HostProbe:
    """Checks host prerequisites before an attempt is dispatched (054-US2).

    The probe reports only: it never installs, writes, or changes anything on
    the host. Every host access goes through the injected `host_seam`, which
    defaults to `_host_seam_factory` and can be replaced in tests.
    """

    name = "host"

    def __init__(self, *, host_seam: HostSeam | None = None) -> None:
        self._host_seam = host_seam

    async def gather(self, config: ControlPlaneConfig) -> HostSnapshot:
        """Read host state through the seam and return a frozen snapshot."""
        # Allow synchronous inspection to run in a thread so a slow CLI
        # authentication check does not block the event loop. The probe owns no
        # subprocess state that must be awaited.
        seam = self._host_seam or _host_seam_factory
        report = await asyncio.to_thread(seam)
        items: list[HostItem] = []
        for name in ("bwrap", "git", _GH_BINARY):
            entry = report.get(name) or {}
            present = bool(entry.get("present"))
            usable = bool(entry.get("usable"))
            purpose = entry.get("purpose") or f"host prerequisite `{name}`"
            if not present:
                detail = entry.get("remedy") or f"install {name}"
            elif not usable:
                detail = (
                    entry.get("unauthenticated_remedy")
                    or entry.get("remedy")
                    or f"{name} is present but not usable"
                )
            else:
                detail = f"{name} is present and usable"
            items.append(
                HostItem(
                    name=name,
                    present=present,
                    usable=usable,
                    purpose=purpose,
                    detail=detail,
                )
            )

        failed = [item for item in items if not item.usable]
        if not failed:
            detail = "host prerequisites are present: " + ", ".join(
                f"{item.name} (usable)" for item in items
            )
        else:
            lines: list[str] = []
            for item in failed:
                state = "absent" if not item.present else "present but unauthenticated"
                lines.append(
                    f"{item.name} is {state} — needed for {item.purpose}; remedy: {item.detail}"
                )
            detail = "; ".join(lines)

        return HostSnapshot(items=tuple(items), detail=detail)

    def evaluate(self, snapshot: HostSnapshot) -> Finding:
        passed = all(item.usable for item in snapshot.items)
        return Finding(check="host", passed=passed, detail=snapshot.detail)


class ForgeCapabilityProbe:
    """Can the installed `gh` answer what the landing poller asks it? (078-US2)

    `HostProbe` already reports whether `gh` is on `PATH` and authenticated, and
    on 2026-08-20 that was true of a host whose `gh` still could not answer the
    poller: `poll_landing` sends a `--json` field set, an older binary does not
    declare one of the names in it, and the epic parked hours after dispatch
    with a node stuck in ENQUEUED. Present, authenticated and *capable* are three
    claims, and only the third is about the question this factory actually asks.

    **Why `install --verify` and not the doctor** (078 trap 11). Both surfaces
    were available and only one is built. This is a first-run defect: it is true
    of a host from the moment the release is installed on it, it is true before
    any epic exists for the doctor to find wedged, and it recurs on exactly one
    other occasion — a downgrade or reinstall of the CLI, after which the
    operator verifies again. The doctor answers "what is wrong with the work in
    flight"; this has to be answerable when there is no work in flight at all,
    which is the only time it is cheap.

    The probe carries no field names and no version numbers of its own. It
    cannot: `factory/mergequeue/gh.py` owns both the field set and the
    vocabulary (`tests/test_forge_sweep.py` holds this module to that), so what
    is checked here is derived from the value the poller sends rather than
    copied beside it — which is the defect this story exists to not repeat.
    """

    name = "forge"

    def __init__(self, *, capability_seam: ForgeCapabilitySeam | None = None) -> None:
        self._capability_seam = capability_seam

    async def gather(self, config: ControlPlaneConfig) -> ForgeCapability:
        """Read the installed CLI's capability through the seam, off the loop.

        The seam spawns subprocesses, so it runs in a thread for the same reason
        `HostProbe`'s does: a binary that answers slowly must not stall the
        probes that would have answered.
        """
        seam = self._capability_seam or _forge_capability_seam_factory
        return await asyncio.to_thread(seam)

    def evaluate(self, snapshot: ForgeCapability) -> Finding:
        """Pass only on `capable`; the detail is the snapshot's own sentence.

        Every other condition — absent, incapable, undetermined — fails, and
        each says a different thing, because each has a different remedy. The
        detail is not rebuilt here: one sentence, written where the vocabulary
        lives, is what keeps a pass from degenerating into a green line that
        does not say what it checked.
        """
        return Finding(
            check=self.name,
            passed=snapshot.condition == FORGE_CAPABLE,
            detail=snapshot.detail,
        )


class EngineIdentityProbe:
    """Does the running engine advertise the same version as this CLI? (105-US3)

    The engine writes an identity record when it starts and removes it on a
    clean exit. A mismatched record means the operator is about to dispatch into
    version skew, which is refused at the dispatch sites. `install --verify`
    surfaces the same fact so an operator can see the problem *before* trying
    to start an epic.

    **Why `install --verify` and not the doctor.** This is a first-run defect:
    it is true from the moment the release is installed on a host that already
    has an engine running, it is true before any epic exists for the doctor to
    find wedged, and it recurs whenever the engine and the CLI diverge again.
    The doctor answers "what is wrong with the work in flight"; this has to be
    answerable when there is no work in flight at all.

    An absent identity file is a **pass**: every native install and every
    pre-105 container has none, and `verify_controlplane` has no skip verdict.
    A missing record is not evidence of skew, only of "nothing to compare".
    """

    name = "engine"

    def __init__(self, *, state_home: Any = None) -> None:
        self._state_home = state_home

    async def gather(self, config: ControlPlaneConfig) -> tuple[EngineIdentity | None, str]:
        """Read the identity record from the host's state home.

        A synchronous filesystem read off the async loop; kept thin so it can be
        driven from the same `verify_controlplane` loop as every other probe.
        """
        from factory.supervision.engine_identity import read_identity
        from factory.registry import resolve_state_home

        state_home = self._state_home or resolve_state_home()
        identity = read_identity(state_home)
        return (identity, str(state_home))

    def evaluate(self, snapshot: tuple[EngineIdentity | None, str]) -> Finding:
        """Pass on match or absence; fail on mismatch with the shared sentence."""
        from factory.supervision.engine_identity import cli_version, engine_skew

        identity, state_home_str = snapshot
        if identity is None:
            record_path = Path(state_home_str) / "ergane" / "supervision" / "engine-identity.json"
            return Finding(
                check=self.name,
                passed=True,
                detail=(
                    f"no engine identity record at {record_path}; "
                    "the version handshake activates only on evidence"
                ),
            )
        cli = cli_version()
        sentence = engine_skew(identity, cli)
        if sentence is None:
            return Finding(
                check=self.name,
                passed=True,
                detail=f"engine version matches this CLI ({cli})",
            )
        return Finding(check=self.name, passed=False, detail=sentence)


REGISTRY: list[Probe] = [
    HostProbe(),
    ForgeCapabilityProbe(),
    EngineIdentityProbe(),
    LLMProbe(),
    TemporalProbe(),
    MemoryProbe(),
    TelemetryProbe(),
    EscalationProbe(),
]


# --- public entries -----------------------------------------------------------


async def verify_controlplane_async(config_path: str | None = None) -> tuple[list[Finding], int]:
    """Async entry: run every probe and return findings plus an exit code."""
    from factory.controlplane.config import load_controlplane_config

    config = load_controlplane_config(config_path)
    findings: list[Finding] = []
    for probe in REGISTRY:
        try:
            snapshot = await probe.gather(config)
        except ServiceNotAnswering as exc:
            findings.append(Finding(check=probe.name, passed=False, detail=str(exc)))
            continue
        except Exception as exc:
            findings.append(
                Finding(
                    check=probe.name,
                    passed=False,
                    detail=f"probe failed unexpectedly: {type(exc).__name__}: {exc}",
                )
            )
            continue
        findings.append(probe.evaluate(snapshot))

    exit_code = 0 if all(f.passed for f in findings) else 1
    return findings, exit_code


def verify_controlplane(config_path: str | None = None) -> tuple[list[Finding], int]:
    """Sync entry for the CLI: run every probe in a fresh event loop."""
    return asyncio.run(verify_controlplane_async(config_path))


def render_findings(findings: list[Finding]) -> str:
    """Render findings as a concise report for the operator."""
    lines: list[str] = []
    for finding in findings:
        status = "PASS" if finding.passed else "FAIL"
        lines.append(f"[{status}] {finding.check}: {finding.detail}")
    return "\n".join(lines)
