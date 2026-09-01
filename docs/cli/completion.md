# `ergane completion`

> emit a shell completion script

```
ergane completion {bash|zsh}
```

| argument | choices | meaning |
| --- | --- | --- |
| `<shell>` | `bash`, `zsh` | target shell |

Prints the script to stdout. It installs nothing and writes to no rc file —
where the script goes is your decision.

## bash

```bash
ergane completion bash > ~/.local/share/bash-completion/completions/ergane
```

Or, for the current shell only:

```bash
eval "$(ergane completion bash)"
```

## zsh

```bash
ergane completion zsh > ~/.zfunc/_ergane
```

with `~/.zfunc` on `$fpath` before `compinit` runs. Or, for the current shell:

```bash
eval "$(ergane completion zsh)"
```

## It follows the parser

Nouns are discovered by walking `factory/cli/nouns/`, so the completion script
reflects whatever the installed version actually has. **Regenerate it after
upgrading** — a stale script completes the previous version's verbs, which is
worse than no completion because it reads as authoritative.

## See also

- [the noun index](README.md) — the same surface, written out
