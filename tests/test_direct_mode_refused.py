"""048-US2: a declaration the dispatch path cannot honour is refused where it is made.

`llm.mode = "direct"` is a choice the interview offered, that `ergane install
--verify` passed more cleanly than `gateway` did, and that cannot run a single
attempt: `issue_attempt_key` mints a LiteLLM *virtual key*, and that is the only
credential primitive this factory has. Honouring `direct` means building a
second per-attempt attribution mechanism, which touches constitution principle V
and is an epic rather than a story. So the mode is refused at the parser.

Two properties this file exists to pin, both easy to get wrong:

- **The token stays in `KNOWN_LL_MODES`.** Deleting it would make the refusal
  read "supported modes are 'gateway'", which tells an operator they made a typo
  when they made a reasonable choice. `temporal.mode = "managed"` is the
  precedent: recognized by name, refused with a message that says why and what
  to do instead.
- **The apparatus is gone, not merely unreachable.** Dead persona-reading,
  persona-seeding and persona-probing code that no branch reaches is a mode that
  can be switched back on by accident. `test_no_module_constructs_renders_or_
  probes_a_direct_block` walks the AST of the three modules rather than grepping
  them, so a comment cannot fail it and a rename cannot hide from it.

Every test binds the config path explicitly (FR-012, plan trap 4) — through the
`config_path` fixture, which sets `ERGANE_CONFIG_PATH` under `tmp_path`. None can
reach the operator's real `~/.config/ergane/config.toml`.

`DIRECT_CONFIG` below **parsed cleanly on the tree before this story**: it carries
a complete `[[llm.persona]]` block, so the refusal these tests assert on is the
new rule firing and not an incidental "persona block missing". Its network
addresses are closed loopback ports so that the red run, in which the probes
still executed, dialled nothing that could answer.

The interview harness (`walkthrough`, `config_path`, `_invoke`) is imported from
the 033 walkthrough tests rather than rebuilt: a second prompter convention one
epic later is the drift the seam was spent avoiding.

The runtime evidence — the red run, one mutation per behaviour, and the command
driven by hand — is pasted verbatim at the bottom of this file (constitution
VIII / D-037).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from factory.cli.errors import EXIT_USER
from factory.controlplane.config import (
    KNOWN_LL_MODES,
    RULE_LLM_DIRECT_NOT_SUPPORTED,
    RULE_UNKNOWN_LLM_MODE,
    ControlPlaneConfigError,
    parse_controlplane_config,
)

# The 033 harness. Two are fixtures, and importing them registers them here.
from tests.test_ergane_install_walkthrough import (  # noqa: F401
    GATEWAY_ANSWERS,
    Run,
    ScriptedPrompter,
    _invoke,
    config_path,
    walkthrough,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The three modules US2-S5 names. Nothing in any of them may construct, render
#: or probe a `direct` LLM block.
DIRECT_SURFACE = (
    REPO_ROOT / "factory" / "controlplane" / "config.py",
    REPO_ROOT / "factory" / "cli" / "install.py",
    REPO_ROOT / "factory" / "controlplane" / "verify.py",
)

#: Every identifier the `direct` apparatus was built from, across all three
#: modules. A rename is not a removal, so the check is by name and by AST node,
#: not by grep.
DIRECT_APPARATUS = frozenset(
    {
        "LLMDirectPersona",
        "_read_direct_personas",
        "_ask_personas",
        "_PERSONA_SEED",
        "_PERSONA_ORDER",
        "personas",
    }
)

#: A config declaring `direct` with everything `direct` used to require. Closed
#: loopback ports throughout: on the red run the probes still ran.
DIRECT_CONFIG = """\
version = 1

[llm]
mode = "direct"

[[llm.persona]]
name = "implementer"
base_url = "http://127.0.0.1:1/v1"
model = "openai/gpt-4o"
api_key_env = "DECLARED_PERSONA_KEY"

[memory]
backend = "none"

[temporal]
mode = "external"
address = "127.0.0.1:4"
namespace = "ergane"

[telemetry]

[escalation]
adapter = "telegram"
"""


# ---------------------------------------------------------------------------
# T016 / US2-S1 — the parser refuses, naming the reason and the route
# ---------------------------------------------------------------------------


def test_direct_mode_is_refused_naming_the_virtual_key_and_the_gateway_route() -> None:
    """US2-S1, FR-008: a stable slug, the reason, and what to do instead.

    The three assertions are the whole of the acceptance criterion: a slug a
    caller can branch on, the *reason* (an attempt runs on a virtual key minted
    at the proxy, and there is nothing to mint for a per-persona endpoint), and
    the supported route named by mode. A refusal that only declines leaves the
    operator to guess.
    """
    with pytest.raises(ControlPlaneConfigError) as excinfo:
        parse_controlplane_config(DIRECT_CONFIG, source="fixture.toml")

    error = excinfo.value
    assert error.rule == RULE_LLM_DIRECT_NOT_SUPPORTED
    assert "virtual key" in error.problem
    assert "gateway" in error.problem
    # The rendered message an operator actually reads names the file too.
    assert str(error).startswith("fixture.toml: [llm_direct_not_supported]")


def test_direct_stays_a_recognised_token_so_the_refusal_stays_specific() -> None:
    """Plan trap 8: refused, not forgotten.

    Deleting `"direct"` from `KNOWN_LL_MODES` would satisfy "the parser refuses
    it" while answering a question the operator did not ask — they would be told
    they typed something unknown. The distinction is asserted against a mode
    that really *is* unknown: the two must not collapse to the same message.
    """
    assert "direct" in KNOWN_LL_MODES

    with pytest.raises(ControlPlaneConfigError) as refused:
        parse_controlplane_config(DIRECT_CONFIG, source="fixture.toml")
    assert refused.value.rule != RULE_UNKNOWN_LLM_MODE

    unknown_text = DIRECT_CONFIG.replace('mode = "direct"', 'mode = "sidecar"')
    with pytest.raises(ControlPlaneConfigError) as unknown:
        parse_controlplane_config(unknown_text, source="fixture.toml")
    assert unknown.value.rule == RULE_UNKNOWN_LLM_MODE
    assert "sidecar" in unknown.value.problem


# ---------------------------------------------------------------------------
# T017 / US2-S2 — the interview neither offers nor accepts it
# ---------------------------------------------------------------------------


def test_the_interview_re_asks_carrying_the_parsers_own_refusal(
    walkthrough,  # noqa: ANN001 - fixture imported from the walkthrough tests
    config_path: Path,
) -> None:
    """US2-S2, FR-009: answering `direct` is refused exactly as any other bad value.

    Nothing in `factory/cli/install.py` decides this. `_ask` renders the
    candidate document and hands it to `parse_controlplane_config`, so the
    moment the parser refuses `direct` the interview refuses it too — which is
    why this story is subtraction rather than a second rule table (plan trap 9).
    What install still has to do by hand is stop *offering* the mode and stop
    seeding a persona block, and both are asserted here on the questions
    actually asked.
    """
    answers = ["direct", *GATEWAY_ANSWERS]

    _, prompter = walkthrough(answers)

    mode_prompts = [p for p in prompter.prompts if p.startswith("llm mode")]
    # Asked twice: once refused, once answered.
    assert len(mode_prompts) == 2
    errors = prompter.errors_for(mode_prompts[0])
    assert len(errors) == 1
    assert RULE_LLM_DIRECT_NOT_SUPPORTED in errors[0]
    assert "virtual key" in errors[0]

    # The mode is not offered, and no persona question follows from asking for it.
    assert not any("direct" in prompt for prompt in prompter.prompts)
    assert not any("persona" in prompt for prompt in prompter.prompts)

    # Every answer was consumed and the file that was written declares gateway.
    assert prompter.answers == []
    assert 'mode = "gateway"' in config_path.read_text(encoding="utf-8")
    assert "persona" not in config_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# T018 / US2-S3 — an operator who installed before this change
# ---------------------------------------------------------------------------


def test_an_existing_direct_config_fails_closed_rather_than_being_rewritten(
    walkthrough,  # noqa: ANN001 - fixture imported from the walkthrough tests
    config_path: Path,
) -> None:
    """US2-S3: re-running install over a `direct` file names the file and the reason.

    `_starting_document` loads the existing config as defaults and fails closed
    on a config the parser refuses, rather than falling back to blank-host
    defaults — which would silently rewrite a file whose contents nobody could
    see. That path already existed; this pins that the new rule reaches it.

    The prompter is given *no answers at all*, so a walkthrough that asked even
    one question would run out and fail loudly rather than pass quietly.
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(DIRECT_CONFIG, encoding="utf-8")

    result, prompter = walkthrough([])

    assert result.code == EXIT_USER
    assert prompter.prompts == []
    assert str(config_path) in result.stderr
    assert RULE_LLM_DIRECT_NOT_SUPPORTED in result.stderr
    assert "fix or remove that file" in result.stderr
    # Not silently rewritten: the bytes on disk are the operator's own.
    assert config_path.read_text(encoding="utf-8") == DIRECT_CONFIG


# ---------------------------------------------------------------------------
# T019 / US2-S4 — the inversion closed: no green verification for a dead mode
# ---------------------------------------------------------------------------


def test_verify_reports_the_refusal_and_reports_no_passing_check(
    config_path: Path,
) -> None:
    """US2-S4, FR-010, SC-003: `direct` was the mode that verified cleanest.

    That is the defect in one line — the probe used only declared values and
    reported PASS on a host with no `LITELLM_*` variable set, for a mode that
    could not mint an attempt key. After this story the config never parses, so
    no probe runs and no finding can be green. `[PASS]` appearing anywhere in
    the output is the failure this asserts against.
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(DIRECT_CONFIG, encoding="utf-8")

    result = _invoke(["install", "--verify"])

    assert result.code == EXIT_USER
    assert "[PASS]" not in result.stdout
    assert RULE_LLM_DIRECT_NOT_SUPPORTED in result.stderr
    assert str(config_path) in result.stderr


# ---------------------------------------------------------------------------
# T020 / US2-S5 — the apparatus is gone, proven structurally
# ---------------------------------------------------------------------------


def _module_trees() -> list[tuple[Path, ast.Module]]:
    return [
        (path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        for path in DIRECT_SURFACE
    ]


def _identifiers(tree: ast.Module) -> set[str]:
    """Every name a module defines, reads or writes, however it spells it."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
        elif isinstance(node, ast.alias):
            names.add(node.asname or node.name.rsplit(".", 1)[-1])
    return names


def _persona_literals(tree: ast.Module) -> set[str]:
    """String constants that could only be a `[[llm.persona]]` key or prompt.

    Deliberately narrow: `verify.py` says "persona `implementer`" about the
    *registry* persona a gateway completion runs as, which is a different object
    and stays. What may not survive is the TOML key, the dotted field paths and
    the interview's persona questions.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
            if text == "persona" or "llm.persona" in text or "llm persona" in text:
                found.add(text)
    return found


def _direct_branches(tree: ast.Module) -> list[ast.If]:
    """Every `if` whose condition mentions the literal `"direct"`."""
    branches: list[ast.If] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        for inner in ast.walk(node.test):
            if isinstance(inner, ast.Constant) and inner.value == "direct":
                branches.append(node)
                break
    return branches


def test_no_module_constructs_renders_or_probes_a_direct_block() -> None:
    """US2-S5: read the three modules' ASTs, not their text.

    Three structural claims, each of which the tree before this story breaks:

    1. no module names any part of the persona apparatus, under any spelling;
    2. no module carries a `[[llm.persona]]` key, field path or prompt;
    3. the only thing a branch on `"direct"` may do is raise — which is what
       separates "recognized and refused" from "still supported somewhere".
    """
    apparatus: list[str] = []
    literals: list[str] = []
    doing: list[str] = []
    raising: list[str] = []

    for path, tree in _module_trees():
        for name in sorted(_identifiers(tree) & DIRECT_APPARATUS):
            apparatus.append(f"{path.name}: {name}")
        for text in sorted(_persona_literals(tree)):
            literals.append(f"{path.name}: {text!r}")
        for branch in _direct_branches(tree):
            where = f"{path.name}:{branch.lineno}"
            if all(isinstance(stmt, ast.Raise) for stmt in branch.body):
                raising.append(where)
            else:
                doing.append(where)

    assert apparatus == []
    assert literals == []
    assert doing == []
    # And the refusal really is there: exactly one branch, in the parser.
    assert len(raising) == 1
    assert raising[0].startswith("config.py:")


# ===========================================================================
# Runtime evidence (constitution VIII / D-037): pasted, not described.
# ===========================================================================
#
# --- The red run, before the refusal existed -------------------------------
#
# Committed first, on a tree carrying only `RULE_LLM_DIRECT_NOT_SUPPORTED` as a
# constant nothing read — so each test fails on its own assertion rather than on
# an import, which a collection error could not have shown.
#
#   $ uv run pytest -q tests/test_direct_mode_refused.py --tb=line
#   FFFFFF                                                          [100%]
#   E   Failed: DID NOT RAISE ControlPlaneConfigError                    (:135)
#   E   Failed: DID NOT RAISE ControlPlaneConfigError                    (:156)
#   E   AssertionError: assert 1 == 2                                    (:192)
#       +  where 1 = len(['llm mode (gateway|direct)'])
#   E   AssertionError: assert ['llm mode (gateway|direct)'] == []       (:233)
#   E   assert '[PASS]' not in '[FAIL] llm:...escalation\n'              (:263)
#       [PASS] memory: skipped by declaration: memory.backend is `none`
#       [PASS] telemetry: skipped by declaration: telemetry has no otlp_endpoint
#   E   AssertionError: assert ['config.py: ...ersonas', ...] == []      (:356)
#       Left contains 7 more items, first extra item: 'config.py: LLMDirectPersona'
#   6 failed in 0.12s
#
# The fifth line is this story's reason to exist, in the old tree's own output:
# a config declaring a mode that cannot mint an attempt key verified two checks
# green.
#
#
# --- Mutation testing, one mutation per behaviour --------------------------
#
# A green suite proves nothing about a test that cannot fail, so each behaviour
# was broken on purpose in the production tree and these files re-run. Every
# mutation was reverted with `git checkout --`, and `git status` was clean
# afterwards, so the tree these transcripts describe is the tree in this diff.
#
#   $ uv run pytest -q tests/test_direct_mode_refused.py \
#       tests/test_controlplane_config.py \
#       tests/test_ergane_install_walkthrough.py --tb=no    # once per mutation
#
# M1  the refusal never fires: `direct` parses again
#     [the raise becomes `return ControlPlaneConfig.LLM(mode="direct")`]
#     7 failed, 30 passed in 2.32s — every test in this file, plus
#     test_controlplane_config.py::test_direct_llm_mode_refused
#
# M2  the token is deleted from KNOWN_LL_MODES, the refusal kept
#     6 failed, 31 passed in 2.35s
#     This is plan trap 8 as a measurement: the refusal still fires, under
#     `unknown_llm_mode`, and five tests plus the config file's own case reject
#     it. Only the AST test survives, correctly — nothing structural moved.
#
# M3  the refusal declines without naming the reason or the route
#     ["`llm.mode` is not supported", same slug]
#     3 failed, 34 passed in 2.29s
#       test_direct_mode_is_refused_naming_the_virtual_key_and_the_gateway_route
#       test_the_interview_re_asks_carrying_the_parsers_own_refusal
#       test_controlplane_config.py::test_direct_llm_mode_refused
#
# M4  the interview offers `direct` again [the question text reverts]
#     2 failed, 35 passed in 2.32s
#       test_the_interview_re_asks_carrying_the_parsers_own_refusal
#       test_ergane_install_walkthrough.py::test_the_real_terminal_prompter_…
#
# M5  a seed for the removed mode comes back to install.py
#     1 failed, 36 passed in 2.32s — test_no_module_constructs_renders_or_…
#
# M6  `_apply_llm_mode` seeds a direct block again
#     1 failed, 36 passed in 2.30s — test_no_module_constructs_renders_or_…
#
# M7  the verify probe grows a direct branch again
#     1 failed, 36 passed in 2.35s — test_no_module_constructs_renders_or_…
#
#     M5, M6 and M7 are the three shapes the apparatus could return in — a dead
#     seed, a live construction, a live probe — one per module. Only the AST
#     test catches any of them, which is what it is for: none changes an
#     observable behaviour, and all three are a mode that can be switched back
#     on by accident.
#
# M8  `_ask_memory` stops honouring the chosen backend
#     [the `backend == "none"` early return is removed]
#     1 failed, 13 passed in 2.25s
#       test_ergane_install_walkthrough.py::test_walkthrough_asks_only_the_…
#     Run because that test was *flipped* by this story — its two-mode
#     demonstration moved from `llm` to `memory` — and a flipped test that
#     cannot fail is worse than the one it replaced.
#
#
# --- The commands, run by hand ---------------------------------------------
#
# Because a green suite has shipped a command that could not start. Paths elided
# to `$SB`, a scratch directory; `ERGANE_CONFIG_PATH` was bound to it throughout,
# so nothing below touched the operator's own config.
#
# (a) The interview, answering `direct` — and `managed` further down, so the two
#     refusals can be read side by side. This is US2-S2 as an operator meets it.
#
#   $ printf 'direct\ngateway\nhttp://127.0.0.1:1/v1\nERGANE_LLM_MASTER_KEY\n
#             none\nmanaged\nexternal\n127.0.0.1:4\nergane\n\n\n
#             http://127.0.0.1:3\n\n\n\n' | ergane install
#   llm mode (gateway) [gateway]:   $SB/config.toml: [llm_direct_not_supported]
#   `llm.mode = "direct"` cannot be dispatched against: every attempt runs on its
#   own model-constrained, TTL'd virtual key minted at the LiteLLM proxy, and a
#   per-persona provider endpoint has no such key to mint, revoke or attribute.
#   Put a LiteLLM-shaped gateway in front of the provider and declare
#   `llm.mode = "gateway"`
#   llm mode (gateway) [gateway]: llm gateway base_url [http://127.0.0.1:4000]:
#   llm gateway master key env-var name [ERGANE_LLM_MASTER_KEY]: memory backend
#   (hindsight|none) [none]: temporal mode (external|managed) [external]:
#     $SB/config.toml: [temporal_managed_not_implemented] `temporal.mode =
#   "managed"` is not implemented; it arrives with epic 042 (managed Temporal +
#   worker units)
#   temporal mode (external|managed) [external]: temporal address …
#   wrote $SB/config.toml
#
#   verifying the control plane...
#   [FAIL] llm: ERGANE_LLM_MASTER_KEY is not set; no credential to complete a round trip
#   [FAIL] temporal: Temporal at 127.0.0.1:4 did not answer: RuntimeError: …
#   [PASS] memory: skipped by declaration: memory.backend is `none`
#   [FAIL] telemetry: could not export to OTLP endpoint http://127.0.0.1:3: …
#   [FAIL] escalation: TELEGRAM_CHAT_ID is not set; cannot deliver a test escalation
#   EXIT=1
#
# (b) US2-S4, against a config file already on disk declaring `direct` — the
#     operator who installed before this change. No probe runs and no finding is
#     printed at all, green or otherwise.
#
#   $ ERGANE_CONFIG_PATH=$SB/legacy.toml ergane install --verify
#   ergane: $SB/legacy.toml: [llm_direct_not_supported] `llm.mode = "direct"`
#   cannot be dispatched against: every attempt runs on its own
#   model-constrained, TTL'd virtual key minted at the LiteLLM proxy, and a
#   per-persona provider endpoint has no such key to mint, revoke or attribute.
#   Put a LiteLLM-shaped gateway in front of the provider and declare
#   `llm.mode = "gateway"`
#   EXIT=1
#
# (c) US2-S3, the same file, re-running the interview over it.
#
#   $ ERGANE_CONFIG_PATH=$SB/legacy.toml ergane install
#   ergane: $SB/legacy.toml: [llm_direct_not_supported] `llm.mode = "direct"`
#   cannot be dispatched against: … declare `llm.mode = "gateway"`; fix or
#   remove that file, then re-run `ergane install`
#   EXIT=1
#   file unchanged: yes
#
#   The last line is `md5sum` before and after: the operator's file was not
#   silently rewritten, and no question was asked before the refusal.
#
#
# --- The full suite, on the tree in this diff -------------------------------
#
#   $ uv run pytest -q
#   2778 passed, 44 skipped, 5 warnings in 292.49s (0:04:52)
#
# One thing worth recording rather than hiding, because it cost this session an
# hour and is a hazard for the next node: the first mutation battery run here
# measured nothing. Its `git checkout --` revert restored each production file
# to HEAD, and HEAD was still the *red* commit, so mutations M2 onward ran
# against a tree with no implementation at all and every one of them reported
# the same failures. The implementation was re-applied, committed, and the
# battery re-run against it — the numbers above are from that second run.
# Commit before you mutate.
