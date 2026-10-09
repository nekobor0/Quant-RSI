"""Controlled HTTP envelope, process contrasts and read-only replay regressions."""
import copy
import urllib.request
from unittest.mock import patch

import pytest

from quant_rsi.harness import agent_workflow as base
from quant_rsi.harness import workflow_v02 as wf
from quant_rsi.harness.workflow_chat import ChatWorkflowAdapter, MockChatTransport, SYSTEM_PROMPT
from quant_rsi.harness.workflow_tools import FixtureTools
from quant_rsi.ledger.store import TraceStore


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **k: pytest.fail('NETWORK FORBIDDEN'))


def run(tmp_path, case='WFA-01-anomaly', profile='correct', fault=None, usage_style='details'):
    store = TraceStore(tmp_path / 'trace.sqlite')
    transport = MockChatTransport(profile, fault=fault, usage_style=usage_style)
    adapter = ChatWorkflowAdapter(transport)
    result = wf.run_workflow(store, case, adapter, 'RUN-v02-test')
    base.save(tmp_path / 'result.json', result)
    return store, result, transport


@pytest.mark.parametrize('case', base.read(base.PACK / 'cases.json'))
@pytest.mark.parametrize('profile', ['correct', 'wrong_final'])
def test_mock_http_multiturn_and_frozen_replay(tmp_path, monkeypatch, case, profile):
    store, result, transport = run(tmp_path, case, profile)
    assert result['status'] == 'COMPLETED'
    assert result['evaluation']['workflow_pass'] == (profile == 'correct')
    assert result['evaluation']['trace_integrity']
    assert result['evaluation']['vector']['BUDGET_COMPLIANT']
    requests = [e['payload'] for e in store.read() if e['kind'] == 'V02_CHAT_REQUEST']
    actions = [e['payload'] for e in store.read() if e['kind'] == 'V02_CHAT_ACTION']
    assert requests[1]['context']['observations']
    assert requests[0]['request']['input_hashes']['context'] != requests[1]['request']['input_hashes']['context']
    assert actions[0]['exchange']['messages'][0]['content'] == SYSTEM_PROMPT
    assert actions[1]['exchange']['messages'][-1]['role'] == 'user'
    assert 'untrusted_tool_observation' in actions[1]['exchange']['messages'][-1]['content']
    assert all(a['reply']['reasoning_tokens'] == 40 for a in actions)
    assert result['usage']['usage']['output_tokens'] == 160 * transport.calls  # not 200
    assert result['usage']['usage']['input_tokens'] > 0
    events, anchor = store.read(), store.checkpoint()
    monkeypatch.setattr(FixtureTools, 'execute', lambda *a: pytest.fail('REEXECUTED TOOL'))
    monkeypatch.setattr(ChatWorkflowAdapter, 'step', lambda *a: pytest.fail('REEXECUTED CHAT'))
    assert wf.replay(events, result, expected_anchor=anchor)['model_calls'] == 0
    assert store.read() == events


def test_controlled_counterfactual_same_initial_prompt_changes_next_action(tmp_path):
    yes, y, _ = run(tmp_path / 'yes', 'WFA-02-available')
    no, n, _ = run(tmp_path / 'no', 'WFA-02-unavailable')
    def requests(store):
        return [e['payload'] for e in store.read() if e['kind'] == 'V02_CHAT_REQUEST']
    yr, nr = requests(yes), requests(no)
    assert yr[0]['context'] == nr[0]['context']
    assert yr[0]['request']['prompt_hash'] == nr[0]['request']['prompt_hash']
    assert yr[1]['request']['prompt_hash'] != nr[1]['request']['prompt_hash']
    def actions(store):
        return [e['payload']['action'] for e in store.read() if e['kind'] == 'V02_CHAT_ACTION']
    ya, na = actions(yes), actions(no)
    assert ya[0] == na[0]
    assert ya[1]['arguments']['vintage_ids'] != na[1]['arguments']['vintage_ids']
    assert ya[2]['arguments']['vintage_id'] == 'v1'
    assert na[2]['arguments']['vintage_id'] == 'v2'
    assert y['final']['conclusion']['verdict'] == 'SELECT_VINTAGE'
    assert n['final']['conclusion']['verdict'] == 'REFUSE'


@pytest.mark.parametrize('profile,dimension,tag', [
    ('illegal_tool', 'TOOL_SELECTION_VALID', 'ILLEGAL_TOOL_OR_ARGUMENT'),
    ('wrong_argument', 'TOOL_SELECTION_VALID', 'ILLEGAL_TOOL_OR_ARGUMENT'),
    ('early_final', 'STATE_TRANSITION_VALID', 'FINAL_WITHOUT_REQUIRED_OBSERVATIONS'),
    ('wrong_reference', 'EVIDENCE_TRACE_COMPLETE', 'INVALID_OBSERVATION_REFERENCE'),
    ('future_claim', 'FINAL_DECISION_CORRECT', 'FUTURE_OR_INELIGIBLE_VINTAGE_CLAIM'),
    ('exhausted_trial', 'BUDGET_COMPLIANT', 'BUDGET_VIOLATION_OR_UNRESOLVED_USAGE'),
    ('tool_failure_claim', 'STATE_TRANSITION_VALID', 'FINAL_AFTER_UNRESOLVED_TOOL_FAILURE'),
])
def test_process_errors_are_differentiated_not_all_zero(tmp_path, profile, dimension, tag):
    case = wf.PROCESS_PROFILES.get(profile, 'WFA-01-anomaly')
    store, result, _ = run(tmp_path, case, profile)
    evaluation = result['evaluation']
    assert not evaluation['workflow_pass']
    assert evaluation['vector'][dimension] is False
    assert any(v is True for v in evaluation['vector'].values())
    assert tag in evaluation['diagnostics']
    assert wf.replay(store.read(), result, expected_anchor=store.checkpoint())['tool_calls'] == 0
    if profile == 'future_claim':
        assert evaluation['vector']['TOOL_SELECTION_VALID'] is True
        # Correct tools ran; only the final claim asserts an unavailable vintage.
        assert evaluation['hard_gates']['actual_required_tools']
    if profile == 'tool_failure_claim':
        assert result['final'] and not evaluation['hard_gates']['execution_completed']


@pytest.mark.parametrize('profile,case,tag', [
    ('redundant', 'WFA-01-anomaly', 'REDUNDANT_LEGAL_TOOL_CALL'),
    ('suboptimal', 'WFA-02-available', 'LEGAL_REJECTED_VINTAGE_AUDIT')])
def test_legal_extra_tools_are_not_illegal_actions(tmp_path, profile, case, tag):
    _, result, _ = run(tmp_path, case, profile)
    assert result['evaluation']['workflow_pass']
    assert tag in result['evaluation']['diagnostics']


@pytest.mark.parametrize('fault,expected', [
    ('http', 'HTTP_ERROR'), ('timeout', 'TASK_TIMEOUT'), ('business', 'BUSINESS_ERROR'),
    ('empty', 'EMPTY_CONTENT'), ('truncated', 'TOKEN_BUDGET_EXHAUSTED'),
    ('json', 'ACTION_JSON_INVALID'), ('action', 'ACTION_SCHEMA_INVALID'),
    ('usage_missing', 'USAGE_UNKNOWN_OR_INVALID'), ('negative_usage', 'USAGE_UNKNOWN_OR_INVALID'),
    ('usage_breach', 'CHAT_USAGE_BREACH')])
def test_failures_have_separate_classes_and_no_retry(tmp_path, fault, expected):
    store, result, transport = run(tmp_path, fault=fault)
    assert result['error'] == expected
    assert transport.calls == 1 and result['tool_calls'] == 0
    assert result['evaluation']['vector']['FINAL_DECISION_CORRECT'] is None
    assert result['evaluation']['failure_class'] != 'WRONG_RESEARCH_CONCLUSION'
    assert wf.replay(store.read(), result, expected_anchor=store.checkpoint())['model_calls'] == 0
    if fault in ('http', 'timeout', 'business', 'usage_missing', 'negative_usage'):
        assert result['usage']['blocked']
        # Unknown actuals retain the entire reserved amount, never a fake zero.
        assert result['usage']['usage']['input_tokens'] == wf.suite()[0]['tokens']['request_input']


def test_native_reasoning_usage_field_is_supported(tmp_path):
    _, result, _ = run(tmp_path, usage_style='native')
    assert result['evaluation']['workflow_pass']


def test_budget_root_cannot_be_reset_by_rename_or_continuation_text(tmp_path):
    store, result, transport = run(tmp_path)
    with pytest.raises(ValueError, match='rename cannot reset'):
        wf.run_workflow(store, 'WFA-01-anomaly', ChatWorkflowAdapter(transport), 'RENAMED')
    assert result['usage']['usage']['candidate_trials'] == 0
    assert any(e['kind'] == 'WORKFLOW_RENAME_DENIED' for e in store.read())


def test_cumulative_token_denial_and_tool_cap(tmp_path, monkeypatch):
    original = wf.suite
    def limited():
        freeze, cases, contract = original()
        cases['WFA-01-anomaly']['ledger_task']['budget_limits']['input_tokens'] = 32768
        return freeze, cases, contract
    monkeypatch.setattr(wf, 'suite', limited)
    _, result, transport = run(tmp_path)
    assert transport.calls == 1  # reservation for round two cannot fit remaining budget
    assert result['error'] == 'CHAT_BUDGET_DENIED'
    monkeypatch.setattr(wf, 'suite', original)
    with patch.object(MockChatTransport, 'decide', lambda s, c:
            {'action': 'TOOL_CALL', 'tool': 'read_fixture', 'arguments': {'fixture_id': 'response'}}):
        _, result, transport = run(tmp_path / 'toolcap')
    assert result['tool_calls'] == 6 and transport.calls == 7
    assert result['error'] == 'TOOL_BUDGET_DENIED'


def test_trace_tampering_fails_and_append_only_store(tmp_path):
    store, result, _ = run(tmp_path)
    events = store.read()
    damaged = copy.deepcopy(events)
    obs = next(e for e in damaged if e['kind'] == 'WORKFLOW_TOOL_RESULT')
    obs['payload']['result']['count'] = 99
    with pytest.raises(ValueError):
        wf.replay(damaged, result, expected_anchor=store.checkpoint())
    import sqlite3
    with sqlite3.connect(tmp_path / 'trace.sqlite') as conn:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute('DELETE FROM events')


def test_adapter_never_accepts_real_transport_or_reads_credentials(monkeypatch):
    with pytest.raises(ValueError, match='OFFLINE'):
        ChatWorkflowAdapter(lambda *a: None)
    monkeypatch.setattr('os.environ.get', lambda *a: pytest.fail('CREDENTIAL READ'))
    adapter = ChatWorkflowAdapter(MockChatTransport())
    assert adapter.client._resolve_key() == 'synthetic-placeholder'


@pytest.mark.parametrize('exc', [RuntimeError('controlled failure'), KeyboardInterrupt()])
def test_interruption_retains_reservation_and_failure_trace(tmp_path, exc):
    with patch.object(ChatWorkflowAdapter, 'step', side_effect=exc):
        store, result, transport = run(tmp_path)
    assert transport.calls == 0
    assert result['usage']['blocked']
    assert result['usage']['usage']['output_tokens'] == 2048
    assert result['status'] == 'PROVIDER_FAILED'
    assert any(e['kind'] == 'V02_COMPLETED' for e in store.read())
    assert wf.replay(store.read(), result, expected_anchor=store.checkpoint())['model_calls'] == 0
