"""Pilot network is stubbed; no account credentials or real APIs are used."""
import copy
import json
import urllib.error
from decimal import Decimal
from pathlib import Path

import pytest

from quant_rsi.harness import capability_oracle as oracle
from quant_rsi.harness import compatibility_pilot as pilot
from quant_rsi.harness import providers
from quant_rsi.ledger.store import TraceStore

SAMPLES = pilot.load(oracle.V02_PATH.with_name('validation_samples_v02.json'))
TEST_KEY = 'offline-pilot-credential-placeholder'


def authorization():
    plan = pilot.validate_freeze()
    return {'approved': True, 'keys_rotated': True, 'call_cap': 12,
            'freeze_sha256': pilot.digest(pilot.FREEZE.read_bytes()),
            'entry_sha256': pilot.digest(Path(pilot.__file__).read_bytes()),
            'money_caps_cny': plan['money_caps_cny']}


class Response:
    status = 200

    def __init__(self, raw):
        self.raw = raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return self.raw


def fake_http(monkeypatch, mutate=None):
    calls = []

    def open_request(request, timeout):
        body = json.loads(request.data)
        tid = body['messages'][1]['content'].split('\n')[0].split(': ')[1]
        calls.append((body, timeout))
        payload = {'model': body['model'], 'id': 'offline-response',
                   'choices': [{'finish_reason': 'stop', 'message': {
                       'content': json.dumps(SAMPLES[tid]['correct']), 'reasoning_content': 'offline'}}],
                   'usage': {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150,
                             'completion_tokens_details': {'reasoning_tokens': 30},
                             'prompt_tokens_details': {'cached_tokens': 10}}}
        if mutate:
            changed = mutate(payload, request)
            if isinstance(changed, bytes):
                return Response(changed)
        return Response(json.dumps(payload).encode())

    monkeypatch.setenv('DEEPSEEK_API_KEY', TEST_KEY)
    monkeypatch.setenv('XIAOMI_API_KEY', TEST_KEY)
    monkeypatch.setattr(providers.urllib.request, 'urlopen', open_request)
    return calls, open_request


def test_selection_prompt_budget_and_base_bindings():
    plan = pilot.validate_freeze()
    tasks = oracle.suite_fixtures('0.2')['tasks']
    selection = pilot.load(pilot.FREEZE.with_name('tasks.json'))['tasks']
    assert plan['task_ids'] == [t['task_id'] for t in selection]
    assert len({tasks[t]['primary_dimension'] for t in plan['task_ids']}) == 6
    assert len({tasks[t]['source_incident_id'] for t in plan['task_ids']}) == 6
    assert all(tasks[t['task_id']]['source_incident_id'] == t['source_incident_id'] for t in selection)
    assert pilot.load(pilot.FREEZE.with_name('prompts.json')) == {
        'system': providers.SYSTEM_PROMPT, 'user': pilot.prompts(plan)}
    total = Decimal(0)
    for pid, config in plan['providers'].items():
        rates = config['prices_cny_per_million']
        expected = (Decimal(plan['input_per_call']) * Decimal(rates['input_miss'])
                    + Decimal(24000) * Decimal(rates['output'])) / Decimal(1000000)
        assert Decimal(config['worst_cost_cny_per_call']) == expected
        assert expected * 6 <= Decimal(plan['money_caps_cny'][pid])
        total += expected * 6
    assert total == Decimal('5.931648')
    assert plan['calls'] == 12 and plan['retries'] == 0


@pytest.mark.parametrize('field,value', [('approved', False), ('keys_rotated', False),
    ('call_cap', 13), ('freeze_sha256', 'old-freeze'), ('entry_sha256', 'old-entry'),
    ('money_caps_cny', {'deepseek': '100', 'xiaomi': '100'})])
def test_authorization_gate_precedes_credentials_or_network(monkeypatch, tmp_path, field, value):
    auth = authorization()
    auth[field] = value
    monkeypatch.setattr(providers.ChatProvider, '_resolve_key', lambda p: pytest.fail('credential read'))
    monkeypatch.setattr(providers.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('network'))
    with pytest.raises(ValueError, match='approval'):
        pilot.run('blocked', auth, tmp_path)
    assert not list(tmp_path.iterdir())


def test_exact_twelve_requests_native_parameters_trace_and_replay(monkeypatch, tmp_path):
    calls, original_open = fake_http(monkeypatch)
    result = pilot.run('stubbed', authorization(), tmp_path)
    assert result['calls'] == 12 and result['stop'] is None
    assert providers.urllib.request.urlopen is original_open
    for body, timeout in calls:
        assert timeout == 300 and body['thinking'] == {'type': 'enabled'}
        assert body['stream'] is False and 'tools' not in body
        if body['model'] == 'deepseek-v4-pro':
            assert body['max_tokens'] == 24000 and body['reasoning_effort'] == 'high'
            assert 'max_completion_tokens' not in body
        else:
            assert body['model'] == 'mimo-v2.6-pro'
            assert body['max_completion_tokens'] == 24000 and 'max_tokens' not in body
            assert body['temperature'] == 1.0 and body['top_p'] == 0.95
    assert all(r['score']['full_pass'] for r in result['records'])
    assert result['anomaly_review']['status'] == 'EVALUATOR_ANOMALY_REVIEW_REQUIRED'
    for pid, vector in result['score_vector'].items():
        assert vector['task_completion_rate_assigned'] == 1 and vector['provider_failure_rate_assigned'] == 0
        expected = Decimal('0.002163') * 6 if pid == 'deepseek' else Decimal('0.00057025') * 6
        assert Decimal(vector['estimated_cost_cny']) == expected
        assert vector['format_or_contract_failure_rate_assigned'] == 0
    root = tmp_path / 'stubbed'
    events = TraceStore(root / 'trace.sqlite').read()
    assert len(events) == 26 and len([e for e in events if e['kind'] == 'PILOT_RESERVED']) == 12
    assert pilot.replay(root) == {'status': 'OFFLINE_REPLAY_VERIFIED', 'attempts': 12, 'real_calls': 0}
    assert len(calls) == 12
    assert all(TEST_KEY.encode() not in p.read_bytes() for p in root.iterdir() if p.is_file())
    with pytest.raises(FileExistsError):
        pilot.run('stubbed', authorization(), tmp_path)
    assert len(calls) == 12
    changed = pilot.load(root / 'attempt_01.json')
    changed['response_text'] = '{}'
    pilot.save(root / 'attempt_01.json', changed)
    with pytest.raises(ValueError, match='attempt file'):
        pilot.replay(root)


@pytest.mark.parametrize('kind,expected', [
    ('http429', 'RATE_LIMIT_STOP'), ('business', 'UNKNOWN_USAGE_RECONCILIATION_REQUIRED'),
    ('invalid_envelope', 'UNKNOWN_USAGE_RECONCILIATION_REQUIRED'),
    ('missing_usage', 'UNKNOWN_USAGE_RECONCILIATION_REQUIRED'),
    ('bad_usage', 'UNKNOWN_USAGE_RECONCILIATION_REQUIRED'),
    ('model', 'MODEL_ID_MISMATCH'), ('missing_model', 'MODEL_METADATA_MISSING'),
    ('token_breach', 'PER_CALL_TOKEN_BUDGET_BREACH'),
    ('credential_echo', 'SECURITY_OUTPUT_NOT_RETAINABLE')])
def test_stop_without_retry_or_escalation(monkeypatch, tmp_path, kind, expected):
    def mutate(payload, request):
        if kind == 'http429':
            raise urllib.error.HTTPError(request.full_url, 429, 'rate limit', {}, None)
        if kind == 'business':
            payload['error'] = {'message': 'failure'}
        if kind == 'invalid_envelope':
            return b'not JSON'
        if kind == 'missing_usage':
            payload.pop('usage')
        if kind == 'bad_usage':
            payload['usage']['completion_tokens'] = True
        if kind == 'model':
            payload['model'] = 'other-model'
        if kind == 'missing_model':
            payload.pop('model')
        if kind == 'token_breach':
            payload['usage']['prompt_tokens'] = 20000
            payload['usage']['total_tokens'] = 20050
        if kind == 'credential_echo':
            payload['choices'][0]['message']['content'] = TEST_KEY
    calls, original_open = fake_http(monkeypatch, mutate)
    result = pilot.run(kind, authorization(), tmp_path)
    assert len(calls) == result['calls'] == 1 and result['stop'] == expected
    assert len(result['unattempted']) == 11
    assert providers.urllib.request.urlopen is original_open
    assert pilot.replay(tmp_path / kind)['attempts'] == 1
    if kind == 'credential_echo':
        assert result['records'][0]['response_text'] is None
        assert not list((tmp_path / kind).glob('raw_*'))
        assert all(TEST_KEY.encode() not in p.read_bytes() for p in (tmp_path / kind).iterdir() if p.is_file())


@pytest.mark.parametrize('finish,text,reasoning,stage', [
    ('length', None, 24000, 'REASONING_EXHAUSTED_NO_CONTENT'),
    ('length', '{', 100, 'OUTPUT_TRUNCATED'),
    ('length', None, None, 'COMBINED_TOKEN_EXHAUSTION_STAGE_UNKNOWN'),
    ('stop', None, 100, None), ('repetition_truncation', '{}', 100, None)])
def test_incomplete_output_is_provider_failure(monkeypatch, tmp_path, finish, text, reasoning, stage):
    def mutate(payload, request):
        payload['choices'][0] = {'finish_reason': finish, 'message': {'content': text}}
        payload['usage'].update(completion_tokens=24000, total_tokens=24100,
                                completion_tokens_details={'reasoning_tokens': reasoning})
    fake_http(monkeypatch, mutate)
    result = pilot.run('incomplete', authorization(), tmp_path)
    for r in result['records']:
        assert r['provider_failure'] and not r['score']['parsed']
        assert r['score']['failure_type'] != 'WRONG_TERMINAL'
        assert r['budget_stage'] == stage
    assert all(v['provider_failure_rate'] == 1 for v in result['score_vector'].values())


@pytest.mark.parametrize('tid', pilot.load(pilot.FREEZE)['task_ids'])
def test_legal_equivalent_answers_refusals_and_contradictions(tid):
    task = oracle.suite_fixtures('0.2')['tasks'][tid]
    good = copy.deepcopy(SAMPLES[tid]['correct'])
    baseline, _ = pilot.score_record(tid, json.dumps(good), None)
    assert baseline['full_pass']
    for fact, rule in task['input_contract']['facts'].items():
        value = good['evidence'].pop(fact)
        good['evidence'][rule['aliases'][-1]] = str(value) if rule['type'] == 'number' else value
    good['reason'] += '; This is a diagnostic result only.'
    equivalent, _ = pilot.score_record(tid, '```json\n' + json.dumps(good) + '\n```', None)
    assert equivalent['full_pass']  # A/E: published aliases, numbers and fences
    fact, rule = next(iter(task['input_contract']['facts'].items()))
    value = task['ground_truth']['facts'][fact]
    wrong = not value if type(value) is bool else value + 1 if isinstance(value, (int, float)) else 'WRONG'
    good['reason'] = f'NOT({fact}={json.dumps(wrong)})'
    denied, _ = pilot.score_record(tid, json.dumps(good), None)
    assert denied['full_pass']  # B: denied wrong value is not a positive false claim
    good['reason'] = f'{fact}={json.dumps(wrong)}'
    contradicted, diag = pilot.score_record(tid, json.dumps(good), None)
    assert not contradicted['full_pass'] and not diag['reason_ok']  # C
    assert diag['reason_failed_predicates']


def test_no_free_prose_contract_relaxation():
    tid = 'A-BACKTEST-NOT-RUN'
    good = copy.deepcopy(SAMPLES[tid]['correct'])
    good['reason'] = 'The backtest was prepared but it was never executed.'
    score, diagnostics = pilot.score_record(tid, json.dumps(good), None)
    assert score['verdict_ok'] and not score['full_pass']
    assert diagnostics['evidence_only_ok'] and not diagnostics['reason_ok']
    assert diagnostics['human_semantic_review'] == 'PENDING'
