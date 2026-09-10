# Tasks: an engine upgrade keeps its rollback image

Read the complete trio and plan traps. Use real generated artifacts and identity
files beneath temporary roots. Factory tests capture every child operation; no
Docker daemon, operator login, worker mutation or production fault injection.
The dependency check and readiness preflight are recorded in the plan; neither
changes the three story slices below nor authorizes live upgrade qualification
inside a factory gate. Reconcile the already-landed onboarding warnings in US3.

## User Story 1 — Bound image cleanup

- [ ] T001 [US1] (US1-S1, FR-001) Add focused tests of the production retention
      policy with target/previous/older published Ergane images, another
      repository and a prefix lookalike. Assert the exact removal set and the
      unconditional retention of unrelated images. Capture the pre-fix red.
- [ ] T002 [US1] (US1-S2, FR-002) Cover unknown/malformed/unrecognized previous
      images, digest/dangling/nonrelease tags, newer images, and numeric version
      ordering. Ambiguous entries stay; an unknown predecessor removes nothing.
- [ ] T003 [US1] (US1-S1, US1-S2, FR-001, FR-002) Repair the existing pure policy
      using the declared repository and conservative numeric release ordering.
      Do not add a dependency, alternate inventory or daemon-wide cleanup.
- [ ] T004 [US1] (US1-S3, FR-003) Exercise the default inventory/removal runner
      with captured subprocess calls. Failed inventory causes no removals;
      successful inventory reaches the production policy; deletion uses only
      eligible explicit references and no force/prune options.
- [ ] T005 [US1] (US1-S3) Run focused and existing retention/upgrade controls,
      commit compact red/green evidence, then run the declared full gate.

## User Story 2 — Preserve pre-stop rollback identity

- [ ] T006 [US2] (US2-S1, FR-004) Add a file-backed lifecycle regression using
      the real identity writer/reader/remover. A synthetic stop removes the old
      identity and start writes the new one; assert read-before-stop ordering
      and old/target image retention. Capture the specific pre-fix red.
- [ ] T007 [US2] (US2-S2, FR-004) Cover absent, malformed and image-less initial
      identity separately. A later readable replacement must not authorize any
      cleanup. Do not patch the reader to return a constant object.
- [ ] T008 [US2] (US2-S1, US2-S2, FR-004) Capture rollback identity before the
      first disruptive call and carry that snapshot to the existing policy.
      Keep unknown predecessor information unknown.
- [ ] T009 [US2] (US2-S3, FR-005) Prove failed stop, failed start and failed
      engine verification cause no removal. Preserve unrelated-finding visibility
      and the engine-specific degraded verdict; change cleanup sequencing as needed.
- [ ] T010 [US2] (US2-S3) Run focused lifecycle/retention and existing upgrade
      controls, commit compact actual red/green and ordered-call output, then
      run the declared full gate. Do not add automatic rollback.

## User Story 3 — Persist and launch the selected image

- [ ] T011 [US3] (US3-S1, FR-006, FR-007, FR-009) Generate and persist an old
      operational project using the real generator/writer. Drive the default
      upgrade runner with subprocess capture; inspect persisted image/version
      and the actual Compose process environment. Prove both the dropped-env
      and literal-old-image regressions before changing implementation.
- [ ] T012 [US3] (US3-S2, FR-007, FR-009) Add comparisons for nondefault mounts,
      user, ports, confinement and unrelated environment values. Assert matching
      updated ownership digests, unchanged unrelated fields and no written secrets.
- [ ] T013 [US3] (US3-S3, FR-008) Add changed/unclaimed/missing/unsupported
      project cases with byte snapshots and a no-stop/no-write call log. Retain
      the existing open-epic refusal and explicit force control; force must not
      adopt operator edits. Add persistence-failure no-start/no-cleanup controls.
- [ ] T014 [US3] (US3-S1, US3-S2, US3-S3, FR-006, FR-007, FR-008) Implement
      pre-disruption validation and narrow persistent project retargeting through
      the existing project/manifest boundaries. Forward the selected version at
      the actual Compose subprocess boundary. Preserve the project's unrelated
      declarations; never rerun install, infer defaults or bypass ownership.
- [ ] T015 [US3] (US3-S1, FR-006, FR-007) Assert a subsequent invocation of the
      same saved project selects the requested image/version without an
      invocation-only overlay. Re-run both real-boundary regressions.
- [ ] T016 [US3] (US3-S4, FR-009) Reconcile the container and engine CLI upgrade
      documentation with implemented behavior and the onboarding refresh. Keep
      real-image/rollback qualification distinct from captured-runner checks.
- [ ] T017 [US3] (US3-S4, FR-009) Run focused new checks plus existing upgrade,
      generator and ownership/manifest controls. Commit compact pasted outputs
      labelled synthetic, then run the full declared gate. Preserve the 64 KiB
      bound and the normal judge/native merge-queue path.
