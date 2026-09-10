# Operator instruction discovery evidence

Six fresh-session records, three session shapes per supported client, qualified
on 2026-09-10. Codex observations come from the installed CLI's
`codex debug prompt-input`: rendered input, not a model response. Claude
observations capture the actual installed CLI's outgoing request before a
private synthetic peer returns an acknowledgment; no model inference occurred.
All use fresh temporary profiles, read-only repositories and isolated network
namespaces. No operator credentials are supplied and no client trust is changed.

Every record is redacted to repository-relative shape names. The full canonical
SHA-256, source revision, request/rendered-input digest and observed counts are
retained under `evidence`; the legacy16-character prefix stays for compatibility.
The complete decoded canonical text occurs once, ignoring only leading/trailing
whitespace. This establishes input loading, not model obedience to precedence.

Source revision c3d21e7 and PR head5cd4391 have identical full Git trees. The
subsequent native landing0d909c5 preserves AGENTS.md, the CLAUDE.md symlink and
the focused instruction tests unchanged. Equivalence was checked with actual
Git diffs; the recorded source is not repinned to a newer commit without proof.
Historical September9 observations over different canonical bytes are
superseded, not relabeled as September10 observations.

| file | chain |
| --- | --- |
| `codex-root.json` | repository-root `AGENTS.md` |
| `codex-nested.json` | nested-directory ancestor `AGENTS.md` |
| `codex-worktree.json` | worktree-root `AGENTS.md` |
| `claude-root.json` | root `CLAUDE.md -> AGENTS.md` |
| `claude-nested.json` | nested ancestor `CLAUDE.md -> AGENTS.md` |
| `claude-worktree.json` | worktree-root `CLAUDE.md -> AGENTS.md` |

Claude's three positive contexts were repeated in fresh profiles. An empty
directory control twice produced zero canonical/guard occurrences, and no
precedence guard. Its counts and digests are retained in
`docs/157-us1-discovery-evidence.md`. Request digests can vary between fresh
processes; the canonical digest and whole-text match are the identity checks.
Neither synthetic response token fields nor the requested model alias are
evidence of real usage or a serving model.
