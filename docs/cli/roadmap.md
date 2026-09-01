# `ergane roadmap`

> run and steer the roadmap scheduler

The roadmap watches a specs corpus and dispatches epics itself. It is the
difference between a factory you drive and a factory that runs.

```
ergane roadmap start   <specs-root> --target-repo PATH [dials]
ergane roadmap status  <specs-root> [--json]
ergane roadmap pause   <specs-root>
ergane roadmap resume  <specs-root>
ergane roadmap promote <specs-root> --spec DIR
ergane roadmap unpark  <specs-root> --spec DIR
```

Every verb takes the specs root as its positional argument, because that is what
identifies the roadmap — one roadmap per corpus.

---

## `ergane roadmap start`

| argument | default | meaning |
| --- | --- | --- |
| `<specs_root>` | — | path to the specs corpus |
| `--target-repo` | **required** | worker-host path to the target repo clone |
| `--proxy-url` | `$LITELLM_PROXY_URL`, else the control-plane config | proxy URL for child epic keys |
| `--max-concurrent-epics` | `1` | concurrent child epics |
| `--max-concurrent-nodes` | `1` | ready nodes per child epic |
| `--poll-interval-s` | `30` | child-poll interval in seconds |
| `--idle-rescan-s` | — | idle rescan interval; **omit to drain and exit** |

Plus the landing dials shared with [`build start`](build.md):
`--promotion-persona`, `--merge-method`, `--landing-poll-interval-s`,
`--stall-after-s`, `--max-recovery-cycles`, `--max-free-rebases`,
`--halt-after-pass`.

**`--idle-rescan-s` decides whether this is a drain or a daemon.** Omitted, the
roadmap dispatches what is ready, waits for it, and exits. Given, it keeps
rescanning at that interval and stays up.

The two concurrency dials multiply. `--max-concurrent-epics 2` with
`--max-concurrent-nodes 2` is four agents, not two.

---

## `ergane roadmap status`

The roadmap's disposition: whether the schedule is running, which run is
current, when the next tick fires, whether dispatch is running or paused, what
is running, and what is parked.

**A degraded surface worth knowing about:** this verb resolves the newest
roadmap run for the corpus regardless of whether that run failed, so one failed
run can break the answer until it ages out of the retention window. When it
reports something implausible, check Temporal's Web UI before believing it.

`--json` prints the query result verbatim.

---

## `ergane roadmap pause` / `resume`

Stop and start dispatch. Paused, the schedule still ticks and the roadmap still
observes; it just does not start anything new. Epics already running are
unaffected.

Whether a pause is deliberate is not something the tool can tell you. When you
find dispatch paused and do not know why, find out before resuming — that is a
decision someone made.

---

## `ergane roadmap promote <specs-root> --spec DIR`

Move one spec to the front of what the roadmap will take next.

---

## `ergane roadmap unpark <specs-root> --spec DIR`

Release a spec the roadmap parked.

A **park** is the roadmap declining to dispatch something it otherwise could,
and it always has a reason — the commonest is that the spec is not visible in
the tree the roadmap derives its delta from. `ergane status specs` reports the
parked count; `roadmap status` names them.

---

## Two behaviours that surprise operators

**A ready spec is not inert just because it has not been promoted.** The roadmap
dispatches ready specs on its own, with its own dials. Marking a spec `ready`
while a roadmap is running is a dispatch decision, not a bookkeeping one — and a
manual `ergane build start` on the same spec will collide with it.

**Readiness and the delta are read from two different trees.** The roadmap reads
a spec's readiness from the corpus you point it at, and derives the *remaining
work* from the committed state of the target repo clone. A spec edited but not
committed can therefore be seen as ready and still have nothing to dispatch.
When a spec parks for no visible reason, check whether its edits are committed
and pushed.

## See also

- [`ergane status`](status.md) — the roadmap's disposition alongside everything else
- [`ergane build`](build.md) — the dials, and how to steer an epic the roadmap started
- [`ergane spec`](spec.md) — what makes a spec ready in the first place
