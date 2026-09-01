"""US3 of epic 125: the operator can see the remaining credential runway.

The surface answers three states:

1. Long-lived token configured: source is the token, no file expiry is reported.
2. Only a copied credential: source is the copied credential and remaining
   validity is shown.
3. Neither: the answer says so and names both remedies.

In every state the rendered output must contain no credential value (trap 4).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from factory.workgraph.adapter import (
    CLAUDE_CODE_OAUTH_TOKEN,
    CREDENTIAL_SOURCE_COPIED_CREDENTIALS,
    CREDENTIAL_SOURCE_OAUTH_TOKEN,
    discover_subscription_credential,
)
from factory.workgraph.credential_status import (
    CredentialStatus,
    _credential_runway,
    credential_status,
    render_credential_status,
)

#: A synthetic long-lived subscription token. Real tokens share the `sk-ant-oat01-`
#: prefix but this value is generated for tests and never valid anywhere.
OAUTH_TOKEN = "sk-ant-oat01-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _fake_operator_home(tmp_path: Path) -> Path:
    """A writable stand-in for the operator's real home directory."""
    home = tmp_path / "operator-home"
    home.mkdir(parents=True)
    return home


def _credential_with_expiry(expires_at: str) -> dict:
    """A synthetic copied credential with the given ISO `expiresAt`."""
    return {
        "accessToken": "fake-access-token",
        "refreshToken": "fake-refresh-token",
        "expiresAt": expires_at,
        "refreshTokenExpiresAt": (datetime.now(timezone.utc) + timedelta(days=28)).isoformat(),
        "scopes": ["claude_code"],
        "subscriptionType": "pro",
        "rateLimitTier": "default",
    }


def _write_credential(path: Path, content: dict | str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, dict):
        path.write_text(json.dumps(content, indent=2), encoding="utf-8")
    else:
        path.write_text(content, encoding="utf-8")
    path.chmod(0o600)
    return path


# --- T023 [P] [US3-S1] token configured: source is token, no expiry ----------------


def test_token_status_names_token_and_skips_file_expiry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When a long-lived token is configured, the status answer names the token as
    the source and does NOT report a misleading eight-hour expiry read from an
    unused credential file."""
    operator_home = _fake_operator_home(tmp_path)
    expired = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    _write_credential(
        operator_home / ".claude" / ".credentials.json",
        _credential_with_expiry(expired),
    )
    monkeypatch.setenv(CLAUDE_CODE_OAUTH_TOKEN, OAUTH_TOKEN)

    status = credential_status(operator_home=operator_home)

    assert status.source == CREDENTIAL_SOURCE_OAUTH_TOKEN
    assert status.expires_at is None
    rendered = render_credential_status(status)
    assert "long-lived token" in rendered.lower() or "oauth token" in rendered.lower()
    assert "expired" not in rendered.lower() or "expires" not in rendered.lower()


# --- T024 [P] [US3-S2] copied credential only: source and remaining validity -------


def test_copied_credential_status_names_source_and_remaining_validity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When only a copied credential is present, the answer names that source and
    reports the remaining validity."""
    operator_home = _fake_operator_home(tmp_path)
    future = (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat()
    _write_credential(
        operator_home / ".claude" / ".credentials.json",
        _credential_with_expiry(future),
    )
    monkeypatch.delenv(CLAUDE_CODE_OAUTH_TOKEN, raising=False)

    status = credential_status(operator_home=operator_home)

    assert status.source == CREDENTIAL_SOURCE_COPIED_CREDENTIALS
    assert status.expires_at == datetime.fromisoformat(future)
    rendered = render_credential_status(status)
    assert "copied" in rendered.lower() or "interactive" in rendered.lower()
    assert "remaining" in rendered.lower() or "expires" in rendered.lower() or "valid" in rendered.lower()


# --- T025 [P] [US3-S3] neither: says so and names both remedies --------------------


def test_missing_credential_status_names_both_remedies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When neither credential is present, the answer says so and names both
    remedies — interactive login and long-lived token."""
    operator_home = _fake_operator_home(tmp_path)
    monkeypatch.delenv(CLAUDE_CODE_OAUTH_TOKEN, raising=False)

    status = credential_status(operator_home=operator_home)

    assert status.source is None
    assert status.expires_at is None
    rendered = render_credential_status(status)
    lower = rendered.lower()
    assert "none found" in lower or "no credential" in lower or "not found" in lower or "missing" in lower
    assert "claude auth login" in lower or "login" in lower
    assert CLAUDE_CODE_OAUTH_TOKEN in rendered or "long-lived" in lower


# --- T026 [P] [US3-S4, trap 4] no credential value in rendered output ------------


@pytest.mark.parametrize(
    "name,monkeypatch_env,credential_expiry",
    [
        ("token_only", {CLAUDE_CODE_OAUTH_TOKEN: OAUTH_TOKEN}, None),
        ("copied_only", {}, "2099-08-20T12:00:00.000Z"),
        ("neither", {}, None),
    ],
)
def test_rendered_output_contains_no_credential_value(
    name: str,
    monkeypatch_env: dict[str, str],
    credential_expiry: str | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A status surface that prints a token is a worse defect than the one this
    spec closes. The rendered output must contain no credential value in any of
    the three states."""
    operator_home = _fake_operator_home(tmp_path)
    if credential_expiry is not None:
        _write_credential(
            operator_home / ".claude" / ".credentials.json",
            _credential_with_expiry(credential_expiry),
        )
    monkeypatch.delenv(CLAUDE_CODE_OAUTH_TOKEN, raising=False)
    for key, value in monkeypatch_env.items():
        monkeypatch.setenv(key, value)

    status = credential_status(operator_home=operator_home)
    rendered = render_credential_status(status)

    # No token prefix, no access/refresh token values, no synthetic token.
    assert "sk-ant-" not in rendered
    assert "fake-access-token" not in rendered
    assert "fake-refresh-token" not in rendered
    if credential_expiry is not None:
        # The expiry timestamp itself is fine to show (it is not a credential
        # value), but the access/refresh values must still be absent.
        assert "fake-access" not in rendered
        assert "fake-refresh" not in rendered


# --- Helper-shape tests: precedence and unknown-expiry handling ------------------


def test_runway_helper_prefers_token_when_both_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The status surface must read the precedence US2 established: token wins."""
    operator_home = _fake_operator_home(tmp_path)
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    _write_credential(
        operator_home / ".claude" / ".credentials.json",
        _credential_with_expiry(future),
    )
    monkeypatch.setenv(CLAUDE_CODE_OAUTH_TOKEN, OAUTH_TOKEN)

    status = _credential_runway(
        operator_home=operator_home,
        environ={CLAUDE_CODE_OAUTH_TOKEN: OAUTH_TOKEN},
    )

    assert status.source == CREDENTIAL_SOURCE_OAUTH_TOKEN


def test_runway_helper_ignores_unparseable_expiry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unreadable expiry is not evidence of a dead credential; status reports
    it as unknown rather than refusing."""
    operator_home = _fake_operator_home(tmp_path)
    _write_credential(operator_home / ".claude" / ".credentials.json", "not json")
    monkeypatch.delenv(CLAUDE_CODE_OAUTH_TOKEN, raising=False)

    status = _credential_runway(operator_home=operator_home)

    assert status.source == CREDENTIAL_SOURCE_COPIED_CREDENTIALS
    assert status.expires_at is None
