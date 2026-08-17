# US1 evidence: the tests red before the implementation, and the mutation battery

Constitution VIII / D-037: the judge is given this diff and the criteria, never
a terminal. Every block below is tool output pasted verbatim, produced by the
command shown above it.

## 1. The tests, watched failing before `factory/cli/init.py` was touched

A test that has never been observed to fail is not evidence. This is the run at
`3e9cbde` with `tests/test_init_schedule_precondition.py` written and no
production change made yet.

```
$ PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/test_init_schedule_precondition.py --tb=line -q
FFF..F..                                                                 [100%]
=================================== FAILURES ===================================
E   AssertionError: a schedule was published: ['ergane-roadmap-widgets']
    assert {'ergane-road...g_actions=0))} == {}

      Left contains 1 more item:
      {'ergane-roadmap-widgets': Schedule(action=ScheduleActionStartWorkflow(workflow='RoadmapWorkflow',
                                                                             args=[metadata {
        key: "encoding"
        value: "json/plain"
      }...
tests/test_init_schedule_precondition.py:187: AssertionError: a schedule was published: ['ergane-roadmap-widgets']
E   AssertionError: schedule: created ergane-roadmap-widgets — created, starting
    roadmap-specs every 300s over .../widgets/specs (note: LITELLM_PROXY_URL is
    unset, so child epics cannot issue keys)
tests/test_init_schedule_precondition.py:214: AssertionError
E   assert False
     +  where False = 'schedule: created ergane-roadmap-refused — created, ...'.startswith(
            'schedule: failed ergane-roadmap-refused')
tests/test_init_schedule_precondition.py:248: assert False
E   AssertionError: schedule: created ergane-roadmap-widgets — created, starting
    roadmap-specs every 300s over .../widgets/specs (note: LITELLM_PROXY_URL is
    unset, so child epics cannot issue keys)
tests/test_init_schedule_precondition.py:348: AssertionError
=========================== short test summary item ============================
FAILED tests/test_init_schedule_precondition.py::test_no_schedule_is_created_when_the_control_plane_cannot_be_read
FAILED tests/test_init_schedule_precondition.py::test_the_refusal_names_the_control_plane_the_remedy_and_the_namespace
FAILED tests/test_init_schedule_precondition.py::test_the_refusal_costs_the_repository_none_of_its_local_scaffold
FAILED tests/test_init_schedule_precondition.py::test_a_control_plane_config_that_will_not_parse_fails_the_step_without_raising
4 failed, 4 passed in 0.44s
```

Read the four passes as carefully as the four failures. They are the tests that
describe behaviour this story must **preserve** rather than introduce — a
readable control plane still creating the schedule and reporting the same line
(US1-S3), an unreachable one still failing the step instead of raising (US1-S5),
the anti-vacuity guard, and FR-010's no-opt-out check. A story satisfied by
deleting the schedule step would have turned those red instead, which is exactly
why US1-S3 is a scenario.

Eight items collected, not "the tests I named" — a mistyped node id collects
nothing and reports success.
