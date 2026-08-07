"""The one place the factory touches an agent (D-018).

Launch a headless coding agent in the node's worktree, watch it, end it when its
deadline passes, classify how it ended, keep what it produced. That is the whole
seam: no diff is read here, no usage is counted here, and nothing the agent
*says* is inspected anywhere (FR-012). A second agent is a second class in this
module — `adapter_for` resolves the persona registry's `agent` field to one — and
the orchestration above it does not change.

Four properties are the reason this file is longer than a `subprocess.run`:

- **The child environment is built, not filtered** (US2-S1). `attempt_env`
  returns exactly the proxy URL, the attempt's virtual key, and a four-name
  passthrough. A denylist would protect the credentials we thought of and leak
  the one the worker host acquires next quarter; by constructing the environment
  the master key and the bot token are absent because nothing put them there
  (constitution V). The virtual key is the only credential that crosses into the
  child, which is exactly what makes the attempt's spend attributable.

- **A deadline ends the process tree.** An agent spawns `git`, `uv`, test
  runners; killing its root leaves grandchildren holding the worktree. So the
  agent gets its own session, the deadline is enforced against the whole process
  *group*, and SIGTERM is followed by SIGKILL once the grace expires — 002's gate
  runner pattern, for the same reason. The bound is enforced here rather than by
  Temporal's `start_to_close_timeout` because a Temporal timeout kills the
  activity and leaves the agent running, forfeiting both the classification and
  the salvage the node's terminal path depends on (R2).

- **The previous attempt is reaped before this one launches** (R4). A worker that
  died mid-attempt leaves an agent alive against the same worktree, and Temporal
  will happily retry the activity into it. Two agents in one worktree is
  corruption, so a pgid file per node is the next run's handle on the last one.
  Reaping is a precaution, not a gate: garbage in that file costs the node
  nothing.

- **Evidence survives every path** (FR-007). `stdout.log` is streamed straight
  into the attempt's archive directory rather than collected at exit, so a killed
  agent leaves what it had printed by the time it died, and the session
  transcript is copied in afterwards on the completed, failed, timed-out and
  killed paths alike. The archive lives under the worker host's `.factory/`,
  never inside a worktree, where salvage would commit the agent's own transcript
  to the node branch and the diff check would read it as work.

Classification is exit status and nothing else: zero → `COMPLETED`, non-zero →
`AGENT_ERROR`, deadline → `TIMEOUT`, cancellation → `KILLED`. `COMPLETED` is a
statement about a process, never a claim that the work is done — the verdict
belongs to component 2, later, from the worktree.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import shutil
import signal
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Protocol

from factory.usage.models import Termination, UsageSnapshot
from factory.workgraph.models import AdapterResult, AttemptContext

#: The agent's combined stdout and stderr, streamed live into the attempt's
#: archive directory. Interleaved as the agent wrote it: two files would put the
#: burden of reconstructing the order on whoever reads the evidence.
STDOUT_LOG_NAME = "stdout.log"

#: Environment variable names the agent inherits from the worker, on top of the
#: two the attempt itself supplies. `PATH` is what finds the agent binary and the
#: tools it shells out to; `HOME` is where it keeps its own session state;
#: `LANG`/`TERM` keep its output decodable and unadorned. A name absent from the
#: worker's environment stays absent from the child's — passthrough is
#: passthrough, not invention.
PASSTHROUGH_ENV: tuple[str, ...] = ("PATH", "HOME", "LANG", "TERM")

#: The agent CLI, resolved from the child's `PATH` (R6). Not configurable: which
#: binary a persona runs is the registry's `agent` field, which selects a class.
DEFAULT_EXECUTABLE = "claude"

#: Seconds between SIGTERM and SIGKILL at the deadline. Long enough for an agent
#: to flush the session transcript that is about to become the only account of
#: what it was doing, short enough that ignoring TERM buys nothing.
DEFAULT_GRACE_S = 10.0

#: How often the adapter beats while waiting (R2) — the interval that makes a
#: multi-hour attempt cancellable in seconds rather than at its deadline.
#:
#: One second, not the leisurely half-minute a liveness signal would need,
#: because the beat is also the *only* channel a kill travels down: Temporal
#: delivers activity cancellation in a heartbeat's response, and its client
#: batches beats to one round trip per 80% of the activity's heartbeat timeout.
#: The interval and that timeout therefore bound how long an agent keeps
#: spending after an operator says stop (`workflow._AGENT_HEARTBEAT_TIMEOUT`
#: derives from this constant for exactly that reason). Beating this often costs
#: nothing — it is an in-process call whose round trips are batched away, and the
#: monitor loop is already awake to check the deadline.
DEFAULT_HEARTBEAT_INTERVAL_S = 1.0

#: Seconds between usage reads while the agent works (R3, plan US1). Much slower
#: than the beat: the read is a proxy round trip, throttled to its own cadence so
#: an hours-long attempt issues a bounded number of `/key/info` calls. The same
#: value the old loop polled at, so moving the read inside the activity does not
#: change how often the proxy is queried — it only stops charging the workflow's
#: history for it (FR-001, FR-002).
DEFAULT_POLL_INTERVAL_S = 30

_NON_ALNUM = re.compile(r"[^a-zA-Z0-9]")


async def _invoke_heartbeat(
    heartbeat: Callable[[UsageSnapshot | None], Awaitable[None] | None],
    snapshot: UsageSnapshot | None,
) -> None:
    """Fire the beat, tolerating a sync or async callback.

    Temporal's `activity.heartbeat` is sync; a test's spy may be `async def`.
    The snapshot is the beat's details — the only reason a callback is ever
    interesting is what it carries, so a callback that raises is a real defect
    (unlike a spend read failing) and propagates.
    """
    result = heartbeat(snapshot)
    if result is not None:
        await result


class AdapterError(RuntimeError):
    """The agent could not be run at all — infrastructure, never a verdict.

    Distinct from a non-zero exit, which is an `AGENT_ERROR` termination and
    ordinary ladder input. This is "there is no such adapter" or "the binary is
    not on the worker host": a config error the operator has to fix, and one the
    ladder must not spend an attempt on.
    """


# The seam (D-018) ------------------------------------------------------------


class AgentAdapter(Protocol):
    """What the factory needs from an agent runner, entire.

    One method, not the five-step decomposition contracts/adapter.md sketches
    (launch/monitor/terminate/classify/transcript): those steps are real, but
    they are steps of *one policy* — the deadline, the process-group termination,
    the reap, the archive — and a protocol that exposed them would make every new
    adapter re-implement that policy, with the FR-007 and US2-S3 guarantees
    riding on each one getting it right. What genuinely differs between agents is
    how a prompt becomes a process, so that is what a second class overrides.
    """

    #: The persona registry's `agent` value that selects this adapter.
    name: str

    async def run_attempt(
        self,
        context: AttemptContext,
        *,
        factory_root: Path | str,
        heartbeat: Callable[[UsageSnapshot | None], Awaitable[None] | None] | None = ...,
        heartbeat_interval_s: float = ...,
        read_usage: Callable[[], Awaitable[UsageSnapshot]] | None = ...,
        poll_interval_s: float = ...,
    ) -> AdapterResult: ...


def adapter_for(agent: str, **options: Any) -> AgentAdapter:
    """The adapter a persona's `agent` field names (constitution VII).

    Unknown names raise rather than falling back to Claude Code: a persona
    naming an agent the factory cannot run is a registry error, and silently
    dispatching to a different agent would produce work nobody asked for under
    a model nobody chose.
    """
    implementation = _ADAPTERS.get(agent)
    if implementation is None:
        known = ", ".join(sorted(_ADAPTERS)) or "<none>"
        raise AdapterError(
            f"no adapter for agent '{agent}' (known: {known}) — a second agent is "
            "a second class in factory/workgraph/adapter.py (D-018)"
        )
    return implementation(**options)


# Paths on the worker host (plan.md § Storage) --------------------------------


def transcript_dir(
    factory_root: Path | str, epic_id: str, node_id: str, attempt: int
) -> Path:
    """`.factory/transcripts/<epic>/<node>/attempt-<n>/` — this attempt's evidence.

    Keyed by the same `(epic, node, attempt)` identity as the virtual key and the
    ledger row, so an archived run is attributable without a lookup, and retries
    of one node never overwrite the record a retry prompt quotes (FR-006).
    """
    return Path(factory_root) / "transcripts" / epic_id / node_id / f"attempt-{attempt}"


def pid_file(factory_root: Path | str, epic_id: str, node_id: str) -> Path:
    """`.factory/run/<epic>/<node>.pid` — the next run's handle on this one (R4).

    Keyed by node rather than attempt because the worktree is the resource being
    protected and there is exactly one per node (FR-013): whichever attempt left
    a process behind, it is *this* node's worktree it is still writing to.
    """
    return Path(factory_root) / "run" / epic_id / f"{node_id}.pid"


def project_dir_name(cwd: Path | str) -> str:
    """Claude Code's per-cwd transcript directory: `/home/a/b` → `-home-a-b`.

    Every non-alphanumeric character of the absolute path becomes `-`. The rule
    belongs to the CLI, not to the factory, so the factory reproduces it to find
    the file it archives (R6) and the Tier 1 smoke is what proves the two still
    agree.
    """
    return _NON_ALNUM.sub("-", str(Path(cwd).resolve()))


# The environment (US2-S1) ----------------------------------------------------


def attempt_env(
    context: AttemptContext, environ: Mapping[str, str] | None = None
) -> dict[str, str]:
    """The agent's entire environment: two attempt values plus the passthrough.

    An allowlist, so `LITELLM_MASTER_KEY` and `TELEGRAM_BOT_TOKEN` are absent by
    omission rather than by redaction (constitution V) — as is every other
    variable the worker happens to carry, credential or not. `ANTHROPIC_AUTH_TOKEN`
    rather than `ANTHROPIC_API_KEY`: it is the bearer-token path the LiteLLM proxy
    expects (R6).
    """
    source = os.environ if environ is None else environ
    return {
        "ANTHROPIC_BASE_URL": context.proxy_url,
        "ANTHROPIC_AUTH_TOKEN": context.virtual_key,
    } | {name: source[name] for name in PASSTHROUGH_ENV if source.get(name)}


# The first adapter (R6) ------------------------------------------------------


class ClaudeCodeAdapter:
    """`claude -p --dangerously-skip-permissions --model <alias> --session-id <uuid>`.

    The prompt arrives on **stdin**: assembled prompts run to hundreds of
    kilobytes and argv has a limit. The model alias travels from the persona
    registry through argv untouched — this class names no model (constitution
    VII) — and the session id, generated by the workflow with `workflow.uuid4()`,
    is what makes the transcript discoverable afterwards, since Claude Code names
    the file after it.

    `executable` and `grace_s` are constructor arguments for the tests' benefit
    (a stub agent, and a grace short enough to observe): in production nothing
    configures them, and the deadline itself is always the persona registry's
    (FR-010).
    """

    name = "claude-code"

    def __init__(
        self,
        *,
        executable: str = DEFAULT_EXECUTABLE,
        grace_s: float = DEFAULT_GRACE_S,
    ) -> None:
        self.executable = executable
        self.grace_s = grace_s

    async def run_attempt(
        self,
        context: AttemptContext,
        *,
        factory_root: Path | str,
        heartbeat: Callable[[UsageSnapshot | None], Awaitable[None] | None] | None = None,
        heartbeat_interval_s: float = DEFAULT_HEARTBEAT_INTERVAL_S,
        read_usage: Callable[[], Awaitable[UsageSnapshot]] | None = None,
        poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    ) -> AdapterResult:
        """Run one attempt to its end, whatever that end is.

        Returns the termination class and the archive directory, and nothing else
        (D-018). Raises `asyncio.CancelledError` on the kill path *after* the
        group is dead and the evidence is archived, so Temporal records the
        cancellation and the workflow still salvages the worktree.
        """
        archive = transcript_dir(
            factory_root, context.epic_id, context.node_id, context.attempt
        )
        archive.mkdir(parents=True, exist_ok=True)
        pids = pid_file(factory_root, context.epic_id, context.node_id)
        await self._reap(pids)

        worktree = Path(context.worktree_path).resolve()
        env = attempt_env(context)

        with (archive / STDOUT_LOG_NAME).open("wb") as log:
            process = await self._launch(context, worktree=worktree, env=env, log=log)
            _write_pid_file(pids, process.pid)
            feeder = asyncio.ensure_future(_feed_prompt(process, context.prompt))
            try:
                termination, last_snapshot = await self._monitor(
                    process,
                    timeout_s=context.timeout_s,
                    heartbeat=heartbeat,
                    interval_s=heartbeat_interval_s,
                    read_usage=read_usage,
                    poll_interval_s=poll_interval_s,
                )
            except BaseException:
                # Cancellation (the workflow's kill) and any failure of the
                # monitor itself end identically: the process group dies and the
                # attempt keeps its evidence. Only the classification differs,
                # and on this path the workflow supplies it.
                await self._reclaim(process)
                self._archive_session(context, worktree, env, archive)
                _clear_pid_file(pids)
                raise
            finally:
                await _stop_feeding(feeder)

        self._archive_session(context, worktree, env, archive)
        _clear_pid_file(pids)
        return AdapterResult(
            termination=termination,
            transcript_path=str(archive),
            last_snapshot=last_snapshot,
        )

    # -- launch ---------------------------------------------------------------

    def argv(self, context: AttemptContext) -> list[str]:
        """The invocation, as the child receives it (R6)."""
        return [
            self.executable,
            "-p",
            "--dangerously-skip-permissions",
            "--model",
            context.model_alias,
            "--session-id",
            context.session_id,
        ]

    async def _launch(
        self,
        context: AttemptContext,
        *,
        worktree: Path,
        env: dict[str, str],
        log: Any,
    ) -> asyncio.subprocess.Process:
        """Spawn the agent in its own session, writing into the archived log.

        `start_new_session=True` is what makes the agent and everything it spawns
        one process group, so the deadline can be enforced against the tree
        rather than against the root of it. stderr is merged into stdout because
        the log is read by a human looking for what went wrong, in order.
        """
        try:
            return await asyncio.create_subprocess_exec(
                *self.argv(context),
                stdin=asyncio.subprocess.PIPE,
                stdout=log,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(worktree),
                env=env,
                start_new_session=True,
            )
        except OSError as error:
            raise AdapterError(
                f"could not launch agent '{self.executable}' for "
                f"{context.epic_id}/{context.node_id} attempt {context.attempt}: {error}"
            ) from error

    # -- monitor and terminate (R2) -------------------------------------------

    async def _monitor(
        self,
        process: asyncio.subprocess.Process,
        *,
        timeout_s: int,
        heartbeat: Callable[[UsageSnapshot | None], Awaitable[None] | None] | None,
        interval_s: float,
        read_usage: Callable[[], Awaitable[UsageSnapshot]] | None,
        poll_interval_s: float,
    ) -> tuple[Termination, UsageSnapshot | None]:
        """Wait for the agent, beating as it goes, and end it at its deadline.

        The wait is chopped into heartbeat-sized pieces rather than one long
        `wait_for`: the beat is what keeps the activity alive in Temporal's eyes
        and what lets a cancellation land within a beat instead of at the
        deadline.

        Observation rides the beat (plan US1): every `poll_interval_s` the proxy
        is read once for the attempt's spend so far, and the newest snapshot (or
        `None` before any reading succeeded) is carried as the beat's details. A
        read that raises leaves the previous snapshot in place and the beat still
        fires — liveness and spend share one channel, and spend must never be
        able to kill liveness (constitution V).
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        exited = asyncio.ensure_future(process.wait())

        snapshot: UsageSnapshot | None = None
        # The first read waits one full poll interval, so the first beat (one
        # heartbeat interval in) necessarily carries `None` — the attempt has
        # not been measured yet (constitution V: unknown, not zero).
        next_read = loop.time() + poll_interval_s

        try:
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                try:
                    await asyncio.wait_for(
                        asyncio.shield(exited), timeout=min(interval_s, remaining)
                    )
                except (asyncio.TimeoutError, TimeoutError):
                    now = loop.time()
                    if read_usage is not None and now >= next_read:
                        # A dead spend read must not kill liveness: keep the
                        # previous snapshot and let the beat fire anyway.
                        try:
                            snapshot = await read_usage()
                        except BaseException:
                            pass
                        next_read = now + poll_interval_s
                    if heartbeat is not None:
                        await _invoke_heartbeat(heartbeat, snapshot)
                    continue
                return (
                    (
                        Termination.COMPLETED
                        if process.returncode == 0
                        else Termination.AGENT_ERROR
                    ),
                    snapshot,
                )
        except BaseException:
            exited.cancel()
            raise

        await self._reclaim(process)
        return Termination.TIMEOUT, snapshot

    async def _reclaim(self, process: asyncio.subprocess.Process) -> None:
        """SIGTERM the agent's process group, then SIGKILL what survives.

        The KILL is sent even when the agent exited politely on TERM: its
        children share the group, outlive it, and go on writing into the node's
        worktree until they are gone (002's gate runner, same reasoning).
        """
        _signal_group(process.pid, signal.SIGTERM)
        with contextlib.suppress(asyncio.TimeoutError, TimeoutError):
            await asyncio.wait_for(process.wait(), timeout=self.grace_s)
        _signal_group(process.pid, signal.SIGKILL)
        await process.wait()

    # -- reap an orphan (R4) --------------------------------------------------

    async def _reap(self, pids: Path) -> None:
        """End the process group a previous run left behind, if it is still there.

        A precaution, not a gate: an unreadable, empty or nonsensical pid file is
        exactly what a worker killed mid-write leaves, and it must not cost the
        node its attempt. `0` is refused explicitly — `killpg(0, …)` means *this*
        process group, which is the worker's own.
        """
        pgid = _read_pgid(pids)
        if pgid is None or not _group_alive(pgid):
            return

        _signal_group(pgid, signal.SIGTERM)
        deadline = asyncio.get_running_loop().time() + self.grace_s
        while _group_alive(pgid) and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.05)
        _signal_group(pgid, signal.SIGKILL)

    # -- archive (FR-007) -----------------------------------------------------

    def _archive_session(
        self,
        context: AttemptContext,
        worktree: Path,
        env: Mapping[str, str],
        archive: Path,
    ) -> None:
        """Copy the agent's session transcript in beside `stdout.log`.

        A copy, not a move: the agent's own history stays where it put it. From
        the *child's* `HOME`, because that is the home the transcript was written
        under. An agent that wrote no transcript is not an error — the log is
        still evidence — and neither is a copy that fails: losing the archive
        step to an unwritable disk would cost a finished attempt its
        classification and buy a re-run of the agent.
        """
        home = env.get("HOME")
        if not home:
            return
        source = (
            Path(home)
            / ".claude"
            / "projects"
            / project_dir_name(worktree)
            / f"{context.session_id}.jsonl"
        )
        if not source.is_file():
            return
        with contextlib.suppress(OSError):
            shutil.copy2(source, archive / source.name)


_ADAPTERS: dict[str, type[Any]] = {ClaudeCodeAdapter.name: ClaudeCodeAdapter}


# stdin, pids, signals --------------------------------------------------------


async def _feed_prompt(process: asyncio.subprocess.Process, prompt: str) -> None:
    """Write the prompt and close the pipe — the close is what ends the agent's read.

    Its own task because a child that never drains stdin would otherwise block
    the launch itself, and the deadline exists precisely for agents that
    misbehave. A pipe that breaks first (an agent that exited early) is that
    agent's exit status to report, not an exception to raise over it.
    """
    stdin = process.stdin
    if stdin is None:  # pragma: no cover - stdin is always a pipe here
        return
    try:
        stdin.write(prompt.encode("utf-8"))
        await stdin.drain()
    except (BrokenPipeError, ConnectionResetError):
        pass
    finally:
        with contextlib.suppress(BrokenPipeError, ConnectionResetError, OSError):
            stdin.close()


async def _stop_feeding(feeder: asyncio.Future[None]) -> None:
    """Let the writer finish, or cancel it if the agent is already gone."""
    feeder.cancel()
    with contextlib.suppress(asyncio.CancelledError, BrokenPipeError, OSError):
        await feeder


def _write_pid_file(pids: Path, pgid: int) -> None:
    """Record this attempt's process group, for whoever runs next (R4).

    The child is a session leader (`start_new_session`), so its pid *is* its
    group id — and the group is what has to die, since the agent's children are
    the half that outlives it.
    """
    pids.parent.mkdir(parents=True, exist_ok=True)
    pids.write_text(f"{pgid}\n", encoding="utf-8")


def _clear_pid_file(pids: Path) -> None:
    """Drop the file on the way out: a stale pid is a reap of somebody else."""
    with contextlib.suppress(OSError):
        pids.unlink(missing_ok=True)


def _read_pgid(pids: Path) -> int | None:
    """The process group a previous run recorded, or None if there is not a usable one."""
    try:
        recorded = int(pids.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    if recorded <= 0 or recorded == os.getpgid(0):
        return None
    return recorded


def _group_alive(pgid: int) -> bool:
    """Whether signal 0 still finds the group (a zombie counts — it exists)."""
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _signal_group(pgid: int, sig: int) -> None:
    """Signal a whole process group, tolerating one that has already gone.

    An empty group is the expected outcome of the second signal, not an error.
    """
    if pgid <= 0:
        return
    with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
        os.killpg(pgid, sig)
