# 157 US1 qualification

## Focused gate

```text
uv run pytest tests/test_operator_instructions.py tests/test_claude_md.py -q
============================== 68 passed in 1.05s ==============================
```

## Repository gate

```text
uv run pytest -q
========== 6079 passed, 58 skipped, 15 warnings in 606.31s (0:10:06) ===========
```

## Codex rendered inputs

`codex-cli 0.154.0` rendered its prompt input in fresh temporary homes. The
evidence is the model-visible input, not a model response. Host paths are
redacted below as `<REPO>`, `<PARENT>` and `<WORKTREE>`.

```text
root:     # AGENTS.md instructions for <REPO>\n\n<INSTRUCTIONS>\n# Ergane ...
nested:   # AGENTS.md instructions for <PARENT>\n\n<INSTRUCTIONS>\n# Ergane ...
worktree: # AGENTS.md instructions for <WORKTREE>\n\n<INSTRUCTIONS>\n# Ergane ...
```

Each rendered chain carried one `AGENTS.md` instruction block beginning with
`If you are a factory implementer node, this is not your brief.`

## Claude fresh sessions

The prior attempt's installed `Claude Code 2.1.261` fresh-session evidence is
retained here, per the recovery brief. The compact redacted records show the
root, nested-directory and worktree compatibility chain
`CLAUDE.md -> AGENTS.md`; the tracked-file tests pin those records to the
canonical bytes of the orientation committed by this story.
