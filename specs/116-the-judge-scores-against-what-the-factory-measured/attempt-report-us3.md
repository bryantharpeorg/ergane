# Attempt report — US3, the record says what the judge was shown

Evidence that no gate can produce, committed as an artifact the diff contains
(constitution VIII). Tool output is pasted, not described.

## T027 — FR-009: the three things this epic may not change

FR-009 names `judge_required` (`factory/verify/models.py`), `prepare_diff` and
the gate implementations. Paths are named here because FR-009 names them and
this is a report, not a task; no task in this slice edits them.

```
$ git diff f0d2a14 --stat -- factory/verify/gates.py
                                     # (no output: the file is not in the diff)
$ git rev-parse f0d2a14:factory/verify/gates.py
81e6921619045ed3d2a22e8041144f1d701f5a6d
$ git hash-object factory/verify/gates.py
81e6921619045ed3d2a22e8041144f1d701f5a6d

$ git diff f0d2a14 -- factory/verify/judge.py | grep -n prepare_diff
                                     # (no output: no hunk touches it)
$ git diff f0d2a14 -- factory/verify/models.py | grep -nE '^[-+].*judge_required'
                                     # (no output: no hunk touches it)
```

Identical blob for the gate implementations, and no hunk in this epic's whole
diff — US1's and US2's included — names either function. `judge_required` still
reads exactly as it did, which matters beyond bookkeeping: US1's argument that
a gate section is never misleading on the judged path rests on it returning
True only when `gates_passed` does.

```python
def judge_required(
    gate_results: Sequence[GateResult],
    output_check: OutputCheck,
    criteria: CriteriaSet,
) -> bool:
    ...
    return (
        gates_passed(gate_results)
        and output_check.passed
        and has_scenarios(criteria)
    )
```

## T028 — the paired demonstration: what ran, and what did not

**The live half did not run, and could not be run from this node.** The plan's
§ *Verification the operator will run* is explicit that it needs a real model
scoring a real unscoreable scenario. Reaching one needs a proxy URL and a judge
virtual key, and a dispatched node's environment carries neither by
construction — constitution V puts the proxy master key in the worker host
environment only, and `scripts/ergane-env.sh` refuses here anyway:

```
$ bash scripts/ergane-env.sh
ERROR: sops not on PATH
$ env | grep -icE 'litellm|anthropic|proxy'
0
```

There is no question to ferry to the operator about this: the answer would have
to be a credential, and a credential is the one thing that may not enter a node.
So the demonstration is left for the operator with its deterministic half done
and its live half stated as missing, rather than reported as passed.

### The half that did run: what actually differs between the two asks

A scenario whose Then-clause names a runtime outcome (`Then the test gate
passes`), one two-line diff that cannot contain a test run, and the same
`build_prompt` called twice:

```
$ uv run python /tmp/us3_demo.py
gates_shown without = False | with = True
user message bytes: without = 682  with = 1137

--- the section the with-gates prompt adds, verbatim ---
# Gate results measured by this factory

These are this factory's own deterministic measurements of the attempt you are
scoring: the commands it ran over the node's work after the diff below was
produced, and the result it recorded for each. A scenario whose Then-clause
names one of these outcomes is scored against the result recorded here, not
against what you predict the command would do.

## test — PASS (exit code: 0)

command: uv run pytest -q
--- end section ---
```

and the clause US1 put in `SYSTEM_PROMPT`, which is the half of the change that
makes the section usable rather than merely present (plan trap 1):

```
... if the evidence is in neither the diff nor the gate results, the scenario
does not pass. Never pass a scenario because the change looks reasonable
overall.
The gate results are evidence, not background. They are this factory's own
measurement of this same attempt, taken by running the commands after the diff
was produced, and they are what a scenario naming a runtime outcome is scored
against: when a scenario's Then-clause names a gate outcome — that the suite
passes, that the types check, that the lint is clean — score it against the
result recorded for that gate, and never against what you predict that gate
would do. A diff cannot contain a test run, so demanding one inside the patch
fails work that is correct and asks the agent to pad its diff to satisfy you.
This widens the evidence to the named measurements you were given and to
nothing else.
```

`gates_shown` reads `True` and `False` off those two assemblies, which is the
fact US3 carries onto the row — measured from the assembled section, not from
the argument, so it cannot keep claiming a section the prompt stopped emitting.

### What the operator still has to run

With `eval "$(scripts/ergane-env.sh)"` in a shell that has `sops`, and the judge
persona's alias and a minted virtual key in `ERGANE_JUDGE_MODEL_ALIAS` /
`ERGANE_JUDGE_VIRTUAL_KEY`, the same script scores that scenario twice against
the live judge and prints both verdicts. The demonstration succeeds when the
with-gates run passes `US1-S1` and the without-gates run fails it. That pair is
the whole argument of the spec, and it is the one claim in this report that is
**not** evidenced.
