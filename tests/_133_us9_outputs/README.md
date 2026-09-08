# 133-US9 verification outputs

Runtime evidence required by US9's acceptance scenarios (epic 133). Each file
holds pasted tool output; no prose substitutes for the run.

- `t042_corpus_sweep_empty_diff.txt` — T042: the pre- and post-change sweeps of
  `ergane spec validate` over all 147 specs of `specs/`, both streams and
  `--json` (plan step 4). Driven in-process from a pinned environment.
- `t042_demo_stage_before_after.txt` — T042: the demonstration's validate stage
  before and after T041, transcript-identical up to the throwaway repo's tmp
  path.
- `t052_controls_differ.txt` — T052: the two re-pointed corpus controls driven
  over a spec each layer refuses, the differing verdict proving each still
  disables something.