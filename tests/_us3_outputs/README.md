# US3 verification outputs

These files are the runtime evidence required by the acceptance scenarios for
US3 of epic 043-runtime-root-integrity.  Each file contains pasted tool output;
no prose description substitutes for the run.

- `us3-s02-dry-run-output.txt` — output of `ergane repo migrate-runtime-root`
  (without `--yes`) against a scratch repo holding only a legacy runtime root and
  a reachable Temporal with no epics open.
