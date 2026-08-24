# 104-US1 — the interview asks where the engine runs (seam capture)

**This is a seam capture, not a real run. No Docker daemon was contacted, no
container was started and no `apparmor_parser` ran.** Every line below is the
pasted output of `factory.cli.main.main(...)` driven through injected seams, on
a host that has no Docker at all:

| Seam | What it was driven with |
| --- | --- |
| `factory.cli.install._docker_daemon_available` | rebound to a constant — "a daemon answers" or "none does". Nothing was probed. |
| `shutil.which` | answers from a table (`docker` / `docker-compose` present or absent), so what the refusal says is a function of the *stated* host and not of this one. |
| `factory.cli.init._prompter_factory` | one scripted prompter for the whole run; the answers are echoed after each prompt, which is why this reads like a terminal session and is not one. |
| `factory.cli.install._interview_personas` | stubbed to a no-op — 103's step reaches a real gateway and is proven in its own file. |
| `factory.cli.install._llm_scan` | stubbed to `None`, so the capture does not depend on what happens to be listening on loopback here. |

Scratch paths are elided to `/tmp/…`; nothing else is edited. The closing verify
battery probes four deliberately closed ports and is elided to its header line; it is 033's behaviour, unchanged by this story, and `EXIT=1`
throughout is that battery failing rather than anything about the engine.

The same properties are asserted mechanically in
`tests/test_install_engine_question.py`; this file is what they look like.

## A daemon answers: `container` is offered first

```text
$ ergane install
llm mode (gateway) [gateway]: gateway
llm gateway base_url [http://127.0.0.1:4000]: http://127.0.0.1:1/v1
llm gateway master key env-var name [ERGANE_LLM_MASTER_KEY]: ERGANE_LLM_MASTER_KEY
memory backend (hindsight|none) [none]: none
temporal mode (external|managed) [external]: external
temporal address [127.0.0.1:7233]: 127.0.0.1:4
temporal namespace [ergane]: ergane
temporal api key env-var name (optional): -
temporal TLS enabled (true|false) [false]: false
telemetry OTLP endpoint (optional):
escalation adapter (telegram|none) [telegram]: none
engine backend (container|systemd|none) [container]: container
engine backend: container
wrote /tmp/…/config.toml
wrote /tmp/…/xdg/ergane/personas.yaml

verifying the control plane...
[… five verify findings, elided …]
EXIT=1
```

`engine backend: container` is the line US5 replaces with generation, consent,
bring-up and verify-through. US1 asks; it does not act.

## The answer is checked, because the parser never sees it

The engine backend is not a control-plane field — the record is the generated
project on disk (plan R1) — so `_ask`'s refuse-and-re-ask loop, which is driven
by `parse_controlplane_config`, has nothing to judge it with. A typo may not
fall through as "not container" and quietly configure only:

```text
engine backend (container|systemd|none) [container]: contianer
  `contianer` is not an engine backend; choose container|systemd|none
engine backend (container|systemd|none) [container]: systemd
wrote /tmp/…/config.toml
```

No `engine backend:` line: only `container` announces itself, and `systemd`
is today's path.

## No daemon: today's interview, unchanged

```text
$ ergane install
llm mode (gateway) [gateway]: gateway
llm gateway base_url [http://127.0.0.1:4000]: http://127.0.0.1:1/v1
llm gateway master key env-var name [ERGANE_LLM_MASTER_KEY]: ERGANE_LLM_MASTER_KEY
memory backend (hindsight|none) [none]: none
temporal mode (external|managed) [external]: external
temporal address [127.0.0.1:7233]: 127.0.0.1:4
temporal namespace [ergane]: ergane
temporal api key env-var name (optional): -
temporal TLS enabled (true|false) [false]: false
telemetry OTLP endpoint (optional):
escalation adapter (telegram|none) [telegram]: none
wrote /tmp/…/config.toml
left existing /tmp/…/xdg/ergane/personas.yaml

verifying the control plane...
[… five verify findings, elided …]
EXIT=1
```

Eleven questions, the same eleven as before this story: the engine container
cannot run here, so install asks nothing about it and behaves exactly as it
does today. That is also what makes US1-S3's "their existing tests pass
unmodified" true on *every* host rather than only on hosts without Docker — the
suite's answer lists do not grow or shrink depending on whether the developer
started Docker this morning. An operator who wants the container here says so
with `--engine`, and lands on the refusal below: it is the same guard, reached
without being asked rather than around it.

## Choosing `container` where no daemon answers

The interview runs identically in all three; only the last line differs, so the
eleven questions above are elided here to the answer that provoked the refusal.
Nothing was written — the refusal fires before `wrote …`, the way `_ask_temporal`
refuses managed mode.

```text
$ ergane install --engine container      # seam: nothing on PATH
[… the eleven interview questions above, identically …]
ergane: engine backend "container" requires a reachable Docker daemon; `docker` is not on PATH. Install Docker Engine together with its Compose v2 plugin (https://docs.docker.com/engine/install/), which is what brings the engine container up (`docker compose`, two words). Choose `systemd` or `none`, or fix Docker and re-run `ergane install`.
EXIT=1

$ ergane install --engine container      # seam: only the legacy binary on PATH
[… the eleven interview questions above, identically …]
ergane: engine backend "container" requires a reachable Docker daemon; the legacy `docker-compose` binary is present (/usr/local/bin/docker-compose) but `docker compose` (v2, two words) is not, and Compose v1 cannot bring the engine container up. Install Docker Engine and the `docker-compose-plugin` package (https://docs.docker.com/engine/install/). Choose `systemd` or `none`, or fix Docker and re-run `ergane install`.
EXIT=1

$ ergane install --engine container      # seam: docker on PATH, daemon silent
[… the eleven interview questions above, identically …]
ergane: engine backend "container" requires a reachable Docker daemon; `docker` is at /usr/bin/docker but `docker info` did not answer, so the daemon is either not running or not reachable from this account. Start it (`sudo systemctl start docker`) and give your user the socket (`sudo usermod -aG docker $USER`, then log in again). Choose `systemd` or `none`, or fix Docker and re-run `ergane install`.
EXIT=1
```

Three hosts, three different fixes. The middle one is the spec's Assumptions
made operational: `docker-compose` (v1, hyphenated) and `docker compose` (v2, a
subcommand of the daemon's own CLI) are different programs, and an operator who
has the first and is told "Docker is not installed" will reasonably conclude the
installer is wrong.

## `--non-interactive` and `--from-file` configure only

```text
$ ergane install --non-interactive       # seam: a daemon answers, and is never asked about
applied default: temporal.tls_enabled = false
wrote /tmp/…/config.toml
left existing /tmp/…/xdg/ergane/personas.yaml

verifying the control plane...
[… five verify findings, elided …]
EXIT=1
```

Driven with the daemon stubbed **present**, which is the only setting that could
fail: a step that asked would ask here. It does not, because both flag-driven
paths return from `install_command` before the engine step, and their backend is
declared (`DEFAULT_ENGINE_BACKEND = "none"`) rather than asked.

Which is also why `--engine` beside either of them is refused by name instead of
silently discarded:

```text
$ ergane install --engine container --non-interactive
ergane: --engine=container cannot be combined with --non-interactive: that path configures only and returns before any engine step could run, so its backend is always `none`. Drop --engine, or run the interview without --non-interactive.
EXIT=1

$ ergane install --engine container --from-file answers.toml
ergane: --engine=container cannot be combined with --from-file: that path configures only and returns before any engine step could run, so its backend is always `none`. Drop --engine, or run the interview without --from-file.
EXIT=1
```

## The five modules that reach `GATEWAY_ANSWERS`, green and unmodified

Plan trap 1: `tests/test_ergane_install_walkthrough.py` defines that answer list
and indexes it by literal position; `tests/test_install_mode_routing.py`,
`tests/test_direct_mode_refused.py` and `tests/test_controlplane_direct_mode.py`
import the very same object; `tests/test_us2_shipped_registry.py` duplicates it
wholesale. Staying outside `_interview` is what keeps all five true.

```text
$ uv run pytest tests/test_ergane_install_walkthrough.py \
      tests/test_install_mode_routing.py tests/test_direct_mode_refused.py \
      tests/test_controlplane_direct_mode.py tests/test_us2_shipped_registry.py -q
50 passed, 1 warning in 6.31s
```

Unmodified is the stronger half of that claim, and it is a fact about the diff
rather than about the run — none of the five appears in it. This is the story's
code, taken before this file was added to it:

```text
$ git diff --stat
 factory/cli/install.py                | 320 +++++++++++++++++++++
 factory/cli/nouns/install.py          |  16 +-
 tests/conftest.py                     |  25 ++
 tests/test_install_engine_question.py | 521 ++++++++++++++++++++++++++++++++++
 4 files changed, 881 insertions(+), 1 deletion(-)
```

`tests/conftest.py` is the one shared file this story touches: it pins the Docker
predicate to "absent" for the whole suite, the way 088-US4 pinned the systemd
predicate beside it. No test contacts a daemon (plan trap 11), and a developer
with Docker running sees the same suite the gate does.

## The whole suite

```text
$ uv run pytest -q
4619 passed, 52 skipped, 7 warnings in 352.66s (0:05:52)
```
