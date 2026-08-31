"""US2: a repository declares the caches its gates need.

`HOME` inside the gate boundary is a tmpfs, so a package manager finds an empty
cache and re-downloads everything a gate touches — or fails where the host would
have passed. The factory already knew that for exactly one package manager:
`_cache_binds` bound `~/.cache/uv` and set `UV_CACHE_DIR` beside it, and its
docstring argues the general case in full. This file holds the generalisation to
the three properties that docstring argues for, one test each:

- **writable** — a read-only cache is worse than none, because the manager reads
  it as a corrupt one;
- **conditional on existence** — a missing cache is not a broken configuration,
  so the gate runs anyway;
- **paired with its variable** — binding a cache the tool cannot find is the
  failure `UV_CACHE_DIR` exists to prevent.

Two more the generalisation itself introduces:

- **the default is not removed** (FR-006). Every manifest that exists declares no
  caches, so the control is parametrised over this repository's committed
  manifest corpus rather than over an invented one: whatever those files say, the
  uv bind they get is byte-identical to the one they got before this key existed.
- **the blast radius is bounded** (FR-007). A declared bind is a hole in a
  verification boundary and the manifest that declares it is written by whoever
  controls the target repository, so a path outside the operator's home is
  refused at load time — after symlinks are resolved, because a link inside home
  pointing out of it is the obvious bypass.

Assertions read the *assembled* argv by scanning for flag/source/destination
triples rather than by position, so they say what the boundary mounts and not
where in the command line it happens to say so.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from factory.verify import gates as gates_module
from factory.verify.factory_yaml import FactoryConfigError, load_factory_config, parse_factory_config
from factory.verify.gates import BwrapGateExecutor, GateInvocation, resolve_gate_executor
from factory.verify.models import CacheDeclaration
from tests.test_toolchain_discovery import PlantedHost

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Every manifest this repository commits. FR-006's control runs over all of
#: them: "a manifest declaring no caches" is not a hypothetical shape to invent,
#: it is every manifest that exists, and a regression here would be one the whole
#: fleet pays for.
MANIFEST_CORPUS = (
    "ergane.yaml",
    "factory.yaml",
    "tests/fixtures/target_repo/ergane.yaml",
)


@pytest.fixture
def host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PlantedHost:
    """A toolchain and an operator home of this test's own.

    `activate` points `HOME` at `host.home`, which is what makes "under the
    operator's home" a fact this test controls instead of a fact about the
    machine the suite happens to run on.
    """
    planted = PlantedHost(tmp_path)
    for name in ("uv", "node", "git", "claude"):
        planted.plant(name)
    planted.activate(monkeypatch)
    return planted


def _manifest(body: str = "") -> str:
    """A minimal valid manifest, plus whatever the test is actually about."""
    return 'version: 2\nruntime: bwrap\ngates:\n  test: "true"\n' + body


def _caches_block(*entries: str) -> str:
    return "caches:\n" + "".join(entries)


def _entry(path: Path | str, env: str | None = None) -> str:
    text = f"  - path: {path}\n"
    if env is not None:
        text += f"    env: {env}\n"
    return text


def _invocation(host: PlantedHost) -> GateInvocation:
    return GateInvocation(
        name="test", command="true", cwd=host.worktree, timeout_s=30, env={}
    )


def _bound(argv: list[str], flag: str) -> list[tuple[str, str]]:
    """Every `(source, destination)` the argv mounts with `flag`."""
    return [
        (argv[index + 1], argv[index + 2])
        for index, token in enumerate(argv[:-2])
        if token == flag
    ]


def _setenv(argv: list[str]) -> dict[str, str]:
    """Every variable the argv sets inside the boundary."""
    return {
        argv[index + 1]: argv[index + 2]
        for index, token in enumerate(argv[:-2])
        if token == "--setenv"
    }


def _plant(home: Path, *relative: str) -> Path:
    path = home.joinpath(*relative)
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


# US2-S1 / T006 — a declared path is bound, and bound writable ----------------


def test_a_declared_cache_path_is_bound_into_the_boundary(host: PlantedHost) -> None:
    """US2-S1: the path the manifest names crosses, at the same absolute path."""
    npm = _plant(host.home, ".npm")
    config = parse_factory_config(_manifest(_caches_block(_entry(npm))))

    argv = BwrapGateExecutor(caches=config.caches)._build_argv(_invocation(host))

    assert (str(npm), str(npm)) in _bound(argv, "--bind")


# FR-004 / T011 — every declared bind is writable ------------------------------


def test_every_declared_cache_bind_is_writable(host: PlantedHost) -> None:
    """A read-only cache is worse than none: the manager treats it as corrupt.

    Asserted two ways, because "writable" is only half a claim on a command line
    that has both flags: the path appears under `--bind`, and no `--ro-bind`
    anywhere in the argv names it as a destination.
    """
    npm = _plant(host.home, ".npm")
    browsers = _plant(host.home, ".cache", "ms-playwright")
    config = parse_factory_config(
        _manifest(_caches_block(_entry(npm), _entry(browsers)))
    )

    argv = BwrapGateExecutor(caches=config.caches)._build_argv(_invocation(host))

    writable = _bound(argv, "--bind")
    readonly = _bound(argv, "--ro-bind")
    for cache in (npm, browsers):
        assert (str(cache), str(cache)) in writable
        assert all(destination != str(cache) for _, destination in readonly)


# US2-S2 / T007 — an absent cache does not fail the gate, and is reported ------


def test_a_declared_cache_absent_from_the_host_does_not_fail_the_gate(
    host: PlantedHost, caplog: pytest.LogCaptureFixture
) -> None:
    """US2-S2: a missing cache is not a broken configuration.

    The uv bind has behaved this way since it was written and the reason is
    unchanged — a host that has never run this gate has no cache to bind, and
    refusing there would turn a cold host into a failing one. What is new is the
    reporting: uv's absence is a fact about one hardcoded path, while a declared
    one is a fact about something the operator asked for, so it is said out loud.
    """
    missing = host.home / ".npm"
    config = parse_factory_config(
        _manifest(_caches_block(_entry(missing, "npm_config_cache")))
    )

    with caplog.at_level(logging.WARNING, logger="factory.verify.gates"):
        argv = BwrapGateExecutor(caches=config.caches)._build_argv(_invocation(host))

    # The gate still runs: the argv ends in the command it was given.
    assert argv[-4:] == ["--", "bash", "-c", "true"]
    # Nothing was bound, and nothing points at a directory that is not there.
    resolved = str(missing.resolve())
    assert all(destination != resolved for _, destination in _bound(argv, "--bind"))
    assert "npm_config_cache" not in _setenv(argv)
    # And the absence is reported, naming the path the operator declared.
    assert resolved in caplog.text


# US2-S3 / T008 — the control: no caches declared means today, exactly ---------


@pytest.mark.parametrize("relative", MANIFEST_CORPUS)
def test_a_manifest_declaring_no_caches_binds_the_uv_cache_exactly_as_today(
    relative: str, host: PlantedHost
) -> None:
    """US2-S3, FR-006: the Python default is not removed by making caches declarable.

    The comparison is against an executor constructed the way every caller
    constructed one before this key existed — `BwrapGateExecutor()`, no caches
    argument at all — so the claim is identity with today's behaviour rather
    than agreement with a reimplementation of it.
    """
    config = load_factory_config(REPO_ROOT / relative)
    assert config.caches == ()

    # Unresolved on purpose: this is the path today's `_cache_binds` composes.
    uv_cache = host.home / ".cache" / "uv"
    uv_cache.mkdir(parents=True, exist_ok=True)

    declared = BwrapGateExecutor(caches=config.caches)
    assert declared._cache_binds() == BwrapGateExecutor()._cache_binds()

    argv = declared._build_argv(_invocation(host))
    assert (str(uv_cache), str(uv_cache)) in _bound(argv, "--bind")
    assert _setenv(argv)["UV_CACHE_DIR"] == str(uv_cache)


def test_a_declared_cache_does_not_move_uv_cache_dir(host: PlantedHost) -> None:
    """FR-006 again, at the seam FR-008 rewrites.

    Before this story the variable loop was `for _, dest in cache_binds:
    setenv UV_CACHE_DIR dest`, correct only while the list could hold exactly
    one entry. A second entry under that loop would have pointed uv at the npm
    cache — the uv bind still present, still writable, and uv looking straight
    past it.
    """
    uv_cache = host.home / ".cache" / "uv"
    uv_cache.mkdir(parents=True, exist_ok=True)
    npm = _plant(host.home, ".npm")
    config = parse_factory_config(
        _manifest(_caches_block(_entry(npm, "npm_config_cache")))
    )

    environment = _setenv(
        BwrapGateExecutor(caches=config.caches)._build_argv(_invocation(host))
    )

    assert environment["UV_CACHE_DIR"] == str(uv_cache)
    assert environment["npm_config_cache"] == str(npm)


# US2-S4 / T009 — a declared bind is a hole, and it is bounded ----------------


def test_a_declared_cache_outside_the_operator_home_is_refused_naming_the_path(
    host: PlantedHost,
) -> None:
    """US2-S4, FR-007: refused at load time, and the message names the path."""
    with pytest.raises(FactoryConfigError) as raised:
        parse_factory_config(_manifest(_caches_block(_entry("/etc/ssl"))))

    assert raised.value.rule == "caches_outside_home"
    message = str(raised.value)
    assert "/etc/ssl" in message
    assert str(host.home.resolve()) in message


def test_a_symlink_inside_home_resolving_outside_it_is_refused(
    host: PlantedHost, tmp_path: Path
) -> None:
    """US2-S4, trap 3: the obvious bypass, closed by resolving before deciding.

    A path check that stopped at the declared spelling would accept this — it
    is spelled inside home — and then mount a directory that is not, which is
    precisely the hole FR-007 exists to bound.
    """
    outside = tmp_path / "outside" / "npm"
    outside.mkdir(parents=True)
    link = host.home / ".npm"
    link.symlink_to(outside)

    with pytest.raises(FactoryConfigError) as raised:
        parse_factory_config(_manifest(_caches_block(_entry(link))))

    assert raised.value.rule == "caches_outside_home"
    message = str(raised.value)
    assert str(link) in message
    assert str(outside.resolve()) in message


def test_the_operator_home_itself_is_not_a_declarable_cache(host: PlantedHost) -> None:
    """Under home, not home: binding the whole home writable is the hole itself."""
    with pytest.raises(FactoryConfigError) as raised:
        parse_factory_config(_manifest(_caches_block(_entry(host.home))))

    assert raised.value.rule == "caches_outside_home"


def test_a_relative_cache_path_is_refused(host: PlantedHost) -> None:
    """A path resolved against whatever directory the process sits in is ambient.

    Constitution IX: the declaration owns the value, so the manifest names the
    directory outright (or spells it `~/...`) instead of leaving the answer to
    the caller's working directory.
    """
    with pytest.raises(FactoryConfigError) as raised:
        parse_factory_config(_manifest(_caches_block(_entry(".npm"))))

    assert raised.value.rule == "caches"
    assert ".npm" in str(raised.value)


def test_a_tilde_relative_cache_path_is_accepted(host: PlantedHost) -> None:
    """`~/.npm` is how an operator writes it, and it is under home by definition."""
    npm = _plant(host.home, ".npm")

    config = parse_factory_config(_manifest(_caches_block(_entry("~/.npm"))))

    assert config.caches == (CacheDeclaration(path=str(npm), env=None),)


# US2-S5 / T010 — the variable is set beside the bind -------------------------


def test_an_environment_variable_named_by_a_declaration_is_set_beside_its_bind(
    host: PlantedHost,
) -> None:
    """US2-S5, FR-008: binding a cache the tool cannot find is the uv failure again."""
    browsers = _plant(host.home, ".cache", "ms-playwright")
    config = parse_factory_config(
        _manifest(_caches_block(_entry(browsers, "PLAYWRIGHT_BROWSERS_PATH")))
    )

    argv = BwrapGateExecutor(caches=config.caches)._build_argv(_invocation(host))

    assert (str(browsers), str(browsers)) in _bound(argv, "--bind")
    assert _setenv(argv)["PLAYWRIGHT_BROWSERS_PATH"] == str(browsers)


def test_a_declaration_naming_no_variable_sets_none(host: PlantedHost) -> None:
    """`env:` is optional: a tool that finds its own cache needs no telling."""
    npm = _plant(host.home, ".npm")
    config = parse_factory_config(_manifest(_caches_block(_entry(npm))))
    baseline = _setenv(BwrapGateExecutor()._build_argv(_invocation(host)))

    environment = _setenv(
        BwrapGateExecutor(caches=config.caches)._build_argv(_invocation(host))
    )

    assert environment == baseline


# The seam: what the runner actually hands the boundary ------------------------


def test_the_boundary_the_runner_resolves_carries_the_manifest_s_caches(
    host: PlantedHost, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A declaration the gate runner never reads is a comment.

    `resolve_gate_executor` is the one seam that turns a manifest into the
    backend a gate runs in — the verify activity and `run_gates` both go through
    it — so this is where a `caches:` key stops being schema and starts being a
    mount.
    """
    npm = _plant(host.home, ".npm")
    (host.worktree / "ergane.yaml").write_text(
        _manifest(_caches_block(_entry(npm, "npm_config_cache"))), encoding="utf-8"
    )
    monkeypatch.setattr(
        gates_module, "BWRAP_BACKEND_BINARY", host.plant("bwrap")
    )

    executor = resolve_gate_executor(host.worktree)

    assert isinstance(executor, BwrapGateExecutor)
    assert executor.caches == (
        CacheDeclaration(path=str(npm), env="npm_config_cache"),
    )


# T012 — the shape the schema accepts, and the near-misses it refuses ---------


@pytest.mark.parametrize(
    "body",
    [
        pytest.param("caches: {}\n", id="a-mapping-not-a-list"),
        pytest.param("caches: []\n", id="declared-empty"),
        pytest.param("caches:\n  - ~/.npm\n", id="a-bare-string-entry"),
        pytest.param("caches:\n  - env: NPM\n", id="no-path"),
        pytest.param("caches:\n  - path: ~/.npm\n    dest: /x\n", id="unknown-key"),
        pytest.param("caches:\n  - path: ~/.npm\n    env: ''\n", id="blank-variable"),
        pytest.param("caches:\n  - path: ~/.npm\n    env: 'npm cache'\n", id="unusable-variable"),
    ],
)
def test_a_near_miss_cache_declaration_is_refused(body: str, host: PlantedHost) -> None:
    """Declared means declared, the rule every optional key in this schema follows."""
    _plant(host.home, ".npm")

    with pytest.raises(FactoryConfigError) as raised:
        parse_factory_config(_manifest(body))

    assert raised.value.rule == "caches"
