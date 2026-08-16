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
from factory.notify.service import TEMPORAL_ADDRESS_ENV, TEMPORAL_NAMESPACE_ENV
from factory.usage.litellm_client import MASTER_KEY_ENV, PROXY_URL_ENV

#: What the fixture config's `[temporal]` block declares. 048-US4 added these
#: two to the report, so tests counting resolved values count four, not two.
DECLARED_TEMPORAL_ADDRESS = "declared.temporal.test:7233"
DECLARED_TEMPORAL_NAMESPACE = "declared"

OVERRIDE_TEMPORAL_ADDRESS = "override.temporal.test:7233"
OVERRIDE_TEMPORAL_NAMESPACE = "override-namespace"

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
    """Remove every override variable this repository's own shell exports.

    All four since 048-US4: `scripts/ergane-env.sh` exports both `TEMPORAL_*`
    names too, and now that they can win a value, a test leaving them set would
    report on the shell rather than on the fixture config (plan trap 4).
    """
    monkeypatch.delenv(PROXY_URL_ENV, raising=False)
    monkeypatch.delenv(MASTER_KEY_ENV, raising=False)
    monkeypatch.delenv(TEMPORAL_ADDRESS_ENV, raising=False)
    monkeypatch.delenv(TEMPORAL_NAMESPACE_ENV, raising=False)


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
    # 048-US4 added Temporal's two values, so a declared host now has four
    # values sourced to its config rather than two.
    assert f"Temporal address: {DECLARED_TEMPORAL_ADDRESS}" in result.stdout
    assert f"Temporal namespace: {DECLARED_TEMPORAL_NAMESPACE}" in result.stdout
    # The config path is named as the winning source once per value.
    assert (
        result.stdout.count(f"  source: the control-plane config at {config_path}") == 4
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
    # All four since 048-US4, set rather than inherited: the count at the end is
    # of *values whose override won*, and leaving Temporal to the shell made it
    # two on a bare host and four with `scripts/ergane-env.sh` loaded — a test
    # whose answer depended on who ran it (plan trap 4).
    monkeypatch.setenv(TEMPORAL_ADDRESS_ENV, OVERRIDE_TEMPORAL_ADDRESS)
    monkeypatch.setenv(TEMPORAL_NAMESPACE_ENV, OVERRIDE_TEMPORAL_NAMESPACE)

    result = _invoke("env", "--sources")

    assert result.code == 0
    assert f"LLM gateway endpoint: {OVERRIDE_BASE_URL}" in result.stdout
    assert f"LLM gateway credential variable: {MASTER_KEY_ENV}" in result.stdout
    assert f"  source: {PROXY_URL_ENV} (environment override)" in result.stdout
    assert f"  source: {MASTER_KEY_ENV} (environment override)" in result.stdout
    assert f"Temporal address: {OVERRIDE_TEMPORAL_ADDRESS}" in result.stdout
    assert f"  source: {TEMPORAL_ADDRESS_ENV} (environment override)" in result.stdout
    assert f"  source: {TEMPORAL_NAMESPACE_ENV} (environment override)" in result.stdout

    # The declaration lost. No declared value may be reported as resolved —
    # and since the file is never opened when an override speaks (FR-002), the
    # declared values cannot appear at all.
    assert DECLARED_BASE_URL not in result.stdout
    assert f"credential variable: {DECLARED_KEY_VAR}" not in result.stdout
    assert DECLARED_TEMPORAL_ADDRESS not in result.stdout

    # The config is still named as the route not taken, so the operator learns
    # where the declaration lives without the report having read it.
    assert (
        result.stdout.count(
            f"  other route: the control-plane config at {config_path} "
            "(not consulted: the override won)"
        )
        == 4
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
    # 048-US4: the claim is "the file was not opened", and it is opened per
    # *value*. Overriding only the LLM pair would leave two values still
    # reaching for the config, failing the assertions below against a resolver
    # behaving exactly as FR-002 requires.
    monkeypatch.setenv(TEMPORAL_ADDRESS_ENV, OVERRIDE_TEMPORAL_ADDRESS)
    monkeypatch.setenv(TEMPORAL_NAMESPACE_ENV, OVERRIDE_TEMPORAL_NAMESPACE)

    result = _invoke("env", "--sources")

    assert result.code == 0
    assert f"LLM gateway endpoint: {OVERRIDE_BASE_URL}" in result.stdout
    assert f"LLM gateway credential variable: {MASTER_KEY_ENV}" in result.stdout
    assert f"Temporal address: {OVERRIDE_TEMPORAL_ADDRESS}" in result.stdout
    assert f"Temporal namespace: {OVERRIDE_TEMPORAL_NAMESPACE}" in result.stdout
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
    # Four values now, and a broken config refuses for each: a Temporal value
    # quietly falling back to `localhost:7233` because the file would not parse
    # is the worse half of this defect, not the forgiving one (048-US4).
    assert "Temporal address: unresolved" in result.stdout
    assert result.stdout.count("the control-plane config cannot be used") == 4
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
# The defect pattern that has cost this repository more than any other is a
# test that cannot fail. So each behaviour below was broken on purpose in
# `factory/cli/env.py` and this file re-run. Every mutation was reverted before
# the evidence was written — the clean run at the end of the battery is pasted
# too — so the tree these transcripts describe is the tree in this diff.
#
#   $ uv run pytest -q --no-header tests/test_env_sources.py   # per mutation
#
# M1  the report always names the environment variable as the source
#     [`if source == override_env` → `if True`]
#     1 failed, 8 passed
#       test_sources_names_the_config_when_the_declaration_wins
#
# M2  the report always names the config as the source
#     [`if source == override_env` → `if False`]
#     1 failed, 8 passed
#       test_sources_names_the_environment_when_the_override_wins
#
# M3  the credential row prints the value instead of the variable name
#     [`_credential` returns `os.environ.get(ref.env_name, "")`]
#     5 failed, 4 passed
#       test_sources_names_the_config_when_the_declaration_wins
#       test_sources_names_the_environment_when_the_override_wins
#       test_sources_does_not_open_the_config_when_the_override_wins
#       test_the_planted_credential_appears_nowhere_in_the_report[declaration]
#       test_the_planted_credential_appears_nowhere_in_the_report[override]
#     This is the leak the sentinel exists for, and both parametrised cases
#     die on it: the report was rendering a real credential.
#
# M4  an unresolved value prints the word and no reason
#     [drop the `f"  {refusal}"` line]
#     2 failed, 7 passed
#       test_nothing_resolved_names_both_routes_and_still_exits_zero
#       test_a_broken_config_is_reported_as_the_parsers_own_refusal
#
# M5  the two override variables are labelled `required` again
#     [`_OVERRIDE_SOURCE = "required"`]
#     1 failed, 8 passed
#       test_bare_env_renders_byte_identically_except_the_two_false_labels
#
# M6  the bare listing's separator narrows by one space
#     [`{default_note}  [` → `{default_note} [`]
#     1 failed, 8 passed
#       test_bare_env_renders_byte_identically_except_the_two_false_labels
#     The one that matters most. A byte-parity pin has to stay green under
#     every correct change, so the only way to know it is not decoration is to
#     move a byte no test names and watch it die. M5 kills it through the two
#     lines that were *meant* to change; M6 kills it through the five that
#     were not.
#
# M7  the report opens the config even when the override won
#     [`load_controlplane_config(config_label)` before rendering]
#     3 failed, 6 passed
#       test_sources_does_not_open_the_config_when_the_override_wins
#       test_nothing_resolved_names_both_routes_and_still_exits_zero
#       test_a_broken_config_is_reported_as_the_parsers_own_refusal
#
# M8  the report gates: a value it cannot resolve exits non-zero
#     2 failed, 7 passed
#       test_nothing_resolved_names_both_routes_and_still_exits_zero
#       test_a_broken_config_is_reported_as_the_parsers_own_refusal
#
# M9  `--sources` prints nothing at all
#     7 failed, 2 passed
#       every test above that reads the report, including both sentinel cases
#     Which is the answer to "would the sentinel assertions pass against empty
#     output?" — they would not, because each is paired with an assertion that
#     the credential's variable *name* was printed.
#
# M10 bare `ergane env` also prints the sources report
#     1 failed, 8 passed
#       test_bare_env_renders_byte_identically_except_the_two_false_labels
#     `--sources` is a mode, not an addition (FR-017).
#
# M11 the `AFTER` literal in this file gains a third changed line
#     [`TELEGRAM_BOT_TOKEN=  [not set, required]` → `[not set, needed by the
#      notifier]`, in the test file rather than in production code]
#     2 failed, 7 passed
#       test_bare_env_renders_byte_identically_except_the_two_false_labels
#       test_the_two_literals_above_differ_on_exactly_the_two_override_lines
#     Recorded because the fixture guard is the one test in this file no
#     production mutation can kill, by construction — it compares two
#     literals. This is the edit it exists to catch.
#
#   after the battery, reverted:  9 passed in 0.13s
#
# Every test in this file is killed by at least one mutation above, and each
# of the eight behavioural ones by a mutation of production code.
#
#
# --- Bare `ergane env`: byte-parity against the base tree's own renderer ----
#
# Not asserted from memory. `git show 2a40d1d:factory/cli/env.py` was loaded
# as a second module beside this diff's, both were handed the same environment,
# and their output was diffed — in all three shapes an operator's shell can be
# in.
#
#   $ python parity.py     # base renderer vs this diff's, same os.environ
#   --- unified diff
#   --- 2a40d1d
#   +++ HEAD
#   @@ -3,2 +3,2 @@
#   -LITELLM_PROXY_URL=  [set, required]
#   -LITELLM_MASTER_KEY=[REDACTED]  [set, required]
#   +LITELLM_PROXY_URL=  [set, override of the control-plane config]
#   +LITELLM_MASTER_KEY=[REDACTED]  [set, override of the control-plane config]
#   --- lines: 7 before, 7 after; byte-identical lines: 5; changed: [2, 3]
#
#        nothing set: 7 lines, byte-identical 5, changed lines [2, 3]
#     everything set: 7 lines, byte-identical 5, changed lines [2, 3]
#              mixed: 7 lines, byte-identical 5, changed lines [2, 3]
#
# Seven entries, five byte-identical, two changed, and the two are the ones
# US1 made untrue. No separator, no order, no state word moved.
#
#
# --- The report on a host where the two sources disagree -------------------
#
# `ergane env --sources` for real, from the installed console script, under a
# scratch HOME with `ERGANE_CONFIG_PATH` bound. Paths elided to `$SB`; nothing
# below touched the operator's config or runtime root. The planted credential
# was `sk-sentinel-must-never-be-rendered` in every case and appears nowhere.
#
#   (a) no LITELLM_* set at all; the config declares the gateway
#   exit: 0
#   LLM gateway endpoint: http://declared.gateway.test/v1
#     source: the control-plane config at $SB/config.toml
#     other route: LITELLM_PROXY_URL (environment override, not set)
#   LLM gateway credential variable: MY_DECLARED_KEY
#     source: the control-plane config at $SB/config.toml
#     other route: LITELLM_MASTER_KEY (environment override, not set)
#
#   This is the host the finding describes, and the line that used to read
#   `LITELLM_PROXY_URL=  [not set, required]`.
#
#   (b) both overrides exported; the config declares different values
#   exit: 0
#   LLM gateway endpoint: http://override.gateway.test/v1
#     source: LITELLM_PROXY_URL (environment override)
#     other route: the control-plane config at $SB/config.toml (not consulted:
#                  the override won)
#   LLM gateway credential variable: LITELLM_MASTER_KEY
#     source: LITELLM_MASTER_KEY (environment override)
#     other route: the control-plane config at $SB/config.toml (not consulted:
#                  the override won)
#
#   This is this development host. The declared endpoint does not appear,
#   because the file was not opened (FR-002).
#
#   (c) they disagree *per value*: the config declares the endpoint, the
#       environment holds the credential
#   exit: 0
#   LLM gateway endpoint: http://declared.gateway.test/v1
#     source: the control-plane config at $SB/config.toml
#     other route: LITELLM_PROXY_URL (environment override, not set)
#   LLM gateway credential variable: LITELLM_MASTER_KEY
#     source: LITELLM_MASTER_KEY (environment override)
#     other route: the control-plane config at $SB/config.toml (not consulted:
#                  the override won)
#
#   Different winners in one report. This is why the two values are resolved
#   separately rather than as a pair, and it is the shape a half-provisioned
#   second machine is actually in.
#
#   (d) no override, no file
#   exit: 0
#   LLM gateway endpoint: unresolved
#     no LLM gateway endpoint is available: set LITELLM_PROXY_URL in the
#     environment, or declare the gateway in $SB/absent.toml (`ergane install`
#     writes it)
#   LLM gateway credential variable: unresolved
#     no LLM gateway credential is available: set LITELLM_MASTER_KEY in the
#     environment, or declare the gateway in $SB/absent.toml (`ergane install`
#     writes it)
#
#   (e) the file is there and the parser refuses it
#   exit: 0
#   LLM gateway endpoint: unresolved
#     the control-plane config cannot be used: $SB/broken.toml:
#     [malformed_toml] is not parseable TOML: Expected ']' at the end of a
#     table declaration (at line 2, column 5)
#   LLM gateway credential variable: unresolved
#     [the same refusal]
#
#   (d) and (e) are the pair trap 3 draws: an absent config degrades to the
#   both-routes refusal, a broken one surfaces the parser's own reason and the
#   file. Both exit zero, because `ergane env` reports and does not gate.
#
#
# --- The full suite, on the tree in this diff ------------------------------
#
#   $ uv run pytest -q
#   2780 passed, 44 skipped, 5 warnings in 293.26s (0:04:53)
#
# Run twice, on this tree and on the same tree before this comment block was
# written: 2780 passed both times, 301.91s and 293.26s. The only difference
# between the tree that was measured and the tree in this diff is the text you
# are reading, which is a comment — said out loud because pasting a suite line
# into the file the suite ran over is unavoidably circular, and the honest
# thing is to name the circle rather than hide it.
#
# 2771 passed on the base at 2a40d1d (US1's recorded figure); the nine added
# here are this file.
