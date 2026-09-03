"""057/US2: the constitution fits the repo it is written into.

These tests are written before the implementation that will satisfy them, so they
are expected to fail on a clean tree. They assert against the composed output
and against fixture repositories so the judge can verify them from the diff alone
(constitution VIII / D-037).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml

import factory.cli.init as init_module
import factory.stack_packs as stack_packs_module
from factory.cli.errors import EXIT_OK, OperatorError

from tests.test_057_us1_constitution_seeded import run_init
from tests.test_ergane_init import ScriptedPrompter, _invoke, make_bare_repo
from tests.test_ergane_init_check import bind_offline_seams, conforming_gh
from tests.fake_schedules import FakeScheduleServer


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> FakeScheduleServer:
    """Bind every outward seam; return the fake schedule server for inspection."""
    control_plane = FakeScheduleServer()
    bind_offline_seams(monkeypatch, conforming_gh(), schedules=control_plane)
    return control_plane


#: Minimal answers with a Python stack's default gate string.
#: Order follows `_TOP_LEVEL_KEYS`, then the US4 template-source question, then
#: the US2 detected-stack question, then the slug.
PYTHON_STACK_ANSWERS: list[str] = [
    "1",  # version
    "bwrap",  # runtime
    'test: "uv run pytest -q"',  # gates
    "",  # timeouts (empty -> omitted)
    "",  # standards (empty -> omitted, default will be used)
    "main",  # landing_branch
    "",  # roadmap (empty -> omitted)
    "",  # forge (empty -> omitted)
    "",  # writes (empty -> omitted)
    "",  # caches (empty -> omitted)
    "",  # diff_refusal_bytes (empty -> omitted)
    "",  # template source (empty -> shipped default)
    "",  # detected stack: accept default
    "myapp",  # slug
]


def test_python_fixture_produces_python_stack_layer_and_states_detection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline: FakeScheduleServer
) -> None:
    """US2-S1/FR-007/FR-008: a repo whose markers identify a pack gets that pack's
    stack layer, and the detected stack is stated to the operator before use."""
    repo = make_bare_repo(
        tmp_path,
        {
            "README.md": "# app\n",
            "pyproject.toml": "[project]\nname = 'app'\nversion = '0.1.0'\n",
        },
    )

    result = run_init(repo, monkeypatch, answers=list(PYTHON_STACK_ANSWERS), offline_server=offline)

    assert result.code == EXIT_OK, result.stderr
    assert "detected" in result.stdout.lower(), "init did not state the detected stack"
    assert "python" in result.stdout.lower(), "init did not name the Python stack"
    constitution = repo / ".specify" / "memory" / "constitution.md"
    assert constitution.exists()
    text = constitution.read_text(encoding="utf-8")
    assert "Python" in text or "pytest" in text or "uv" in text, (
        "Python stack layer not written into constitution"
    )


def test_operator_answer_overrides_detected_stack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline: FakeScheduleServer
) -> None:
    """US2-S2/FR-008: an operator answer in the interview overrides detection."""
    repo = make_bare_repo(
        tmp_path,
        {
            "README.md": "# app\n",
            "pyproject.toml": "[project]\nname = 'app'\nversion = '0.1.0'\n",
        },
    )

    # Provide an override answer when asked about the stack.
    # The prompt text is "detected stack"; any non-empty answer is the override.
    answers = [
        "1",  # version
        "bwrap",  # runtime
        'test: "uv run pytest -q"',  # gates
        "",  # timeouts
        "",  # standards
        "main",  # landing_branch
        "",  # roadmap
        "",  # forge
        "",  # writes
        "",  # caches
        "",  # diff_refusal_bytes
        "",  # template source (empty -> shipped default)
        "agnostic",  # detected stack: override with agnostic fallback
        "myapp",  # slug
    ]
    bind_offline_seams(monkeypatch, conforming_gh(), schedules=offline)
    prompter = ScriptedPrompter(answers)
    monkeypatch.setattr(init_module, "_prompter_factory", lambda: prompter)

    result = _invoke(["init", str(repo)], monkeypatch)

    assert result.code == EXIT_OK, result.stderr
    # The override path leaves evidence in the transcript.
    assert "using operator-chosen stack" in result.stdout.lower(), (
        "init did not report applying the operator's stack choice"
    )


def test_a_stack_name_no_pack_answers_to_is_refused_not_defaulted(
    tmp_path: Path,
) -> None:
    """FR-008, plan trap 11: a wrong answer is not an absent one.

    An empty answer means "take the proposal" and must keep meaning that. A
    name no pack answers to is a different thing entirely, and quietly treating
    it as an omission would write the detected stack's layer into a repository
    whose operator had just said they wanted a different one — the one case
    where they have stated in as many words that the proposal is wrong.
    """
    repo = make_bare_repo(
        tmp_path, {"pyproject.toml": "[project]\nname = 'app'\nversion = '0.1.0'\n"}
    )

    with pytest.raises(OperatorError) as refusal:
        init_module.select_stack_with_operator(repo, ScriptedPrompter(["rust"]))

    message = str(refusal.value)
    assert "rust" in message, f"the refusal does not name what was asked for: {message!r}"
    for pack in stack_packs_module.resolve_stack_packs():
        assert pack.name in message, (
            f"the refusal does not name {pack.name!r} as an available stack: {message!r}"
        )

    # And the empty answer still takes the proposal, unchanged.
    assert init_module.select_stack_with_operator(repo, ScriptedPrompter([""])).name == "python"


def test_unmatched_fixture_produces_language_agnostic_layer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline: FakeScheduleServer
) -> None:
    """US2-S3/FR-009: a repo matching no shipped pack gets the language-agnostic layer
    with a clear list of what the user must complete."""
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})

    # Unmatched repos do not ask the detected-stack question, so use the 13-entry
    # minimal answer list from the US1 test.
    from tests.test_057_us1_constitution_seeded import MINIMAL_ANSWERS as UNMATCHED_ANSWERS

    result = run_init(
        repo, monkeypatch, answers=list(UNMATCHED_ANSWERS), offline_server=offline
    )

    assert result.code == EXIT_OK, result.stderr
    constitution = repo / ".specify" / "memory" / "constitution.md"
    assert constitution.exists()
    text = constitution.read_text(encoding="utf-8")

    fallback = stack_packs_module.fallback_pack()
    assert fallback.render_layer().strip() in text, (
        "the fallback stack layer is not what was written into the document"
    )

    # FR-009 is not satisfied by the word "complete" appearing somewhere. What it
    # asks for is that the document name the parts the user has to finish, so
    # assert each of them is named — an empty `completion` list would otherwise
    # pass a substring check against the surrounding prose.
    assert fallback.completion, "the fallback pack names nothing to complete"
    for item in fallback.completion:
        assert item in text, f"the document does not name {item!r} as the user's to complete"

    # And no other pack's commands leaked in: an unmatched repository being
    # handed `uv run pytest -q` is the wrong-pack failure this story guards.
    for pack in stack_packs_module.resolve_stack_packs():
        if pack.fallback:
            continue
        for command in pack.commands.values():
            assert command not in text, (
                f"{pack.name!r} command {command!r} was written into a repository "
                "whose markers matched no stack"
            )


def test_shipped_packs_use_only_own_toolchain_commands() -> None:
    """US2-S4/SC-003: every shipped pack names only commands valid for its own
    toolchain, and no pack names a tool belonging to another pack.

    The check is `check_tool_hygiene`, which compares each pack's commands
    against the tool roster the pack itself declares. Reading the pack files is
    not evidence (plan trap 8), and neither is a check that cannot fail: the
    companion test below feeds it packs that violate every rule and asserts it
    catches each one.
    """
    packs = stack_packs_module.resolve_stack_packs()
    assert packs, "no stack packs resolved"

    violations = stack_packs_module.check_tool_hygiene(packs)

    assert violations == [], "shipped packs violate tool hygiene:\n" + "\n".join(violations)

    # A cross-pack check over one real pack proves nothing, so pin the fact the
    # check is being applied to more than the fallback: at least two shipped
    # packs declare tools, which is what makes disjointness a live constraint.
    with_tools = [p for p in packs if p.tools]
    assert len(with_tools) >= 2, (
        "fewer than two shipped packs declare tools, so the cross-pack check is "
        f"vacuous; packs resolved: {[p.name for p in packs]}"
    )


def test_tool_hygiene_check_catches_every_violation_it_claims_to() -> None:
    """SC-003: the mechanical check has teeth.

    Each case below is a way a pack could name another stack's tool. A check
    that passes the shipped packs but cannot fail is not evidence of anything,
    so every rule is exercised against a pack built to break it.
    """
    python = stack_packs_module.StackPack(
        name="python",
        label="Python",
        markers=("pyproject.toml",),
        toolchain="Python (uv)",
        commands={"test": "uv run pytest -q"},
        tools=("uv", "pytest"),
        dependency_policy="Ask first.",
        source="<synthetic>",
    )

    def variant(**overrides: Any) -> stack_packs_module.StackPack:
        return python._replace(**overrides)

    # 1. A command running a tool the pack never declared.
    undeclared = variant(name="node", commands={"test": "npm test"}, tools=())
    assert stack_packs_module.check_tool_hygiene([undeclared]), (
        "a command running an undeclared tool was not caught"
    )

    # 2. A pack whose command names another pack's tool as an argument, where
    #    the leading executable is its own. This is the case a leading-token
    #    check alone misses.
    node = variant(
        name="node",
        label="Node.js",
        markers=("package.json",),
        toolchain="Node.js (npm)",
        commands={"test": "npm test"},
        tools=("npm",),
    )
    smuggler = variant(commands={"test": "uv run npm test"})
    caught = stack_packs_module.check_tool_hygiene([smuggler, node])
    assert any("npm" in v for v in caught), (
        f"a foreign tool hidden in an argument was not caught; got {caught}"
    )

    # 3. A pack claiming another pack's tool as its own, which is how a pack
    #    would dodge rule 2 by declaring the tool it smuggles.
    claimer = variant(commands={"test": "npm test"}, tools=("uv", "pytest", "npm"))
    assert stack_packs_module.check_tool_hygiene([claimer, node]), (
        "two packs claiming the same tool were not caught"
    )

    # 4. A pack padding its roster with a tool none of its commands runs, which
    #    is the other half of the rule-3 dodge.
    padded = variant(tools=("uv", "pytest", "npm"))
    assert stack_packs_module.check_tool_hygiene([padded]), (
        "a declared tool that no command runs was not caught"
    )

    # 5. A pack with commands but no tool roster at all.
    rosterless = variant(tools=())
    assert stack_packs_module.check_tool_hygiene([rosterless]), (
        "a pack with commands and no declared tools was not caught"
    )

    # And the honest pair passes, so the check is not simply always failing.
    assert stack_packs_module.check_tool_hygiene([python, node]) == []


def test_every_shipped_pack_travels_in_the_wheel() -> None:
    """T020: pack data is package data, and the evidence is a built wheel.

    Defect #103 was an installed Ergane that carried none of its data files: a
    stranger's install seeded nothing. The plan's instruction is explicit —
    verify by inspecting a built wheel, never by reading the build config — so
    this reads the zip, not `pyproject.toml`.
    """
    # `test_distribution_install._build_wheel` is the one that copies the pack
    # directory into the build tree rather than relying on `git checkout-index`,
    # so it sees a pack file that is present but not yet committed. That matters:
    # the failure mode this test exists to catch is a pack that never reaches the
    # wheel, and a harness that silently omits new pack files would report that
    # failure for every new pack whether or not the packaging was sound.
    from tests.test_distribution_install import _build_wheel
    from tests.test_distribution_rename import _wheel_contents

    with tempfile.TemporaryDirectory() as tmp:
        contents = set(_wheel_contents(_build_wheel(Path(tmp))))

    shipped = stack_packs_module.resolve_stack_packs()
    assert shipped, "no stack packs resolved"
    for pack in shipped:
        expected = f"factory/{stack_packs_module.PACKS_DIRNAME}/{Path(pack.source).name}"
        assert expected in contents, (
            f"pack {pack.name!r} is not in the wheel; a stranger's install would "
            f"not carry it. Wheel holds: "
            f"{sorted(p for p in contents if stack_packs_module.PACKS_DIRNAME in p)}"
        )


def test_two_markers_produce_question_not_pick(
    tmp_path: Path,
) -> None:
    """Edge case: two stack markers in one repository produce a question, not a pick."""
    repo = make_bare_repo(
        tmp_path,
        {
            "README.md": "# app\n",
            "pyproject.toml": "[project]\nname = 'app'\nversion = '0.1.0'\n",
            "package.json": '{"name": "app", "version": "0.1.0"}\n',
        },
    )

    # For this test to exercise ambiguity, add a second shipped pack that also
    # matches package.json so detection sees more than one match.
    extra_dir = tmp_path / "extra_packs"
    extra_dir.mkdir()
    node_pack = {
        "name": "node",
        "label": "Node.js",
        "markers": ["package.json"],
        "toolchain": "Node.js (npm)",
        "commands": {"test": "npm test", "lint": "npm run lint"},
        "dependency_policy": "Ask before adding dependencies.",
    }
    (extra_dir / "node.yaml").write_text(
        yaml.safe_dump(node_pack, sort_keys=False), encoding="utf-8"
    )

    detected = stack_packs_module.detect_stack(repo, extra_directories=[extra_dir])

    assert detected is None, (
        "two markers produced a single pick instead of a question"
    )

    # `None` alone is not enough: it is also what "nothing matched" returns, and
    # the two demand opposite treatment. Unmatched means write the fallback;
    # ambiguous means ask. A caller that cannot tell them apart has to guess,
    # which is the trap. So the detection result names which case it is.
    detection = stack_packs_module.detect_stack_packs(repo, extra_directories=[extra_dir])
    assert detection.ambiguous, "ambiguity is not reported as ambiguity"
    assert not detection.unmatched, "ambiguity was reported as no match at all"
    assert {p.name for p in detection.candidates} == {"python", "node"}, (
        f"candidates not both named; got {[p.name for p in detection.candidates]}"
    )
    assert detection.pack is None, "an ambiguous detection still picked a pack"

    plain_parent = tmp_path / "plain"
    plain_parent.mkdir()
    unmatched = stack_packs_module.detect_stack_packs(
        make_bare_repo(plain_parent, {"README.md": "# app\n"})
    )
    assert unmatched.unmatched, "a repo with no markers was not reported unmatched"
    assert not unmatched.ambiguous, "a repo with no markers was reported ambiguous"


def test_ambiguity_is_not_silently_resolved_without_an_operator(
    tmp_path: Path,
) -> None:
    """Plan trap 7, T021: with nobody to ask, ambiguity still is not a pick.

    The non-interactive path cannot put a question on a terminal, so the honest
    outcome is the fallback layer *plus* a statement that no stack was chosen
    and why. Silently writing one of the candidates' layers would be the coin
    flip the trap forbids; silently writing the fallback would hide a question
    the operator needs to answer.
    """
    repo = make_bare_repo(
        tmp_path,
        {
            "pyproject.toml": "[project]\nname = 'app'\nversion = '0.1.0'\n",
            "package.json": '{"name": "app", "version": "0.1.0"}\n',
        },
    )

    pack, notice = init_module.select_stack_without_operator(repo)

    assert pack.fallback, (
        f"an ambiguous repository was assigned the {pack.name!r} stack with no "
        "operator to confirm it"
    )
    assert "python" in notice.lower() and "node" in notice.lower(), (
        f"the notice does not name the candidates it could not choose between: {notice!r}"
    )
    assert "no stack" in notice.lower() or "not choose" in notice.lower(), (
        f"the notice does not say that no stack was chosen: {notice!r}"
    )


def test_adding_a_pack_changes_only_data_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US2-S5/FR-010/SC-004: adding a pack changes no code outside the pack data.

    The selector reads from data and branches on what it finds, so adding a new
    pack requires only a new data file. This test lists the resolved packs, adds
    a synthetic one in a temporary location, and asserts the selector sees it
    without a new code branch.
    """
    packs = stack_packs_module.resolve_stack_packs()
    names_before = {p.name for p in packs}

    # Create a synthetic pack file and add it to the resolution path through the
    # test seam. The implementation must provide a way to point the resolver at
    # additional directories; this test documents that seam.
    extra_dir = tmp_path / "extra_packs"
    extra_dir.mkdir()
    synthetic = {
        "name": "synthetic-test-stack",
        "label": "Synthetic",
        "markers": ["synthetic.marker"],
        "toolchain": "synthetic",
        "commands": {"test": "synthetic-test"},
        "dependency_policy": "Ask before adding dependencies.",
    }
    (extra_dir / "synthetic.yaml").write_text(
        yaml.safe_dump(synthetic, sort_keys=False), encoding="utf-8"
    )

    with_packs = stack_packs_module.resolve_stack_packs(extra_directories=[extra_dir])
    names_after = {p.name for p in with_packs}

    assert "synthetic-test-stack" in names_after, "synthetic pack was not picked up"
    assert names_before <= names_after, "adding a pack dropped an existing pack"

    # Resolution is only half of it. The pack has to be *selected* from its own
    # declared markers and *written* by the same renderer as every other pack,
    # with no code taught about it.
    repo_parent = tmp_path / "repo"
    repo_parent.mkdir()
    repo = make_bare_repo(repo_parent, {"synthetic.marker": "x\n"})
    detection = stack_packs_module.detect_stack_packs(repo, extra_directories=[extra_dir])
    assert detection.pack is not None and detection.pack.name == "synthetic-test-stack", (
        "the selector did not choose the added pack from its own declared markers"
    )

    layer = detection.pack.render_layer()
    assert "synthetic-test" in layer, f"the added pack's command was not written: {layer!r}"
    assert "Synthetic" in layer, f"the added pack's label was not written: {layer!r}"


def test_no_shipped_pack_is_named_in_the_code_that_selects_or_writes_packs() -> None:
    """SC-004/FR-010: the selector reads data, not a branch per stack.

    A resolver that loads data files and a writer that then says
    `if pack.name == "agnostic"` has moved the branch rather than removed it,
    and the next pack that needs different treatment gets another one. So no
    shipped pack's name may appear as a literal in the code that selects or
    writes packs — including the fallback's, which is declared by the pack data
    itself (constitution IX: the value is read from the declaration that owns
    it).
    """
    packs = stack_packs_module.resolve_stack_packs()
    assert packs, "no stack packs resolved"

    fallbacks = [p for p in packs if p.fallback]
    assert len(fallbacks) == 1, (
        f"expected exactly one pack to declare itself the fallback, got "
        f"{[p.name for p in fallbacks]}"
    )

    repo_root = Path(stack_packs_module.__file__).resolve().parents[1]
    sources = [
        repo_root / "factory" / "stack_packs.py",
        repo_root / "factory" / "cli" / "init.py",
    ]
    for source in sources:
        text = source.read_text(encoding="utf-8")
        # Strip comments and docstring prose is not worth the machinery; match
        # the quoted literal instead, which is what a branch would need.
        for pack in packs:
            for literal in (f'"{pack.name}"', f"'{pack.name}'"):
                assert literal not in text, (
                    f"{source.relative_to(repo_root)} names pack {pack.name!r} as a "
                    f"literal ({literal}); packs are data, so selecting or writing "
                    "one must not require the code to know its name"
                )
