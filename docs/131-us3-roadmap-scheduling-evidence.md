# 131-US3 — two-pass scheduling evidence

The output is pasted from one isolated fixture run: the `001-built` spec is
scripted `ready` and observed-landed, while `002-real` has genuine work. The
activity recorder separates the two consecutive passes at the second corpus
read.

```text
pass1 001-built absent from dispatchable; 002-real dispatched
pass1 activities read_spec_text_activity(001-built); landed_for_spec(001-built); read_spec_text_activity(002-real); landed_for_spec(002-real); drift_for_spec(001-built); clone_target(002-real); preflight_spec(002-real); onboard_target(002-real)
pass2 001-built absent from dispatchable; no spec dispatched
pass2 activities read_spec_text_activity(001-built); landed_for_spec(001-built); drift_for_spec(001-built)
roadmap_status 001-built rendered_state=built dispatchable=false landed=true kind=observed
```
