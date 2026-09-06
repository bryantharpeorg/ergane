# Implementation Plan: a landed read says what it could not see

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**One reader, four callers, no measurement.**
`factory/workgraph/landed.py:130` — `landed_facts` is the whole surface. Its
signature already carries the opt-out the second story needs:

```python
def landed_facts(
    repo: str | Path,
    spec_dir: str,
    *,
    default_branch: str,
    fetch: bool = True,
) -> dict[str, LandedFact]:
```

and its docstring states who is entitled to `fetch=False` and why, at
`factory/workgraph/landed.py:147`: "A *reporting* caller must not touch the
network or write a remote-tracking ref to answer a question". The four callers
are `factory/activities/roadmap_activities.py:409`,
`factory/activities/roadmap_activities.py:532`, `factory/cli/status.py:483` and
`factory/workgraph/cli.py:188`. Two of them already pass `fetch=False`, together
with `factory/cli/nouns/build.py:1114`, which reads a head the same way.

**The mechanism that turns blindness into a wrong commit.**
`factory/workgraph/landed.py:360` — `_attesting_commit`:

```python
    for commit, _subject, _body in _git_log_subjects(repo, head):
        frontmatter = _frontmatter_at(repo, commit, spec_dir)
        if frontmatter.get("state") != "landed":
            continue
        try:
            parent = _git(repo, "rev-parse", f"{commit}^").strip()
        except WorktreeError:
            # Root commit: it is the introduction if it attests.
            return commit
```

On a truncated history the graft boundary makes `rev-parse <commit>^` fail, the
`except WorktreeError` at `factory/workgraph/landed.py:375` reads that as "root
commit", and the shallow head is returned as the attesting commit for every story
the spec declares. `factory/workgraph/landed.py:229` is the `if` that admits the
whole fallback.

**Re-reproduced during this refinement, at 602a92c**, with a depth-1 clone of this
repository in scratch. The transcript, pasted verbatim:

```
--- FULL clone (ergane-buildout) ---
US1 observed d5119a8d
US2 observed 8d5102e2
US3 observed 94c8cd87
--- SHALLOW depth-1 clone ---
US1 attested 602a92cf
US2 attested 602a92cf
US3 attested 602a92cf
```

The spec is `126-a-killed-node-leaves-no-ref-to-collide-with`. The source entry
measured the same shape at 238b494, where the shallow head happened to be an
operator commit; at 602a92c it is a node landing for an unrelated spec. Neither is
any of the three real landing commits, which is the point.

**The detection primitive exists in git and nowhere in this tree.**
`git rev-parse --is-shallow-repository` returns `true` on the depth-1 clone and
`false` on this working tree, verified in the same run. `grep -rn 'shallow'
factory/ --include=*.py` returns five hits — `factory/verify/criteria.py:227`,
`factory/verify/gates.py:151`, `factory/verify/gates.py:682`,
`factory/workgraph/prompt.py:664` and `factory/workgraph/adapter.py:513` — every
one of them prose about bind ordering or header nesting. There is no `--depth`
anywhere in `factory/`.

**The degradation the second story must imitate is fifteen lines away from the
one it must replace.** `factory/cli/status.py:378` — `_readiness_basis`:

```python
    branch = landing_branch(repo)
    try:
        head = _landing_head(repo, branch, fetch=False)
    except Exception as error:  # WorktreeError, or a repo with no commits yet
        return (
            ReadinessBasis(
                observed=False,
                detail=f"attestation only — cannot read branch {branch}: {error}",
            ),
            None,
        )

    return (
        ReadinessBasis(
            observed=True,
            detail=(
                f"attestation, plus landings on {branch} ({head[:12]}) in {repo}, "
                "read without fetching"
            ),
        ),
```

The `ReadinessBasis` dataclass is at `factory/cli/status.py:247`; the degraded
arm is `factory/cli/status.py:404-411` and the confident arm — the sentence FR-005
forbids on a truncated history, because it claims landings were read when the
reader could not see them — is `factory/cli/status.py:413-419`. Note that
`factory/cli/status.py:403` succeeds on a shallow clone: resolving a head is not
the operation that goes blind, which is why FR-001 puts the measurement in the
reader and has the basis ask the same helper rather than inferring anything from
this call.

**What the verb does today**, `factory/workgraph/cli.py:168` — `landed_command`:

```python
    try:
        facts = landed_facts(repo, epic_id, default_branch=default_branch)
    except Exception as error:
        raise _OperatorError(
            f"cannot read landed facts for {epic_id}: {error}"
        ) from error
```

No `fetch=` argument, no flag to supply one — `grep -rn 'no-fetch\|no_fetch'
factory/ --include=*.py` is empty — and one user error for every cause. The flag
belongs beside `--json` at `factory/cli/nouns/spec.py:225`, in the subparser built
at `factory/cli/nouns/spec.py:216`, and the handler that wraps it is
`factory/cli/nouns/spec.py:452` — `_landed_command`.

**The output a degraded read must not produce**, `factory/workgraph/cli.py:230-238`:

```python
        for story_key, title in declared:
            if story_key in facts:
                continue
            print()
            print(f"{story_key} has no landing yet. To rescue it by hand, open a PR with:")
            print(f"  title:   {_rescue_pr_title(epic_id, story_key, title)}")
            print(
                f"  trailer: {rescue_trailer(epic_id=epic_id, node_id=story_key.lower(), story_key=story_key)}"
            )
```

with the `--json` counterpart at `factory/workgraph/cli.py:209-221` and the
command's single success return at `factory/workgraph/cli.py:239`.

**The test harness to copy, not to invent.** `tests/test_landed.py:101` —
`repo_builder` builds a real git repository in `tmp_path` with a spec in it;
`tests/test_landed.py:328` — `test_historical_kind_is_distinct_and_rendered`
drives the verb over one with a bare argument class; and
`tests/test_landed.py:587` — `test_unattested_unattributed_spec_yields_empty_baseline`
is the control FR-002 must keep passing — it is the test that asserts `{}` means
"nothing landed", and the reason "return `{}` on a shallow clone" is the wrong
fix rather than the cheap one.

**The bound that is not a bug.** `factory/workgraph/worktree.py:108` is
`GIT_TIMEOUT_S = 300`, applied at `factory/workgraph/worktree.py:1971`. The real
300-second exposure was already fixed: `factory/activities/roadmap_activities.py:511`
— `_drift_from_git` records the 2026-08-26 incident in its own docstring at
`factory/activities/roadmap_activities.py:517-523` and now runs under
`asyncio.to_thread`.

## Traps

**Trap 1 — The shallow read does not merely lose the landing, it pins the wrong
commit, and the obvious fix reproduces the defect in a second form.** FR-002. The
transcript above is the reproduction: three stories ATTESTED at a commit that
landed none of them. The tempting one-line fix is to make the attestation fallback
return `None` on a truncated history, which makes `landed_facts` return `{}` — and
`{}` is exactly what `tests/test_landed.py:587` —
`test_unattested_unattributed_spec_yields_empty_baseline` asserts for a repository
where genuinely nothing landed. A caller cannot tell those apart, so the derivation
path would then compile a full graph and rebuild every landed story instead of
compiling a wrong delta. Wrong answer, different direction. The read must refuse.

**Trap 2 — A shallow fixture built the obvious way is not shallow, and the test
passes green while asserting nothing.** FR-001 and every US1 scenario. Verified in
scratch at 602a92c:

```
$ git clone --depth 1 ./srcrepo plainclone
Cloning into 'plainclone'...
warning: --depth is ignored in local clones; use file:// instead.
done.
plain is-shallow: false
plain commits: 3
$ git clone --depth 1 "file://$PWD/srcrepo" fileclone
file is-shallow: true
file commits: 1
```

A fixture that clones the `repo_builder` repository by plain path gets a complete
clone, the reader behaves exactly as it always did, and the new refusal never
fires — so the test that was supposed to prove the defect proves the opposite and
lands green. The `file://` prefix is load-bearing. Do not silence the warning; do
not use `--shallow-since` instead, which has the same local-clone caveat.

**Trap 3 — The trigger the first key is NAMED for is refuted. Do not inherit it,
and do not build it.** The key reads `landing-read-is-blind-on-the-runner`; its
own ledger note says the trigger does not occur. Every call site runs on the
worker host or the operator's machine; the workflow `ergane init --wire` generates
is built by `factory/mergequeue/wiring.py:143` — `render_gates_workflow`, which
emits `actions/checkout@v4` at `factory/mergequeue/wiring.py:162` and then only
the declared gate commands, and never invokes `ergane` —
`grep -rln 'ergane ' .github/workflows/` is empty. **Do NOT add `fetch-depth: 0`
to that generated workflow.** It fixes nothing here and rewrites the CI of every
repository the factory has ever wired. Note also that the source entry names this
file as bare `wiring.py` with a line range; the repository-relative path, and the
only form an anchor may take, is `factory/mergequeue/wiring.py:143`.

**Trap 4 — Most of the second half already landed. Rebuild none of it.** FR-006
through FR-010 touch exactly one verb. `factory/cli/status.py:403`,
`factory/cli/status.py:483` and `factory/cli/nouns/build.py:1114` already pass
`fetch=False` (046 FR-002, 052), and `factory/cli/status.py:404-411` already
returns a named degradation. The residue is `factory/workgraph/cli.py:188-192`
and nothing else. Equally: the derive paths at `factory/workgraph/cli.py:452`,
`factory/activities/roadmap_activities.py:409` and
`factory/activities/roadmap_activities.py:532` keep `fetch=True`. An implementer
who "makes it consistent" by adding `fetch=False` there has made derivation read a
stale baseline, which is the defect this reader's docstring exists to prevent.

**Trap 5 — `GIT_TIMEOUT_S` is a deliberate bound and this spec does not touch
it.** `factory/workgraph/worktree.py:108`, applied at
`factory/workgraph/worktree.py:1971`. The source finding compared it against a
five-second figure from a different repository; that comparison is a category
error and the triage recorded it as one. The genuine exposure it describes was
fixed on 2026-08-26 and the fix is documented in place at
`factory/activities/roadmap_activities.py:517-523`. Shortening the timeout would
make a large checkout fail for a reason unrelated to anything here.

**Trap 6 — The two exit-code vocabularies disagree by one, and only the RAISE
path is translated.** FR-010. `factory/workgraph/cli.py:69` defines
`EXIT_TRANSPORT = 2`. Under the unified contract, `factory/cli/errors.py:26`
defines `EXIT_TRANSPORT = 3` and `factory/cli/errors.py:25` defines
`EXIT_USAGE = 2`. `factory/cli/nouns/spec.py:107` maps a *raised* old code 2 onto
the new 3, with the comment saying exactly that — but a value the command
*returns* passes through `factory/cli/errors.py:52` — `run_cli` untouched. So the
natural move, "reuse the module's own `EXIT_TRANSPORT` and return it", makes
`ergane spec landed` exit 2, which the unified contract reads as a usage error:
the operator is told they typed something wrong, which is the exact defect this
story is fixing, now expressed as a number instead of a sentence. Assert the code
through the noun's handler, not through `landed_command` alone.

**Trap 7 — Existing callers construct the argument object by hand and will not
carry the new flag.** FR-007. `tests/test_landed.py:350` is literally
`class Args:` with `spec_dir` and `default_branch` and nothing else, and
`factory/workgraph/cli.py:205` already reads `getattr(args, "as_json", False)`
for precisely this reason. An implementer who writes `args.no_fetch` breaks
`tests/test_landed.py:328` — `test_historical_kind_is_distinct_and_rendered` and
`tests/test_landed.py:528` — `test_cli_prints_rescue_title_and_trailer_for_unlanded_stories`
with an `AttributeError`, then reads the red as "my
change is wrong" and starts editing the reader. Use `getattr` with a default.

**Trap 8 — A degraded read that still prints the rescue suggestion is the
expensive form of this defect, not a cosmetic one.** FR-009. The output at
`factory/workgraph/cli.py:230-238` tells the operator, for every story with no
fact, to open a pull request with a given title and a given trailer. On a
truncated history every landed story has no fact. Following that advice opens a
duplicate landing for work that is already on the branch — the read's blindness
converted into a write. The declared stories must still be listed, because
printing nothing is the failure this story is fixing, but they are listed as
unconfirmed and without a rescue line.

**Trap 9 — Raise from `landed_facts` itself, before the scan, and subclass
`WorktreeError`.** FR-003. Two failure modes if you do not.
`factory/workgraph/landed.py:360` — `_attesting_commit` catches `WorktreeError`
around a `rev-parse` at `factory/workgraph/landed.py:375`, so a degradation raised
from a helper called underneath it is swallowed and turns back into "root commit:
it is the introduction". And `factory/cli/status.py:469` — `_observed_landing`
wraps the reader in a bare `except Exception` whose docstring makes the
conservative promise "any doubt is `None`"; a degradation that subclasses
`WorktreeError` keeps that promise, and FR-005 is what makes the omission visible
in the basis sentence instead of silent. Do not widen or narrow that catch.

**Trap 10 — The helper must be asked by both doors, not implemented twice.**
FR-001. `factory/workgraph/landed.py:130` — `landed_facts` and
`factory/cli/status.py:378` — `_readiness_basis` both need the answer, and
`_readiness_basis` cannot get it from the reader because the reader raises rather
than returns. Export one helper from `factory/workgraph/landed.py` and import it
in `factory/cli/status.py` the way `factory/cli/status.py:106` already imports
`_resolve_default_head` under an alias. Two independent `rev-parse` calls with two
different fallbacks on error is how the two doors start disagreeing about the same
repository.

## Sizing

US1 touches `factory/workgraph/landed.py` (one helper, one exception class, one
guard at the top of the reader) and `factory/cli/status.py` (one branch in
`_readiness_basis`). Its tests live in `tests/test_landed.py` beside
`tests/test_landed.py:587` — `test_unattested_unattributed_spec_yields_empty_baseline`,
plus one assertion in the status tests. The shallow fixture is four lines of
`git clone --depth 1 file://…` over the existing `tests/test_landed.py:101` —
`repo_builder` repository.

US2 touches `factory/workgraph/cli.py` (the flag, the degradation, the report) and
`factory/cli/nouns/spec.py` (one `add_argument`). Its tests live in
`tests/test_landed.py` and one assertion through the noun handler for the exit
code.

The two stories name no production file in common: `factory/workgraph/landed.py`
and `factory/cli/status.py` against `factory/workgraph/cli.py` and
`factory/cli/nouns/spec.py`. They share the test module `tests/test_landed.py`,
which is a merge-order matter and not a contention edge; the
`depends_on_merged` edge already sequences them.

Both stories are well inside the 64 KiB deterministic diff bound (D-050): US1 is
under sixty production lines plus one test file's worth of additions, US2 under
fifty plus the same, and each verification task asks for two short pasted
transcripts rather than a session log.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only, so
runtime evidence is committed as pasted output. Beyond that:

1. Clone this repository into scratch with `git clone --depth 1 --branch
   ergane-buildout file:///home/admin/code/ergane shallow`, confirm
   `git -C shallow rev-parse --is-shallow-repository` prints `true`, and read
   `126-a-killed-node-leaves-no-ref-to-collide-with` through the reader. Before
   the change it returns three ATTESTED facts at the shallow head; after, it must
   refuse by name.
2. Read the same spec from the full working tree. It must return US1, US2 and US3
   OBSERVED at d5119a8, 8d5102e and 94c8cd8 — unchanged, byte for byte, from
   before the change. This is the control that FR-004 held.
3. Run `ergane spec landed specs/126-a-killed-node-leaves-no-ref-to-collide-with
   --default-branch ergane-buildout` against the shallow clone. It must name the
   degradation, list the three stories as unconfirmed, print no rescue title or
   trailer, and exit 3. Check the exit code with `echo $?`, not by reading the
   prose.
4. Run the same command with `--no-fetch` against the full working tree with the
   network unavailable, and confirm it answers. Then run it without the flag and
   confirm it still fetches.
5. Run `ergane status` with the specs root inside the shallow clone and confirm the
   readiness basis sentence names the incomplete history rather than claiming it
   read landings on the branch.

Step 1 paired with step 2 is the falsifiable test of the whole spec: the same
question, asked of two clones of one repository, must now give one right answer
and one honest refusal instead of two confident answers of which one is false.
