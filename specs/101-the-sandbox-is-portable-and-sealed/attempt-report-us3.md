# Attempt report — 101 US3, *a toolchain failure is annotated, not echoed*

Two tasks are answered here: T021 (FR-010's three untouched things) and T022
(the operator's warm-cache demonstration). Everything is pasted tool output, not
description.

## T021 — FR-010: what this epic did not change

FR-010 names three things every story of this epic must leave alone: the tmpfs
`HOME` decision, the network posture, and the interpreter-bind helper. Checked
across the **whole epic** — US1, US2 and US3 together — rather than across this
story alone, because FR-010 binds every story and only the epic-wide diff can
say whether one of them moved it.

`84ffa26` is the commit before US1 landed; `HEAD` is this story's second commit.

**No changed line in the epic touches any of the three.** Every `+`/`-` line in
the gate module's epic-wide diff that so much as mentions `tmpfs`, `HOME`,
`unshare` or `network`:

```console
$ git diff 84ffa26 HEAD -- factory/verify/gates.py \
    | grep -E '^[+-]' | grep -vE '^(\+\+\+|---)' \
    | grep -iE 'tmpfs|unshare|network|\bHOME\b'
+        #: bounded to the operator's home by the parser that read them. Empty by
+        # destination — the same `--setenv` path `HOME` above takes. This loop
+    # backwards: the install already ran, in a `HOME` the boundary replaced with
+    # a tmpfs. The correction is appended here rather than in an executor
+    # quote the advice is not a toolchain failure, and a `HOME` lecture on a
```

Five lines, all of them comment prose: two of US2's, three of this story's. No
statement among them.

**The tmpfs `HOME` decision — the two argv lines — is byte-identical**, moved
only by the lines US2 inserted above it:

```console
$ git show 84ffa26:factory/verify/gates.py | grep -n -B1 -A1 'argv.extend(\["--tmpfs", str(home)\])'
689-        # A factory-owned home for the gate, writable but not the operator's.
690:        argv.extend(["--tmpfs", str(home)])
691-        argv.extend(["--setenv", "HOME", str(home)])

$ git show HEAD:factory/verify/gates.py | grep -n -B1 -A1 'argv.extend(\["--tmpfs", str(home)\])'
727-        # A factory-owned home for the gate, writable but not the operator's.
728:        argv.extend(["--tmpfs", str(home)])
729-        argv.extend(["--setenv", "HOME", str(home)])
```

**The network posture is unchanged**: the same three `unshare` occurrences, same
text, same meaning — the declaration that egress is out of scope, the pid
namespace, and the docstring sentence FR-010 quotes. Nothing was added and
nothing became a `--unshare-net`:

```console
$ git show 84ffa26:factory/verify/gates.py | grep -n unshare
520:    is intentionally not unshared — egress is out of scope — and the gate runs
704:        argv.extend(["--unshare-pid", "--die-with-parent"])
845:        The boundary deliberately does not unshare the network (egress is out

$ git show HEAD:factory/verify/gates.py | grep -n unshare
549:    is intentionally not unshared — egress is out of scope — and the gate runs
747:        argv.extend(["--unshare-pid", "--die-with-parent"])
888:        The boundary deliberately does not unshare the network (egress is out
```

**The interpreter-bind helper is byte-identical** — same line count, same byte
count, same checksum, before the epic and after it:

```console
$ for R in 84ffa26 HEAD; do
    git show $R:factory/verify/gates.py \
      | sed -n '/    def _interpreter_binds/,/^    def /p' | wc -lc
    git show $R:factory/verify/gates.py \
      | sed -n '/    def _interpreter_binds/,/^    def /p' | md5sum
  done
     50    2675
7f44df8bbe36bb2d1977af0a536a02ca  -
     50    2675
7f44df8bbe36bb2d1977af0a536a02ca  -
```

## T022 — the operator's warm-cache demonstration

### What was run, and the one substitution

The plan asks for a browser-driven smoke gate: declare the browser cache, run
the gate warm and cold, paste both durations. **That form could not be run on
this host, and installing what it needs was not mine to decide.** The host has
`node` (nvm, v22.22.2) and nothing else of a JavaScript world — no `npm`, no
`npx`:

```console
$ ls /home/admin/.nvm/versions/node/v22.22.2/bin/
node
```

Playwright cannot be installed without one, and a package manager is a
dependency: constitution III puts the approved roster at `uv`, `temporalio`,
`httpx`, `pyyaml`, `pytest` and `python-telegram-bot`, and adding to it needs
operator approval first. There is also no browser cache on this host to be warm
about — the operator's cache holds exactly one entry, `uv`.

So the demonstration was run in the package world this host does have, which is
what T022's own closing sentence points at: *the same evidence `_cache_binds`'
own docstring cites for the Python world.* Three configurations of one real gate
(`uv pip install temporalio -q`) in the real bubblewrap boundary, through
`run_gates`, in a linked git worktree — production's shape. Only the cache binds
differ between them; the mount set, the tmpfs `HOME` and the network posture are
identical. Three runs each, fresh worktree and fresh venv every run, median
reported.

The gate also prints what the boundary looks like from inside, because a
duration alone cannot distinguish "the cache was carried" from "the download was
quick today".

### The measurement

```console
$ uv run python demo3.py
A  built-in uv bind (today)            status=PASS median=0.12s runs=[0.16, 0.11, 0.12]
    UV_CACHE_DIR=/home/admin/code/ergane/.ergane/homes/101-the-sandbox-is-portable-and-sealed/us3/.cache/uv
    entries=6
B  declared cache, built-in dropped    status=PASS median=0.12s runs=[0.12, 0.12, 0.11]
    UV_CACHE_DIR=/home/admin/code/ergane/.ergane/homes/101-the-sandbox-is-portable-and-sealed/us3/.cache/uv-declared
    entries=6
C  no cache crosses the boundary       status=PASS median=0.47s runs=[0.47, 0.47, 0.42]
    UV_CACHE_DIR=<unset>
    entries=0
```

**A is today's behaviour** — the built-in bind, `UV_CACHE_DIR` naming the host
cache, six entries visible inside the boundary.

**C is a repository with a JavaScript world before US2**, reproduced by letting
the boundary carry no cache at all: the variable is unset, so the tool falls back
to `$HOME/.cache/uv` — which is inside the tmpfs, and therefore empty. Zero
entries, and the gate still passed, so every wheel it installed came off the
network. **0.47s against 0.12s: 3.9× the warm gate.** On a host without egress
the same run is not slow, it is a FAIL.

**B is the story this epic is about.** The built-in bind is dropped and the
manifest declares the cache instead:

```yaml
caches:
  - path: ~/.cache/uv-declared
    env: UV_CACHE_DIR
```

The declared path is bound, its own variable is set beside it pointing at it,
six entries are visible, and the gate takes the same 0.12s as A. **The declared
route carries a cache exactly as the hardcoded one did** — which is the whole
claim, because a Playwright browser cache rides on that same route with a
different path and a different variable name.

### What this does not prove

It does not prove a browser survives to gate time. That needs a real browser and
a real smoke gate, and this host has neither. What it does prove is the
mechanism underneath: that a cache named in a manifest crosses the boundary
writable, that its variable is set beside it, and that the difference between
carrying it and not is the difference between a cached resolve and a network
one. The browser-shaped confirmation stays the operator's, on a host with a
JavaScript toolchain.

The scratch repository, its origin and the three scripts were built outside this
worktree and are not in the diff; the numbers above are their output.

## This story's own change, in one line

A gate that failed while a tool told the agent to install a toolchain now
carries the boundary's `HOME` fact and the remedy in its failure detail, and
that detail reaches the next attempt's prompt through the path it already took —
asserted end to end in `tests/test_101_toolchain_failure_is_annotated.py`, which
also holds the control: a failure matching no signature is recorded as the same
object it always was.
