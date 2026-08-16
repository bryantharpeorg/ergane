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
import copy
from pathlib import Path
from typing import Any, Callable

from factory.cli import init as init_module
from factory.cli.errors import EXIT_OK, EXIT_USER, OperatorError
from factory.controlplane.config import (
    ControlPlaneConfigError,
    controlplane_document,
    load_controlplane_config,
    parse_controlplane_config,
    render_controlplane_document,
    resolve_config_path,
)
from factory.controlplane.verify import render_findings, verify_controlplane
from factory.locking import LockUnavailable, exclusive_lock

#: How long `ergane install` waits for another install to finish before it
#: refuses. Overridable per invocation with `--lock-timeout`.
DEFAULT_LOCK_TIMEOUT_S = 30.0

#: The answer that clears an optional field that currently has a value.
CLEAR = "-"

#: What a blank host is offered before it has answered anything. Every value is
#: valid, so the whole interview can be completed by pressing Enter.
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
        "namespace": "ergane",
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
_PERSONA_SEED: dict[str, Any] = {
    "name": "implementer",
    "base_url": "http://127.0.0.1:4000",
    "model": "CHANGEME",
    "api_key_env": "ERGANE_LLM_API_KEY",
}
_HINDSIGHT_SEED: dict[str, Any] = {
    "backend": "hindsight",
    "url": "http://127.0.0.1:8888",
}


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def add_install_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the walkthrough's own flags to the `install` subparser."""
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

    try:
        with exclusive_lock(path, timeout_s=timeout_s):
            document = _interview(path)
            text = render_controlplane_document(document)
            _write_config(path, text)
            print(f"wrote {path}")
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


# ---------------------------------------------------------------------------
# The interview
# ---------------------------------------------------------------------------


def _interview(path: Path) -> dict[str, Any]:
    """Ask every subsystem in order and return the validated document."""
    document = _starting_document(path)
    prompter = init_module._prompter()

    document = _ask_llm(prompter, document, path)
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


def _ask_llm(prompter: Any, document: dict[str, Any], path: Path) -> dict[str, Any]:
    document = _ask(
        prompter,
        "llm mode (gateway|direct)",
        document,
        path,
        default=document["llm"].get("mode"),
        apply=_apply_llm_mode,
    )

    if document["llm"].get("mode") == "direct":
        return _ask_personas(prompter, document, path)

    document = _ask(
        prompter,
        "llm gateway base_url",
        document,
        path,
        default=document["llm"].get("base_url"),
        apply=lambda doc, value: _set(doc, ("llm", "base_url"), value),
    )
    return _ask(
        prompter,
        "llm gateway master key env-var name",
        document,
        path,
        default=document["llm"].get("master_key_env"),
        apply=lambda doc, value: _set(doc, ("llm", "master_key_env"), value),
    )


def _ask_personas(
    prompter: Any, document: dict[str, Any], path: Path
) -> dict[str, Any]:
    """Ask for `direct` mode's per-persona endpoints, one persona at a time."""
    existing = list(document["llm"].get("persona") or [])
    collected: list[dict[str, Any]] = []
    index = 0

    while True:
        seed = existing[index] if index < len(existing) else dict(_PERSONA_SEED)
        document["llm"]["persona"] = collected + [dict(seed)]
        for key, prompt in (
            ("name", "llm persona name"),
            ("base_url", "llm persona base_url"),
            ("model", "llm persona model"),
            ("api_key_env", "llm persona api key env-var name"),
        ):
            document = _ask(
                prompter,
                prompt,
                document,
                path,
                default=document["llm"]["persona"][index].get(key),
                apply=lambda doc, value, key=key, index=index: _set(
                    doc, ("llm", "persona", index, key), value
                ),
            )
        collected = list(document["llm"]["persona"])
        index += 1

        another = prompter.ask("add another llm persona? (y/N)", default="n")
        if another.strip().lower() not in ("y", "yes"):
            break

    document["llm"]["persona"] = collected
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
            doc, ("temporal", "tls_enabled"), _as_bool(value)
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
        "escalation adapter (telegram)",
        document,
        path,
        default=document["escalation"].get("adapter"),
        apply=lambda doc, value: _set(doc, ("escalation", "adapter"), value),
    )
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
            error = str(refusal)
            continue
        return candidate


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
    """Switch the `[llm]` block to `mode`, seeding only that mode's fields."""
    current = document.get("llm") or {}
    if current.get("mode") == mode:
        return document
    if mode == "gateway":
        document["llm"] = dict(_GATEWAY_SEED)
    elif mode == "direct":
        document["llm"] = {"mode": "direct", "persona": [dict(_PERSONA_SEED)]}
    else:
        # Unknown: keep the answer so the parser refuses it by name.
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


__all__ = [
    "DEFAULT_LOCK_TIMEOUT_S",
    "add_install_arguments",
    "install_command",
]
