# 051-US1 evidence — SC-001

**SC-001**: on a machine whose git creates `master`, `git init . && ergane init`
with every default accepted produces a manifest whose `landing_branch` check
passes.

This is a claim about a machine, so it is a transcript rather than a sentence
(constitution VIII / D-037: the judge sees the diff and the criteria, never a
terminal). Both runs below are the same script against the same host, differing
only in which `factory` package is on `PYTHONPATH`: the tree at `3e9cbde` for
BEFORE, this branch for AFTER. The line printing `factory/cli/init.py` and
`has _current_branch` is in each run so the two cannot be confused.

Every exit code is captured as `rc=$?` immediately after the command and before
any pipe (plan trap 2). The interview is answered by a here-doc of nine blank
lines — eight manifest keys, then the slug — which is what pressing enter
through it does.

**Isolation.** `HOME`, `ERGANE_STATE_HOME` and `ERGANE_CONFIG_PATH` point into a
scratch directory and `TEMPORAL_ADDRESS` at a dead port, under `env -i`, so
these runs cannot register a repository in the operator's registry nor create a
schedule on the operator's live control plane. That is why `control_plane` and
`roadmap_schedule` fail in every stanza, and why `repo_read` fails — a scratch
repository has no GitHub remote and `gh` is not authenticated here. None of the
three touches `landing_branch`, which is judged from `refs/heads/` in the
repository itself.

## Two repository shapes, because they answer differently

- **`committed`** — `git init` then one commit. The repository is on `master`
  and `refs/heads/master` exists. This is SC-001's subject, and it goes from
  FAIL to PASS.
- **`empty`** — `git init` and nothing else: no commits, no resolvable HEAD.
  This is US1-S3. It offers the literal `main` and still reports
  `[FAIL] landing_branch` — **unchanged by this story, and unfixable by it**: an
  empty repository has no refs at all, so `git show-ref --verify
  refs/heads/<anything>` fails whatever the interview offers. `ergane init`
  completes and exits 0, which is what FR-002 requires. Worth naming plainly:
  the reproduction quoted in the spec's Context is this shape, and the sentence
  in SC-001 is only achievable in the shape that has a commit.

## BEFORE — the tree at `3e9cbde`

Excerpted: the two decisive lines per case, from a run of the same script. The
elision is marked; nothing between the quoted lines is rewritten.

```
=== BEFORE ===

$ git --version
git version 2.43.0

# which factory package this run imports, and what it offers as a literal
/tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/base-tree/factory/cli/init.py
_PLACEHOLDERS[landing_branch] = main
has _current_branch = False
```

### case: empty

```
schema version [1]: runtime backend [bwrap]: gates (YAML mapping of gate name to command) [test: 'true']: timeouts in seconds (YAML mapping of gate name to seconds, optional) []: standards document path (optional) []: landing branch [main]: roadmap dials (YAML mapping of cadence_s, max_concurrent_epics, max_concurrent_nodes, optional) []: forge this repository is on (optional) []: repo slug [empty]:
  [FAIL] landing_branch: the manifest declares `landing_branch: main` but /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-before/empty has no such branch; create it with `git -C /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-before/empty branch main`, or declare the branch this repository actually lands on
# ergane.yaml -> landing_branch: main
```

### case: committed

```
schema version [1]: runtime backend [bwrap]: gates (YAML mapping of gate name to command) [test: 'true']: timeouts in seconds (YAML mapping of gate name to seconds, optional) []: standards document path (optional) []: landing branch [main]: roadmap dials (YAML mapping of cadence_s, max_concurrent_epics, max_concurrent_nodes, optional) []: forge this repository is on (optional) []: repo slug [committed]:
  [FAIL] landing_branch: the manifest declares `landing_branch: main` but /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-before/committed has no such branch; create it with `git -C /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-before/committed branch main`, or declare the branch this repository actually lands on
# ergane.yaml -> landing_branch: main
```

The offered default is `main` in both, on a repository that is on `master`.

## AFTER — this branch, verbatim and unabridged

```
=== AFTER ===

$ git --version
git version 2.43.0

# which factory package this run imports, and what it offers as a literal
/tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/wt-051-us1/factory/cli/init.py
_PLACEHOLDERS[landing_branch] = main
has _current_branch = True

------------------------------------------------------------------
case: empty
------------------------------------------------------------------
$ git init .
Initialized empty Git repository in /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/empty/.git/

$ git symbolic-ref --short HEAD
master
rc=0
$ git rev-parse --abbrev-ref HEAD
fatal: ambiguous argument 'HEAD': unknown revision or path not in the working tree.
Use '--' to separate paths from revisions, like this:
'git <command> [<revision>...] -- [<file>...]'
HEAD
rc=128

$ ergane init      # nine blank answers: press enter through the interview
schema version [1]: runtime backend [bwrap]: gates (YAML mapping of gate name to command) [test: 'true']: timeouts in seconds (YAML mapping of gate name to seconds, optional) []: standards document path (optional) []: landing branch [main]: roadmap dials (YAML mapping of cadence_s, max_concurrent_epics, max_concurrent_nodes, optional) []: forge this repository is on (optional) []: repo slug [empty]: joined /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/empty as slug 'empty'
written:
  /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/empty/ergane.yaml
  /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/empty/.gitignore
  /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/empty/.ergane
registered: 'empty' -> /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/empty
schedule: failed ergane-roadmap-empty — cannot reach Temporal at 127.0.0.1:1 (namespace 'factory'): Failed client connect: Server connection error: tonic::transport::Error(Transport, ConnectError(ConnectError("tcp connect error", 127.0.0.1:1, Os { code: 111, kind: ConnectionRefused, message: "Connection refused" })))
github wiring: not attempted — re-run with `ergane init --wire` to
  queue the landing branch and require one check per declared gate
next, run:
  git -C /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/empty add ergane.yaml .gitignore .ergane
  git -C /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/empty commit -m "join ergane"

ergane readiness for /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/empty (ergane.yaml)
  [FAIL] repo_read: could not read the repo via its forge (GH_REFUSED): To get started with GitHub CLI, please run:  gh auth login
Alternatively, populate the GH_TOKEN environment variable with a GitHub API authentication token.

  [PASS] runtime_root_ignored: .ergane/ is ignored by git
  [PASS] registry_entry: registered as 'empty' in /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/state/ergane/repos.json
  [FAIL] landing_branch: the manifest declares `landing_branch: main` but /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/empty has no such branch; create it with `git -C /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/empty branch main`, or declare the branch this repository actually lands on
  [FAIL] control_plane: the control plane could not be probed: ControlPlaneConfigError: /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/state/no-such-config.toml: [config_missing] cannot be read (No such file or directory); run `ergane install` to create the control-plane config — `ergane install --verify` reports each subsystem separately
  [FAIL] roadmap_schedule: this repository's roadmap schedule could not be judged: cannot reach Temporal at 127.0.0.1:1 (namespace 'factory'): Failed client connect: Server connection error: tonic::transport::Error(Transport, ConnectError(ConnectError("tcp connect error", 127.0.0.1:1, Os { code: 111, kind: ConnectionRefused, message: "Connection refused" })))
4 of 6 checks failed
rc=0

$ cat ergane.yaml
version: 1
runtime: bwrap
gates:
  test: 'true'
landing_branch: main

$ ergane init --check
ergane readiness for /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/empty (ergane.yaml)
  [FAIL] repo_read: could not read the repo via its forge (GH_REFUSED): To get started with GitHub CLI, please run:  gh auth login
Alternatively, populate the GH_TOKEN environment variable with a GitHub API authentication token.

  [PASS] runtime_root_ignored: .ergane/ is ignored by git
  [PASS] registry_entry: registered as 'empty' in /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/state/ergane/repos.json
  [FAIL] landing_branch: the manifest declares `landing_branch: main` but /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/empty has no such branch; create it with `git -C /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/empty branch main`, or declare the branch this repository actually lands on
  [FAIL] control_plane: the control plane could not be probed: ControlPlaneConfigError: /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/state/no-such-config.toml: [config_missing] cannot be read (No such file or directory); run `ergane install` to create the control-plane config — `ergane install --verify` reports each subsystem separately
  [FAIL] roadmap_schedule: this repository's roadmap schedule could not be judged: cannot reach Temporal at 127.0.0.1:1 (namespace 'factory'): Failed client connect: Server connection error: tonic::transport::Error(Transport, ConnectError(ConnectError("tcp connect error", 127.0.0.1:1, Os { code: 111, kind: ConnectionRefused, message: "Connection refused" })))
4 of 6 checks failed
rc=1

------------------------------------------------------------------
case: committed
------------------------------------------------------------------
$ git init .
Initialized empty Git repository in /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/committed/.git/
$ echo '# app' > README.md && git add -A && git commit -m 'initial commit'
rc=0

$ git symbolic-ref --short HEAD
master
rc=0
$ git rev-parse --abbrev-ref HEAD
master
rc=0

$ ergane init      # nine blank answers: press enter through the interview
schema version [1]: runtime backend [bwrap]: gates (YAML mapping of gate name to command) [test: 'true']: timeouts in seconds (YAML mapping of gate name to seconds, optional) []: standards document path (optional) []: landing branch [master]: roadmap dials (YAML mapping of cadence_s, max_concurrent_epics, max_concurrent_nodes, optional) []: forge this repository is on (optional) []: repo slug [committed]: joined /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/committed as slug 'committed'
written:
  /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/committed/ergane.yaml
  /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/committed/.gitignore
  /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/committed/.ergane
registered: 'committed' -> /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/committed
schedule: failed ergane-roadmap-committed — cannot reach Temporal at 127.0.0.1:1 (namespace 'factory'): Failed client connect: Server connection error: tonic::transport::Error(Transport, ConnectError(ConnectError("tcp connect error", 127.0.0.1:1, Os { code: 111, kind: ConnectionRefused, message: "Connection refused" })))
github wiring: not attempted — re-run with `ergane init --wire` to
  queue the landing branch and require one check per declared gate
next, run:
  git -C /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/committed add ergane.yaml .gitignore .ergane
  git -C /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/committed commit -m "join ergane"

ergane readiness for /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/committed (ergane.yaml)
  [FAIL] repo_read: could not read the repo via its forge (GH_REFUSED): To get started with GitHub CLI, please run:  gh auth login
Alternatively, populate the GH_TOKEN environment variable with a GitHub API authentication token.

  [PASS] runtime_root_ignored: .ergane/ is ignored by git
  [PASS] registry_entry: registered as 'committed' in /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/state/ergane/repos.json
  [PASS] landing_branch: landing branch 'master' exists
  [FAIL] control_plane: the control plane could not be probed: ControlPlaneConfigError: /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/state/no-such-config.toml: [config_missing] cannot be read (No such file or directory); run `ergane install` to create the control-plane config — `ergane install --verify` reports each subsystem separately
  [FAIL] roadmap_schedule: this repository's roadmap schedule could not be judged: cannot reach Temporal at 127.0.0.1:1 (namespace 'factory'): Failed client connect: Server connection error: tonic::transport::Error(Transport, ConnectError(ConnectError("tcp connect error", 127.0.0.1:1, Os { code: 111, kind: ConnectionRefused, message: "Connection refused" })))
3 of 6 checks failed
rc=0

$ cat ergane.yaml
version: 1
runtime: bwrap
gates:
  test: 'true'
landing_branch: master

$ ergane init --check
ergane readiness for /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/committed (ergane.yaml)
  [FAIL] repo_read: could not read the repo via its forge (GH_REFUSED): To get started with GitHub CLI, please run:  gh auth login
Alternatively, populate the GH_TOKEN environment variable with a GitHub API authentication token.

  [PASS] runtime_root_ignored: .ergane/ is ignored by git
  [PASS] registry_entry: registered as 'committed' in /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/state/ergane/repos.json
  [PASS] landing_branch: landing branch 'master' exists
  [FAIL] control_plane: the control plane could not be probed: ControlPlaneConfigError: /tmp/claude-1000/-home-admin-code-ergane/26b636f4-b4ec-41c9-b750-8585e2849003/scratchpad/scratch-051-us1/tx-after/state/no-such-config.toml: [config_missing] cannot be read (No such file or directory); run `ergane install` to create the control-plane config — `ergane install --verify` reports each subsystem separately
  [FAIL] roadmap_schedule: this repository's roadmap schedule could not be judged: cannot reach Temporal at 127.0.0.1:1 (namespace 'factory'): Failed client connect: Server connection error: tonic::transport::Error(Transport, ConnectError(ConnectError("tcp connect error", 127.0.0.1:1, Os { code: 111, kind: ConnectionRefused, message: "Connection refused" })))
3 of 6 checks failed
rc=1
```

## What changed, in three lines

| | BEFORE | AFTER |
| --- | --- | --- |
| the question, on a `master` repository | `landing branch [main]:` | `landing branch [master]:` |
| the manifest an operator who pressed enter gets | `landing_branch: main` | `landing_branch: master` |
| the check | `[FAIL] landing_branch: the manifest declares ...` | `[PASS] landing_branch: landing branch 'master' exists` |

The check itself — `factory/mergequeue/onboard.py:384` — is untouched by this
story. It was right; the offer was wrong.
