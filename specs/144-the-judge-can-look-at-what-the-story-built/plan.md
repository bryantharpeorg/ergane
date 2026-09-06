# Implementation Plan: the judge can look at what the story built

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**The type that forecloses everything, in one line.**
`factory/verify/judge.py:269` — `JudgePrompt` is the whole of what one judge
invocation posts, and its message field is
`factory/verify/judge.py:285` — `JudgePrompt`:

```python
    messages: list[dict[str, str]]
    truncated_input: bool
    gates_shown: bool
```

`factory/verify/judge.py:918` — `_complete` puts that object straight on the
wire at `factory/verify/judge.py:938` — `_complete`:

```python
    body: dict[str, Any] = {
        "model": model_alias,
        "temperature": 0,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "messages": prompt.messages,
    }
```

The path it posts to is declared at `factory/verify/judge.py:111` and is
`/chat/completions` — the OpenAI-shaped completions endpoint the proxy serves,
which is the shape the content block must be written in. `dict[str, str]` cannot
hold one, so the type is the first thing US1 widens. FR-001.

**The assembler, and the exact accounting to copy.**
`factory/verify/judge.py:307` — `build_prompt` is pure — the section it sits
under says so at `factory/verify/judge.py:290` — and it already solves this
spec's hardest sub-problem once, for the gate section
(`factory/verify/judge.py:345` — `build_prompt`):

```python
    gate_blocks = _gate_blocks(gate_results)
    # Every element of `blocks` is joined with one newline, so a block list of
    # length k costs its own bytes plus k separators — measured, not estimated,
    # because this is exactly the amount the diff no longer has (FR-004).
    gate_bytes = sum(len(block.encode("utf-8")) for block in gate_blocks) + len(
        gate_blocks
    )
    prepared = prepare_diff(diff_text, limit=max(DIFF_INPUT_LIMIT - gate_bytes, 0))
```

Read that comment before writing FR-005. "Measured, not estimated" is the whole
requirement: the artifact section's own text and the encoded image bytes are both
subtracted from what `factory/verify/judge.py:473` — `prepare_diff` is given, and
`DIFF_INPUT_LIMIT` is the constant at `factory/verify/diffbounds.py:47`. The
blocks are appended at `factory/verify/judge.py:394` — `build_prompt` and the
object is returned at `factory/verify/judge.py:397` — `build_prompt`, whose
`gates_shown=bool(gate_blocks)` at `factory/verify/judge.py:405` — `build_prompt`
carries the comment that is also FR-006's argument: "What the prompt carries, not
what the caller passed."

**Why that subtraction needs a floor, which the gate section gets for free.** The
copy above is safe only because a gate's contribution is bounded one gate at a
time: `factory/verify/judge.py:218` declares 2 KiB of a non-PASS gate's output
tail and says in its own comment that 2 KiB is "enough to spend on one gate what
the diff is fitted into". A picture has no such bound by nature. Read what
`factory/verify/judge.py:473` — `prepare_diff` does when the limit it is handed
reaches zero, at `factory/verify/judge.py:500` — `prepare_diff`:

```python
    head_block = listing + TRUNCATION_NOTICE + preamble
    allowance = max(limit - len(head_block.encode("utf-8")), 0)
    grants = _allocate([section.size for section in sections], allowance)
```

`max(..., 0)` never raises and never complains: every section is granted zero,
the prompt carries the file listing, the truncation notice and no diff body at
all, and the judge scores every scenario against a picture with no code beside
it. Two declared 24 KiB PNGs encode to roughly 64 KiB and do exactly that. FR-022
is the floor; trap 16 is the reproduction.

**The section to model, and why it is a named constant.** The gate section's
heading is declared at `factory/verify/judge.py:197` and its preamble at
`factory/verify/judge.py:202`, and the docstring above them says why they are
named rather than inlined: two other things have to find them — the accounting,
and the tests that assert where the section sits. The artifact section needs the
same treatment for the same two reasons.
`factory/verify/judge.py:409` — `_gate_blocks` is the function to model,
including its bounded tail (`factory/verify/judge.py:218` declares the character
limit it cuts to).

**The flag that already rides this exact route, with the argument written out.**
`factory/verify/models.py:576` — `JudgeVerdict` carries
`gates_shown: bool = False` at `factory/verify/models.py:609` — `JudgeVerdict`,
and the paragraph at `factory/verify/models.py:594` — `JudgeVerdict` is FR-006
in advance:

> It is a plain bool written in both directions, never an absent field (plan trap
> 8): a record that carried it only when the answer was yes would, when the
> answer was no, be indistinguishable from one written before this spec existed.

Copy that, including the default. It reaches the verdict through
`factory/verify/judge.py:591` — `parse_verdict`, whose keyword arguments at
`factory/verify/judge.py:597` — `parse_verdict` are the two facts about the
prompt the parser is told rather than allowed to invent.

**The library entry point, which is the only caller of either, and which the
records must travel through.** `factory/verify/judge.py:752` — `run_judge` is the
one function in `factory/` that calls `build_prompt` or `parse_verdict` — grep
`build_prompt(` and `parse_verdict(` over the package and the only hits outside
their own definitions are `factory/verify/judge.py:798` — `run_judge` and
`factory/verify/judge.py:816` — `run_judge`. Its signature already shows the shape
FR-020 asks for, at `factory/verify/judge.py:760` — `run_judge`:

```python
    gate_results: Sequence[GateResult] | None = None,
```

and it forwards that argument at `factory/verify/judge.py:798` — `run_judge`:

```python
    prompt = build_prompt(
        criteria,
        diff_text,
        prior_feedback=prior_feedback,
        gate_results=gate_results,
    )
```

Then it carries the assembled prompt's flag onto **both** verdicts it can return:
the parsed one at `factory/verify/judge.py:822` — `run_judge`, and the
malformed-response one at `factory/verify/judge.py:836` — `run_judge`, which 116
covered deliberately and commented at `factory/verify/judge.py:833` — `run_judge`:

```python
            # Recorded on the unreadable-response path too: what the judge was
            # shown is a fact about the ask, and an ask that produced garbage
            # was still made with — or without — the measurements in it.
            gates_shown=prompt.gates_shown,
```

Four lines, all four of them US4's — the story split out of US1 so that the
assembler and the wiring are two PRs rather than one over the bound (§ Sizing).
Without them US2 has no parameter to hand records to and the only way to reach
the assembler is to call it from the activity, which is trap 15.

**The row the operator reads, and the two hand-written lines that put a field on
it.** A verdict is stored as JSON by `factory/verify/store.py:1238` — `_judge_to_dict`
and rebuilt by `factory/verify/store.py:1261` — `_judge_from_dict` (the call
sites are `factory/verify/store.py:982` and `factory/verify/store.py:1045`).
`gates_shown` reaches the row only because 116 wrote it out twice, at
`factory/verify/store.py:1257` — `_judge_to_dict`:

```python
        # 116-US3 (FR-008), and written in both directions on purpose (plan
        # trap 8): a key present only when the answer is yes would, when the
        # answer is no, make the row byte-identical to one written before this
        # spec — which is exactly the silence the field exists to break.
        "gates_shown": judge.gates_shown,
```

and at `factory/verify/store.py:1281` — `_judge_from_dict`:

```python
        gates_shown=bool(data.get("gates_shown", False)),
```

The codec is longhand on purpose, and the file says so in the docstring at
`factory/verify/store.py:1286` — `_contradiction_to_dict`: a field added to the
record "has to be added here too, and the alternative is a record that
round-trips *almost* everything, quietly". FR-021 and trap 17.

**The fourth chokepoint, which the hand-over missed.** Principle VIII's escape
hatch says runtime evidence is committed as an artifact the diff contains
(`.specify/memory/constitution.md:72-76`). It is closed here.
`factory/workgraph/worktree.py:1496` — `diff` builds the judge's entire input
with one command at `factory/workgraph/worktree.py:1527` — `diff`:

```python
        patch = _git(path, "diff", "--cached", base_ref, env_extra=index)
```

No `--binary` and no `--text`, so a committed PNG arrives as
`Binary files a/shot.png and b/shot.png differ`. Trap 2 is about what not to do
with that line.

**The declaration this spec reads is 134's, and it arrives free.** 134 puts a
`GateArtifact` tuple on `GateResult` beside `worktree_writes`
(`factory/verify/models.py:405` — `GateResult`), each record naming the declared
path, the declared type, whether the artifact was present, its size and the
location its bytes were written to; its FR-016 keeps the bytes themselves off the
record because `factory/verify/models.py:362` — `GateResult` crosses a Temporal
payload boundary. Those records already travel to the judge activity: they ride
on `gate_results`, which `factory/workgraph/workflow.py:2901` — `_score` puts on
`factory/activities/verify_activities.py:426` — `RunJudgeInput`, whose docstring
at `factory/activities/verify_activities.py:399` — `RunJudgeInput` explains that
they are the same list `judge_required` was handed one step earlier. US2 needs no
new carriage for the records — only for the bytes, and only inside the activity.

**134 already declined to store some of them, and that case is not "absent".**
134's FR-015 bounds the bytes it stores per artifact by its own named constant
and records an artifact above that bound *present*, with its true size and **no
stored location**, never truncated. So there are two different "present" records
this spec must tell apart: one with a location it can read, and one with none at
all. The second is a withheld record with its own reason, and it also fixes the
magnitude of this spec's show-limit — see trap 12.

**134's type vocabulary has no picture in it, and that is US4's one schema edit.**
134 defines its type set — `sbom`, `coverage`, `scan`, `opaque` — as a `StrEnum`
in `factory/verify/models.py` beside
`factory/verify/models.py:241` — `CacheDeclaration`, read by its `artifacts:`
reader in `factory/verify/factory_yaml.py` and carried on
`factory/verify/models.py:291` — `FactoryConfig`. None of those four is a
picture, and none of them may be admitted to the prompt. FR-008 adds `image` to
that enum. Whether `factory/verify/factory_yaml.py` needs an edit at all depends
on how 134's landed reader validates: 134's own T010 models it on
`_read_caches`, and if it validates the declared type *against the enum* then
widening the enum is the whole change and that file is untouched. Check the
landed reader first; edit it only if it spells the four type names a second time.
Sizing states both outcomes.

**The persona field to copy, down to its refusal.**
`factory/config.py:170` — `Persona` carries `context_window: int | None = None` at
`factory/config.py:194` — `Persona`; the name is registered in the optional-field
tuple at `factory/config.py:152`, checked against the unknown-field set at
`factory/config.py:264` — `_build_persona`, parsed at
`factory/config.py:275` — `_build_persona` by
`factory/config.py:350` — `_optional_context_window`, refused for a deterministic
persona at `factory/config.py:298` — `_build_persona`:

```python
        # US4: no agent runs, so there is no environment to put the window in.
        if context_window is not None:
            raise fail(
                f"field 'context_window' must be null when agent is "
                f"'{DETERMINISTIC_AGENT}', got {context_window!r}"
            )
```

and passed to the constructor at `factory/config.py:326` — `_build_persona`. Six
places, all of them one line. The shipped example documents its own field list at
`personas.example.yaml:19`, and the judge entry the operator edits is at
`personas.example.yaml:53`.

**The carrier from the registry to the judge call, end to end.**
`factory/workgraph/models.py:295` — `ResolvedPersona` is what a rung is routed by;
its `agent: str = ""` at `factory/workgraph/models.py:320` — `ResolvedPersona` is
defaulted for the reason FR-011 needs — "a recorded payload written before the
field existed must still deserialize". It is built in three places:
`factory/activities/agent_activities.py:370` — `resolve_persona`,
`factory/workgraph/workflow.py:1267` — `_resolve` and
`factory/workgraph/workflow.py:1285` — `_resolve`. The judge's own entry is
resolved once per epic at `factory/workgraph/workflow.py:998` — `run`, travels to
`factory/workgraph/workflow.py:2708` — `_judge` and reaches the request at
`factory/workgraph/workflow.py:2923` — `_score`. That last site is the only
production line FR-012 needs in workflow code.

**The activity that will build the records.**
`factory/activities/verify_activities.py:430` — `run_judge` forwards its request
to the library at `factory/activities/verify_activities.py:444` — `run_judge`. It
is an activity, so it may read the filesystem; the workflow may not. Everything
FR-013, FR-014 and FR-015 ask for is *built* between those two lines — and then
**travels** through the library entry point `factory/verify/judge.py:752` — `run_judge`,
on the parameter FR-020 puts there. The activity never calls the assembler
itself; doing so bypasses the entry point's retry and malformed-response paths
and is trap 15.

**The authoring layer, and the three doors it has today.**
`factory/cli/nouns/spec.py:1440` is the closed list of fifteen phrasings, with
`("visually", r"visually")` at `factory/cli/nouns/spec.py:1454`.
`factory/cli/nouns/spec.py:1781` — `_check_evidence` reads each Then-clause, and
at `factory/cli/nouns/spec.py:1830` — `_check_evidence` a clause with no marker
is admitted, a clause naming a declared gate
(`factory/cli/nouns/spec.py:1513` — `_names_a_declared_gate`) is admitted, and a
clause whose scenario carries a diff-evidence word
(`factory/cli/nouns/spec.py:1481`) becomes a borderline warning
(`factory/cli/nouns/spec.py:1748` — `_borderline_warning`) rather than a refusal.
Everything else is refused by
`factory/cli/nouns/spec.py:1588` — `_evidence_refusal`, which names exactly two
remedies at `factory/cli/nouns/spec.py:1605` — `_evidence_refusal`. US3 adds the
fourth admission and the third remedy.

**Where US3 reads the declaration from.**
`factory/cli/nouns/spec.py:1539` — `_Declarations` is one read of one manifest
answering every question this module asks of it; the gate set it carries is
documented at `factory/cli/nouns/spec.py:1548` — `_Declarations` and filled at
`factory/cli/nouns/spec.py:1559` — `_declared_gates` from the same
`load_factory_config` call that already returns `config.gates` and
`config.diff_refusal_bytes`. 134's artifacts come off that same object. The
report that must name them is
`factory/cli/nouns/spec.py:1666` — `_JudgeEvidenceReport`, whose emitted document
is built at `factory/cli/nouns/spec.py:1685` — `as_dict` and already carries a
`gates` block with the manifest path and the declared names.

**Why "add rendering" would be the wrong build.**
`factory/verify/gate_annotation.py:86` is a closed roster of three browser-driving
tools — `factory/verify/gate_annotation.py:90`,
`factory/verify/gate_annotation.py:92` and
`factory/verify/gate_annotation.py:94` — and it exists because repositories
really declare Playwright, Puppeteer and Cypress gates against this factory. The
producer half is not missing. Trap 5.

## Traps

**Trap 1 — This touches binding doctrine, no story here may amend it, and the
doctrine is already behind the code.** Principle VIII is marked NON-NEGOTIABLE at
`.specify/memory/constitution.md:63`, its evidence sentence is at
`.specify/memory/constitution.md:72-76`, and it is anchored by D-050 at
`.specify/memory/constitution.md:162` and D-037 at
`.specify/memory/constitution.md:167`. It says the judge is given the diff and the
criteria snapshot and nothing else. **That is not what the tree does.** Spec 116
landed on 2026-08-31 and the system prompt at `factory/verify/judge.py:138`
already tells the judge "You may also be given this factory's gate results"; grep
`.specify/memory/constitution.md` and `docs/decisions.md` for "gate result" and
both come back empty, and the last constitutional amendment is D-051 dated
2026-08-24 at `.specify/memory/constitution.md:157-160`. So the declared artifact
is the fourth input, not the third, and the amendment the operator writes should
cover the class — the story's diff, the criteria snapshot, and the factory's own
measurements of that same attempt, its gate results and its gates' declared
artifacts — and should record the 116 drift rather than leaving a second
undocumented input behind. The wrong move an implementer will be tempted to make
is to edit `.specify/memory/constitution.md` so its own story reads coherently.
That file is the standards path every dispatched attempt is told to obey; editing
it changes what every future agent is held to, and no story in this trio names
it. If the doctrine and your story disagree, the story stops and the operator
decides.

**Trap 2 — The obvious fix to the fourth chokepoint is one flag, and it is wrong.**
`factory/workgraph/worktree.py:1527` — `diff` runs `git diff --cached <base_ref>`
with no `--binary`, so a committed screenshot reaches the judge as one line. An
implementer who finds this will add `--binary`. That puts base64 of every changed
binary — a committed browser cache, a compiled asset, a font — inside the
allowance `factory/verify/judge.py:473` — `prepare_diff` fits the diff into,
against a threshold measured over the whole assembly
(`factory/verify/diffbounds.py:137` — `assembled`) whose refusal value is
declared at `factory/verify/diffbounds.py:66`. It also rewrites every prompt in
the corpus for every repository, declared artifact or not. The channel this spec
builds is beside the diff, not inside it, which is why spec.md's "What this spec
is not" says the diff assembly is untouched.

**Trap 3 — Widening the message type must not widen every message.** The existing
judge test corpus compares assembled prompts — that is the argument
`factory/verify/judge.py:409` — `_gate_blocks` makes in its own docstring about
why an empty gate list must assemble nothing, "because the judge's whole existing
test corpus compares assembled prompts and a heading over an empty list would
rewrite all of it". The same holds twice over here: a change that makes every user
message a content list turns every one of those comparisons red for a reason this
spec is not about, and the implementer's temptation will then be to update the
fixtures rather than to notice the design error. FR-007 requires the single-string
content whenever no image block was assembled, and US1-S2 is the test that pins it.

**Trap 4 — The component cannot spell this limit's other name, and the gate is the
whole suite.** `tests/test_final_sweep.py:614` — `test_the_component_cannot_even_spell_a_cap`
runs over every `factory/**/*.py`
(the module list is built at `tests/test_final_sweep.py:104`) and fails on any
identifier, argument name, keyword or **string constant** whose words intersect
`ENFORCEMENT_WORDS` (`tests/test_final_sweep.py:469`) — which contains `budget`,
`budgets`, `cap`, `caps`, `capped`, `quota`, `quotas`, `breach`, `breached`,
`enforce`, `exceed` and `exceeded`. Docstrings are exempt, and only docstrings:
the exemption is the `id(node) not in docstrings` test at
`tests/test_final_sweep.py:602` — `code_words`, which is why
`factory/verify/judge.py:473` — `prepare_diff` may say "Under the cap" in prose
and may not spell it in code. So the natural names for this spec's two new
constants and its withheld-reason strings — `ARTIFACT_BUDGET`, `image_cap`, a
message saying the artifact "exceeds" the limit — are all gate-red on the one
declared gate, which is the entire suite. Use `limit` or `bound`, and say "is
larger than" rather than "exceeds". The red arrives from a file this spec never
edits, which is why it reads like an unrelated failure.

**Trap 5 — The title overreaches; scope is the artifact channel.**
`factory/verify/gate_annotation.py:86` exists precisely because repositories
declare Playwright, Puppeteer and Cypress gates that drive real browsers here —
the three signatures are at `factory/verify/gate_annotation.py:90`,
`factory/verify/gate_annotation.py:92` and
`factory/verify/gate_annotation.py:94`. A spec chartered to "make the factory
render things" builds a screenshot verb, a browser driver and a headless
configuration nobody asked for, none of which the ledger row is about. Nothing in
this trio runs a browser, downloads one, or decides how a repository takes a
picture. A gate is an arbitrary command and it stays one.

**Trap 6 — The authoring layer must gain a door, not lose entries.**
`factory/cli/nouns/spec.py:1440` is a closed list and
`factory/cli/nouns/spec.py:1454` is the `visually` entry an implementer will reach
for first, because deleting it makes the failing example pass. It would also admit
every genuinely unprovable clause in every repository — the defect the list was
built from, reintroduced. FR-017 forbids removing any entry and requires a third
admission beside `factory/cli/nouns/spec.py:1513` — `_names_a_declared_gate`,
conditioned on the target repository's manifest declaring an `image` artifact.
FR-018's control is the other half: for a manifest that declares none, the refusal
must stay character-for-character today's, because
`factory/cli/nouns/spec.py:1605` — `_evidence_refusal`'s text is what operators
have in their runbooks.

**Trap 7 — `build_prompt` is pure, and the temptation is one line away.**
`factory/verify/judge.py:290` marks the section it lives in as pure assembly, and
every judge test calls `factory/verify/judge.py:307` — `build_prompt` directly.
134's `GateArtifact` carries the location its bytes were written to, so the
shortest path from records to prompt is to open that path inside the assembler.
Doing it puts a filesystem read into a pure function that runs in a hundred tests,
makes those tests need real files on disk, and puts an I/O failure inside prompt
assembly. FR-002 states the rule in the negative on purpose: the assembler takes
bytes or nothing, never a path, and US1's tests never write a file.

**Trap 8 — The bytes may not travel on the workflow payload, and workflow code may
not read them.** 134 kept the bytes off
`factory/verify/models.py:362` — `GateResult` because that record crosses a
Temporal activity boundary; putting an image on it is the outage 134 avoided.
`factory/workgraph/workflow.py:2901` — `_score` already carries the gate results
into the request at `factory/workgraph/workflow.py:2923` — `_score`, and it is
workflow code: it may read neither the filesystem nor the environment. So the only
place the read can happen is between
`factory/activities/verify_activities.py:430` — `run_judge` and
`factory/activities/verify_activities.py:444` — `run_judge`. An implementer who
adds a bytes field to
`factory/activities/verify_activities.py:399` — `RunJudgeInput` and fills it in
`_score` has written both errors at once, and the suite's workflow tests will not
necessarily catch either. FR-012 puts exactly one new field on that request, and
it is a bool.

**Trap 9 — A hand-built record proves nothing about what a gate declared.**
US1's tests construct artifact records and call the assembler; that is correct for
US1 and it is green before US2 exists. US2's tests may not do it. The claim US2
makes is that the activity reads what 134's collector wrote, so its fixtures must
start from a `GateResult` carrying `GateArtifact` records and a real file at the
stored location — with three exceptions that are the point: US2-S4's stored
location names a path that does **not** exist, which is how "the file is never
opened" is proven; US2-S5's first two records differ only in stored size; and its
third has no stored location at all while its fourth was never written. An implementer who tests US2 by handing
records straight to the assembler has re-tested US1 and shipped a channel
production never reads.

**Trap 10 — A plain bool cannot tell "declared false" from "undeclared", and the
deterministic refusal needs the difference.**
`factory/config.py:298` — `_build_persona` refuses `context_window` on a persona
that runs no agent by testing `is not None`, which works because
`factory/config.py:350` — `_optional_context_window` returns `int | None`. A
`vision` field parsed straight to `bool` with a `False` default gives that refusal
nothing to test: `vision: false` on a deterministic persona would be
indistinguishable from an entry that never mentioned it, and US2-S1's third case
cannot be written. Parse to `bool | None` — undeclared is `None` — the way
`factory/config.py:194` — `Persona` already declares its optional integer, and let
`factory/workgraph/models.py:295` — `ResolvedPersona` carry the plain bool with
its own default, which is the shape
`factory/workgraph/models.py:320` — `ResolvedPersona` already uses for `agent`.

**Trap 14 — Every new field crosses a Temporal payload boundary, and one without
a default makes yesterday's history undecodable.** Three of the four fields this
spec adds sit on records the worker puts on the wire —
`factory/workgraph/models.py:295` — `ResolvedPersona`,
`factory/activities/verify_activities.py:399` — `RunJudgeInput` and
`factory/verify/models.py:576` — `JudgeVerdict` — and
`tests/test_temporal_payload_shape.py:629` — `test_every_boundary_field_has_a_default_or_is_allowlisted`
sweeps all of them, failing any field that has neither a default nor an entry in
the allowlist whose `ResolvedPersona` line is
`tests/test_temporal_payload_shape.py:575` and whose `RunJudgeInput` line is
`tests/test_temporal_payload_shape.py:443`. The default is
not style: the converter builds each record with `cls(**decoded)`, so a field an
older payload never carried is a missing required argument and the operator meets
it as `__init__() missing 1 required positional argument` from whichever command
happened to ask. Give every new field a default — which is what FR-006, FR-011 and
FR-012 already require for their own reason — and add nothing to that allowlist:
an entry there says absence must stay loud, and "this judge was shown no picture"
is a fact, not an absence.

**Trap 11 — Do not pin the operator's dial, and this defect class has recurred
seven times.** The temptation in US2 is one line: assert that this repository's
own `personas.yaml` declares vision on the judge. Do not.
`tests/test_122_registry_is_not_pinned.py:372` — `test_no_assertion_about_the_shipped_registry_constrains_a_vendor_or_route`
reads the suite's own assertions about the shipped registry and fails when one
constrains a vendor or a route, and its module docstring records that every
previous fix in this class removed one literal and left the mechanism. This
repository's gate *is* the suite, so a pinned dial reds every node of every epic
until an operator puts the dial back. Test the loader against synthetic registries
written by the test — `tests/test_config.py:55` — `_entry` and
`tests/test_config.py:309` — `test_context_window_loads_as_positive_integer` are
the shapes to copy, with
`tests/test_config.py:345` — `test_deterministic_persona_with_a_context_window_is_rejected`
as the model for the refusal case. No story here edits `personas.yaml`; whether
this repository's judge is routed to a model that can be shown a picture is the
operator's decision, and it is verification step 4.

**Trap 12 — The declared type is semantic, the media type is not on the record,
and the two byte limits are not the same limit.** 134's vocabulary is `sbom`,
`coverage`, `scan`, `opaque`, and FR-008 adds `image` to it — but a content block
needs a media type, and no field on `GateArtifact` carries one. Do not sniff the
bytes: 134's FR-009 forbids the platform parsing an artifact's contents, and a
sniffer buys nothing a declaration does not. FR-013 resolves the media type from
the declared path's suffix against a named closed set, and an `image` artifact
whose suffix is outside that set arrives as a withheld record with that reason.
The second half of this trap is arithmetic. 134's FR-015 already bounds the bytes
it **stores** per artifact and records anything above it present, with its true
size and no stored location. This spec's per-artifact **show**-limit is a
different constant and must be **strictly smaller** than 134's, or its own
over-limit branch is unreachable in production. Strictly, not "no larger":
at equality every artifact that has a stored location is at or below the
show-limit, because nothing above 134's bound was ever stored — so US2-S5's first
case would be a fixture no collector could produce, the branch would be dead code
passing on a synthetic record, and this trap would permit the outcome it was
written against. And the artifact 134 recorded present with no stored location is
not "absent": it is its own withheld case with its own reason, distinct again
from the artifact 134 recorded as never written, which is why US2-S5 asserts four
records rather than two. Reusing 134's constant collapses the first distinction
and a careless reading of "not present" collapses the second.

**Trap 13 — This trio's own scenarios are bound by the layer US3 is changing.**
`factory/cli/nouns/spec.py:1781` — `_check_evidence` refuses a Then-clause naming
what only a running system shows, and it refuses this spec's scenarios too. Every
Then in spec.md is written about the assembled object, the record, the persona
declaration, the refusal string and the committed test — never about what the
picture shows — and any scenario added during the build must be written the same
way. An implementer who hits that refusal while writing a new criterion has met
the defect this spec exists to end, and the answer is still to phrase the clause
around the artifact rather than to relax the checker: US3 relaxes it exactly once,
under exactly one condition, and FR-017 forbids the broader move.

**Trap 15 — The activity cannot reach the assembler, and the one-line shortcut
skips the retry path.** The obvious reading of "build the records in the activity"
is that the activity then calls `factory/verify/judge.py:307` — `build_prompt`
itself. It must not.
`factory/activities/verify_activities.py:430` — `run_judge` calls the library at
`factory/activities/verify_activities.py:444` — `run_judge`, and the library
function `factory/verify/judge.py:752` — `run_judge` is what owns the completion,
the malformed-response RETRY, the retry ladder and the contradiction re-ask at
`factory/verify/judge.py:839` — `run_judge`. An activity that assembles its own
prompt and posts it has left all of that behind, and the tests that would catch it
are the ones nobody writes. FR-020 is why US4 owns the entry point: the records
travel on a parameter, exactly as `gate_results` does at
`factory/verify/judge.py:760` — `run_judge`. If US4 lands without that parameter,
US2 has nowhere to put its records and the shortcut is the only thing left, which
is why US2 merges after US4 and why US2-S3 asserts on the argument that entry
point was called with rather than on the assembler's.

**Trap 16 — The subtraction has no floor, and a big enough picture posts a judge
no diff at all.** FR-005 copies the gate section's accounting, but the gate
section is bounded per gate at `factory/verify/judge.py:218` and a picture is not.
Hand `factory/verify/judge.py:473` — `prepare_diff` a limit of zero — two declared
24 KiB PNGs will do it — and `factory/verify/judge.py:500` — `prepare_diff`
computes `allowance = max(limit - head, 0)` = 0, grants every section zero, and
returns a listing, a truncation notice and no code. The judge then scores every
scenario and returns a verdict, and nothing anywhere is red. That is the inverse
of the defect this spec exists to end: a judge shown a picture and no code. FR-022
bounds the whole artifacts section by its own named constant well under
`DIFF_INPUT_LIMIT` (`factory/verify/diffbounds.py:47`) and withholds the records
past it, and US1-S5 asserts the diff section is not empty when a picture is shown.
An implementer who writes only the subtraction has written the defect.

**Trap 17 — The verdict codec is longhand, and a field that skips it round-trips
as false forever, quietly.** `factory/verify/store.py:1238` — `_judge_to_dict` and
`factory/verify/store.py:1261` — `_judge_from_dict` name every field of
`JudgeVerdict` by hand; the docstring at
`factory/verify/store.py:1286` — `_contradiction_to_dict` says why, and what it
costs when a field is added to the record and not to them: "a record that
round-trips *almost* everything, quietly". Adding
`artifacts_shown` to `factory/verify/models.py:576` — `JudgeVerdict` gives every
in-memory test a true flag and every stored row a false one, and the story lands
green while the operator's verification steps 4 and 5 — the falsifiable test of
this whole spec — read `False` on a judge that was shown the picture. FR-021 is
the two lines, and they are US4's. Note also that spec 132 adds its own field to
these same two functions; if both epics run at once, expect a one-line conflict
there. It is not the only queued draft on this trio's files — trap 19.

**Trap 18 — The allowance shrinks by exactly the artifacts' bytes; the rendered
diff section does not.** FR-005 is an exact claim and it is exact about one
number only: the `limit` handed to
`factory/verify/judge.py:473` — `prepare_diff`. What comes back is not that
number less anything predictable.
`factory/verify/judge.py:542` — `_render_section` cuts on whole-line boundaries
and pays for an elision marker whose own width follows the digit count of the
number it prints (`factory/verify/judge.py:584` — `_marker`), and
`factory/verify/judge.py:515` — `_allocate` divides in integers. Measured on this
tree at `602a92c`, against a fixture of 13-byte lines at a limit of 20,000:
lowering the limit by 1 moved the rendered section by 0 bytes, by 100 moved it by
91, by 128 moved it by 130, by 512 moved it by 507, and only a lowering that
happened to be a multiple of the line width came out exact. An implementer told
to assert "exactly N bytes shorter" therefore meets a red no production change
can clear, and the two ways out are both wrong: weaken the assertion and be
scored against a criterion that said "exactly", or rewrite `prepare_diff`'s
line-boundary truncation and red the 116 suite. 116 met this wall and asserted the
threshold and the inequality instead —
`tests/test_116_judge_sees_gates.py:385` — `test_the_gate_section_is_spent_from_the_diffs_own_allowance`
and
`tests/test_116_judge_sees_gates.py:406` — `test_the_gate_section_and_the_diff_together_stay_under_the_input_limit`
— and US1-S4 and T004 now say exactly that. If the exact number is wanted, spy on
the limit `prepare_diff` was called with; never on the text it returned.

**Trap 19 — Three drafts are queued against these same files, and only one of
them is in the frontmatter.** `depends_on_landed` names 134 because this spec
cannot be built before it. Two more untracked drafts sit on this trio's own
production files and no gate can see either: `specs/133-spec-validate-has-one-implementation-and-two-faces`
cites `factory/cli/nouns/spec.py` 388 times and restructures that module, which is
US3's **only** production file and the source of every line anchor in US3's tasks;
and `specs/136-a-generated-file-does-not-spend-the-judges-attention` cites
`factory/verify/judge.py` 64 times and is about the judge's diff allowance — the
same accounting FR-005 tells the implementer to copy and FR-022 tells him to
bound. Spec 132 is the third, on the store codec (trap 17). None of them has
landed as of `602a92c` and nothing in the tree orders them against this one. So
the re-validate in step 2 of the operator's sequence is not only about 134: run it
after **any** of 134, 133 or 136 lands, and re-read `factory/verify/judge.py`'s
accounting before dispatching US1 if 136 landed first, because "copy the
gate-section subtraction" may by then name a different subtraction.

## Sizing

Sized against the only precedent that measures this work. Spec 116 built the same
channel in the same module and split it across three stories, and the landed diffs
are on the record: `6f4f0b1` (US1, five scenarios, five files, 713 insertions of
which `tests/test_116_judge_sees_gates.py` was 511) measured **39,687 diff bytes**;
`f0d2a14` (US2, five scenarios, 888 insertions) **44,444**; `8f5f633` (US3, three
scenarios, nine files, 883 insertions including a 124-line pasted attempt report)
**47,439**, which is 72% of the 64 KiB deterministic refusal at
`factory/verify/diffbounds.py:47` (D-050). Two numbers out of that: roughly a
hundred test lines per acceptance scenario, and roughly 56 diff bytes per
insertion. **Count the test module and the pasted evidence, not the production
lines** — in this repository the tests are three to five times the production
diff, which is what actually spends the bound, and the open ledger row
`verify/the-diff-budget-is-a-diligence-limit-not-a-complexity-limit-and-it-bites-hardest-on-a-story-that-tests-its-work-thoroughly`
records a clean first story refused at 73,973 bytes of which three test files were
42,938.

**US1** — one production file, `factory/verify/judge.py`: the widened message
type, the new pure record, the artifact section and its named constants, and the
accounting subtraction with its total bound. Five scenarios, so one new test
module beside the existing judge suite of roughly five hundred lines, around a
hundred and seventy production lines, and T009's two elided prompt dumps. That is
116-US1's shape almost exactly: ~750 insertions, ~42 KiB, two thirds of the bound.

**US4** — three production files and a fourth conditionally.
`factory/verify/judge.py` (the shown flag on `JudgePrompt`, through
`factory/verify/judge.py:591` — `parse_verdict`, and the four lines through
`factory/verify/judge.py:752` — `run_judge`), `factory/verify/models.py` (the
`image` member of 134's type enum and `artifacts_shown` on
`factory/verify/models.py:576` — `JudgeVerdict`), and `factory/verify/store.py`
(the two codec lines beside `gates_shown` at
`factory/verify/store.py:1257` — `_judge_to_dict` and
`factory/verify/store.py:1281` — `_judge_from_dict`).
`factory/verify/factory_yaml.py` is touched **only** if 134's reader spells the
artifact type set a second time instead of validating against the enum; check the
landed reader before assuming either way. Four scenarios, under fifty production
lines, tests in the judge suite, the evidence-store suite and whichever module
134's reader tests land in: ~450 insertions, ~25 KiB. It is a separate story from
US1 for one measured reason — together they are 116-US1 and 116-US3 in one PR,
which the arithmetic above puts past the refusal — and it is one story rather than
three because a flag defined in one story and persisted in another reads false on
every row in between.

**US2** — five production files, four of them one line each:
`factory/config.py` (the optional field, its parser and the deterministic
refusal), `factory/workgraph/models.py` (one defaulted field on
`factory/workgraph/models.py:295` — `ResolvedPersona`),
`factory/activities/agent_activities.py` (fill it at
`factory/activities/agent_activities.py:370` — `resolve_persona`),
`factory/workgraph/workflow.py` (fill it at
`factory/workgraph/workflow.py:1267` — `_resolve` and
`factory/workgraph/workflow.py:1285` — `_resolve`, and read it at
`factory/workgraph/workflow.py:2923` — `_score`), and
`factory/activities/verify_activities.py`, which carries the whole of the story's
substance: one bool on
`factory/activities/verify_activities.py:399` — `RunJudgeInput`, one named
show-limit, one named media-type set, and the function that turns gate results
into artifact records handed to the entry point's parameter.
`personas.example.yaml` gains one documented field line at
`personas.example.yaml:19`. Its tests touch
`tests/test_config.py` (the registry cases), one new module for the activity's
admission table, and the persona-resolution suite. Six scenarios and under a
hundred and fifty production lines: ~800 insertions, ~45 KiB. This is the tightest
story in the trio; if it grows during the build, the seam is between the persona
chain (FR-010, FR-011, FR-012) and the activity's admission table (FR-013,
FR-014, FR-015), and the story to split off takes a new number.

**US3** — one production file, `factory/cli/nouns/spec.py`: the artifact set on
`factory/cli/nouns/spec.py:1539` — `_Declarations`, its fill at
`factory/cli/nouns/spec.py:1559` — `_declared_gates`, the admission at
`factory/cli/nouns/spec.py:1830` — `_check_evidence`, the third remedy at
`factory/cli/nouns/spec.py:1605` — `_evidence_refusal`, and the report field at
`factory/cli/nouns/spec.py:1685` — `as_dict`. Four scenarios, cases added to the
existing validate suite, under fifty production lines: ~350 insertions, ~20 KiB.

One production file is shared, and the graph orders it: US1 and US4 both edit
`factory/verify/judge.py`, and US4 merges after US1, so they are never in flight
against the same base. Beyond that pair no two stories name a production file in
common — US2 owns the persona chain and the judge activity, US3 owns
`factory/cli/nouns/spec.py`, and the only file either of them reads *about* is
`factory/verify/models.py`, which only US4 edits.

Note for whoever sizes the evidence: a pasted judge prompt is text and cheap only
when **both** of its large halves are elided. An assembled prompt that carries a
picture carries it base64-encoded — that is the picture, in text, spending the
same 64 KiB the code does — and the same prompt's diff section is fitted up to
`DIFF_INPUT_LIMIT`, which is the whole story bound on its own, on a fixture the
accounting tasks deliberately make large. **No story may commit a screenshot as
its evidence, and that includes a prompt dump that still has the payload or the
diff body in it**: paste the media type, the byte length and a hash where the
bytes were, and the heading, the byte length and the first and last few lines
where the diff section was. The artifact these stories build is the channel, not
the picture.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only, so
runtime evidence is committed as pasted output. Beyond that:

1. Confirm the amendment exists before anything is dispatched: Principle VIII in
   `.specify/memory/constitution.md:63` admits the factory's own measurements of
   the attempt — its gate results and its gates' declared artifacts — and
   `docs/decisions.md` carries a new entry saying so, which also records that 116
   admitted gate results on 2026-08-31 without one. Nothing in the gate can check
   this, and a spec flipped ready without it dispatches stories whose own
   standards document forbids what they build.
2. Re-run `ergane spec validate specs/144-the-judge-can-look-at-what-the-story-built
   --target-repo <this repository> --specs-root specs` **after any of 134, 133 or
   136 has landed** and before the flag is flipped. 134 edits
   `factory/verify/models.py` and `factory/activities/verify_activities.py`, which
   most of this trio's anchors point into; 133 restructures
   `factory/cli/nouns/spec.py`, which is US3's only production file and the source
   of every anchor in its tasks; 136 changes the judge's diff allowance in
   `factory/verify/judge.py`, which is the accounting US1 copies (trap 19). The
   anchors are written in the symbol-tier form so that drift is machine-caught at
   exactly this moment, and nothing catches it otherwise — and if 136 landed
   first, re-read the subtraction at
   `factory/verify/judge.py:345` — `build_prompt` by hand before dispatching US1,
   because validate can see that a line moved and not that the instruction is now
   the wrong one.
3. On a scratch target repository, declare a gate that writes a PNG and declare
   that file as an `image` artifact. Run one node. Read the stored artifact
   through 134's reader and confirm the bytes are there.
4. Set the judge persona's vision declaration in the operator's own registry
   (`~/.config/ergane/personas.yaml`, never this repository's `personas.yaml`) and
   dispatch again. Read the recorded verdict row and confirm the shown flag is
   true and the judge's reasoning refers to the picture.
5. Remove that declaration and dispatch a third time. Confirm the shown flag is
   false on the row, that the judge's prompt carried the withheld line naming the
   gate and the path, and that the verdict is a verdict rather than an outage — a
   judge that cannot see must still score the diff.
6. Declare a picture large enough to spend the artifacts section's whole bound and
   dispatch once more. Confirm the prompt still carries a diff section with code
   in it, and that the surplus artifacts appear as withheld lines naming the bound.
7. Write a spec whose Then-clause names the declared artifact path and run
   `ergane spec validate --target-repo <that repository>`. Confirm it is admitted.
   Delete the `artifacts:` line from that manifest and re-run: the same clause
   must be refused, and the refusal must not name the artifact door.

Step 5 is the falsifiable test of the whole spec, and it is only runnable because
FR-021 puts the flag on the stored row. A channel that shows the picture when it
can is worth little beside one that says, on the row, that it could not — because
the failure this spec was written from is twelve stories, four gates and a judge
all reading green on a product nobody had looked at.
