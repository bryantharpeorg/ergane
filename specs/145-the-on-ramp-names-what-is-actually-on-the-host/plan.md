# Implementation Plan: the on-ramp names what is actually on the host

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**Temporal is a hard requirement of the control plane, and the page is silent.**
`factory/controlplane/config.py:434` — `_read_temporal` opens with
`_expect_block(document, "temporal", source)` at
`factory/controlplane/config.py:437`, and `factory/controlplane/config.py:751` —
`_expect_block` is the refusal:

```python
def _expect_block(
    document: Mapping[str, Any], key: str, source: str
) -> Mapping[str, Any]:
    if key not in document:
        raise ControlPlaneConfigError(
            RULE_MISSING_REQUIRED,
            f"declares no `[{key}]` subsystem block",
            source=source,
            field=key,
        )
```

`README.md` never names it. Measured at `602a92c`: `grep -c -i temporal README.md`
is `0` over all 278 lines, and `git log --all -S"temporal" -i -- README.md`
returns no commits at all — the word has never been on any branch. The
prerequisites section runs from `README.md:17` to `README.md:97`; its two
subsections are `README.md:19` and `README.md:47`.

**Managed mode is live. The comment beside it is not.**
`factory/controlplane/config.py:41-42` still reads:

```python
#: Allowed temporal modes (FR-004).  "managed" is recognized as a token but
#: refused until 042 lands.
KNOWN_TEMPORAL_MODES = ("external", "managed")
```

The rule that comment points at, `factory/controlplane/config.py:69`, has **no
call site anywhere under `factory/`** — `grep -rn RULE_TEMPORAL_MANAGED_NOT_IMPLEMENTED
factory/` returns only its own definition. What actually happens is
`factory/controlplane/config.py:447-450`:

```python
    if mode == "managed":
        # Managed mode installs a local Temporal server under systemd; address
        # and namespace are not operator inputs (FR-009).
        return ControlPlaneConfig.Temporal(mode="managed")
```

The dataclass is `factory/controlplane/config.py:165` — `Temporal`, nested inside
`ControlPlaneConfig`. 119 wired the rest end to end:
`factory/supervision/units.py:344` —
`declared_temporal_mode` reads `temporal.mode` off the operator's config,
`factory/supervision/units.py:371` — `declared_layout` hands it to the resolver,
`factory/supervision/units.py:442` — `_temporal_managed` turns it into a
yes-or-no, and `factory/supervision/units.py:495-497` inserts the
`ergane-temporal.service` unit named at `factory/supervision/units.py:86`.
`ergane worker install` is the verb, at `factory/cli/nouns/worker.py:53`. That is
the second way to have a Temporal server, and README.md may state it as fact.

**And that fact is already provable offline, which is where US1's evidence comes
from.** `factory/supervision/units.py:473` — `generated_files` is the pure half:
given a layout it returns the unit tuple and mutates nothing.
`tests/test_supervision_managed_temporal.py:84` — `managed_layout` builds an
`InstallLayout` with `temporal_mode="managed"` under `tmp_path`, and
`tests/test_supervision_managed_temporal.py:106` —
`test_managed_mode_installs_temporal_unit` asserts `ergane-temporal.service` is
among the names it yields. The impure half is
`factory/supervision/units.py:946` — `install`, which writes files, runs
`systemctl --user daemon-reload`, `loginctl enable-linger` and
`systemctl --user enable --now` for every name in
`factory/supervision/units.py:131` — and which
`factory/cli/nouns/worker.py:32` — `_require_systemd_user_session` refuses
outright where there is no user bus. That verb has no dry run
(`grep -n 'dry.run' factory/cli/nouns/worker.py` returns nothing), so it belongs
to the operator's own sequence below and to no node.

**The README's guard is a four-part contract.** `tests/test_readme.py:199-207` is
the concept table; `tests/test_readme.py:210` — `missing_readme_concepts` is the
checker, and it reads two slices cut by `tests/test_readme.py:171` —
`_section_between`, one of them `"## What you must already have"` up to
`"## Installing Ergane"`. `tests/test_readme.py:189` — `_lower_words` tokenizes
with `[a-z0-9]+(?:[/-][a-z0-9]+)*`, so `temporal.mode` becomes the two tokens
`temporal` and `mode`. `tests/test_readme.py:301` — `_mutations` supplies the
deliberately-broken copies and `tests/test_readme.py:387` —
`test_missing_concept_is_detected` sweeps them; `tests/test_readme.py:396` —
`test_reworded_equivalent_page_passes` proves the guards are not keyed to one
literal string. The module docstring says why all four exist: "A test that only
asserts the sentence is present today would pass forever on a page nobody edits."

**The page also asserts its own citations, and its own silence about status.**
`tests/test_readme.py:107` —
`test_every_path_the_file_cites_exists` resolves every span
`tests/page_holds_true.py:388` — `extract_paths` finds against the repository
root, skipping only spans that start with `/`. `tests/page_holds_true.py:301` —
`extract_commands` extracts every command-shaped span whose first word is
`ergane` and parses it, and `tests/page_holds_true.py:258` —
`_is_command_shaped` excludes any span containing `=` or `/`. The third sweep is
`tests/test_readme.py:140` — `test_the_file_names_no_spec_status`, which runs
`tests/page_holds_true.py:430` — `status_claims` over the page and refuses any
spec identifier — the pattern admits a bare `0dd`, so `042` is one — that sits
within eighty characters of a status word such as `landed`.

Two further page-level guards live in that module and are named here only so the
count is honest — new prerequisite prose cannot plausibly trip either:
`tests/test_readme.py:123` — `test_the_file_contains_no_secret_value` and
`tests/test_readme.py:156` — `test_the_file_names_no_spend_figure`. That is FIVE
page-level guards in `tests/test_readme.py`, not three. A sixth assertion over
the same page lives in a different module altogether —
`tests/test_113_us2_docs_drift.py:91` —
`test_readme_procedure_matches_shipped_profile` — and it is the only `README.md`
guard nothing else in this plan points at. It is trap 16, and it constrains
where the new prose may put a fenced block.

**The requirements verb refuses twice, with the same two defects on both
branches.** `factory/cli/nouns/install.py:62` — `_requirements_command` has a
no-aliases branch at `factory/cli/nouns/install.py:89-97` and an all-example
branch at `factory/cli/nouns/install.py:101-108`. The second reads:

```python
    if all(is_example_alias(alias) for alias in alias_to_personas):
        registry_path = resolve_default_registry_path()
        raise OperatorError(
            f"persona registry has not been configured yet: "
            f"edit {registry_path} and replace the example/ placeholder aliases; "
            f"the registry is resolved from "
            f"{ERGANE_PERSONAS_PATH_ENV}, then {FACTORY_PERSONAS_PATH_ENV}, then "
            f"$XDG_CONFIG_HOME/{DEFAULT_REGISTRY_REL} (or ~/.config/ergane/{DEFAULT_REGISTRY_REL}), then the packaged default",
            code=EXIT_USER,
        ) from None
```

`factory/config.py:47` is `DEFAULT_REGISTRY_REL = Path("ergane") / REGISTRY_FILENAME`,
so the tilde spelling on `factory/cli/nouns/install.py:106` — and identically on
`factory/cli/nouns/install.py:95` — renders `~/.config/ergane/ergane/personas.yaml`.
`grep -rn 'config/ergane/{' factory/` returns exactly those two lines and nothing
else, so the doubled path is only ever those two. The value `registry_path`
comes from `factory/config.py:111` —
`resolve_default_registry_path`, whose XDG default is built at
`factory/config.py:124` and whose final fall-through at `factory/config.py:132-134`
returns `factory/config.py:81` — `_resolve_default_registry_path`, the copy
packaged inside the distribution.

**The two branches share a line, and it is not the one you would grep for.**
Measured at `602a92c`,
`grep -rn 'replace the example/ placeholder aliases' factory/` returns **two**
lines, not three: `factory/cli/nouns/install.py:103`, the all-example branch
quoted above, and `factory/controlplane/verify.py:462-463`, which is the doctor's
LLM probe building an `LLMSnapshot` detail — a different verb with a different
reader, printing no resolution order at all, and out of scope; see trap 6. The
no-aliases branch does **not** carry that phrase:
`factory/cli/nouns/install.py:92` reads
"edit {registry_path} and declare at least one persona with a gateway model
alias". What the two branches genuinely share, byte for byte, is the
resolution-order line — `factory/cli/nouns/install.py:95` and
`factory/cli/nouns/install.py:106`, the only two hits of
`grep -rn 'config/ergane/{' factory/` — and that shared line is where the doubled
path lives. So a grep for the message wording finds ONE of the two branches this
story edits, plus one file it must not touch.

**The landed refusal that must survive** is
`tests/test_ergane_install_requirements.py:240` —
`test_requirements_with_example_registry_prints_configuration_guidance`, whose
assertion at `tests/test_ergane_install_requirements.py:269` is `assert code != 0,
"an unconfigured registry must refuse, not print empty requirements"` and which
then requires the three env names and the resolved path in the output.

**The scanner folds every non-200 into unreachable.**
`factory/discovery/llm_scanner.py:90` — `_probe_one` succeeds at
`factory/discovery/llm_scanner.py:106` and otherwise returns, at
`factory/discovery/llm_scanner.py:118-125`:

```python
    else:
        return ScanResult(
            address=address,
            reachable=False,
            aliases=(),
            classification=None,
            detail=f"{_MODELS_PATH} answered {models_response.status_code}",
        )
```

The second probe, `factory/discovery/llm_scanner.py:127-131`, has a similar shape
but a different consequence — by the time it runs `/v1/models` has already
answered 200, so its `except` leaves the endpoint reachable and inference-only,
not unreachable:

```python
    # A second, still-unauthenticated probe decides dispatchability.
    has_key_management = False
    try:
        key_response = await client.post(f"{base}{_KEY_GENERATE_PATH}")
        has_key_management = key_response.status_code == 200
    except httpx.HTTPError:
        has_key_management = False
```

and the classification follows at `factory/discovery/llm_scanner.py:135-143`.
The two members live at `factory/discovery/llm_scanner.py:23-24` on
`factory/discovery/llm_scanner.py:20` — `EndpointClassification`; the default
candidates, in the order they are probed, at
`factory/discovery/llm_scanner.py:40-43`. The public entry is
`factory/discovery/llm_scanner.py:64` — `scan_endpoints`, whose signature closes
at `factory/discovery/llm_scanner.py:69` with **no key parameter**, and whose
docstring states the terms at `factory/discovery/llm_scanner.py:74-75`: "The scan
is unauthenticated: no API key is attached to any probe request."

**What reads a classification.** `grep -rn EndpointClassification factory/`
returns five call sites outside the scanner itself.
`factory/discovery/llm_scanner.py:154` —
`render_scan_results` prints `result.classification.value`, so the new member's
value is operator-visible text. `factory/controlplane/verify.py:634` constructs
`INFERENCE_ONLY` for its own message and is not this spec's business — but a
landed *test* over that module asserts the enum's exact membership, which is trap
14 and the one thing in US3 that reaches outside the two production files.
`factory/cli/install.py:277` binds `_scan_endpoints = scan_endpoints` as the
interview's seam, `factory/cli/install.py:2132` — `_llm_scan` picks the
candidate, `factory/cli/install.py:2149` — `_offered_llm_mode` turns it into an
offer (`factory/cli/install.py:2185-2193` is the inference-only tail), and
`factory/cli/install.py:1545` — `_ask_llm` asks with `default=offered.mode` at
`factory/cli/install.py:1560`.

**The offline ways to drive both seams, and which fake is actually live.** There
is exactly ONE working fake transport for the scanner:
`tests/test_llm_discovery.py:38` — `FakeTransport`, built by the factory at
`tests/test_llm_discovery.py:103-111`, taking exactly `models`, `key_generate` (a
bool per address) and `dead` — it cannot express a status code at all. That is
the one US3-S1, US3-S2, US3-S3 and US3-S6 extend.
`tests/test_install_mode_routing.py:53` — `FakeTransport` looks like a second
one and is **dead code in its own module**: `grep -n FakeTransport
tests/test_install_mode_routing.py` returns only that line. The interview tests
do not use a transport at all. They go through
`tests/test_install_mode_routing.py:111` — `_run_with_scan_result`, which
monkeypatches `install_module._scan_endpoints` with a `_fake_scan` that ignores
the transport and returns `[result]` — a LIST with exactly one element. So
US3-S4's "inference-only first, secured gateway second" is expressed by making
that helper return a two-element list in that order, not by building a transport.
`tests/test_install_mode_routing.py:174` —
`test_dispatchable_scan_offers_gateway_with_address_defaulted` and
`tests/test_install_mode_routing.py:200` —
`test_inference_only_scan_offers_direct_and_names_missing_capability` are the
shapes to copy for US3-S4 and the first half of US3-S5;
`tests/test_install_mode_routing.py:306` —
`test_operator_declared_address_overrides_scan_result` is the shape for the
re-run half.

**The parser-level test module for US1-S5** is `tests/test_controlplane_config.py`,
where `tests/test_controlplane_config.py:122` — `test_happy_parse` is the shape.
Measured at `602a92c` that module contains no occurrence of `managed`, so the
assertion is new *there*. It is not new to the tree:
`tests/test_supervision_managed_temporal.py:131` —
`test_temporal_managed_mode_parses_without_refusal` already asserts
`cfg.temporal.mode == "managed"`, as 119's own proof that the parse-time refusal
is gone. Write it anyway, in the parser's own module: FR-005's point is that the
comment being corrected and the behaviour it describes are pinned in one place,
and a supervision module is not that place. Do not delete or move 119's test.

## Traps

**Trap 1 — The README guard is FOUR edits, and three of them are invisible to a
green suite.** FR-003. Adding the sentence and one presence assertion leaves
`tests/test_readme.py:291` — `test_the_page_states_all_required_concepts`
green forever on a page nobody edits, which is the exact failure the module
docstring says the mutation tests exist to prevent. All four are required: a name
in `tests/test_readme.py:199-207`, a check inside `tests/test_readme.py:210` —
`missing_readme_concepts`, a mutation in `tests/test_readme.py:301` —
`_mutations`, and a rewording inside `tests/test_readme.py:396` —
`test_reworded_equivalent_page_passes`. The rewording is the one an implementer
skips, and it is the one that stops the guard being a literal-string match.

**Trap 2 — The sentence must land inside the prerequisites section or the guard
cannot see it.** FR-001. `tests/test_readme.py:171` — `_section_between` cuts
`"## What you must already have"` up to `"## Installing Ergane"` and the checks
run over that slice's tokens. A Temporal paragraph added under
`"## Configuring the control plane"` (`README.md:135`) reads perfectly to a human
and is invisible to `missing_readme_concepts`, so the mutation test fails for a
reason that looks like a broken guard. Note that `README.md:97` is the
`## Installing Ergane` heading itself — the closing *boundary*, not a line to
insert on; the prose belongs above it. And `tests/test_readme.py:189` —
`_lower_words` tokenizes on `[a-z0-9]+(?:[/-][a-z0-9]+)*`, so `temporal.mode` is
never one token: a required set written as `{"temporal.mode"}` can never match.
Use `{"temporal", "server"}`-shaped sets, as the seven existing checks do.

**Trap 3 — A backticked `~/.config/...` path fails README.md's own suite, and so
does naming a spec beside a status word.**
FR-004. `tests/page_holds_true.py:388` — `extract_paths` keeps any backticked
span that contains `/`, skipping only spans that begin with `/`, and
`tests/test_readme.py:107` — `test_every_path_the_file_cites_exists` then
resolves it against the repository root. `README.md` cites no `~/.config` path
today, which is why nobody has hit this. Name the config file in prose, or cite a
path that is in the tree. The sibling rule is safer than it looks, and the whole
predicate matters — `tests/page_holds_true.py:258` — `_is_command_shaped` keeps a
span only when it is non-empty, does **not** start with `-`, splits into **at
least two** whitespace-separated words, and — with those words joined —
contains none of `/`, `=` or `.` (the three-way test is
`tests/page_holds_true.py:278`). So `` `temporal.mode = "managed"` `` is excluded
three times over (a `.`, an `=`, and no leading entrypoint), a one-word span like
`` `personas.yaml` `` is excluded twice, and `` `ergane worker install` `` **is**
command-shaped and must parse. Reason from all four clauses, not from the `=`
and `/` half: a span you expect to be ignored because it has a dot is ignored for
that reason, and a two-word span with none of the three characters is extracted
whether you meant it as a command or not. The third sweep is the one
an implementer trips *because* they read trap 4: the single most natural sentence
after learning managed mode is live is "managed mode landed with 042", and
`tests/test_readme.py:140` — `test_the_file_names_no_spec_status` refuses it,
because a bare `042` is a spec identifier and `landed` is a status word inside its
eighty-character window. State what managed mode **does**, never when it arrived,
and name no spec number on the page at all.

**Trap 4 — The tree's own comment will tell you the opposite of the truth.**
FR-005. `factory/controlplane/config.py:41-42` says `managed` is "refused until
042 lands". It is not refused: `factory/controlplane/config.py:447-450` accepts
it and 119 wired the whole path. The wrong move is to read that comment, believe
it, and write a README sentence saying managed Temporal is not implemented yet —
which makes the page newly false and passes every guard in this spec, because the
guards check that the concept is *stated*, not that it is *true*. Correct the
comment in the same diff. Do **not** delete
`factory/controlplane/config.py:69`: it is a stable rule slug named in
`docs/decisions.md`, and removing it is a wider act than this story.

**Trap 5 — There is a stale transcript that will look like a contradiction, and
it is not yours to fix.** `tests/test_ergane_install_walkthrough.py:137` still
shows `[temporal_managed_not_implemented] ... it arrives with epic 042` — inside
a `.. code-block:: text` in the module docstring, which the file itself labels
"This transcript is from the 033 tree. One line of it has since gone stale". It
is prose, not an assertion, and nothing runs it. Chasing it grows the diff
without changing behaviour and drags US1 into a module it has no business in.

**Trap 6 — The doubled path is on TWO lines, the landed test drives only one
branch, and a THIRD copy of the wording is not yours.** FR-006, FR-007.
`factory/cli/nouns/install.py:95` sits in the no-aliases
branch and `factory/cli/nouns/install.py:106` in the all-example branch; the two
strings are identical and the conditions that reach them are not.
`tests/test_ergane_install_requirements.py:240` —
`test_requirements_with_example_registry_prints_configuration_guidance` writes a
registry whose aliases are all `example/`, so it reaches only the second. A fix
on one line, tested through that branch, is green and half-done — and the
no-aliases branch is the one a genuinely empty registry hits. The other half of
this trap fires when an implementer greps the message string instead of reading
the function. `grep -rn 'replace the example/ placeholder aliases' factory/`
returns **two** hits, and neither pair is the pair you want: the first is the
all-example branch here, and the second is
`factory/controlplane/verify.py:462-463`, the doctor's LLM probe, not the
requirements verb. The no-aliases branch is invisible to that grep because it
says something else — `factory/cli/nouns/install.py:92` reads "declare at least
one persona with a gateway model alias". So greping the wording finds one branch
in scope and one file out of it, and silently misses the second branch FR-006 and
FR-007 both bind. Read `_requirements_command` top to bottom instead, or grep the
line the two branches really share: `grep -rn 'config/ergane/{' factory/` returns
exactly `factory/cli/nouns/install.py:95` and `factory/cli/nouns/install.py:106`,
which is where FR-007's doubled path lives and nowhere else. Leave
`factory/controlplane/verify.py` out of this diff entirely; changing it makes US2
a two-module story for no reader's benefit.

**Trap 7 — Do NOT make the verb print instead of refusing.** FR-008. The ledger
row for this key asks for exactly that ("the verb knows the requirements and
refuses anyway; printing them is strictly more useful"), and it is out of scope:
063-US3 landed the refusal as an acceptance criterion and
`tests/test_ergane_install_requirements.py:240` asserts
`code != 0` with the message "an unconfigured registry must refuse, not print
empty requirements". Printing `example/your-architect-model` as a gateway
requirement would be a new lie in place of the old one. No hunk of the diff may
modify that test; if you find yourself editing it, the design is wrong.

**Trap 8 — The override path needs a public name, and the two obvious reaches
are private.** FR-006. The message must name a path the operator can create, and
`factory/config.py:104` — `_xdg_config_home` and `factory/config.py:81` —
`_resolve_default_registry_path` are both private to `factory/config.py`;
importing either into `factory/cli/nouns/install.py` couples the CLI to the
resolver's internals and will drift. The value wanted is the one
`factory/config.py:111` — `resolve_default_registry_path` computes at
`factory/config.py:124` as `default`. Export one public helper beside it and
import that. Whatever is chosen, the refusal must name the resolved registry as
what is being **read** and the override as what to **create** — the two are
different paths on a wheel install and the same path in a checkout, and the
message must be true in both.

And that last sentence is also the trap in US2-S1's *fixture*. A test that merely
clears `ERGANE_PERSONAS_PATH` and `FACTORY_PERSONAS_PATH` and points
`XDG_CONFIG_HOME` at a `tmp_path` does **not** reach the packaged copy in this
repository: there is no `factory/personas.yaml` in a checkout — `pyproject.toml`
force-includes `personas.example.yaml` to that name only at wheel build time — so
`factory/config.py:81` — `_resolve_default_registry_path` falls through to
`parents[1] / "personas.yaml"`, which is the operator's own 26 KiB **configured**
registry at the repository root. `gather_gateway_aliases` then returns a full
mapping, no `example/` alias is present, and the verb exits **zero** with a
requirements listing. The route that reaches US2-S1's Given is to rebind
`factory/config.py:81` — `_resolve_default_registry_path` to an example registry
written under `tmp_path`; it is looked up as a module global by
`factory/config.py:111` — `resolve_default_registry_path`, so
`monkeypatch.setattr` on `factory.config` is enough and the CLI's own
function-body import still sees it.

**Trap 9 — There is ONE live `FakeTransport`, and it cannot answer 401.**
FR-009, FR-010. `tests/test_llm_discovery.py:38` — `FakeTransport` takes
`models`, `key_generate` (a bool) and `dead`, and its factory
`tests/test_llm_discovery.py:103-111` forwards exactly those three kwargs, so a
status dimension must be threaded through both or every existing call site
breaks. That is the fake to extend, and `httpx.Response(401)` through the
existing seam is all the new dimension has to produce. Do **not** extend
`tests/test_install_mode_routing.py:53` — `FakeTransport`: it has zero call sites
in its own module and the interview tests never reach it, so widening it would
land a change no test exercises while the story's own scenarios stayed red. The
interview seam is `tests/test_install_mode_routing.py:111` —
`_run_with_scan_result`, which monkeypatches `_scan_endpoints` and ignores
transports entirely.

**Trap 10 — A new enum member is operator-visible text and changes a rendered
line.** FR-009. `factory/discovery/llm_scanner.py:154` — `render_scan_results`
prints `result.classification.value`, so the member's *value* is what an operator
reads, and its tail line "The scan found no reachable LLM endpoint" is guarded by
`if not any(r.reachable for r in results)` — which stops firing once a secured
gateway counts as reachable. That is the intent, and
`tests/test_llm_discovery.py:206` — `test_scan_finding_nothing_reports_plainly`
stays green because it drives a wholly dead host, but a new test that asserts
that tail on a 401 host is asserting the bug.

**Trap 11 — Fixing the scanner alone can make US3-S4 pass for the wrong reason.**
FR-012, FR-013. `factory/discovery/llm_scanner.py:40-43` probes
the LiteLLM port on loopback **before** the Ollama port, and
`factory/cli/install.py:2132` — `_llm_scan` returns the first *reachable*
result in candidate order once no dispatchable one exists. So on the default pair
the secured gateway would be chosen by position, not by preference, and a
scenario written with the gateway first proves nothing about FR-012. Write the
test with the inference-only endpoint FIRST in the result list. And note that
the scanner change alone still lands the operator in `direct`:
`factory/cli/install.py:2149` — `_offered_llm_mode` only branches on
`DISPATCHABLE` at `factory/cli/install.py:2173` and falls through to the
inference-only tail at `factory/cli/install.py:2185-2193` for everything else, so
an authentication-required result would be offered as `direct` with the
gateway's address — a subtler wrong answer than today's.

**Trap 12 — `blank_host` is not "no `llm` block", and it is not "`{"llm": {}}`
either".** FR-013. Read the two lines before you write a fixture.
`factory/cli/install.py:2161` is
`existing_mode = document.get("llm", {}).get("mode")` and
`factory/cli/install.py:2166` is
`blank_host = existing_mode is None or document.get("llm") == BLANK_DOCUMENT["llm"]`.
Evaluate that on `{"llm": {}}`: `existing_mode` is `None`, the FIRST disjunct
short-circuits, and the document **is** a blank host. The trap runs the other
way. A *real* blank host is seeded from `factory/cli/install.py:242-249`, whose
`llm.mode` is already `"gateway"`, so `existing_mode is None` is false there and
blank-host detection rests entirely on the dict-equality half — which means any
fixture that has touched even one field of the seeded `llm` block before
`_offered_llm_mode` runs is silently read as a **re-run**, the existing mode
wins, and the scan is ignored. So: seed the blank-host fixture exactly the way
the interview does, or the new offer never runs and the red looks like the
production change failing.

For the re-run control in US3-S5, declare a real mode rather than emptying the
block — and do **not** model it on `tests/test_install_mode_routing.py:306` —
`test_operator_declared_address_overrides_scan_result`, which is the obvious
reach and controls nothing here. That test declares nothing in the document: its
walkthrough starts from a blank host and it drives the operator's typed
*answers*, asserting a typed address beats the scanned default. It never reaches
`_offered_llm_mode`'s re-run branch at `factory/cli/install.py:2161` and
`factory/cli/install.py:2166` at all. The harness that does seed an existing file
is `tests/test_ergane_install_walkthrough.py:644` —
`test_rerun_offers_the_existing_file_as_defaults_and_touches_only_telemetry`, and
the cheapest proof of all is to call `factory/cli/install.py:2149` —
`_offered_llm_mode` directly with a document whose `llm` block differs from
`BLANK_DOCUMENT["llm"]` and whose `llm.mode` is `"direct"`. Drive that half with
an **authentication-required** result, never an inference-only one: an
inference-only result falls through to the tail at
`factory/cli/install.py:2185-2193`, which this story does not touch, so a re-run
control written with it would pass over an implementation that copied the
dispatchable branch and dropped its `if blank_host or existing_mode != "direct"`
guard at `factory/cli/install.py:2176` — flipping an operator who chose `direct`
to `gateway` on every re-run, with all six US3 scenarios green.

**Trap 13 — Do not make any probe carry a credential.** FR-014.
`factory/discovery/llm_scanner.py:64` — `scan_endpoints` closes its signature at
`factory/discovery/llm_scanner.py:69` with no key parameter, and its docstring at
`factory/discovery/llm_scanner.py:74-75` states why. The ledger row's own
suggested remedy asks for a credential so the scan can "finish the job"; that
contradicts 055 FR-003/SC-002 and its committed control
`tests/test_llm_discovery.py:159` — `test_scan_sends_no_authorization_header`.
The whole point of the new classification is that "something is here and it wants
a credential" is a useful answer that costs nothing to learn. Widen that test's
fixture; do not weaken its assertion.

**Trap 14 — A landed test asserts the enum has exactly two members, and it is in
a module this plan otherwise tells you to stay out of.** FR-009.
`tests/test_controlplane_verify_us1.py:484` —
`test_llm_verify_imports_classification_from_scanner` ends with
`assert {e.name for e in EndpointClassification} == {"DISPATCHABLE",
"INFERENCE_ONLY"}`. The third member turns it red on the first production line
US3 writes, and nothing else in this spec points at that file. That test's
subject is 055 US1-S4 — that `verify.py` **imports** the enum rather than
redefining it — so the repair is to widen the expected set to include the new
member and leave the two `is` identity assertions above it exactly as they are.
Do not delete the assertion: deleting it silently drops 055's import-reuse
control. Do not edit `factory/controlplane/verify.py` itself; the production
module needs no change, and `factory/controlplane/verify.py:634` constructing
`INFERENCE_ONLY` for its own message is still correct after this spec.

**Trap 15 — An empty registry file does NOT reach the no-aliases branch.**
FR-006, FR-007. The obvious way to drive `factory/cli/nouns/install.py:88` —
`if not alias_to_personas` is to point `ERGANE_PERSONAS_PATH` at an empty file.
It lands somewhere else entirely: `factory/config.py:219` — `load_personas`
refuses an empty document at `factory/config.py:242-246` with "persona registry
… must be a non-empty mapping of persona name to persona fields", and
`factory/cli/nouns/install.py:79-81` catches that and re-raises it at
`factory/cli/nouns/install.py:82-85` as `cannot load persona registry:
ConfigError: …` — a message with no resolution order, no tilde path and no
create-not-edit wording, so a test asserting any of FR-006's or FR-007's
properties against it asserts against output that cannot exist. The route that
does reach the no-aliases branch is a registry that **loads** and yields no
gateway alias: personas declared `agent: subscription` or `agent: none`, because
`factory/config.py:203` — `routes_through_gateway` is False for both and
`factory/controlplane/verify.py:400` — `gather_gateway_aliases` skips them,
returning `{}`. The fixture at
`tests/test_ergane_install_requirements.py:84` — `fixture_registry_path` already
declares one of each; a registry holding only those two is the one-line change.

**Trap 16 — a fenced `bash` block in the prerequisites section turns a landed
test red in a module nothing else in this spec names.** FR-004.
`tests/test_113_us2_docs_drift.py:53` — `_extract_readme_procedure` searches
`README.md` for the FIRST fenced block whose info string is `bash` — the regex is
non-greedy and `re.DOTALL`, so it takes the first opening marker and the next
closing one — and returns the **empty string** unless that block contains both
`printf` and `apparmor_parser`. `tests/test_113_us2_docs_drift.py:91` —
`test_readme_procedure_matches_shipped_profile` then asserts the extraction is
non-empty, with the message "could not extract profile procedure from README.md",
and compares it line for line against `container/ergane-bwrap.apparmor`. Today
the page's first such block is the AppArmor one at `README.md:83`, closing at
`README.md:92` — and it sits INSIDE the section trap 2 orders you to write into
(`README.md:17` to `README.md:97`). Measured at `602a92c`: inserting a
`### A Temporal server` subsection carrying a `bash` fence after the bullets that
end at `README.md:71` flips the extractor from a match to the empty string. The
wrong move is the natural one — showing `ergane worker install` as a fenced
example above `README.md:83` — and what it produces is a red declared `test` gate
whose failure message names the AppArmor profile rather than the paragraph that
caused it, whereupon the tempting repair is to edit a landed acceptance control
in another module. That is the failure trap 14 exists to prevent for US3,
arriving in US1. Three right moves: name the verb in inline backticks the way
`README.md:70` already does, or open the fence with `toml` (the regex matches
only `bash`), or put a `bash` fence **below** `README.md:92`, after the AppArmor
block. `tests/test_113_us2_docs_drift.py` itself takes no hunk of this diff. Its
name is a misnomer worth knowing — it landed as 111's US2, in `eda14ed` on
2026-08-29 — so looking for it under a spec directory numbered 113 finds nothing.

## Sizing

US1 touches `README.md` (one subsection under an existing heading),
`tests/test_readme.py` (four small edits in three places) and one comment in
`factory/controlplane/config.py`, plus one new parser assertion in
`tests/test_controlplane_config.py`. Two further modules appear in US1's slice
only as files it may not write: `tests/test_113_us2_docs_drift.py`, which asserts
over the same page from outside this plan and constrains where the new prose may
put a fenced block (trap 16), and `tests/test_ergane_install_walkthrough.py`,
whose stale transcript at `tests/test_ergane_install_walkthrough.py:137` is not
US1's to chase (trap 5).

US2 touches `factory/cli/nouns/install.py` (two message strings) and
`factory/config.py` (one exported helper), plus new assertions in
`tests/test_ergane_install_requirements.py` — with the landed
`tests/test_ergane_install_requirements.py:240` —
`test_requirements_with_example_registry_prints_configuration_guidance` left
byte-identical.

US3 touches `factory/discovery/llm_scanner.py` (one enum member, one branch in
`_probe_one`) and `factory/cli/install.py` (the preference order in `_llm_scan`
and one branch in `_offered_llm_mode`), plus `tests/test_llm_discovery.py`,
`tests/test_install_mode_routing.py`, and one widened assertion line in
`tests/test_controlplane_verify_us1.py` (trap 14) — a test-only file, no
production module beyond the two named. US3 **reads**
`tests/test_ergane_install_walkthrough.py:644` for the shape of a re-run harness
and writes no hunk into that module, which is why US3 may declare
`concurrent_with: [US1]` against the file US1 also names, at
`tests/test_ergane_install_walkthrough.py:137`, and also only as a prohibition
(trap 5).

The three stories name no production file in common. The near miss worth stating
once more: `factory/cli/nouns/install.py` (US2) and `factory/cli/install.py`
(US3) are two different modules — the CLI noun and the interview — and neither
story may edit the other's.

All three are well inside the 64 KiB deterministic diff bound (D-050): each is
under a hundred production lines, and the pasted evidence each verification task
asks for is one short command transcript, not a suite log.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only, so
runtime evidence must be committed as pasted output. Everything in this list
needs a real host, a real systemd session or a real proxy, which is why none of
it is a node's task:

1. Read `README.md`'s prerequisites section and confirm a stranger could satisfy
   it: that a Temporal server is named as required, and that both
   `temporal.mode = "external"` and `temporal.mode = "managed"` are named with
   the verb that realises each.
2. On a host declaring `temporal.mode = "managed"`, run `ergane worker install`
   and confirm `ergane-temporal.service` is among the units written — the claim
   US1's prose makes, run forwards. This step, and only this step, actually
   writes units and starts services; `factory/supervision/units.py:946` —
   `install` runs `systemctl --user enable --now`, so it belongs to the operator
   on a host they own and to no attempt in a worktree.
3. Under a fresh `HOME` with no `~/.config/ergane/personas.yaml`, run
   `ergane install --requirements` from an installed wheel and read the refusal:
   it must name the packaged registry as what is being read, name a path to
   create, print `~/.config/ergane/personas.yaml` with one `ergane/` segment, and
   still exit non-zero.
4. Repeat step 3 with `ERGANE_PERSONAS_PATH` pointing at a registry whose
   personas are all `agent: subscription` or `agent: none` — **not** an empty
   file, which is refused earlier and never reaches this branch (trap 15) — and
   confirm the same three properties. This is the branch trap 6 exists for and no
   committed test drove it before this spec.
5. Put a master key on a local LiteLLM proxy so it answers 401 unauthenticated,
   leave an Ollama running on the other default loopback candidate, and run
   `ergane install --scan`.
   The gateway must report as reachable and authentication-required, not as down.
6. With that same pair up, run `ergane install` on a host with no prior
   declaration and press Enter at the first question. The offered mode must be
   `gateway` and the defaulted address the proxy's, not Ollama's.

Step 6 is the falsifiable test of the whole spec: it is a stranger's first hour,
run forwards, on the host the hand-over was written from.
