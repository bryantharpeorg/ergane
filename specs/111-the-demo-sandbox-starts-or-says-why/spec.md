---
state: draft
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
---

# Feature Specification: the demo sandbox starts, or says why

**Created**: 2026-08-27
**Depends on**: 110 (landed, attested). US1 → US2 are sequential; both touch
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

## Work Graph

```yaml
US1:
  implements: []
  depends_on: []
US2:
  implements: []
  depends_on: []
  depends_on_merged: [US1]
```

Chain depth 2. US2 is sequential rather than concurrent because US1 introduces
the shared remedy constant that US2's committed-path assertion reads, and both
stories edit `factory/controlplane/verify.py`.

## Requirements (summary — numbered at refinement)

Two named sandbox refusals distinguished by their measured stderr; one shared
remedy source across both tiers; an unrecognised failure that admits it; the
committed AppArmor profile and its parsed-directive test; the two corrected
comments with the path pin retained; and the docs procedure pinned to the
committed file.

## Success Criteria (summary)

Pasted: the two refusal transcripts side by side, showing different remedies for
different stderr; the profile-directive test output; the before-and-after of both
corrected comments.

**Operator verification, which is the point of the spec**, and which no task in
this spec can perform: on a machine that has never had Ergane and has never had
`/etc/apparmor.d/bwrap`, run the released demo, read the refusal, follow only
what it says, and run it again. The second run reaches the halt statement. Until
that has been done once, this spec has improved a sentence and proved nothing.
