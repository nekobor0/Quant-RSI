"""No network or real credentials: exercise the clarified batch and failure bytes."""
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
from quant_rsi.harness import compatibility_pilot_clarified as new
from quant_rsi.harness import compatibility_pilot as old, capability_oracle as oracle, providers

KEY = 'offline-placeholder-not-a-real-credential'
SAMPLES = old.load(oracle.V02_PATH.with_name('validation_samples_v02.json'))


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('network forbidden'))
    monkeypatch.setenv('DEEPSEEK_API_KEY', KEY)
    monkeypatch.setenv('XIAOMI_API_KEY', KEY)
    monkeypatch.setattr(new, 'utc_now', lambda: datetime(2026, 10, 10, tzinfo=timezone.utc))


def approval():
    auth = old.load(new.FREEZE.with_name('authorization_request.json'))
    return dict(auth, approved=True)


class Response:
    status = 200

    def __init__(self, raw=None, error=None):
        self.raw, self.error = raw, error

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        if self.error:
            raise self.error
        return self.raw


def envelope(request):
    body = json.loads(request.data)
    tid = body['messages'][1]['content'].splitlines()[0].split(': ')[1]
    return {'model': body['model'], 'choices': [{'finish_reason': 'stop', 'message': {
        'content': json.dumps(SAMPLES[tid]['correct'])}}],
        'usage': {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150,
                  'completion_tokens_details': {'reasoning_tokens': 30}}}


def install(monkeypatch, behaviour=None):
    calls = []

    def open_request(request, timeout):
        calls.append(request)
        return behaviour(request) if behaviour else Response(json.dumps(envelope(request)).encode())

    monkeypatch.setattr(providers.urllib.request, 'urlopen', open_request)
    return calls


def test_prompt_changes_only_public_contract_and_no_truth_lookup(monkeypatch):
    plan = new.validate()
    before = copy.deepcopy(oracle.suite_fixtures('0.2'))
    after = copy.deepcopy(before)
    for task in after['tasks'].values():
        task['ground_truth'] = {'deliberately': 'irrelevant to prompt generation'}
    expected = new.prompts(plan)
    monkeypatch.setattr(oracle, 'suite_fixtures', lambda suite: after)
    assert new.prompts(plan) == expected
    for tid, text in expected.items():
        lines = text.splitlines()
        assert json.loads(lines[1][7:]) == before['tasks'][tid]['public_input']
        contract = json.loads(lines[2][17:])
        assert contract['facts'] == before['tasks'][tid]['input_contract']['facts']
        assert 'not the literal word fact' in contract['reason_role']
        assert 'source is not accepted' in contract['sources']
        assert 'timestamps exactly' in contract['identifier_policy']


def test_contract_is_clarified_without_relaxing_evaluator():
    tid = 'A-META-COUNT-ITEMS'
    answer = copy.deepcopy(SAMPLES[tid]['correct'])
    answer['reason'] = 'declared_count=0; NOT(items_len=0)'
    assert old.score_record(tid, json.dumps(answer), None)[0]['full_pass']
    for reason in ['fact={"declared_count":0}', 'data_count=0', 'declared_count=1',
                   'NOT(declared_count=0)']:
        answer['reason'] = reason
        assert not old.score_record(tid, json.dumps(answer), None)[0]['full_pass']


@pytest.mark.parametrize('field,value', [('approved', False), ('run_id', 'renamed'),
    ('entry_sha256', 'old-entry'), ('freeze_sha256', 'old-freeze'),
    ('total_money_cap_cny', '300')])
def test_gate_before_credentials(monkeypatch, tmp_path, field, value):
    auth = approval()
    auth[field] = value
    monkeypatch.setattr(providers.ChatProvider, '_resolve_key', lambda p: pytest.fail('credential read'))
    monkeypatch.setattr(providers.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('dispatch'))
    with pytest.raises(ValueError):
        new.run(new.validate()['run_id'], auth, tmp_path)
    assert not list(tmp_path.iterdir())


def test_real_runner_uses_clarified_messages_and_restores_globals(monkeypatch, tmp_path):
    originals = {n: getattr(old, n) for n in ['FREEZE', '__file__', 'prompts', 'PilotChatProvider', 'TraceStore', 'output_safe']}
    calls = install(monkeypatch)
    plan = new.validate()
    result = new.run(plan['run_id'], approval(), tmp_path)
    assert result['calls'] == len(calls) == 12 and result['stop'] is None
    assert all(r['score']['full_pass'] for r in result['records'])
    for request in calls:
        body = json.loads(request.data)
        tid = body['messages'][1]['content'].splitlines()[0].split(': ')[1]
        assert body['messages'] == [{'role': 'system', 'content': providers.SYSTEM_PROMPT},
                                   {'role': 'user', 'content': new.prompts(plan)[tid]}]
        assert 'tools' not in body
    assert all(getattr(old, n) is v for n, v in originals.items())
    root = tmp_path / plan['run_id']
    hashes = {p.name: old.digest(p.read_bytes()) for p in root.iterdir() if p.is_file()}
    assert new.replay(root)['attempts'] == 12
    assert len(calls) == 12
    assert hashes == {p.name: old.digest(p.read_bytes()) for p in root.iterdir() if p.is_file()}
    with pytest.raises(FileExistsError):
        new.run(plan['run_id'], approval(), tmp_path)
    assert len(calls) == 12


@pytest.mark.parametrize('case', ['invalid_json', 'partial', 'valid_json_partial',
                                 'read_error', 'http_429', 'credential_echo', 'timeout',
                                 'context_exit_error', 'http_429_surrogate'])
def test_failure_retention_stop_and_replay(monkeypatch, tmp_path, case):
    def behaviour(request):
        if case in ('http_429', 'http_429_surrogate'):
            raise urllib.error.HTTPError('https://offline.invalid', 429, 'arbitrary ' + KEY,
                                         {}, io.BytesIO(b'{"error":"busy"}' if case == 'http_429'
                                                        else b'{"error":"\\ud800"}'))
        if case == 'timeout':
            raise TimeoutError('arbitrary ' + KEY)
        if case == 'invalid_json':
            return Response(b'not-json')
        if case == 'read_error':
            return Response(error=OSError('arbitrary ' + KEY))
        if case == 'valid_json_partial':
            return Response(error=IncompleteRead(json.dumps(envelope(request)).encode(), 10))
        if case == 'context_exit_error':
            class BadClose(Response):
                def __exit__(self, *args):
                    raise OSError('arbitrary ' + KEY)
            return BadClose(json.dumps(envelope(request)).encode())
        partial = KEY.encode() if case == 'credential_echo' else b'{"partial":'
        return Response(error=IncompleteRead(partial, 10))
    calls = install(monkeypatch, behaviour)
    plan = new.validate()
    result = new.run(plan['run_id'], approval(), tmp_path)
    assert result['calls'] == len(calls) == 1
    assert len(result['unattempted']) == 11
    record = result['records'][0]
    assert record['cost_cny_decimal'] is None
    assert result['reserved_cost_cny']['deepseek'] == '0.30'
    assert record['transport_error']
    root = tmp_path / plan['run_id']
    assert all(KEY.encode() not in p.read_bytes() for p in root.iterdir() if p.is_file())
    if case in ('invalid_json', 'partial', 'valid_json_partial', 'http_429',
                'context_exit_error', 'http_429_surrogate'):
        assert record['raw_ref']
    else:
        assert record['raw_ref'] is None
    if case == 'invalid_json':
        assert record['provider_failure'] == 'PROVIDER_RESPONSE_INVALID'
        assert record['transport_error']['stage'] == 'response_parse_or_validation'
    if case in ('partial', 'valid_json_partial'):
        assert record['provider_failure'] == 'TRANSPORT_FAILED' and record['raw_partial']
        assert record['transport_error']['exception_type'] == 'IncompleteRead'
        assert record['transport_error']['expected_remaining_bytes'] == 10
    if case == 'context_exit_error':
        assert record['transport_error']['stage'] == 'response_context_exit'
        assert record['response_text'] is None
    if case == 'credential_echo':
        assert result['stop'] == 'SECURITY_OUTPUT_NOT_RETAINABLE'
    assert new.replay(root)['attempts'] == 1
    assert len(calls) == 1
    if record['raw_ref']:
        (root / record['raw_ref']).write_bytes(b'tampered')
        with pytest.raises(ValueError, match='changed raw'):
            new.replay(root)


def test_capture_limit_scans_secret_before_truncating(monkeypatch, tmp_path):
    monkeypatch.setattr(new, 'FAILURE_CAPTURE_LIMIT', 100)
    def behaviour(request):
        raise urllib.error.HTTPError('https://offline.invalid', 500, KEY, {},
                                     io.BytesIO(b'a' * 90 + KEY.encode() + b'z' * 100))
    calls = install(monkeypatch, behaviour)
    plan = new.validate()
    result = new.run(plan['run_id'], approval(), tmp_path)
    assert len(calls) == 1 and result['stop'] == 'SECURITY_OUTPUT_NOT_RETAINABLE'
    assert result['records'][0]['raw_ref'] is None


def test_unicode_escaped_key_in_incomplete_body_is_not_retained(monkeypatch, tmp_path):
    escaped = ''.join('\\u%04x' % ord(c) for c in KEY)
    calls = install(monkeypatch, lambda request: Response(
        error=IncompleteRead(('{"partial":"' + escaped).encode(), 10)))
    plan = new.validate()
    result = new.run(plan['run_id'], approval(), tmp_path)
    assert len(calls) == 1 and result['stop'] == 'SECURITY_OUTPUT_NOT_RETAINABLE'
    root = tmp_path / plan['run_id']
    assert not list(root.glob('raw_*'))
    assert all(KEY.encode() not in p.read_bytes() and escaped.encode() not in p.read_bytes()
               for p in root.iterdir() if p.is_file())


@pytest.mark.parametrize('instant,allowed', [
    ('2026-10-09T01:30:00+00:00', False), ('2026-10-09T05:30:00+00:00', False),
    ('2026-10-09T04:00:00+00:00', True), ('2026-10-09T10:00:00+00:00', True),
    ('2026-10-10T02:00:00+00:00', True)])
def test_offpeak_room(monkeypatch, instant, allowed):
    monkeypatch.setattr(new, 'utc_now', lambda: datetime.fromisoformat(instant))
    if allowed:
        new.require_offpeak_room(new.validate())
    else:
        with pytest.raises(ValueError, match='off-peak'):
            new.require_offpeak_room(new.validate())
