"""Where the toolchain is on *this* host, found rather than declared.

Both sandboxes — the agent boundary in `factory.workgraph.adapter` and the gate
boundary in `factory.verify.gates` — must bind a handful of executables
read-only so the process inside can run at all: the package manager, node, git,
and the agent runner itself. Until this module existed they named those paths as
string literals, and the literals carried two things that are not facts about
software, only facts about one machine on one afternoon:

- **An operator's home.** `/home/admin/...`. Any other `HOME` could not run an
  attempt or a gate; the failure was `bwrap: Can't find source path`, from a
  process that had already forked, in a launch that reported `agent_error` with
  no diff. That is what blocked the second install.
- **A version number.** `/home/admin/.local/share/claude/versions/2.1.223`,
  `/home/admin/.nvm/versions/node/v22.22.2/bin/node`. The installer keeps
  several versions and prunes on its own schedule — at the time this was written
  the store held `2.1.222`, `2.1.223` and `2.1.224` while the adapter pinned the
  middle one. One prune turns every dispatch into the same mount error.

So: discover. `shutil.which` over a search path, resolve what it returns, bind
what was actually found, and derive the container's `PATH` from those same
resolutions instead of from a third copy of the literals. A tool that cannot be
found raises `ToolchainError` *before* the sandbox forks, naming the tool and
where it looked — which is what the old comment above the literal list promised
("a named refusal rather than silently widening the mount set") and never
delivered.

Two design points that are not obvious:

**The search path is wider than `PATH`.** The worker runs as a systemd user
unit, and its `PATH` is `/home/admin/.local/bin:/home/admin/.temporalio/bin:
/usr/local/bin:/usr/bin:/bin` — which contains no node at all, because nvm puts
node under a per-version directory that only an interactive shell's `nvm use`
prepends. A discovery that consulted `PATH` alone would refuse every dispatch on
the very host it was meant to keep working. `toolchain_search_dirs` therefore
appends the per-user locations a toolchain installer actually uses, nvm's
version directories among them, *discovered by listing the directory* rather
than by naming a version.

**The runner's install layout is read, not assumed.** `claude` on PATH is a
symlink into `<install>/versions/<version>`; the version file is what must be
bound at the symlink's path, or the symlink dangles inside the namespace. The
gate boundary needs the whole install directory instead — see `install_root` —
because a gate may launch an inner agent whose own version pin it cannot know.
Both are derived, so neither can rot. They are *separately* derived
(`find_install_root`) rather than one read off the other, because the launcher
and the payload go missing independently: a boundary built by a factory that
predates this module carries the payload and not the launcher.

**The system tree underneath them is discovered on the same terms.** The two
boundaries also opened their argv with a hand-written `/usr` bind and two
`--symlink` entries, above a comment asserting that this host has no `/lib64` —
true of the aarch64 machine the line was written on, false of every x86_64
Linux, where the container then has no dynamic loader and the agent cannot
start at all. `system_tree_argv` walks `/bin`, `/lib`, `/lib64` and `/sbin` on
the host it is given and emits an entry for each one the host really keeps as a
symlink, with that link's own target. Same rule, same refusal shape, one
implementation for both boundaries.

Evidence that the host these literals described is unchanged. Discovery run in
the worker's own environment — `PATH=/home/admin/.local/bin:/home/admin/
.temporalio/bin:/usr/local/bin:/usr/bin:/bin`, read from `/proc/<worker>/environ`
— returns exactly the four paths the literals named:

    uv      found_at=/home/admin/.local/bin/uv
    node    found_at=/home/admin/.nvm/versions/node/v22.22.2/bin/node
    git     found_at=/usr/bin/git
    claude  found_at=/home/admin/.local/bin/claude
            real=/home/admin/.local/share/claude/versions/2.1.223

node is the one that proves the widened search path is load-bearing rather than
decorative: it is on no entry of that PATH, and a `shutil.which` over `PATH`
alone would have refused every dispatch on the machine this was written to keep
running.

Dumping both sandboxes' assembled argv before and after the change, in that same
environment, the agent boundary comes out byte-for-byte identical and the gate
boundary differs by exactly one entry — the runner's `PATH` name, which the gate
did not carry before because nothing inside it used to look the runner up:

    --- before.json
    +++ after.json
    @@ -46,6 +46,9 @@
       "--ro-bind",
       "/home/admin/.local/share/claude",
       "/home/admin/.local/share/claude",
    +  "--symlink",
    +  "/home/admin/.local/share/claude/versions/2.1.223",
    +  "/home/admin/.local/bin/claude",
       "--ro-bind",
       "/home/admin/.local/share/uv/python",
       "/home/admin/.local/share/uv/python",

That is the only change to either mount set, and it is a symlink rather than a
mount: the file it points at was already inside the boundary via the
install-directory bind on the line above, so nothing new crosses. What changed is
that the name the container's own `PATH` already advertised now resolves. Why a
symlink and not a bind is `BwrapGateExecutor._toolchain_binds`'s subject.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

#: The package manager every gate command in this factory shells out to.
UV = "uv"

#: The javascript runtime. Bound because the agent's inner loop reaches for it,
#: not because the runner needs it — the runner is a native binary on this host.
NODE = "node"

#: Version control. The agent commits, the gate diffs, the salvage path reads.
GIT = "git"

#: The agent runner. Its *name* is the adapter's `DEFAULT_EXECUTABLE`; this
#: module never assumes which one, it is passed in.
DEFAULT_AGENT_RUNNER = "claude"

#: Directories appended to `PATH` when searching, after it and in this order.
#: `/bin` is not listed: on every host this factory targets it is a symlink to
#: `/usr/bin`, and a duplicate would only lengthen the refusal message.
_SYSTEM_FALLBACK_DIRS: tuple[str, ...] = ("/usr/local/bin", "/usr/bin")

#: The directory bwrap is guaranteed to be able to find `bash` in, appended to
#: the container `PATH` when no resolved tool already contributed it.
_CONTAINER_PATH_FLOOR = "/usr/bin"


#: The one system directory a sandbox binds. Everything else the container's
#: `/bin`, `/lib`, `/lib64` and `/sbin` resolve to lives under it.
SYSTEM_TREE_ROOT = "/usr"

#: The paths a usr-merged host keeps as symlinks into `/usr`, walked in mount
#: order. Which of them a given host actually has is *read*, never assumed: the
#: set differs by architecture and by distribution, and the two entries that
#: used to be written out by hand were the set on one aarch64 machine.
MIRRORED_SYSTEM_PATHS: tuple[str, ...] = ("/bin", "/lib", "/lib64", "/sbin")


class ToolchainError(RuntimeError):
    """A tool a sandbox must mount was not found on this host.

    Raised while the argv is being assembled, so the caller can refuse by name
    instead of letting bwrap fail on a source path after the fork.
    """


class SystemTreeError(ToolchainError):
    """A system path a sandbox must mirror is not something it can mirror.

    A subclass, because both boundaries already turn a `ToolchainError` into a
    refusal that never forks — the gate into a 127 outcome carrying the reason,
    the adapter into an `AdapterError` the ladder does not charge as an attempt
    — and the system tree wants exactly that treatment. Naming it separately is
    what lets a caller or a test tell "this host has no node" from "this host's
    `/usr` is not a directory".
    """


@dataclass(frozen=True)
class ResolvedTool:
    """One executable, as the host actually holds it.

    `found_at` is the path a `PATH` lookup returned — possibly a symlink, and
    the path the container's `PATH` must name. `real_path` is what that
    resolves to, which is what a bind mount has to take as its source when the
    two differ (the agent runner's `claude` symlink is exactly that case).
    """

    name: str
    found_at: Path
    real_path: Path

    @property
    def bin_dir(self) -> Path:
        """The directory the container's `PATH` must name for this tool."""
        return self.found_at.parent

    @property
    def bind(self) -> tuple[str, str]:
        """`(host source, container destination)` for a read-only leaf bind."""
        return (str(self.real_path), str(self.found_at))


def _describe(path: Path) -> str:
    """What is at `path`, in words a refusal can carry."""
    if path.is_symlink():
        return f"a symlink to {os.readlink(path)!r}"
    if not path.exists():
        return "nothing at all"
    if path.is_dir():
        return "a directory"
    if path.is_file():
        return "a regular file"
    return "neither a directory nor a regular file"


def system_tree_argv(root: Path | str = Path("/")) -> list[str]:
    """The sandbox's system tree, read off a host rather than declared.

    Returns the bwrap tokens that give the container a system tree: `/usr`
    bound read-only, followed by one `--symlink` for each of
    `MIRRORED_SYSTEM_PATHS` that **this host has as a symlink**, carrying the
    host's own target verbatim. The destinations are always the container's
    canonical paths; only the sources are read from `root`, which is what lets
    a test supply a layout instead of asserting the machine it runs on.

    Both boundaries call this — the agent's in `factory.workgraph.adapter` and
    the gate's in `factory.verify.gates`. They used to open their argv with the
    same three literal entries and the same comment claiming there was no
    `/lib64` "on this host", and the claim was true of the aarch64 machine the
    line was written on and false of every x86_64 Linux, where the loader lives
    at `/lib64/ld-linux-x86-64.so.2` and a container without it starts nothing.
    Two copies of a fact about one machine is how they came to be wrong in the
    same way twice, which is why this is one function and not a corrected pair.

    Three cases, and the difference between them is the whole story:

    - **A symlink.** Mirror it: `--symlink <readlink(p)> <p>`. The target is
      read, not constructed, so a host whose `/lib` points somewhere unusual
      gets that somewhere.
    - **Absent.** Emit nothing, and do not refuse. `/lib64` is absent on
      aarch64; binding a path that is not there is `bwrap: Can't find source
      path` from a process that has already forked, which is the same defect
      pointing the other way, and refusing would disable every dispatch on the
      machine this factory runs on.
    - **Anything else.** A directory is tolerated — a host with an un-merged
      `/usr` can be bound there and has nothing to mirror — but no entry is
      emitted for it, because a mirrored entry means a symlink and this is not
      one. A path that is neither raises `SystemTreeError`, naming it and what
      was found, while the argv is still a list.

    `/usr` itself is the one requirement: it must exist and be a directory, or
    there is no system tree to build and no defensible guess to make.
    """
    host_root = Path(root)

    usr = host_root / SYSTEM_TREE_ROOT.lstrip("/")
    if not usr.is_dir():
        raise SystemTreeError(
            f"sandbox system tree: {SYSTEM_TREE_ROOT} must be a directory to "
            f"bind read-only, but {usr} is {_describe(usr)}. The container's "
            f"whole toolchain resolves under it, so there is nothing to build "
            f"and nothing to guess."
        )
    argv: list[str] = ["--ro-bind", str(usr), SYSTEM_TREE_ROOT]

    for mirrored in MIRRORED_SYSTEM_PATHS:
        path = host_root / mirrored.lstrip("/")
        if path.is_symlink():
            argv.extend(["--symlink", os.readlink(path), mirrored])
        elif not path.exists():
            continue
        elif not path.is_dir():
            raise SystemTreeError(
                f"sandbox system tree: {mirrored} on this host is "
                f"{_describe(path)} ({path}), which can be neither mirrored as "
                f"a symlink nor bound as a directory. Refusing here, before "
                f"anything forks, rather than letting bwrap fail on the source "
                f"path inside a namespace that has already been created."
            )
    return argv


def _home(env: Mapping[str, str] | None = None) -> Path:
    """The home directory to search under — the process's, not an operator's."""
    source = os.environ if env is None else env
    raw = source.get("HOME")
    if raw:
        return Path(raw)
    return Path.home()


def _version_sort_key(name: str) -> tuple[int, ...]:
    """Order `v22.22.2` after `v18.20.4`, numerically rather than lexically.

    Lexical order puts `v9` after `v22`, which would bind a node three major
    versions old on a host that keeps both. Non-numeric names sort lowest.
    """
    numbers = re.findall(r"\d+", name)
    return tuple(int(number) for number in numbers[:4]) if numbers else (-1,)


def _nvm_bin_dirs(home: Path) -> list[Path]:
    """nvm's per-version `bin` directories, newest first.

    The directory is *listed*; no version appears in this file. nvm's
    `alias/default` is deliberately not consulted: it records what an
    interactive shell would pick, and the container's `PATH` is derived from
    whatever is bound here, so the two cannot disagree.
    """
    versions_dir = home / ".nvm" / "versions" / "node"
    if not versions_dir.is_dir():
        return []
    try:
        candidates = [entry for entry in versions_dir.iterdir() if (entry / "bin").is_dir()]
    except OSError:
        return []
    candidates.sort(key=lambda entry: _version_sort_key(entry.name), reverse=True)
    return [entry / "bin" for entry in candidates]


def toolchain_search_dirs(env: Mapping[str, str] | None = None) -> list[Path]:
    """Directories to look for a tool in, in priority order, deduplicated.

    `PATH` first — whatever the caller's environment says is authoritative — then
    the per-user install locations a `PATH` may legitimately omit, then the
    system directories. The widening is what makes discovery work under a
    systemd user unit whose `PATH` predates the toolchain that was installed
    into `~/.local/bin` and `~/.nvm`.
    """
    source = os.environ if env is None else env
    dirs: list[Path] = []

    raw_path = source.get("PATH") or os.defpath
    for entry in raw_path.split(os.pathsep):
        if entry:
            dirs.append(Path(entry))

    home = _home(env)
    dirs.append(home / ".local" / "bin")
    dirs.extend(_nvm_bin_dirs(home))
    dirs.extend(Path(entry) for entry in _SYSTEM_FALLBACK_DIRS)

    seen: set[str] = set()
    unique: list[Path] = []
    for directory in dirs:
        key = str(directory)
        if key in seen:
            continue
        seen.add(key)
        unique.append(directory)
    return unique


def find_tool(name: str, *, env: Mapping[str, str] | None = None) -> ResolvedTool | None:
    """Resolve one executable, or `None` when this host does not have it."""
    search = os.pathsep.join(str(directory) for directory in toolchain_search_dirs(env))
    found = shutil.which(name, path=search)
    if found is None:
        return None
    found_at = Path(found)
    try:
        real_path = found_at.resolve(strict=True)
    except OSError:
        # A dangling symlink on PATH is not a tool; bwrap would refuse its
        # source path exactly as if it were missing, so treat it as missing.
        return None
    return ResolvedTool(name=name, found_at=found_at, real_path=real_path)


def require_tool(
    name: str, *, purpose: str, env: Mapping[str, str] | None = None
) -> ResolvedTool:
    """Resolve one executable or refuse by name, before anything forks."""
    tool = find_tool(name, env=env)
    if tool is not None:
        return tool
    searched = os.pathsep.join(str(directory) for directory in toolchain_search_dirs(env))
    raise ToolchainError(
        f"toolchain discovery failed: {name!r} was not found on this host, and "
        f"{purpose} cannot be built without it. Searched: {searched}. Install "
        f"it or put it on the worker's PATH — the sandbox binds what discovery "
        f"returns, never a hardcoded path."
    )


def resolve_toolchain(
    names: Sequence[str],
    *,
    purpose: str,
    optional: Iterable[str] = (),
    env: Mapping[str, str] | None = None,
) -> list[ResolvedTool]:
    """Resolve a sandbox's tools in order, refusing by name on the first miss.

    Order is the caller's and is load-bearing twice over: it is the order the
    binds are emitted in, and it is the order `container_path` derives the
    container's `PATH` from. A name in `optional` is skipped when absent rather
    than refused — the gate boundary treats node and the agent runner that way,
    because a repository whose gates need neither still has gates that run.
    """
    optional_names = set(optional)
    resolved: list[ResolvedTool] = []
    for name in names:
        if name in optional_names:
            tool = find_tool(name, env=env)
            if tool is not None:
                resolved.append(tool)
            continue
        resolved.append(require_tool(name, purpose=purpose, env=env))
    return resolved


def container_path(tools: Sequence[ResolvedTool]) -> str:
    """The `PATH` to set inside the namespace, derived from what was bound.

    Inherited `PATH` names host directories that are not mounted, so the
    container needs its own — and the only defensible source for it is the set
    of directories the binds actually put there. Deriving it means a host whose
    node lives somewhere else gets a `PATH` naming that somewhere else, with no
    second list to keep in step.

    `/usr/bin` is appended when no tool contributed it: bwrap execs `bash` for a
    gate command by name, and a `PATH` without it turns every gate into
    "bash: command not found".
    """
    dirs: list[str] = []
    for tool in tools:
        entry = str(tool.bin_dir)
        if entry not in dirs:
            dirs.append(entry)
    if _CONTAINER_PATH_FLOOR not in dirs:
        dirs.append(_CONTAINER_PATH_FLOOR)
    return ":".join(dirs)


def install_root(tool: ResolvedTool) -> Path:
    """The runner's whole installation when it uses a versioned layout.

    The agent runner installs as `<install>/versions/<version>` with a symlink
    on `PATH` pointing at the current one. The gate boundary binds the whole
    install directory rather than the version the *outer* launch resolved,
    because a gate may launch an inner agent that resolves a different one — the
    installer can prune and repoint between the two. A runner that is just a
    binary somewhere yields that binary, so the caller's bind is a leaf either
    way and the mount set never widens beyond the layout that is really there.
    """
    if tool.real_path.parent.name == "versions":
        return tool.real_path.parent.parent
    return tool.real_path


def find_install_root(
    name: str, *, tool: ResolvedTool | None = None, env: Mapping[str, str] | None = None
) -> Path | None:
    """The runner's installation directory, launcher on `PATH` or not.

    Two routes, tried in that order, because they fail independently:

    1. **Through the launcher.** If `name` resolves, its installation is read
       off the resolution (`install_root`). This is the authoritative route: it
       names the installation the thing that would actually run belongs to.

    2. **Beside a `bin` directory on the search path.** An XDG-layout installer
       puts the launcher at `<prefix>/bin/<name>` and the payload at
       `<prefix>/share/<name>`, so every `bin` directory already on the search
       path names a candidate prefix. Nothing is assumed about which prefix, and
       the candidate has to exist as a directory to qualify — which is also why
       the directory must really be named `bin`, rather than the rule being
       "look beside anything on the search path".

    Route 2 is not defensive padding; it is the route the *nested* case needs,
    and leaving it out was a measured regression. Inside a gate boundary built
    by a factory that predates this module, `~/.local/share/claude` is mounted
    but `~/.local/bin/claude` is not — the old code bound the payload by literal
    and never needed a launcher to reach it. A discovery that could only arrive
    *through* `PATH` therefore found nothing where the old literal found the
    directory, and the gate one level in failed with

        ls: cannot access '/home/admin/.local/share/claude/versions':
        No such file or directory

    which is the same test, and the same message, that made the previous commit
    necessary. The same shape occurs outside any boundary, on any host that has
    the runner installed but not linked onto the worker's `PATH`. Both routes
    are derived; neither names a home or a version.
    """
    resolved = tool if tool is not None else find_tool(name, env=env)
    if resolved is not None:
        return install_root(resolved)
    for directory in toolchain_search_dirs(env):
        if directory.name != "bin":
            continue
        candidate = directory.parent / "share" / name
        if candidate.is_dir():
            return candidate
    return None
