---
state: draft
fixes:
  - docs/readme-prerequisites-omit-the-temporal-server-entirely
  - install/the-requirements-verb-refuses-on-a-fresh-install-and-names-the-wrong-file
  - install/the-scanner-classifies-a-properly-secured-gateway-as-unreachable
# DRAFTED 2026-09-04 by the refinement workflow (refinement-2026-09-04) from
# docs/triage-2026-09-03-ergane-web-round3.md § "the-on-ramp-names-what-is-actually-on-the-host"
# (lines 275-293), against ergane-buildout at 602a92c. Every `file:line` in
# spec.md and plan.md was read from that commit with `sed -n Np` and verified to
# resolve to the symbol named, not recalled.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), still against 602a92c, after an
# adversarial review refuted the trio. Two blocking defects and six minor ones,
# by class: (1) a NEIGHBOUR LANDED that the draft never named — 055-US1's
# committed `assert {e.name for e in EndpointClassification} == {"DISPATCHABLE",
# "INFERENCE_ONLY"}` goes red the moment US3 adds its third member, so FR-009 now
# names the widening, plan.md carries trap 14 and tasks.md a task for it, and the
# file is in § Sizing; (2) an INSTRUCTION WRONG in tasks.md T008, which asked a
# node for the transcript of a verb that writes systemd units and starts services
# on the operator's live host — rewritten to evidence producible inside the
# worktree, with the real run left where plan.md already had it, as operator
# step 2; (3) an INSTRUCTION WRONG in plan.md trap 12, whose worked example was
# the inverse of `factory/cli/install.py:2166` — restated on the true mechanism
# and corrected in T019 too; (4) three anchor-accuracy corrections — the dead
# second `FakeTransport`, the `Temporal` cite put into symbol form, and a third
# copy of the requirements wording named as out of scope; (5) two criteria made
# readable from a diff — FR-008/US2-S3 phrased as "no hunk modifies" rather than
# "appears unmodified", and FR-011 scoped to the probe it means; (6) house-rule
# `[P]` markers dropped where three Phase-3 tasks share one fixture. Because
# (1) and (4) put `factory/controlplane/verify.py` in both US2's and US3's task
# slices — in each case only as a prohibition, never as a hunk — US3 now declares
# `concurrent_with: [US2]` to override the inferred contention edge that would
# otherwise serialise two stories that cannot collide. No key added or removed;
# no hold reversed; state stays draft.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): a second adversarial review, still
# against 602a92c. One blocking defect per lens and five minor ones, by class.
# (1) INSTRUCTION WRONG in tasks.md T026, which asked the US3 node for the
# transcript of a scan against a real master-keyed LiteLLM proxy and of a real
# interactive interview — the two runs plan.md's own preamble says are "none of
# it is a node's task" — rewritten to evidence producible inside the worktree
# exactly as T008 already was, with the real runs left as operator steps 5 and 6.
# (2) INSTRUCTION WRONG in plan.md step 4, T010 and T015, which reached the
# no-aliases refusal with "an empty registry file": an empty file is refused
# earlier, by `factory/config.py:219` — `load_personas` at
# `factory/config.py:242-246`, and surfaces as the load-failure refusal at
# `factory/cli/nouns/install.py:82-85`, which carries no resolution order and no
# tilde path at all. Replaced everywhere with a registry whose personas are all
# subscription or deterministic, and plan.md gained trap 15 for the wrong branch.
# (3) Three anchor-accuracy corrections: the "three copies" grep is TWO hits and
# the genuine twin is the resolution-order line, `_is_command_shaped` is now
# quoted in full, and US1-S4 names `test_every_command_the_file_names_parses`
# beside the path sweep it was wrongly crediting. (4) Two criteria made
# unfakeable: US2-S1's Given names the route that actually reaches the packaged
# copy, because a checkout has no `factory/personas.yaml` and the resolver would
# otherwise hand back the repository's own configured registry and exit zero; and
# US3-S5's re-run half is driven with an AUTHENTICATION-REQUIRED result, so
# FR-013's third clause exercises the guard on the branch US3 adds rather than one
# it never reaches. (5) T004 and US1-S5's test half labelled the control they are.
# DECLINED, with evidence: rewriting six constant citations into the
# `path.py:NN` — `symbol` form. `factory/cli/nouns/spec.py:825` — `_symbol_spans`
# maps only `FunctionDef`, `AsyncFunctionDef` and `ClassDef` names, so a module
# constant or a local has no span, `_line_hits_symbol` answers "absent", and the
# tier would REFUSE this draft rather than check it — confirmed by parsing all
# six with `ast`. One consequence of (2): T020's new pointer puts
# `tests/test_ergane_install_walkthrough.py` in US3's slice beside US1's, in both
# cases only as a file neither story may write, so US3's `concurrent_with` widens
# to `[US1, US2]` and the Work Graph prose states both prohibitions. No key added
# or removed; no hold reversed; state stays draft.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): a third adversarial review, still
# against 602a92c. One blocking defect and four minor ones, by class.
# (1) NEIGHBOUR LANDED that no file in the trio named. `eda14ed` (2026-08-29,
# 111-the-demo-sandbox-starts-or-says-why/us2) landed
# `tests/test_113_us2_docs_drift.py:91` —
# `test_readme_procedure_matches_shipped_profile`, whose extractor
# `tests/test_113_us2_docs_drift.py:53` — `_extract_readme_procedure` takes the
# FIRST fenced `bash` block on the page and returns the empty string unless that
# block holds `printf` and `apparmor_parser`. Today that first block is the
# AppArmor one at `README.md:83`, closing at `README.md:92` — INSIDE the section
# US1 is told to write into. Reproduced: inserting a subsection with a `bash`
# fence after the bullets at `README.md:71` flips the extractor from a match to
# the empty string, reddening a landed test whose failure message names the
# AppArmor profile rather than the paragraph that caused it. FR-004 now forbids
# the fence, US1-S4 asserts its absence from the diff, plan.md carries trap 16,
# T005 and T006 carry the prohibition, and the module is named in US1's § Sizing
# line as a file no story may write.
# (2) The guard count made honest: `tests/test_readme.py` carries FIVE page-level
# guards, not three. `tests/test_readme.py:123` —
# `test_the_file_contains_no_secret_value` and `tests/test_readme.py:156` —
# `test_the_file_names_no_spend_figure` were unnamed, so US1-S4 no longer closes
# with "three named asserters" as though the enumeration were complete.
# (3) A stale count corrected: the "edit the packaged registry" wording has TWO
# copies, so the NOT IN SCOPE paragraph below now says "the second copy", which
# is what § What this spec is not and plan.md trap 6 have said since the last
# repair.
# (4) `docs/onramp.html` named as the unfixed sibling: its
# `What you must already have` section at `docs/onramp.html:341` has the same
# silence, and its only two mentions of Temporal, `docs/onramp.html:226` and
# `docs/onramp.html:240`, are architecture prose rather than a prerequisite. The
# ledger row is scoped to `README.md` (`refs: [README.md]`), so the key still
# closes WHOLE here; the successor key is the operator's to mint at closure, the
# same shape as the requirements verb's clause 3 above.
# (5) One anchor-accuracy correction: `README.md:47` is the `### Everything else`
# heading, not a bullet list; the bullets begin at `README.md:49`.
# No key added or removed; no hold reversed; state stays draft.
#
# WHERE THIS CAME FROM. Three sightings — N1, N3 and N4 — of the round-2
# `ergane-web` hand-over, a consumer repository that is itself a target of this
# factory (D-003). They are three separate ledger keys and one failure: the
# verbs a stranger runs before their first dispatch describe a host that is not
# theirs. Each is small, each sits on the on-ramp, and shipping them apart means
# three releases before a stranger's first hour is honest.
#
# WHAT IT COST, MEASURED. The hand-over recorded 54 operator interventions
# across 20 landed stories over 2026-08-22 to 2026-08-28. N1 is graded "first
# thing a clean host trips on": README.md carries zero occurrences of the string
# `temporal` across all 278 lines, and `git log --all -S"temporal" -i -- README.md`
# returns ZERO commits, so the word has never appeared on any branch — while the
# control plane refuses outright a config with no `[temporal]` block. N4 is worse
# than the document graded it: the scan's SECOND probe is unauthenticated too, so
# `DISPATCHABLE` is unreachable for any correctly-secured gateway, and a stranger
# with a proper LiteLLM proxy and a local Ollama who presses Enter lands on
# Ollama in `direct` mode — the mode README.md's own prose tells them not to
# choose.
#
# WHAT EACH KEY BUYS, AND WHAT IT DOES NOT — read this before triage closes any
# of the three. The half-fix failure (100, 092, 118) is a `fixes:` list longer
# than the FRs justify, so each key is mapped here.
#   * `docs/readme-prerequisites-omit-the-temporal-server-entirely` — WHOLE.
#     FR-001 states the requirement, FR-002 names both ways to satisfy it,
#     FR-003 makes it undeletable, FR-004 keeps the page's own suites green, and
#     FR-005 closes the note's second clause ("nor that temporal.mode =
#     'managed' is parsed and refused") by correcting the tree's stale prose:
#     managed is no longer refused, 119 wired it end to end.
#   * `install/the-requirements-verb-refuses-on-a-fresh-install-and-names-the-wrong-file`
#     — TWO OF THREE CLAUSES, DELIBERATELY. The row names three defects. FR-006
#     fixes clause 1 (it points at the tool venv) and FR-007 fixes clause 2 (the
#     doubled path). Clause 3 — "the verb knows the requirements and refuses
#     anyway; printing them is strictly more useful" — is NOT a defect this
#     tree agrees with: 063-US3 landed the refusal as an acceptance criterion
#     with a committed test asserting `code != 0`, and FR-008 pins it. If the
#     operator still wants the verb to print an all-example registry, that is a
#     new key and a decision entry, not this spec. THE LEDGER DEBT THAT CREATES:
#     when triage closes this key on landing, clause 3 leaves the ledger with no
#     successor, so the operator mints
#     `install/the-requirements-verb-could-print-what-it-refuses-to-print` as a
#     WANT at closure, citing the 063-US3 decision and this spec's FR-008 as why
#     it is not a defect. Closing this key without minting that one loses the
#     reporter's third clause silently.
#   * `install/the-scanner-classifies-a-properly-secured-gateway-as-unreachable`
#     — the DEFECT whole, the reporter's second remedy refused. FR-009 to FR-013
#     fix exactly what the summary states. The row's notes also propose
#     "accept a key so the scan can finish the job"; that contradicts 055
#     FR-003/SC-002 and its committed control, and FR-014 pins the refusal
#     instead. Making the scan credentialed needs its own decision entry.
#
# NOT IN SCOPE. This spec does not reverse 063-US3 — `--requirements` still
# refuses an unconfigured registry with a non-zero exit and only its words
# change. It does not make any probe carry a credential. It does not restructure
# the interview: the question order, the `_ask` seam and the direct-mode
# surrender text are untouched. It does not rewrite README.md — one subsection
# under an existing heading, and one guard beside the seven that exist. It does
# not delete `RULE_TEMPORAL_MANAGED_NOT_IMPLEMENTED`, which is a stable rule slug
# named by `docs/decisions.md`; only the comment beside it is corrected. And it
# does not touch the second copy of the "edit the packaged registry" wording,
# which lives in the doctor's own LLM probe in `factory/controlplane/verify.py`
# rather than in the requirements verb: that message is not what the ledger row
# reports and editing it grows US2 into another module. Nor does it edit
# `docs/onramp.html`, whose `What you must already have` section at
# `docs/onramp.html:341` carries the same silence about the Temporal server: that
# is a separate page with its own suite (`tests/test_onramp_html.py`), the ledger
# row is scoped to `README.md`, and a successor key is the operator's to mint at
# closure if they want the HTML on-ramp fixed too.
---

# Feature Specification: the on-ramp names what is actually on the host

**Created**: 2026-09-04
**Depends on**: nothing.

## The gap, stated precisely

Three verbs run before a stranger's first dispatch — reading `README.md`,
`ergane install --requirements`, and `ergane install --scan` feeding the
interview. All three describe a host the stranger does not have, and each does it
for its own mechanical reason.

**The Temporal server is a hard requirement nobody is told about.**

1. The control plane refuses a config with no `[temporal]` block:
   `factory/controlplane/config.py:434` — `_read_temporal` calls
   `_expect_block(document, "temporal", source)` at
   `factory/controlplane/config.py:437`, and
   `factory/controlplane/config.py:751` — `_expect_block` raises
   `RULE_MISSING_REQUIRED` when the key is absent.
2. `README.md` never says so. The string does not occur in the page's 278 lines,
   and it has never occurred: `git log --all -S"temporal" -i -- README.md` finds
   no commit on any branch. The prerequisites section
   (`README.md:17`, closing at `README.md:97`) names the gateway, `gh`, the merge
   queue and Spec Kit; its second subsection opens at `README.md:47` and that
   subsection's bullets begin at `README.md:49`.
3. Nor does it say how to get one, and there are two ways the tree already
   supports. External: `temporal.mode = "external"` plus an address, which
   `factory/controlplane/config.py:434` — `_read_temporal` reads at its tail.
   The engine's own: `temporal.mode = "managed"`, accepted at
   `factory/controlplane/config.py:447-450`, read back by
   `factory/supervision/units.py:344` — `declared_temporal_mode`, turned into a
   yes-or-no by `factory/supervision/units.py:442` — `_temporal_managed`, and
   written as the `ergane-temporal.service` unit named at
   `factory/supervision/units.py:86` by the insert at
   `factory/supervision/units.py:495-497` — which `ergane worker install`
   reaches through `declared_layout` at `factory/cli/nouns/worker.py:53`.
4. The tree's own prose still says the second way is refused. The comment at
   `factory/controlplane/config.py:41-42` reads "`managed` is recognized as a
   token but refused until 042 lands", and the rule it points at,
   `factory/controlplane/config.py:69`, has no call site anywhere under
   `factory/`. 119 removed the refusal and left its epitaph.
5. And a sentence added today can be deleted tomorrow with a green suite.
   `tests/test_readme.py:199-207` enumerates the seven protected concepts that
   `tests/test_readme.py:210` — `missing_readme_concepts` checks; none is
   Temporal.

**The requirements verb names a file the operator cannot usefully edit, at a
path that does not exist.**

6. On a fresh install `ergane install --requirements` refuses — correctly, per
   063-US3 — and the refusal at `factory/cli/nouns/install.py:101-108` says
   "edit {registry_path}". `factory/cli/nouns/install.py:100` set that value from
   `factory/config.py:111` — `resolve_default_registry_path`, whose final branch
   (`factory/config.py:132-134`) hands off to `factory/config.py:81` —
   `_resolve_default_registry_path`, which returns the copy packaged **inside the
   installed distribution**. So the hint tells a stranger to edit a file under
   `site-packages`, which the next upgrade overwrites.
7. The resolution order it prints is doubled. `factory/config.py:47` is
   `DEFAULT_REGISTRY_REL = Path("ergane") / REGISTRY_FILENAME`, already carrying
   the `ergane/` segment, and both refusal branches prefix it again:
   `factory/cli/nouns/install.py:95` and `factory/cli/nouns/install.py:106` each
   render `~/.config/ergane/{DEFAULT_REGISTRY_REL}`, printing
   `~/.config/ergane/ergane/personas.yaml`. The `$XDG_CONFIG_HOME` spelling on
   the same two lines is correct; only the tilde copy doubles.

**The scan reports the one endpoint that can dispatch as down, and the interview
acts on that reading.**

8. `factory/discovery/llm_scanner.py:90` — `_probe_one` takes the success branch
   at `factory/discovery/llm_scanner.py:106` and folds **every** other status
   into unreachable at `factory/discovery/llm_scanner.py:118-125`, returning
   `reachable=False, classification=None`. A LiteLLM proxy with a master key set
   — the proxy `README.md:19` requires — answers 401 to an unauthenticated
   `GET /v1/models`.
9. The second probe has the same shape, and it is worse than the hand-over
   graded it. `factory/discovery/llm_scanner.py:127-131` posts `/key/generate`
   unauthenticated and reads `has_key_management = key_response.status_code == 200`,
   so a **protected** key-management API (401) is indistinguishable from an
   **absent** one (404) at `factory/discovery/llm_scanner.py:135-143`.
   `DISPATCHABLE` is therefore unreachable for any correctly-secured gateway.
10. `factory/cli/install.py:2132` — `_llm_scan` returns the first dispatchable
    result and otherwise the first *reachable* one. A secured gateway is neither,
    so it is skipped entirely; an Ollama on the second default loopback
    candidate answers
    `/v1/models` unauthenticated and is the only candidate left.
11. `factory/cli/install.py:2149` — `_offered_llm_mode` then writes that address
    into `document["llm"]["base_url"]` at `factory/cli/install.py:2192` and
    offers `direct` at `factory/cli/install.py:2193`, which
    `factory/cli/install.py:1545` — `_ask_llm` makes the default answer at
    `factory/cli/install.py:1560`. A stranger presses Enter and lands in the mode
    `README.md:39` tells them not to choose, on an endpoint that cannot mint a
    per-attempt key.

## The rule this spec is asking for

**Every verb a stranger runs before their first dispatch describes the host they
actually have: the page names the Temporal server and both ways to get one, the
requirements refusal names a file they can create, and the scan reports a secured
endpoint as secured rather than as absent — while every refusal that is a landed
decision keeps refusing, and no probe gains a credential.**

The scanner's cases, complete:

| `GET /v1/models` | `POST /key/generate` | classification | reachable |
|---|---|---|---|
| 200 | 200 | `dispatchable` — unchanged | yes |
| 200 | 401 or 403 | **`authentication-required`** — new | **yes** |
| 200 | any other status, or a transport error | `inference-only` — unchanged | yes |
| 401 or 403 | not probed | **`authentication-required`** — new | **yes** |
| any other status | not probed | none — unchanged | no |
| transport error | not probed | none — unchanged | no |

And the interview's preference order becomes `dispatchable`, then
`authentication-required`, then `inference-only`. Only the two bold rows are new;
every other row keeps today's result and today's detail text. Note the asymmetry
the table makes explicit: a transport error on the FIRST probe is unreachable, a
transport error on the SECOND is inference-only, because by then `/v1/models` has
already answered 200.

### What this spec is not

It is not a reversal of 063-US3. `ergane install --requirements` still exits
non-zero on an unconfigured registry and still names the whole resolution order.
Only the words of the refusal change, and
`tests/test_ergane_install_requirements.py:240` —
`test_requirements_with_example_registry_prints_configuration_guidance` must keep
passing with no hunk of the diff touching it.

It is not a rewrite of every message that carries the "edit the packaged
registry" wording. Measured at `602a92c`,
`grep -rn 'replace the example/ placeholder aliases' factory/` returns **two**
hits, not three: `factory/cli/nouns/install.py:103`, the requirements verb's
all-example branch, which is this spec's business, and
`factory/controlplane/verify.py:462-463`, which belongs to the doctor's LLM probe
and is not the verb the ledger row reports. That second one stays exactly as it
is. The verb's *other* refusal branch is not a copy of that phrase —
`factory/cli/nouns/install.py:92` reads "declare at least one persona with a
gateway model alias" — so greping the phrase finds one of the two branches this
spec edits, never both. What the two branches genuinely share is the
resolution-order line at `factory/cli/nouns/install.py:95` and
`factory/cli/nouns/install.py:106`, the only two hits of
`grep -rn 'config/ergane/{' factory/`, and that shared line is where FR-007's
doubled path lives.

It is not a credentialed scan. No probe gains an `Authorization` header. 055
FR-003's committed control, `tests/test_llm_discovery.py:159` —
`test_scan_sends_no_authorization_header`, keeps passing and is widened to sweep
the new branches.  Teaching the scan to authenticate is a separate decision entry.

It is not a restructuring of the interview. The question order, the `_ask` seam
and the direct-mode surrender text are untouched; only which candidate the offer
is derived from changes.

It is not a rewrite of `README.md`. One subsection under an existing heading, and
one guard beside the seven that already exist — and no fenced `bash` block above
`README.md:83`, because `tests/test_113_us2_docs_drift.py:53` —
`_extract_readme_procedure` reads the page's first such block and
`tests/test_113_us2_docs_drift.py:91` —
`test_readme_procedure_matches_shipped_profile` refuses anything there but the
AppArmor procedure (trap 16). That module takes no hunk of this diff.

It is not an edit of `docs/onramp.html`. That page's own
`What you must already have` section at `docs/onramp.html:341` omits the Temporal
server exactly as `README.md` does, and its two mentions of Temporal —
`docs/onramp.html:226` and `docs/onramp.html:240` — are architecture prose rather
than a prerequisite. The ledger row this spec closes is scoped to `README.md`, so
closing it whole is honest; the HTML on-ramp is a separate page with its own
suite (`tests/test_onramp_html.py`) and wants a successor key, not a wider diff
here.

## User Scenarios & Testing

### User Story 1 - The page names the Temporal server, and cannot lose it again (Priority: P1)

As a stranger on a clean host, I learn that Ergane needs a Temporal server before
I discover it by failing, and I learn the two ways to have one.

**Why this priority**: P1 because it is the first thing a clean host trips on and
it blocks on nothing. It is also the story that carries the tree's own stale
prose: the same untruth — that managed Temporal is refused — is written in a
comment beside the code that honours it, and correcting one without the other
leaves the page and the source disagreeing again.

**Independent Test**: Run the README guard function over the committed page, over
a copy with the Temporal prose removed, and over a copy with it reworded; read
what each reports.

**Acceptance Scenarios**:

1. **Given** a copy of `README.md` whose Temporal prose has been removed,
   **When** `tests/test_readme.py:210` — `missing_readme_concepts` runs over it,
   **Then** it reports the Temporal prerequisite as missing, proven by a
   committed entry in `tests/test_readme.py:301` — `_mutations` that the
   parametrized `tests/test_readme.py:387` — `test_missing_concept_is_detected`
   sweeps. A guard with no mutation entry asserts nothing about a page nobody
   edits.
2. **Given** the committed `README.md`, **When** the same function runs over it,
   **Then** it reports nothing missing — so the prose and the guard that protects
   it land in one diff, and neither half can be committed without the other.
3. **Given** a copy of `README.md` whose Temporal prose is **reworded** rather
   than removed, **When** the same function runs over it, **Then** it still
   reports nothing missing, proven by a committed rewording inside
   `tests/test_readme.py:396` — `test_reworded_equivalent_page_passes`, so the
   guard is keyed to meaning and not to one literal string.
4. **Given** the new prose, **When** the page's own sweeps run, **Then** every
   `ergane` invocation it names parses against the live parser — asserted by the
   existing `tests/test_readme.py:50` —
   `test_every_command_the_file_names_parses`, parametrized over the spans
   `tests/page_holds_true.py:301` — `extract_commands` finds, with
   `tests/test_readme.py:86` — `test_the_command_sweep_actually_read_the_file`
   as its anti-vacuity guard — and every path it cites resolves in the tree,
   asserted by the existing `tests/test_readme.py:107` —
   `test_every_path_the_file_cites_exists`, which resolves a backticked span
   against the repository root, so no tilde-prefixed configuration path may be
   cited in a backtick — and the page names no spec number beside a status word,
   asserted by the existing `tests/test_readme.py:140` —
   `test_the_file_names_no_spec_status` — and no hunk of the diff introduces a
   fenced `bash` block above `README.md:83`, so the first such block on the page
   is still the AppArmor one and `tests/test_113_us2_docs_drift.py:91` —
   `test_readme_procedure_matches_shipped_profile` still extracts a procedure
   instead of the empty string that `tests/test_113_us2_docs_drift.py:53` —
   `_extract_readme_procedure` returns otherwise. Four asserters, four different
   questions: the path sweep does not read commands, the command sweep does not
   resolve paths, and the drift test lives in another module and reads neither.
   Four is not the page's whole guard — `tests/test_readme.py:123` —
   `test_the_file_contains_no_secret_value` and `tests/test_readme.py:156` —
   `test_the_file_names_no_spend_figure` sweep it too — but these four are the
   ones new prerequisite prose can plausibly break.
5. **Given** the comment at `factory/controlplane/config.py:41-42`, **When** the
   diff is read, **Then** it no longer states that `managed` is refused and
   instead names what the mode now does, and a committed test asserts that a
   config declaring `temporal.mode = "managed"` parses into a `Temporal` whose
   mode is `managed` — so the sentence and the parser are pinned together rather
   than left to drift for a fourth time. **That second half is a control and is
   expected to pass the moment it is written**: 119 already removed the
   parse-time refusal, and `tests/test_supervision_managed_temporal.py:131` —
   `test_temporal_managed_mode_parses_without_refusal` already proves it
   elsewhere. Its job is to pin the sentence FR-005 corrects to the behaviour
   that sentence describes, not to go red first.

### User Story 2 - The requirements refusal names a file the operator can create (Priority: P2)

As an operator on a fresh install, the verb that refuses tells me what to do
next, at a path that exists.

**Why this priority**: P2 and independent of US1. It is two message strings on
one function, and the risk is entirely in the control: the refusal itself is a
landed acceptance criterion that must survive the edit intact.

**Independent Test**: Point the registry at an unconfigured file, run
`ergane install --requirements`, and read the refusal's text and its exit code.

**Acceptance Scenarios**:

1. **Given** an install whose persona registry resolves to a copy the operator
   cannot usefully edit — reached in a test by rebinding
   `factory/config.py:81` — `_resolve_default_registry_path` to an example
   registry under `tmp_path`, because a checkout carries no
   `factory/personas.yaml` and the resolver would otherwise hand back the
   repository's own configured registry and exit zero — **When**
   `ergane install --requirements` refuses, **Then** a committed test asserts the
   message names that resolved path as the registry **being read** and names a
   concrete override path for the operator to **create**, and asserts the message
   does not tell the operator to edit the packaged copy.
2. **Given** either refusal branch — the no-aliases branch at
   `factory/cli/nouns/install.py:89-97` and the all-example branch at
   `factory/cli/nouns/install.py:101-108` — **When** its resolution order is
   read, **Then** a committed test asserts the tilde spelling carries exactly one
   `ergane/` segment, by asserting `~/.config/ergane/personas.yaml` is present
   and `~/.config/ergane/ergane/` is absent from the captured output. Both
   branches are asserted: they carry the same defect on two lines and fixing one
   is invisible to a test that drives the other.
3. **The control that matters most.** **Given** a registry that is entirely
   `example/` aliases, **When** the verb runs, **Then** it still exits non-zero
   and still names `ERGANE_PERSONAS_PATH`, `FACTORY_PERSONAS_PATH`,
   `XDG_CONFIG_HOME` and the resolved path — with no hunk of the diff modifying
   `tests/test_ergane_install_requirements.py:240` —
   `test_requirements_with_example_registry_prints_configuration_guidance`, and
   with the declared `test` gate green over it.
4. **The control.** **Given** a registry that **is** configured, **When** the
   verb runs, **Then** it exits zero and prints the same alias listing and the
   same three key-management endpoints as today, so a message edit cannot have
   reached the success path.

### User Story 3 - A secured endpoint scans as secured, and the interview prefers it (Priority: P3)

As a stranger who did the secure thing and put a master key on my gateway, the
scan does not tell me my gateway is down and the interview does not hand me an
endpoint that cannot dispatch.

**Why this priority**: P3 and independent of US1 and US2. It is the largest of
the three and the only one that changes a classification other code reads, so it
carries the most controls.

**Independent Test**: Drive the scanner's injected transport seam with a
401-answering endpoint beside a 200-answering inference-only one, and read both
the scan results and the mode the interview offers.

**Acceptance Scenarios**:

1. **Given** an endpoint whose `GET /v1/models` answers 401, **When** the scan
   probes it through the injected transport, **Then** a committed test asserts
   the result is reachable, classified authentication-required, and carries a
   detail naming that a credential is required and that the scan presented none.
2. **Given** an endpoint whose `GET /v1/models` answers 200 and whose
   `POST /key/generate` answers 403, **When** the scan probes it, **Then** a
   committed test asserts the result is authentication-required and **not**
   inference-only, because a protected route is evidence the route exists — an
   absent one answers 404, which is the case that must stay inference-only.
3. **The control.** **Given** endpoints that answer 404, answer 500, and refuse
   the connection, **When** the scan probes each, **Then** a committed test
   asserts all three remain unreachable with no classification and with their
   detail text byte-identical to today's, so widening the reachable set has not
   swallowed a genuinely dead host.
4. **Given** a host where a secured gateway and an inference-only endpoint both
   answer and no prior mode has been declared, **When** the interview derives its
   offer, **Then** a committed test asserts the offered mode is `gateway` and the
   defaulted `llm.base_url` is the secured gateway's address — not the
   inference-only endpoint's, which is what a diff that changed only the scanner
   would still produce.
5. **The control.** **Given** a host where only an inference-only endpoint
   answers, and separately a re-run whose document already declares
   `llm.mode = "direct"`, **When** the interview derives its offer in each case,
   **Then** committed tests assert that the inference-only host is still offered
   `direct` with that address and the same unavailable-reason text as today, and
   that the re-run — driven with an **authentication-required** result, the only
   kind that reaches the branch this story adds — is still offered `direct`, so
   the new branch carries the same already-declared guard the dispatchable branch
   carries at `factory/cli/install.py:2176`. The re-run document must differ from
   `factory/cli/install.py:242-249` — `BLANK_DOCUMENT`'s `llm` block, or
   `factory/cli/install.py:2166` reads it as a blank host and the guard is never
   exercised. A re-run control driven with an inference-only result proves
   nothing about this story's code: that result falls through to a tail the story
   does not touch.
6. **The security control.** **Given** every probe made on every branch above,
   including the two new ones, **When** the recorded requests are read, **Then**
   none carries an authorization header — asserted by
   `tests/test_llm_discovery.py:159` — `test_scan_sends_no_authorization_header`
   with its assertion unchanged and its fixture widened to cover a 401-answering
   and a 403-answering endpoint.

## Functional Requirements

- **FR-001**: `README.md` MUST state, inside the section beginning at
  `README.md:17` and ending at `README.md:97`, that Ergane requires a reachable
  Temporal server, because the control plane refuses a configuration with no
  `[temporal]` block.
- **FR-002**: The same section MUST name both supported ways to have one — an
  external server declared `temporal.mode = "external"` with an address, and the
  engine's own server declared `temporal.mode = "managed"`, which
  `ergane worker install` writes and supervises as a systemd user unit.
- **FR-003**: `tests/test_readme.py` MUST protect that statement the way it
  protects the other seven concepts: a name in
  `tests/test_readme.py:199-207`, a check inside `tests/test_readme.py:210` —
  `missing_readme_concepts` reading the prerequisites section, a mutation entry
  in `tests/test_readme.py:301` — `_mutations`, and a rewording inside
  `tests/test_readme.py:396` — `test_reworded_equivalent_page_passes`.
- **FR-004**: The new prose MUST NOT introduce a citation the page's existing
  sweeps refuse: no backticked tilde-prefixed or otherwise non-repository path,
  no spec number written beside a status word, and every `ergane` invocation it
  names MUST parse against the live parser. It MUST NOT introduce a fenced
  `bash` block above the AppArmor block at `README.md:83`, because
  `tests/test_113_us2_docs_drift.py:53` — `_extract_readme_procedure` reads the
  page's first such block and `tests/test_113_us2_docs_drift.py:91` —
  `test_readme_procedure_matches_shipped_profile` refuses anything else there;
  `tests/test_113_us2_docs_drift.py` MUST NOT be edited.
- **FR-005**: The comment at `factory/controlplane/config.py:41-42` MUST stop
  saying `managed` is refused and MUST state what the mode does now, and a
  committed test MUST assert that `temporal.mode = "managed"` parses into a
  `Temporal` whose mode is `managed`.
  `RULE_TEMPORAL_MANAGED_NOT_IMPLEMENTED` at
  `factory/controlplane/config.py:69` MUST NOT be deleted; it is a stable rule
  slug named by `docs/decisions.md`.
- **FR-006**: Both refusals in `factory/cli/nouns/install.py:62` —
  `_requirements_command` MUST name the resolved registry as the file being read
  and MUST name a concrete override path for the operator to create; neither may
  instruct the operator to edit a path inside the installed distribution.
- **FR-007**: Both refusals MUST render the tilde spelling of the default
  registry with exactly one `ergane/` segment, so the printed path is
  `~/.config/ergane/personas.yaml`.
- **FR-008**: Both refusals MUST keep their non-zero exit and MUST keep naming
  `ERGANE_PERSONAS_PATH`, `FACTORY_PERSONAS_PATH`, `XDG_CONFIG_HOME` and the
  resolved path; no hunk of the diff may modify
  `tests/test_ergane_install_requirements.py:240` —
  `test_requirements_with_example_registry_prints_configuration_guidance`, and
  the declared `test` gate MUST be green over it.
- **FR-009**: `factory/discovery/llm_scanner.py:90` — `_probe_one` MUST classify
  a 401 or 403 answer to `GET /v1/models` as reachable and
  authentication-required, with a detail stating that a credential is required
  and that the scan presented none. The landed membership assertion at
  `tests/test_controlplane_verify_us1.py:484` —
  `test_llm_verify_imports_classification_from_scanner` MUST be widened to
  include the new member, with the two `is` identity assertions beside it
  unchanged and `factory/controlplane/verify.py` itself untouched.
- **FR-010**: `_probe_one` MUST classify a 401 or 403 answer to
  `POST /key/generate` as authentication-required rather than inference-only,
  while a 404 keeps today's inference-only result.
- **FR-011**: Every other non-200 answer to `GET /v1/models`, and every transport
  error reaching that first probe, MUST keep today's unreachable result with its
  detail text unchanged; a transport error on `POST /key/generate` MUST keep
  today's inference-only result with its detail text unchanged; and
  `dispatchable` MUST keep meaning both routes answered 200.
- **FR-012**: `factory/cli/install.py:2132` — `_llm_scan` MUST prefer a
  dispatchable result, then an authentication-required one, then an
  inference-only one.
- **FR-013**: On a host with no prior operator declaration, an
  authentication-required result MUST make
  `factory/cli/install.py:2149` — `_offered_llm_mode` offer `gateway` and default
  `llm.base_url` to that address; an inference-only result MUST keep today's
  `direct` offer and its unavailable-reason text; and a mode already declared on
  a re-run MUST keep winning over the scan, including — and proven with — an
  authentication-required result, which is the only kind that reaches the new
  branch.
- **FR-014**: No probe the scan makes may carry a credential.
  `tests/test_llm_discovery.py:159` — `test_scan_sends_no_authorization_header`
  MUST keep its assertion unchanged and MUST sweep the new 401 and 403 branches.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005]
US2:
  depends_on: []
  implements: [FR-006, FR-007, FR-008]
US3:
  depends_on: []
  concurrent_with: [US1, US2]
  implements: [FR-009, FR-010, FR-011, FR-012, FR-013, FR-014]
```

No edges, and that is a claim about files rather than a default. The three
stories name no production file in common: US1 edits `README.md`,
`tests/test_readme.py` and one comment in `factory/controlplane/config.py`; US2
edits `factory/cli/nouns/install.py` and `factory/config.py`; US3 edits
`factory/discovery/llm_scanner.py` and `factory/cli/install.py`, and widens one
landed assertion in `tests/test_controlplane_verify_us1.py` without touching the
module that test guards. Note that US2's
`factory/cli/nouns/install.py` and US3's `factory/cli/install.py` are two
different modules with confusable names — the CLI noun and the interview — and
neither story touches the other's. No story reads a symbol another story adds, so
there is nothing for a `depends_on_merged` edge to sequence; three nodes may run
concurrently and land in any order.

`concurrent_with: [US1, US2]` on US3 is a deliberate override of two inferred
contention edges, and in both cases the shared file is named only so that nobody
edits it. Against US2 the file is `factory/controlplane/verify.py`: US2 is told
the second copy of the "edit the packaged registry" wording lives there and is
not the requirements verb, and US3 is told the module that imports the
classification enum needs no change. Against US1 the file is
`tests/test_ergane_install_walkthrough.py`: US1 is told its stale transcript at
`tests/test_ergane_install_walkthrough.py:137` is a labelled historical
docstring and must not be chased, and US3 is told to **read**
`tests/test_ergane_install_walkthrough.py:644` for the shape of a re-run harness
while putting its own new assertion in `tests/test_install_mode_routing.py`.
Neither pair of stories may put a hunk in the shared file, so there is nothing
for the diffs to collide over and no reason to serialise them.
