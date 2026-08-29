---
state: ready
fixes:
  - ci/test-suite-pins-the-operator-dial
# DRAFTED 2026-08-29 by the operator session, against ergane-buildout at aef5257,
# while trying and failing to apply an ordinary operator instruction.
#
# THE SUITE MAKES UNUSABLE, IN THE REPOSITORY THAT SHIPPED IT, THE FEATURE THAT
# REPOSITORY SHIPPED. `023-composable-verification` added the `ladder:` block so
# an operator could declare the retry ladder in `ergane.yaml`. Two tests read
# this repository's LIVE manifest and freeze it, so declaring one reddens trunk:
#
#   tests/test_factory_yaml.py:463  test_erganes_own_manifest_loads
#                                   -> assert config.version == 1
#   tests/test_factory_yaml.py:1667 test_v1_identity_against_erganes_own_manifest
#                                   -> assert config == FactoryConfig(version=1,
#                                      ..., ladder=VerificationConfig())
#
# The second pins `ladder` to its DEFAULT, so any ladder at all fails it. There
# is no way around the manifest: `max_attempts` has no CLI dial — `ergane build
# start` exposes eight flags and no attempt cap — and no environment override
# exists anywhere under `factory/`.
#
# AND THE BLAST RADIUS IS NOT TRUNK, IT IS EVERY NODE. This repository's gate is
# `test: "uv run pytest -q"` (`ergane.yaml`). A node's gate runs the suite inside
# its own worktree, so a committed manifest change that reddens the suite fails
# every future attempt, not merely the operator's push. That is why the change
# this spec unblocks was written, validated and then deliberately left
# uncommitted.
#
# THE TEST'S PURPOSE IS REAL AND IS BEING OVER-SERVED. Its docstring says "the
# repo root `ergane.yaml` must stay byte-identical in every story (FR-011)".
# FR-011's subject is a STORY. A dispatched node must not edit the manifest,
# because the config gate parses it with the WORKER's installed parser, so a
# story that declares a key its worktree's parser knows and the worker's does not
# is refused at CONFIG_ERROR in 0.0s before any gate command runs — 020/US1 died
# four times proving exactly that. The invariant is correct. What is wrong is
# that a fixture reading LIVE operator config cannot distinguish "no node may
# edit this" from "nobody may edit this", and enforces the second.
#
# FIFTH SIGHTING OF ONE CLASS, AND THE FIRST OUTSIDE THE PERSONA REGISTRY.
# `ci/test-suite-pins-the-operator-dial` has been un-pinned field by field three
# times — 037 for `context_window`, then `model` on 2026-08-19 and again on
# 2026-08-29 — and returned each time on the next field. This spec does not
# un-pin a fourth field. It changes what the live manifest is allowed to be
# asserted about at all.
#
# THE REMEDY ALREADY EXISTS IN THIS SUITE, one file away.
# `tests/test_forge_manifest.py:58` calls the live manifest `OWN_MANIFEST` — "the
# file US5-S4 says this story may not edit" — and puts every parsing assertion
# against a globbed corpus at `tests/fixtures/target_repo/manifests/`, which
# ships eleven sample manifests today. This spec makes `test_factory_yaml.py`
# follow the convention its neighbour already established.
#
# NOT IN SCOPE. This spec does not change the manifest schema, does not change
# `ergane.yaml`, does not remove the live-manifest load (see trap 1), does not
# weaken FR-011, and does not touch the persona registry — the registry half of
# this finding is a separate surface and stays as it is.
---

# Feature Specification: the operator's manifest is not a frozen fixture

**Created**: 2026-08-29
**Depends on**: nothing outside this spec.

## The gap, stated precisely

Two tests assert that this repository's live `ergane.yaml` parses to one exact,
frozen value. One of them names the schema version; the other compares the whole
`FactoryConfig` field for field, including a `ladder` pinned to its default.

The manifest is the operator's file. Every dial it carries — the ladder, the
gates, the landing branch — is a dial the operator is meant to turn. Freezing its
parsed value in the suite means the operator cannot turn any of them without
reddening the gate that every node must pass.

## The rule this spec is asking for

**A test may assert that the operator's live manifest is valid. It may not assert
what the operator chose.**

Parser behaviour is proved against committed samples, which no operator edits and
which therefore can be frozen honestly.

### What this spec is not

It is not a schema change, and it does not edit `ergane.yaml`. The manifest
change this unblocks is the operator's to make afterwards.

It is not the removal of the live-manifest load. That load catches a stale
`standards` path before a live dispatch does, which is worth keeping — see US1-S3.

It is not a weakening of FR-011. A node still may not edit the manifest, and US1-S5
keeps a test that says so.

It is not a fix for the persona-registry half of the same finding. That surface is
untouched here.

## User Scenarios & Testing

### User Story 1 - The live manifest is checked for validity, not for content (Priority: P1)

As an operator, I can declare any legal `ladder:` block — or change any other
dial — in this repository's manifest without a test failing.

**Why this priority**: P1 and it depends on nothing. Until it lands, an operator
instruction that spec 023 was written to serve cannot be carried out, and the
attempt to carry it out fails every node rather than only the push.

**Acceptance Scenarios**:

1. **Given** this repository's manifest declaring a `ladder:` block, **When** the
   suite runs, **Then** it passes — proven by a committed test. This is the whole
   point: today it fails on two assertions.
2. **Given** this repository's manifest at any schema version the parser accepts,
   **When** the suite runs, **Then** no test asserts a particular version number
   — proven by a committed test. A version is an operator's choice, and pinning
   it is how the last four recurrences happened.
3. **Given** a manifest declaring a `standards` path that does not exist, **When**
   the suite runs, **Then** a test fails naming the missing file — proven by a
   committed test. This is what the live-manifest load is genuinely for, and it
   must survive.
4. **Given** the committed sample corpus, **When** v1 parsing changes shape,
   **Then** a test fails — proven by a committed test. The v1 regression fixture
   keeps working; it moves off the operator's file and onto a sample that can be
   frozen honestly.
5. **Given** a node's worktree whose manifest differs from the landing branch's,
   **When** the check that FR-011 asks for runs, **Then** it refuses naming the
   file — proven by a committed test. A node still may not edit the manifest.
6. **Given** the live manifest, **When** the suite asserts against it, **Then**
   what it asserts is derivable from the manifest being *valid* rather than from
   the manifest being *this one* — proven by a committed test that reads the
   assertions themselves. Without this the next dial gets pinned the next time
   somebody reaches for a convenient literal.

## Work Graph

```yaml
US1:
  implements: []
  depends_on: []
```

One story. Both edits land in `tests/test_factory_yaml.py` plus one new sample
under `tests/fixtures/target_repo/manifests/`, and splitting them would serialise
two halves of a single file rename on each other for no gain.

## Requirements

- **FR-001**: The suite MUST NOT assert that this repository's live manifest has
  a particular schema version.
- **FR-002**: The suite MUST NOT assert that this repository's live manifest
  parses to a particular `FactoryConfig` value.
- **FR-003**: The suite MUST still fail when the live manifest cannot be parsed.
- **FR-004**: The suite MUST still fail when the live manifest's declared
  `standards` path does not exist.
- **FR-005**: v1 parse-shape regression MUST still be proven, against a committed
  sample manifest rather than against the live one.
- **FR-006**: The FR-011 invariant — that a dispatched node does not edit the
  manifest — MUST still be proven.
- **FR-007**: The suite MUST NOT be made to pass by deleting coverage; every
  assertion removed from the live manifest MUST have a committed-sample
  counterpart.

## Success Criteria (summary)

- An operator can declare a `ladder:` block in `ergane.yaml`, run the suite, and
  see it green.
- A parser regression in v1 semantics still fails a test.
- A stale `standards` path still fails a test before a live dispatch finds it.
- The next operator dial that moves does not produce a sixth recurrence.
