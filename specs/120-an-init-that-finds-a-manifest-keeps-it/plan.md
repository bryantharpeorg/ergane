# Implementation Plan: an init that finds a manifest keeps it

**Spec**: `specs/120-an-init-that-finds-a-manifest-keeps-it/spec.md`

Stop rewriting what is already valid; when a rewrite is unavoidable, lose
nothing; and reconcile against the file rather than against the edit.

## What already exists, and where

- **The five lines that lose the data**: `_init_default(key, repo_root)`
  (`factory/cli/init.py:641`). It calls `_build_defaults(repo_root)`, then
  returns `None` for anything in `_OPTIONAL_KEYS` **before** consulting that
  result. The comment above the early return — "Optional keys have a safe default
  of 'absent'" — is the defect stated as a justification.
- **The values it discards**: `_build_defaults(repo_root)` (`:611`) opens
  `existing = _load_existing_defaults(repo_root)` and seeds each key with
  `existing.get(key, <placeholder>)` (`:614-616`). The committed value is
  therefore in hand at the moment it is thrown away.
- **The vocabulary**: `_OPTIONAL_KEYS = ("timeouts", "standards", "roadmap",
  "forge", "writes")` (`:437`). `ladder` and `verify` appear nowhere in it, which
  is why FR-006 is a separate requirement from FR-005 — they are not
  "optional keys handled wrongly", they are keys init has never heard of.
- **The emitter**: `yaml.safe_dump(value, default_flow_style=False)` (`:605`),
  with two comments nearby (`:476`, `:587`) recording other things `safe_dump`
  does that had to be worked around. Neither preserves comments, and nothing
  here can.
- **Why `--check` cannot catch it**: `standards` is optional in the schema at
  `factory/verify/factory_yaml.py:459-461` — `_read_standards`, whose own
  comment says "Absent is not a defect: most repos declare no standards
  document" — so a manifest missing it is valid.
  This is correct schema behaviour and is not changed.

## Traps

**Trap 1 — "valid" must mean the schema's answer, not init's.** US1 turns on
whether the existing manifest is valid. Ask the same loader `init --check` asks,
so the two verbs cannot disagree about the same file. An independent notion of
validity inside init is how a file gets called valid by one verb and replaced by
another.

**Trap 2 — not rewriting is not declining.** FR-002 and US1-S2. `--wire` does
real work — the ruleset, the required checks, the scaffolded workflow — and the
manifest write is one part of it. An implementer who early-returns when the
manifest is valid has skipped the job the operator asked for. Separate the
decision "write the manifest" from the decision "do the wiring".

**Trap 3 — an invalid manifest is a conversation, not a licence.** US1-S4. The
tempting reading of "leave a valid manifest alone" is "so replace an invalid
one". That is worse than today: it destroys a file whose author is mid-edit.
Report and stop.

**Trap 4 — fix the ordering, not the comment.** The minimal edit is to move the
`_OPTIONAL_KEYS` early return below the `defaults` consultation, so an existing
value wins and "absent" applies only when nothing was declared. Do that rather
than special-casing `standards`, which would leave `roadmap`, `forge`, `writes`
and `timeouts` losing data for the next person to find.

**Trap 5 — `ladder` and `verify` need adding to the carry-forward path, not to
the interview.** FR-006 asks that they survive a rewrite. It does not ask init to
start interviewing operators about the ladder. Carry them through; do not grow
the question set.

**Trap 6 — FR-007's refusal must not fire on a manifest init wrote.** An
unrecognised key refuses the rewrite, which is right for an operator's hand-added
key and wrong if init's own output round-trips into something it does not
recognise. Assert a round trip: write a manifest, rewrite it, and confirm no
refusal.

**Trap 7 — US3 is comparing against the wrong object, and the fix is to move the
read.** The non-interactive path rewrites, then compares the schedule to the
rewritten manifest. Read the roadmap dial from the file as it stood before any
write, and compare against that. Once US1 lands, the common case rewrites
nothing — but the comparison must be correct in the case that does.

**Trap 8 — the byte-identical assertion is the only one that catches comment
loss.** US1-S1 says byte-identical, comments included. A test asserting the
parsed structures match would pass on a rewrite that dropped forty lines of
prose, which is exactly the failure being fixed. Compare bytes.

## Sizing

US1 is a condition and a separation of two decisions — small, with traps 2 and 3
the risks. US2 is the ordering fix plus two keys plus a refusal. US3 is moving
one read earlier.

If an attempt is changing the manifest schema, making `standards` mandatory, or
replacing the YAML emitter, it has gone outside the spec.

## Verification the operator will run, independent of the gate

The gate proves the file is untouched. The operator's demonstration is the one
that mattered — the diff nobody would have run:

```bash
eval "$(scripts/ergane-env.sh)"
cd <a target repo with a configured, commented manifest>
git stash list && git status --short          # clean tree first
sha256sum ergane.yaml
uv run ergane init --wire --non-interactive
sha256sum ergane.yaml                          # must match
git diff --stat                                # must be empty for the manifest
uv run ergane init --check                     # must still pass
```

The demonstration succeeds when the two checksums match and `git diff` shows
nothing for the manifest. Paste both checksums into the attestation. Before this
spec the same sequence silently removes `standards`, the whole `ladder` block and
about forty lines of comments, and `init --check` reports the result valid.
