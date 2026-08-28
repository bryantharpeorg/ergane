# Implementation Plan: the demo sandbox starts, or says why

Drafted 2026-08-27 against ergane-buildout at 3e5c940. Every anchor below was
read from that commit. The measurements in spec.md's frontmatter — the two-path
bwrap comparison, the `bwrap (unconfined)` label, the `dpkg -S` result — are
inputs to this plan, not open questions.

## Requirements, numbered here

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

## Technical approach, story by story

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
tiers resolve the same constant is what makes it stick.

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

## Work Graph

```yaml
US1:
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005]
  depends_on: []
US2:
  implements: [FR-006, FR-007, FR-008, FR-009, FR-010]
  depends_on: []
  depends_on_merged: [US1]
```

Chain depth 2 — US1 → US2.

## Sizing

Two stories, both small. US1 is one pure function, two call-site changes, and
its tests. US2 is one committed file, two comment edits, and two test modules.
Neither should approach the size of a 110 story.

**The risk here is not sprawl, it is scope creep into privilege.** Every trap in
this plan except T6 and T7 exists to keep a small correctness fix from becoming
a host-provisioning feature. If a story starts growing a `--fix` flag, stop.

## File contention

| story | owns |
| --- | --- |
| US1 | `factory/verify/` (new module for the remedy function), `factory/supervision/demo_driver.py`, `factory/controlplane/verify.py` (finding text only), its tests (new file) |
| US2 | `container/<profile>.apparmor` (new), `factory/workgraph/adapter.py` (comment only), `factory/controlplane/verify.py` (comment only), `README.md`, `docs/onramp.html`, its tests (new file) |

Both stories touch `factory/controlplane/verify.py` — US1 its finding text, US2
its pinned-path comment — which is why they are sequential rather than
concurrent.

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

## Verification the operator will run, independent of the gate

The gate cannot reach this one. Every test in this spec runs against captured
strings and committed files, because the failure it is about requires a host
that this host is not.

After it lands: on a machine with `kernel.apparmor_restrict_unprivileged_userns=1`
and **no** `/etc/apparmor.d/bwrap` — a stock Ubuntu 24.04+ box, or this host with
the profile temporarily moved aside and reloaded — run the released demo, read
the refusal, do only what it says, and run it again. Two readings are the
evidence: the refusal names AppArmor rather than a Debian sysctl, and the second
run reaches the halt statement.
