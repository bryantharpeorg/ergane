# spec-validate fixtures (133-US1)

Two synthetic fixture trios and the one target repository they share, committed
so the golden captures under `tests/golden/spec_validate/` are taken over bytes
that never move. A golden taken against a corpus spec under `specs/` would go
red the next time that spec was refined, for a reason that has nothing to do
with the validate verb (plan trap 12); these trios are edited only together
with the goldens they feed.

| Path | What it is |
| --- | --- |
| `clean-specs/001-clean-trio/` | Validates clean: no refusal, no advisory. One skipped layer — `anchor_resolution`, because the `path:NN` citation in its `spec.md` names a file the shared target repository does not carry — and one information note from its `tasks.md` ERGANE-TODO sentinel. Its stdout golden carries the all-pass sentence. |
| `defective-specs/002-defective-trio/` | Deliberately defective: one evidence refusal (a Then-clause asserting "renders correctly in the browser", which no gate the shared manifest declares can produce) and one scenario-coverage advisory (US1-S1 is declared, its `tasks.md` names no scenario id). A run carrying a refusal never prints the all-pass sentence, so this trio freezes the shape the clean one cannot (plan trap 3). Its stderr golden is where US6-S4 takes the exact evidence-refusal string from. |
| `target-repo/` | The one fixture target repository both trios share: an `ergane.yaml` (schema v2) declaring a single gate, `smoke`, and none of the files the trios cite. Without a readable manifest declaring a gate, the evidence layer would skip instead of refusing (plan trap 20). |

Each trio sits in a parent directory holding nothing else, because the
frontmatter layer reads `spec_dir.parent` as the specs root and a sibling file
would join the roadmap it reads (plan trap 13). Both trios deliberately carry
one ERGANE-TODO sentinel each: the sentinel loop needs no store and embeds no
absolute path, so the information note it produces is host-independent.

Editing any document here means re-capturing all six artifacts in the same
commit — see `tests/golden/spec_validate/README.md`.