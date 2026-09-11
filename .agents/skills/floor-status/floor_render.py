"""Render frozen factory-floor observations without consulting a registry.

Input documents are the JSON produced by ``ergane build status --json`` and a
typed attempt-history read. The renderer itself opens no process and no service.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


UNKNOWN = "<unknown>"
UNAVAILABLE = "<unavailable>"


def _value(value: Any) -> str:
    if value is None or value == "":
        return UNKNOWN
    return str(value)


def _service_lines(services: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    for name, fact in services.items():
        if not isinstance(fact, Mapping):
            lines.append(f"unavailable: {name} {_value(fact)}")
            continue
        state = _value(fact.get("state", UNAVAILABLE))
        reason = _value(fact.get("reason", "reason unavailable"))
        display_name = name.replace("_", " ")
        lines.append(
            f"unavailable: {display_name} {reason}"
            if state == "unavailable"
            else f"{display_name}: {state}"
        )
    return lines


def render_floor(
    *,
    status: Mapping[str, Any],
    attempts: Sequence[Mapping[str, Any]],
    services: Mapping[str, Any],
    registry: Mapping[str, Any] | None = None,
    mutations: Any | None = None,
) -> str:
    """Render only the recorded facts in the supplied typed documents.

    ``registry`` is accepted for callers that want to prove a renderer does not
    consult it. It is deliberately read by no code path. ``mutations`` exists
    for denied-seam tests and is likewise never called.
    """
    del registry, mutations
    epic_id = _value(status.get("epic_id"))
    execution = _value(status.get("execution_status"))
    worker_revision = _value(status.get("worker_revision"))
    lines = [
        f"floor report: {epic_id} ({execution}; worker {worker_revision})",
        "evidence source: recorded status and verification-store rows",
    ]

    nodes = status.get("nodes", {})
    if not isinstance(nodes, Mapping):
        raise ValueError("status nodes must be a mapping")
    if not nodes:
        lines.append("no running nodes recorded")
    for node_id, node in nodes.items():
        state = _value(node.get("state"))
        attempt = _value(node.get("attempt"))
        lines.append(f"node {node_id}: state {state}  attempt {attempt}")

    dispatches_by_node: dict[str, list[Mapping[str, Any]]] = {}
    for row in attempts:
        node_id = _value(row.get("node_id"))
        dispatches_by_node.setdefault(node_id, []).append(row)

    if not attempts:
        lines.append("no recorded dispatches")
        lines.append("no recorded attempts")
    else:
        for node_id, rows in dispatches_by_node.items():
            if len(rows) > 1:
                lines.append(f"node {node_id}: {len(rows)} recorded dispatches")
            for index, row in enumerate(rows, start=1):
                prefix = (
                    f"dispatch {index} of {len(rows)}: {row.get('dispatch')}"
                    if len(rows) > 1
                    else f"dispatch {row.get('dispatch')}"
                )
                dispatch = _value(row.get("dispatch"))
                attempt = _value(row.get("attempt"))
                runner = _value(row.get("persona"))
                model = _value(row.get("model_alias"))
                route = _value(row.get("route"))
                evidence = _value(row.get("evidence_source", "verification-store"))
                lines.append(
                    f"  {prefix}  attempt {attempt}  "
                    f"runner {runner}  model {model}  route {route}  "
                    f"evidence {evidence}"
                )

    lines.extend(_service_lines(services))
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="render frozen floor observations")
    parser.add_argument("status", type=Path)
    parser.add_argument("attempts", type=Path)
    parser.add_argument("services", type=Path)
    args = parser.parse_args(argv)

    with args.status.open(encoding="utf-8") as source:
        status_document = json.load(source)
    with args.attempts.open(encoding="utf-8") as source:
        attempts_document = json.load(source)
    with args.services.open(encoding="utf-8") as source:
        services_document = json.load(source)
    print(
        render_floor(
            status=status_document,
            attempts=attempts_document.get("attempts", ()),
            services=services_document,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
