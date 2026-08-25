# 104-US5 — bring-up, readiness and verify-through: a seam capture

**This is a seam capture, not a run against a daemon.** Every transcript below
is the output of the code under test driven through injected seams — the
**compose runner** (`container_engine._run_compose`), the **port probe**
(`container_engine._probe_address`) and the **clock** (`now`/`sleep`). No Docker
daemon exists in this environment and none was contacted: the agent sandbox
binds no `/var/run/docker.sock`, trap 11 forbids starting a real daemon,
container or `apparmor_parser`, and R10 says the local build needs a checkout a
wheel does not carry. **The verify output the "engine" prints below is the
capture script's fixture string, not a real engine's** — which is also R8's
point: what is under test is that install takes the child's *exit code* as the
verdict and never reads its words.

The real runs against a real daemon are the operator's, in the last section of
this spec's `plan.md`; no gate waits on them. Paths are elided to `…/container`;
the capture ran under a scratch `ERGANE_STATE_HOME`, off `~` (trap 5). The
readiness-timeout path is asserted in
`test_a_readiness_timeout_names_the_address_and_the_timeout` rather than
reproduced here.

## 1. Bring-up ending in a passing verify-through (US5-S1)

Written, brought up detached, waited on — bounded, on the address its own
published port makes reachable — then verified *inside* the engine. The port was
silent at the preflight, so there was nothing to collide with and `ps` was never
asked.

```text
wrote 4 file(s) to …/container
  wrote: compose.yaml
  wrote: .env
  wrote: seccomp-ergane.json
  wrote: ergane-engine.profile
bringing the engine container up from …/container/compose.yaml...
waiting up to 180s for the engine to answer on 127.0.0.1:7233...

verifying the control plane inside the engine container (`ergane`), which is where the factory will actually run:
[PASS] llm: gateway at http://127.0.0.1:4000 answered in 41ms
[PASS] temporal: ergane namespace reachable at 127.0.0.1:7233
[PASS] memory: skipped by declaration: memory.backend is `none`

  the engine container is up and verified.
  runner calls, in order:
    $ docker compose -f …/container/compose.yaml up -d
    $ docker compose -f …/container/compose.yaml exec -T ergane ergane install --verify
```

## 2. A failing verify leaves the engine up and names a remedy (US5-S2)

The findings reach the operator first, then the refusal. The recorded runner
calls are the whole of the claim: `ps`, `up`, `exec`, and **no `down`, `stop`,
`rm` or `kill`**.

```text
bringing the engine container up from …/container/compose.yaml...
waiting up to 180s for the engine to answer on 127.0.0.1:7233...

verifying the control plane inside the engine container (`ergane`), which is where the factory will actually run:
[PASS] llm: gateway at http://127.0.0.1:4000 answered in 41ms
[FAIL] temporal: Temporal at 127.0.0.1:7233 did not answer: ConnectionRefused

  ergane: the engine container came up, and its own verify reported failures. It is still running, deliberately, so they can be reproduced against it — nothing was stopped or removed.
  remedy: the findings above name what did not answer; re-run `ergane install` to change the answers behind them (it converges), or `docker compose -f …/container/compose.yaml logs ergane` for what the engine said. `ergane uninstall` takes it down when you are done.
  exit=1
  runner calls, in order:
    $ docker compose -f …/container/compose.yaml ps --services --status running
    $ docker compose -f …/container/compose.yaml up -d
    $ docker compose -f …/container/compose.yaml exec -T ergane ergane install --verify
  teardown verbs recorded: []
```

## 3. Idempotent re-entry against a half-up stack (US5-S3)

Project on disk, service running, port answering. The render is a function of
the confirmed answers, so every digest matches and the writer touches nothing;
the preflight recognises our own service and lets `up` through.

```text
engine container project at …/container is already current
  unchanged: compose.yaml
  unchanged: .env
  unchanged: seccomp-ergane.json
  unchanged: ergane-engine.profile
<the bring-up and verify blocks here are byte-identical to §1's; elided>

  runner calls, in order:
    $ docker compose -f …/container/compose.yaml ps --services --status running
    $ docker compose -f …/container/compose.yaml up -d
    $ docker compose -f …/container/compose.yaml exec -T ergane ergane install --verify
```

## 4. The published-port preflight refuses a collision (trap 6)

Something answers, and `docker compose ps` says it is not this project's service
— on the reference floor, the native managed Temporal. Refused before `up`: `ps`
is the only command run.

```text
  ergane: something is already listening on 127.0.0.1:7233, and `docker compose ps` reports this project's `ergane` service is not running — so that port belongs to something else, most likely this host's own native Temporal tier. Publishing onto it would leave the host CLI on one Temporal and the engine on another, both looking healthy.
  remedies, either one: drain the native tier (stop its managed Temporal unit, or `ergane worker uninstall`); or set `temporal.address` to a free port, which is safe because the engine keeps its own Temporal database. Then re-run `ergane install`.
  exit=1
  runner calls, in order:
    $ docker compose -f …/container/compose.yaml ps --services --status running
```

## 5. R12 — one address convention, `host:port`, on both sides (US5-S4)

The generated `.env` names the engine's **own loopback** in the tree-wide
spelling, never the host's published port; the supervisor then resolves both
spellings to one endpoint and splits it once. As 088 landed, `_run_supervisor`
appended a port unconditionally, so this same `.env` value would have produced
`127.0.0.1:7233:7233`, the probe would have dialled host `127.0.0.1:7233`,
readiness would have timed out and the engine would never have come up.

```text
  generated .env  TEMPORAL_ADDRESS=127.0.0.1:7233
  published port  ('127.0.0.1:7233:7233',)
  host dials      127.0.0.1:7233
  supervisor:   '127.0.0.1:7233' -> '127.0.0.1:7233'  split -> ('127.0.0.1', 7233)
  supervisor:        '127.0.0.1' -> '127.0.0.1:7233'  split -> ('127.0.0.1', 7233)
  supervisor:   'localhost:7233' -> 'localhost:7233'  split -> ('localhost', 7233)
```

Both spellings resolve, deliberately: `factory.worker` and
`factory.notify.service` read the same `TEMPORAL_ADDRESS` out of the same
environment and need the port in it. Two consumers, one variable, one meaning.
