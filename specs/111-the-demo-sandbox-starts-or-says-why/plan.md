# Implementation Plan: the demo sandbox starts, or says why

Drafted 2026-08-27 against ergane-buildout at 3e5c940. Every anchor below was
read from that commit. The measurements in spec.md's frontmatter — the two-path
bwrap comparison, the `bwrap (unconfined)` label, the `dpkg -S` result — are
inputs to this plan, not open questions.

Amended 2026-08-28 with US3 (FR-011 … FR-017), whose anchors were read from
`1045370` on the same branch. The live failure in spec.md's amended frontmatter —
the 401 from Ollama Cloud, the cooldown, the dispatch that followed anyway — is
likewise an input, not an open question.

## Requirements, numbered here

### US1 and US2 — the sandbox refusal and the shipped grant

- **FR-001** — There is exactly one source of sandbox-remedy text in the tree,
  and both tiers read it: the demo driver's refusal path
  (`factory/supervision/demo_driver.py:145-151`, used at `:369-378`) and the
  host probe's bwrap finding (`factory/controlplane/verify.py:301-330`). Today
  the driver owns a `SANDBOX_REMEDY` string constant that the host probe knows
  nothing about; after this story the string lives in one module and both import
  it.
- **FR-002** — The remedy is selected by the failure's own stderr, not printed
  unconditionally. Two patterns are recognised, both measured:
  `setting up uid map: Permission denied` (the AppArmor unprivileged-userns
  restriction) and `Can't mount proc` (Docker's masked `/proc`, bubblewrap#284,
  measured 2026-08-26 and answered by `systempaths=unconfined`).
- **FR-003** — The AppArmor remedy names, in this order: that
  `kernel.apparmor_restrict_unprivileged_userns=1` is what refused the
  namespace; that `apparmor=unconfined` on a container does not lift it, because
  AppArmor attaches by executable path on exec; and the committed profile's path
  in this repository, with the two commands that load it. It does **not** mention
  `kernel.unprivileged_userns_clone`, which is a Debian-era knob and is not the
  mechanism (spec.md frontmatter).
- **FR-004** — The masked-`/proc` remedy keeps today's text — `systempaths=unconfined`
  on the engine service, already set in `container/compose.demo.yaml:37` — and
  gains no AppArmor content. The two remedies are different text.
- **FR-005** — An unrecognised stderr produces the probe's stderr verbatim plus
  one line stating the failure is not one of the two known shapes, listing both
  remedies as candidates without asserting either. Silence and a guess are both
  refused: the driver stops before any spend either way, so the only question is
  whether the stranger is told something true.
- **FR-006** — The AppArmor profile ships in this repository at a committed path
  under `container/`. Its content is the profile measured working on 2026-08-27:
  `abi <abi/4.0>,` / `include <tunables/global>` / `profile bwrap /usr/bin/bwrap
  flags=(unconfined) {` / `userns,` / `include if exists <local/bwrap>` / `}`.
- **FR-007** — A committed test asserts the profile's *directives* — that it
  attaches at `/usr/bin/bwrap` and grants `userns` — by parsing, not by digest.
  A digest test breaks on a reflow and passes on a profile that has quietly lost
  its grant; this project has been bitten by exactly that class of check
  (`docs/decisions.md`, the vacuous-sweep entries).
- **FR-008** — `factory/workgraph/adapter.py:293-295` no longer says Ubuntu's
  profile permits this. It says: the pin is required because AppArmor attaches by
  path, the grant comes from a profile no package ships, and the profile this
  project ships is at `<committed path>`. **The pin itself does not change** —
  `BWRAP_BACKEND_BINARY` stays `/usr/bin/bwrap`, and for the measured reason.
- **FR-009** — `factory/controlplane/verify.py:248-250` carries the same
  correction and the same pointer, in its own voice.
- **FR-010** — The one-time load procedure printed in `README.md` and in
  `docs/onramp.html` is the committed profile. A test extracts the profile text
  from the documented procedure and asserts it equals the committed file, so a
  page and an artifact cannot drift.

### US3 — the credential refusal

- **FR-011** — `container/compose.demo.yaml:125` declares the credential in
  Compose's *required* form, `${UPSTREAM_MODEL_API_KEY:?<message>}`, and the
  message names the variable and says it is an Ollama Cloud key with the URL that
  issues one. Compose then fails during interpolation — before Postgres is
  created, before the 300s gateway migration window — for the stranger who never
  exported it. This is the cheapest of the three refusals in this spec and it
  fires in about a second.
- **FR-012** — `_is_mandatory` (`tests/test_109_us2_demo_compose.py:181-193`)
  still classifies the required form as mandatory, asserted **directly** on the
  helper and not only through its callers. Four committed tests are computed from
  `_mandatory_compose_vars()`; if that set silently becomes empty, all four pass
  while checking nothing. The helper's docstring examples gain the `:?` case.
- **FR-013** — `run_prepare_phase` decides on a **typed finding**, not on an exit
  code and not on parsed text. After `ergane install --from-file` returns, the
  phase runs the control plane's own `LLMProbe`
  (`factory/controlplane/verify.py:408-656`) against the config install just
  wrote and evaluates it into a `Finding`. No second definition of "the gateway
  works", no new request shape, no scraping of `render_findings` output.
- **FR-014** — The checks that stop the demo are a named module-level constant
  whose value is exactly `{"llm"}`. A failed check outside that set is reported
  and preparation continues, which is today's behaviour and stays: the demo runs
  with `--halt-after-pass` and never opens a pull request, so an unauthenticated
  `gh` — the ordinary state of a demo container — genuinely cannot stop it from
  reaching its last line. A gateway that cannot complete a token can. The comment
  at `demo_driver.py:339-347` keeps its `gh` reasoning; only its width changes.
- **FR-015** — On a fatal finding the phase prints the finding's own `detail`
  verbatim (it carries the gateway's upstream error), then one remedy line, then
  returns nonzero **before** `write_sentinel(state_home, PREPARED_SENTINEL)` at
  `demo_driver.py:382`. The remedy names `UPSTREAM_MODEL_API_KEY`, says it is an
  Ollama Cloud key read by the *gateway* container, and gives the way back:
  `docker compose -p <project> down -v`, export, re-run.
- **FR-016** — Nothing in the engine container reads `UPSTREAM_MODEL_API_KEY`,
  because it is not there (see T8). The refusal names the variable from the
  demo's published contract. A committed test asserts the name appears in the
  remedy text **and** that the driver module never looks it up in the
  environment.
- **FR-017** — A probe that raises becomes a failed finding naming the exception,
  mirroring `verify.py:1170-1181`. An unreachable gateway, a malformed config or
  an import error must produce the refusal, not a traceback caught by `main`'s
  catch-all at `demo_driver.py:738-740`, which would print `first boot failed:`
  and name no remedy at all.

## What already exists, and where

| Piece | Where | State |
| --- | --- | --- |
| Demo-tier sandbox probe | `sandbox_probe_argv` / `run_sandbox_probe`, `factory/supervision/demo_driver.py:189-244` | Correct shape already — `--proc` is load-bearing and present (110 T5). **Nothing about the probe changes.** |
| Demo-tier remedy | `SANDBOX_REMEDY`, `demo_driver.py:145-151` | One unconditional string; names the wrong sysctl |
| Demo-tier refusal path | `run_prepare_phase`, `demo_driver.py:366-379` | Prints stderr, then the remedy, then returns 1 before any spend — the ordering is right and stays |
| Native-tier bwrap probe | `_bwrap_probe_argv` / `_run_bwrap_probe`, `verify.py:259-298` | 088-US1 already **executes** bwrap at the pinned path with the production mount shape. Strong enough; only its finding text is in scope |
| Native-tier host finding | `_inspect_host` / `HostProbe`, `verify.py:301-330`, `:957-1000` | Reports bwrap present-and-runnable; carries no remedy for the userns denial |
| The path pin and its rationale | `BWRAP_BACKEND_BINARY`, `adapter.py:293-295`; `_BWRAP_PINNED_PATH`, `verify.py:248-250` | Correct pin, false premise in both comments |
| The profile itself, as measured | `/etc/apparmor.d/bwrap` on the floor host, root-created 2026-07-16, unowned by any package | Not in the tree. This spec puts it there |
| Prior art for a shipped confinement asset | `container/ergane-engine.profile`, `container/seccomp-ergane.json` | The convention already exists: confinement artifacts live in `container/` and are referenced by name |
| The research that called this | `docs/container-onramp-research-findings.md:95-112` | Names the mechanism, the non-stockness, and the consequence for the native path |
| The credential check itself | `LLMProbe`, `factory/controlplane/verify.py:408-656`; the per-alias completion at `:534-581`; `Finding(check="llm")` at `:648-656` | **Already correct and already ran.** One 1-token completion per distinct registry alias, through the configured gateway. With a bad upstream key every `demo/` alias fails and the finding is FAIL. Nothing about this probe changes |
| Install's verdict | `_install_from_file`, `factory/cli/install.py:1279-1281` | Runs the full sweep, prints `render_findings`, collapses seven checks to `EXIT_OK`/`EXIT_USER` |
| The place it is discarded | `run_prepare_phase`, `factory/supervision/demo_driver.py:339-347` | The whole defect. Correct about `gh`, and too wide by exactly one check |
| The gate it should have used | `main`, `demo_driver.py:719-724`, and the sentinel write at `:382` | The ordering is already right — refuse before `prepared`, and `prepared` before any spend. US3 adds a reason to refuse, not a new mechanism |
| The demo's single credential | `container/compose.demo.yaml:125` (gateway service only; the engine's environment is `:38-103` and does not contain it) | `${UPSTREAM_MODEL_API_KEY}`, which Compose answers with a warning and an empty string |
| Docker-gated test seam | `_docker_binary` / the skip marker, `tests/test_109_us2_demo_compose.py:633-651` | Already the convention for a test that needs a live daemon; FR-011's live half uses it |
| The prediction of this exact failure | `tests/test_109_us2_demo_compose.py:795-830` | Describes the experience in prose and tests only that the docs and the file name the same variable |

## Technical approach, story by story

### US3 — the demo refuses a credential it has already proven unusable

Two changes, in two files, in the order a stranger meets them.

**The compose declaration.** `${UPSTREAM_MODEL_API_KEY}` becomes
`${UPSTREAM_MODEL_API_KEY:?…}`. That is the whole of FR-011. It costs one line
and it catches the commonest case — the variable never exported, or exported in a
different shell than the one that ran `docker compose` — before a single
container is created.

**The preflight.** `run_prepare_phase` gains one seam and one branch, placed
immediately after the existing install block at `demo_driver.py:329-347` and
before step 2's `git init`. The seam is a callable returning a `Finding`,
defaulting to a small function that loads the config install just wrote and runs
`LLMProbe().gather(...)` / `.evaluate(...)` inside `asyncio.run`, wrapping a
raising probe into a failed finding the way `verify.py:1170-1181` does.

Run **only** the LLM probe, not the whole sweep. Three reasons, and the third is
the load-bearing one: the other six verdicts are already on the stranger's screen
from install's own report; re-running them would re-dial Temporal and re-shell
`gh` for nothing; and a fatal refusal that can only ever be computed from the one
probe in the fatal set cannot regress into the aggregate-exit-code bug this story
exists to fix. The fatal set (FR-014) is structural, not a filter applied late.

The step counter does not change — the preflight is part of "step 1/5 ergane
install", because it is the same question install was already asking. See T13.

### US1 — a refused sandbox names the restriction that refused it

The remedy stops being a constant and becomes a small pure function over the
probe's stderr: `sandbox_remedy(stderr: str) -> str`, living in one module that
both `demo_driver` and `verify` import. Two compiled patterns, two texts, one
fallback. The demo driver's refusal path calls it with the outcome's stderr
instead of printing `SANDBOX_REMEDY`; the host probe's bwrap finding calls it
with the probe's stderr when the probe ran and failed.

Where the function lives matters for import direction. `demo_driver` already
imports from `factory.workgraph.adapter` and `factory.verify.toolchain`;
`verify` imports from neither. Put it beside the thing it is about —
`factory/verify/` — so nothing in the control plane grows a dependency on
supervision code.

### US2 — the grant is a file this project ships

One new file under `container/`, alongside `ergane-engine.profile` and
`seccomp-ergane.json`, which is where this project already keeps confinement
artifacts. One test module that parses it. Two comment corrections, each a few
lines, each keeping its pin. One docs test that extracts the profile from the
documented procedure in both pages and compares it to the file.

## Traps

**T1 — do not make this an installer.** The obvious next step from "ship the
profile" is "have `ergane install` load it", and the research note even suggests
it. It is out of scope by operator ruling (spec.md frontmatter): writing to
`/etc/apparmor.d` and running `apparmor_parser` widens a host's sandbox policy,
which is a consent surface, not a convenience. Nothing in this spec acquires
privilege or writes outside the repository. A task that adds a `sudo` anywhere
is out of scope and should be refused, not negotiated.

**T2 — do not change the probe shapes.** Both probes are correct and both were
argued for at cost. The demo probe's `--proc` is 110's T5 — a probe without it
passes on a host where no agent can start. The native probe's full mount shape
is 088-US1's findings §1 failure mode 14. This spec changes what a failure
*says*, never what is tried. A diff that edits `sandbox_probe_argv` or
`_bwrap_probe_argv` is out of scope.

**T3 — do not un-pin `/usr/bin/bwrap`.** The comments are wrong about *why* the
pin is needed; the pin is right. AppArmor attaches by path, so a vendored or
copied binary genuinely does fail — that half of both comments is the measured
2026-08-27 result (`/tmp/bwrap-copy` → `setting up uid map: Permission denied`).
Correcting a premise is not licence to remove the conclusion.

**T4 — `apparmor=unconfined` is not an escape hatch, and the correction must say
so.** The demo compose file's own comment block
(`container/compose.demo.yaml:22-31`) explains the unconfined pair as a delivery
constraint, which is true and stays. But a reader can take it to mean the
container is therefore unmediated, and it is not: the sandbox child's measured
label is `bwrap (unconfined)`, an attachment from the *host's* policy. If the
new remedy text does not make that explicit, the stranger will try to fix it
inside the compose file, which cannot work.

**T5 — one remedy source, or the tiers drift.** Today the demo driver owns the
only remedy text and the host probe has none. If US1 writes a second string into
`verify.py` instead of importing one, this spec ships the same defect it is
fixing, one file over. FR-001 is the requirement; the committed test that both
tiers resolve the same constant is what makes it stick. This is about the two
*sandbox* tiers only — US3's gateway-credential remedy, which will already be in
the tree when US1 runs, is a different failure domain with one branch and stays
where US3 put it. Folding it into the sandbox classifier is not consolidation, it
is a category error.

**T6 — the profile test must fail when the grant is removed.** `userns,` is the
whole point of the file. A test that asserts the file exists, or that its bytes
match a digest, passes on a profile that has been reformatted into
uselessness or fails on a harmless reflow. Parse the directives, assert the
attachment path and the `userns` grant specifically. This project's own
`page_holds_true` history is the reason this trap is written down: a sweep that
skips what it cannot parse always passes.

**T7 — the docs test must read the procedure, not restate it.** FR-010 is only
worth having if it would catch a page whose `printf` was edited. Extract the
profile text from the documented commands and compare; do not assert that the
page contains a hard-coded copy of the profile, which is the same string written
twice and drifts the same way.

### Traps for US3

**T8 — `UPSTREAM_MODEL_API_KEY` is not in this container's environment, and the
obvious implementation is therefore wrong.** It appears exactly once in
`container/compose.demo.yaml`, at line 125, on the **gateway** service. The
engine service's environment list (`:38-103`) does not contain it and must not:
the whole point of the gateway is that the agent never holds the operator's
upstream credential. So `os.environ.get("UPSTREAM_MODEL_API_KEY")` inside the
driver returns `None` on a perfectly healthy stack, and a preflight built on that
check refuses every demo, including the ones that would have worked. The driver
learns the credential is bad by watching the gateway fail to use it — never by
looking for it. FR-016's test exists to nail this shut.

**T9 — do not make install's exit code fatal.** The one-line version of this
story is "stop ignoring the nonzero exit", and it is wrong. `ergane install`
returns `EXIT_USER` when *any* check fails, and on a stock demo host `gh` is
unauthenticated by design — `compose.demo.yaml:99-103` says so, and `GH_TOKEN`
defaults to empty deliberately. A story that refuses on install's exit code
breaks the demo for everyone, including the operator who verified it working on
2026-08-27. Narrow the tolerance to a named set; do not remove it.

**T10 — seven existing tests call `run_prepare_phase`, and a seam with a
production default will turn every one of them into a refusal.**
`tests/test_110_us1_demo_first_boot.py` drives the phase with `run_cli` and
`probe` injected but nothing else; add a preflight that defaults to the real
control-plane probe and those tests will try to verify a control plane that does
not exist, get a failed finding, and take the new refusal path. **Updating them
is part of this story, not a follow-up.** They are at
`tests/test_110_us1_demo_first_boot.py:349, 442, 494, 538, 552, 596, 610`.

**T11 — the compose change can make four other tests vacuous.**
`_mandatory_compose_vars()` (`tests/test_109_us2_demo_compose.py:784-793`)
computes its answer through `_is_mandatory`, which today returns True for
`${VAR}` and False for `${VAR:-default}` by testing `":-" not in value`. The
required form `${VAR:?msg}` still satisfies that predicate — but nothing asserts
it does, and the failure mode is silence: an empty mandatory set makes the
exactly-one-variable test and the docs-agreement test pass while checking
nothing. FR-012 is one direct assertion on the helper, and it is the difference
between a test suite and a green light. This project has shipped this exact class
of vacuity before — a README containing `nergane repo forget` passed a sweep
whose only guard was that the command list was non-empty.

**T12 — the loudest error in the log is the wrong one; do not key on it.** After
the upstream 401, LiteLLM put `demo/implementer`'s only deployment into cooldown,
and every call after that returned `429` / `RouterRateLimitError: No deployments
available for selected model` (spec.md frontmatter). Whichever of the two a probe
happens to catch, the demo's answer is identical, because this stack has exactly
one upstream credential and one deployment per alias. Print the finding's own
detail — whatever it says — and then one fixed remedy. Do **not** build a
status-code classifier: US1's two-branch classifier exists because there are two
genuinely different sandbox remedies; here there is one.

**T13 — do not renumber the steps.** The phase emits `step 1/5 … step 5/5` and
`tests/test_110_us1_demo_first_boot.py:22-37` carries that transcript. The
preflight belongs *inside* step 1 — it is the verdict on the install that just
ran — so the count does not change. Renumbering to `/6` is churn that breaks a
landed story's evidence for nothing.

**T14 — the probe proves the OpenAI path, and the agent uses the Anthropic one.**
`_probe_one_alias` posts to `/chat/completions` (`verify.py:534-554`); the
dispatched agent is handed `ANTHROPIC_BASE_URL` and speaks Messages at
`/v1/messages`, which is what the 2026-08-28 traceback shows. For a credential
failure the two are the same event — one key, one upstream — so the preflight is
sound. Two consequences: the remedy text must say the credential was rejected,
not that the agent path was exercised; and nobody should "strengthen"
`_probe_one_alias` by asserting non-empty content. It checks `bool(choices)` on
purpose — the demo's implementer alias is a reasoning model, and a reasoning
model at `max_tokens: 1` returns a choice with empty content. Asserting content
would refuse a working key.

**T15 — the teardown command must keep working without the variable, and it
already does.** `${VAR:?…}` is evaluated on every Compose invocation that reads
the file, so `curl … | docker compose -f - down -v` would fail for a stranger
whose key is unset — which is exactly the stranger who most needs to tear down.
`docs/onramp.html:297-298` already documents teardown as
`docker compose -p <project> down -v`, which names the project and reads no file,
so the guard does not break it. Leave that line alone; do not "helpfully" change
it to the `-f -` form.

## Work Graph

```yaml
US3:
  implements: [FR-011, FR-012, FR-013, FR-014, FR-015, FR-016, FR-017]
  depends_on: []
US1:
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005]
  depends_on: []
  depends_on_merged: [US3]
US2:
  implements: [FR-006, FR-007, FR-008, FR-009, FR-010]
  depends_on: []
  depends_on_merged: [US1]
```

Chain depth 3 — US3 → US1 → US2. The story keys are not in dependency order and
that is deliberate: US1 and US2 were drafted first, US3 is the one that fired.

## Sizing

Three stories, all small. US3 is one compose line, one seam, one branch, one
constant and its tests, plus the seven existing call sites T10 names. US1 is one
pure function, two call-site changes, and its tests. US2 is one committed file,
two comment edits, and two test modules. None should approach the size of a 110
story.

**The risk in US1 and US2 is not sprawl, it is scope creep into privilege.**
Every trap for those two except T6 and T7 exists to keep a small correctness fix
from becoming a host-provisioning feature. If a story starts growing a `--fix`
flag, stop.

**The risk in US3 is the opposite: doing too little in the wrong place.** The
one-line version — refuse on install's nonzero exit — is smaller than the right
answer and breaks the demo for everyone (T9). The other tempting shortcut,
reading the environment variable directly, is smaller still and refuses every
healthy stack (T8). US3 is small, but it is not one line.

## File contention

| story | owns |
| --- | --- |
| US3 | `container/compose.demo.yaml` (one env line), `factory/supervision/demo_driver.py` (prepare phase), `tests/test_110_us1_demo_first_boot.py` (the seven call sites in T10), an assertion added to `tests/test_109_us2_demo_compose.py`, its tests (new file) |
| US1 | `factory/verify/` (new module for the remedy function), `factory/supervision/demo_driver.py`, `factory/controlplane/verify.py` (finding text only), its tests (new file) |
| US2 | `container/<profile>.apparmor` (new), `factory/workgraph/adapter.py` (comment only), `factory/controlplane/verify.py` (comment only), `README.md`, `docs/onramp.html`, its tests (new file) |

US3 and US1 both touch `factory/supervision/demo_driver.py` — US3 its prepare
phase, US1 its sandbox refusal text — and US1 and US2 both touch
`factory/controlplane/verify.py`, US1 its finding text and US2 its pinned-path
comment. That is why all three are sequential rather than concurrent.

US3 touches no file US2 owns, so if the operator wants only the credential fix
tonight it can be dispatched and landed alone, and US1/US2 re-derived afterwards
with `--delta`.

## Dispatch hazards, for the operator running this epic

- **Re-derive the workgraph at dispatch** with `--target-repo "$PWD"` from the
  operator checkout; the committed artifact carries compile-time absolute paths.
- **Do not run `scripts/gate-commit` while an attempt is in flight** — a
  concurrent operator gate turns a node's gate red for a reason the node cannot
  see. Measured twice on 2026-08-25.
- **US2 edits `docs/onramp.html`, which an operator session also edits.** That
  page was corrected by hand on 2026-08-27 and republished as an artifact; if it
  changes again between dispatch and landing, the FR-010 test is where the
  conflict surfaces. Land US2 before touching the page again.
- **The worker on the floor host must be current before dispatch** — a stale
  worker imports stale factory code when a story lands.
- **US3 edits `factory/supervision/demo_driver.py`, which the running container
  image also carries.** Nothing in flight imports it — the demo driver runs only
  inside a demo container — but a rebuilt image is what carries the fix to a
  stranger. Landing US3 fixes nothing that anyone can `curl` until the next
  release publishes a `compose.yaml` and an image that contain it. Say so when
  reporting the story done; a landed US3 and a fixed demo are not the same event.
- **US3 changes `container/compose.demo.yaml`, which the release workflow
  rewrites on publish.** `.github/workflows/release.yml:230-233` does a literal
  `content.replace('${ERGANE_VERSION}', version)` on that file, so FR-011's guard
  on a *different* variable does not disturb it — checked 2026-08-28, recorded
  here so nobody re-derives it. What still needs a human is fetching the
  published `compose.yaml` after the next release and confirming the guard
  survived into the artifact strangers actually download.

## Verification the operator will run, independent of the gate

The gate cannot reach US1 or US2. Every test they carry runs against captured
strings and committed files, because the failure they are about requires a host
that this host is not.

After they land: on a machine with
`kernel.apparmor_restrict_unprivileged_userns=1` and **no**
`/etc/apparmor.d/bwrap` — a stock Ubuntu 24.04+ box, or this host with the
profile temporarily moved aside and reloaded — run the released demo, read the
refusal, do only what it says, and run it again. Two readings are the evidence:
the refusal names AppArmor rather than a Debian sysctl, and the second run
reaches the halt statement.

US3's verification is cheaper and the operator should run it the same evening it
lands, because it is the only one of the three whose failure has already been
observed. From cold volumes, three times:

1. `UPSTREAM_MODEL_API_KEY` unset → Compose refuses at interpolation, in about a
   second, naming the variable. No container is created.
2. `UPSTREAM_MODEL_API_KEY=sk-not-a-real-key` → the stack comes up, install runs,
   the driver refuses after install and before `git init`, printing the gateway's
   own error and the remedy. **No dispatch, no `dispatch-attempted` sentinel, no
   spend.** This is the run that failed on 2026-08-28.
3. A real Ollama Cloud key → the demo reaches the halt statement, as it did on
   2026-08-27.

Between runs, `docker compose -p <project> down -v`. Run 2 is the whole point:
verify by *reading the sentinel directory*, not just the log — the demo must not
have written `dispatch-attempted`, because a stranger who fixes their key must
get a demo rather than a refusal to re-run.
