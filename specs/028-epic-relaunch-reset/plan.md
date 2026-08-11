# Plan: 028-epic-relaunch-reset

Scaffolded from the following ledger findings:

- `interpreter/relaunched-epic-resumes-the-dead-runs-tree` — critical: Relaunching a killed or terminated epic silently resumes the dead run's worktree at the dead run's base pin, because three artifacts outlive the workflow: the worktree directory (survives 'temporal workflow terminate' entirely), the <node>.json base-ref sidecar (survives even a clean kill_epic), and the node branch (survives by explicit design). There is no operator command that clears them.

Refine the approach before the spec is readied.
