"""114-US3: a live tier that did not run says so.

`tests/test_114_us1_smoke_onboards.py` fixed the instance and
`tests/test_114_us2_fixtures_onboard.py` stopped the class. Neither of them
addresses what let the defect live for twelve days: `5055 passed, 57 skipped`
is a line that reads as *everything is fine* and means *everything that ran is
fine*. Six live tiers are registered in `pyproject.toml:81-88`, all six skipped
on every one of those runs, and the summary said nothing about it.

The hook these tests pin — `pytest_terminal_summary` in `tests/conftest.py` —
makes the absence legible. At the end of every run it names each registered
`live_*` marker, says whether tests carrying it actually executed, and for the
ones that did not, names the condition that would have run them. Both strings
come out of the marker's own registration string, parsed at the
`<name>: <description>` boundary, so there is exactly one place either is
written and no second list to drift (plan T3's failure mode, applied to markers).

It is a describer and never a gate (FR-009, plan T6). A summary hook that failed
a run for lacking production credentials would turn every developer's
`uv run pytest -q` red, and the first response would be to delete it — so
`test_the_hook_changes_no_exit_status` runs each scratch session twice, once
with the hook loaded and once without, and holds the two exit statuses equal.

How these tests observe the hook
--------------------------------

A terminal summary is only observable from a finished session, so each test runs
a real one: a scratch directory under `tmp_path` holding one throwaway test
module and a `conftest.py` whose entire body imports the hook by name from
`tests.conftest`. The session is invoked with `-c <repo>/pyproject.toml`, so
`config.getini("markers")` is the live registration list this story is about,
and with a stripped environment, so "no live environment" is a fact about the
run rather than a hope about the host.

`test_the_hook_is_wired_into_the_repositorys_own_suite` closes the last gap: an
importable hook function is not a loaded one, so that test runs a real, cheap
repo test file under the real `tests/conftest.py` and reads the report out of
its output.

Verification evidence (constitution VIII; US3-S1, US3-S2, SC-003)
------------------------------------------------------------------

**A run with no live environment** — the repository's own suite, one file, under
the real `tests/conftest.py`, on this branch:

.. code-block:: text

    $ uv run pytest tests/test_criteria.py -q
    ...............................                                    [100%]
    ================================ live tiers ================================
    live_capacity   did not run — runs when a server answers at TEMPORAL_ADDRESS/TEMPORAL_NAMESPACE
    live_epic       did not run — runs when Tier 1 env is set
    live_merge      did not run — runs when FACTORY_SAMPLE_REPO is set and gh is authenticated
    live_onramp     did not run — runs when every prerequisite in docs/onramp-exercise.md is present
    live_proxy      did not run — runs when LITELLM_PROXY_URL and LITELLM_MASTER_KEY are set
    live_telegram   did not run — runs when TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set
    31 passed in 0.59s

**A run in which a live tier did execute** — a scratch session carrying one
`live_epic`-marked test that is allowed to run:

.. code-block:: text

    $ python -m pytest -c <repo>/pyproject.toml <tmp>/test_scratch.py -q
    ..                                                                 [100%]
    ================================ live tiers ================================
    live_capacity   did not run — runs when a server answers at TEMPORAL_ADDRESS/TEMPORAL_NAMESPACE
    live_epic       ran (1 test)
    live_merge      did not run — runs when FACTORY_SAMPLE_REPO is set and gh is authenticated
    live_onramp     did not run — runs when every prerequisite in docs/onramp-exercise.md is present
    live_proxy      did not run — runs when LITELLM_PROXY_URL and LITELLM_MASTER_KEY are set
    live_telegram   did not run — runs when TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set
    2 passed in 0.00s

The two cases are distinguishable, which is the whole of US3-S2: a report that
can only announce absence cannot tell a reader whether the tier ran.

**Full suite, before and after** — the seven new tests here, and nothing else
moved:

.. code-block:: text

    $ uv run pytest -q      # tree restored to 0190ab0, before this story
    5102 passed, 57 skipped, 7 warnings in 337.48s (0:05:37)

    $ uv run pytest -q      # this branch
    5109 passed, 57 skipped, 6 warnings in 334.96s (0:05:34)
    ================================ live tiers ================================
    live_capacity   did not run — runs when a server answers at TEMPORAL_ADDRESS/TEMPORAL_NAMESPACE
    live_epic       did not run — runs when Tier 1 env is set
    live_merge      did not run — runs when FACTORY_SAMPLE_REPO is set and gh is authenticated
    live_onramp     did not run — runs when every prerequisite in docs/onramp-exercise.md is present
    live_proxy      did not run — runs when LITELLM_PROXY_URL and LITELLM_MASTER_KEY are set
    live_telegram   did not run — runs when TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set

(+7 passed is exactly the seven tests below; the skip count is unchanged, and
the warning tally is run-to-run noise, as `tests/test_114_us1_smoke_onboards.py`
recorded for the same reason. What changed is the six lines under the count:
before them, a reader of that run had no way to tell that all six live tiers
had sat out.)

The skip count is unchanged: this story adds no test that can skip, and removes
none that does. Nothing here reads an environment variable to decide whether to
run (plan T4) — the report is what the suite says about the environment, not
something the environment decides.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from tests.conftest import LIVE_TIER_REPORT_TITLE

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"

#: The registration phrase every live marker uses to name its own precondition.
#: Read here only to *derive the expectation* from `pyproject.toml`; the hook
#: parses the registration itself, and neither side reads the other's answer.
AUTO_SKIP_PHRASE = "auto-skips unless "

#: A scratch session must not inherit whatever the operator happens to export.
#: Any variable whose name mentions one of these is dropped, which covers the
#: credentials the registered tiers name by name; the scratch modules carry no
#: skip guard of their own, so the report's answer never depends on the host.
LIVE_ENV_FRAGMENTS = ("LITELLM", "TELEGRAM", "TEMPORAL", "SAMPLE_REPO", "GH_TOKEN")

#: The whole of a scratch session's conftest. Importing the hook by name is all
#: pytest needs to register it, and it leaves the rest of `tests/conftest.py`
#: — the autouse store isolation, the fake proxy, the host-launch substitution —
#: out of the scratch run.
SCRATCH_CONFTEST = """\
from tests.conftest import pytest_terminal_summary  # noqa: F401
"""

#: The control: the same scratch session with no hook at all. What its output
#: lacks, and what its exit status equals, is how the hook's effect is measured.
CONTROL_CONFTEST = "# no hook: the control for the no-verdict proof\n"


def registered_live_tiers() -> dict[str, str]:
    """`{marker name: the condition that would run it}`, read from `pyproject.toml`.

    Derived from the registration string rather than restated (FR-008): the
    name is what precedes the first colon and the condition is what follows
    `auto-skips unless`, so a marker whose precondition is reworded moves this
    expectation with it.
    """
    ini = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    registrations = ini["tool"]["pytest"]["ini_options"]["markers"]

    tiers: dict[str, str] = {}
    for registration in registrations:
        name, _, description = registration.partition(":")
        name = name.strip()
        if not name.startswith("live_"):
            continue
        _, phrase, condition = description.partition(AUTO_SKIP_PHRASE)
        assert phrase, (
            f"marker {name!r} is registered without {AUTO_SKIP_PHRASE!r}, so no "
            "condition can be drawn from its own registration: "
            f"{registration!r}"
        )
        tiers[name] = condition.strip()
    assert tiers, f"no live_* markers registered in {PYPROJECT}"
    return tiers


def scratch_session(
    tmp_path: Path,
    body: str,
    *,
    conftest: str = SCRATCH_CONFTEST,
) -> subprocess.CompletedProcess[str]:
    """Run one throwaway pytest session and return its completed process.

    The session uses the repository's own `pyproject.toml` as its config file,
    so the markers the hook reports on are the registered ones, and an
    environment with every live credential stripped out, so a tier that does not
    run in it did not run for lack of the thing its registration names.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "conftest.py").write_text(conftest, encoding="utf-8")
    (tmp_path / "test_scratch.py").write_text(body, encoding="utf-8")

    env = {
        name: value
        for name, value in os.environ.items()
        if not any(fragment in name for fragment in LIVE_ENV_FRAGMENTS)
    }
    env["PYTHONPATH"] = str(REPO_ROOT)

    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-c",
            str(PYPROJECT),
            str(tmp_path / "test_scratch.py"),
            "-q",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )


def tier_lines(output: str) -> dict[str, str]:
    """The report's per-tier lines, keyed by the marker each one names.

    Keyed by first token rather than by position: the assertion is that the
    report *names* a tier, not that it names it third.
    """
    lines: dict[str, str] = {}
    for raw in output.splitlines():
        line = raw.strip()
        head = line.split(" ", 1)[0]
        if head.startswith("live_"):
            assert head not in lines, f"tier {head!r} reported twice:\n{output}"
            lines[head] = line
    return lines


GREEN_BODY = """\
def test_green():
    assert True
"""

RED_BODY = """\
def test_green():
    assert True


def test_red():
    assert False, "this session is meant to fail"
"""

LIVE_BODY = """\
import pytest


@pytest.mark.live_epic
def test_the_live_tier_executes():
    assert True


def test_offline():
    assert True
"""


# --- US3-S1: a tier that did not run says so, and says what would run it ------


def test_a_run_with_no_live_tier_names_every_tier_and_its_condition(
    tmp_path: Path,
) -> None:
    """FR-008: every registered live marker, with the condition from its own line."""
    result = scratch_session(tmp_path, GREEN_BODY)
    output = result.stdout + result.stderr

    assert LIVE_TIER_REPORT_TITLE in output, output
    reported = tier_lines(output)
    expected = registered_live_tiers()

    assert set(reported) == set(expected), (
        "the report and pyproject.toml disagree about which live tiers exist; "
        f"reported {sorted(reported)}, registered {sorted(expected)}\n{output}"
    )
    for name, condition in expected.items():
        line = reported[name]
        assert "did not run" in line, (
            f"{name} did not run in this session but the report does not say so: "
            f"{line!r}\n{output}"
        )
        assert condition in line, (
            f"{name}'s line does not name the condition its registration "
            f"declares ({condition!r}): {line!r}\n{output}"
        )


# --- US3-S2: a tier that did run is reported as having run --------------------


def test_a_tier_that_executed_is_reported_as_having_run(tmp_path: Path) -> None:
    """FR-008: the report distinguishes the two cases, rather than only absence."""
    result = scratch_session(tmp_path, LIVE_BODY)
    output = result.stdout + result.stderr

    assert result.returncode == 0, output
    reported = tier_lines(output)

    ran = reported["live_epic"]
    assert "ran" in ran and "did not run" not in ran, (
        f"live_epic executed in this session; the report says {ran!r}\n{output}"
    )
    assert "1 test" in ran, (
        f"the report should say how much of the tier ran: {ran!r}\n{output}"
    )

    for name, line in reported.items():
        if name == "live_epic":
            continue
        assert "did not run" in line, (
            f"{name} carried no test in this session: {line!r}\n{output}"
        )


# --- US3-S3: it is emitted on every run, not only on a red one ----------------


@pytest.mark.parametrize(
    ("body", "expected_status"),
    [(GREEN_BODY, 0), (RED_BODY, 1)],
    ids=["green", "red"],
)
def test_the_report_is_emitted_on_every_run(
    tmp_path: Path, body: str, expected_status: int
) -> None:
    """FR-009: a notice that appears only on failure is one nobody reads."""
    result = scratch_session(tmp_path, body)
    output = result.stdout + result.stderr

    assert result.returncode == expected_status, output
    assert LIVE_TIER_REPORT_TITLE in output, output
    assert set(tier_lines(output)) == set(registered_live_tiers()), output


# --- US3-S4: it describes, and never decides ----------------------------------


@pytest.mark.parametrize(
    ("body", "expected_status"),
    [(GREEN_BODY, 0), (RED_BODY, 1)],
    ids=["green", "red"],
)
def test_the_hook_changes_no_exit_status(
    tmp_path: Path, body: str, expected_status: int
) -> None:
    """FR-009, plan T6: the same session exits the same way with and without it.

    Asserting `returncode == 0` alone would pass against a hook that turned a
    red run green, so both directions are held against a control session that
    loads no hook at all.
    """
    with_hook = scratch_session(tmp_path / "with-hook", body)
    without_hook = scratch_session(
        tmp_path / "control", body, conftest=CONTROL_CONFTEST
    )

    assert with_hook.returncode == without_hook.returncode == expected_status, (
        "the hook moved the exit status: "
        f"{without_hook.returncode} without it, {with_hook.returncode} with it\n"
        f"--- with hook ---\n{with_hook.stdout}{with_hook.stderr}\n"
        f"--- control ---\n{without_hook.stdout}{without_hook.stderr}"
    )
    assert LIVE_TIER_REPORT_TITLE in with_hook.stdout + with_hook.stderr
    assert LIVE_TIER_REPORT_TITLE not in without_hook.stdout + without_hook.stderr, (
        "the control session emitted the report without loading the hook, so "
        "these tests are measuring something other than the hook"
    )


# --- the hook is loaded by the repository's own suite, not merely importable ---


def test_the_hook_is_wired_into_the_repositorys_own_suite() -> None:
    """A hook that only a scratch conftest imports protects nobody.

    Runs one real, cheap repo test file under the real `tests/conftest.py` and
    reads the report out of its output. `tests/test_criteria.py` carries no live
    marker and takes a fifth of a second, so this costs the suite almost
    nothing and proves the wiring end to end.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "tests/test_criteria.py",
            "-q",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr

    assert result.returncode == 0, output
    assert LIVE_TIER_REPORT_TITLE in output, output
    assert set(tier_lines(output)) == set(registered_live_tiers()), output
