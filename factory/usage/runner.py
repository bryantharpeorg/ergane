"""Measured runner telemetry for attempts that bypass the gateway.

Only structured runner events are read, never prose. Execution manifests bind
usage to the dispatched route and time window, including activity relaunches.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from factory.usage.models import AggregatedUsage, KeyLease


@dataclass(frozen=True)
class RunnerUsage:
    aggregate: AggregatedUsage
    source: str
    status: str


_FIELDS = ('prompt_tokens', 'completion_tokens', 'cache_read_tokens', 'cache_write_tokens', 'request_count')


def _number(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _time(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError('Usage timestamps must be strings')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Usage timestamps must include a timezone')
    return parsed.astimezone(timezone.utc)


def _sum(values: Iterable[int | None]) -> int | None:
    items = [value for value in values if value is not None]
    return sum(items) if items else None


def combine(usages: list[AggregatedUsage]) -> AggregatedUsage:
    values = {field: _sum(getattr(u, field) for u in usages) for field in _FIELDS}
    if any(usage.request_count is None for usage in usages):
        values['request_count'] = None
    return AggregatedUsage(**values, spend_usd=0.0)


def _claude(events: Iterable[Mapping[str, Any]]) -> tuple[AggregatedUsage, bool]:
    clean = True
    messages: dict[str, dict[str, int | None]] = {}
    for event in events:
        if event.get('type') != 'assistant':
            continue
        message = event.get('message')
        if not isinstance(message, dict) or not isinstance(message.get('id'), str):
            clean = False
            continue
        usage = message.get('usage')
        if not isinstance(usage, dict):
            usage = {}
        counters = {name: _number(usage.get(name)) for name in (
            'input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens',
        )}
        previous = messages.setdefault(message['id'], counters)
        # Claude repeats a message across content blocks; retain the most
        # complete counters, rather than adding the same request repeatedly.
        for name, value in counters.items():
            if value is not None:
                previous[name] = max(previous[name] or 0, value)
    rows = []
    for values in messages.values():
        clean &= values['input_tokens'] is not None and values['output_tokens'] is not None
        prompt = values['input_tokens']
        if prompt is not None:
            prompt += (values['cache_read_input_tokens'] or 0) + (values['cache_creation_input_tokens'] or 0)
        rows.append(AggregatedUsage(prompt, values['output_tokens'], values['cache_read_input_tokens'],
                                    values['cache_creation_input_tokens'], 1, 0.0))
    return combine(rows), clean


def parse_claude(events: Iterable[Mapping[str, Any]]) -> AggregatedUsage:
    return _claude(events)[0]


def _codex(events: Iterable[Mapping[str, Any]], since: str) -> tuple[AggregatedUsage, bool]:
    names = ('input_tokens', 'output_tokens', 'cached_input_tokens', 'cache_write_input_tokens')
    previous: dict[str, int | None] = dict.fromkeys(names, 0)
    sums: dict[str, int | None] = dict.fromkeys(names)
    start = _time(since)
    clean = True
    for event in events:
        payload = event.get('payload')
        if event.get('type') != 'event_msg' or not isinstance(payload, dict) or payload.get('type') != 'token_count':
            continue
        info = payload.get('info')
        if info is None:  # rate-limit-only event, no new token measurement
            continue
        totals = info.get('total_token_usage') if isinstance(info, dict) else None
        if not isinstance(totals, dict):
            clean = False
            continue
        try:
            when = _time(event['timestamp'])
        except (KeyError, TypeError, ValueError):
            clean = False
            continue
        current = {name: _number(totals.get(name)) for name in names}
        if when >= start:
            for name, value in current.items():
                if value is None or previous[name] is None:
                    clean = False if name in names[:2] else clean
                    continue
                delta = value - previous[name]
                if delta < 0:
                    # A reset/compaction is an unresolved boundary, not negative usage.
                    clean = False
                    delta = value
                sums[name] = (sums[name] or 0) + delta
        previous = current
    return AggregatedUsage(*(sums[name] for name in names), request_count=None, spend_usd=0.0), clean


def parse_codex(events: Iterable[Mapping[str, Any]], *, since: str) -> AggregatedUsage:
    return _codex(events, since)[0]


def _read_events(path: Path) -> tuple[list[dict[str, Any]], bool]:
    events = []
    clean = True
    with path.open() as stream:
        for line in stream:
            try:
                event = json.loads(line)
                if isinstance(event, dict):
                    events.append(event)
                else:
                    clean = False
            except ValueError:
                clean = False
    return events, clean


def archive_execution_usage(root: Path, context: Any, started_at: str, completed: bool) -> None:
    """Called on the host after archive, including cancellation. No workflow change."""
    from factory.config import effective_route, ROUTE_SUBSCRIPTION
    from factory.workgraph.adapter import transcript_dir

    if effective_route(context.route, context.agent) != ROUTE_SUBSCRIPTION:
        return
    archive = transcript_dir(root, context.epic_id, context.node_id, context.attempt)
    if not archive.is_dir():
        return
    paths = ([archive / f'{context.session_id}.jsonl'] if context.agent in ('claude-code', 'subscription')
             else sorted(archive.glob('rollout-*.jsonl')) if context.agent == 'codex' else [])
    usages = []
    clean = completed
    for path in paths:
        if not path.is_file():
            clean = False
            continue
        events, parsed = _read_events(path)
        clean &= parsed
        if context.agent == 'codex':
            usage, parsed = _codex(events, started_at)
            clean &= parsed
        else:
            usage, parsed = _claude(events)
            clean &= parsed
        # Old Codex rollouts are archived too. No events in this execution's
        # time window means no contribution, not an unknown extra session.
        if usage.prompt_tokens is not None or usage.completion_tokens is not None:
            usages.append(usage)
    aggregate = combine(usages)
    measured = aggregate.prompt_tokens is not None or aggregate.completion_tokens is not None
    complete = clean and aggregate.prompt_tokens is not None and aggregate.completion_tokens is not None
    document = {
        'epic_id': context.epic_id, 'node_id': context.node_id, 'attempt': context.attempt,
        'session_id': context.session_id, 'route': 'subscription', 'source': context.agent,
        'started_at': started_at,
        'status': 'complete' if complete else 'partial' if measured else 'unknown',
        'aggregate': asdict(aggregate),
    }
    target = archive / f'usage-{context.session_id}.json'
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(document) + '\n')
    temporary.replace(target)


def read_attempt_usage(root: Path, lease: KeyLease) -> RunnerUsage | None:
    from factory.workgraph.adapter import transcript_dir

    archive = transcript_dir(root, lease.epic_id, lease.node_id, lease.attempt)
    measurements = []
    sources = set()
    statuses = []
    for path in sorted(archive.glob('usage-*.json')):
        try:
            doc = json.loads(path.read_text())
            if not isinstance(doc, dict) or any(doc.get(name) != getattr(lease, name) for name in ('epic_id', 'node_id', 'attempt')):
                continue
            if doc.get('route') != 'subscription' or _time(doc['started_at']) < _time(lease.issued_at):
                continue
            raw = doc['aggregate']
            values = {field: _number(raw.get(field)) for field in _FIELDS}
            measurements.append(AggregatedUsage(**values, spend_usd=0.0))
            sources.add(str(doc['source']))
            statuses.append(doc['status'])
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            statuses.append('unknown')
    if not measurements:
        return None
    aggregate = combine(measurements)
    status = 'complete' if all(s == 'complete' for s in statuses) else 'partial'
    return RunnerUsage(aggregate, next(iter(sources)) if len(sources) == 1 else 'mixed', status)
