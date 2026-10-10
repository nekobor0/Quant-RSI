"""Public policy, prospective request capture and authorization gates, offline."""
import copy
import io
import json
import socket
import sys
import urllib.error
from datetime import datetime, timezone
from http.client import IncompleteRead
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from quant_rsi.harness import compatibility_pilot_023 as new, evaluator_023 as evaluator
from quant_rsi.harness import compatibility_pilot_clarified as base, compatibility_pilot as pilot
from quant_rsi.harness import capability_oracle as oracle, providers, evaluator_022 as old
from quant_rsi.ledger.store import TraceStore

TASK = 'A-PROVIDER-TOKEN-LIMIT'
KEY = 'offline-placeholder-not-a-real-credential'
SAMPLES = pilot.load(oracle.V02_PATH.with_name('validation_samples_v02.json'))


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('network forbidden'))
    monkeypatch.setenv('DEEPSEEK_API_KEY', KEY)
    monkeypatch.setenv('XIAOMI_API_KEY', KEY)
    monkeypatch.setattr(new.base, 'utc_now', lambda: datetime(2026, 10, 10, tzinfo=timezone.utc))


def response(value='TOKEN_BUDGET_EXHAUSTED', verdict='PASS', negated=False):
    answer = copy.deepcopy(SAMPLES[TASK]['correct'])
    answer['verdict'] = verdict
    answer['evidence']['failure_class'] = value
    assertion = f'failure_class={json.dumps(value)}'
    answer['reason'] = ('NOT(' + assertion + ')' if negated else assertion) + '; answer_observed=false'
    return json.dumps(answer).encode()


@pytest.mark.parametrize('value', ['TOKEN_BUDGET_EXHAUSTED', 'TOKEN_LIMIT', 'length'])
def test_public_aliases_apply_to_evidence_and_reason(value):
    assert evaluator.adjudicate(TASK, response(value)).full_pass
    assert old.adjudicate_tolerant(TASK, response(value)).full_pass == (value == 'TOKEN_BUDGET_EXHAUSTED')
    assert not evaluator.adjudicate(TASK, response(value, negated=True)).full_pass


@pytest.mark.parametrize('value', ['token_limit', 'LENGTH', ' length', 'TOKEN_LIMIT.',
    'RESEARCH_WRONG', 'HTTP_ERROR', 24000, None])
def test_aliases_do_not_guess_other_values(value):
    assert not evaluator.adjudicate(TASK, response(value)).full_pass


def test_aliases_do_not_correct_wrong_verdict_or_other_facts():
    score = evaluator.adjudicate(TASK, response('length', verdict='INSUFFICIENT_EVIDENCE'))
    assert score.failure_type == 'WRONG_TERMINAL' and score.evidence_ok
    answer = json.loads(response('length'))
    answer['evidence']['answer_observed'] = True
    assert not evaluator.adjudicate(TASK, json.dumps(answer).encode()).full_pass
    answer = copy.deepcopy(SAMPLES['A-PROVIDER-EMPTY']['correct'])
    answer['evidence']['failure_class'] = 'length'
    raw = json.dumps(answer).encode()
    assert evaluator.adjudicate('A-PROVIDER-EMPTY', raw) == old.adjudicate_tolerant('A-PROVIDER-EMPTY', raw)


def test_punctuation_and_malformed_json_policy_stays_bounded():
    answer = json.loads(response('TOKEN_LIMIT'))
    answer['reason'] += '; This is a diagnostic result only'
    assert evaluator.adjudicate(TASK, json.dumps(answer).encode()).full_pass
    for raw in (b'{bad', b'{"verdict":"PASS","verdict":"REFUSE"}', b''):
        assert evaluator.adjudicate(TASK, raw) == old.adjudicate_tolerant(TASK, raw)
    assert evaluator.adjudicate(TASK, None, failure_type='TRANSPORT_FAILED').failure_type == 'TRANSPORT_FAILED'


def test_public_contract_never_uses_hidden_truth(monkeypatch):
    plan = new.validate()
    before = new.prompts(plan)
    data = copy.deepcopy(oracle.suite_fixtures('0.2'))
    for task in data['tasks'].values():
        task['ground_truth'] = {'synthetic': 'not consulted'}
    monkeypatch.setattr(oracle, 'suite_fixtures', lambda *a: data)
    assert new.prompts(plan) == before
    policy = new.contract(TASK)
    assert policy['version'] == new.CONTRACT_VERSION
    assert 'omit' in policy['reason_role']
    assert 'execution diagnosis' in new.SYSTEM_PROMPT
    assert 'acting' not in new.SYSTEM_PROMPT.split('Use PASS', 1)[1].split('Use REFUSE', 1)[0]


def approval():
    return dict(pilot.load(new.FREEZE.with_name('authorization_request.json')), approved=True)


@pytest.mark.parametrize('field,value', [('approved', False), ('keys_rotated', False),
    ('entry_sha256', 'old-entry'), ('freeze_sha256', 'old-freeze'),
    ('run_id', 'renamed'), ('launch_channel', 'PAID_DSH_CONTROLLER')])
def test_gate_before_credentials_and_network(monkeypatch, tmp_path, field, value):
    auth = approval()
    auth[field] = value
    monkeypatch.setattr(providers.ChatProvider, '_resolve_key', lambda *a: pytest.fail('credential read'))
    monkeypatch.setattr(providers.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('dispatch'))
    with pytest.raises(ValueError):
        new.run(new.RUN_ID, auth, tmp_path)
    assert not list(tmp_path.iterdir())


class Response:
    status = 200

    def __init__(self, raw, error=None):
        self.raw, self.error = raw, error

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        if self.error:
            raise self.error
        return self.raw


def install(monkeypatch, failure=None):
    calls = []

    def transport(request, timeout):
        calls.append(json.loads(request.data))
        if failure == 'partial':
            return Response(None, IncompleteRead(b'{"partial":true}', 100))
        if failure == 'invalid_json':
            return Response(b'{bad envelope')
        if failure == 'http_429':
            raise urllib.error.HTTPError('https://offline.invalid', 429, 'busy', {}, io.BytesIO(b'{"error":"busy"}'))
        body = calls[-1]
        tid = body['messages'][1]['content'].splitlines()[0].split(': ')[1]
        text = response('TOKEN_LIMIT').decode() if tid == TASK else json.dumps(SAMPLES[tid]['correct'])
        return Response(json.dumps({'model': body['model'], 'choices': [
            {'finish_reason': 'stop', 'message': {'content': text}}], 'usage': {
                'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150,
                'completion_tokens_details': {'reasoning_tokens': 20}}}).encode())

    monkeypatch.setattr(providers.urllib.request, 'urlopen', transport)
    return calls


def test_twelve_requests_frozen_new_scores_trace_and_readonly_replay(monkeypatch, tmp_path):
    originals = {'system': providers.SYSTEM_PROMPT, 'adjudicate': oracle.adjudicate,
                 'freeze': base.FREEZE, 'entry': base.ENTRY, 'contract': base.CONTRACT_VERSION,
                 'trace': base.TraceStore, 'prompts': base.prompts}
    calls = install(monkeypatch)
    result = new.run(new.RUN_ID, approval(), tmp_path)
    assert result['calls'] == len(calls) == 12
    assert all(record['score']['full_pass'] and record['provider_attempts'] == 1 for record in result['records'])
    assert {name: value for name, value in originals.items()} == {
        'system': providers.SYSTEM_PROMPT, 'adjudicate': oracle.adjudicate,
        'freeze': base.FREEZE, 'entry': base.ENTRY, 'contract': base.CONTRACT_VERSION,
        'trace': base.TraceStore, 'prompts': base.prompts}
    texts = new.prompts(new.validate())
    for body in calls:
        tid = body['messages'][1]['content'].splitlines()[0].split(': ')[1]
        assert body['messages'] == [{'role': 'system', 'content': new.SYSTEM_PROMPT},
                                    {'role': 'user', 'content': texts[tid]}]
        assert 'tools' not in body
        assert body.get('max_tokens', body.get('max_completion_tokens')) == 24000
    root = tmp_path / new.RUN_ID
    started = TraceStore(root / 'trace.sqlite').read()[0]['payload']
    assert started['evaluator_version'] == evaluator.VERSION
    assert started['contract_version'] == new.CONTRACT_VERSION
    assert started['launch_channel'] == 'USER_OPERATED_TERMINAL_NO_PAID_CONTROLLER'
    before = {file.name: pilot.digest(file.read_bytes()) for file in root.iterdir() if file.is_file()}
    assert new.replay(root)['attempts'] == 12
    assert before == {file.name: pilot.digest(file.read_bytes()) for file in root.iterdir() if file.is_file()}
    with pytest.raises(FileExistsError):
        new.run(new.RUN_ID, approval(), tmp_path)
    assert len(calls) == 12


@pytest.mark.parametrize('failure', ['partial', 'invalid_json', 'http_429'])
def test_failure_capture_single_attempt_stop_and_replay(monkeypatch, tmp_path, failure):
    calls = install(monkeypatch, failure)
    result = new.run(new.RUN_ID, approval(), tmp_path)
    assert result['calls'] == len(calls) == 1
    assert len(result['unattempted']) == 11
    assert result['records'][0]['transport_error']
    assert result['records'][0]['raw_ref']
    assert not result['records'][0]['score']['full_pass']
    assert result['stop']
    assert new.replay(tmp_path / new.RUN_ID)['attempts'] == 1
    assert len(calls) == 1


def test_changed_public_policy_refuses_without_output(monkeypatch, tmp_path):
    original_read = Path.read_bytes

    def read(path):
        raw = original_read(path)
        return raw + b' ' if path == evaluator.POLICY else raw

    monkeypatch.setattr(Path, 'read_bytes', read)
    monkeypatch.setattr(evaluator, 'REPORT', tmp_path / 'report.json')
    assert evaluator.main(['--write']) == 1
    assert not evaluator.REPORT.exists()


def test_default_cli_does_not_authorize_or_read_credentials(monkeypatch):
    monkeypatch.setattr(providers.ChatProvider, '_resolve_key', lambda *a: pytest.fail('credential read'))
    monkeypatch.setattr(providers.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('dispatch'))
    assert new.main([]) is None
    assert pilot.load(new.FREEZE.with_name('authorization_request.json'))['approved'] is False
