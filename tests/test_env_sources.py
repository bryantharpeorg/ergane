"""048-US3: `ergane env --sources` reports which source won for each value.

US1 joined the declaration to the build. A human standing at a second machine
still could not tell that it had worked: `ergane env` reported
`LITELLM_PROXY_URL` as `not set` on a host whose config supplied the endpoint
and whose build would have started fine. This file pins the verb that makes
US1 checkable by that human.

Four disciplines the whole file obeys:

- **`--sources` is a new mode; the bare command's output is pinned to
  byte-parity** (FR-017). An operator may already be reading that listing on an
  unfamiliar machine, and this is the spec whose whole point is that
  diagnostics were lying. The one deliberate exception is the word `required`
  on the two override variables, which US1 made false.
- **The fixture config and the fixture environment disagree on every value they
  both carry** (plan trap 5). If they agreed, no test here could tell which
  source the report actually consulted — which is the entire subject of the
  story.
- **Every test binds `ERGANE_CONFIG_PATH` to a `tmp_path`** and deletes the
  legacy alias (FR-012, plan trap 4). `resolve_config_path()` falls back to
  `$XDG_CONFIG_HOME` and then `Path.home()`, so a test that forgot would read
  the operator's real `~/.config/ergane/config.toml` — a file that exists on
  this host, that the operator edits, and that will not exist on the grader's.
  Same class as the store-isolation defect of 2026-08-14.
- **Every test that asserts a credential's absence also asserts that the
  report printed something.** A sentinel assertion against empty output is the
  purest form of a test that cannot fail.

The runtime evidence — the red run, one mutation per behaviour, and the report
as it renders on a host where the two sources disagree — is pasted verbatim at
the bottom of this file (constitution VIII / D-037).
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import NamedTuple

import pytest

from factory.cli import main as main_module
from factory.env import ERGANE_CONFIG_PATH_ENV, FACTORY_CONFIG_PATH_ENV
from factory.usage.litellm_client import MASTER_KEY_ENV, PROXY_URL_ENV

# --- fixture values: the two sources disagree on everything (plan trap 5) -----

DECLARED_BASE_URL = "http://declared.gateway.test/v1"
DECLARED_KEY_VAR = "DECLARED_KEY_VAR"

OVERRIDE_BASE_URL = "http://override.gateway.test/v1"

#: A credential that could leak if the report ever rendered a *value* where a
#: variable name belongs (plan trap 6). Distinctive on purpose: a blank or
#: absent fixture credential would make US3-S3 worthless.
SENTINEL_CREDENTIAL = "sk-sentinel-048-us3-must-never-be-rendered"

#: The credential the *losing* source declares, so that "the winner won" and
#: "the loser was not consulted" are separable claims.
LOSING_CREDENTIAL = "sk-declared-048-us3-loser-never-consulted"


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str


def _invoke(*argv: str) -> Run:
    """Run one `ergane` invocation, capturing both streams."""
    old_out, old_err = sys.stdout, sys.stderr
    out, err = io.StringIO(), io.StringIO()
    try:
        sys.stdout, sys.stderr = out, err
        try:
            code = main_module.main(list(argv))
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    return Run(code, out.getvalue(), err.getvalue())


def _write_config(tmp_path: Path) -> Path:
    """A complete, parseable config declaring a gateway, at a bound path.

    All five blocks, because the parser requires all five, and
    `temporal.address` because `temporal.mode = "external"` requires it (plan
    trap 12b): a missing one presents as US1's broken-config refusal and sends
    you hunting in the wrong module.
    """
    path = tmp_path / "config.toml"
    path.write_text(
        f"""\
version = 1

[llm]
mode = "gateway"
base_url = "{DECLARED_BASE_URL}"
master_key_env = "{DECLARED_KEY_VAR}"

[memory]
backend = "none"

[temporal]
mode = "external"
address = "declared.temporal.test:7233"
namespace = "declared"

[telemetry]

[escalation]
adapter = "telegram"
chat_id_env = "DECLARED_CHAT_ID"
bot_token_env = "DECLARED_BOT_TOKEN"
""",
        encoding="utf-8",
    )
    return path


def _write_broken_config(tmp_path: Path) -> Path:
    """TOML the parser refuses, at a bound path."""
    path = tmp_path / "config.toml"
    path.write_text('version = 1\n[llm\nmode = "gateway"\n', encoding="utf-8")
    return path


def _bind_config(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    """Bind the config path explicitly (FR-012, plan trap 4).

    The legacy alias is deleted rather than set: two variables holding
    different paths emit a deprecation warning, and this file is in the
    business of asserting on exact output.
    """
    monkeypatch.setenv(ERGANE_CONFIG_PATH_ENV, str(path))
    monkeypatch.delenv(FACTORY_CONFIG_PATH_ENV, raising=False)


def _no_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove the two legacy variables this repository's own shell exports."""
    monkeypatch.delenv(PROXY_URL_ENV, raising=False)
    monkeypatch.delenv(MASTER_KEY_ENV, raising=False)


# ---------------------------------------------------------------------------
# T026 / US3-S1 — the declaration won, and the report says so
# ---------------------------------------------------------------------------


def test_sources_names_the_config_when_the_declaration_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US3-S1, FR-011: the freshly-installed host, told that its answers were used.

    This is the case where today's `ergane env` says `LITELLM_PROXY_URL: not
    set` and is technically true and operationally a lie.
    """
    config_path = _write_config(tmp_path)
    _bind_config(monkeypatch, config_path)
    _no_overrides(monkeypatch)
    monkeypatch.setenv(DECLARED_KEY_VAR, SENTINEL_CREDENTIAL)

    result = _invoke("env", "--sources")

    assert result.code == 0
    assert f"LLM gateway endpoint: {DECLARED_BASE_URL}" in result.stdout
    assert f"LLM gateway credential variable: {DECLARED_KEY_VAR}" in result.stdout
    # The config path is named as the winning source once per value.
    assert (
        result.stdout.count(f"  source: the control-plane config at {config_path}") == 2
    )
    # And the route not taken is named too, so the operator learns both ways
    # each value could have been supplied (FR-011).
    assert f"  other route: {PROXY_URL_ENV} (environment override, not set)" in result.stdout
    assert f"  other route: {MASTER_KEY_ENV} (environment override, not set)" in result.stdout
    # The loser must not be reported as a winner.
    assert OVERRIDE_BASE_URL not in result.stdout
    # The two modes are separate: `--sources` reports resolution, not the
    # variable listing the bare command prints.
    assert "ERGANE_VERIFICATION_DB_PATH" not in result.stdout


# ---------------------------------------------------------------------------
# T027 / US3-S2 — the environment overrode the declaration, and the report says so
# ---------------------------------------------------------------------------


def test_sources_names_the_environment_when_the_override_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US3-S2: this development host, which exports both and has no config behind them."""
    config_path = _write_config(tmp_path)
    _bind_config(monkeypatch, config_path)
    monkeypatch.setenv(PROXY_URL_ENV, OVERRIDE_BASE_URL)
    monkeypatch.setenv(MASTER_KEY_ENV, SENTINEL_CREDENTIAL)
    monkeypatch.setenv(DECLARED_KEY_VAR, LOSING_CREDENTIAL)

    result = _invoke("env", "--sources")

    assert result.code == 0
    assert f"LLM gateway endpoint: {OVERRIDE_BASE_URL}" in result.stdout
    assert f"LLM gateway credential variable: {MASTER_KEY_ENV}" in result.stdout
    assert f"  source: {PROXY_URL_ENV} (environment override)" in result.stdout
    assert f"  source: {MASTER_KEY_ENV} (environment override)" in result.stdout

    # The declaration lost. Neither declared value may be reported as resolved
    # — and since the file is never opened when an override speaks (FR-002),
    # the declared endpoint cannot appear at all.
    assert DECLARED_BASE_URL not in result.stdout
    assert f"credential variable: {DECLARED_KEY_VAR}" not in result.stdout

    # The config is still named as the route not taken, so the operator learns
    # where the declaration lives without the report having read it.
    assert (
        result.stdout.count(
            f"  other route: the control-plane config at {config_path} "
            "(not consulted: the override won)"
        )
        == 2
    )


def test_sources_does_not_open_the_config_when_the_override_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-002, US1-S3's shape applied to the report.

    Bound to TOML the parser refuses: a report that opened the file could not
    pass this. It is the only way to observe a read that did not happen.
    """
    broken = _write_broken_config(tmp_path)
    _bind_config(monkeypatch, broken)
    monkeypatch.setenv(PROXY_URL_ENV, OVERRIDE_BASE_URL)
    monkeypatch.setenv(MASTER_KEY_ENV, SENTINEL_CREDENTIAL)

    result = _invoke("env", "--sources")

    assert result.code == 0
    assert f"LLM gateway endpoint: {OVERRIDE_BASE_URL}" in result.stdout
    assert f"LLM gateway credential variable: {MASTER_KEY_ENV}" in result.stdout
    assert "cannot be used" not in result.stdout
    assert "malformed_toml" not in result.stdout


# ---------------------------------------------------------------------------
# T028 / US3-S3 — a planted credential reaches no line of the report
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("winner", ["declaration", "override"])
def test_the_planted_credential_appears_nowhere_in_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, winner: str
) -> None:
    """US3-S3, SC-005, plan trap 6: both routes to a credential, neither rendering one.

    Parametrised over which source wins because the two branches build the
    report from different objects: a report that redacted one and spilled the
    other would pass a single-case test.

    The second half of each assertion pair — that the variable *name* is
    printed — is what stops this test passing against empty output.
    """
    config_path = _write_config(tmp_path)
    _bind_config(monkeypatch, config_path)
    if winner == "declaration":
        _no_overrides(monkeypatch)
        monkeypatch.setenv(DECLARED_KEY_VAR, SENTINEL_CREDENTIAL)
        expected_name = DECLARED_KEY_VAR
    else:
        monkeypatch.setenv(PROXY_URL_ENV, OVERRIDE_BASE_URL)
        monkeypatch.setenv(MASTER_KEY_ENV, SENTINEL_CREDENTIAL)
        expected_name = MASTER_KEY_ENV

    result = _invoke("env", "--sources")

    assert result.code == 0
    assert SENTINEL_CREDENTIAL not in result.stdout
    assert SENTINEL_CREDENTIAL not in result.stderr
    # A variable *name* is not a secret and is exactly what the operator needs;
    # the parser already refuses a credential-shaped value where a name belongs.
    assert f"LLM gateway credential variable: {expected_name}" in result.stdout


# ---------------------------------------------------------------------------
# T029 / US3-S4 — nothing resolved: name both routes, and still exit zero
# ---------------------------------------------------------------------------


def test_nothing_resolved_names_both_routes_and_still_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US3-S4, FR-004: a report is not a gate.

    An operator told about only the environment variable exports it and
    concludes the config does nothing — the belief 048 exists to end. So the
    unresolved case names both routes, for both values, and exits zero anyway.
    """
    absent = tmp_path / "absent.toml"
    _bind_config(monkeypatch, absent)
    _no_overrides(monkeypatch)

    result = _invoke("env", "--sources")

    assert result.code == 0
    assert "LLM gateway endpoint: unresolved" in result.stdout
    assert "LLM gateway credential variable: unresolved" in result.stdout
    for name in (PROXY_URL_ENV, MASTER_KEY_ENV):
        assert f"set {name} in the environment" in result.stdout
    assert result.stdout.count(f"declare the gateway in {absent}") == 2


def test_a_broken_config_is_reported_as_the_parsers_own_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-005 at the report: say the file is wrong, not that a variable is unset.

    The diagnostic that sends an operator to export `LITELLM_PROXY_URL` when
    their config has a typo is the exact failure this command exists to
    prevent. Still exit zero: `ergane env` reports, it does not gate.
    """
    broken = _write_broken_config(tmp_path)
    _bind_config(monkeypatch, broken)
    _no_overrides(monkeypatch)

    result = _invoke("env", "--sources")

    assert result.code == 0
    assert "LLM gateway endpoint: unresolved" in result.stdout
    assert result.stdout.count("the control-plane config cannot be used") == 2
    assert str(broken) in result.stdout
    assert "malformed_toml" in result.stdout
    # Not a story about the environment.
    assert f"set {PROXY_URL_ENV} in the environment" not in result.stdout


# ---------------------------------------------------------------------------
# T030 / US3-S5 — bare `ergane env` is byte-identical, minus two false words
# ---------------------------------------------------------------------------

#: The environment the two literals below were captured under. Every one of the
#: seven variables `_ENTRIES` reads is pinned set or unset, so the rendering is
#: a function of the code alone and not of the shell the suite runs in. The
#: four render branches — set/unset, default/no default, secret/plain — are all
#: exercised.
_BARE_SET = {
    "TEMPORAL_ADDRESS": "temporal.fixture.test:7233",
    "LITELLM_PROXY_URL": "http://fixture.proxy.test/v1",
    "LITELLM_MASTER_KEY": "sk-fixture-master-key-048-us3",
    "ERGANE_LEDGER_PATH": "/fixture/ledger.db",
    # Not read by `_ENTRIES`: the legacy alias is pinned to the same value so
    # the 040 rename resolver does not emit a "both are set" deprecation
    # during parser construction. No path here is ever opened by `ergane env`.
    "FACTORY_LEDGER_PATH": "/fixture/ledger.db",
}
_BARE_UNSET = (
    "TEMPORAL_NAMESPACE",
    "TELEGRAM_BOT_TOKEN",
    "ERGANE_VERIFICATION_DB_PATH",
)

#: Captured from `ergane env` on the tree at `2a40d1d`, before this story
#: touched `factory/cli/env.py`. Pasted verbatim, not reconstructed.
TODAY = (
    "TEMPORAL_ADDRESS= (default: localhost:7233)  [set, default]\n"
    "TEMPORAL_NAMESPACE= (default: factory)  [not set, default]\n"
    "LITELLM_PROXY_URL=  [set, required]\n"
    "LITELLM_MASTER_KEY=[REDACTED]  [set, required]\n"
    "TELEGRAM_BOT_TOKEN=  [not set, required]\n"
    "ERGANE_LEDGER_PATH=  [set, default .factory/ledger.db]\n"
    "ERGANE_VERIFICATION_DB_PATH=  [not set, default .factory/verification.db]\n"
)

#: The same output after this story. Two lines move and five do not.
AFTER = (
    "TEMPORAL_ADDRESS= (default: localhost:7233)  [set, default]\n"
    "TEMPORAL_NAMESPACE= (default: factory)  [not set, default]\n"
    "LITELLM_PROXY_URL=  [set, override of the control-plane config]\n"
    "LITELLM_MASTER_KEY=[REDACTED]  [set, override of the control-plane config]\n"
    "TELEGRAM_BOT_TOKEN=  [not set, required]\n"
    "ERGANE_LEDGER_PATH=  [set, default .factory/ledger.db]\n"
    "ERGANE_VERIFICATION_DB_PATH=  [not set, default .factory/verification.db]\n"
)


def test_bare_env_renders_byte_identically_except_the_two_false_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US3-S5, FR-017: the acceptance condition, not a nicety.

    An operator may already be eyeballing this output on an unfamiliar
    machine, and this is the spec whose whole point is that diagnostics were
    lying. So every unchanged entry is asserted byte-for-byte against what the
    pre-048 tree printed, and the whole stream is compared as one string so
    that a moved separator, a reordered entry or an inserted line cannot pass.

    The one exception is deliberate and fenced: `LITELLM_PROXY_URL` and
    `LITELLM_MASTER_KEY` were labelled `required`, US1 made that false, and a
    report that calls an override required sends an operator to export a
    variable they do not need.
    """
    _bind_config(monkeypatch, tmp_path / "absent.toml")
    for name, value in _BARE_SET.items():
        monkeypatch.setenv(name, value)
    for name in _BARE_UNSET:
        monkeypatch.delenv(name, raising=False)

    result = _invoke("env")

    assert result.code == 0
    assert result.stdout == AFTER

    today_lines = TODAY.splitlines()
    now_lines = result.stdout.splitlines()
    assert len(now_lines) == len(today_lines)
    for before, now in zip(today_lines, now_lines):
        if before.split("=", 1)[0] in (PROXY_URL_ENV, MASTER_KEY_ENV):
            continue
        assert now == before  # byte-equal, entry by entry — not a spot check

    changed = {line.split("=", 1)[0]: line for line in now_lines}
    for name in (PROXY_URL_ENV, MASTER_KEY_ENV):
        assert "required" not in changed[name]
        assert "override of the control-plane config" in changed[name]

    # `--sources` is a mode, not an addition: the bare command prints the
    # listing and nothing else.
    assert "LLM gateway endpoint" not in result.stdout
    assert result.stderr == ""


def test_the_two_literals_above_differ_on_exactly_the_two_override_lines() -> None:
    """A guard on the fixture, not a claim about behaviour — and said out loud.

    This compares two literals in this file. Its job is to stop a later edit
    smuggling a third changed line into `AFTER`, which would leave the
    byte-parity loop above passing while the report had quietly been
    restructured. Without it, `AFTER` is an unchecked restatement of whatever
    the code happens to print.
    """
    today_lines = TODAY.splitlines()
    after_lines = AFTER.splitlines()
    differing = [
        line.split("=", 1)[0]
        for before, line in zip(today_lines, after_lines)
        if before != line
    ]
    assert differing == [PROXY_URL_ENV, MASTER_KEY_ENV]


# ===========================================================================
# Runtime evidence (constitution VIII / D-037): pasted, not described.
# ===========================================================================
#
# --- The red run, before `--sources` existed -------------------------------
#
#   $ uv run pytest -q --no-header -rf --tb=line tests/test_env_sources.py
#   E   AssertionError: assert 2 == 0        [x7, one per --sources test]
#   E   AssertionError: assert 'TEMPORAL_ADD...ication.db]\n'
#                          == 'TEMPORAL_ADD...ication.db]\n'
#   FAILED tests/test_env_sources.py::test_sources_names_the_config_when_the_declaration_wins
#   FAILED tests/test_env_sources.py::test_sources_names_the_environment_when_the_override_wins
#   FAILED tests/test_env_sources.py::test_sources_does_not_open_the_config_when_the_override_wins
#   FAILED tests/test_env_sources.py::test_the_planted_credential_appears_nowhere_in_the_report[declaration]
#   FAILED tests/test_env_sources.py::test_the_planted_credential_appears_nowhere_in_the_report[override]
#   FAILED tests/test_env_sources.py::test_nothing_resolved_names_both_routes_and_still_exits_zero
#   FAILED tests/test_env_sources.py::test_a_broken_config_is_reported_as_the_parsers_own_refusal
#   FAILED tests/test_env_sources.py::test_bare_env_renders_byte_identically_except_the_two_false_labels
#   8 failed, 1 passed, 1 warning in 0.12s
#
#   -- and the byte-parity failure named the two lines, and only those two:
#   E     Skipping 135 identical leading characters in diff
#   E     - L=  [set, override of the control-plane config]
#   E     - LITELLM_MASTER_KEY=[REDACTED]  [set, override of the control-plane config]
#   E     + L=  [set, required]
#   E     + LITELLM_MASTER_KEY=[REDACTED]  [set, required]
#   E       TELEGRAM_BOT_TOKEN=  [not set, required]
#   E       ERGANE_LEDGER_PATH=  [set, default .factory/ledger.db]
#   E       ERGANE_VERIFICATION_DB_PATH=  [not set, default .factory/verification.db]
#
# `assert 2 == 0` is argparse refusing an unknown `--sources`: exit 2 is the
# usage code, so seven of the eight failures are the flag not existing. The
# one test that passed is the fixture guard, which compares two literals in
# this file and is labelled as such above.
#
# A red run is weak evidence on its own — it says the feature is absent, not
# that any single assertion bites. The mutations below are the real answer to
# "what would make this pass if the production code did nothing?".
#
#
# --- Mutation testing, one mutation per behaviour --------------------------
#
# (pasted after the implementation lands)
#
#
# --- The report on a host where the two sources disagree -------------------
#
# (pasted after the implementation lands)
#
#
# --- The full suite, on the tree in this diff ------------------------------
#
# (pasted after the implementation lands)
