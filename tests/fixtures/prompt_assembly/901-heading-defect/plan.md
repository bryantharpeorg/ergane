# Plan: Runtime root integrity (reconstructed)

The plan is well-formed and whole; assembly quotes it verbatim into every
node's prompt and has no failure mode of its own here. It exists in this
fixture because the trio is read as a trio: a missing `plan.md` is a different
defect (US1 scenario 4), and a fixture that carried it by accident would prove
the wrong thing.

## Approach

Resolve the runtime root in one place, and let every store address itself
through that resolver rather than through its own environment read.

## Traps

- The leak detector's only green condition on a working host must never be the
  destruction of the live store.
