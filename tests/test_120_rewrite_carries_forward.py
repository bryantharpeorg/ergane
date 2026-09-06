"""120/US2: when `ergane init` does rewrite a manifest, it carries it forward.

US1 stopped the common case — a valid manifest is now kept, byte for byte. This
file is about the case that remains: the rewrite init genuinely performs, which
is the mechanism the reported data loss came through and which US1 does not
touch. A rewrite that silently drops what the operator declared is the same
defect wearing a rarer hat.

The mechanism, stated once so every assertion below reads as a consequence of
it: `_init_default` computed the existing manifest's values through
`_build_defaults` and then returned `None` for every member of `_OPTIONAL_KEYS`
one line before using them, and `_render_manifest` emitted only
`_TOP_LEVEL_KEYS`, which is the schema's *v1* vocabulary — so `ladder` and
`verify` could not survive any path at all, interview or not.

Seven assertions, one per acceptance scenario, plus the two the plan's traps
ask for:

- **standards survives a non-interactive rewrite** (US2-S1, trap 4).
- **`ladder` and `verify` survive on either path** (US2-S2, trap 5). Carried,
  not interviewed: `tests/test_forge_manifest.py` pins `set(_PROMPTS) ==
  set(_TOP_LEVEL_KEYS)`, so growing the question set is not available and is not
  wanted.
- **an unrecognised key refuses, naming it** (US2-S3), rather than being dropped.
- **the control** (US2-S4): a manifest written where none existed still has its
  optional keys absent. Without this the story is passable by an init that
  invents values for a repository that declared none.
- **comment loss is announced before the write** (US2-S5), proven at the moment
  `_write_scaffold` is called rather than by the order of two lines in a buffer.
- **the remedy loop** (US2-S6): the guidance init itself prints — re-run with
  `--wire` — is followed, and the `ladder` block is still there afterwards.
- **the check reports the file** (US2-S7): after that re-run, the schedule the
  check judges healthy is the one the operator's own dial asked for, and the
  manifest it judges still declares everything it declared. The loss erased its
  own evidence by moving both sides together; this is the assertion that would
  have caught it.
- **round trip** (FR-007, trap 6): init's own output rewrites without refusing,
  so the refusal fires on an operator's hand-added key and never on init's.
- **the whole tuple** (FR-005, trap 4): every member of `_OPTIONAL_KEYS`, not
  only `standards`, because a fix special-cased to the reported key leaves the
  next four for the next person to find.

No real GitHub, Temporal or control plane is reached: `bind_offline_seams` binds
every outward seam, and the schedule assertions read `FakeScheduleServer`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

import factory.cli.init as init_module
from factory.cli.errors import EXIT_OK, EXIT_USER
from factory.verify.factory_yaml import (
    MANIFEST_NAME,
    _TOP_LEVEL_KEYS,
    parse_factory_config,
)

from tests.fake_schedules import FakeScheduleServer
from tests.test_ergane_init import _invoke, make_bare_repo
from tests.test_ergane_init_check import bind_offline_seams
from tests.test_ergane_init_wiring import FakeGitHub

#: A manifest of the shape the finding was reported against, and then some: it
#: declares one key from every group a rewrite has to carry — an interviewed
#: optional key (`standards`), a block init has no vocabulary for (`ladder`), a
#: v2 list (`verify`), and a dial the check reconciles against (`roadmap`).
#: Every line beginning with `#` is prose no emitter in this tree can reproduce.
CONFIGURED_MANIFEST = """\
# ergane.yaml — what "green" means for this repository, and why.
#
# Written by hand and committed. The comments are the reason the values are
# what they are.

version: 2
runtime: bwrap

gates:
  test: "uv run pytest -q"

# The document every dispatched agent is told to read and obey. This is the key
# whose loss started epic 120.
standards: docs/STANDARDS.md

landing_branch: main

# Reconciled onto this repository's Temporal schedule by init itself.
roadmap:
  cadence_s: 900

# A block init had no vocabulary for: absent from `_TOP_LEVEL_KEYS` and from
# `_PROMPTS`, and therefore absent from anything init wrote.
ladder:
  max_attempts: 4
  debugger_cycles: 1

# This repository judges nothing: gates and the diff bound decide, and no judge
# runs. A rewrite that dropped this line would quietly re-enable one.
verify:
  - gates
  - diff_check
"""

#: The cache path is spelled `~`-relative on purpose: the parser refuses a path
#: outside the operator's home, and `~` is the one spelling that is inside it on
#: whatever machine the suite runs on. It is also the spelling a carry-forward
#: must keep — resolving it would rewrite the operator's line into this host's.
EVERY_OPTIONAL_KEY = """\
version: 2
runtime: bwrap
gates:
  test: "uv run pytest -q"
timeouts:
  test: 1800
standards: docs/STANDARDS.md
landing_branch: main
roadmap:
  cadence_s: 900
  max_concurrent_epics: 2
  max_concurrent_nodes: 3
forge: github
writes:
  test: true
caches:
  - path: ~/.cache/ergane-120
    env: ERGANE_120_CACHE
diff_refusal_bytes: 120000
"""

#: `_PROMPTS` keyed the other way round, so a prompter can answer by manifest
#: key rather than by matching the human sentence init happens to print.
_KEY_BY_PROMPT = {text: key for key, text in init_module._PROMPTS.items()}


class ConfirmingPrompter:
    """An operator who accepts every value init offers, changing only what they mean to.

    Deliberately not the empty answer. For an optional key an empty answer means
    *omit* — the operator asking for the key to go — so a prompter built from
    empty strings could never distinguish "init dropped my `standards`" from "I
    asked for it to be dropped". This one answers with the default init printed,
    which is the operator who read the offer and accepted it.

    `changes` is keyed by manifest key; anything in it is typed over the offer,
    which is how a test forces a rewrite rather than the keep US1 gave it.
    """

    def __init__(self, changes: dict[str, str] | None = None, *, slug: str = "app") -> None:
        self.changes = dict(changes or {})
        self.slug = slug
        self.asked: list[str] = []

    def ask(self, prompt: str, *, default: str | None = None, error: str | None = None) -> str:
        if error is not None:
            # A re-ask means the parser refused the previous answer. Answering
            # again with the same text would spin forever, so the refusal is the
            # test result.
            raise AssertionError(f"the parser refused {prompt!r}: {error}")
        self.asked.append(prompt)
        if prompt == "repo slug":
            return self.slug
        # 057/US4: the template-source question is not part of the manifest schema,
        # so it has no entry in `_KEY_BY_PROMPT`. Accepting the default means using
        # the shipped default.
        if prompt == init_module._TEMPLATE_SOURCE_PROMPT:
            return default or ""
        key = _KEY_BY_PROMPT.get(prompt)
        if key is None:
            raise AssertionError(f"unexpected question: {prompt!r}")
        if key in self.changes:
            return self.changes[key]
        return default or ""


def repo_with(tmp_path: Path, manifest: str | None) -> Path:
    """A committed git repository, optionally already declaring a manifest.

    `make_bare_repo` names the directory `app`, which is also the slug init
    normalises out of it — the one T013b reads the schedule back under.
    """
    files = {"README.md": "# app\n", "pyproject.toml": "[project]\nname='app'\n"}
    if manifest is not None:
        files[MANIFEST_NAME] = manifest
    return make_bare_repo(tmp_path, files)


def rewritten_non_interactively(repo: Path) -> str:
    """The manifest text the non-interactive path produces over `repo`.

    Init's own machinery, not a re-implementation of it: `_interview` is the
    function `init_command` runs whenever it rewrites, and
    `_NonInteractivePrompter` is the prompter it runs it with under
    `--non-interactive`. What is left out is `init_command`'s US1 short-circuit,
    which is what decides *whether* to rewrite — this asks what a rewrite
    carries, which is the whole of US2.
    """
    existing = init_module._existing_manifest(repo)
    values = init_module._interview(
        repo, existing, prompter=init_module._NonInteractivePrompter(repo, [])
    )
    return init_module._render_manifest(values)


def wire_non_interactively(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    schedules: FakeScheduleServer | None = None,
    wire: bool = True,
) -> Any:
    """`ergane init [--wire] --non-interactive <repo>`, every seam bound offline."""
    bind_offline_seams(
        monkeypatch, FakeGitHub(owner_repo="acme/app"), schedules=schedules
    )
    argv = ["init", *(["--wire"] if wire else []), "--non-interactive", str(repo)]
    return _invoke(argv, monkeypatch)


def interactively(
    repo: Path, monkeypatch: pytest.MonkeyPatch, prompter: ConfirmingPrompter
) -> Any:
    """`ergane init <repo>` with an operator at the terminal, every seam bound."""
    monkeypatch.setattr(init_module, "_prompter_factory", lambda: prompter)
    bind_offline_seams(monkeypatch, FakeGitHub(owner_repo="acme/app"))
    return _invoke(["init", str(repo)], monkeypatch)


# ---------------------------------------------------------------------------
# T009 [US2-S1, trap 4] the reported key, on the reported path
# ---------------------------------------------------------------------------


def test_a_non_interactive_rewrite_keeps_a_declared_standards(tmp_path: Path) -> None:
    """US2-S1: the key whose loss started the epic survives the rewrite.

    Mutation: put the `_OPTIONAL_KEYS` early return back above the `defaults`
    consultation in `_init_default` and this fails — the value is computed by
    `_build_defaults` either way, and the ordering is the whole defect.
    """
    repo = repo_with(tmp_path, CONFIGURED_MANIFEST)

    text = rewritten_non_interactively(repo)

    assert parse_factory_config(text).standards == "docs/STANDARDS.md"
    assert "standards: docs/STANDARDS.md" in text


# ---------------------------------------------------------------------------
# T010 [US2-S2, trap 5] the two keys init had no vocabulary for, on both paths
# ---------------------------------------------------------------------------


def test_ladder_and_verify_survive_a_non_interactive_rewrite(tmp_path: Path) -> None:
    """US2-S2, first path. Neither key is asked about; both are carried."""
    repo = repo_with(tmp_path, CONFIGURED_MANIFEST)

    text = rewritten_non_interactively(repo)

    carried = parse_factory_config(text)
    assert carried.ladder.max_attempts == 4
    assert carried.ladder.debugger_cycles == 1
    assert carried.verify_order == ("gates", "diff_check")
    # Declared, not defaulted: a rewrite that dropped `verify` would parse to
    # the default order and read as if the operator had asked for a judge.
    assert "verify:" in text and "ladder:" in text


def test_ladder_and_verify_survive_an_interactive_rewrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US2-S2, second path — end to end, with a real rewrite on disk.

    The operator changes one gate command and confirms everything else, which is
    the ordinary reason to re-run init at all. The manifest is therefore
    genuinely rewritten (US1's keep does not apply), and the two keys nobody was
    asked about have to come through it.
    """
    repo = repo_with(tmp_path, CONFIGURED_MANIFEST)
    prompter = ConfirmingPrompter({"gates": 'test: "make check"'})

    result = interactively(repo, monkeypatch, prompter)

    assert result.code == EXIT_OK, result.stderr
    text = (repo / MANIFEST_NAME).read_text(encoding="utf-8")
    assert text != CONFIGURED_MANIFEST, "this test only proves anything on a rewrite"
    rewritten = parse_factory_config(text)
    assert rewritten.gates == {"test": "make check"}
    assert rewritten.ladder.max_attempts == 4
    assert rewritten.verify_order == ("gates", "diff_check")
    assert rewritten.standards == "docs/STANDARDS.md"
    # Trap 5: carried, never interviewed. Nobody was asked about either key.
    assert "ladder" not in " ".join(prompter.asked)
    assert "verify" not in " ".join(prompter.asked)


def test_the_interview_gains_no_question_for_a_carried_key() -> None:
    """Trap 5 stated as the invariant rather than as an observation.

    `tests/test_forge_manifest.py` already pins `set(_PROMPTS) ==
    set(_TOP_LEVEL_KEYS)`; this says the other half — that the keys init carries
    without asking are exactly the ones the interview has no prompt for.
    """
    carried = [key for key in init_module._KNOWN_KEYS if key not in _TOP_LEVEL_KEYS]

    # 128 FR-001: `boundary_only_gates` is a v2-only key, registered where
    # `ladder` and `verify` already were, so init carries it forward rather
    # than refusing it (trap 4: it must not go in `_TOP_LEVEL_KEYS`, where the
    # interview's prompt set lives) and gains no question for it (trap 5).
    assert carried == ["ladder", "verify", "boundary_only_gates"]
    assert not set(carried) & set(init_module._PROMPTS)


# ---------------------------------------------------------------------------
# T011 [US2-S3] an unrecognised key is a refusal, not a deletion
# ---------------------------------------------------------------------------


def test_a_key_init_cannot_carry_refuses_naming_it(tmp_path: Path) -> None:
    """US2-S3 at the seam that decides it.

    The document is built by hand because the loader refuses an unknown
    top-level key before init ever sees the file — which is the *good* case, and
    is why this guard exists for the other one: a key the schema has learned and
    init's writer has not. That is not hypothetical, it is the state this epic
    found the tree in, with `ladder` as the key.
    """
    repo = repo_with(tmp_path, CONFIGURED_MANIFEST)
    existing = init_module._existing_manifest(repo)
    ahead = init_module._ExistingManifest(
        path=existing.path,
        text=existing.text,
        declared={**existing.declared, "promotion": {"persona": "reviewer"}},
        config=existing.config,
    )

    with pytest.raises(Exception) as refusal:
        init_module._carried_forward(ahead)

    assert "promotion" in str(refusal.value)


def test_a_key_init_cannot_carry_stops_the_run_and_leaves_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US2-S3 end to end, with init's vocabulary narrowed to what it was.

    `_KNOWN_KEYS` is the one constant that says which keys a rewrite can carry;
    narrowing it to `_TOP_LEVEL_KEYS` reproduces init exactly as this epic found
    it — a writer that had never heard of `ladder`. The requirement is that such
    an init *refuses and names the key* rather than writing a manifest without
    it, which is what it did.
    """
    repo = repo_with(tmp_path, CONFIGURED_MANIFEST)
    before = (repo / MANIFEST_NAME).read_bytes()
    monkeypatch.setattr(init_module, "_KNOWN_KEYS", _TOP_LEVEL_KEYS)

    result = interactively(
        repo, monkeypatch, ConfirmingPrompter({"gates": 'test: "make check"'})
    )

    assert result.code == EXIT_USER
    assert (repo / MANIFEST_NAME).read_bytes() == before
    output = result.stdout + result.stderr
    assert "ladder" in output and "verify" in output


# ---------------------------------------------------------------------------
# T012 [US2-S4] the control: absent stays absent where nothing was declared
# ---------------------------------------------------------------------------


def test_a_manifest_written_where_none_existed_declares_no_optional_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US2-S4: "absent" is still the right default for a file that does not exist.

    The control on the ordering fix. Consulting the defaults before returning
    absent must not become inventing a value: a repository that declared nothing
    still gets exactly what it got before this story.
    """
    repo = repo_with(tmp_path, None)

    result = wire_non_interactively(repo, monkeypatch)

    assert result.code == EXIT_OK, result.stderr
    text = (repo / MANIFEST_NAME).read_text(encoding="utf-8")
    document = yaml.safe_load(text)
    # 057/US1: `standards` is no longer omittable into nothing; the other optional
    # keys stay absent when the repository declared none.
    assert document["standards"] == ".specify/memory/constitution.md"
    assert set(document) == {
        "version",
        "runtime",
        "gates",
        "landing_branch",
        "standards",
    }
    for key in init_module._OPTIONAL_KEYS:
        if key == "standards":
            continue
        assert key not in document, f"init invented {key!r} for a repo that declared none"
        assert init_module._init_default(key, repo) is None
    assert init_module._init_default("standards", repo) == ".specify/memory/constitution.md"


# ---------------------------------------------------------------------------
# T013 [US2-S5] comment loss is announced before the write, not after
# ---------------------------------------------------------------------------


def test_the_operator_is_told_before_a_rewrite_discards_comments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US2-S5: told *before* the write, proven at the moment of the write.

    "Before" is asserted by reading what the operator had already been shown
    when `_write_scaffold` was called, rather than by the order two lines happen
    to sit in at the end. A warning printed after the file changed is a report,
    not a warning.
    """
    repo = repo_with(tmp_path, CONFIGURED_MANIFEST)
    seen: list[str] = []
    written = init_module._write_scaffold

    def spy(repo_root: Path, manifest_text: str | None) -> None:
        seen.append(sys.stdout.getvalue())
        return written(repo_root, manifest_text)

    monkeypatch.setattr(init_module, "_write_scaffold", spy)

    result = interactively(
        repo, monkeypatch, ConfirmingPrompter({"gates": 'test: "make check"'})
    )

    assert result.code == EXIT_OK, result.stderr
    assert (repo / MANIFEST_NAME).read_text(encoding="utf-8") != CONFIGURED_MANIFEST
    assert len(seen) == 1
    told = seen[0]
    assert "comment" in told.lower(), (
        "nothing warned the operator before the write; what they had been told "
        f"by then was:\n{told}"
    )
    assert MANIFEST_NAME in told


def test_a_manifest_that_is_kept_warns_about_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control on the warning: US1's keep loses no comment, so it says nothing.

    A warning that fired on every run would be one operators learn to scroll
    past, which is how the next silent loss goes unread.
    """
    repo = repo_with(tmp_path, CONFIGURED_MANIFEST)

    result = wire_non_interactively(repo, monkeypatch)

    assert result.code == EXIT_OK, result.stderr
    assert (repo / MANIFEST_NAME).read_text(encoding="utf-8") == CONFIGURED_MANIFEST
    assert "comment" not in result.stdout.lower()


# ---------------------------------------------------------------------------
# T013a [US2-S6] the remedy the verb recommends is safe to follow
# ---------------------------------------------------------------------------


def test_following_inits_own_guidance_keeps_the_ladder_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US2-S6: the operator does what `_wire`'s "not attempted" line tells them.

    The line reads "re-run with `ergane init --wire`", and `--wire` was the
    command that deleted the block it was helping the operator complete. The
    assertion is the whole loop: run init, read the recommendation off its own
    output, run the recommended command, and find the block still there.
    """
    repo = repo_with(tmp_path, CONFIGURED_MANIFEST)

    first = wire_non_interactively(repo, monkeypatch, wire=False)

    assert first.code == EXIT_OK, first.stderr
    assert "re-run with `ergane init --wire`" in first.stdout

    second = wire_non_interactively(repo, monkeypatch)

    assert second.code == EXIT_OK, second.stderr
    text = (repo / MANIFEST_NAME).read_text(encoding="utf-8")
    assert text == CONFIGURED_MANIFEST
    assert parse_factory_config(text).ladder.max_attempts == 4


# ---------------------------------------------------------------------------
# T013b [US2-S7] the check reports the file, not the edit
# ---------------------------------------------------------------------------


def test_the_check_after_the_re_run_reports_the_manifest_on_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US2-S7: the healthy verdict is about the repository the operator has.

    This is the assertion the loss defeated. It deleted the block, reconciled the
    schedule to what was left, and both sides then agreed — so `--check` called a
    flattened repository healthy and nothing in the loop could tell it from one
    that had never been configured. Three facts have to hold together:

    - the manifest still declares what it declared (`ladder`, and the dial);
    - the schedule the check judges carries the operator's own 900s cadence, not
      `RoadmapDials()`'s default 300 — which is what a stripped manifest would
      have reconciled it to, agreeing with itself all the way;
    - and the check passes, so "healthy" is a claim about that state.
    """
    repo = repo_with(tmp_path, CONFIGURED_MANIFEST)
    floor = FakeScheduleServer()

    result = wire_non_interactively(repo, monkeypatch, schedules=floor)

    assert result.code == EXIT_OK, result.stderr
    kept = parse_factory_config((repo / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert kept.ladder.max_attempts == 4
    assert kept.roadmap is not None and kept.roadmap.cadence_s == 900

    schedule = floor.schedules[init_module.roadmap_schedule.schedule_id_for("app")]
    assert [i.every.total_seconds() for i in schedule.spec.intervals] == [900.0]

    profile = init_module.check_repo(repo)
    finding = next(f for f in profile.findings if f.check == "roadmap_schedule")
    assert finding.passed, finding.detail
    assert [f.check for f in profile.findings if f.blocking] == []


# ---------------------------------------------------------------------------
# T014 [FR-007, trap 6] the refusal fires on the operator's key, never on init's
# ---------------------------------------------------------------------------


def test_inits_own_output_rewrites_without_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Trap 6: write a manifest, then rewrite it, and find no refusal.

    An unrecognised key stops the run, which is right for a key an operator
    added by hand and catastrophic if init's own output round-trips into
    something it does not recognise: every re-run of every joined repository
    would refuse.
    """
    repo = repo_with(tmp_path, None)
    assert wire_non_interactively(repo, monkeypatch).code == EXIT_OK

    written = (repo / MANIFEST_NAME).read_text(encoding="utf-8")
    assert written  # init wrote one; this is the file being fed back in

    # No refusal, and the rewrite is a fixed point: what init writes, init writes
    # again unchanged.
    assert rewritten_non_interactively(repo) == written


# ---------------------------------------------------------------------------
# T015 [FR-005, trap 4] the whole tuple, not the reported member of it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", init_module._OPTIONAL_KEYS)
def test_every_optional_key_carries_forward(tmp_path: Path, key: str) -> None:
    """FR-005: the ordering fix covers `_OPTIONAL_KEYS`, member by member.

    Special-casing `standards` — the key the report named — would leave
    `timeouts`, `roadmap`, `forge`, `writes`, `caches` and `diff_refusal_bytes`
    losing data for whoever finds them next. Parametrised over the tuple itself
    so a key added to it later is covered the day it is added.
    """
    repo = repo_with(tmp_path, EVERY_OPTIONAL_KEY)
    declared = yaml.safe_load(EVERY_OPTIONAL_KEY)
    assert key in declared, "the fixture must declare every optional key"

    assert init_module._init_default(key, repo) == declared[key]

    rewritten = yaml.safe_load(rewritten_non_interactively(repo))
    assert rewritten[key] == declared[key]


def test_a_rewrite_carries_every_declared_key_and_invents_none(tmp_path: Path) -> None:
    """FR-005 whole: the rewrite is the same declaration, not a subset of it.

    Key by key is what catches a partial fix; the set comparison is what catches
    a rewrite that both keeps everything and adds a key nobody asked for.
    """
    repo = repo_with(tmp_path, EVERY_OPTIONAL_KEY)

    rewritten = yaml.safe_load(rewritten_non_interactively(repo))

    assert rewritten == yaml.safe_load(EVERY_OPTIONAL_KEY)


def test_the_comment_reader_finds_prose_and_ignores_a_hash_in_a_value() -> None:
    """FR-009's mechanism: what counts as a comment about to be lost.

    A `#` inside a quoted scalar is part of a gate command, not prose — a reader
    that counted it would warn about losing something no rewrite can lose, and a
    warning that cries wolf is one operators stop reading.
    """
    assert init_module._comment_lines("# why\nversion: 2\n") == ["# why"]
    assert init_module._comment_lines("version: 2  # v2\n") == ["version: 2  # v2"]
    assert init_module._comment_lines('gates:\n  test: "make x#y"\n') == []
    assert init_module._comment_lines(CONFIGURED_MANIFEST)
