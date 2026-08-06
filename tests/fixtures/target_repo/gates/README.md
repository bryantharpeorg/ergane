# Gate scripts

Every gate command in every manifest is `bash gates/<name>.sh`, so a gate's
behaviour lives in one readable file instead of being spelled out as a shell
one-liner inside YAML. The runner executes commands with `bash -c` and
`cwd=<worktree>` (research R3), which is why the paths below are worktree-relative.

Two constraints these scripts honour, both of them consequences of R3's scrubbed
environment:

- **Bash builtins first, coreutils only when unavoidable.** A gate that needed a
  Python interpreter would fail for two indistinguishable reasons — a real gate
  failure, or a `PATH` the runner scrubbed too hard. `sleep` is the one external
  binary used (in the timeout scripts), and it is used where its absence would be
  obvious rather than subtle.
- **No credentials assumed.** `env-probe.sh` is the only script that mentions the
  factory's secrets, and it mentions them precisely to prove they are not there.

Each script appends its gate name to `.factory-gate-order.log` (gitignored) before
doing anything else, so execution order is observable from the worktree and not
merely inferred from the order of the returned results.
