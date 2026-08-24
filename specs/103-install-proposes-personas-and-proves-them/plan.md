# Implementation Plan: install proposes personas and proves them

**Spec**: `specs/103-install-proposes-personas-and-proves-them/spec.md`
**Evidence base**: `docs/container-onramp-research-findings.md` §5 — the
prior-art survey behind every ruling. Read it before proposing a different
interaction pattern; the rulings are deliberate.

## What already exists, and where

**Every line number below was read individually off `838b9c3` on 2026-08-23.**
Re-verify before flipping to ready, per house rule.

**The registry and its vocabulary (`factory/config.py`):**

- `:44` `REGISTRY_FILENAME`, `:47` `DEFAULT_REGISTRY_REL` — where the operator
  copy lives (`~/.config/ergane/personas.yaml` via XDG).
- `:57` `EXAMPLE_ALIAS_PREFIXES = ("example/",)`, `:76-78` `is_example_alias`
  — what "unconfigured" means, mechanically.
- `:60-73` `shipped_registry_text()` — the example text install seeds; US4
  rewrites *alias fields within* this text, so parse-and-rewrite must keep
  every other field and comment intact or regenerate faithfully. Decide
  early: a YAML round-trip loses comments; writing the file from the parsed
  personas plus a generated header is the honest shape. Say in the header
  that the file was written by install and how to regenerate.
- `:143` `DETERMINISTIC_AGENT = "none"`, `:149` `SUBSCRIPTION_AGENT` — the
  two exemptions US4 must honour.
- `:170` `Persona` — fields; `:196-199` `is_llm`; `:202-208`
  `routes_through_gateway` — **the predicate that decides probed vs
  confirmed vs skipped.** Use it; do not re-derive from `agent` strings.
- `:219` `load_personas` — validate the written file by loading it back
  before declaring success; `ConfigError` on your own output is a failed
  install, not a warning.

**The scan and its security stance (`factory/discovery/llm_scanner.py`):**

- `:1-8` — the module docstring: unauthenticated by design, injected
  `httpx.AsyncBaseTransport` seam (FR-005 of its own spec). **Enrichment
  copies the seam discipline, not the unauthenticated stance** — it runs
  post-confirmation with the operator's named key env.
- `:28-36` `ScanResult` — `aliases` at `:33` is the tuple US1 enriches.
- `:46-47` — `_MODELS_PATH`, `_KEY_GENERATE_PATH` — the existing endpoint
  vocabulary; add enrichment paths beside them, same style.
- `:64-87` `scan_endpoints` — sync wrapper over async with injected
  transport; copy this shape for the enrichment entry point.

**The interview (`factory/cli/install.py`):**

- `:250` `install_command` — the interactive path; the seed call at
  `:261-263` (`_seed_personas_registry` defined at `:300-317`). US4's new
  step runs *after* `_interview` returns a valid document and *before*
  `verify_controlplane` — the registry must be written before verify probes
  it, which is what makes SC-004's "verify passes in the same run" real.
- `:320` `_install_non_interactive` (seed at `:347-349`) and `:414`
  `_install_from_file` (seed at `:441-443`) — FR-010: untouched.
- `:384-412` `_FilePrompter` — the test seam US4's end-to-end interview test
  drives; its `ask` signature at `:398` is what your persona lines must go
  through, so the transcript is assertable.
- `:684-700` `_interview` — the subsystem order; the scan at `:693` is
  advisory. Your step consumes the *confirmed* document (`document["llm"]`
  mode/base_url/master_key_env), not the scan result — the scan may have
  found a different endpoint than the operator confirmed.
- `:722-783` `_ask_llm` — how mode decides follow-ups; `:950` `_ask` — the
  question primitive with `default=` and `apply=`; reuse it for persona
  lines rather than inventing a second prompt shape.
- `:1144-1158` `_llm_scan` — first-dispatchable-wins; `:1161` `_offered_llm_mode`.

**The probe machinery US3/US4 stand on (`factory/controlplane/verify.py`):**

- `:67` `LLMSnapshot`, `:77` `LLMAliasResult` — existing result shapes.
- `:318-335` `gather_gateway_aliases` — excludes deterministic and
  subscription personas (`:326-331`); the same exclusion governs which
  personas get probes.
- `:340` `class LLMProbe` — the client seam; `:420-460` the key-management
  probe: mint short-TTL model-constrained key, check spend logs, **revoke in
  a `finally`** (`:446-450`). The canary runs under this discipline —
  FR-005 says so and US3-S3 tests it.
- `:466-480` `_probe_one_alias` — the 1-token completion (`max_tokens: 1`,
  `bool(choices)`); US4 reuses it per chosen alias.
- `:373-381` — the all-example refusal inside the probe path: after US4, a
  successfully-written registry makes this branch unreachable on the happy
  path; it stays for the non-interactive paths (FR-010).

**The requirements printer (`factory/cli/nouns/install.py`):**

- `:59-110` — `--requirements`: derives alias→personas and prints what the
  gateway must serve; `:95-99` the example refusal. After US4 this printer's
  output on a fresh interactive install lists real aliases — no change
  needed, but its tests must not assume `example/` forever.

## Traps

**1. Do not send the master key to anything the operator has not confirmed.**
The scan's docstring states the rationale (`llm_scanner.py:3-8`). Enrichment
reads the *confirmed document's* base_url and key env — not the scan result's
address. If they differ, the operator's answer wins.

**2. The registry write must survive `load_personas` round-trip.** Write,
then load with `factory/config.py:219`, then verify. A write that produces a
`ConfigError` is install failing, and the error must name the file as
install-written. Never leave a half-written file on the failure path —
write to a temp file and rename, or write only after all probes pass
(FR-007 orders it: probe first, write once).

**3. The judge canary's known-bad diff is a fixture, not an LLM artifact.**
Commit the toy diff, criteria and schema as test/package data. A canary that
generates its own test case cannot distinguish a wrong model from a wrong
fixture.

**4. Three distinct canary failure reasons, asserted distinctly.** Prose,
schema violation, wrong verdict — collapse them and the operator sees
"canary failed" with nothing to act on (US3-S2 wants three).

**5. `max_tokens` on the canary must be generous.** Operator memory: a
reasoning model under a tight cap returns empty content that looks like a
broken gateway. The 1-token completion probe is exempt (its check is
`bool(choices)`, `:471`); the canary needs real output — give it an explicit
budget in the hundreds of tokens and assert on parsed JSON, not on length.

**6. The blanket-accept exemption is structural, not textual.** FR-006 says
the judge and fallbacks are exempt from any blanket accept. If US4 adds an
"accept all" affordance, the exemption lives in the code path (those
personas re-prompt), not in a printed warning. Test through the
`_FilePrompter` transcript: an all-Enter answer file still yields explicit
questions for judge and fallbacks.

**7. Interview seams, not network, in every US4 test.** The end-to-end
interview test injects enrichment fixtures and a fake probe client; no test
opens a socket. The scanner's own tests (`llm_scanner.py:3-5`) are the
precedent.

**8. Do not double-probe.** `verify_controlplane` will re-probe every alias
right after install writes the registry (`install_command` calls it at
`:281-284`). That is correct and cheap (1 token per alias) — do not
special-case verify to skip aliases US4 already probed; the redundancy is
the proof the written file works via the production path.

**9. Subscription personas: confirm, never probe, never skip silently.**
`routes_through_gateway` (`factory/config.py:202-208`) is the predicate.
The operator sees the CLI-side model name and confirms it (US4-S5); the
transcript proves the question was asked.

**10. The judge sees the diff and the criteria, nothing else** (Principle
VIII). Every SC is pasted output committed in the diff.

## Sizing

US1 and US3 are small, well-bounded modules with injected transports. US2 is
pure functions plus a data table — the easiest story here, but the table's
*content* is judgement: take the requirements rows from the spec's ruling
verbatim. US4 is the largest and the one to watch: it touches the interview,
the write path, and the failure paths, and its tests are transcript-driven.
If it needs splitting at refinement, the seam is "picker + write" vs
"probe wiring" — but try it whole first; the pieces share every fixture.

## What else is in flight, and why it does not collide

088 (container) touches `factory/controlplane/verify.py` — **the same file
as US3/US4's probe reuse** — but its US1 edits `_inspect_host` (`:253-298`)
and this spec reads the LLM probe section (`:318-480`). Disjoint regions,
same file: the merge queue handles it, but do not dispatch 088-US1 and
103-US4 into the same attempt window if the operator can avoid it; a
speculative-merge conflict here costs an ejection that the poller cannot
see (operator memory: queue ejection is invisible). 104/105/106 do not touch
these files.

## Verification the operator will run, independent of the gate

- **A real interactive install against the homelab LiteLLM**: watch the
  proposals, accept, watch probes, confirm the written file and the passing
  verify. This is the run that makes the story real.
- **Unplug test**: point install at a gateway with one model only and
  confirm the judge-independence preference degrades gracefully (same alias
  allowed when it is the only qualifier) rather than refusing.
- **The canary against a genuinely weak model** (a small local model via
  Ollama): confirm it fails the known-bad-diff check — the canary's reason
  to exist is that this happens.
