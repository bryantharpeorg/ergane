"""The `ergane install` walkthrough (033 US3, FR-007).

The interview asks each subsystem's *mode* first and then only the fields that
mode needs, writes the control-plane config, and ends by running US2's
verification — so the last thing install prints is proof rather than hope.

Four properties FR-007 requires, and where each lives:

- **Validated at entry with the parser's own rules.** There is no second rule
  table. The interview keeps a complete in-progress document, renders it after
  every answer, and hands the rendered text to `parse_controlplane_config`; a
  refusal is shown to the operator and the question is asked again. The text
  that is finally written is the very text that parsed. This is 034/us1's
  discipline (`factory/cli/init.py`) applied to a second file, and it means a
  rule added to the parser is enforced by the interview the same day.
- **An existing config is loaded as defaults.** Re-running edits rather than
  clobbers, and because the file is rendered from a canonical form, a re-run
  that changes one answer moves exactly one block (plan trap 4).
- **An exclusive lock for the whole run**, taken before the first question so
  that a second install is refused before it collects answers it cannot write —
  `factory.locking`, shared with 034's registry lock.
- **The verification runs last**, inside the lock, and its findings are the
  command's final output.

The prompter is 034/us1's seam (`factory.cli.init._prompter_factory`), reused
rather than reinvented: a second prompter convention one epic later is the drift
the rename was spent avoiding (plan trap 6).
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import dataclasses
import os
import re
import tempfile
import tomllib
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from factory.cli import init as init_module
from factory.cli.errors import EXIT_OK, EXIT_USER, OperatorError
import factory.config as config_module
from factory.controlplane.canary.probe import (
    CanaryResult,
    probe_judge_canary,
)
from factory.controlplane.config import (
    DIRECT_MODE_SURRENDERED_PROPERTIES_TEXT,
    KNOWN_LL_MODES,
    RULE_SECRET_VALUE_NOT_REFERENCE,
    ControlPlaneConfigError,
    _SECRET_PATTERNS,
    controlplane_document,
    load_controlplane_config,
    parse_controlplane_config,
    render_controlplane_document,
    resolve_config_path,
)
from factory.controlplane.verify import render_findings, verify_controlplane
from factory.discovery.llm_enrichment import EnrichmentRecord, enrich_aliases
from factory.discovery.llm_scanner import (
    EndpointClassification,
    ScanResult,
    scan_endpoints,
)
from factory.discovery.proposal import (
    PERSONA_REQUIREMENTS,
    OperatorChoice,
    ProposedMapping,
    Refusal,
    build_proposal,
)
from factory.locking import LockUnavailable, exclusive_lock

# 104-US5: the engine container's four modules — render, consent, write, bring
# up. By module rather than by symbol, so rebinding a seam on one of them
# (`container_engine._run_compose`) is seen at this file's call sites.
# `container_project.derived_environment_names` imports *this* module from
# inside its body, which is where the cycle between the two is broken.
from factory.supervision import (
    container_engine,
    container_manifest,
    container_profile,
    container_project,
)
from factory.notify.service import DEFAULT_TEMPORAL_NAMESPACE
from factory.usage.litellm_client import LiteLLMClient

#: How long `ergane install` waits for another install to finish before it
#: refuses. Overridable per invocation with `--lock-timeout`.
DEFAULT_LOCK_TIMEOUT_S = 30.0

#: The answer that clears an optional field that currently has a value.
CLEAR = "-"

#: Sentinel returned by `_controlplane_default` when an interview field has no
#: safe documented default. A non-interactive path that omits such a field must
#: refuse before writing anything (FR-004).
_NO_DEFAULT = object()


#: Optional interview fields: an empty or omitted answer means "leave absent".
_OPTIONAL_INTERVIEW_FIELDS = frozenset(
    {
        ("memory", "api_key_env"),
        ("temporal", "api_key_env"),
        ("telemetry", "otlp_endpoint"),
        ("escalation", "bot_token_env"),
        ("escalation", "chat_id_env"),
    }
)


def _deep_get(document: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    """Return the value at `path`, or `None` if any step is missing."""
    target: Any = document
    for step in path:
        if not isinstance(target, dict) or step not in target:
            return None
        target = target[step]
    return target


def _deep_set(document: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    """Create intermediate dicts as needed and set `path` to `value`."""
    target: Any = document
    for step in path[:-1]:
        if step not in target or not isinstance(target[step], dict):
            target[step] = {}
        target = target[step]
    target[path[-1]] = value


def _controlplane_default(document: Mapping[str, Any], field: tuple[str, ...]) -> Any:
    """Return the documented default for an interview field.

    This is the shared defaults source the non-interactive paths read.  The
    interactive path displays the same values through `BLANK_DOCUMENT` for fields
    that have a safe default; fields with no safe default keep a placeholder in
    `BLANK_DOCUMENT` only so the full-parser checks in `_ask` stay valid while
    the interview is in progress (FR-006).

    A returned value of `_NO_DEFAULT` means the field is required and must be
    supplied by the operator or the answer file.
    """
    if field == ("version",):
        return 1

    if field == ("llm", "mode"):
        return "gateway"
    if field == ("llm", "base_url"):
        return "http://127.0.0.1:4000"

    llm_mode = _deep_get(document, ("llm", "mode")) or "gateway"
    if field == ("llm", "master_key_env") and llm_mode == "gateway":
        return "ERGANE_LLM_MASTER_KEY"
    if field == ("llm", "api_key_env") and llm_mode == "direct":
        return "ERGANE_LLM_API_KEY"

    if field == ("memory", "backend"):
        return "none"

    memory_backend = _deep_get(document, ("memory", "backend")) or "none"
    if field == ("memory", "url") and memory_backend == "hindsight":
        return "http://127.0.0.1:8888"

    if field == ("temporal", "mode"):
        return "external"

    temporal_mode = _deep_get(document, ("temporal", "mode")) or "external"
    if field == ("temporal", "address") and temporal_mode == "external":
        return "127.0.0.1:7233"
    if field == ("temporal", "namespace") and temporal_mode == "external":
        return DEFAULT_TEMPORAL_NAMESPACE
    if field == ("temporal", "tls_enabled"):
        return False

    if field == ("telemetry", "otlp_endpoint"):
        return None

    # Escalation has no safe default: every adapter requires standing up a
    # third-party service.  US3 adds `"none"` as a *selectable* value, not a
    # default.
    if field == ("escalation", "adapter"):
        return _NO_DEFAULT

    # The remaining fields are optional and default to "absent".
    if field in _OPTIONAL_INTERVIEW_FIELDS:
        return None

    return _NO_DEFAULT


# ---------------------------------------------------------------------------
# Where the engine runs (104-US1)
# ---------------------------------------------------------------------------

#: The engine runs in a Docker container — spelled **the engine container**
#: everywhere, because three unrelated things in this tree are called a
#: container and only one of them is this.
ENGINE_CONTAINER = "container"
#: Today's path: the engine runs on the host under systemd user units.
ENGINE_SYSTEMD = "systemd"
#: Today's exit: configure the control plane and stop there.
ENGINE_NONE = "none"

#: In offer order — the container first, because it is what this spec exists to
#: make easy. `_offered_engine_backend` reverses the order when no daemon
#: answers, so the offer always leads with the backend it is defaulting to.
ENGINE_BACKENDS = (ENGINE_CONTAINER, ENGINE_SYSTEMD, ENGINE_NONE)

#: The backend the flag-driven paths run under. `--non-interactive` and
#: `--from-file` configure only and return before any engine step could run
#: (US1-S3), so the answer is declared here rather than asked and there is no
#: question for either path to grow.
DEFAULT_ENGINE_BACKEND = ENGINE_NONE


#: What a blank host is offered before it has answered anything. The values
#: here are the defaults the interactive path displays; the non-interactive
#: path resolves the same fields from `_controlplane_default` (FR-006).  Fields
#: whose only safe value is operator-supplied keep a placeholder so the
#: full-parser checks in `_ask` stay valid while the interview is in progress;
#: that placeholder-escape issue is pre-existing and is fixed from the shared
#: defaults source in 061/US3.
BLANK_DOCUMENT: dict[str, Any] = {
    "version": 1,
    "llm": {
        "mode": "gateway",
        "base_url": "http://127.0.0.1:4000",
        "master_key_env": "ERGANE_LLM_MASTER_KEY",
    },
    "memory": {"backend": "none"},
    "temporal": {
        "mode": "external",
        "address": "127.0.0.1:7233",
        "namespace": DEFAULT_TEMPORAL_NAMESPACE,
    },
    "telemetry": {},
    "escalation": {
        "adapter": "telegram",
        "bot_token_env": "TELEGRAM_BOT_TOKEN",
        "chat_id_env": "TELEGRAM_CHAT_ID",
    },
}

#: Seeds used when an operator switches a block to a mode it was not in.
_GATEWAY_SEED: dict[str, Any] = dict(BLANK_DOCUMENT["llm"])
_DIRECT_SEED: dict[str, Any] = {
    "mode": "direct",
    "base_url": "http://127.0.0.1:4000",
    "api_key_env": "ERGANE_LLM_API_KEY",
}
_HINDSIGHT_SEED: dict[str, Any] = {
    "backend": "hindsight",
    "url": "http://127.0.0.1:8888",
}

#: Seam: how the interview probes the network. Rebound in US3 tests.
_scan_endpoints = scan_endpoints

#: Seam: how the persona step fetches capability metadata. Rebound in US4 tests.
_enrich_aliases = enrich_aliases

#: Seam: how the persona step lists aliases from the confirmed gateway.
_fetch_aliases_from_gateway = None  # type: ignore[var-assign]

#: Seam: how the persona step probes a chosen alias with a 1-token completion.
_probe_one_token = None  # type: ignore[var-assign]

#: Seam: how the persona step runs the judge canary.


def _default_fetch_aliases_from_gateway(
    base_url: str, master_key_env: str
) -> list[str]:
    """List aliases served by the confirmed gateway."""

    async def _fetch() -> list[str]:
        master_key = os.environ.get(master_key_env)
        if not master_key:
            return []
        client = LiteLLMClient(base_url=base_url, master_key=master_key, timeout=10.0)
        try:
            return sorted(await client.list_model_ids())
        except Exception:
            return []
        finally:
            await client.aclose()

    return asyncio.run(_fetch())


async def _default_probe_judge_canary(
    alias: str, base_url: str, master_key_env: str
) -> Any:
    """Run the judge canary pointed at the confirmed gateway."""
    return await probe_judge_canary(
        alias,
        client_factory=lambda: LiteLLMClient(
            base_url=base_url,
            master_key=os.environ.get(master_key_env, ""),
            timeout=30.0,
        ),
    )


def _sync_probe_judge_canary(alias: str, base_url: str, master_key_env: str) -> Any:
    """Synchronous entry for the canary seam."""
    return asyncio.run(_default_probe_judge_canary(alias, base_url, master_key_env))


_probe_judge_canary = _sync_probe_judge_canary


# ---------------------------------------------------------------------------
# Persona registry step (US4)
# ---------------------------------------------------------------------------



async def _async_probe_one_token(
    alias: str,
    base_url: str,
    master_key_env: str,
    timeout: float = 30.0,
) -> tuple[bool, str]:
    """Async implementation: probe one alias with a 1-token completion."""
    from factory.controlplane.canary.probe import _key_is_model_constrained

    master_key = os.environ.get(master_key_env)
    if not master_key:
        return False, f"{master_key_env} is not set"

    client = LiteLLMClient(base_url=base_url, master_key=master_key, timeout=timeout)
    minted_key: str | None = None
    try:
        try:
            minted_key = await client.issue_key(
                key_alias="ergane-install-persona-probe",
                models=[alias],
                ttl="5m",
            )
        except Exception as exc:
            return False, f"could not mint probe key for `{alias}`: {type(exc).__name__}: {exc}"
        try:
            info = await client.get_key_info(minted_key)
        except Exception as exc:
            return False, f"gateway minted a key but /key/info failed: {type(exc).__name__}: {exc}"
        if not _key_is_model_constrained(info, alias):
            return False, f"gateway minted a key for `{alias}` but it is not model-constrained"
        request = {
            "model": alias,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
        }
        try:
            response_data = await client.chat_completion(request)
            completed = bool(response_data.get("choices"))
        except Exception as exc:
            return False, f"1-token completion failed for `{alias}`: {type(exc).__name__}: {exc}"
        if completed:
            return True, f"completed 1-token completion for alias `{alias}`"
        return False, f"1-token completion for alias `{alias}` returned no choices"
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


def _default_probe_one_token(
    alias: str,
    base_url: str,
    master_key_env: str,
    timeout: float = 30.0,
) -> tuple[bool, str]:
    """Synchronous entry for the 1-token probe seam."""
    return asyncio.run(_async_probe_one_token(alias, base_url, master_key_env, timeout))


# Fill in the module-level seam bindings now that the implementations exist.
_fetch_aliases_from_gateway = _default_fetch_aliases_from_gateway
_probe_one_token = _default_probe_one_token


def _update_persona_lines(text: str, updates: dict[str, dict[str, Any]]) -> str:
    """Return `text` with only the listed persona model/fallback lines changed.

    Preserves comments, ordering and every field other than `model`/`fallback`.
    Values are written unquoted when they are simple scalars; `None` becomes
    the literal `null`.
    """

    def _scalar(value: Any) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    lines = text.splitlines()
    for name, fields in updates.items():
        in_block = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if in_block and stripped and not line.startswith(" "):
                in_block = False
            if stripped == f"{name}:" or stripped.startswith(f"{name}:"):
                in_block = True
                continue
            if not in_block:
                continue
            for field in ("model", "fallback"):
                if field not in fields:
                    continue
                if stripped.startswith(f"{field}:"):
                    indent = len(line) - len(line.lstrip())
                    lines[i] = f"{' ' * indent}{field}: {_scalar(fields[field])}"
                    break
    return "\n".join(lines) + "\n"


def _write_personas_registry(path: Path, text: str) -> None:
    """Write `text` to `path` atomically and validate it by loading it back."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".personas.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        Path(tmp).chmod(0o600)
        Path(tmp).replace(path)
    except Exception:
        try:
            Path(tmp).unlink(missing_ok=True)
        except Exception:
            pass
        raise
    try:
        config_module.load_personas(str(path))
    except config_module.ConfigError as exc:
        raise OperatorError(
            f"wrote {path} but it does not load as a persona registry: {exc}",
            code=EXIT_USER,
        ) from None


#: Personas that need a gateway alias, in the order they are presented.
_GATEWAY_PERSONA_ORDER: tuple[str, ...] = (
    "implementer",
    "judge",
    "debugger",
    "closer",
    "architect",
    "researcher",
)


def _persona_prompt_text(result: ProposedMapping | OperatorChoice, slot: str) -> tuple[str, str]:
    """Return (prompt, default) for a persona primary/fallback line.

    The default is the proposed alias; the prompt includes the reason.
    """
    if isinstance(result, ProposedMapping):
        if slot == "primary":
            return f"{result.persona} {slot} ({result.reason})", result.primary
        return f"{result.persona} {slot} ({result.reason})", result.fallback
    # OperatorChoice: no classified candidate qualified.
    candidates = ", ".join(result.candidates) if result.candidates else "(none)"
    return (
        f"{result.persona} {slot}: no classified candidate qualified; choose from {candidates}",
        "",
    )


def _ask_persona_alias(
    prompter: Any,
    name: str,
    slot: str,
    proposal: dict[str, ProposedMapping | OperatorChoice | Refusal],
    candidates: list[EnrichmentRecord],
    chosen_primary: dict[str, str],
) -> tuple[str, dict[str, ProposedMapping | OperatorChoice | Refusal], list[EnrichmentRecord]]:
    """Ask the operator for one persona slot and return the chosen alias.

    On an unsatisfiable proposal, raises `OperatorError`.  The returned
    proposal and candidate list reflect any override the operator typed.
    """
    from factory.config import Persona, WriteScope

    # Build a synthetic Persona dict for the proposal builder: the current
    # primary choices influence the judge's ranking.
    personas: dict[str, Persona] = {}
    for pname in _GATEWAY_PERSONA_ORDER:
        personas[pname] = Persona(
            name=pname,
            agent="claude-code",
            model=chosen_primary.get(pname),
            fallback=None,
            skills=(),
            write_scope=WriteScope.WORKTREE,
            needs_worktree=True,
        )

    result = proposal.get(name)
    if isinstance(result, Refusal):
        raise OperatorError(
            f"persona `{name}` cannot be satisfied: {result.requirement}; "
            f"considered aliases: {', '.join(result.candidates)}",
            code=EXIT_USER,
        )

    prompt, default = _persona_prompt_text(result, slot)
    answer = prompter.ask(prompt, default=default or None).strip()
    chosen = answer if answer else (default or "")

    # If the operator picked an alias not in the current candidate list,
    # synthesize a classified record so the proposal builder knows about it.
    if chosen and chosen not in {r.alias for r in candidates}:
        candidates = list(candidates) + [
            EnrichmentRecord(
                alias=chosen,
                tool_calling=True,
                structured_output=True,
                reasoning=True,
                detail="operator override",
            )
        ]
        # Rebuild proposal so the judge can avoid this alias if it's the implementer.
        proposal = build_proposal(personas, tuple(candidates))
        result = proposal.get(name)
        if isinstance(result, Refusal):
            # Report every alias that was originally available, including the one
            # that just failed, so the operator sees the full candidate list.
            all_aliases = tuple(r.alias for r in records)
            raise OperatorError(
                f"persona `{name}` cannot be satisfied: {result.requirement}; "
                f"considered aliases: {', '.join(all_aliases)}",
                code=EXIT_USER,
            )

    return chosen, proposal, candidates


def _interview_personas(
    prompter: Any,
    document: dict[str, Any],
    personas_path: Path,
) -> None:
    """Propose, confirm, probe and write the persona registry (US4).

    Uses the confirmed LLM block from `document`; never sends credentials to an
    unconfirmed endpoint.  Writes only after every chosen alias has passed its
    probe.
    """
    base_url = document["llm"]["base_url"]
    master_key_env = document["llm"]["master_key_env"]

    # Load the existing seeded registry; its non-alias fields are preserved.
    personas = config_module.load_personas(str(personas_path))

    # Fetch and enrich aliases from the confirmed gateway.
    aliases = _fetch_aliases_from_gateway(base_url, master_key_env)
    records = _enrich_aliases(
        base_url, aliases, master_key_env=master_key_env, timeout=10.0
    )
    candidates: list[EnrichmentRecord] = list(records)

    # Build the initial proposal using empty primary choices.
    proposal = build_proposal(personas, tuple(candidates))

    chosen_primary: dict[str, str] = {}
    chosen_fallback: dict[str, str] = {}
    tried_aliases: dict[str, set[str]] = {name: set() for name in _GATEWAY_PERSONA_ORDER}

    # Primary pass.
    for name in _GATEWAY_PERSONA_ORDER:
        while True:
            result = proposal.get(name)
            if isinstance(result, Refusal):
                # Report every alias that was originally available, including the one
                # that just failed, so the operator sees the full candidate list.
                all_aliases = tuple(r.alias for r in records)
                raise OperatorError(
                    f"persona `{name}` cannot be satisfied: {result.requirement}; "
                    f"considered aliases: {', '.join(all_aliases)}",
                    code=EXIT_USER,
                )

            prompt, default = _persona_prompt_text(result, "primary")
            answer = prompter.ask(prompt, default=default or None).strip()
            chosen = answer if answer else (default or "")

            if chosen in tried_aliases[name]:
                # Operator picked an alias that already failed for this slot.
                print(f"  `{chosen}` already failed for {name}; choose another")
                continue

            passed, detail = _probe_one_token(chosen, base_url, master_key_env)
            print(f"  probing {name} -> {chosen}: {'PASS' if passed else 'FAIL'}")
            if passed and name == "judge":
                canary = _probe_judge_canary(chosen, base_url, master_key_env)
                if not canary.passed:
                    passed = False
                    detail = canary.detail

            if passed:
                chosen_primary[name] = chosen
                break

            # Probe failed: drop the alias from candidates and re-rank.
            tried_aliases[name].add(chosen)
            candidates = [r for r in candidates if r.alias != chosen]
            proposal = build_proposal(personas, tuple(candidates))
            print(f"  `{chosen}` failed ({detail}); re-ranking {name} candidates")

    # Fallback pass: each line is explicitly presented, never defaulted through.
    for name in _GATEWAY_PERSONA_ORDER:
        while True:
            result = proposal.get(name)
            if isinstance(result, (Refusal, OperatorChoice)):
                # No classified candidate for fallback; offer the primary as fallback.
                default_fallback = chosen_primary[name]
            else:
                default_fallback = result.fallback

            prompt = f"{name} fallback (press Enter to accept `{default_fallback}`)"
            answer = prompter.ask(prompt, default=default_fallback).strip()
            chosen = answer if answer else default_fallback

            if chosen in tried_aliases[name]:
                print(f"  `{chosen}` already failed for {name}; choose another")
                continue

            passed, detail = _probe_one_token(chosen, base_url, master_key_env)
            print(f"  probing {name} fallback -> {chosen}: {'PASS' if passed else 'FAIL'}")
            if passed:
                chosen_fallback[name] = chosen
                break

            tried_aliases[name].add(chosen)
            candidates = [r for r in candidates if r.alias != chosen]
            proposal = build_proposal(personas, tuple(candidates))
            print(f"  `{chosen}` failed ({detail}); re-ranking {name} fallback candidates")

    # Subscription personas: confirm the CLI-side model name, never probe.
    subscription_updates: dict[str, dict[str, Any]] = {}
    for name, persona in personas.items():
        if not persona.is_llm or persona.routes_through_gateway:
            continue
        if persona.agent == config_module.DETERMINISTIC_AGENT:
            continue
        current_model = persona.model or ""
        prompt = f"{name} model (subscription, press Enter to accept `{current_model}`)"
        answer = prompter.ask(prompt, default=current_model).strip()
        chosen = answer if answer else current_model
        subscription_updates[name] = {"model": chosen}

    # Collect all updates and write once.
    updates: dict[str, dict[str, Any]] = {}
    for name in _GATEWAY_PERSONA_ORDER:
        updates[name] = {
            "model": chosen_primary[name],
            "fallback": chosen_fallback[name],
        }
    updates.update(subscription_updates)

    original_text = personas_path.read_text(encoding="utf-8")
    new_text = _update_persona_lines(original_text, updates)
    _write_personas_registry(personas_path, new_text)

    print(f"wrote {personas_path}")
    for name, fields in updates.items():
        if "model" in fields:
            print(f"  {name}: model={fields['model']}, fallback={fields.get('fallback')}")


def _ask_engine_backend(
    prompter: Any,
    document: dict[str, Any],
    path: Path,
    offered: _OfferedEngine,
) -> str:
    """Ask the one question, through `_ask`, and return the answer as a value.

    The `apply` captures instead of applying: the engine backend is a property
    of the *installation*, not of the control plane, and `_TOP_LEVEL_KEYS`
    refuses any key that is not one of the five subsystems by name.  The record
    is the generated project on disk (plan R1), so the document `_ask` renders
    and re-parses here comes back exactly as it went in — which also re-proves
    it still parses at the last question, for free.

    `_ask`'s own refuse-and-re-ask loop is driven by the parser and cannot judge
    an answer the parser never sees, so an unrecognised backend is named and
    re-asked here.  Letting it fall through as "not container" would configure
    only, silently, on a typo.
    """
    captured: list[Any] = []

    def _capture(candidate: dict[str, Any], value: Any) -> dict[str, Any]:
        captured.append(value)
        return candidate

    while True:
        _ask(
            prompter,
            f"engine backend ({offered.choices})",
            document,
            path,
            default=offered.backend,
            apply=_capture,
        )
        answer = captured[-1]
        if answer in ENGINE_BACKENDS:
            return str(answer)
        typed = "" if answer is None else str(answer)
        print(f"  `{typed}` is not an engine backend; choose {offered.choices}")


def _interview_engine(
    prompter: Any,
    document: dict[str, Any],
    path: Path,
    *,
    requested: str | None = None,
) -> str:
    """Ask where the engine runs, and return the choice (104-US1).

    A step of its own, called from `install_command` with an injected prompter —
    103's `_interview_personas` is the precedent, and the reason is the same one:
    `_interview` is consumed positionally by `_FilePrompter` from a list
    `_plan_file_answers` builds, and five test modules index that list. A
    question added *inside* it desynchronises every answer after it and surfaces
    as a complaint about the wrong prompt.

    Nothing is persisted and nothing is read off disk (plan R2). The choice is
    returned as a value and `install_command` holds it as a local, which is what
    keeps this story concurrent with the generator that will consume it.

    The question is asked when the engine container can actually run — when a
    daemon answers. On a host where none does, install asks nothing new and
    behaves exactly as it does today, which is US1-S1's "the paths I do not
    choose are left exactly as they are today" taken literally. An operator who
    wants the container on such a host says `--engine=container`, and lands on
    the guard below: it is the same guard either way, so the flag is a way to
    reach the capability check without being asked, not a way around it.
    """
    offered = _offered_engine_backend(_docker_daemon_available())

    if requested is not None:
        choice = requested
    elif offered.unavailable_reason is None:
        choice = _ask_engine_backend(prompter, document, path, offered)
    else:
        choice = offered.backend

    # `_ask_temporal` refuses managed mode on a host with no systemd user
    # session, at the answer and before anything is written; this is that guard
    # for the engine container.
    if choice == ENGINE_CONTAINER and offered.unavailable_reason is not None:
        raise OperatorError(offered.unavailable_reason, code=EXIT_USER)

    if choice == ENGINE_CONTAINER:
        # Announced with the answer, not with the act: plan R3 asks every
        # question before anything is done, and `_install_engine_container`
        # below is the acting half, which runs after the persona registry the
        # engine reads has been written.
        print(f"engine backend: {choice}")
    return choice


def _install_engine_container(path: Path, prompter: Any) -> int:
    """Generate the engine container's project, bring it up, and verify through
    it (104-US5) — the acting half of the answer `_interview_engine` took.

    The order is the story. **Resolve first, before anything privileged**: that
    is where an install with no build context refuses (R10) and where a path no
    mount covers refuses (trap 4), and both must fire before the sudo prompt.
    **Then consent** (104-US4), which decides the confinement variant and so the
    project — before a byte is written, so a declined load produces a whole
    config-F project rather than half a config-G one. **Then write**, through
    US3's digest manifest. **Then bring up, wait and verify**.

    There is no host-side `verify_controlplane` here: the engine is where the
    factory will actually run, so the battery runs *there* (R8).
    """
    config = load_controlplane_config(str(path))

    project = container_project.resolve_project(config)
    decision = container_profile.load_profile(prompter)
    if decision.confinement != container_project.CONFINEMENT_PROFILE:
        project = container_project.resolve_project(
            config, confinement=decision.confinement
        )

    print("")
    print(container_manifest.write_project(project).render())

    container_engine.bring_up_and_verify(project)
    print("")
    print(f"the engine container is up and verified at {project.directory}.")
    return EXIT_OK


def _refuse_engine_flag_beside_a_flag_driven_path(
    args: argparse.Namespace, requested: str
) -> None:
    """Refuse `--engine` alongside `--non-interactive` / `--from-file` (US1-S3).

    Both paths return before any engine step could run, so honouring the flag is
    impossible — and silently ignoring it discards an explicit operator
    instruction, which is the failure mode worth a message.
    """
    for flag, present in (
        ("--from-file", getattr(args, "from_file", None) is not None),
        ("--non-interactive", bool(getattr(args, "non_interactive", False))),
    ):
        if not present:
            continue
        raise OperatorError(
            f"--engine={requested} cannot be combined with {flag}: that path "
            f"configures only and returns before any engine step could run, so "
            f"its backend is always `{DEFAULT_ENGINE_BACKEND}`. Drop --engine, "
            f"or run the interview without {flag}.",
            code=EXIT_USER,
        )


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def add_install_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the walkthrough's own flags to the `install` subparser."""
    parser.add_argument(
        "--from-file",
        metavar="PATH",
        dest="from_file",
        help=(
            "read interview answers from a TOML file instead of stdin; "
            "documented defaults fill omitted fields, and fields with no safe "
            "default cause a refusal"
        ),
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        dest="non_interactive",
        help=(
            "use documented defaults for every question; fields with no safe "
            "default cause a refusal"
        ),
    )
    parser.add_argument(
        "--lock-timeout",
        type=float,
        default=DEFAULT_LOCK_TIMEOUT_S,
        metavar="SECONDS",
        help=(
            "how long to wait for another `ergane install` to release the "
            f"config lock before refusing (default: {DEFAULT_LOCK_TIMEOUT_S:g})"
        ),
    )


def install_command(args: argparse.Namespace) -> int:
    """Run the interview, write the config, and verify what was written."""
    path = resolve_config_path()
    timeout_s = float(getattr(args, "lock_timeout", DEFAULT_LOCK_TIMEOUT_S))

    # 104-US1: where the engine runs, declared on the command line or asked
    # below. Refused here, before either flag-driven path returns, so an
    # instruction that cannot be honoured is never quietly dropped.
    requested_engine = getattr(args, "engine", None)
    if requested_engine is not None:
        _refuse_engine_flag_beside_a_flag_driven_path(args, requested_engine)

    if getattr(args, "from_file", None) is not None:
        return _install_from_file(Path(args.from_file), path, timeout_s)

    if getattr(args, "non_interactive", False):
        return _install_non_interactive(path, timeout_s)

    personas_dir = config_module._xdg_config_home() / config_module.DEFAULT_REGISTRY_REL.parent
    try:
        personas_path, personas_created = _seed_personas_registry(personas_dir)
    except OSError as error:
        raise OperatorError(
            f"cannot seed persona registry at {personas_dir / config_module.REGISTRY_FILENAME}: {error}",
            code=EXIT_USER,
        ) from None

    try:
        with exclusive_lock(path, timeout_s=timeout_s):
            document = _interview(path)
            # 104-US1, plan R3 — ask early, act late: the last question is
            # asked before the first thing is done, so an install that is going
            # to refuse the chosen backend refuses with nothing written. US5
            # acts on this local; US1 only asks.
            engine_backend = _interview_engine(
                init_module._prompter(), document, path, requested=requested_engine
            )
            text = render_controlplane_document(document)
            _write_config(path, text)
            print(f"wrote {path}")
            print(
                f"{'wrote' if personas_created else 'left existing'} {personas_path}"
            )
            # US4: propose, confirm and prove persona aliases before verify runs.
            _interview_personas(
                init_module._prompter(), document, personas_path
            )
            # 104-US5, plan R3 — act late: the engine reads the persona registry
            # that was just written, so this is the earliest point the container
            # can be generated, brought up and verified. The two other backends
            # keep today's host-side verification, unchanged.
            if engine_backend == ENGINE_CONTAINER:
                return _install_engine_container(path, init_module._prompter())
            print("")
            print("verifying the control plane...")
            findings, exit_code = verify_controlplane(str(path))
            print(render_findings(findings))
            return EXIT_OK if exit_code == 0 else EXIT_USER
    except LockUnavailable as error:
        raise OperatorError(
            f"another `ergane install` holds the lock on {path} "
            f"(waited {error.timeout_s:g}s); wait for it to finish, or remove "
            f"{error.target.name}.lock if no install is running",
            code=EXIT_USER,
        ) from None


def _write_config(path: Path, text: str) -> None:
    """Write the config, creating its directory, with owner-only permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)


def _seed_personas_registry(config_home: Path) -> tuple[Path, bool]:
    """Copy the shipped example registry to the operator's config directory.

    Returns ``(target_path, created)``.  If the file already exists it is left
    untouched and ``created`` is ``False``.
    """
    target = config_home / config_module.REGISTRY_FILENAME
    if target.exists():
        return target, False
    config_home.mkdir(parents=True, exist_ok=True)
    target.write_text(config_module.shipped_registry_text(), encoding="utf-8")
    target.chmod(0o600)
    return target, True


# ---------------------------------------------------------------------------
# Shared non-interactive planning (US1/US2)
# ---------------------------------------------------------------------------


def _install_non_interactive(path: Path, timeout_s: float) -> int:
    """Use documented defaults and run the same interview without a terminal."""
    # The blank document is the shared source for fields with safe defaults.
    # Fields with no safe default are left missing and will be reported.
    raw_doc: dict[str, Any] = copy.deepcopy(BLANK_DOCUMENT)
    answers, reports, missing, completed = _plan_file_answers(raw_doc)

    for line in reports:
        print(line)

    if missing:
        raise OperatorError(
            "non-interactive install is missing required fields with no safe default: "
            + ", ".join(sorted(missing)),
            code=EXIT_USER,
        )

    # Validate before taking the lock or writing.
    try:
        parse_controlplane_config(
            render_controlplane_document(completed), source=str(path)
        )
    except ControlPlaneConfigError as refusal:
        raise OperatorError(
            _redact_parser_error(refusal, completed), code=EXIT_USER
        ) from None

    personas_dir = config_module._xdg_config_home() / config_module.DEFAULT_REGISTRY_REL.parent
    try:
        personas_path, personas_created = _seed_personas_registry(personas_dir)
    except OSError as error:
        raise OperatorError(
            f"cannot seed persona registry at {personas_dir / config_module.REGISTRY_FILENAME}: {error}",
            code=EXIT_USER,
        ) from None

    try:
        with exclusive_lock(path, timeout_s=timeout_s):
            document = _interview(path, prompter=_FilePrompter(answers))
            text = render_controlplane_document(document)
            _write_config(path, text)
            print(f"wrote {path}")
            print(
                f"{'wrote' if personas_created else 'left existing'} {personas_path}"
            )
            print("")
            print("verifying the control plane...")
            findings, exit_code = verify_controlplane(str(path))
            print(render_findings(findings))
            return EXIT_OK if exit_code == 0 else EXIT_USER
    except LockUnavailable as error:
        raise OperatorError(
            f"another `ergane install` holds the lock on {path} "
            f"(waited {error.timeout_s:g}s); wait for it to finish, or remove "
            f"{error.target.name}.lock if no install is running",
            code=EXIT_USER,
        ) from None


# ---------------------------------------------------------------------------
# Answer-file driven path (US1)
# ---------------------------------------------------------------------------


class _FilePrompter:
    """A prompter that returns answers planned from an answer file.

    It satisfies the same contract as `factory.cli.init._prompter()`: an
    `ask(prompt, *, default, error)` method returning a string.  Because the
    answer file is pre-validated before the interview begins, an `error`
    argument reaching here means the planned answers do not parse — a drift
    between the planner and the interview that must fail loudly rather than loop.
    """

    def __init__(self, answers: list[str]) -> None:
        self._answers = answers
        self._index = 0

    def ask(
        self, prompt: str, *, default: str | None = None, error: str | None = None
    ) -> str:
        if error is not None:
            raise AssertionError(
                f"file-driven answer was refused by the parser: {error}"
            )
        if self._index >= len(self._answers):
            raise AssertionError(
                f"file-driven prompter ran out of answers at {prompt!r}"
            )
        answer = self._answers[self._index]
        self._index += 1
        return answer


def _install_from_file(answer_path: Path, path: Path, timeout_s: float) -> int:
    """Read answers from a file, validate, and run the same interview."""
    raw_doc = _load_answer_file(answer_path)
    answers, reports, missing, completed = _plan_file_answers(raw_doc)

    for line in reports:
        print(line)

    if missing:
        raise OperatorError(
            "answer file is missing required fields with no safe default: "
            + ", ".join(sorted(missing)),
            code=EXIT_USER,
        )

    # Validate the completed document with the parser before taking the lock or
    # touching the write path.  This is where the secret-shape guard fires for
    # file-supplied values (FR-007).
    try:
        parse_controlplane_config(
            render_controlplane_document(completed), source=str(path)
        )
    except ControlPlaneConfigError as refusal:
        raise OperatorError(
            _redact_parser_error(refusal, completed), code=EXIT_USER
        ) from None

    personas_dir = config_module._xdg_config_home() / config_module.DEFAULT_REGISTRY_REL.parent
    try:
        personas_path, personas_created = _seed_personas_registry(personas_dir)
    except OSError as error:
        raise OperatorError(
            f"cannot seed persona registry at {personas_dir / config_module.REGISTRY_FILENAME}: {error}",
            code=EXIT_USER,
        ) from None

    try:
        with exclusive_lock(path, timeout_s=timeout_s):
            document = _interview(path, prompter=_FilePrompter(answers))
            text = render_controlplane_document(document)
            _write_config(path, text)
            print(f"wrote {path}")
            print(
                f"{'wrote' if personas_created else 'left existing'} {personas_path}"
            )
            print("")
            print("verifying the control plane...")
            findings, exit_code = verify_controlplane(str(path))
            print(render_findings(findings))
            return EXIT_OK if exit_code == 0 else EXIT_USER
    except LockUnavailable as error:
        raise OperatorError(
            f"another `ergane install` holds the lock on {path} "
            f"(waited {error.timeout_s:g}s); wait for it to finish, or remove "
            f"{error.target.name}.lock if no install is running",
            code=EXIT_USER,
        ) from None


def _load_answer_file(path: Path) -> dict[str, Any]:
    """Read an answer file and return its top-level table."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise OperatorError(
            f"answer file not found: {path} ({error.strerror or 'No such file or directory'})",
            code=EXIT_USER,
        ) from None
    except OSError as error:
        raise OperatorError(
            f"cannot read answer file {path}: {error}", code=EXIT_USER
        ) from None

    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise OperatorError(
            f"answer file {path} is not valid TOML: {_one_line(error)}",
            code=EXIT_USER,
        ) from None

    if not isinstance(document, dict):
        raise OperatorError(
            f"answer file {path} must contain a TOML table at the top level, "
            f"not {_kind(document)}",
            code=EXIT_USER,
        ) from None

    return document


def _plan_file_answers(
    document: Mapping[str, Any],
) -> tuple[list[str], list[str], list[str], dict[str, Any]]:
    """Resolve an answer document into a string answer list and a completed doc.

    Returns `(answers, report_lines, missing_fields, completed_document)`.
    Documented defaults are applied to omitted fields and reported (FR-003);
    fields with no safe default are collected (FR-004).  The returned
    `completed_document` is the document the interview would produce from those
    answers, and is used for pre-validation.
    """
    completed: dict[str, Any] = copy.deepcopy(dict(document))
    _ensure_block(completed, "llm")
    _ensure_block(completed, "memory")
    _ensure_block(completed, "temporal")
    _ensure_block(completed, "telemetry")
    _ensure_block(completed, "escalation")

    explicit = _explicit_field_paths(completed)
    answers: list[str] = []
    reports: list[str] = []
    missing: list[str] = []

    def take(field: tuple[str, ...], *, required: bool) -> Any:
        """Return the value for `field`, applying a documented default if needed."""
        raw = _deep_get(completed, field)
        if raw is None or (isinstance(raw, str) and raw == ""):
            if field in _OPTIONAL_INTERVIEW_FIELDS:
                # Optional and absent/empty: keep absent.
                return None if raw is None else ""
            default = _controlplane_default(completed, field)
            if default is _NO_DEFAULT:
                missing.append(".".join(field))
                return ""
            if field not in explicit:
                reports.append(_report_default(".".join(field), default))
            _deep_set(completed, field, default)
            return default
        return raw

    def take_optional(field: tuple[str, ...]) -> Any:
        """Return the optional value, or empty string when absent."""
        raw = _deep_get(completed, field)
        if raw is None or (isinstance(raw, str) and raw == ""):
            return ""
        return raw

    # LLM
    llm_mode = take(("llm", "mode"), required=True)
    answers.append(_answer_text(llm_mode))
    base_url = take(("llm", "base_url"), required=True)
    answers.append(_answer_text(base_url))
    if llm_mode == "gateway":
        master_key_env = take(("llm", "master_key_env"), required=True)
        answers.append(_answer_text(master_key_env))
    elif llm_mode == "direct":
        api_key_env = take(("llm", "api_key_env"), required=True)
        answers.append(_answer_text(api_key_env))

    # Memory
    memory_backend = take(("memory", "backend"), required=True)
    answers.append(_answer_text(memory_backend))
    if memory_backend == "hindsight":
        memory_url = take(("memory", "url"), required=True)
        answers.append(_answer_text(memory_url))
        memory_api_key = take_optional(("memory", "api_key_env"))
        answers.append(_answer_text(memory_api_key))

    # Temporal
    temporal_mode = take(("temporal", "mode"), required=True)
    answers.append(_answer_text(temporal_mode))
    if temporal_mode == "external":
        temporal_address = take(("temporal", "address"), required=True)
        answers.append(_answer_text(temporal_address))
        temporal_namespace = take(("temporal", "namespace"), required=True)
        answers.append(_answer_text(temporal_namespace))
        temporal_api_key = take_optional(("temporal", "api_key_env"))
        answers.append(_answer_text(temporal_api_key))
        tls_enabled = take(("temporal", "tls_enabled"), required=True)
        answers.append(_answer_text(tls_enabled))

    # Telemetry
    otlp_endpoint = take_optional(("telemetry", "otlp_endpoint"))
    answers.append(_answer_text(otlp_endpoint))

    # Escalation
    escalation_adapter = take(("escalation", "adapter"), required=True)
    answers.append(_answer_text(escalation_adapter))
    bot_token_env = take_optional(("escalation", "bot_token_env"))
    answers.append(_answer_text(bot_token_env))
    chat_id_env = take_optional(("escalation", "chat_id_env"))
    answers.append(_answer_text(chat_id_env))

    return answers, reports, missing, completed


def _ensure_block(document: dict[str, Any], name: str) -> None:
    """Make sure `document` contains a dict for the named subsystem."""
    if name not in document or not isinstance(document[name], dict):
        document[name] = {}


def _explicit_field_paths(document: Mapping[str, Any]) -> set[tuple[str, ...]]:
    """Return the field paths that were explicitly present in the input."""
    explicit: set[tuple[str, ...]] = set()
    for top_key, top_value in document.items():
        if top_key == "version":
            explicit.add(("version",))
        elif isinstance(top_value, dict):
            for nested_key in top_value:
                explicit.add((top_key, nested_key))
    return explicit


def _answer_text(value: Any) -> str:
    """Render a planned value the way `_ask` expects it as an answer string."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _report_default(field: str, value: Any) -> str:
    """One line reporting that a documented default was applied (FR-003)."""
    if isinstance(value, bool):
        rendered = "true" if value else "false"
    elif isinstance(value, str):
        rendered = f'"{value}"'
    elif isinstance(value, int):
        rendered = str(value)
    else:
        rendered = repr(value)
    return f"applied default: {field} = {rendered}"


def _redact_parser_error(
    refusal: ControlPlaneConfigError, document: dict[str, Any]
) -> str:
    """The parser's message, with any credential from the file taken back out."""
    message = str(refusal)
    if refusal.rule != RULE_SECRET_VALUE_NOT_REFERENCE:
        return message
    return _redact_secret_values(message, document)


def _redact_secret_values(message: str, document: Any) -> str:
    """Replace every secret-looking string found in `document` with `<value withheld>`."""
    for value in _walk_strings(document):
        if _looks_like_secret(value):
            message = message.replace(repr(value), _WITHHELD).replace(value, _WITHHELD)
    return message


def _walk_strings(value: Any) -> Iterator[str]:
    """Yield every string leaf in a nested document."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _walk_strings(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)


def _looks_like_secret(value: str) -> bool:
    """True when `value` matches a shape the parser treats as a credential."""
    for pattern in _SECRET_PATTERNS:
        if pattern.search(value):
            return True
    return False


# ---------------------------------------------------------------------------
# The interview
# ---------------------------------------------------------------------------


def _interview(path: Path, prompter: Any | None = None) -> dict[str, Any]:
    """Ask every subsystem in order and return the validated document."""
    document = _starting_document(path)
    if prompter is None:
        prompter = init_module._prompter()

    # US3: discover what is reachable before asking. The scan is advisory: a
    # failure, absence or classification may never prevent the operator from
    # answering by hand.
    scan = _llm_scan()

    document = _ask_llm(prompter, document, path, scan)
    document = _ask_memory(prompter, document, path)
    document = _ask_temporal(prompter, document, path)
    document = _ask_telemetry(prompter, document, path)
    document = _ask_escalation(prompter, document, path)
    return document


def _starting_document(path: Path) -> dict[str, Any]:
    """Load the existing config as defaults, or seed a blank host.

    An existing file the process cannot read — or one the parser refuses — fails
    closed naming the path and the problem. Falling back to defaults here would
    silently rewrite a config whose contents nobody could see (spec edge case).
    """
    if not path.exists():
        return copy.deepcopy(BLANK_DOCUMENT)
    try:
        existing = load_controlplane_config(path)
    except ControlPlaneConfigError as error:
        raise OperatorError(
            f"{error}; fix or remove that file, then re-run `ergane install`",
            code=EXIT_USER,
        ) from None
    return controlplane_document(existing)


def _ask_llm(
    prompter: Any, document: dict[str, Any], path: Path, scan: ScanResult | None
) -> dict[str, Any]:
    """Ask the LLM block, using a scan to default mode and address.

    The scan is advisory: an operator-declared address always wins, and a scan
    that found nothing falls back to today's question unchanged.
    """
    offered = _offered_llm_mode(scan, document)

    document = _ask(
        prompter,
        f"llm mode ({offered.choices})",
        document,
        path,
        default=offered.mode,
        apply=_apply_llm_mode,
        unavailable_error=offered.unavailable_reason,
    )

    # The chosen mode decides which follow-up fields are asked.
    mode = document["llm"].get("mode")
    if mode == "gateway":
        document = _ask(
            prompter,
            "llm gateway base_url",
            document,
            path,
            default=document["llm"].get("base_url"),
            apply=lambda doc, value: _set(doc, ("llm", "base_url"), value),
        )
        document = _ask(
            prompter,
            "llm gateway master key env-var name",
            document,
            path,
            default=document["llm"].get("master_key_env"),
            apply=lambda doc, value: _set(doc, ("llm", "master_key_env"), value),
        )
    elif mode == "direct":
        # Before accepting the answer, state what direct gives up.
        print(DIRECT_MODE_SURRENDERED_PROPERTIES_TEXT)

        document = _ask(
            prompter,
            "llm direct base_url",
            document,
            path,
            default=document["llm"].get("base_url"),
            apply=lambda doc, value: _set(doc, ("llm", "base_url"), value),
        )
        document = _ask(
            prompter,
            "llm direct api key env-var name",
            document,
            path,
            default=document["llm"].get("api_key_env"),
            apply=lambda doc, value: _set(doc, ("llm", "api_key_env"), value),
        )
    return document


def _ask_memory(prompter: Any, document: dict[str, Any], path: Path) -> dict[str, Any]:
    document = _ask(
        prompter,
        "memory backend (hindsight|none)",
        document,
        path,
        default=document["memory"].get("backend"),
        apply=_apply_memory_backend,
    )
    if document["memory"].get("backend") == "none":
        return document

    document = _ask(
        prompter,
        "memory url",
        document,
        path,
        default=document["memory"].get("url"),
        apply=lambda doc, value: _set(doc, ("memory", "url"), value),
    )
    return _ask(
        prompter,
        "memory api key env-var name (optional)",
        document,
        path,
        default=document["memory"].get("api_key_env"),
        apply=lambda doc, value: _set(doc, ("memory", "api_key_env"), value),
        optional=True,
    )


def _systemd_user_session_available() -> bool:
    """Whether this host can run `systemctl --user` commands (FR-011).

    A host without a user D-Bus bus — common in containers and minimal SSH
    sessions — fails with 'Failed to connect to bus'.  Managed mode needs that
    bus to enable, start and watch its unit, so it is refused here rather than
    half-way through unit installation.
    """
    import subprocess

    result = subprocess.run(
        ("systemctl", "--user", "daemon-reload"),
        capture_output=True,
        text=True,
        check=False,
    )
    # Any stderr means the bus is missing; a present session answers empty stderr
    # (even if the daemon state is otherwise not ideal).
    return result.stderr.strip() == ""


#: How long the Docker probe waits for the daemon to answer.  A probe that
#: hangs is worse than one that says no: the operator sits at a prompt waiting
#: for a question that never arrives, and `docker info` against a wedged socket
#: is exactly that shape.
_DOCKER_PROBE_TIMEOUT_S = 5.0


def _docker_daemon_available(timeout_s: float = _DOCKER_PROBE_TIMEOUT_S) -> bool:
    """Whether a Docker daemon answers on this host (104-US1).

    The engine-container backend's capability predicate, deliberately sitting
    beside `_systemd_user_session_available` — the systemd tier's — because two
    capability probes in two modules is how they stop agreeing.

    It asks about **the daemon only**.  "Can this installation build an image"
    is a different question with a different answer (a wheel install carries no
    build context), and it belongs to the generator that needs it, not to a
    second copy here.
    """
    import shutil
    import subprocess

    if shutil.which("docker") is None:
        return False

    try:
        result = subprocess.run(
            ("docker", "info", "--format", "{{.ServerVersion}}"),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_s,
        )
    except (subprocess.TimeoutExpired, OSError):
        # A wedged socket, a binary that vanished between `which` and here, a
        # daemon mid-restart: all of them mean "no daemon answered", and none of
        # them is a reason to end an interview with a traceback.
        return False
    return result.returncode == 0


def _docker_compose_v2_available(timeout_s: float = _DOCKER_PROBE_TIMEOUT_S) -> bool:
    """Whether `docker compose` (v2, a subcommand) resolves on this host.

    Consulted only while building a refusal, never while offering the question:
    the offer turns on the daemon, and this distinguishes *which* piece is
    missing once we already know the answer is no.
    """
    import subprocess

    try:
        result = subprocess.run(
            ("docker", "compose", "version"),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_s,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0


_DOCKER_INSTALL_URL = "https://docs.docker.com/engine/install/"

#: Every refusal opens and closes the same way, so the operator reads the same
#: sentence shape whether the choice arrived through the question or `--engine`.
_ENGINE_REFUSAL_OPENING = (
    'engine backend "container" requires a reachable Docker daemon; '
)
_ENGINE_REFUSAL_CLOSING = (
    " Choose `systemd` or `none`, or fix Docker and re-run `ergane install`."
)

_DOCKER_MISSING = (
    "`docker` is not on PATH. Install Docker Engine together with its Compose v2 "
    f"plugin ({_DOCKER_INSTALL_URL}), which is what brings the engine container "
    "up (`docker compose`, two words)."
)

#: `docker-compose` (v1, hyphenated) and `docker compose` (v2, a subcommand of
#: the daemon's own CLI) are different programs and only the second can bring
#: the engine container up.  An operator who has the first and is told "Docker is
#: not installed" will reasonably believe the installer is wrong.
_LEGACY_COMPOSE = (
    "the legacy `docker-compose` binary is present ({legacy}) but `docker compose` "
    "(v2, two words) is not, and Compose v1 cannot bring the engine container up. "
    "Install Docker Engine and the `docker-compose-plugin` package "
    f"({_DOCKER_INSTALL_URL})."
)

_DAEMON_SILENT = (
    "`docker` is at {docker} but `docker info` did not answer, so the daemon is "
    "either not running or not reachable from this account. Start it "
    "(`sudo systemctl start docker`) and give your user the socket "
    "(`sudo usermod -aG docker $USER`, then log in again)."
)


def _docker_unavailable_reason() -> str:
    """Name the missing piece, and how to get it (US1-S2).

    Three hosts, three different fixes: nothing installed, the legacy Compose
    binary installed instead, and Docker installed but silent.  A refusal that
    collapsed them into one message would send two of the three operators after
    the wrong thing.
    """
    import shutil

    docker = shutil.which("docker")
    legacy = shutil.which("docker-compose")

    if legacy is not None and (docker is None or not _docker_compose_v2_available()):
        middle = _LEGACY_COMPOSE.format(legacy=legacy)
    elif docker is None:
        middle = _DOCKER_MISSING
    else:
        middle = _DAEMON_SILENT.format(docker=docker)
    return _ENGINE_REFUSAL_OPENING + middle + _ENGINE_REFUSAL_CLOSING


def _ask_temporal(
    prompter: Any, document: dict[str, Any], path: Path
) -> dict[str, Any]:
    document = _ask(
        prompter,
        "temporal mode (external|managed)",
        document,
        path,
        default=document["temporal"].get("mode"),
        apply=_apply_temporal_mode,
    )
    if document["temporal"].get("mode") == "managed" and not _systemd_user_session_available():
        raise OperatorError(
            "temporal.mode = \"managed\" requires a systemd user session; "
            "this host does not have one (systemctl --user is not available). "
            "Choose external Temporal or enable user sessions.",
            code=EXIT_USER,
        )
    if document["temporal"].get("mode") == "managed":
        # Managed mode installs its own server; these fields are not operator inputs.
        document["temporal"].pop("address", None)
        document["temporal"].pop("namespace", None)
        document["temporal"].pop("api_key_env", None)
        document["temporal"].pop("tls_enabled", None)
        return document
    document = _ask(
        prompter,
        "temporal address",
        document,
        path,
        default=document["temporal"].get("address"),
        apply=lambda doc, value: _set(doc, ("temporal", "address"), value),
    )
    document = _ask(
        prompter,
        "temporal namespace",
        document,
        path,
        default=document["temporal"].get("namespace"),
        apply=lambda doc, value: _set(doc, ("temporal", "namespace"), value),
    )
    document = _ask(
        prompter,
        "temporal api key env-var name (optional)",
        document,
        path,
        default=document["temporal"].get("api_key_env"),
        apply=lambda doc, value: _set(doc, ("temporal", "api_key_env"), value),
        optional=True,
    )
    return _ask(
        prompter,
        "temporal TLS enabled (true|false)",
        document,
        path,
        default="true" if document["temporal"].get("tls_enabled") else "false",
        apply=lambda doc, value: _set(
            doc, ("temporal", "tls_enabled"), _as_optional_bool(value)
        ),
    )


def _ask_telemetry(
    prompter: Any, document: dict[str, Any], path: Path
) -> dict[str, Any]:
    return _ask(
        prompter,
        "telemetry OTLP endpoint (optional)",
        document,
        path,
        default=document["telemetry"].get("otlp_endpoint"),
        apply=lambda doc, value: _set(doc, ("telemetry", "otlp_endpoint"), value),
        optional=True,
    )


def _ask_escalation(
    prompter: Any, document: dict[str, Any], path: Path
) -> dict[str, Any]:
    document = _ask(
        prompter,
        "escalation adapter (telegram|none)",
        document,
        path,
        default=document["escalation"].get("adapter"),
        apply=_apply_escalation_adapter,
    )
    if document["escalation"].get("adapter") == "none":
        return document
    document = _ask(
        prompter,
        "escalation bot token env-var name (optional)",
        document,
        path,
        default=document["escalation"].get("bot_token_env"),
        apply=lambda doc, value: _set(doc, ("escalation", "bot_token_env"), value),
        optional=True,
    )
    return _ask(
        prompter,
        "escalation chat id env-var name (optional)",
        document,
        path,
        default=document["escalation"].get("chat_id_env"),
        apply=lambda doc, value: _set(doc, ("escalation", "chat_id_env"), value),
        optional=True,
    )


# ---------------------------------------------------------------------------
# One question, validated by the parser
# ---------------------------------------------------------------------------


def _ask(
    prompter: Any,
    prompt: str,
    document: dict[str, Any],
    path: Path,
    *,
    default: Any,
    apply: Callable[[dict[str, Any], Any], dict[str, Any]],
    optional: bool = False,
    unavailable_error: str | None = None,
) -> dict[str, Any]:
    """Ask one question until the whole document parses with the answer applied.

    An empty answer keeps the offered default; for an optional field with no
    default it means "omit", and `-` clears one that has a value. The candidate
    is judged by `parse_controlplane_config` over the *rendered* document, so
    the interview refuses exactly what the parser would refuse — at entry,
    before anything is written.
    """
    default_text = _default_text(default)
    error: str | None = None

    while True:
        answer = prompter.ask(prompt, default=default_text, error=error).strip()

        if answer == CLEAR:
            value: Any = None
        elif answer == "":
            # Keep what was offered. For an optional field with nothing to
            # offer, that is `None` — the field stays absent.
            value = default
        else:
            value = answer

        candidate = apply(copy.deepcopy(document), value)
        try:
            parse_controlplane_config(
                render_controlplane_document(candidate), source=str(path)
            )
        except ControlPlaneConfigError as refusal:
            error = _redacted(refusal, value)
            continue
        # If the operator explicitly picked a mode the scan says is unavailable,
        # explain why before returning the valid candidate. The parser accepts
        # `direct` now (055-US2), so this is the scan's advisory warning.
        if unavailable_error is not None and value == default and answer == "":
            # They accepted the default; nothing else to say.
            return candidate
        if unavailable_error is not None and value == "direct" and answer != "":
            print(unavailable_error)
        return candidate


#: Shown in place of a credential the operator pasted where a reference belongs.
_WITHHELD = "<value withheld>"

#: Backwards-compatible alias for existing references in this module.
WITHHELD = _WITHHELD


def _redacted(refusal: ControlPlaneConfigError, value: Any) -> str:
    """The parser's message, with a just-typed credential taken back out.

    FR-002 wants the offending value repr-rendered and FR-003 forbids a secret
    value reaching any log; for a value the operator typed one line ago those
    pull in opposite directions, and FR-003 wins. Only the rule that fires *on*
    a credential is redacted — a mistyped mode is still echoed, because seeing
    it is how the operator fixes it.

    Found by running the walkthrough rather than by reading it: the terminal
    transcript of a pasted `sk-…` contained the key.
    """
    message = str(refusal)
    if refusal.rule == RULE_SECRET_VALUE_NOT_REFERENCE and isinstance(value, str):
        message = message.replace(repr(value), WITHHELD).replace(value, WITHHELD)
    return message


def _default_text(default: Any) -> str | None:
    if default is None:
        return None
    if isinstance(default, bool):
        return "true" if default else "false"
    return str(default)


def _as_bool(value: Any) -> Any:
    """Map an answer to a boolean, or leave it alone for the parser to refuse."""
    if value is None or isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("true", "yes", "y", "1"):
        return True
    if text in ("false", "no", "n", "0"):
        return False
    return value


def _as_optional_bool(value: Any) -> Any:
    """As `_as_bool`, but a false answer *removes* the key.

    The canonical rendering omits a flag sitting at its default, so writing
    `tls_enabled = false` here would make the interview's output differ from
    `render_controlplane_config` — and would add a line to `[temporal]` the
    first time a hand-written config was re-run, breaking US3-S2's promise that
    changing the OTLP endpoint touches only `[telemetry]`.
    """
    resolved = _as_bool(value)
    return None if resolved is False else resolved


def _set(document: dict[str, Any], route: tuple[Any, ...], value: Any) -> dict[str, Any]:
    """Set (or delete, when `value is None`) one key on the in-progress document."""
    target: Any = document
    for step in route[:-1]:
        target = target[step]
    key = route[-1]
    if value is None:
        if isinstance(target, dict):
            target.pop(key, None)
    else:
        target[key] = value
    return document


def _apply_llm_mode(document: dict[str, Any], mode: Any) -> dict[str, Any]:
    """Switch the `[llm]` block to `mode`, seeding only that mode's fields.

    The scan may have already set `base_url` to a discovered address; preserve it
    when switching to the matching mode so the operator sees the discovered default.
    """
    current = document.get("llm") or {}
    if current.get("mode") == mode:
        return document

    preserved_address = current.get("base_url")
    if mode == "gateway":
        document["llm"] = dict(_GATEWAY_SEED)
        if preserved_address:
            document["llm"]["base_url"] = preserved_address
    elif mode == "direct":
        document["llm"] = dict(_DIRECT_SEED)
        if preserved_address:
            document["llm"]["base_url"] = preserved_address
    else:
        # Unrecognized, or recognized and refused: keep the answer so the parser
        # refuses it by name and the operator reads the parser's own reason.
        document["llm"] = {**current, "mode": mode}
    return document


def _apply_memory_backend(document: dict[str, Any], backend: Any) -> dict[str, Any]:
    current = document.get("memory") or {}
    if current.get("backend") == backend:
        return document
    if backend == "none":
        document["memory"] = {"backend": "none"}
    elif backend == "hindsight":
        document["memory"] = dict(_HINDSIGHT_SEED)
    else:
        document["memory"] = {**current, "backend": backend}
    return document


def _apply_temporal_mode(document: dict[str, Any], mode: Any) -> dict[str, Any]:
    current = document.get("temporal") or {}
    document["temporal"] = {**current, "mode": mode}
    return document


def _apply_escalation_adapter(document: dict[str, Any], adapter: Any) -> dict[str, Any]:
    """Switch the `[escalation]` block to `adapter`, seeding only that adapter's fields.

    Selecting `none` clears the optional Telegram fields so the canonical
    rendering omits them, matching the non-interactive path that declares
    `adapter = "none"` without credentials.
    """
    current = document.get("escalation") or {}
    if current.get("adapter") == adapter:
        return document
    if adapter == "none":
        document["escalation"] = {"adapter": "none"}
    else:
        document["escalation"] = {**current, "adapter": adapter}
    return document


@dataclasses.dataclass(frozen=True)
class _OfferedLLM:
    mode: str
    choices: str
    unavailable_reason: str | None


def _llm_scan() -> ScanResult | None:
    """Probe the default loopback candidates and return the most capable result.

    Returns the first dispatchable result found, then the first reachable
    inference-only result, then `None` when nothing answers. The scan is
    unauthenticated: no credential is sent.
    """
    results = _scan_endpoints()
    dispatchable = [r for r in results if r.classification == EndpointClassification.DISPATCHABLE]
    if dispatchable:
        return dispatchable[0]
    reachable = [r for r in results if r.reachable and r.classification is not None]
    if reachable:
        return reachable[0]
    return None


def _offered_llm_mode(scan: ScanResult | None, document: dict[str, Any]) -> _OfferedLLM:
    """Choose the offered mode and default address from the scan.

    - Dispatchable endpoint: offer `gateway` and default its address.
    - Inference-only endpoint: offer `direct`, default its address, and keep a
      reason naming the missing key-management capability.
    - No scan result / no reachable endpoint: fall back to today's question.

    An existing config's mode is respected on a *re-run* so a saved gateway config
    is not flipped to direct by a local inference endpoint. On a blank host the
    scan's classification is offered.
    """
    existing_mode = document.get("llm", {}).get("mode")
    # A blank host is seeded with BLANK_DOCUMENT whose mode is the historical
    # gateway default. Treat that seed as "no prior operator declaration" so the
    # scan can offer a different mode. A re-run loads the existing file via
    # `controlplane_document`, which produces a fresh dict, so identity is enough.
    blank_host = existing_mode is None or document.get("llm") == BLANK_DOCUMENT["llm"]

    if scan is None or not scan.reachable or scan.classification is None:
        # No usable scan result: keep the existing mode if there is one.
        mode = existing_mode if existing_mode is not None else "gateway"
        return _OfferedLLM(mode=mode, choices=mode, unavailable_reason=None)

    if scan.classification == EndpointClassification.DISPATCHABLE:
        # A dispatchable endpoint is good for gateway mode.
        document["llm"]["base_url"] = scan.address
        if blank_host or existing_mode != "direct":
            return _OfferedLLM(
                mode="gateway",
                choices="gateway",
                unavailable_reason=None,
            )
        # Operator already chose direct on a re-run; keep that default.
        return _OfferedLLM(mode="direct", choices="direct", unavailable_reason=None)

    # Inference-only: direct is the natural offer for a blank host.
    reason = (
        f"`gateway` is unavailable: the endpoint at {scan.address} answers "
        f"/v1/models but not the key-management API (/key/generate), so the "
        f"factory cannot mint per-attempt virtual keys there."
    )
    if blank_host:
        document["llm"]["base_url"] = scan.address
        return _OfferedLLM(mode="direct", choices="direct", unavailable_reason=reason)

    # Re-run: keep the existing mode (gateway or direct) and its existing address.
    # Only update the default address when the host has no prior declaration.
    mode = existing_mode if existing_mode in KNOWN_LL_MODES else "direct"
    return _OfferedLLM(mode=mode, choices=mode, unavailable_reason=reason)


@dataclasses.dataclass(frozen=True)
class _OfferedEngine:
    """What the engine question offers, and why the container is not on offer.

    `_OfferedLLM`'s shape, for the same reason: probe first, offer the probed
    answer first, and keep the reason when the capable option is unavailable so
    an operator who reaches for it anyway is told what is missing rather than
    that they typed something wrong.
    """

    backend: str
    choices: str
    unavailable_reason: str | None


def _offered_engine_backend(daemon_available: bool) -> _OfferedEngine:
    """Choose the offered backend from the Docker probe (US1-S1, US1-S2).

    The probe is a parameter rather than a call, the way `_offered_llm_mode`
    takes the scan it did not run: the caller owns the one probe, and a test can
    state the host instead of having one.
    """
    if daemon_available:
        return _OfferedEngine(
            backend=ENGINE_CONTAINER,
            choices="|".join(ENGINE_BACKENDS),
            unavailable_reason=None,
        )

    # No daemon: `none` is today's exit and therefore the honest default, and
    # the offer leads with it. The reason is computed now and carried, so the
    # question and the `--engine` flag refuse with the same sentence.
    return _OfferedEngine(
        backend=DEFAULT_ENGINE_BACKEND,
        choices="|".join((ENGINE_NONE, ENGINE_SYSTEMD, ENGINE_CONTAINER)),
        unavailable_reason=_docker_unavailable_reason(),
    )


__all__ = [
    "DEFAULT_ENGINE_BACKEND",
    "DEFAULT_LOCK_TIMEOUT_S",
    "ENGINE_BACKENDS",
    "ENGINE_CONTAINER",
    "ENGINE_NONE",
    "ENGINE_SYSTEMD",
    "add_install_arguments",
    "install_command",
]
