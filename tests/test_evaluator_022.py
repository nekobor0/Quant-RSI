"""Offline policy and evidence-binding tests; no real credentials or network."""
import copy
import json
import os
import shutil
import socket
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from quant_rsi.harness import evaluator_022 as evaluator
from quant_rsi.harness import capability_oracle as oracle, compatibility_pilot_clarified as pilot, providers

TASK = 'A-META-COUNT-ITEMS'
EXPLANATION = 'The supplied fields contradict each other.'
SAMPLES = json.loads(oracle.V02_PATH.with_name('validation_samples_v02.json').read_bytes())


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('network forbidden'))
    monkeypatch.setattr(providers.ChatProvider, '_resolve_key', lambda *a: pytest.fail('credential read'))


def answer(explanation):
    response = copy.deepcopy(SAMPLES[TASK]['correct'])
    response['reason'] = explanation + '; declared_count=0; items_len=1'
    return json.dumps(response).encode()


@pytest.mark.parametrize('explanation', [EXPLANATION, EXPLANATION[:-1]])
def test_one_period_is_optional(explanation):
    response = answer(explanation)
    assert evaluator.adjudicate_tolerant(TASK, response).full_pass
    assert oracle.adjudicate_v02(TASK, response).full_pass == (explanation == EXPLANATION)


@pytest.mark.parametrize('explanation', [EXPLANATION.lower(), EXPLANATION + '.',
    EXPLANATION.replace('supplied fields', 'supplied  fields'),
    'Explanation: ' + EXPLANATION, EXPLANATION[:-1] + '!', EXPLANATION + ' extra'])
def test_other_expression_changes_rejected(explanation):
    score = evaluator.adjudicate_tolerant(TASK, answer(explanation))
    assert not score.full_pass
    assert 'reason:UNSUPPORTED_CLAUSE' in score.exact_mismatches


def test_variants_do_not_extend_unlisted_or_ambiguous_sentences():
    assert evaluator._period_variants(['Sentence.']) == {'Sentence.', 'Sentence'}
    assert evaluator._period_variants(['Sentence.', 'Sentence.']) == {'Sentence.'}
    assert evaluator._period_variants(['Sentence..']) == {'Sentence..'}
    assert evaluator._period_variants(['Sentence']) == {'Sentence'}


@pytest.mark.parametrize('change', ['fact', 'negation', 'source', 'verdict', 'extra_field'])
def test_period_tolerance_preserves_other_hard_checks(change):
    response = json.loads(answer(EXPLANATION[:-1]))
    if change == 'fact':
        response['evidence']['declared_count'] = 99
    elif change == 'negation':
        response['reason'] += '; NOT(declared_count=0)'
    elif change == 'source':
        response['evidence']['sources'] = ['FABRICATED']
    elif change == 'verdict':
        response['verdict'] = 'PASS'
    else:
        response['evidence']['unlisted'] = 0
    raw = json.dumps(response).encode()
    assert not evaluator.adjudicate_tolerant(TASK, raw).full_pass
    # Removing only the explanation eliminates punctuation differences.
    response['reason'] = response['reason'].split(';', 1)[1]
    raw = json.dumps(response).encode()
    assert evaluator.adjudicate_tolerant(TASK, raw) == oracle.adjudicate_v02(TASK, raw)


@pytest.mark.parametrize('raw,failure', [(b'{broken', None), (b'', None),
    (None, 'TRANSPORT_FAILED'), (None, 'OUTPUT_TRUNCATED')])
def test_provider_and_parse_failures_are_unchanged(raw, failure):
    assert evaluator.adjudicate_tolerant(TASK, raw, failure_type=failure) == \
        oracle.adjudicate_v02(TASK, raw, failure_type=failure)


def test_scoped_policy_restores_original_loader_and_fixture():
    loader = oracle.load_fixtures
    before = oracle.V02_PATH.read_bytes()
    evaluator.adjudicate_tolerant(TASK, answer(EXPLANATION[:-1]))
    assert oracle.load_fixtures is loader
    assert oracle.V02_PATH.read_bytes() == before


@pytest.mark.parametrize('target', ['oracle', 'fixture'])
def test_changed_frozen_binding_refuses_before_scoring_or_writing(monkeypatch, tmp_path, target):
    changed = tmp_path / 'changed'
    changed.write_bytes(b'changed frozen bytes')
    if target == 'oracle':
        monkeypatch.setattr(oracle, '__file__', str(changed))
    else:
        monkeypatch.setattr(oracle, 'V02_PATH', changed)
    output = tmp_path / 'report.json'
    monkeypatch.setattr(evaluator, 'BOUND_REPORT', output)
    monkeypatch.setattr(evaluator, 'load_bound_run', lambda *a: pytest.fail('evidence read'))
    monkeypatch.setattr(oracle, 'adjudicate_v02', lambda *a, **k: pytest.fail('scoring'))
    assert evaluator.main(['--write']) == 1
    assert not output.exists()
    with pytest.raises(ValueError, match='frozen binding changed'):
        evaluator.adjudicate_tolerant(TASK, answer(EXPLANATION))


def build_run(output, fail=False):
    class Response:
        status = 200

        def __init__(self, raw):
            self.raw = raw

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return self.raw

    def transport(request, timeout):
        if fail:
            raise TimeoutError('offline synthetic timeout')
        body = json.loads(request.data)
        tid = body['messages'][1]['content'].splitlines()[0].split(': ')[1]
        return Response(json.dumps({'model': body['model'], 'choices': [{
            'finish_reason': 'stop', 'message': {'content': json.dumps(SAMPLES[tid]['correct'])}}],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150,
                      'completion_tokens_details': {'reasoning_tokens': 20}}}).encode())

    auth = json.loads(pilot.FREEZE.with_name('authorization_request.json').read_bytes())
    auth['approved'] = True
    with patch.object(providers.ChatProvider, '_resolve_key', return_value='offline-placeholder'), \
            patch.object(providers.urllib.request, 'urlopen', transport), \
            patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'offline-placeholder',
                                    'XIAOMI_API_KEY': 'offline-placeholder'}), \
            patch.object(pilot, 'utc_now', return_value=datetime(2026, 10, 10, tzinfo=timezone.utc)):
        plan = pilot.validate()
        pilot.run(plan['run_id'], auth, output)
    return output / plan['run_id']


@pytest.fixture
def captured_run(tmp_path):
    return build_run(tmp_path / 'captured')


def hashes(root):
    return {file.name: sha256(file.read_bytes()).hexdigest() for file in root.iterdir() if file.is_file()}


def test_bound_report_links_all_inputs_and_preserves_sources(monkeypatch, tmp_path, captured_run):
    output = tmp_path / 'bound.json'
    monkeypatch.setattr(evaluator, 'BOUND_REPORT', output)
    before = hashes(captured_run)
    assert evaluator.main(['--run', str(captured_run), '--write']) == 0
    report = json.loads(output.read_bytes())
    assert report['bindings']['new_evaluator']['sha256'] == sha256(Path(evaluator.__file__).read_bytes()).hexdigest()
    assert report['bindings']['fixture']['sha256'] == evaluator.FROZEN_FIXTURE_SHA256
    provenance = report['batches'][0]['provenance']
    assert provenance['files_sha256'] == before
    assert len(provenance['records']) == 12
    assert provenance['trace_anchor']
    assert report['confirmed_legal_answer_misjudgments'] is None
    assert evaluator.main(['--run', str(captured_run), '--write']) == 0
    output.write_bytes(b'existing receipt')
    assert evaluator.main(['--run', str(captured_run), '--write']) == 1
    assert output.read_bytes() == b'existing receipt'
    assert hashes(captured_run) == before


@pytest.mark.parametrize('file', ['result.json', 'prompts.json', 'raw_01.json',
    'attempt_01.json', 'trace.sqlite'])
def test_evidence_tamper_refused(captured_run, tmp_path, file):
    root = tmp_path / captured_run.name
    shutil.copytree(captured_run, root)
    path = root / file
    if file == 'trace.sqlite':
        import sqlite3
        with sqlite3.connect(path) as conn:
            conn.execute('DROP TRIGGER events_no_update')
            conn.execute("UPDATE events SET event_hash='tampered' WHERE sequence=1")
    else:
        path.write_bytes(b'{}')
    with pytest.raises((ValueError, KeyError)):
        evaluator.load_bound_run(root)


def test_original_score_mismatch_refused():
    record = {'provider_id': 'synthetic', 'task_id': TASK,
              'response_text': answer(EXPLANATION).decode(), 'score': {}}
    with pytest.raises(ValueError, match='stored original score differs'):
        evaluator.rescore_record(record)


def test_missing_run_does_not_produce_partial_report(monkeypatch, tmp_path):
    output = tmp_path / 'report.json'
    monkeypatch.setattr(evaluator, 'BOUND_REPORT', output)
    assert evaluator.main(['--run', str(tmp_path / 'missing'), '--write']) == 1
    assert not output.exists()


def test_unknown_usage_failure_remains_evidence_without_a_score_upgrade(tmp_path):
    root = build_run(tmp_path / 'failed', fail=True)
    before = hashes(root)
    records, provenance = evaluator.load_bound_run(root)
    assert len(records) == 1
    assert provenance['records'][0]['raw_ref'] is None
    row = evaluator.rescore_record(records[0])
    assert not row['changed']
    assert not row['score_0_2_2']['full_pass']
    assert hashes(root) == before
