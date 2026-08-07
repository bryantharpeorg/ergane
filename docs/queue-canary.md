# Merge-queue canary

This file landed through the factory's real merge queue on 2026-08-07,
minutes after the queue went live on `bryantharpeorg/ergane` — a deliberate
end-to-end rehearsal of the path every factory node now takes: branch push
from a target clone, `gh pr create`, `gh pr merge --auto --squash` into the
queue, the Actions `test` check, and GitHub's merge. If you are reading this
on the default branch, the path works.
