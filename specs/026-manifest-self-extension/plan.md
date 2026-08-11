# Plan: 026-manifest-self-extension

Scaffolded from the following ledger findings:

- `interpreter/manifest-schema-cannot-be-extended-by-a-story` — critical: The config gate parses the node's factory.yaml with the WORKER's installed parser, not the worktree's, so any story that adds a factory.yaml key fails CONFIG_ERROR on every attempt no matter how correct its code is

Refine the approach before the spec is readied.
