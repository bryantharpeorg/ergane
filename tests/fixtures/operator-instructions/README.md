# `operator-instructions/` — six-client-context discovery evidence (157 US1-S2)

Six fresh-session observations, three session shapes per client, recorded on
2026-09-09 against the installed clients (`codex-cli 0.153.4`,
`Claude Code 2.1.261`). Every record is **redacted**: host paths and the
scratch homes the probes ran in are replaced by `<REPO>`, `<PARENT>` and
`<HOME>`; the model alias is kept (it is the route the factory declares, not a
secret); no credential, token or account value appears anywhere — the probes
drove the CLI's own non-interactive surfaces, not a signed-in account.

`AGENTS.md` content in these records is the real canonical orientation
(`markers` below were planted only in *scratch* fixtures during measurement;
the repo's own file was never modified). `canonical_sha` pins the canonical
orientation bytes each record's client actually received, so a drift between
the file and the evidence is detectable.

| file | client | session shape | what it proves |
| --- | --- | --- | --- |
| `codex-root.json` | codex | repository root | Codex loads the canonical file at the root |
| `codex-nested.json` | codex | nested directory | the nearest `AGENTS.md` wins; parent chain still resolves to the canonical text when no nearer file exists |
| `codex-worktree.json` | codex | git worktree | a worktree root is a discovery stop — no ancestor policy crosses it |
| `claude-root.json` | claude | repository root | the compatibility entry point resolves to the canonical bytes |
| `claude-nested.json` | claude | nested directory | same resolution from a nested cwd |
| `claude-worktree.json` | claude | git worktree | the symlink survives the worktree shape the factory's own nodes run in |

`tests/test_operator_instructions.py` parses these records and asserts the
observation contract (US1 scenario 2): every record names the canonical
instructions exactly once, and each carries the dispatched-node facts — the
assembled prompt and the declared standards precedence — that keep
auto-discovery from becoming a second standards channel.