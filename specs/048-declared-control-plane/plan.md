# Plan: 048-declared-control-plane

Refined against the tree at `4ce493d` on 2026-08-16. Every line anchor below was
opened and read by hand at that commit; re-check them if the tree moves before
dispatch. Three anchors in the originating finding were already stale when this
plan was written — see "What the finding got wrong" — which is the standing
argument for checking rather than citing.

Findings this spec closes:

| Finding | Sev | Story |
| --- | --- | --- |
| `install/the-config-install-writes-reaches-nothing-that-builds` (consequence 1: the declared endpoint reaches no build) | critical | US1, made visible by US3 |
| `install/the-config-install-writes-reaches-nothing-that-builds` (consequence 2: `direct` verifies green and cannot dispatch) | critical | US2 |

The finding is one ledger entry with two consequences. It is not resolved until
both are closed, so `ergane findings resolve` waits for US1 and US2 together.
US4 closes the same class one subsystem over and has no ledger entry of its own;
file one only if it is split out.

## The inversion — read this before anything else

The story this defect appears to tell is "install declares, the build ignores,
they drifted apart". The tree tells a different one, and the difference decides
how much of this spec is US2's.

`direct` mode — which **cannot** dispatch — verifies cleanly on a host with no
`LITELLM_*` variable set. Its probe uses only declared values
(`verify.py:218-232`, called at `:250`).

`gateway` mode — which **can** dispatch — does not. `LLMProbe.gather` resolves
the credential correctly through the declared name at `verify.py:206-207`, then
builds its client through `LiteLLMClient.from_env()` at `verify.py:110`, which
reads the legacy variables. Both halves of the collision are inside one
function. The repository's own test admits it:

```python
# tests/test_controlplane_verify.py:927-933
monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake-master")
# LiteLLMClient.from_env() is called first and requires these env vars.
monkeypatch.setenv("LITELLM_PROXY_URL", "http://127.0.0.1:1")
monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-dummy")
```

Three variables, two naming schemes, to verify one endpoint. A subsystem that
had drifted would verify its declaration and fail at use. This one verifies a
declaration it cannot use and fails to verify the one it can. Declaration and
consumption were never joined; there was no moment at which they agreed.

## What already exists, and where

### The environment side — what builds today

| Thing | Location | Note |
| --- | --- | --- |
| `PROXY_URL_ENV` / `MASTER_KEY_ENV` | `factory/usage/litellm_client.py:56-57` | `"LITELLM_PROXY_URL"` / `"LITELLM_MASTER_KEY"`. Read these names; never restate the strings. |
| `LiteLLMClient.from_env` | `factory/usage/litellm_client.py:134-157` | Reads `PROXY_URL_ENV` at `:146`, checks `MASTER_KEY_ENV` at `:149`, reads it at `:154`. **Raises naming the variable name only** (`:148`, `:150`) — the discipline FR-003 preserves. |
| `from_env`'s callers | `factory/workgraph/cli.py:113`, `factory/cli/nouns/__init__.py:39`, `factory/activities/usage_activities.py:164`, `factory/controlplane/verify.py:110`, `factory/doctor/probes.py:253` | **Five, not two.** All are CLI, activity or probe scope; none is workflow scope, so a config read inside `from_env` breaks no determinism rule. |
| `_master_key_from_env` | `factory/activities/roadmap_activities.py:348-357` | The sixth path: `os.environ["LITELLM_MASTER_KEY"]` at `:357`, used by `_preflight_client` at `:345`, which constructs a client directly instead of via `from_env`. It takes `proxy_url` as an argument, so only the credential half needs the resolver here. |
| `open_client` seam | `factory/activities/usage_activities.py:158-164` | The activities' one route to the proxy; tests replace it. `issue_attempt_key` calls it at `:197` and treats `LiteLLMError` as permanent at `:198-200`. |
| `issue_attempt_key` | `factory/activities/usage_activities.py:180-181` | Mints a LiteLLM virtual key (`client.issue_key`, `:209`). This is why US2 refuses `direct`: there is one credential primitive and it is a proxy virtual key. |
| Epic start, live | `factory/cli/nouns/build.py:371-378` | `os.environ.get(PROXY_URL_ENV)`, the refusal at `:373-376`, `EpicInput(..., proxy_url=proxy_url)` at `:404-408`. This is the noun `ergane build start` dispatches to (`start_command` at `:348`, wired at `:764`). |
| Epic start, duplicate | `factory/workgraph/cli.py:457-467` | A byte-for-byte second copy of the same refusal, still imported (`factory/cli/repo.py:45`, `factory/cli/nouns/spec.py:31`) and still driven by `tests/test_workgraph_sweep.py` and `tests/test_live_epic.py`. FR-006 covers it. |
| Roadmap start | `factory/cli/roadmap.py:203-206` | `args.proxy_url or os.environ.get(PROXY_URL_ENV, "")`, refusal at `:205-207`, `RoadmapInput(..., proxy_url=...)` at `:214`. The `--proxy-url` flag defaults from the same variable at `:86`. |
| Where the URL ends up | `factory/workgraph/workflow.py:415` (`EpicInput.proxy_url`), `factory/roadmap/workflow.py:211`, `AttemptContext.proxy_url` at `factory/workgraph/models.py:310`, `ANTHROPIC_BASE_URL` at `factory/workgraph/adapter.py:760` | **The endpoint is already a declared workflow input threaded from the CLI.** The workflow never reads it from the environment. That is why US1's endpoint resolution belongs at the CLI boundary and needs no workflow change at all. |
| `ergane env` | `factory/cli/env.py:30-38`, `:51-62` | `_ENTRIES` labels both variables `required` at `:33-34`; `_SECRET_VARS` at `:27` is why `MASTER_KEY_ENV` prints `[REDACTED]`. US3's whole surface. |
| PR-body sweep | `factory/activities/merge_activities.py:339-340` → `factory/mergequeue/messages.py:82` | Reads both variables and drops them on the floor by design (`_ = (...)`). Not a consumer. Out of scope; do not touch. |
| `ergane --version` | `factory/cli/main.py:154` | Prints the proxy URL or `"not configured"`. Cosmetic for US1; US4 touches the adjacent Temporal lines at `:152-153`. |

### The config side — what install writes

| Thing | Location | Note |
| --- | --- | --- |
| `ControlPlaneConfig.LLMGateway` | `factory/controlplane/config.py:119-125` | `base_url`, `master_key_env`, `timeout_s`. `master_key_env` holds a **variable name**, never a key — the shape FR-003 depends on. |
| `_read_llm` | `factory/controlplane/config.py:317-341` | Gateway branch at `:332-341`. Note the TOML shape: `base_url` and `master_key_env` sit at the top level of `[llm]`, not under an `[llm.gateway]` table; only the *typed* form nests them. |
| `_require_secret_ref` / `_reject_secret_shape` | `factory/controlplane/config.py:765-785`, `:799-808` | The parser already refuses a value that looks like a credential where a variable name belongs. Nothing in this spec may weaken this. |
| `LLMGateway.timeout_s` | `factory/controlplane/config.py:125` | Dead: nothing sets it from the block, and `controlplane_document` deliberately does not render `llm.timeout_s` (`:576-578`). Do not start honouring it in this spec; if you want to, that is its own story. |
| `load_controlplane_config` / `resolve_config_path` | `factory/controlplane/config.py:197-234`, `:174-187` | Path precedence is `ERGANE_CONFIG_PATH` → `FACTORY_CONFIG_PATH` → `$XDG_CONFIG_HOME/ergane/config.toml` → `~/.config/ergane/config.toml`, via `resolve_env_path` (`factory/env.py:49`). A missing file raises `RULE_CONFIG_MISSING` (`:209-215`), not `FileNotFoundError`. |
| Degrade-gracefully precedent | `factory/registry.py:214-227`, `factory/notify/adapter.py:237-258` | Both read the control-plane config and both return `None` when it is absent or refused, rather than raising, because their callers must work on an unprovisioned host. Read both before choosing US1's failure shape — and note US1's shape is *different*, see trap 3. |

### The `direct` apparatus US2 removes

| Thing | Location |
| --- | --- |
| `KNOWN_LL_MODES = ("gateway", "direct")` | `factory/controlplane/config.py:31` |
| `LLMDirectPersona`, `LLM.personas` | `factory/controlplane/config.py:109-117`, `:132` |
| `_read_llm`'s direct branch | `factory/controlplane/config.py:328-330` |
| `_read_direct_personas` | `factory/controlplane/config.py:344-395` |
| Persona rendering | `factory/controlplane/config.py:567` (`_PERSONA_ORDER`), `:583-597`, `:658-670` |
| `_PERSONA_SEED`, `_apply_llm_mode`'s direct arm | `factory/cli/install.py:83-88`, `:501-502` |
| The mode question and its branch | `factory/cli/install.py:186`, `:193-194` |
| `_ask_personas` | `factory/cli/install.py:214-249` |
| `LLMProbe`'s direct branch | `factory/controlplane/verify.py:182-197`, and the `_do_completion` call at `:249-250` |
| `_llm_client_factory`'s direct refusal | `factory/controlplane/verify.py:102-111` — dead already: it is only called from the gateway arm at `:236`, so the `raise` at `:111` is unreachable. |

### The refusal pattern US2 copies

`temporal.mode = "managed"` is a token the parser recognizes and refuses until
042 lands: listed in `KNOWN_TEMPORAL_MODES` (`config.py:39`), slug
`RULE_TEMPORAL_MANAGED_NOT_IMPLEMENTED` (`config.py:54`), raised at
`config.py:437-443` with a message naming the epic that will deliver it. Copy
that shape exactly, and cite it in FR-014's decision entry. It is why `direct`
stays in `KNOWN_LL_MODES` rather than being deleted from it: a
recognized-but-refused token produces a specific message, and an unknown one
produces "supported modes are 'gateway'", which tells a user who chose `direct`
nothing about why.

### Temporal's surface (US4)

The interview writes the declaration at `factory/cli/install.py:294-309`
(address at `:296`, namespace at `:304`). **Ten** sites connect, none reading
it:

| Site | Line | Note |
| --- | --- | --- |
| `factory/worker.py` | `:221-222` | The worker process itself. Trap 1 applies hardest here. |
| `factory/cli/nouns/__init__.py` | `:51-52` | `_open_client`, the CLI's shared seam. |
| `factory/cli/main.py` | `:152-153` | The `--version` banner. Cosmetic, but it is an operator-facing claim about where this install points. |
| `factory/cli/roadmap.py` | `:183-184` | |
| `factory/cli/repo.py` | `:62-63` | |
| `factory/workgraph/cli.py` | `:778-779` | |
| `factory/notify/service.py` | `:678-679` | |
| `factory/doctor/probes.py` | `:483-484` | **Hardcoded literals** `"TEMPORAL_ADDRESS"` / `"localhost:7233"` rather than the constants. |
| `factory/controlplane/verify.py` | `:118-119` | `_temporal_client_factory` — **config first, env fallback.** |
| `factory/controlplane/verify.py` | `:308-309` | `TemporalProbe.gather` — same inverted precedence, same hardcoded literals. |

The constants are `TEMPORAL_ADDRESS_ENV` / `TEMPORAL_NAMESPACE_ENV` and
`DEFAULT_TEMPORAL_ADDRESS = "localhost:7233"` /
`DEFAULT_TEMPORAL_NAMESPACE = "factory"` at `factory/notify/service.py:105-111`.
The defaults happen to agree with the four hardcoded copies today; that is luck,
not design, and FR-015 ends it.

The last two rows are the story's real content. Everywhere else reads the
environment only; verification reads the config first. Where the two disagree,
`ergane install --verify` reports on one server and the worker connects to
another — a green check about a machine nothing runs on (US4-S3, SC-006).

## What the finding got wrong

Correct these in your head before you start; the ledger entry is evidence, not
scripture. (The operator is amending the entry itself; this list is what the
amendment covers.)

1. "The only consumers of the written config are `factory/cli/install.py` and
   `factory/controlplane/verify.py`." There are six:
   `factory/registry.py:223`, `factory/notify/adapter.py:255` and
   `factory/cli/init.py:649` also consume it. The config is not dead; the
   dispatch path is deaf.
2. "`ergane build start` reads `proxy_url` from `os.environ[PROXY_URL_ENV]`" —
   true at `factory/cli/nouns/build.py:371`, but there are **three** such sites
   (`workgraph/cli.py:457`, `cli/roadmap.py:203`), plus `merge_activities.py:339-340`
   and `cli/main.py:154` which read and discard. Fixing one is not fixing the
   class; FR-006 exists for that reason.
3. "A user completes install, sees five PASS findings, then the build fails."
   True for `direct`, false for `gateway` — see "The inversion" above. The
   correction matters because it moves US2 from tidying-up to load-bearing.
4. The sibling finding it names —
   `install/the-wheel-ships-no-persona-registry…` — is **already fixed** in
   `b63388c` (#103), with `pyproject.toml:44-45` force-including the registry
   and `tests/test_installed_layout.py` pinning it. The ledger is stale. Do not
   re-fix it and do not cite it as still-open in any commit.

## Route choices left to the implementer

**Where the resolver lives.** Recommended: a new module
`factory/controlplane/resolve.py` returning one frozen value object per
subsystem, carrying no secret. For the LLM gateway, four fields:

```
base_url            the resolved endpoint
base_url_source     "LITELLM_PROXY_URL" | "<config path>"
master_key_env      the NAME of the variable holding the credential
master_key_source   "LITELLM_MASTER_KEY" | "<config path>"
```

Everything US1, US3 and US4 need is in that object, and because it holds only
names and a URL, FR-003 and SC-005 are true by construction rather than by
discipline — which is the point of choosing this shape over returning a
`(url, key)` pair. The credential value is fetched at the last moment by
whoever needs it, exactly as `from_env` fetches it today. US4 adds a sibling
object of the same shape for address and namespace; if the two want a shared
helper, write it — but do not generalise it into a framework, there are two.

Rejected alternative: putting the precedence inside
`factory/usage/litellm_client.py`. That module's docstring (`:1-24`) is a
promise that it is the *proxy* seam; teaching it to read TOML from `~` makes it
two things, and it forces `factory.usage` to import `factory.controlplane`,
which is the wrong direction — `controlplane/verify.py:29` already imports the
other way.

**Do not rename `from_env`.** The name becomes slightly inaccurate. Renaming it
costs edits at five call sites plus their tests for no behavioural gain, and
diff size is a real constraint here. Delegate from it and leave the name; say so
in the commit message.

**Where the endpoint resolves.** At the three CLI entry points, before the
workflow input is built (`build.py:371`, `workgraph/cli.py:457`,
`roadmap.py:203`). Nothing in `factory/workgraph/workflow.py` or
`factory/roadmap/workflow.py` changes: the endpoint is *already* a declared
input (`workflow.py:415`, `roadmap/workflow.py:211`), and that is the property
that makes this story cheap.

**Where the credential resolves.** Inside `LiteLLMClient.from_env`
(`litellm_client.py:134-157`) and inside `_master_key_from_env`
(`roadmap_activities.py:348`). Both are activity/CLI scope. Both must end up
consulting the same resolver, or the roadmap and the epic will disagree about
which host they are on.

**US3 is a new `--sources` mode, not a changed default.** The bare command's
output is something an operator may already be reading on an unfamiliar
machine, and rewriting a diagnostic's default output inside the spec whose
whole point is that diagnostics were lying is the wrong trade. The one
exception is the word `required` at `env.py:33-34`, which US1 makes untrue;
correcting a word that has become false is not the same act as restructuring
the report, and FR-017 pins everything else to byte-parity so the distinction
is enforced rather than promised.

**How SC-004's control seam works.** The disable must be explicit — a keyword
argument, a module-level default, an injected loader — never an environment
read. A control implemented as "unset a variable" is not a control; it is the
same code path.

## Traps

**Trap 1 — this host must keep working, untouched.** The worker running on this
machine right now reads `LITELLM_PROXY_URL`, `LITELLM_MASTER_KEY` and
`TEMPORAL_ADDRESS` from an environment loaded by `scripts/ergane-env.sh`, and
there is no `~/.config/ergane/config.toml` behind it that would resolve. A
change that requires re-provisioning this machine to keep building is a failed
change, not a migration. Override-wins is not a nicety; it is the acceptance
condition (US1-S2, US1-S8, US4-S2, SC-001). Write the override test first, in
both stories.

**Trap 2 — workflow code may not read the environment or the disk.**
`tests/test_workflow_env_guard.py` walks the AST of every module carrying
`@workflow.defn` and fails on `os.environ`, `environ.get` or `os.getenv`
reachable at workflow scope (the guard itself is at `:36-67`, the test at
`:227`). It exists because 039 had to be written after one workflow-scope
`os.environ` read silently disabled the entire roadmap schedule. The guard does
not yet know about *file* reads — so a `load_controlplane_config()` inside a
workflow would pass the guard and break replay determinism anyway. Resolution
lives at a CLI boundary or in an activity. Nowhere else.

**Trap 3 — degrade for a *missing* config, refuse for a *broken* one.**
`factory/registry.py:224` and `factory/notify/adapter.py:256` swallow
`ControlPlaneConfigError` wholesale, because a repo registration must not
depend on a provisioned engine. US1 must not copy that reflexively. The
distinction FR-004 and FR-005 draw:

- overrides set → never open the file (US1-S3);
- no override, no file → refuse naming both routes (US1-S4);
- no override, file present but refused by the parser → surface the parser's
  reason and the path (US1-S5).

The third is the one that matters. An operator who typo'd their config and is
told "`LITELLM_PROXY_URL` is not set" will export a variable instead of fixing
the file, and will conclude the config does nothing — which is precisely the
belief this spec exists to end.

**Trap 4 — a config-resolution test that reads the operator's real config
cannot fail here and behaves differently elsewhere.** `resolve_config_path()`
falls back to `$XDG_CONFIG_HOME` and then `Path.home()` (`config.py:190-194`).
A test that forgets to bind the path is reading `~/.config/ergane/config.toml`
on this host — a file that exists, that the operator edits, and that will not
exist on the grader's. Every test in this spec's diff sets `ERGANE_CONFIG_PATH`
to a `tmp_path` or passes an explicit path argument (FR-012). This is the same
class as the store-isolation defect of 2026-08-14, where a test's only green
condition on a working host was deleting production data.

**Trap 5 — ask of every test what would make it pass if the production code did
nothing.** Four tests in this repository were found last week to be
structurally unable to fail. The shape to avoid here is a resolution test that
plants the *same* value in the environment and the config: it passes whichever
source the resolver actually consulted, and proves nothing. Fixture configs and
fixture environments must disagree on every value they both carry (US1-S2 and
US4-S2 say so explicitly), and the parity tests must be written against the
*current* construction so they fail the moment behaviour moves.

**Trap 6 — the sentinel tests must plant a value that could leak.** US1-S7 and
US3-S3 are worth nothing if the fixture credential is `""` or absent. Plant a
distinctive string, resolve successfully, and assert its absence from the
`repr`, the rendered output and the workflow input. That is the only shape in
which SC-005 is evidence rather than a claim.

**Trap 7 — `direct` is refused at parse, which means every existing `direct`
test flips.** `tests/test_controlplane_config.py`,
`tests/test_controlplane_verify.py` and `tests/test_ergane_install_walkthrough.py`
carry direct-mode cases. They are not collateral damage to be deleted quietly —
each one becomes the refusal's test or is removed with a reason. A US2 diff that
drops a test file wholesale will be read as hiding a regression, and rightly.

**Trap 8 — `direct` stays in `KNOWN_LL_MODES`.** Deleting the token makes the
message "supported modes are 'gateway'", which answers a different question
than the one a user who chose `direct` is asking. Keep it recognized, refuse it
specifically, exactly as `managed` is handled at `config.py:39` / `:54` /
`:437-443`.

**Trap 9 — the interview validates through the parser, so US2 is mostly
subtraction.** `_ask` (`factory/cli/install.py:381-422`) renders the candidate
document and hands it to `parse_controlplane_config` at `:416-418`; a refusal
re-asks the question carrying the message. So the moment the parser refuses
`direct`, the interview refuses it too, for free — US2-S2's committed test just
pins that. What US2 must still do by hand is stop *offering* it in the prompt
text (`:186`) and stop seeding it (`:501-502`). Do not build a second rule
table; 033 spent a story on not having one.

**Trap 10 — keep the credential out of the error, and keep the value out of the
`repr`.** `from_env` raises naming only the variable name
(`litellm_client.py:148-150`), `LiteLLMClient.__repr__` is written out
explicitly so a traceback frame cannot spill the key (`:175-178`), and
`install.py:429-444` redacts a just-typed credential out of the parser's own
message. Three separate precautions already in the tree. Every new error path
and every new value object joins them.

**Trap 11 — `factory/controlplane/__init__.py` is 0 bytes and must stay that
way.** `factory/controlplane/verify.py:29` imports
`factory.usage.litellm_client`. Once `litellm_client` imports
`factory.controlplane.resolve`, any import placed in that `__init__` — a
convenience re-export, a "tidy up the public surface" pass — makes
`litellm_client` → `controlplane` → `verify` → `litellm_client` a cycle at
worker start. The failure will not look like this change: it will look like an
unrelated `ImportError` or a partially-initialised module, at the top of a
traceback nobody connects to a package `__init__`. Leave the file empty and say
so in a comment if you must touch it at all.

**Trap 12 — two stories append to `docs/decisions.md`.** US1 writes the
precedence entry (FR-013) and US2 writes the `direct` entry (FR-014), both at
the end of the same file. That is why US2 carries `depends_on_merged: [US1]`
rather than running beside it: a pass-edge would let both worktrees append at
the same base and collide in the queue. Take the *next* free number after the
one your base already contains — do not guess a number from this plan, and do
not renumber an existing entry. Entries are immutable by construction; supersede,
never edit.

> **This already happened, on 2026-08-16, and "the next free number" was not
> enough.** US1 and an unrelated operator PR both appended **D-046** within the
> hour, because US1's base predated that merge and neither could see the other.
> Git caught it only because the two entries landed on adjacent lines; in
> different regions there would have been no conflict and two live D-046 entries.
> US1's was renumbered to **D-047** at merge, and its in-code reference in
> `resolve.py` updated to match. The log also already contains **D-036 and D-037
> twice each** and is ordered newest-first at the top and newest-last at the
> bottom, so the tail does not tell you the highest number. Filed as
> `docs/the-decision-log-has-duplicate-numbers-and-two-orderings`. **US2: after
> rebasing, grep the whole file for your chosen number before you commit it, and
> expect the operator to renumber you at merge if a sibling lands first.**

**Trap 12b — three things US1 found and deliberately left for you.** Each was
verified against the tree; none is speculation.

- **`factory/cli/main.py:154`** still reads
  `os.environ.get(PROXY_URL_ENV) or "not configured"`, so `ergane --version` now
  reports "not configured" on a host whose config declares a gateway. **US4 owns
  it**: US4 already edits the adjacent Temporal lines at `:152-153`, so it is one
  hunk there and a separate story anywhere else.
- **`factory/cli/env.py:33-34`** labels both override variables `required`, which
  US1 made false. **US3 owns it** under FR-017, and US3's byte-parity assertion is
  what keeps the correction from turning into a rewrite of the report.
- **`temporal.address` is required when `temporal.mode = "external"`.** US1 reads
  nothing from `[temporal]`, but any fixture config a later story writes must
  carry it or the parser refuses the file — which will present as US1's own
  "broken config" refusal (FR-005) and send you hunting in the wrong module.
  **This is the cheapest of the three to trip over and the most confusing.**

**Trap 13 — `verify.py` reads Temporal config-first, and that is the bug, not
the model.** `verify.py:118-119` and `:308-309` do
`config.address or os.environ.get(...)`. It is tempting to read that as the
pattern to copy, because it is the only place in the tree that consults the
config at all. It is backwards: US1 and US4 establish env-over-config, and
leaving verify inverted means the probe and the worker can target different
servers (US4-S3, SC-006). US4 changes those two sites to the one precedence,
which will make some existing verify tests fail — those failures are the story
working.

**Trap 14 — size.** The judge refuses a diff over `DIFF_INPUT_LIMIT`
(`factory/verify/diffbounds.py:38`, 60 KiB) deterministically, through
`DiffSizeRefusal` (`factory/verify/models.py:281`) — 045 landed that, so an
oversized story now fails before a judge token is spent rather than being judged
on a truncated diff. Two stories are at risk: US2, because subtraction across
three modules plus their test corpus adds up fast, and US4, because it touches
ten sites. Both are thin *per site*; check the running total before committing
and split rather than shipping a diff the judge will refuse.

**Trap 15 — the judge sees the diff and the criteria, nothing else.** Every
"proven by a committed test" means a test file in your diff. The transcript
excerpts and line anchors in this plan are not evidence your story can cite;
they are how you find the code. Where a story needs runtime evidence, paste the
tool output into a committed artifact.

## Verification the operator will run, independent of the gate

- Build the wheel, install it into a clean venv under `env -i` with a scratch
  `HOME`, run `ergane install` accepting every default, export only the
  variables the interview named, and run `ergane build start` — the failure
  mode the finding describes must be gone, and the endpoint reached must be the
  declared one.
- On this development host, with `scripts/ergane-env.sh` loaded and no config
  file present, start an epic and confirm it dispatches exactly as before.
- Answer `direct` to the interview's llm mode question and read what it says.
- Declare one Temporal address in the config, export a different one, and
  confirm `ergane install --verify` and the worker agree about which server
  they are talking to.
- Run `ergane env` and `ergane env --sources` on both hosts and confirm the
  first is unchanged and the second tells the truth about which is which.
