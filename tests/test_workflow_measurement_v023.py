import copy
import json
import sys

import pytest

from quant_rsi.harness import workflow_measurement_v023 as m


@pytest.fixture(scope='module')
def reviewed():
    return {profile: m.review(profile) for profile in ('luna', 'mimo', 'deepseek')}


@pytest.mark.parametrize('text,error', [
    ('{', 'ACTION_JSON_INVALID'), ('[]', 'ACTION_SCHEMA_INVALID'),
    ('{"code":"x","action":"FINAL"}', 'ACTION_SCHEMA_INVALID'),
    ('{"code":1}', 'ACTION_SCHEMA_INVALID'), ('{"code":"a","code":"b"}', 'ACTION_SCHEMA_INVALID')])
def test_rejection_is_deterministically_reconstructed(text, error):
    case = {'kind': 'CODE', 'public_code': {'submission': {'source_bytes_max': 100}}}
    action, failure, candidate = m.decode_action(case, text)
    assert action is None and failure == error


def test_valid_code_and_output_limit_are_not_weakened():
    case = {'kind': 'CODE', 'public_code': {'submission': {'source_bytes_max': 1}}}
    assert m.decode_action(case, '{"code":"x"}') == ({'code': 'x'}, None, None)
    assert m.decode_action(case, '{"code":"xx"}')[1] == 'ACTION_SCHEMA_INVALID'


def test_precise_root_mapping_and_unknown_settlement_rejection():
    def event(kind, **payload):
        return {'kind': kind, 'payload': payload}
    events = [event('ATTEMPT_STARTED', attempt_id='CHAT-C2-1', budget_root_run_id='C2'),
        event('ATTEMPT_STARTED', attempt_id='CHAT-C23-1', budget_root_run_id='C23'),
        event('ATTEMPT_SETTLED', attempt_id='CHAT-C23-1', usage_state='BREACH'),
        event('ATTEMPT_SETTLED', attempt_id='CHAT-C2-1', usage_state='KNOWN')]
    view = m.budget_event_view(events, 'C2')
    assert [e['payload']['attempt_id'] for e in view if e['kind'] == 'ATTEMPT_SETTLED'] == ['CHAT-C2-1']
    assert len(events) == 4 and events[2]['payload']['usage_state'] == 'BREACH'
    with pytest.raises(ValueError, match='WITHOUT_RESERVATION'):
        m.budget_event_view([event('ATTEMPT_SETTLED', attempt_id='missing')], 'C2')


def test_public_contract_declares_array_and_keeps_strict_parser():
    cases = m.base.read(m.comparison.PACK / 'cases.json')
    tools = m.base.read(m.comparison.PACK / 'action_contract.json')
    for key, case in cases.items():
        context = m.public_context(case, tools, [], [])
        if case['kind'] == 'CODE':
            assert context['task']['submission']['output_keys'] == ['code']
        else:
            schema = context['action_contract']['FINAL']['evidence']
            assert schema['type'] == 'array' and schema['items']['type'] == 'string' and schema['uniqueItems']
    case = cases['Q-DA-01']
    for refs in ['OBS-1', ['OBS-1', 'OBS-1'], [1]]:
        text = json.dumps(dict(action='FINAL', conclusion={}, evidence=refs))
        assert m.decode_action(case, text)[1] == 'ACTION_SCHEMA_INVALID'
    assert m.decode_action(case, json.dumps(dict(action='FINAL', conclusion={}, evidence=['OBS-1'])))[1] is None


def test_all_three_historical_batches_replay_without_new_execution(reviewed):
    for profile, count, passes in [('luna', 32, 31), ('mimo', 21, 19), ('deepseek', 23, 15)]:
        result = reviewed[profile]
        assert result['cases'] == count and result['strict_pass_count'] == passes
        assert result['status'] == 'OFFLINE_FIXED_MEASUREMENT_REVIEW_VERIFIED'
        assert result['model_calls'] == result['tool_calls'] == result['container_calls'] == 0
        assert result['original_scores_unchanged'] is True
    cp = next(r for r in reviewed['mimo']['results'] if r['task_id'] == 'Q-CP-01')
    assert cp['status'] == 'INVALID_ACTION' and not cp['score_v023']['score']['full_pass']
    assert next(r for r in reviewed['deepseek']['results'] if r['task_id'] == 'Q-DA-02')['score_v023']['vector']['BUDGET_COMPLIANT'] is True


def test_expression_reviews_are_separate_from_strict_scores_for_every_model(reviewed):
    assert reviewed['luna']['expression_reviews_not_scores'] == reviewed['mimo']['expression_reviews_not_scores'] == 0
    assert reviewed['deepseek']['expression_reviews_not_scores'] == 7
    for row in reviewed['deepseek']['results']:
        value = row['expression_review']
        if value:
            assert value['all_facts_correct'] and value['references_valid']
            assert not value['admitted_as_score'] and not row['score_v023']['task_pass']


def test_provider_failures_stay_failures_and_unknown_reservation_stays_held(reviewed):
    mimo = next(r for r in reviewed['mimo']['results'] if r['task_id'] == 'Q-CP-02')
    ds = next(r for r in reviewed['deepseek']['results'] if r['task_id'] == 'Q-CP-04')
    assert mimo['status'] == ds['status'] == 'PROVIDER_FAILED'
    assert not mimo['score_v023']['score']['full_pass'] and not ds['score_v023']['score']['full_pass']
    with m.source('mimo'):
        summary = m.base.read(m.core.OUTPUT / 'summary.json')
        assert summary['accounting']['unknown_usage'] == 1
        assert summary['accounting']['input_tokens'] == 180536 and summary['accounting']['output_tokens'] == 37992


def test_forged_failure_label_is_rejected_before_acceptance():
    with m.source('mimo'):
        summary = m.base.read(m.core.OUTPUT / 'summary.json')
        events = m.base.read(m.core.OUTPUT / 'trace.json')
        case = m.core.suite()[1]['Q-CP-01']
        result = next(r for r in summary['results'] if r['case_key'] == 'Q-CP-01')
        forged = copy.deepcopy(events)
        response = next(e['payload'] for e in forged if e['kind'] == 'MODEL_RESPONSE' and e['payload']['run_id'] == result['run_id'])
        response['error'] = 'ACTION_JSON_INVALID'
        with pytest.raises(ValueError, match='ACCEPTANCE_OR_REJECTION_CHANGED'):
            m.verify_case(case, result, forged, legacy=True)


def test_corrected_live_seam_never_exposes_rejected_code_as_action(monkeypatch):
    with m.source('mimo'):
        config, cases, tools = m.core.suite()
        case = cases['Q-CP-01']
        monkeypatch.setattr(m.core, 'permit', lambda events: None)
        class Store:
            def __init__(self): self.events = []
            def read(self): return self.events
            def append(self, event_id, kind, payload): self.events.append({'kind': kind, 'payload': payload})
        class Budget:
            def __init__(self): self.reservations = []; self.settlements = []
            def reserve(self, *args, **kwargs): self.reservations.append((args, kwargs))
            def settle(self, *args, **kwargs): self.settlements.append((args, kwargs))
        class Agent:
            def step(self, task_id, messages):
                native = dict(model=config['provider']['model_id'], choices=[dict(message={'content': '{"action":"FINAL","code":"x"}'}, finish_reason='stop')],
                    usage=dict(prompt_tokens=20, completion_tokens=10, total_tokens=30))
                return m.core.http.parsed_reply(native, 200, 1, 'chat'), dict(
                    body=m.core.http.public_request(config['provider'], messages), envelope=native,
                    raw_hex=json.dumps(native).encode().hex(), raw_partial=False, observation={'cleanup_confirmed': True})
        store, budget = Store(), Budget()
        with m.core.contract.execution_bindings(m.core.OUTPUT, m.core.BATCH, m.core.LIMITS, m.core.permit, m.core.score, m.core.model_request):
            value = m.model_request(store, budget, 'SYNTHETIC', case, Agent(), config, tools, 1, [], [], [], [])
        assert value['action'] is None and value['rejected_candidate'] == {'action': 'FINAL', 'code': 'x'}
        assert value['error'] == 'ACTION_SCHEMA_INVALID' and value['resources']['output_tokens'] == 10
        assert len(budget.reservations) == len(budget.settlements) == 1


def test_cli_has_no_real_start_or_credential_arguments(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['entry', '--help'])
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    assert 'prepare' in help_text and 'review' in help_text
    assert 'start' not in help_text and 'credential' not in help_text
