---
state: landed
# LANDED 2026-08-29. All three stories are on ergane-buildout: US3 at 50a82f1
# (#371), US1 at 5345044 (#372), US2 at eda14ed (#373), all merged 2026-08-28
# evening. Flipped off `ready` because a spec left at `ready` after its stories
# land is re-dispatched by the next roadmap tick: on 2026-08-29 that happened,
# and the re-dispatched US3 was handed a base_ref (eda14ed) that already
# contained its own work, so four attempts produced empty diffs before the agent
# escalated. See specs/090-the-factory-reads-origin-not-the-operators-checkout.
#
# DRAFTED 2026-08-27 by the operator session, against ergane-buildout at 3e5c940
# (0.5.0 released, 110 landed and attested). Every file:line below was read from
# that commit and verified against the tree before drafting.
#
# WHY THIS EXISTS. On 2026-08-27 the released demo was run end to end from
# `docs/onramp.html`, verbatim, on the floor host: cold volumes, one command,
# `us1 PASSED` at 6m23s. It worked. The reason it worked is not a reason a
# stranger has.
#
# MEASURED THAT DAY, on this host (kernel 6.17.0-1018-nvidia, Ubuntu, `sysctl
# kernel.apparmor_restrict_unprivileged_userns = 1`), inside a container running
# under `container/compose.demo.yaml`'s exact security options:
#
#     /usr/bin/bwrap  --dev-bind / / --unshare-user --unshare-pid --proc /proc
#         -> exit 0
#     cp /usr/bin/bwrap /tmp/bwrap-copy && /tmp/bwrap-copy  <same argv>
#         -> bwrap: setting up uid map: Permission denied   (exit 1)
#
# Same binary. Same container. Same security options. The only difference is the
# path, and therefore which AppArmor profile the kernel attaches on exec. The
# sandbox child's label was read directly and is `bwrap (unconfined)` — the
# profile at /etc/apparmor.d/bwrap, `profile bwrap /usr/bin/bwrap
# flags=(unconfined) { userns, }`. `dpkg -S /etc/apparmor.d/bwrap` reports no
# package owns it; it is root-created, dated 2026-07-16, hand-installed during
# Ergane's original sandbox bring-up. `/etc/apparmor.d/unprivileged_userns`,
# which is what a binary with no matching profile falls to, IS package-owned by
# `apparmor`.
#
# THE FALSE BELIEF THIS SPEC EXISTS TO CORRECT. Two load-bearing comments state
# the opposite of the measurement:
#   - `factory/workgraph/adapter.py:293-295`: "Ubuntu 24.04's AppArmor profile
#     permits unprivileged user namespaces only for the system binary at this
#     path (trap 6); a copied or vendored binary has no profile and fails with
#     EPERM."
#   - `factory/controlplane/verify.py:248-250`: "Only `/usr/bin/bwrap` carries
#     the AppArmor grant the adapter relies on."
# Both read as though the grant is a distro default. It is not. The second half
# of each sentence is right — the pinning is correct and stays — but the premise
# is a local artifact described as a property of Ubuntu.
#
# THIS WAS ALREADY KNOWN AND WRITTEN DOWN. `docs/container-onramp-research-findings.md:101-109`
# says it plainly: "That stub is not stock Ubuntu 24.04. The `apparmor` package
# ships ~90 such stubs (`crun`, `podman`, `linux-sandbox`, `flatpak`…) but **not**
# `bwrap`; the bubblewrap .deb doesn't ship it either… This means the native path
# has the same undocumented host dependency… `ergane install` should own placing
# this file." Nothing dispatched that sentence. This spec is that sentence,
# dispatched.
#
# THE OPERATOR'S RULING, taken 2026-08-27 with three options on the table
# (honest refusal + accurate remedy / move the demo to config G / both as two
# stories): the honest refusal. Config G is verified and better confinement, but
# it makes the stranger's FIRST command fail until they load a profile, which
# trades a legible refusal for a mandatory prerequisite. This spec keeps config F
# and makes the refusal worth reading. Config G remains available and unspec'd.
#
# WHAT THIS SPEC DOES NOT DO. It does not install anything on a host. Nothing
# here runs `sudo`, writes to `/etc`, or calls `apparmor_parser`. The research
# note's suggestion that `ergane install` "should own placing this file" is
# deliberately NOT taken: a tool that silently widens a host's sandbox policy is
# a different consent surface than a tool that tells you what to widen and why.
# Placing it stays the operator's deliberate act. This spec ships the file, names
# it in every refusal, and proves the file the refusal names exists.
#
# ── AMENDED 2026-08-28 ────────────────────────────────────────────────────────
# US3 was added after the released demo was run on a stranger-shaped machine — a
# fresh multipass VM, Docker newly installed, cold volumes — and failed in a way
# this spec's rule already covers but none of its stories reached.
#
# WHAT WAS OBSERVED, in the `docker compose up` stream:
#
#     gateway-1 | litellm.exceptions.AuthenticationError: OpenAIException -
#         {"error":{"message":"Unauthorized","type":"api_error","param":null,"code":null}}
#     gateway-1 | . Received Model Group=demo/implementer
#     gateway-1 | INFO: 172.18.0.4:46220 - "POST /v1/messages?beta=true" 401 Unauthorized
#     gateway-1 | LiteLLM Proxy:ERROR: No deployments available for selected model,
#         Try again in 5 seconds. Passed model=demo/implementer
#         cooldown_list=['37d908d8fa93c875108b8e7481b2e932c223eda34ffc139cefc32e247a97a229']
#
# Read in order: the upstream (Ollama Cloud) rejected the credential; LiteLLM put
# the alias's only deployment into cooldown; every call after that returned 429
# "No deployments available", which reads like a rate limit and is not one. The
# second error is louder than the first and names the wrong cause.
#
# By the time that printed, the demo had installed, scaffolded, committed, probed
# the sandbox, derived a one-story graph, and DISPATCHED. It spent the stranger's
# attempt against a credential the stack had already proven it could not use.
#
# WHY IT GOT THAT FAR, and this is the whole of US3. `ergane install --from-file`
# runs the full control-plane verification and returns EXIT_USER when any check
# fails (`factory/cli/install.py:1279-1281`). The LLM probe completes one token
# per distinct registry alias (`factory/controlplane/verify.py:534-581`), so with
# a bad upstream key every `demo/` alias fails and the `llm` finding is FAIL.
# That verdict was computed, rendered, and printed. The driver then discarded it:
#
#     factory/supervision/demo_driver.py:339-347
#         if install_status != 0:
#             # Install's exit code is control-plane *verification*, not whether
#             # the config was written: an unauthenticated `gh` is a FAIL and is
#             # also the normal state of a demo container. …
#             emit("control-plane verification reported findings (exit …); "
#                  "the configuration was written, so preparation continues")
#
# That tolerance is right about `gh` and wrong in its width. One exit code stands
# for seven checks, so the check that means "nothing you do next can work" is
# indistinguishable from the check that means "you are not logged in to GitHub",
# which this demo never needs — it halts before a pull request by construction.
#
# `main`'s own docstring (`demo_driver.py:719-724`) calls the gate between the
# phases absolute and then enumerates it: "a control plane that wrote no config,
# a sandbox that could not start". The design was right. The enumeration was one
# item short, and the missing item is the one that costs money.
#
# ALSO OBSERVED: `container/compose.demo.yaml:125` declares the credential as
# `${UPSTREAM_MODEL_API_KEY}`, and Compose answers an unset variable with a
# warning and an empty string. A stranger who never exported it gets a stack that
# starts, looks healthy for six minutes, and then fails identically to one whose
# key is merely wrong. `tests/test_109_us2_demo_compose.py:795-830` already
# predicted this experience in prose — "the demo looks like it worked and dies at
# the first agent call with a 401 that does not name its cause" — while testing
# only that the docs and the compose file name the same variable.
#
# THE OPERATOR'S RULING, 2026-08-28: fix it first. US3 is dispatched ahead of US1
# and US2. The Work Graph's order is deliberate and is not the story-key order.
---

# Feature Specification: the demo sandbox starts, or says why

**Created**: 2026-08-27 · **Amended**: 2026-08-28 (US3)
**Depends on**: 110 (landed, attested). US3 → US1 → US2 are sequential: US3 and
US1 both edit `factory/supervision/demo_driver.py`, US1 and US2 both edit
`factory/controlplane/verify.py`.

## The gap, stated precisely

Ergane's agent sandbox needs one thing from the host that Ergane neither ships,
places, documents, nor names when it is missing: permission for
`/usr/bin/bwrap` to create an unprivileged user namespace.

On Ubuntu 23.10 and later, `kernel.apparmor_restrict_unprivileged_userns=1`
denies that by default. An executable with no matching AppArmor profile falls to
the package-owned `unprivileged_userns` profile and its `uid_map` write returns
EPERM. The demo's `apparmor=unconfined` does not lift this, because AppArmor
attaches a profile **by executable path on exec** — so the process that matters
is mediated by the *host's* policy no matter what the container declares.

The factory already depends on the fix and believes it is free:

```
factory/workgraph/adapter.py:293-295
    #: Absolute path the bwrap backend is pinned to. Ubuntu 24.04's AppArmor
    #: profile permits unprivileged user namespaces only for the system binary
    #: at this path (trap 6); a copied or vendored binary has no profile and
    #: fails with EPERM.
```

It is not Ubuntu 24.04's profile. It is a file somebody put on this host in
July. Every other machine is a stock machine.

When it *is* missing, what the stranger reads is wrong twice over. The demo
driver's remedy (`factory/supervision/demo_driver.py:145-151`) says:

> `remedy: the agent sandbox needs an unmasked /proc … and make sure
> unprivileged user namespaces are enabled on the host (sysctl
> kernel.unprivileged_userns_clone=1)`

`kernel.unprivileged_userns_clone` is a Debian-era knob. It is not what
restricts this on Ubuntu, and setting it changes nothing. The remedy names a
mechanism that is not the one that fired, and names no file, no profile, and no
command that would work.

## The rule this spec is asking for

**Every refusal the factory prints for a sandbox that could not start names the
mechanism that actually fired, and names a remedy that is present in this
repository — and the grant the factory depends on is a file this project ships
and tests, not a property it attributes to a distribution.**

**And: the demo stops before it spends anything on a stack that has already told
it the spend cannot succeed.** The demo's own verification runs before dispatch
and its verdicts are printed; a verdict that means "the dispatch you are about to
make cannot complete" must stop the driver rather than scroll past. This is the
same rule as the first one, applied to the other thing that has to be true before
an agent starts: the sandbox must be able to run it, and the gateway must be able
to answer it.

### What this spec is not

It is not an installer. Nothing here acquires privilege, writes outside the
repository, or changes a host's confinement policy. It is not a change of
confinement posture: the demo stays config F, `apparmor=unconfined`, exactly as
110 landed it. And it is not a second sandbox — the probe shapes that exist stay
the probe shapes that exist; only what they *say when they fail* changes, and
where the fix they point at lives.

## User Scenarios & Testing

### User Story 1 - A refused sandbox names the restriction that refused it (Priority: P1)

As a stranger whose demo stopped before it spent anything, I read a refusal that
distinguishes which of the two known sandbox refusals fired, and tells me the
one thing to do about that one.

**Why this priority**: P1 and first. This is the story that turns a dead end
into a two-minute fix, and it is reachable by every other machine on earth.

**Independent Test**: drive the refusal formatter over each of the two captured
stderr strings and read back which remedy it produced; no bwrap, no container.

**Acceptance Scenarios**:

1. **Given** a sandbox probe that failed with stderr containing
   `setting up uid map: Permission denied`, **When** the driver formats its
   refusal, **Then** the remedy names AppArmor's unprivileged-userns restriction
   as the cause, names `kernel.apparmor_restrict_unprivileged_userns` as the
   sysctl to read, and points at the profile this repository ships by its
   committed path — proven by a committed test that asserts each of those three
   strings and asserts the string `unprivileged_userns_clone` is **absent**.
2. **Given** a sandbox probe that failed with stderr containing
   `Can't mount proc`, **When** the driver formats its refusal, **Then** the
   remedy names Docker's masked `/proc` paths and `systempaths=unconfined`, and
   does **not** mention AppArmor — proven by a committed test asserting the two
   remedies are different text for different stderr.
3. **Given** a probe failure whose stderr matches neither pattern, **When** the
   driver formats its refusal, **Then** it prints the probe's stderr verbatim
   and one line saying the failure is unrecognised, naming both known remedies
   without asserting either — a refusal that guesses is worse than one that
   admits it does not know.
4. **Given** `HostProbe`'s bwrap check failing on the native tier
   (`factory/controlplane/verify.py:301-330`), **When** `ergane install --verify`
   renders its finding, **Then** that finding carries the same remedy vocabulary
   from the same single source — proven by a test asserting the demo driver and
   the host probe resolve their remedy text from one shared constant, so the two
   tiers cannot drift into two different pieces of advice.

### User Story 2 - The grant is a file this project ships (Priority: P1)

As the repository, I carry the AppArmor profile my own refusals tell operators
to load, and my comments describe it as what it is: a file somebody must put on
the host, not a thing Ubuntu already did.

**Why this priority**: P1. US1's remedy points at a path; this story is what
makes that path resolve. A remedy naming a file that is not in the tree is the
same defect one level down.

**Independent Test**: read the committed profile and assert its text; grep the
two corrected comments; no host, no privilege.

**Acceptance Scenarios**:

1. **Given** this repository, **When** a test looks for the profile the remedy
   names, **Then** it exists at a committed path under `container/`, and its
   content is exactly the four-directive profile measured working on
   2026-08-27 — `abi <abi/4.0>`, `include <tunables/global>`, `profile bwrap
   /usr/bin/bwrap flags=(unconfined)` with `userns,` and a `local/bwrap`
   include — proven by a test that reads the file and asserts on its parsed
   directives rather than on a whole-file digest, so reformatting does not
   break it but removing `userns,` does.
2. **Given** the comment at `factory/workgraph/adapter.py:293-295`, **When** a
   test reads it, **Then** it no longer attributes the grant to Ubuntu and does
   state that the profile is not shipped by any package — proven by a test that
   asserts the phrase attributing it to a distribution release is gone and that
   the committed profile's path is named there. The path pin itself does not
   change: pinning is still correct, and for exactly the measured reason.
3. **Given** the comment at `factory/controlplane/verify.py:248-250`, **When**
   the same test reads it, **Then** it carries the same correction and the same
   pointer.
4. **Given** the shipped profile, **When** the docs sweep runs, **Then** the
   one-time load procedure named in `README.md` and `docs/onramp.html` matches
   the committed file — proven by a test that extracts the profile text from the
   documented procedure and asserts it equals the committed profile, so the page
   and the artifact cannot drift.

### User Story 3 - The demo refuses a credential it has already proven unusable (Priority: P0)

As a stranger whose upstream key is missing, wrong or expired, I am told so
before the demo dispatches a story against it, in a refusal that names the one
environment variable the demo asks me for — rather than after, in a two-hundred
line LiteLLM traceback whose loudest error is a rate limit that is not one.

**Why this priority**: P0 and first. This fired on a real machine on 2026-08-28
and cost a dispatched attempt (spec.md frontmatter). Unlike the sandbox refusal,
it is not conditional on an unusual host: every stranger supplies this credential
by hand, and every way of getting it wrong lands here. The information needed to
refuse is already computed, already rendered, and already on the stranger's
screen when the driver decides to continue past it.

**Independent Test**: drive `run_prepare_phase` with an injected control-plane
verification that returns a failed `llm` finding and assert it returns nonzero,
writes no `prepared` sentinel, and prints a remedy naming the variable; then
drive it with a failed `gh`/`escalation` finding and assert preparation
continues. No container, no gateway, no network.

**Acceptance Scenarios**:

1. **Given** a control plane whose `llm` check fails — the gateway cannot
   complete a token for the aliases the demo dispatches — **When**
   `run_prepare_phase` runs, **Then** it prints the finding's own detail
   verbatim, prints a remedy naming `UPSTREAM_MODEL_API_KEY`, and returns
   nonzero **without** writing the `prepared` sentinel — proven by a committed
   test asserting the return value, the two printed strings, and
   `sentinel_path(state_home, PREPARED_SENTINEL).exists() is False`.
2. **Given** a control plane whose `llm` check passes and whose `host`,
   `escalation`, `memory` or `telemetry` checks fail — an unauthenticated `gh`
   being the ordinary state of a demo container — **When** `run_prepare_phase`
   runs, **Then** preparation continues to the sandbox probe exactly as it does
   today — proven by a committed test that fails a non-`llm` check and asserts
   the phase reaches the probe. The tolerance at `demo_driver.py:339-347` is
   narrowed, not removed.
3. **Given** the set of checks that stop the demo, **When** a test reads it,
   **Then** it is exactly `{"llm"}` — proven by a committed assertion on the
   named constant, so widening or narrowing it is an edit with a test to change
   rather than a judgement buried in a conditional.
4. **Given** an environment with no `UPSTREAM_MODEL_API_KEY` set, **When**
   `docker compose` interpolates the demo file, **Then** it refuses before any
   container is created, with a message naming the variable — proven by a
   committed test asserting the gateway service declares the variable in the
   `${NAME:?message}` required form and that the message names both the variable
   and where an Ollama key comes from, plus the same assertion driven through a
   real `docker compose config` when a daemon is reachable
   (`tests/test_109_us2_demo_compose.py:633-651`).
5. **Given** the demo's own drift tests, **When** the required form changes from
   `${NAME}` to `${NAME:?message}`, **Then** `_is_mandatory`
   (`tests/test_109_us2_demo_compose.py:181-193`) still classifies it as
   mandatory — proven by a committed assertion on that helper directly, so the
   four tests computed from `_mandatory_compose_vars()` cannot become vacuous by
   silently returning an empty set.

## Work Graph

```yaml
US3:
  implements: []
  depends_on: []
US1:
  implements: []
  depends_on: []
  depends_on_merged: [US3]
US2:
  implements: []
  depends_on: []
  depends_on_merged: [US1]
```

Chain depth 3, and the order is not the story-key order. US3 runs first by
operator ruling (spec.md frontmatter): it is the failure that has actually
happened, and it is the only one of the three that costs money when it is not
fixed. US1 follows because it edits the same file US3 does
(`factory/supervision/demo_driver.py`), and US2 follows US1 because US1
introduces the shared remedy source that US2's committed-path assertion reads and
both edit `factory/controlplane/verify.py`.

## Requirements (summary — numbered at refinement)

Two named sandbox refusals distinguished by their measured stderr; one shared
remedy source across both tiers; an unrecognised failure that admits it; the
committed AppArmor profile and its parsed-directive test; the two corrected
comments with the path pin retained; the docs procedure pinned to the committed
file; a demo-fatal check set of exactly `{llm}` enforced before the `prepared`
sentinel; and a compose declaration that refuses an unset credential at
interpolation time.

## Success Criteria (summary)

Pasted: the two refusal transcripts side by side, showing different remedies for
different stderr; the profile-directive test output; the before-and-after of both
corrected comments; and the credential refusal as the driver prints it, beside
the `docker compose config` refusal for an unset variable.

**Operator verification, which is the point of the spec**, and which no task in
this spec can perform: on a machine that has never had Ergane and has never had
`/etc/apparmor.d/bwrap`, run the released demo, read the refusal, follow only
what it says, and run it again. The second run reaches the halt statement. Until
that has been done once, this spec has improved a sentence and proved nothing.

US3 has its own, and it is cheap: run the demo from cold volumes with
`UPSTREAM_MODEL_API_KEY` unset (it must refuse in one second, before Postgres
starts), then with it set to a syntactically plausible but invalid key (it must
refuse after install, before dispatch, naming the variable), then with a real
key (it must reach the halt statement). Three runs, one of which spends. The
middle run is the one that failed on 2026-08-28 and is the reason this story
exists.
