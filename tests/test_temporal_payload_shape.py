"""What a record has to look like to survive being read out of an older history.

A Temporal workflow's state is not stored; it is *replayed*. Every payload the
run ever wrote — its input, the arguments of every signal it received, the result
of every activity it awaited — sits in a history that outlives the worker
process, the deploy, and in the roadmap's case the week. When a query arrives, or
a worker picks the run up again, today's code decodes yesterday's bytes.

That makes a dataclass field a wire-compatibility decision, and the two
directions are not symmetric. Measured against `temporalio` 1.31's default
payload converter, which is the one this factory runs:

    encoded  {"max_concurrent_epics": 1, "max_concurrent_nodes": 3, ...}
    decoded with an EXTRA key    -> fine, the unknown key is dropped
    decoded with a MISSING key   -> TypeError: RoadmapStatus.__init__()
                                    missing 1 required positional argument:
                                    'max_concurrent_nodes'

Removing a field is survivable. *Adding* one without a default is not: the
converter builds the record with `cls(**decoded)`, so a field the older payload
never carried is a missing required argument, and the exception surfaces to the
operator as whatever the call site happened to be doing — for 052 it was
`ergane status`, which died with that message and nothing else.

So the rule this file holds (FR-006) is: every field of a record that crosses
the Temporal payload boundary either has a default, or is named in an explicit
allowlist because a default there would be a lie.

Nothing here needs a Temporal server. The payload roundtrip goes through the
converter in-process, and the query is called as the plain method it is.
"""

from __future__ import annotations

import json
from typing import Any

import temporalio.api.common.v1 as common
from temporalio.converter import default as default_data_converter

from factory.roadmap.workflow import RoadmapStatus, RoadmapWorkflow


def payload_of(value: Any) -> common.Payload:
    """Encode with the converter the factory actually runs, not a stand-in."""
    return default_data_converter().payload_converter.to_payload(value)


def decode_as(payload: common.Payload, record: type) -> Any:
    """Decode with the converter the factory actually runs."""
    return default_data_converter().payload_converter.from_payload(payload, record)


def payload_missing(value: Any, *field_names: str) -> common.Payload:
    """The same payload as an older worker, before those fields existed, wrote it.

    A history recorded before a field existed is byte-for-byte a payload with
    that key absent, so the fixture is the real encoding with keys removed — not
    a hand-built dict that might disagree with the converter about how the rest
    of the record is spelled. Each name is asserted present before it is removed,
    so a renamed field makes this loud instead of making it vacuous.
    """
    encoded = payload_of(value)
    body = json.loads(encoded.data)
    for name in field_names:
        assert name in body, (
            f"{name!r} is not in the encoded payload of {type(value).__name__}, "
            "so removing it proves nothing"
        )
        del body[name]
    return common.Payload(metadata=encoded.metadata, data=json.dumps(body).encode())


# --- US2-S1: an older history is still readable -------------------------------


def test_roadmap_status_reconstructs_from_a_payload_that_predates_the_bound() -> None:
    """The exact shape of the 052 defect, as a payload rather than a story.

    `max_concurrent_nodes` joined `RoadmapStatus` after the record shipped. Every
    roadmap history written before that day encodes a `RoadmapStatus` without the
    key, and decoding one has to succeed at the documented default rather than
    raise.
    """
    current = RoadmapStatus(
        specs=[],
        running=[],
        parked=[],
        max_concurrent_epics=1,
        max_concurrent_nodes=3,
        paused=False,
    )
    older = payload_missing(current, "max_concurrent_nodes")

    reconstructed = decode_as(older, RoadmapStatus)

    # 1 is the default `RoadmapInput.max_concurrent_nodes` already documents:
    # one node in flight per child epic, the sequential behaviour an
    # unconfigured roadmap gets.
    assert reconstructed.max_concurrent_nodes == 1
    assert reconstructed.max_concurrent_epics == 1
    assert reconstructed.specs == []


def test_roadmap_status_reconstructs_from_a_payload_that_predates_either_bound() -> None:
    """Both bounds are knobs with one documented default, so both must default.

    `max_concurrent_epics` is the older of the two and is not the field that
    broke `ergane status`, but it is the same kind of field — a bound whose
    absence means "the roadmap was not configured", never "the roadmap does not
    know" — so leaving it required would leave the same trap set one field over.
    """
    current = RoadmapStatus(
        specs=[],
        running=[],
        parked=[],
        max_concurrent_epics=2,
        max_concurrent_nodes=3,
    )
    older = payload_missing(current, "max_concurrent_epics", "max_concurrent_nodes")

    reconstructed = decode_as(older, RoadmapStatus)

    assert reconstructed.max_concurrent_epics == 1
    assert reconstructed.max_concurrent_nodes == 1


def test_the_zero_state_query_reports_the_bounds_in_force() -> None:
    """The construction site that raised the message the operator actually saw.

    `roadmap_status` answers before the corpus has been read — a run that has not
    finished its first pass, or one whose replay stopped short of it — and that
    branch built a `RoadmapStatus` without `max_concurrent_nodes` at all. With no
    default on the field it raised `TypeError` *inside the worker*, which the
    client re-raised as a query failure carrying the message verbatim.

    A default alone would make this branch answer, and answer wrongly: it would
    report the shipped default instead of the bound the run is holding. So the
    branch has to pass the bounds in force, and this test fails either way — no
    default (raises) or a default leaned on (reports 1 for a run bounded at 4).

    Calling the query as a plain method is deliberate: it is a read-only handler
    that executes no activity and touches no `workflow` API on this path, so it
    needs no server and no test environment to answer.
    """
    roadmap = RoadmapWorkflow()
    roadmap._max_concurrent_epics = 3
    roadmap._max_concurrent_nodes = 4

    answer = roadmap.roadmap_status()

    assert answer.specs == []
    assert answer.running == []
    assert answer.parked == []
    assert answer.max_concurrent_epics == 3
    assert answer.max_concurrent_nodes == 4
