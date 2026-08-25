"""105-US3: the engine/CLI version handshake (T019).

The refusal sentence is the single source of truth; three surfaces emit it, and
none may paraphrase.
"""

from __future__ import annotations

import pytest

from factory.registry import resolve_state_home
from factory.supervision import engine_identity as identity_module
from factory.supervision.engine_identity import (
    EngineIdentity,
    engine_skew,
    identity_path,
    image_reference,
)


def test_engine_skew_mismatch_names_both_versions_and_remedies_and_path(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T019 / US3-S1 / FR-012 / FR-022: mismatch returns one refusal sentence."""
    state_home = tmp_path / "state"
    monkeypatch.setenv("ERGANE_STATE_HOME", str(state_home))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("FACTORY_STATE_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)

    identity = EngineIdentity(
        version="0.3.0",
        started_at="2026-08-25T12:00:00+00:00",
        image_reference="ghcr.io/bryantharpeorg/ergane:0.3.0",
        image_digest=None,
    )

    monkeypatch.setattr(identity_module, "cli_version", lambda: "0.4.0")

    sentence = engine_skew(identity)
    assert sentence is not None
    assert "engine is running ergane 0.3.0" in sentence
    assert "this CLI is 0.4.0" in sentence
    assert "ergane engine upgrade" in sentence
    assert "docker pull ghcr.io/bryantharpeorg/ergane:0.4.0" in sentence
    expected_path = identity_path(state_home)
    assert str(expected_path) in sentence
    assert expected_path.is_absolute()
    assert "~" not in sentence


def test_engine_skew_matching_version_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T019 / US3-S2: matching versions produce no sentence."""
    identity = EngineIdentity(
        version="0.4.0",
        started_at="2026-08-25T12:00:00+00:00",
        image_reference="ghcr.io/bryantharpeorg/ergane:0.4.0",
        image_digest=None,
    )
    monkeypatch.setattr(identity_module, "cli_version", lambda: "0.4.0")
    assert engine_skew(identity) is None


def test_engine_skew_absent_identity_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T019 / US3-S3: no identity file means no refusal, native path untouched."""
    monkeypatch.setattr(identity_module, "cli_version", lambda: "0.4.0")
    assert engine_skew(None) is None


def test_image_reference_uses_repository_constant() -> None:
    """The pinned image reference in the remedy names the repository CI pushes to."""
    assert image_reference("0.4.0") == "ghcr.io/bryantharpeorg/ergane:0.4.0"
