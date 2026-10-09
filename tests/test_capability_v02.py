"""Offline evaluator measurement validation; HTTP is stubbed throughout."""
import copy
import io
import json
import urllib.error
from collections import Counter
from pathlib import Path

import pytest

from quant_rsi.harness import capability_oracle as oracle
from quant_rsi.harness import comparison, providers
from quant_rsi.ledger.store import TraceStore, verify_events

SUITE = oracle.suite_fixtures('0.2')
TASKS = SUITE['task_order']
SAMPLES = json.loads(oracle.V02_PATH.with_name('validation_samples_v02.json').read_text(encoding='utf-8'))


def answer(tid):
    return copy.deepcopy(SAMPLES[tid]['correct'])


def score(tid, obj):
    return oracle.adjudicate(tid, json.dumps(obj).encode(), suite='0.2')


def test_task_provenance_coverage_and_contract_transparency():
    assert len(TASKS) == 24
    assert set(oracle.load_fixtures()['tasks']) <= set(TASKS)
    assert Counter(t['primary_dimension'] for t in SUITE['tasks'].values()) == {d['id']: 4 for d in SUITE['capability_dimensions']}
    assert len({t['source_incident_id'] for t in SUITE['tasks'].values()}) == 10
    for tid, task in SUITE['tasks'].items():
        assert task['task_kind'] == 'STATIC_DIAGNOSTIC'
        assert task['exposure_status'] == 'PUBLIC_DEV'
        assert task['difficulty_label'] and task['scoring_predicates']
        assert set(task['ground_truth']['facts']) == set(task['input_contract']['facts'])
        for ref in task['source_evidence']:
            path, _, anchor = ref.partition('#')
            source = comparison.ROOT / path
            assert source.is_file()
            if anchor.startswith('tasks/'):
                assert anchor[6:] in json.loads(source.read_text(encoding='utf-8'))['tasks']
        prompt = providers.build_prompt(tid, task['public_input'], contract=oracle.v02_contract(tid))
        contract = json.loads(prompt.split('answer_contract: ')[1])
        assert 'ground_truth' not in prompt and 'accept_verdicts' not in prompt
        assert 'expected' not in json.dumps(contract)
        assert contract['verdict_meanings'] and contract['refusal_conditions']
    verdicts = {s['correct']['verdict'] for s in SAMPLES.values()}
    assert {'PASS', 'REFUSE', 'FLAG_INCONSISTENT', 'INSUFFICIENT_EVIDENCE'} <= verdicts


@pytest.mark.parametrize('tid', TASKS)
def test_frozen_correct_wrong_and_equivalent_examples(tid):
    good = answer(tid)
    baseline = score(tid, good)
    assert baseline.full_pass, baseline.to_dict()
    bad = SAMPLES[tid]['wrong_decision']
    assert not score(tid, bad).full_pass
    assert score(tid, bad).evidence_ok  # wrong decision with correct numbers
    good['evidence'] = dict(reversed(list(good['evidence'].items())))
    good['reason'] += '; This is a diagnostic result only.'
    for fact, rule in SUITE['tasks'][tid]['input_contract']['facts'].items():
        v = good['evidence'].pop(fact)
        good['evidence'][rule['aliases'][-1]] = str(v) if rule['type'] == 'number' else v
    raw = ('```json\n' + json.dumps(good) + '\n```').encode()
    assert oracle.adjudicate(tid, raw, suite='0.2').full_pass


@pytest.mark.parametrize('tid', TASKS)
def test_each_required_fact_has_error_sensitivity(tid):
    for fact, rule in SUITE['tasks'][tid]['input_contract']['facts'].items():
        good = answer(tid)
        value = good['evidence'][fact]
        wrong = not value if type(value) is bool else value + 1 if isinstance(value, (int, float)) else ['invented'] if isinstance(value, list) else 'WRONG'
        good['evidence'][fact] = wrong
        assert not score(tid, good).full_pass, (tid, fact)
        good = answer(tid)
        good['reason'] = fact + '=' + json.dumps(wrong)
        assert score(tid, good).failure_type == 'DISQUALIFYING_CLAIM'
        good['reason'] = 'NOT(' + good['reason'] + ')'
        assert score(tid, good).full_pass  # quoted, explicitly denied wrong claim
        good['reason'] = 'NOT(' + fact + '=' + json.dumps(value) + ')'
        assert not score(tid, good).full_pass


def test_conflicting_aliases_duplicate_keys_and_nonfinite_values_are_rejected():
    tid = 'A-META-COUNT-ITEMS'
    good = answer(tid)
    good['evidence']['data_count'] = 1
    assert not score(tid, good).full_pass
    raw = json.dumps(answer(tid)).replace('"declared_count": 0', '"declared_count": 0, "declared_count": 1').encode()
    assert oracle.adjudicate(tid, raw, suite='0.2').failure_type == 'UNPARSEABLE_OR_INVALID_FORMAT'
    good = answer(tid)
    good['evidence']['declared_count'] = True
    assert not score(tid, good).full_pass
    good['evidence']['declared_count'] = 'NaN'
    assert not score(tid, good).full_pass
    good['evidence']['declared_count'] = float('nan')
    assert score(tid, good).failure_type == 'UNPARSEABLE_OR_INVALID_FORMAT'


@pytest.mark.parametrize('tid', ['A-PIT-BACKFILL-REFUSAL', 'A-BACKTEST-NOT-RUN', 'A-UNKNOWN-NOT-PASS', 'A-SOURCE-FABRICATION'])
def test_fabricated_qualification_or_sources_and_free_prose_fail(tid):
    good = answer(tid)
    good['evidence']['sources'] += ['EXCHANGE:DOES_NOT_EXIST']
    assert score(tid, good).failure_type == 'DISQUALIFYING_CLAIM'
    good = answer(tid)
    good['reason'] = 'This proves PIT and backtest qualification.'
    assert not score(tid, good).full_pass
    good['evidence']['pit_qualified'] = True
    assert not score(tid, good).full_pass


@pytest.mark.parametrize('raw', [b'```python\n{}\n```', b'```json\n{}', b'{} trailing', b'{broken', b'[]'])
def test_only_legal_json_presentation_is_accepted(raw):
    assert oracle.adjudicate(TASKS[0], raw, suite='0.2').failure_type == 'UNPARSEABLE_OR_INVALID_FORMAT'


class HttpResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return json.dumps(self.payload).encode()


@pytest.mark.parametrize('payload,expected', [
    ({'choices': [{'message': {'content': ''}, 'finish_reason': 'stop'}], 'usage': {'completion_tokens': 5}}, 'EMPTY_CONTENT'),
    ({'choices': [{'message': {'content': ''}, 'finish_reason': 'length'}]}, 'TOKEN_BUDGET_EXHAUSTED'),
    ({'choices': [{'message': {'content': '{partial'}, 'finish_reason': 'length'}]}, 'TOKEN_BUDGET_EXHAUSTED'),
    ({'code': 401, 'msg': 'private'}, 'BUSINESS_ERROR'),
    ({'error': {'message': 'private'}}, 'BUSINESS_ERROR'),
    ([], 'PROVIDER_RESPONSE_INVALID'),
])
def test_provider_failures_do_not_retry_or_escalate(monkeypatch, payload, expected):
    calls = []
    def fake(request, timeout):
        calls.append(json.loads(request.data))
        return HttpResponse(payload)
    monkeypatch.setenv('TEST_KEY', 'unit-test-placeholder')
    monkeypatch.setattr(providers.urllib.request, 'urlopen', fake)
    provider = providers.ChatProvider('test', 'test-model', 'https://example.invalid', 'TEST_KEY')
    reply = provider.reply(TASKS[0], 'test')
    assert reply.failure_type == expected
    assert reply.attempts == 1 and len(calls) == 1
    assert calls[0]['max_tokens'] == 24000


@pytest.mark.parametrize('exception,expected', [
    (TimeoutError('private'), 'TASK_TIMEOUT'),
    (urllib.error.URLError(TimeoutError('private')), 'TASK_TIMEOUT'),
    (urllib.error.HTTPError('https://example.invalid', 503, 'private', {}, io.BytesIO(b'private')), 'HTTP_ERROR'),
])
def test_timeout_http_classification_and_safe_errors(monkeypatch, exception, expected):
    calls = []
    def fail(*args, **kwargs):
        calls.append(1)
        raise exception
    monkeypatch.setenv('TEST_KEY', 'unit-test-placeholder')
    monkeypatch.setattr(providers.urllib.request, 'urlopen', fail)
    reply = providers.ChatProvider('test', 'model', 'https://example.invalid', 'TEST_KEY').reply(TASKS[0], 'test')
    assert reply.failure_type == expected
    assert 'private' not in reply.transport_error
    assert len(calls) == 1


def test_usage_finish_model_and_reasoning_tokens_are_retained(monkeypatch):
    payload = {'model': 'deployed-model', 'choices': [{'message': {'content': '{}', 'reasoning_content': 'abc'}, 'finish_reason': 'stop'}],
               'usage': {'prompt_tokens': 7, 'completion_tokens': 11, 'completion_tokens_details': {'reasoning_tokens': 8}}}
    monkeypatch.setenv('TEST_KEY', 'unit-test-placeholder')
    monkeypatch.setattr(providers.urllib.request, 'urlopen', lambda *a, **k: HttpResponse(payload))
    reply = providers.ChatProvider('test', 'requested', 'https://example.invalid', 'TEST_KEY').reply(TASKS[0], 'test')
    assert (reply.input_tokens, reply.output_tokens, reply.reasoning_tokens) == (7, 11, 8)
    assert reply.observed_model == 'deployed-model' and reply.finish_reason == 'stop'


def test_v02_offline_profiles_trace_pairing_and_denominators(tmp_path):
    pair = [providers.MockProvider('mock-a', 'frozen-correct'), providers.MockProvider('mock-b', 'wrong-decision')]
    manifest = comparison.run_comparison(pair, 'V02-TEST', tmp_path, suite='0.2')
    assert manifest['budget_usage']['attempts'] == 48
    assert manifest['incident_cluster_count'] == 10
    assert manifest['score_vector']['mock-a']['tasks_full_pass'] == 24
    assert manifest['score_vector']['mock-b']['tasks_full_pass'] == 0
    assert manifest['paired_cluster_differences']['mock-a-mock-b']['clusters_observed'] == 10
    assert manifest['anomaly_review']['status'] == 'EVALUATOR_ANOMALY_REVIEW_REQUIRED'
    assert manifest['research_agent_workflow_verified'] is False
    assert 'dimension_mean_rate' not in manifest['score_vector']['mock-a']
    assert len(list((tmp_path / 'V02-TEST').glob('attempt_*.json'))) == 48
    events = TraceStore(tmp_path / 'V02-TEST/trace.sqlite').read()
    verify_events(events)
    assert sum(e['kind'] == 'COMPARISON_RESERVED' for e in events) == 48
    for dim in manifest['score_vector']['mock-a']['by_dimension'].values():
        assert dim['assigned'] >= 4


def test_missing_real_authorization_and_repeat_are_blocked_before_dispatch(tmp_path):
    with pytest.raises(ValueError, match='authorization'):
        comparison.run_comparison([providers.planned_pairs()['deepseek']], 'NO-REAL', tmp_path, suite='0.2')
    assert not (tmp_path / 'NO-REAL').exists()
    with pytest.raises(ValueError, match='one attempt'):
        comparison.run_comparison([providers.MockProvider()], 'NO-REPEAT', tmp_path, repeat=2, suite='0.2')


def test_budget_denial_is_distinct_and_preserves_assignment(tmp_path, monkeypatch):
    plan = json.loads(oracle.V02_PATH.with_name('freeze_v02.json').read_text(encoding='utf-8'))
    plan['caps']['calls'] = 1
    fixture = tmp_path / 'fixtures_v02.json'
    fixture.write_bytes(oracle.V02_PATH.read_bytes())
    (tmp_path / 'validation_samples_v02.json').write_bytes(oracle.V02_PATH.with_name('validation_samples_v02.json').read_bytes())
    (tmp_path / 'freeze_v02.json').write_text(json.dumps(plan), encoding='utf-8')
    monkeypatch.setattr(oracle, 'V02_PATH', fixture)
    manifest = comparison.run_comparison([providers.MockProvider('mock-a')], 'STOP', tmp_path, suite='0.2')
    assert manifest['budget_stop'] == 'BUDGET_EXHAUSTED'
    assert manifest['score_vector']['mock-a']['tasks_assigned'] == 24
    assert manifest['score_vector']['mock-a']['task_pass_rate'] == round(1/24, 4)
    assert len(manifest['unattempted']) == 23
    assert all(r['failure_type'] == 'BUDGET_EXHAUSTED' for r in manifest['unattempted'])


def test_anomaly_triggers_do_not_change_scores():
    good = {'score': {'full_pass': True, 'parsed': True, 'verdict_ok': True, 'evidence_ok': True, 'failure_type': None}}
    bad = {'score': {'full_pass': False, 'parsed': False, 'verdict_ok': False, 'evidence_ok': False, 'failure_type': 'UNPARSEABLE_OR_INVALID_FORMAT'}}
    assert 'ALL_TASKS_FULL_PASS' in comparison.evaluator_anomalies([good], {})['reasons']
    reasons = comparison.evaluator_anomalies([bad], {})['reasons']
    assert 'ALL_TASKS_ZERO' in reasons and 'FORMAT_FAILURE_RATE_GE_25_PERCENT' in reasons
    vector = {'a': {'tasks_full_pass': 1, 'tasks_assigned': 2, 'by_dimension': {'dim': {'rate': 0.5}}},
              'b': {'tasks_full_pass': 1, 'tasks_assigned': 2, 'by_dimension': {'dim': {'rate': 0.5}}}}
    assert 'ALL_MODELS_SAME_DIMENSION:dim' in comparison.evaluator_anomalies([good], vector)['reasons']
    split = copy.deepcopy(good); split['score']['evidence_ok'] = False; split['score']['full_pass'] = False
    assert 'VERDICT_EVIDENCE_SPLIT_GE_25_PERCENT' in comparison.evaluator_anomalies([split], {})['reasons']


def test_runner_separates_no_answer_parse_and_wrong_research(tmp_path):
    class FailureProvider:
        provider_id, model_id = 'failure-profile', 'offline-only'
        def reply(self, tid, prompt):
            i = TASKS.index(tid)
            if i == 0:
                return providers.ProviderReply(True, '', 200, None, 1, 1, 1, 1, finish_reason='stop')
            if i == 1:
                return providers.ProviderReply(True, '{partial', 200, None, 1, 24000, 1, 1, finish_reason='length')
            if i == 2:
                return providers.ProviderReply(False, None, None, 'TASK_TIMEOUT', 0, 0, 1, 1, failure_class='TASK_TIMEOUT')
            if i == 3:
                return providers.ProviderReply(True, '{broken', 200, None, 1, 1, 1, 1)
            return providers.ProviderReply(True, json.dumps(SAMPLES[tid]['wrong_decision']), 200, None, 1, 1, 1, 1)
    manifest = comparison.run_comparison([FailureProvider()], 'CLASSIFY', tmp_path, suite='0.2')
    hist = manifest['score_vector']['failure-profile']['failure_types']
    assert hist == {'EMPTY_CONTENT': 1, 'TOKEN_BUDGET_EXHAUSTED': 1, 'TASK_TIMEOUT': 1,
                    'UNPARSEABLE_OR_INVALID_FORMAT': 1, 'WRONG_TERMINAL': 20}
    assert manifest['score_vector']['failure-profile']['provider_failure_count'] == 3
    assert manifest['score_vector']['failure-profile']['format_failure_count'] == 1
    assert manifest['records'][1]['response_text'] == '{partial'
    assert manifest['capability_result_valid'] is True


def test_freeze_changes_stop_before_provider_dispatch(tmp_path, monkeypatch):
    plan = json.loads(oracle.V02_PATH.with_name('freeze_v02.json').read_text(encoding='utf-8'))
    first = next(iter(plan['sha256']))
    plan['sha256'][first] = '0' * 64
    fixture = tmp_path / 'fixtures_v02.json'
    fixture.write_bytes(oracle.V02_PATH.read_bytes())
    (tmp_path / 'freeze_v02.json').write_text(json.dumps(plan), encoding='utf-8')
    monkeypatch.setattr(oracle, 'V02_PATH', fixture)
    with pytest.raises(ValueError, match='frozen file changed'):
        comparison.run_comparison([providers.MockProvider()], 'NO-DISPATCH', tmp_path, suite='0.2')
    assert not (tmp_path / 'NO-DISPATCH').exists()
