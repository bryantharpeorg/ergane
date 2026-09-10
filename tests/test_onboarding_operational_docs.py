"""Onboarding links and live-exercise scope must match their actual sources."""
import ast
from html.parser import HTMLParser
from pathlib import Path
import shlex

import pytest

from factory.cli.landing import halt_after_pass_from_args
from tests.page_holds_true import html_code_spans, parse_argv


ROOT = Path(__file__).resolve().parents[1]


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.targets = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.targets.extend(value for key, value in attrs if key == 'href' and value)


def test_visual_onramp_links_the_full_setup_and_codex_procedure():
    reader = Links()
    reader.feed((ROOT / 'docs/onramp.html').read_text())
    assert {'getting-started.md', 'codex-gateway-setup.md'} <= set(reader.targets)
    for target in reader.targets:
        if '://' in target or target.startswith('#'):
            continue
        path = (ROOT / 'docs' / target.split('#', 1)[0]).resolve()
        assert path.is_relative_to(ROOT), target
        assert path.is_file(), target


def test_live_exercise_documents_its_actual_runner_guard_and_evidence_limit():
    # Read the guard declaration without collecting or running the live test.
    source = ast.parse((ROOT / 'tests/test_live_onramp.py').read_text())
    guards = [ast.literal_eval(node.value) for node in source.body
              if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == 'AGENT_EXECUTABLE'
                      for target in node.targets)]
    assert len(guards) == 1
    guide = (ROOT / 'docs/onramp-exercise.md').read_text()
    assert f'`{guards[0]}` prerequisite' in guide
    assert 'copied persona registry' in guide
    assert 'not a Codex-specific qualification' in guide


def test_onramp_dispatch_examples_parse_with_their_paths_and_halt_flag():
    # The generic prose scanner excludes spans with paths. Read the actual HTML
    # code blocks using its shared HTML reader, then call the real CLI parser.
    phases = {('spec', 'validate'), ('spec', 'derive'),
              ('build', 'ship'), ('build', 'start')}
    observed = {}
    for span in html_code_spans((ROOT / 'docs/onramp.html').read_text()):
        if tuple(span.split()[:3]) not in {('ergane', *phase) for phase in phases}:
            continue
        argv = tuple(shlex.split(span))
        phase = argv[1:3]
        assert phase not in observed, f'duplicate dispatch example: {phase}'
        assert argv[3].startswith('specs/'), argv
        parsed = parse_argv(argv)
        assert parsed is not None
        if phase == ('build', 'ship'):
            assert halt_after_pass_from_args(parsed) is True
            assert '--target-repo' in argv
        if phase == ('build', 'start'):
            assert halt_after_pass_from_args(parsed) is False
            assert argv[3].endswith('/workgraph.json')
        observed[phase] = argv
        # Keep path-bearing examples in scope even when the command is broken.
        with pytest.raises(AssertionError, match='parse failed'):
            parse_argv((*argv, '--nonexistent-onramp-option'))
        with pytest.raises(AssertionError, match='parse failed'):
            parse_argv(argv[:3])
    assert set(observed) == phases
