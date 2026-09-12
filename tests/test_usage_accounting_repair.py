"""Regression coverage for missing request logs and runner usage attribution."""
import json
from dataclasses import replace
from pathlib import Path

import pytest

from factory.activities import usage_activities as activities
from factory.usage import ledger
from factory.usage.litellm_client import LiteLLMError
from factory.usage.models import KeyLease, Termination
from tests.test_ledger_schema import make_record


@pytest.fixture
def lease():
    return KeyLease('sk-test', 'epic:node:1:implementer', 'node', 'epic', 1,
                    'implementer', 'spec', '2026-09-10T00:00:00Z')


class Proxy:
    def __init__(self, rows, spend=1.0):
        self.rows = iter(rows)
        self.spend = spend
        self.last = []

    async def get_spend(self, key):
        return self.spend

    async def fetch_spend_log_rows(self, key, *, issued_at):
        self.last = next(self.rows, self.last)
        if isinstance(self.last, Exception):
            raise self.last
        return self.last


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(activities, 'FINAL_READ_DELAYS', (0, 0), raising=False)


@pytest.mark.asyncio
async def test_missing_request_logs_preserve_cost_and_are_not_confirmed(lease):
    reading = await activities._read_final_usage(Proxy([[]]), lease)
    record = activities._record_for(activities.TeardownInput(lease, Termination.COMPLETED), reading)
    assert record.spend_usd == 1.0
    assert record.prompt_tokens is None
    assert not record.final_usage_confirmed
    assert record.usage_status == 'unknown'


@pytest.mark.asyncio
async def test_partial_logs_are_measured_but_not_complete(lease):
    reading = await activities._read_final_usage(Proxy([[{'prompt_tokens': 100, 'completion_tokens': 10, 'spend': 0.1}]]), lease)
    record = activities._record_for(activities.TeardownInput(lease, Termination.COMPLETED), reading)
    assert record.prompt_tokens == 100
    assert record.spend_usd == 1.0
    assert record.usage_status == 'partial'
    assert not record.final_usage_confirmed


@pytest.mark.asyncio
async def test_delayed_logs_recover_without_double_counting(lease):
    row = {'request_id': 'a', 'prompt_tokens': 100, 'completion_tokens': 10, 'spend': 1.0}
    reading = await activities._read_final_usage(Proxy([[], [row], [row]]), lease)
    record = activities._record_for(activities.TeardownInput(lease, Termination.COMPLETED), reading)
    assert record.prompt_tokens == 100
    assert record.request_count == 1
    assert record.final_usage_confirmed


@pytest.mark.asyncio
async def test_failed_log_read_keeps_fresh_key_spend(lease):
    reading = await activities._read_final_usage(Proxy([LiteLLMError('offline')]), lease)
    record = activities._record_for(activities.TeardownInput(lease, Termination.COMPLETED), reading)
    assert record.spend_usd == 1.0
    assert not record.final_usage_confirmed


def test_teardown_retry_cannot_erase_confirmed_measurement(tmp_path):
    with ledger.connect(tmp_path/'ledger.db') as db:
        original = ledger.upsert_record(db, make_record(usage_source='gateway', usage_status='complete'))
        retried = ledger.upsert_record(db, replace(original, prompt_tokens=None, completion_tokens=None,
                                                   spend_usd=None, final_usage_confirmed=False, usage_status='unknown'))
        assert retried.prompt_tokens == original.prompt_tokens
        assert retried.spend_usd == original.spend_usd
        assert retried.final_usage_confirmed


def test_mixed_coverage_reports_subtotals_without_complete_total(tmp_path):
    with ledger.connect(tmp_path/'ledger.db') as db:
        ledger.upsert_record(db, make_record(usage_source='gateway', usage_status='complete'))
        ledger.upsert_record(db, make_record(key_alias='other', prompt_tokens=None, completion_tokens=None,
                                             final_usage_confirmed=False, usage_status='unknown'))
        report = ledger.rollup(db, by='epic')
        assert report['totals']['prompt_tokens'] is None
        assert report['coverage']['totals']['measured_prompt_tokens'] == 1200
        assert report['coverage']['totals']['missing_usage_rows'] == 1


def test_claude_repeated_message_blocks_are_counted_once():
    from factory.usage.runner import parse_claude
    def event(identity, output):
        return {'type':'assistant', 'message':{'id':identity, 'usage':{
            'input_tokens':100,'output_tokens':output,'cache_read_input_tokens':20,'cache_creation_input_tokens':0}}}
    usage = parse_claude([event('a', 1),event('a', 10),event('b', 5)])
    assert (usage.prompt_tokens, usage.completion_tokens, usage.request_count) == (240,15,2)
    assert usage.cache_read_tokens == 40


def test_codex_cumulative_counts_and_previous_session_baseline():
    from factory.usage.runner import parse_codex
    def event(time, prompt, output):
        return {'timestamp':time,'type':'event_msg','payload':{'type':'token_count','info':{'total_token_usage':{
            'input_tokens':prompt,'output_tokens':output,'cached_input_tokens':0}}}}
    usage = parse_codex([event('2026-09-09T12:00:00Z',100,10),
                         event('2026-09-10T12:00:00Z',150,20),
                         event('2026-09-10T12:00:01Z',150,20),
                         event('2026-09-10T12:00:02Z',200,30)], since='2026-09-10T00:00:00Z')
    assert (usage.prompt_tokens,usage.completion_tokens) == (100,20)
    assert usage.cache_write_tokens is None
    assert usage.request_count is None  # cumulative events do not prove request count


def test_additive_migration_preserves_old_rows_and_readonly_reporting(tmp_path):
    import sqlite3
    from factory.usage.cli import open_readonly
    path = tmp_path/'old.db'
    db = sqlite3.connect(path)
    old_ddl = ledger._SCHEMA_DDL
    old_ddl = old_ddl.replace("    torn_down_at           TEXT    NOT NULL,", "    torn_down_at           TEXT    NOT NULL")
    old_ddl = '\n'.join(line for line in old_ddl.splitlines() if not any(name in line for name in ('usage_source ', 'usage_status ', 'cost_basis ')))
    db.executescript(old_ddl)
    db.execute('INSERT INTO schema_version VALUES (2)')
    db.close()
    with open_readonly(path) as before:
        assert ledger.rollup(before, by='epic')['coverage']['totals']['missing_usage_rows'] == 0
        assert 'usage_source' not in {r[1] for r in before.execute('PRAGMA table_info(usage_records)')}
    with ledger.connect(path) as after:
        assert after.execute('SELECT version FROM schema_version').fetchone()[0] == 4
        assert {'usage_source','usage_status','cost_basis'} <= {r[1] for r in after.execute('PRAGMA table_info(usage_records)')}


def context(**overrides):
    from types import SimpleNamespace
    return SimpleNamespace(**{'epic_id':'epic','node_id':'node','attempt':1,'session_id':'session-1',
                               'agent':'claude-code','route':'subscription',**overrides})


def write_events(path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(event)+'\n' for event in events))


def claude_event():
    return {'type':'assistant','message':{'id':'m1','usage':{
        'input_tokens':100,'output_tokens':10,'cache_creation_input_tokens':20,'cache_read_input_tokens':30}}}


@pytest.mark.asyncio
async def test_subscription_archive_to_teardown_never_contacts_proxy(tmp_path, lease, monkeypatch):
    from factory.usage.runner import archive_execution_usage
    archive = tmp_path/'transcripts/epic/node/attempt-1'
    write_events(archive/'session-1.jsonl', [claude_event(),claude_event()])
    archive_execution_usage(tmp_path, context(), '2026-09-10T12:00:00Z', True)
    monkeypatch.setattr('factory.activities.agent_activities.factory_root', lambda: tmp_path)
    monkeypatch.setattr(activities, '_ledger_path', lambda: tmp_path/'ledger.db')
    def forbidden():
        pytest.fail('subscription teardown must not open a proxy client')
    monkeypatch.setattr(activities, 'open_client', forbidden)
    record = await activities.teardown_attempt(activities.TeardownInput(replace(lease,key=''),Termination.COMPLETED))
    assert (record.prompt_tokens,record.completion_tokens,record.request_count)==(150,10,1)
    assert record.spend_usd is None
    assert record.cost_basis == 'unknown'
    assert record.usage_source == 'claude-code'
    assert record.usage_status == 'complete'
    assert record.final_usage_confirmed


def test_interrupted_or_truncated_subscription_is_partial(tmp_path, lease):
    from factory.usage.runner import archive_execution_usage, read_attempt_usage
    path = tmp_path/'transcripts/epic/node/attempt-1/session-1.jsonl'
    write_events(path,[claude_event()])
    path.write_text(path.read_text()+'{"truncated":')
    archive_execution_usage(tmp_path, context(), '2026-09-10T12:00:00Z', True)
    usage = read_attempt_usage(tmp_path, replace(lease,key=''))
    assert usage.status == 'partial'
    assert usage.aggregate.prompt_tokens == 150


def test_gateway_events_do_not_create_subscription_usage(tmp_path):
    from factory.usage.runner import archive_execution_usage
    path = tmp_path/'transcripts/epic/node/attempt-1/session-1.jsonl'
    write_events(path,[claude_event()])
    archive_execution_usage(tmp_path, context(route='gateway'), '2026-09-10T12:00:00Z', True)
    assert not list(path.parent.glob('usage-*.json'))


def test_old_execution_manifests_are_not_reused_for_reissued_alias(tmp_path, lease):
    from factory.usage.runner import archive_execution_usage, read_attempt_usage
    path = tmp_path/'transcripts/epic/node/attempt-1/session-1.jsonl'
    write_events(path,[claude_event()])
    archive_execution_usage(tmp_path, context(), '2026-09-09T12:00:00Z', True)
    assert read_attempt_usage(tmp_path, replace(lease,key='')) is None


def test_codex_old_rollout_does_not_leak_into_new_execution(tmp_path, lease):
    from factory.usage.runner import archive_execution_usage, read_attempt_usage
    archive = tmp_path/'transcripts/epic/node/attempt-1'
    def event(when, count):
        return {'timestamp':when,'type':'event_msg','payload':{'type':'token_count','info':{'total_token_usage':{
            'input_tokens':count,'output_tokens':count//10,'cached_input_tokens':0}}}}
    write_events(archive/'rollout-old.jsonl',[event('2026-09-09T00:00:00Z',10000)])
    write_events(archive/'rollout-current.jsonl',[event('2026-09-10T13:00:00Z',100),event('2026-09-10T13:01:00Z',200)])
    archive_execution_usage(tmp_path,context(agent='codex'), '2026-09-10T12:00:00Z',True)
    measured=read_attempt_usage(tmp_path,replace(lease,key=''))
    assert measured.aggregate.prompt_tokens == 200
    assert measured.aggregate.completion_tokens == 20
    assert measured.aggregate.request_count is None


@pytest.mark.asyncio
async def test_free_model_requires_usable_tokens_and_stable_reads(lease):
    rows = [{'request_id':'a','spend':0.0,'prompt_tokens':123,'completion_tokens':5}]
    reading=await activities._read_final_usage(Proxy([rows],spend=0.0),lease)
    assert reading.status=='complete'
    rows = [{'request_id':'a','spend':0.0}]
    reading=await activities._read_final_usage(Proxy([rows],spend=0.0),lease)
    assert reading.status=='unknown'


def test_reconciliation_is_readonly_and_requires_mapping_and_matching_cost(tmp_path):
    from factory.usage.reconcile import preview
    path=tmp_path/'ledger.db'
    with ledger.connect(path) as db:
        ledger.upsert_record(db,make_record(prompt_tokens=None,completion_tokens=None,request_count=None))
    candidate={'key_alias':'epic-7:node-3:2','mapping_key_count':1,'mapping_alias_count':1,
               'first_request_at':'2026-07-24T10:01:00Z','last_request_at':'2026-07-24T10:30:00Z',
               'prompt_tokens':1200,'completion_tokens':340,'request_count':7,'spend_usd':0.4212}
    before=path.read_bytes()
    assert preview(path,[candidate])['candidate_count']==1
    assert path.read_bytes()==before
    assert preview(path,[{**candidate,'mapping_key_count':2}])['candidate_count']==0
    assert preview(path,[{**candidate,'spend_usd':123}])['candidate_count']==0


@pytest.mark.asyncio
async def test_agent_activity_archives_subscription_usage_on_completion(tmp_path, monkeypatch):
    from factory.activities.agent_activities import run_agent_attempt
    from factory.workgraph.models import AdapterResult, AttemptContext
    from factory.usage.runner import read_attempt_usage
    ctx=AttemptContext(epic_id='epic',node_id='node',attempt=1,prompt='fixture',worktree_path=str(tmp_path),
                       home_path=str(tmp_path/'home'),proxy_url='',virtual_key='',model_alias='fixture',
                       session_id='session-1',timeout_s=10,agent='claude-code',route='subscription')
    class Runner:
        async def run_attempt(self, dispatched, **kwargs):
            path=tmp_path/'transcripts/epic/node/attempt-1'/f'{dispatched.session_id}.jsonl'
            write_events(path,[claude_event()])
            return AdapterResult(Termination.COMPLETED,transcript_path=str(path.parent))
        def _refusal_markers(self):
            return ()
    monkeypatch.setattr('factory.activities.agent_activities.factory_root',lambda:tmp_path)
    monkeypatch.setattr('factory.activities.agent_activities.adapter_for',lambda _:Runner())
    result=await run_agent_attempt(ctx)
    assert result.termination==Termination.COMPLETED
    lease=KeyLease('', 'epic:node:1:implementer', 'node','epic',1,'implementer','spec','2020-01-01T00:00:00Z')
    measured=read_attempt_usage(tmp_path,lease)
    assert measured.aggregate.prompt_tokens==150
    assert measured.status=='complete'


@pytest.mark.asyncio
async def test_agent_activity_archives_partial_usage_on_cancellation(tmp_path, monkeypatch):
    import asyncio
    from temporalio.exceptions import CancelledError
    from factory.activities.agent_activities import run_agent_attempt
    from factory.workgraph.models import AttemptContext
    from factory.usage.runner import read_attempt_usage
    ctx=AttemptContext(epic_id='epic',node_id='node',attempt=1,prompt='fixture',worktree_path=str(tmp_path),
                       home_path=str(tmp_path/'home'),proxy_url='',virtual_key='',model_alias='fixture',
                       session_id='session-1',timeout_s=10,agent='claude-code',route='subscription')
    class Runner:
        async def run_attempt(self, dispatched, **kwargs):
            write_events(tmp_path/'transcripts/epic/node/attempt-1'/f'{dispatched.session_id}.jsonl',[claude_event()])
            raise asyncio.CancelledError()
    monkeypatch.setattr('factory.activities.agent_activities.factory_root',lambda:tmp_path)
    monkeypatch.setattr('factory.activities.agent_activities.adapter_for',lambda _:Runner())
    with pytest.raises(CancelledError):
        await run_agent_attempt(ctx)
    lease=KeyLease('', 'epic:node:1:implementer','node','epic',1,'implementer','spec','2020-01-01T00:00:00Z')
    measured=read_attempt_usage(tmp_path,lease)
    assert measured.aggregate.prompt_tokens==150
    assert measured.status=='partial'


@pytest.mark.asyncio
async def test_retry_with_less_detail_keeps_the_measured_partial_snapshot(lease):
    partial = [{'request_id':'a','prompt_tokens':100,'completion_tokens':10,'spend':0.1}]
    unreadable = [{'request_id':'a','spend':0.1}]
    reading = await activities._read_final_usage(Proxy([partial, unreadable]),lease)
    assert reading.aggregate.prompt_tokens==100
    assert reading.status=='partial'


def test_missing_message_usage_keeps_known_subtotal_but_marks_partial(tmp_path, lease):
    from factory.usage.runner import archive_execution_usage, read_attempt_usage
    path=tmp_path/'transcripts/epic/node/attempt-1/session-1.jsonl'
    write_events(path,[claude_event(),{'type':'assistant','message':{'id':'m2'}}])
    archive_execution_usage(tmp_path,context(),'2026-09-10T12:00:00Z',True)
    measured=read_attempt_usage(tmp_path,replace(lease,key=''))
    assert measured.status=='partial'
    assert measured.aggregate.prompt_tokens==150


def test_malformed_codex_timestamp_does_not_fail_the_finished_attempt(tmp_path, lease):
    from factory.usage.runner import archive_execution_usage, read_attempt_usage
    path=tmp_path/'transcripts/epic/node/attempt-1/rollout-current.jsonl'
    def event(timestamp):
        return {'timestamp':timestamp,'type':'event_msg','payload':{'type':'token_count','info':{
            'total_token_usage':{'input_tokens':100,'output_tokens':10}}}}
    write_events(path,[event('2026-09-10T13:00:00Z'),event(None)])
    archive_execution_usage(tmp_path,context(agent='codex'),'2026-09-10T12:00:00Z',True)
    measured=read_attempt_usage(tmp_path,replace(lease,key=''))
    assert measured.status=='partial'
    assert measured.aggregate.prompt_tokens==100
