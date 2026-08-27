"""The container starts a notifier bridge only when it can be configured.

`factory/notify/service.py` raises SystemExit on an unset TELEGRAM_BOT_TOKEN.
That is right for the systemd deployment — a notifier unit deployed without a
token should fail loudly — and fatal inside the container, where the supervisor
treats a supervised child dying unprompted as a fault and stops everything.

`container/compose.demo.yaml` sets `TELEGRAM_BOT_TOKEN=` empty on purpose, so
the demo shipped a configuration that killed itself. Three files, each defensible
alone. Observed 2026-08-26 on a cold boot:

    ergane-1 | ergane demo: step 1/5 ergane install --from-file ...
    ergane-1 | INFO:__main__:worker polling 'workgraph' ... with 46 activities
    ergane-1 | TELEGRAM_BOT_TOKEN is not set; the bridge cannot poll Telegram
    ergane-1 | child bridge exited first with status 1; stopping container

Not starting it is the honest option: an idle process that polls nothing would
satisfy the supervisor by pretending to be a notifier.
"""

from __future__ import annotations

import pytest

from factory.notify import service as notify_service
from factory.supervision import container_supervisor


def test_the_supervisor_and_the_bridge_name_the_same_credential() -> None:
    """The supervisor spells the variable rather than importing the module.

    Importing `factory.notify.service` to read one constant would pull in the
    Telegram client stack at a point where no child exists yet, so the name is
    duplicated on purpose — and duplicated names drift unless something checks.
    """
    assert container_supervisor.BRIDGE_TOKEN_ENV == notify_service.BOT_TOKEN_ENV


def test_a_token_in_the_config_configures_the_bridge() -> None:
    assert container_supervisor._bridge_is_configured({"telegram_bot_token": "123:abc"})


def test_a_token_in_the_environment_configures_the_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(container_supervisor.BRIDGE_TOKEN_ENV, "123:abc")
    assert container_supervisor._bridge_is_configured({})


def test_an_absent_token_leaves_the_bridge_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(container_supervisor.BRIDGE_TOKEN_ENV, raising=False)
    assert not container_supervisor._bridge_is_configured({})


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_the_demo_s_empty_token_leaves_the_bridge_unconfigured(
    blank: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`TELEGRAM_BOT_TOKEN=` in compose reaches os.environ as "", not None.

    This is the case that shipped. A truthiness check on `is None` would pass
    every other test in this file and still stop the container.
    """
    monkeypatch.setenv(container_supervisor.BRIDGE_TOKEN_ENV, blank)
    assert not container_supervisor._bridge_is_configured({})
    assert not container_supervisor._bridge_is_configured({"telegram_bot_token": blank})


def test_the_demo_compose_file_ships_the_empty_token_this_guards() -> None:
    """Pin the premise: if the demo ever sets a real token, this guard is moot."""
    from pathlib import Path

    compose = Path(__file__).resolve().parents[1] / "container" / "compose.demo.yaml"
    text = compose.read_text(encoding="utf-8")
    assert f"- {container_supervisor.BRIDGE_TOKEN_ENV}=\n" in text, (
        "compose.demo.yaml no longer ships an empty TELEGRAM_BOT_TOKEN; this test's "
        "premise has changed and the bridge-skip path may no longer be exercised"
    )
