# Operator instruction discovery evidence

Six fresh-session records, three session shapes per supported client. Codex
observations come from `codex debug prompt-input` and show the rendered model
input, not a model response. Claude observations record fresh non-interactive
Claude Code sessions.

Every record is redacted to repository-relative shape names. Canonical bytes are
pinned by the first 16 hex characters of `AGENTS.md`'s SHA-256.

| file | chain |
| --- | --- |
| `codex-root.json` | repository-root `AGENTS.md` |
| `codex-nested.json` | nested-directory ancestor `AGENTS.md` |
| `codex-worktree.json` | worktree-root `AGENTS.md` |
| `claude-root.json` | root `CLAUDE.md -> AGENTS.md` |
| `claude-nested.json` | nested ancestor `CLAUDE.md -> AGENTS.md` |
| `claude-worktree.json` | worktree-root `CLAUDE.md -> AGENTS.md` |
