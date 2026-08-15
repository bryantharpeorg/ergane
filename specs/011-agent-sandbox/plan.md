# Plan: The worktree is where the agent starts, not where it is kept

Refined against the tree at `0bf0c93` on 2026-08-14 (first pass `5f0042e`,
2026-08-11 — every anchor moved between the two; do not trust the old ones from
a stale checkout). Every anchor below was resolved by hand against `0bf0c93`.
If one does not resolve when you read it, trust the code and say so in your
handoff rather than hunting.

## Decided at refinement: the backend is bwrap (operator decision, 2026-08-14)

The boundary is **bubblewrap**, driven directly — no container image, no
daemon, no new Python dependency. Verified on this host (Ubuntu 24.04.4,
aarch64) on 2026-08-14:

```
$ bwrap --ro-bind /usr /usr --symlink usr/lib /lib --symlink usr/bin /bin \
        --proc /proc --dev /dev --unshare-pid --die-with-parent -- ps -e
    PID TTY          TIME CMD
      1 ?        00:00:00 bwrap
      2 ?        00:00:00 ps
```

Two processes visible from inside: full PID-namespace isolation. The
2026-08-14 `rm -rf .factory` dies because the runtime root is simply not in
the mount set, and the 2026-08-12 `pkill -f "python -"` dies because the
worker is not in the PID namespace.

The alternatives were weighed and declined, so do not relitigate them at
dispatch: Docker is present on this host but its daemon detaches the container
from the adapter's process tree (destroying the deadline machinery trap 2
protects), requires an arm64 image containing the agent toolchain maintained
forever, and its socket is root-equivalent. Podman is not installed. The seam
(US2) is the cross-platform story: a macOS backend (Seatbelt, most credibly
via Anthropic's `sandbox-runtime`) is a future second implementation behind
the same seam; Windows runs Ergane inside WSL2, where bwrap works unchanged.

Consequence for the manifest: the `runtime:` key's value domain changes from a
container image reference to a backend name. `_read_runtime` at
`factory/verify/factory_yaml.py:193` and its error text at `:197` (which
still says "requires a container image reference") change with it, and this
repository's own `factory.yaml:15` — currently
`runtime: ghcr.io/astral-sh/uv:python3.11-bookworm` — is updated to
`runtime: bwrap` in US2's diff. The comment at `factory/verify/models.py:187`
("`runtime` is recorded but execution-reserved") dies in US3's diff, when it
stops being true.

## What to read before writing anything

| Thing | Where | Why |
| --- | --- | --- |
| The entire current boundary | `factory/workgraph/adapter.py:532` | `cwd=str(worktree)` and nothing else. This is what US3 replaces |
| The agent's argv | `factory/workgraph/adapter.py:528` | `argv(context)` — the seam wraps this, it does not rewrite it (FR-011) |
| Why the child is a session leader | `factory/workgraph/adapter.py:521` (docstring), `:534` | `start_new_session=True` exists for the deadline, see trap 2 |
| The pid file and the group kill | `factory/workgraph/adapter.py:290` (`pid_file`), `:804` (`_write_pid_file`), `:835`/`:851` (`killpg`) | The deadline's whole mechanism; US4 must keep it working |
| Transcript archiving | `factory/workgraph/adapter.py:738` (`_archive_session`) | Reads the agent `HOME` and **returns early if the session file is absent** — trap 3 |
| The runtime seam in the manifest | `factory/verify/factory_yaml.py:82` (`_TOP_LEVEL_KEYS`), `:120` (call), `:193` (`_read_runtime`), `:197` (error text) | `runtime:` is parsed and validated today; US2 changes its value domain |
| …and that it is dead | `factory/verify/models.py:187` | *"`runtime` is recorded but execution-reserved — gates run as `bash -c` on the host."* |
| The gate seam to copy | `factory/verify/gates.py:208` | `GateExecutor` is already a `Protocol` |
| The host implementation | `factory/verify/gates.py:351-372` | `["bash", "-c", …]` at `:367`, in the worktree. US5 adds a sibling, it does not edit this |
| The selector | `factory/verify/gates.py:612` | `run_gates` — where US5's second executor is chosen |
| The declared runtime | `factory.yaml:15` | The image reference US2 replaces with `bwrap` |
| The toolchain the agent runs | `~/.local/bin/claude` → `~/.local/share/claude/versions/<v>`, `~/.local/bin/uv`, `~/.nvm/versions/node/<v>/bin/node`, `/usr/bin/git` | All but git live in the **operator's home** — trap 13 |

The shape of this work is still favourable: the manifest already declares a
runtime key, the key is already parsed and validated, and gate execution is
already behind a Protocol with one implementation. US2–US5 are finishing a
design that was drawn and then left unwired — not introducing a concept.

## US1 — the detector

Capture `git status --porcelain` (or equivalent plumbing) over the *target
repository* at attempt start, capture it again at teardown, diff the two, and
file a finding when tracked paths differ. Key it so recurrence is countable per
epic/node, and put the changed paths in the evidence.

Where it hangs is a judgement call the implementer owns, but it must be a place
that runs on **every** termination path — completed, agent error, timeout,
killed — because the breach is likeliest on the paths that end badly. The
teardown bracket that 010 made total (`try/finally` around the key lease) is
the precedent for "runs whatever happens": read it before choosing.

Note the target repo is not always the operator's checkout — it is
`graph.target_repo`. Write it against that, not against a hardcoded path.

## US2 — the seam and the refusal

Put the launch at `adapter.py:528-534` behind a Protocol, following
`GateExecutor` (`gates.py:208`). Two implementations exist when this story
lands: the host launch (today's code, kept — selectable only explicitly, for
US4's control and for nothing else) and the fake the tests drive. The bwrap
implementation arrives in US3; this story gives it a socket to plug into.

The seam resolves the backend from the manifest's `runtime:` key and refuses
when it cannot be provided, naming the backend and the platform — e.g.
"sandbox backend 'bwrap' not available: /usr/bin/bwrap missing on linux". The
refusal must fire *before* any agent process starts. Silent fallback to the
host launch is the one behaviour FR-008 exists to forbid.

This story also changes `_read_runtime`'s value domain and error text
(`factory_yaml.py:193`, `:197`) and updates `factory.yaml:15`, in one diff, so
no window exists where the manifest declares an image nothing can run.

## US3 — the filesystem boundary

The bwrap invocation, concretely. What worked verbatim on this host is the
skeleton; the story fleshes it out:

- `--ro-bind /usr /usr`, `--symlink usr/bin /bin`, `--symlink usr/lib /lib` —
  **there is no `/lib64` on this aarch64 host**; binding it fails with "no
  such file or directory". Build the projection from what exists.
- `--proc /proc --dev /dev --tmpfs /tmp`
- `--bind <worktree> <worktree>` — same absolute path inside and out, so every
  path in prompts, transcripts and pid files stays meaningful. The **leaf**,
  never the runtime root above it (trap 9).
- The git plumbing per trap 1. Route choice, state which you took: the minimal
  set (`.git/worktrees/<node>` plus the shared object store and refs) is
  tighter; binding the parent repo's whole `.git` directory writable is
  acceptable if the minimal set proves brittle, because the working tree does
  not live under `.git` — but say so, because it hands the agent ref-level
  write access to the operator's repo history.
- The toolchain, read-only, per trap 13.
- A factory-owned home, writable, bound from a host path (trap 3), with
  `--setenv HOME` pointing at it — the 018 interplay, trap 4.
- `--unshare-pid --die-with-parent` — the signal boundary US4 asserts.
- **No `--unshare-net`** — egress is out of scope and the agent must reach the
  proxy.
- Invoke `/usr/bin/bwrap` by absolute path — trap 6 explains why this is
  load-bearing and not style.

## US4 — deadlines, transcripts, signals

bwrap is launched as a direct child, in the agent's session and process group,
so the existing `killpg` path (`:835`, `:851`) reaches it — but what it
reaches is bwrap, and only `--die-with-parent` guarantees the namespaced
children die with it. Re-establish the deadline deliberately and prove it with
a deliberately hanging agent (trap 2). The transcript archive at `:738` must
find the session file on the *host* side of the home bind (trap 3). The pkill
containment is asserted on the worker's liveness (trap 11), and the whole
story carries the control: boundary off via the seam's explicit host
implementation, damage reproduced (trap 12, SC-009).

## US5 — the gates

Add a second `GateExecutor` beside the host one at `gates.py:351`. Do not edit
the host implementation; do not change the Protocol at `:208`. `run_gates` at
`:612` picks between them. This is the whole reason `GateExecutor` was made a
Protocol.

## Traps

**Trap 1 — the one that decides the design. A worktree's `.git` is a file, not
a directory.** Verified on this tree:

```
$ cat .factory/worktrees/<epic>/<node>/.git
gitdir: /home/admin/code/ergane/.git/worktrees/<node>
```

So git *inside* the worktree reaches back into the target repository's `.git`
directory, and "just don't mount the target repo" breaks `add`, `commit`,
`diff`, `branch` and salvage — every operation the attempt performs at its
end. The boundary must expose `.git/worktrees/<node>` **and the shared object
store** while keeping the working tree invisible. Get this wrong and the
failure arrives at commit time, after the agent has done all its work, which
is the most expensive place in the ladder to discover it. Prove it with
US3-S2 (`git add`/`commit`/`diff` inside the boundary) before building
anything else in US3.

**Trap 2 — the deadline machinery survives bwrap, but only on purpose.**
`start_new_session=True` (`:534`) makes the launched child a session leader so
its pid *is* its process-group id, the pid file records the pgid
(`_write_pid_file:804`), and the deadline kills the group (`killpg`, `:835`,
`:851`). With bwrap as that child the group kill reaches *bwrap*; the agent
and its spawn live in a PID namespace behind it. `--die-with-parent` is what
makes bwrap's death take the namespace with it — omit it and a killed bwrap
can orphan everything inside, which is a leaked attempt holding a live virtual
key, the exact class 010 spent an epic closing. Also note the pid file now
records bwrap's pgid, not the agent CLI's pid: fine for the group kill, wrong
for anything that assumes the pid is the CLI. FR-006 is not a formality:
re-establish termination deliberately and test it with a deliberately hanging
agent.

**Trap 3 — the transcript disappears silently.** `_archive_session`
(`adapter.py:738`) resolves the session file from the agent's home and
**returns early when it is absent**, because an agent that wrote no transcript
is not an error. Inside the boundary, `HOME` is whatever the mount set says it
is, and the archive step runs on the host: unless the agent's home is a bind
of a host path the archive step can read, every attempt silently stops
producing a transcript and the code treats it as normal. The test that catches
this asserts on the archive's *contents*, not on the environment. This is the
same failure shape 018 carries as its own trap — read that one too.

**Trap 4 — do not let this quietly become 018, or 018 quietly become this.**
If US3 lands first, the agent stops seeing the operator's `HOME` as a side
effect, and it will be tempting to close 018 as done. Do not: 018 *states* the
property, tests it and keeps it stated, and a later change to the mount set
could restore the inherited home with nothing failing. If 018 lands first, US3
must not undo its `PASSTHROUGH_ENV` edit while rearranging the environment.
The two specs are orthogonal on purpose and each keeps its own assertion.

**Trap 5 — the suite must not need the backend, and the live tests must not
skip by marker.** FR-010. Seam-driven tests prove the logic against the fake
and never skip. The tests that drive the *live* boundary (US3-S4, US4-S1,
US4-S3, the control) guard on **detection** — `shutil.which("bwrap")` or the
absolute path — because nothing passes `-m` in CI or the gate, so markers are
decorative (`live-tier-skips-by-guard-not-marker`, an already-filed defect).
On the gate host bwrap is present, so the live tests always run where
verification happens; a host without it still gets a green seam suite, which
is SC-005's exact claim.

**Trap 6 — AppArmor pins the backend to its installed path.** Ubuntu 24.04
sets `kernel.apparmor_restrict_unprivileged_userns = 1`: unprivileged user
namespaces are denied *except* for binaries with an AppArmor profile
permitting them, and `/etc/apparmor.d/bwrap` grants exactly that to
`/usr/bin/bwrap`. A copied, vendored or rebuilt bwrap has no profile and dies
with `EPERM` at namespace creation. Invoke the system binary by absolute path;
if it is absent, that is FR-008's refusal — never a bundled fallback, and
never Docker, which is also on this host and is not the decided backend.
(Rootlessness, which this trap used to be about, is satisfied by construction:
bwrap runs unprivileged as the worker's own uid, no daemon, no root.)

**Trap 7 — the detector must not clean up after the agent.** FR-002. It is
reporting on the operator's own tree, which may contain the operator's own
uncommitted work. A detector that "helpfully" stashes or checks out destroys
real work to make a metric look clean. Read-only, always.

**Trap 8 — do not contain the worker.** Out of scope, and worth restating here
because the refactor invites it: the activities, the workflow and the
merge-queue poller all stay on the host. Only the agent process and the gate
process move.

**Trap 9 — the node worktree is a leaf of the runtime root, and mounting the
root is the whole disaster.** This is the trap the 2026-08-14 incident bought,
and it is the easiest one to walk into because the convenient mount is the
wrong one. The layout is:

```
<runtime-root>/                     <- .ergane/ (or legacy .factory/)
  verification.db  doctor.db  ledger.db   <- the factory's memory
  transcripts/  run/  homes/
  worktrees/<epic>/<node>           <- the agent's worktree, and its siblings
```

So the thing the agent needs is *four levels down* inside the thing it must
never touch. Mounting `<runtime-root>` and trusting the agent to stay in its
subdirectory is the same containment as `cwd=`, which is what this spec exists
to delete. Mount the leaf. The same rule covers the agent home if it lives
under `homes/` — bind the node's own home leaf, never `homes/` itself.

Two consequences worth stating because they are not obvious:

- **"Clean my scratch state" and "destroy every running node" are the same
  command** while worktrees live under the runtime root. The 033/us2 agent
  believed it was doing the first. Consider whether the boundary should also
  move worktrees out from under the state root — that is a larger change than
  this spec, and if you decide against it, say so in the commit so the next
  person knows it was weighed rather than missed.
- **The agent's own worktree was inside the blast radius**, so the attempt
  killed itself, no escalation fired, and the dependent node died too. A
  boundary that protects the stores but still lets an agent delete its own
  worktree has fixed the reporting and not the outage.

**Trap 10 — a detector that lives in the directory it watches reports nothing
on the worst case.** FR-013. US1's natural implementation snapshots state at
attempt start and compares at teardown. If that snapshot lives under the
runtime root, the one event it most needs to catch is the one that deletes the
snapshot. Hold it somewhere the agent cannot reach, and test the case where
the whole root is gone rather than the case where one file changed.

**Trap 11 — `pkill` exit codes cannot tell you the boundary worked.** FR-015
and SC-008. `pkill -f <pattern>` exits 1 when it matched nothing, which is
exactly what a contained agent should see — and also exactly what an
*uncontained* agent sees when its pattern happens to miss. The assertion that
means something is the worker's own liveness after the call. On 2026-08-12 the
pattern `python -` matched the worker's systemd command line and SIGTERMed it
mid-attempt; the mitigation since was to respell `ExecStart` so it carries no
`python -` substring, which dodges one string and is not a boundary. Do not
let that mitigation be mistaken for this requirement being already met.

**Trap 12 — prove this by control, not by a passing suite.** SC-009.
Everything in this spec is a claim that something *cannot* happen, and the
failure mode for that class of claim is a test that passes because the
dangerous thing was never actually attempted. Each containment test needs its
negative twin: the same scripted agent, the boundary disabled via the seam's
explicit host implementation, the damage reproduced. The factory already
believed it had store isolation —
`hardening/test-suite-writes-to-the-live-evidence-store` is marked resolved,
and the store was destroyed anyway by a route no test covered.

**Trap 13 — the agent's toolchain lives in the operator's home.** Verified on
this host: `claude` is `~/.local/bin/claude`, a symlink into
`~/.local/share/claude/versions/<v>`; `uv` is `~/.local/bin/uv`; `node` is
`~/.nvm/versions/node/<v>/bin/node`. Only `git` is in `/usr/bin`. The lazy
mount is `--ro-bind /home/admin /home/admin`, and it hands the agent the
operator's entire home read-only — `~/.config/gh` tokens, `~/.claude.json`,
ssh keys — which is precisely what US3-S3 exists to fail. Bind the specific
leaves read-only instead, and bind the symlink *targets*, not just
`~/.local/bin`, or `claude` dangles inside the boundary. `PATH` inside the
sandbox must then name those bind points. When a version bump moves the
target, the refusal path (FR-008) is what should fire — never a silent
widening of the mount.

## What "done" looks like

A scripted agent that tries to write an absolute path into the target
repository's working tree gets an error on its own tool call; `git status` in
the operator's checkout is byte-identical before and after; the same attempt
still commits, is judged, and lands; the literal `rm -rf .factory` and
`pkill -f "python -"` both bounce off the boundary and both still do damage
with it switched off. Then, on a host with no bwrap installed at all,
`uv run pytest` is green.
