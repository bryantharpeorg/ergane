# 104-US4 — the consent step loads the profile (seam capture)

**This is a seam capture, not a session at a terminal.** `apparmor_parser` was
never executed, no `sudo` was invoked, no kernel policy was touched, no Docker
daemon was contacted and no container was started. Every block below is the
pasted output of `container_profile.load_profile(...)` and
`container_project.render_compose(...)` driven through injected seams:

| Seam | What it was driven with |
| --- | --- |
| the prompter (`prompter.ask`) | one scripted answer per capture, echoed after the prompt — which is why this reads like a terminal session and is not one |
| the printer (`emit=`) | a list, shared with the prompter, so *ordering* between output and prompt is a recorded fact rather than two separate captures guessed at |
| the privileged runner (`run=`) | a recorder returning a scripted `PrivilegedResult`. It **records** the argv and the text of the file that argv names; it runs nothing |
| the host | a scratch `/tmp/seam-capture` pointed at by `HOME`, `ERGANE_STATE_HOME` and `XDG_CONFIG_HOME`, with a one-repo fixture `repos.json` |

The agent sandbox binds no Docker socket and trap 11 forbids a real
`apparmor_parser`, so a plausible-looking real transcript would be
indistinguishable from a fabricated one. The real runs are the operator's, in
the plan's last section. The same properties are asserted mechanically in
`tests/test_container_profile.py`; this file is what they look like.

## Consent — the text, then the prompt, then the load

The profile is read through US2's package-data resolver (R10), so this is what
an operator sees from a wheel install too. Shown **before** the prompt, verbatim
and whole; the middle of it is elided here at the marked line and nowhere in the
program.

```text
the engine container runs under the AppArmor profile `ergane-engine`, which must be loaded into the kernel once. This is the only privileged step of the install; the whole profile is below.

# Base: docker-default AppArmor profile from moby v28.3.3
# Source: https://github.com/moby/moby/blob/v28.3.3/profiles/apparmor/default.c
# Deltas from docker-default:
#   - abi <abi/4.0> for userns mediation
#   - allow userns, mount, pivot_root for bubblewrap namespace setup
#   - every docker-default deny line retained

abi <abi/4.0>,
#include <tunables/global>

profile ergane-engine flags=(attach_disconnected,mediate_deleted) {
  #include <abstractions/base>

  network,
  capability,
  file,
  umount,

  # Deltas from docker-default: bwrap's namespace setup
  userns,
  mount,
  pivot_root,

  [… the signal, deny @{PROC}, deny /sys and ptrace rules, elided here only …]

  ptrace (trace,read,tracedby,readby) peer=ergane-engine,
}

load the AppArmor profile `ergane-engine` into the kernel with sudo? (Y/n) [y]: y
loaded AppArmor profile `ergane-engine`
```

The default is `y`, which inverts `factory/cli/init.py:268`, this repository's
only other consent grammar. That is trap 7 and the operator's explicit approval,
not an oversight: declining does not avoid the privileged act on a fresh host,
so a default-no produces a config-F engine nobody chose.

What the privileged seam **recorded**, and what it would have run:

```text
argv    = ['sudo', 'apparmor_parser', '-r', '/tmp/ergane-apparmor-x044wu8h/ergane-engine.profile']
file[1325 bytes] == profile_text(): True
decision = ProfileDecision(confinement='profile', attempted=True, failure='', statement=('confinement: config G, `apparmor=ergane-engine`.',))
```

The file the argv names holds the bytes that were displayed — written from the
same string, not read from the artifact a second time. The operator consents to
text, and that text is what the parser is handed.

The project rendered from that decision:

```yaml
    security_opt:
      - no-new-privileges:true
      - seccomp:./seccomp-ergane.json
      - apparmor=ergane-engine
```

```text
'unconfined' in the rendered compose: False
```

## Decline — nothing privileged, and an honestly annotated F engine

```text
load the AppArmor profile `ergane-engine` into the kernel with sudo? (Y/n) [y]: n
declined: nothing was run under sudo and no kernel policy was touched.
  [… the statement below, printed from the same constant, elided here only …]
```

```text
recorded privileged calls: []
decision.attempted = False
decision.confinement = 'unconfined'
decision.failure = ''
```

**Empty, on the seam.** "No privileged command was attempted" is asserted on
what the runner recorded, not on the sentence the installer printed — an
installer that merely *says* nothing happened is the failure that criterion
exists to rule out.

The generated `compose.yaml` says the same thing to the operator who reads the
file next month rather than the terminal today, because comments are data (R4)
and this text is one constant reaching both:

```yaml
    cap_drop: [ALL]
    # Confinement: config F -- `apparmor=unconfined`, which is NOT the shipped
    # configuration. The shipped one is config G, `apparmor=ergane-engine`:
    # the named profile in ergane-engine.profile beside this file. It was not loaded
    # into the kernel, so this project asks Docker for no AppArmor profile at all.
    # seccomp and no-new-privileges are identical in both variants; AppArmor is the
    # whole of the difference.
    #
    # This is a completely generated, honestly annotated engine, and these are its
    # remaining prerequisites -- config F is not the privilege-free option, it is
    # the other one:
    #
    #   1. A /etc/apparmor.d/bwrap stub must already be loaded on this host. It is
    #      not stock Ubuntu 24.04 and no package owns it -- it is hand-installed
    #      on the reference floor. Without it bwrap fails at `write failed
    #      /proc/self/uid_map: Operation not permitted` with no obvious cause
    #      (measured: docs/container-onramp-research-findings.md section 8, item
    #      3).
    #   2. To reach config G instead, load the profile from this directory and
    #      re-run install:  sudo apparmor_parser -r ./ergane-engine.profile
    #      then `ergane install`.
    #
    # Do not read this as "AppArmor is off". On Ubuntu 23.10 and later, removing
    # the profile activates the kernel's capability-stripping unprivileged_userns
    # transition: the namespace is created and the uid_map write is then refused.
    # Turning AppArmor off to debug this makes it worse, always (findings section
    # 8, item 4).
    security_opt:
      - no-new-privileges:true
      - seccomp:./seccomp-ergane.json
      - apparmor=unconfined
```

And it is a **complete** project, not a degraded one — four files, the same four
G generates:

```text
compose.yaml             0o644    3805 bytes
.env                     0o600     641 bytes
seccomp-ergane.json      0o644   16299 bytes
ergane-engine.profile    0o644    1325 bytes
```

The profile is copied in either way: under F it is what the operator loads to
reach G later, which is the command annotation 2 names.

## A refusing `apparmor_parser` — verbatim, then the same fallback

The runner was scripted to `PrivilegedResult(1, "", <stderr>)`. The stderr is a
stub written for this capture; no parser produced it.

```text
load the AppArmor profile `ergane-engine` into the kernel with sudo? (Y/n) [y]: y
`sudo apparmor_parser -r /tmp/ergane-apparmor-ynli2q5p/ergane-engine.profile` exited 1; it said:

AppArmor parser error for /tmp/ergane-apparmor-8fq2p1/ergane-engine.profile in profile /tmp/ergane-apparmor-8fq2p1/ergane-engine.profile at line 8: Could not open 'abi/4.0'
AppArmor parser error: syntax error, unexpected TOK_ID

falling back to the same configuration a decline produces:
  [… the identical statement, elided here only …]
```

Verbatim means unreflowed and unprefixed: the operator has to be able to paste
it into a search box. The stub's own stale temp path is reproduced exactly as
given, which is the point — the installer does not tidy the parser's words.

```text
decision.failure == the stubbed stderr, byte for byte: True
decision.statement == the declined decision's statement: True
decision.confinement = 'unconfined'   decision.attempted = True
render_compose(F after failure) == render_compose(F after decline): True
project_dir() exists on disk: False   (/tmp/seam-capture/state/ergane/supervision/container)
```

**Never a half-configured project.** The last two lines are the whole argument:
the failure changes the confinement variant and nothing else, so what results is
the same complete F project a decline produces — and nothing partial survives
because nothing was written. The consent step decides; US3's writer writes.

## The reference is untouched (trap 9)

Config F is reachable only through `resolve_project(confinement=...)`.
`reference_project()` still takes no parameters, so the committed reference
cannot go red on a changed default in a file nobody edited.

```text
STRUCT   True   (yaml.safe_load of both sides compares equal)
COMMENTS True   (17 comment lines, ordered, equal after stripping)
'unconfined' in render_compose(reference_project()): False
inspect.signature(reference_project).parameters: {}
```

```text
$ uv run pytest tests/test_container_profile.py tests/test_container_project.py tests/test_088_us3_container_drift.py
tests/test_container_profile.py ............................             [ 38%]
tests/test_container_project.py ............................             [ 76%]
tests/test_088_us3_container_drift.py .................                  [100%]

============================== 73 passed in 1.39s ==============================
```
