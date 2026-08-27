---
state: draft
# DRAFTED 2026-08-26 ~1:10 PM CT by the operator session, against ergane-buildout
# at 4aae6b7 (109 landed and attested, #351 landed). Every file:line below was
# read from that commit on 2026-08-26 and verified against the tree before
# drafting.
#
# WHY THIS EXISTS. 109 landed all four of its stories and its own attestation
# says what is missing: "landed and unproven, and those are different words on
# purpose." The gap was then measured and filed as
# `onramp/the-one-command-demo-never-dispatches-anything` (critical, 2026-08-26):
# the one command brings up temporal+worker+bridge and stops. Nothing dispatches
# a story, so US3's halting mode — five tests, landed correct — has no path to
# being exercised by the command it was built for. A stranger gets three healthy
# services and no demonstration.
#
# THE OPERATOR'S RULING, taken 2026-08-26 with three options on the table
# (bundle-and-dispatch / next-step banner / narrow the promise): the demo
# dispatches. This is the same ruling 109's own frontmatter records from
# 2026-08-25 — "The demo dispatches ONE story and STOPS BEFORE LANDING" — now
# carried the last mile. The banner option was rejected because a demo that
# prints homework is not a demonstration; the narrowing option was rejected
# because 109's promise is attested text.
#
# RECONCILING THE PROGRAM DOC. `docs/container-onramp-program.md` decision 7
# says install's closing move is "never a dispatch. Dispatch spends money;
# onboarding must not." That decision governs `ergane install`, whose
# demonstration is and stays free (`_closing_demonstration`,
# factory/cli/install.py:972 — it stops at derive on purpose). The demo compose
# project is a different consent surface: the stranger exports
# UPSTREAM_MODEL_API_KEY and pipes the file to `docker compose up` — exporting
# the key IS the opt-in to spend it, on one story, bounded by halt-after-pass.
# A docs/decisions.md entry recording this distinction lands with US1.
#
# MEASURED BEFORE DRAFTING, so nobody re-litigates it from guesses:
#   - The demo container cannot run its agent sandbox as shipped. On the floor
#     host (kernel 6.17.0-1018-nvidia, 2026-08-26), an adapter-shaped bwrap
#     invocation under compose.demo.yaml's exact security options fails with
#     `bwrap: Can't mount proc on /newroot/proc: Operation not permitted` —
#     Docker's masked /proc paths trip the kernel's fully-visible-proc rule
#     (bubblewrap#284). Adding `systempaths=unconfined` to security_opt makes
#     the same invocation pass (sandbox child labeled `bwrap (unconfined)`,
#     git runs inside). Verified through the real delivery mechanism:
#     `cat file | docker compose -f - run` with the security_opt list. The
#     2026-08-23 research measured the mount succeeding on this kernel; a
#     kernel update since has made the knob mandatory. Filed as
#     `container/nested-bwrap-proc-mount-refused-on-current-kernel` for the
#     reference tier; for the demo tier the knob ships in the file (US3).
#   - Even a hand-typed `ergane build start` inside the shipped demo container
#     is refused before the halt flag is reachable: no config.toml (nothing
#     runs install), so `_resolved_proxy_url()` (factory/cli/nouns/build.py:692)
#     raises. The bundled answers file
#     (container/ergane-install-answer.demo.toml) is referenced by nothing but
#     a test today. US1 is where it starts earning its place in the image.
#
# Settled at drafting:
#   - THE DRIVER IS NOT A FOURTH SUPERVISED CHILD. The supervisor exits nonzero
#     when a child dies unprompted (container_supervisor.py:420-426), which is
#     correct for services and fatal for a one-shot. The driver is spawned as a
#     plain subprocess when ERGANE_DEMO=1, reaped, its exit code logged —
#     never in the `controllers`/`tasks` maps, never able to stop the stack.
#     This also respects 109's T3: the supervised-children set stays at three.
#   - THE DRIVER SHELLS THE CLI, IT DOES NOT IMPORT THE FACTORY. Every step is
#     an `ergane` verb a human could type (`install --from-file`, `spec …` via
#     `build ship`, `build status`). The demo demonstrates the product's own
#     verbs, and the driver stays a thin narrator that cannot drift from them.
#   - DISPATCH IS ONE VERB, NOT THREE. `ergane build ship` (106) already runs
#     validate → derive → dispatch with `--yes` and carries `--halt-after-pass`
#     through `add_landing_dial_flags` into `start_command`
#     (factory/cli/nouns/build.py:838-893, factory/cli/landing.py:183-191).
#     The driver reuses it; it does not reimplement the chain.
#   - THE REPO NEEDS A COMMIT, WHICH THE INSTALL DEMO NEVER NEEDED.
#     `_closing_demonstration` stops at derive, which reads the working tree.
#     Dispatch creates worktrees from `main`, so the driver must commit the
#     manifest and spec — with an explicit git identity, because the container
#     user has none. This is exactly the class of gap that made 109's US2 take
#     three attempts; it is named here so it costs nothing this time.
#
# US3 LANDED BEFORE THIS FILE DID. Its landing commit (7d3c06ab, #353; the
# systempaths separator corrected by #354) predates the trio's own landing
# (#355), so the delta baseline reads the spec at US3's landing commit, finds
# no file there, and pins a None fingerprint — every delta derive reopens the
# landed story (observed 2026-08-26 on the first remainder dispatch, which
# needed a hand-edited workgraph). The commit that introduces this comment
# carries the rescue trailer (107 FR-015) in its body, making it US3's newest
# landing fact at a revision where this spec exists. That pins the real
# fingerprint and keeps US3 closed in every future delta.
#
# US1 LANDED AS A RESCUE, TWICE OVER. Its verified attempt (opus-closer, gate
# 5007 passed exit 0, judge PASS on US1-S1..S5) could not push its node branch:
# the epic had been killed and re-dispatched to move the story off the house
# implementer, and while the stale LOCAL node branch was archived, the remote
# one still pointed at the killed run's tip, so `open_landing_pr` was rejected
# non-fast-forward and terminated the epic with both nodes KILLED. The code
# reached the branch via PR #360 (ccc7a28). That squash carried no landing
# attribution: the rescue TITLE is human-readable by design and does not match
# the landing subject grammar, and GitHub builds a multi-commit squash body
# from the commit list rather than the pull request body, so the trailer that
# was in the PR description never reached the commit. This commit is the
# attribution — single-commit, so its own message becomes the squash body.
---

# Feature Specification: the demo dispatches the story it promised

**Created**: 2026-08-26
**Depends on**: 109 (landed). US1 → US2 are sequential; US3 is file-only and
independent of both.

## The gap, stated precisely

109 shipped the three services, the halting mode, and the publish job. What no
story shipped is the actor: the entrypoint
(`factory/supervision/container_supervisor.py:39-43`) supervises

```python
_CHILDREN: dict[str, str] = {
    "temporal": "factory.supervision.temporal_server",
    "worker": "factory.worker",
    "bridge": "factory.notify.service",
}
```

and nothing else. The demo volumes come up empty: no repository, no manifest,
no spec, no control-plane config. `--halt-after-pass` is reachable only from
`ergane build start` and `ergane build ship` and `ergane roadmap start`, and no
process in the stack runs any of them. The finding's summary is exact: "curl |
docker compose up brings up temporal+worker+bridge and then stops."

## The rule this spec is asking for

**On first boot with `ERGANE_DEMO=1`, the stack configures itself from its
bundled answers, scaffolds a throwaway repository and one demonstration spec,
dispatches that one story with halt-after-pass, and narrates what happens —
agent, gate, judge, and the landing-not-attempted statement — into the one
screen the stranger is watching: `docker compose up`'s log stream.**

### What the demo is not

It still does not land — 109's "What the demo is not" stands unamended. It does
not dispatch twice: a restarted container finds its sentinel and supervises
quietly. And it does not die trying: any first-boot failure — bad key, refused
sandbox, refused preflight — is stated in the log with its remedy, and the
three services stay up so the stranger can act on what they read.

## User Scenarios & Testing

### User Story 1 - First boot leaves the demo project dispatchable (Priority: P1)

As the demo container starting for the first time, I install my control plane
from the bundled answers, create the throwaway repository with its manifest and
one demonstration spec, prove the agent sandbox can actually start, and record
that first boot happened.

**Why this priority**: P1 and first. US2 dispatches what this story prepares,
and every failure this story can catch is one the stranger would otherwise meet
mid-dispatch, with money spent.

**Independent Test**: drive the driver's prepare phase against a scratch state
home and repo path (no Temporal, no gateway, no dispatch) and read back the
config, the repo, the spec, the commit, and the sentinel.

**Acceptance Scenarios**:

1. **Given** `ERGANE_DEMO=1` and no sentinel, **When** the supervisor reaches
   the point where worker and bridge are running
   (`container_supervisor.py:334-336`), **Then** it spawns the demo driver as a
   plain subprocess — proven by a committed test that also proves the driver is
   **absent** from the supervised `controllers`/`tasks` maps, and that a driver
   exiting nonzero does not stop the container.
2. **Given** the driver's prepare phase, **When** it runs, **Then** it performs,
   in order, each step as an `ergane` CLI invocation or the named existing seam:
   `ergane install --from-file
   /opt/ergane/container/ergane-install-answer.demo.toml`; `git init -b main`
   of the demo repository; the manifest via the same text
   `_demo_manifest_text` writes (factory/cli/install.py:1049); the spec trio
   via `scaffold_spec(slug="demo", title="Demonstration", anchor=…,
   demonstration=True)` (factory/doctor/scaffold.py:27); a git commit of all of
   it under an explicit demo identity — and a committed test drives the phase
   offline and asserts the repo, spec directory, commit and config all exist.
3. **Given** the prepared repository, **When** `ergane spec validate` and
   `ergane spec derive` run against it, **Then** both succeed — the committed
   test runs them through the CLI seam (`_run_cli`,
   factory/cli/install.py:1071) and asserts a compiled `workgraph.json`.
4. **Given** the sandbox preflight, **When** the driver probes an
   adapter-shaped `bwrap` invocation (`--unshare-pid --die-with-parent --proc
   /proc --dev /dev` plus read-only binds, the shape of
   `factory/workgraph/adapter.py:427-580`), **Then** a refusal is printed with
   the probe's own stderr and a named remedy, the driver stops **before any
   dispatch**, and the supervised services keep running — the committed test
   injects a failing probe **and asserts directly, through the supervisor
   seam, that the three supervised children are still up after the driver's
   nonzero exit**. A test that only proves the absence of a dispatch sentinel
   does not prove this and does not satisfy the scenario (the first run's
   judge failed exactly that shortcut).
5. **Given** a restart after a first boot whose prepare phase completed and
   whose probe succeeded, **When** the supervisor starts, **Then** the
   sentinel makes the driver a no-op that says so in one line. **Given** a
   restart after a **probe refusal**, **Then** the probe runs again — no
   sentinel was written on the refusal path, so a stranger who fixes their
   host and restarts gets the demo rather than a permanent sulk. Proven by
   tests that run the driver twice in each of the two states.

### User Story 2 - The demo dispatches, narrates, and halts (Priority: P1)

As the demo driver with a prepared project, I dispatch the one story with
halt-after-pass and narrate its progress into the supervisor's log stream until
the terminal state, closing with the statement that landing was not attempted.

**Why this priority**: P1. This is the story the finding is about; US3's halting
mode gets its first caller.

**Independent Test**: drive the dispatch phase against a stub CLI seam that
plays a scripted sequence of status documents, and read the narration off the
captured stream.

**Acceptance Scenarios**:

1. **Given** a prepared project, **When** the dispatch phase runs, **Then** the
   dispatch is exactly `ergane build ship <spec-dir> --target-repo <repo>
   --yes --halt-after-pass` — one verb, no reimplemented
   validate/derive/start chain — proven by a committed test over the driver's
   assembled argv.
2. **Given** a dispatched epic, **When** the driver watches it, **Then** it
   polls `ergane build status` and prints each node state transition once as it
   is observed, and on a terminal state prints the full status render — which
   in halting mode carries the landing-not-attempted statement
   (`_halt_after_pass_lines`, factory/cli/nouns/build.py:557-572) — proven by
   a test that scripts PENDING → RUNNING → VERIFYING → PASSED and asserts the
   statement reaches the stream verbatim.
3. **Given** a dispatch refusal (`build ship` exits nonzero — preflight
   finding, unreachable proxy, refused persona), **When** the phase runs,
   **Then** the driver prints the refusal as its own last words, writes the
   sentinel so a restart does not retry the spend, and exits nonzero without
   stopping the services — proven by a test with a failing seam.
4. **Given** an epic that fails rather than passes (gate or judge), **When**
   the watch loop reaches the terminal state, **Then** the driver prints the
   failure render exactly as `ergane build status` states it, without
   editorializing — the mode changes where success stops, never what failure
   means (109 US3-S4).

### User Story 3 - The file carries the demo (Priority: P2)

As the shipped compose file, I carry the three lines the demo needs — the demo
flag, the gateway endpoint for exec'd shells, and the security option the
sandbox was measured to require — without growing a second mandatory variable.

**Why this priority**: P2 by size, not by optionality — three lines and their
tests. File-only, so it can land in parallel with US1/US2.

**Independent Test**: read the committed file and assert the three lines and
the unchanged mandatory-variable count.

**Acceptance Scenarios**:

1. **Given** `container/compose.demo.yaml`, **When** a drift test reads the
   engine service's environment, **Then** `ERGANE_DEMO=1` and
   `LITELLM_PROXY_URL=http://gateway:4000` are present as **literal** values,
   and the mandatory-variable count test
   (`tests/test_109_us2_demo_compose.py:275`) still counts exactly one.
2. **Given** the engine service's `security_opt`, **When** the test reads it,
   **Then** `systempaths=unconfined` is present, and the adjacent comment names
   the mechanism it answers: Docker's masked /proc paths trip the kernel's
   fully-visible-proc refusal inside the sandbox's user namespace
   (bubblewrap#284), measured on kernel 6.17.0-1018 on 2026-08-26 — in the
   same voice as the existing seccomp/apparmor comment block
   (`container/compose.demo.yaml:22-31`).
3. **Given** the whole file, **When** the existing 109 drift suite runs,
   **Then** every test passes unmodified except the ones this story extends,
   and no volume, service or mount changed.

## Work Graph

```yaml
US1:
  implements: []
  depends_on: []
US2:
  implements: []
  depends_on: []
  depends_on_merged: [US1]
US3:
  implements: []
  depends_on: []
  concurrent_with: [US1, US2]
```

`concurrent_with` is declared on US3 for the same reason 109 declared it: the
validator's `slice_contention` layer reads prose mentions as slice membership,
and US1/US2's tasks necessarily *name* `container/compose.demo.yaml` (the file
that sets the flag they read) while editing only
`factory/supervision/demo_driver.py`, `factory/supervision/container_supervisor.py`
and their tests. US3 edits the compose file and the 109 drift suite and touches
no supervision code.

Chain depth 2: US1 → US2, with US3 alongside from the first round.

## Requirements (summary — numbered at refinement)

The ERGANE_DEMO gate and the not-a-supervised-child invariant; the prepare
phase's ordered steps as CLI verbs and named seams; the commit with an explicit
identity; validate and derive succeeding on the prepared repo; the sandbox
preflight and its refusal shape; the sentinel and its exactly-once semantics;
the one-verb dispatch; the watch loop and the verbatim halt statement; refusal
and failure legibility without editorializing; the three compose lines; the
unchanged mandatory count; the systempaths comment naming its mechanism.

## Success Criteria (summary)

Pasted: the prepare-phase test transcript; a scripted watch-loop narration
ending in the halt statement; the compose drift suite passing with
before-and-after counts; and — operator-run, after this lands — one real first
boot on the floor host, from image build to the halt statement in
`docker compose up` output.

**Operator verification, which is the point of the spec**, run on a machine that
has never had Ergane installed, after the release that carries this:

```bash
export UPSTREAM_MODEL_API_KEY=…
curl -fsSL https://github.com/bryantharpeorg/ergane/releases/latest/download/compose.yaml \
  | docker compose -f - up
```

A stranger sees the stack come up, the driver install and scaffold, one story
dispatched, an agent write code, a gate run, a judge render a verdict, and the
statement that landing was not attempted — with no second command typed.
