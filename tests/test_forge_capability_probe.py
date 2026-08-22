"""078-US2: install verification refuses a `gh` that cannot answer the poller.

On 2026-08-20 an epic parked because the host's `gh` could not answer one of the
`--json` fields `poll_landing` sends. Nothing told the operator: the suite was
green on the maintainer's machine, `ergane install --verify` said the GitHub CLI
was "present and usable" — meaning on `PATH` and authenticated — and the first
report of the gap was a node stuck in ENQUEUED hours later.

This file is the check that names it first. It asks the installed binary which
`--json` fields it declares, compares that against **the field set the poller
itself sends**, and turns the three possible answers into three different
sentences:

- *capable* — a pass that says which binary answered, at which version, and
  which fields were checked. A green line that does not say what it checked is
  the defect class in `verify/readiness-proves-a-thing-is-declared-not-that-it-works`;
- *incapable* — a failure naming the missing field, the installed version, and
  the upgrade remedy;
- *absent* — a distinct named condition, because "install it" and "upgrade it"
  are different remedies and telling an operator the wrong one costs an evening.

**Every test here drives the real code path against a stub `gh` on `PATH`**, not
against an injected fake capability: a script in `tmp_path` that answers
`--version` and `__complete`, and logs every argv it was given. The stub is what
makes the incapable case reproducible on any host and what lets the field set be
mutated under a fixed vocabulary. The one thing no stub can prove — that the
probe reads the poller's own value rather than a copy — is proved by mutating
`factory.mergequeue.gh._VIEW_FIELDS` and watching the unedited probe follow it.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Sequence

import pytest

import factory.controlplane.verify as verify_module
import factory.mergequeue.gh as gh_module
from factory.controlplane.config import ControlPlaneConfig as Cfg
from factory.mergequeue.gh import (
    FORGE_ABSENT,
    FORGE_CAPABLE,
    FORGE_INCAPABLE,
    FORGE_UNDETERMINED,
    _VIEW_FIELDS,
    inspect_forge_capability,
    poller_view_argv,
)

#: A `--json` field name no forge CLI has ever declared. Used as the mutation
#: below, where it stands in for "a field this binary is too old to know".
INVENTED_FIELD = "erganeMutationOnlyField"

#: The version the stub reports. Deliberately not this host's: a test that
#: asserted the real version would be asserting the machine.
STUB_VERSION = "2.31.0"

#: The name install verification renders this check under.
_CHECK_NAME = "forge"


def _write_stub_forge_cli(
    directory: Path,
    *,
    declares: Sequence[str],
    version: str = STUB_VERSION,
    log: Path | None = None,
) -> Path:
    """Write an executable stub of the forge CLI that declares exactly `declares`.

    It answers the two questions the capability check is allowed to ask — its
    version, and the `--json` vocabulary of a command — in the shape the real
    binary answers them (one field per line, terminated by the completion
    directive line). Everything else exits non-zero, so a check that tried to
    *run* a poll against it, with the credential and the network that needs,
    would be visible in the log rather than silently tolerated.
    """
    script = directory / "gh"
    # Nothing but shell builtins: the check runs its questions under the same
    # scrubbed environment the real runner uses, whose `PATH` is whatever the
    # caller's is — which in these tests is this directory and nothing else. A
    # stub reaching for `cat` would fail there for a reason that has nothing to
    # do with what is being measured.
    lines = [
        "#!/bin/sh",
        f'printf "%s\\n" "$*" >> {log}' if log is not None else "",
        'if [ "$1" = "--version" ]; then',
        f'  echo "gh version {version} (2026-01-01)"',
        f'  echo "https://github.com/cli/cli/releases/tag/v{version}"',
        "  exit 0",
        "fi",
        'if [ "$1" = "__complete" ]; then',
        *(f"  echo '{field}'" for field in declares),
        '  echo ":2"',
        "  exit 0",
        "fi",
        'echo "stub forge CLI was asked to run: $*" >&2',
        "exit 1",
    ]
    script.write_text("\n".join(line for line in lines if line) + "\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


def _poller_fields() -> tuple[str, ...]:
    """The poller's field set, read from the poller's own value."""
    return tuple(field for field in _VIEW_FIELDS.split(",") if field)


def _blank_config() -> Cfg:
    """A config whose subsystems are disabled; the capability probe ignores it."""
    return Cfg(
        version=1,
        llm=Cfg.LLM(mode="gateway"),
        memory=Cfg.Memory(backend="none"),
        temporal=Cfg.Temporal(mode="external"),
        telemetry=Cfg.Telemetry(mode="none"),
        escalation=Cfg.Escalation(adapter="telegram"),
    )


async def _finding_for(stub_directory: Path, monkeypatch: pytest.MonkeyPatch):
    """Run the real probe with `stub_directory` as the whole of `PATH`."""
    monkeypatch.setenv("PATH", str(stub_directory))
    probe = verify_module.ForgeCapabilityProbe()
    snapshot = await probe.gather(_blank_config())
    return snapshot, probe.evaluate(snapshot)


# ---------------------------------------------------------------------------
# T012 [US2-S1, FR-005] a refused field fails verification, by name and version
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_refused_poller_field_fails_verification_naming_field_and_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The 2026-08-20 host, reproduced: one field short of what the poller sends.

    The stub declares every field the poller asks for except the last one, so
    the refusal is a real vocabulary gap rather than a broken binary — exactly
    the shape that parked the epic.
    """
    fields = _poller_fields()
    refused = fields[-1]
    log = tmp_path / "argv.log"
    _write_stub_forge_cli(tmp_path, declares=fields[:-1], log=log)

    snapshot, finding = await _finding_for(tmp_path, monkeypatch)

    assert finding.passed is False
    assert snapshot.condition == FORGE_INCAPABLE
    assert refused in finding.detail, finding.detail
    assert STUB_VERSION in finding.detail, finding.detail
    assert str(tmp_path / "gh") in finding.detail, finding.detail
    # The remedy, and it is the one for an out-of-date binary.
    assert "upgrade" in finding.detail.lower(), finding.detail
    assert "cli.github.com" in finding.detail, finding.detail
    # And it never tried to *run* a poll: no credential, no network, no repo.
    asked = log.read_text(encoding="utf-8").splitlines()
    assert asked, "the check never invoked the binary at all"
    assert all(
        line.startswith("--version") or line.startswith("__complete") for line in asked
    ), asked


# ---------------------------------------------------------------------------
# T013 [US2-S2, FR-007] a pass says what it verified and which binary answered
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_passing_check_says_what_it_verified_and_which_binary_answered(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A green line that does not say what it checked is worth nothing.

    So the pass is asserted to carry all four of: the resolved path, the
    version, the command, and every field name it settled — not just `passed`.
    """
    fields = _poller_fields()
    _write_stub_forge_cli(tmp_path, declares=[*fields, "someFieldNobodyAsksFor"])

    snapshot, finding = await _finding_for(tmp_path, monkeypatch)

    assert finding.passed is True
    assert snapshot.condition == FORGE_CAPABLE
    assert snapshot.binary == str(tmp_path / "gh")
    assert snapshot.fields == fields
    assert snapshot.undeclared == ()

    assert str(tmp_path / "gh") in finding.detail, finding.detail
    assert STUB_VERSION in finding.detail, finding.detail
    assert " ".join(snapshot.command) in finding.detail, finding.detail
    for field in fields:
        assert field in finding.detail, f"{field} not named in: {finding.detail}"


# ---------------------------------------------------------------------------
# T014 [US2-S3, FR-006] absent is a distinct named condition from incapable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_absent_is_a_distinct_named_condition_from_incapable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Absent and incapable have different remedies, so they are different answers.

    Both fail. What must differ is the name of the condition and the sentence
    the operator acts on: an absent binary is installed, an old one is upgraded,
    and an operator sent to the wrong one of those loses the evening.
    """
    incapable_home = tmp_path / "old"
    incapable_home.mkdir()
    _write_stub_forge_cli(incapable_home, declares=_poller_fields()[:-1])
    empty_home = tmp_path / "empty"
    empty_home.mkdir()

    _, incapable = await _finding_for(incapable_home, monkeypatch)
    absent_snapshot, absent = await _finding_for(empty_home, monkeypatch)

    assert incapable.passed is False
    assert absent.passed is False
    assert absent_snapshot.condition == FORGE_ABSENT
    assert absent_snapshot.condition != FORGE_INCAPABLE
    assert absent.detail != incapable.detail

    # The absent case names installation and cannot name a version it never read.
    assert "install" in absent.detail.lower(), absent.detail
    assert "upgrade" not in absent.detail.lower(), absent.detail
    assert absent_snapshot.version == ""
    assert absent_snapshot.binary is None
    # ...and it does not accuse a field of being refused by a binary that is not there.
    assert absent_snapshot.undeclared == ()
    for field in _poller_fields():
        assert field not in absent.detail, absent.detail


# ---------------------------------------------------------------------------
# T015 [US2-S4, FR-003] the mutation: the probe follows the poller's field set
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_probe_follows_the_pollers_field_set_without_being_edited(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Trap 5's control, and the reason this story is not the defect one layer up.

    The whole 2026-08-20 defect was one hand-maintained list disagreeing with
    another. A capability check carrying its own copy of the field set would
    rebuild it exactly, and would pass this file's other tests while doing so —
    they all use the real field set, which a copy would match on the day it was
    written.

    So the field set is *changed* here, with the binary's vocabulary held fixed,
    and the probe is not edited. Both directions are asserted: a field added to
    what the poller sends is refused by name, and a field set narrowed to what
    the binary declares passes and reports the narrowed set. A probe with a copy
    fails both.
    """
    declared = ("state", "isDraft", "mergeStateStatus")
    _write_stub_forge_cli(tmp_path, declares=declared)

    # Direction one: the poller starts asking for something new. Nothing here
    # touches the probe — only the value `poll_pr` sends.
    monkeypatch.setattr(gh_module, "_VIEW_FIELDS", ",".join([*declared, INVENTED_FIELD]))
    grown_snapshot, grown = await _finding_for(tmp_path, monkeypatch)

    assert grown.passed is False
    assert grown_snapshot.condition == FORGE_INCAPABLE
    assert grown_snapshot.undeclared == (INVENTED_FIELD,)
    assert INVENTED_FIELD in grown.detail, grown.detail

    # Direction two: the poller narrows. The same unedited probe now passes, and
    # says it verified the narrowed set — a copy would still name the old one.
    monkeypatch.setattr(gh_module, "_VIEW_FIELDS", ",".join(declared[:2]))
    narrowed_snapshot, narrowed = await _finding_for(tmp_path, monkeypatch)

    assert narrowed.passed is True
    assert narrowed_snapshot.fields == declared[:2]
    assert "mergeStateStatus" not in narrowed.detail, narrowed.detail
    assert INVENTED_FIELD not in narrowed.detail, narrowed.detail


def test_the_checked_argv_is_built_by_the_poller_itself() -> None:
    """The derivation, asserted at its source: the argv comes from `poll_pr`.

    `poller_view_argv()` records what `GhClient.poll_pr` builds rather than
    describing it, so the command *and* the field set follow the poller. This is
    the same thing 071-US2 got wrong by enumerating methods and never reading
    the argument inside one of them.
    """
    argv = poller_view_argv()

    assert "--json" in argv
    index = argv.index("--json")
    assert argv[index + 1] == _VIEW_FIELDS, (
        "the checked field set must be the value the poller sends, not a copy"
    )
    assert argv[:index], "the command the poller issues was not recorded"


# ---------------------------------------------------------------------------
# The probe is reached by install verification, not merely defined
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_install_verification_itself_reports_the_refusal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US2-S1 end to end: the operator runs verification and reads the refusal.

    A probe class nobody registered is a check that never runs — which is the
    finding this story is named after. So this goes through the entry point the
    CLI calls and reads the rendered report, with the other subsystems' seams
    made to fail fast so the test measures the forge line and not the network.
    """
    forge_home = tmp_path / "bin"
    forge_home.mkdir()
    fields = _poller_fields()
    _write_stub_forge_cli(forge_home, declares=fields[:-1])
    monkeypatch.setenv("PATH", str(forge_home))

    monkeypatch.setattr(verify_module, "_host_seam_factory", _passing_host_seam)
    for seam in (
        "_llm_client_factory",
        "_temporal_client_factory",
        "_memory_client_factory",
        "_telegram_bot_factory",
    ):
        monkeypatch.setattr(verify_module, seam, _raising(seam))

    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'version = 1\n\n[llm]\nmode = "gateway"\nbase_url = "http://llm.test"\n'
        'master_key_env = "ERGANE_LLM_MASTER_KEY"\n\n[memory]\nbackend = "none"\n\n'
        '[temporal]\nmode = "external"\naddress = "127.0.0.1:1"\nnamespace = "factory"\n\n'
        '[telemetry]\n\n[escalation]\nadapter = "none"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("ERGANE_CONFIG_PATH", str(config_path))

    findings, exit_code = await verify_module.verify_controlplane_async(str(config_path))

    assert exit_code == 1
    report = verify_module.render_findings(findings)
    forge_line = next(
        line for line in report.splitlines() if line.startswith(f"[FAIL] {_CHECK_NAME}:")
    )
    assert fields[-1] in forge_line, forge_line
    assert STUB_VERSION in forge_line, forge_line


def test_the_probe_is_registered_with_install_verification() -> None:
    """The registration itself, asserted: an unregistered probe checks nothing."""
    registered = [
        probe
        for probe in verify_module.REGISTRY
        if isinstance(probe, verify_module.ForgeCapabilityProbe)
    ]

    assert len(registered) == 1, [probe.name for probe in verify_module.REGISTRY]
    assert registered[0].name == _CHECK_NAME


# ---------------------------------------------------------------------------
# The undetermined condition: a binary that will not say what it declares
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_binary_that_will_not_say_what_it_declares_is_its_own_condition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """"I could not ask" is neither a pass nor an accusation of a missing field.

    It must not pass, because a green line that checked nothing is this story's
    whole subject; and it must not report a field as refused, because no field
    was ever asked about. So it is a fourth named condition.
    """
    _write_stub_forge_cli(tmp_path, declares=())

    snapshot, finding = await _finding_for(tmp_path, monkeypatch)

    assert snapshot.condition == FORGE_UNDETERMINED
    assert finding.passed is False
    assert snapshot.undeclared == ()
    for field in _poller_fields():
        assert field not in finding.detail, finding.detail


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _passing_host_seam() -> dict[str, object]:
    """A host report with every prerequisite present, so `host` is not the story."""
    return {
        name: {
            "present": True,
            "usable": True,
            "purpose": f"host prerequisite `{name}`",
            "remedy": f"install {name}",
        }
        for name in ("bwrap", "git", "gh")
    }


def _raising(name: str):
    """A seam factory that reports `ServiceNotAnswering` for the named subsystem."""

    def factory(*args: object, **kwargs: object) -> object:
        raise verify_module.ServiceNotAnswering(name, reason="not configured in this test")

    return factory
