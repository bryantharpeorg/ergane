# US1 evidence: the `env -i` reproduction, re-run against the built wheel (SC-001)

The finding this spec was drafted from was not reasoned into existence — it was
produced by walking the portability path as a new user would. SC-001 asks for
that same walk, against the wheel built from this branch, and for the transcript
to be committed: the judge is given this diff and the criteria, never a terminal
(constitution VIII / D-037).

Everything below is pasted verbatim, under one stated substitution: `$S` stands
for the scratch root

```
/tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-050-us1/us1-repro
```

and nothing else is elided. The one line the whole document exists for — the
schedule step's report — is left with its paths in full, because a *scratch
temporary directory that no longer exists* is exactly what the orphaned schedule
pointed at, and seeing that is part of reading it.

## Setup: the shipped wheel, a clean venv, a fresh repository

```
$ uv build --wheel --out-dir $S/dist
Building wheel...
Successfully built .../scratch-050-us1/us1-repro/dist/ergane-0.1.0-py3-none-any.whl
build rc=0

$ python3 -m venv $S/venv && $S/venv/bin/pip install --quiet $S/dist/ergane-0.1.0-py3-none-any.whl
install rc=0

$ cd $S/portab/repo && git init -b main --quiet && git commit -q -m init
acedaea init
```

**One false reading, recorded rather than hidden.** The first attempt at the
pre-check below was run from the operator's own checkout as its working
directory, and `python -c` puts the working directory at the front of
`sys.path`. It imported `/home/admin/code/ergane/factory/cli/init.py` — the
*source tree*, not the wheel — and failed with `ImportError: cannot import name
'_control_plane_reason'`, which is what the wheel would look like if the fix
were missing from it. Every command below therefore runs from
`$S/portab/repo` and the first line printed is `factory.__file__`, so the
transcript states which copy of the code produced it instead of assuming.

## The precondition, evaluated under the reproduction's exact environment

Run before `ergane init`, so this proves the refusal fires without any schedule
lifecycle running at all:

```
$ cd $S/portab/repo && env -i HOME=$S/home PATH=/usr/bin:/bin:$S/venv/bin \
    $S/venv/bin/python -c '<print factory.__file__, the config path, the reason, the target>'

factory from: $S/venv/lib/python3.12/site-packages/factory/__init__.py
config path : $S/home/.config/ergane/config.toml
exists      : False
reason      : ControlPlaneConfigError: $S/home/.config/ergane/config.toml: [config_missing] cannot be read (No such file or directory); run `ergane install` to create the control-plane config
would reach : Temporal at localhost:7233 in namespace 'factory' (built-in default)
rc=0
```

Read the last line as the point of plan trap 9 made concrete. `env -i` declared
nothing, and the resolution still lands on this host's **live** namespace,
chosen by the built-in default. That is how `ergane-roadmap-repo` came to exist
on a namespace the operator had never named, and it is why the refusal says
which namespace and which source rather than only that it refused. FR-001 stops
this machine because nothing is readable; it would *not* stop a machine whose
config reads fine and whose fallback still picks a namespace nobody declared —
that is 051's two literals, deliberately not widened into here.

## The reproduction itself

`< /dev/null` is "accept every interview default": the terminal prompter reads
`EOFError` as an empty answer and takes the default, which is what the original
run did. The slug defaults to the directory name, `repo` — precisely the name a
scratch clone or a tutorial checkout gets.

```
$ temporal schedule list --namespace factory        # BEFORE
    ScheduleId                Action              Paused  NextRunTime  LastRunTime
  ergane-roadmap  {"Workflow":"RoadmapWorkflow"}  true    1 day ago    1 day ago
rc=0

$ cd $S/portab/repo && env -i HOME=$S/home PATH=/usr/bin:/bin:$S/venv/bin \
    $S/venv/bin/ergane init . < /dev/null
ergane init exit code: 0
```

The exit code was captured into `rc=$?` before anything was piped anywhere. A
`cmd | head; echo $?` reports the *pipe's* status, which produced a false
reading on this host earlier the same day and nearly became a filed finding.

stdout, verbatim (the interview's prompts run together on one line because
nothing echoed a newline into a redirected stdin):

```
schema version [1]: runtime backend [bwrap]: gates (YAML mapping of gate name to command) [test: 'true']: timeouts in seconds (YAML mapping of gate name to seconds, optional) []: standards document path (optional) []: landing branch [main]: roadmap dials (YAML mapping of cadence_s, max_concurrent_epics, max_concurrent_nodes, optional) []: forge this repository is on (optional) []: repo slug [repo]: joined $S/portab/repo as slug 'repo'
written:
  $S/portab/repo/ergane.yaml
  $S/portab/repo/.gitignore
  $S/portab/repo/.ergane
registered: 'repo' -> $S/portab/repo
schedule: failed ergane-roadmap-repo — refused: the control plane could not be read, so no schedule was created — ControlPlaneConfigError: /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-050-us1/us1-repro/home/.config/ergane/config.toml: [config_missing] cannot be read (No such file or directory); run `ergane install` to create the control-plane config — and `ergane install` is what creates it; a schedule for this repository would otherwise have gone to Temporal at localhost:7233 in namespace 'factory' (built-in default)
github wiring: not attempted — re-run with `ergane init --wire` to
  queue the landing branch and require one check per declared gate
next, run:
  git -C .../portab/repo add ergane.yaml .gitignore .ergane
  git -C .../portab/repo commit -m "join ergane"

ergane readiness for .../portab/repo (ergane.yaml)
  [FAIL] repo_read: could not read the repo via its forge (GH_REFUSED): To get started with GitHub CLI, please run:  gh auth login
Alternatively, populate the GH_TOKEN environment variable with a GitHub API authentication token.

  [PASS] runtime_root_ignored: .ergane/ is ignored by git
  [PASS] registry_entry: registered as 'repo' in .../home/.local/state/ergane/repos.json
  [PASS] landing_branch: landing branch 'main' exists
  [FAIL] control_plane: the control plane could not be probed: ControlPlaneConfigError: .../home/.config/ergane/config.toml: [config_missing] cannot be read (No such file or directory); run `ergane install` to create the control-plane config — `ergane install --verify` reports each subsystem separately
  [FAIL] roadmap_schedule: no roadmap schedule 'ergane-roadmap-repo' exists on the control plane, so no tick will ever dispatch .../portab/repo's specs — run `ergane init .../portab/repo` to create it; flipping a spec to `ready` without one does nothing, with no error
3 of 6 checks failed
```

stderr was empty.

Compare the schedule line against the one this spec's Context recorded:

```
before   schedule: created ergane-roadmap-repo — created, starting roadmap-specs every 300s over /tmp/.../portab/repo/specs (note: LITELLM_PROXY_URL is unset, so child epics cannot issue keys)
after    schedule: failed  ergane-roadmap-repo — refused: the control plane could not be read, so no schedule was created — ControlPlaneConfigError: … ; run `ergane install` … — and `ergane install` is what creates it; a schedule for this repository would otherwise have gone to Temporal at localhost:7233 in namespace 'factory' (built-in default)
```

## The claim that matters, checked against the world

Not "the command said it refused" — that is a claim about the report. This is
the schedule list on the operator's live namespace, read before and after:

```
$ temporal schedule list --namespace factory        # AFTER
    ScheduleId                Action              Paused  NextRunTime  LastRunTime
  ergane-roadmap  {"Workflow":"RoadmapWorkflow"}  true    1 day ago    1 day ago
rc=0

$ diff before.txt after.txt
diff rc=0 (0 = identical)

$ temporal schedule describe --schedule-id ergane-roadmap-repo --namespace factory
Error: schedule not found
describe rc=1
```

One schedule, the operator's, still paused. The identifier the incident created
does not exist.

## FR-004: the repository-scoped half is untouched

Everything local still happened, which is the whole point of the split between
acts that are local and reversible and acts that publish to shared
infrastructure. Being able to join a repository before standing up a control
plane is a real workflow, and this preserves it:

```
$ ls -a $S/portab/repo
.  ..  .ergane  ergane.yaml  .git  .gitignore  README.md

$ cat $S/portab/repo/ergane.yaml
version: 1
runtime: bwrap
gates:
  test: 'true'
landing_branch: main

$ cat $S/portab/repo/.gitignore
.ergane/

$ cat $S/home/.local/state/ergane/repos.json
{
  "repos": {
    "repo": {
      "manifest": ".../portab/repo/ergane.yaml",
      "path": ".../portab/repo"
    }
  },
  "version": 1
}
```

`ergane init`'s exit code is still 0, and deliberately so — the scaffold and the
registry entry genuinely did succeed. `ergane init --check` is the door whose
exit code is the readiness verdict; this spec's Out of Scope records that it was
checked and is correct as built.

## What this run touched on the live host, stated plainly

The readiness report at the end of `init` calls `read_schedule`, which **opens a
client onto the live Temporal at `localhost:7233`, namespace `factory`, and
describes `ergane-roadmap-repo`** — that is where its `[FAIL] roadmap_schedule`
line comes from. It is a read: `describe` on an id that does not exist, and it
predates this story. The three `temporal schedule list` / `describe` commands
above are reads too, run by hand as the verification the plan asks for. Nothing
in this run created, updated, paused or deleted a schedule anywhere, and the
before/after listing is the evidence for that rather than the assertion.
