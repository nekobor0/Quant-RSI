"""Judge validity is distinct from substantive, independently authored calibration."""
import copy
import json
import urllib.request

import pytest

from quant_rsi.harness import agent_workflow as base
from quant_rsi.harness import hybrid_judge as judge
from quant_rsi.ledger.store import TraceStore, verify_events


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **k: pytest.fail('NO NETWORK'))


@pytest.fixture(scope='module')
def calibration():
    return judge.build_calibration()


def reviewed(tmp_path, packet, mode='correct'):
    store = TraceStore(tmp_path / 'trace.sqlite')
    transport = judge.MockJudgeTransport(mode)
    reply = judge.JudgeAdapter(transport).review(packet)
    result = judge.append_judgment(store, packet, reply, review_id='REVIEW-' + mode)
    assert transport.calls == 1
    return store, result


@pytest.mark.parametrize('index', range(18))
def test_18_hand_reviewable_calibration_samples(tmp_path, calibration, index):
    packets, _, references = calibration
    packet, reference = packets[index], references[index]
    original = copy.deepcopy(packet['deterministic'])
    store, result = reviewed(tmp_path, packet)
    assert result['validation']['accepted']
    assert judge.calibration_check(result, reference)['within_reference']
    assert result['deterministic_original'] == original
    assert packet['deterministic'] == original
    assert result['single_total_score'] is None and not result['D08_achieved']
    assert reference['human_check'] and reference['reference_author'] != 'Judge'
    assert result['validation']['semantic_quality_verified'] is False
    verify_events(store.read(), store.checkpoint())


def test_identity_blinding_and_private_authentic_receipt_mapping(calibration):
    packets, registry, references = calibration
    assert len(packets) == len(registry) == len(references) == 18
    for packet, receipt in zip(packets, registry):
        serialized = json.dumps(packet)
        assert receipt['run_id'] not in serialized
        assert 'scripted-correct-v01' not in serialized
        assert 'scripted-wrong-v01' not in serialized
        assert 'simulated-chat-' not in serialized
        assert 'reference_author' not in serialized and 'rating_ranges' not in serialized
        assert 'source_profile' not in serialized
        assert judge.validate_packet(packet) == set(receipt['references'])
        events = base.read(base.ROOT / receipt['source_trace'])
        actual = {e['event_id']: e['event_hash'] for e in events}
        assert all(actual[r['event_id']] == r['event_hash'] for r in receipt['references'].values())


@pytest.mark.parametrize('mode', ['wrong_score', 'expression_bias'])
def test_structurally_valid_wrong_scores_need_reference_review(tmp_path, calibration, mode):
    packet, reference = calibration[0][0], calibration[2][0]
    _, result = reviewed(tmp_path, packet, mode)
    assert result['validation']['accepted']  # syntax/gates cannot certify soft quality
    checked = judge.calibration_check(result, reference)
    assert not checked['within_reference'] and checked['human_review_required']
    assert len(checked['differences']) == 6


def test_fabricated_evidence_refs_are_rejected_but_raw_is_retained(tmp_path, calibration):
    store, result = reviewed(tmp_path, calibration[0][0], 'fabricated')
    assert not result['validation']['accepted']
    assert all('FABRICATED' in e for e in result['validation']['errors'])
    assert 'O-invented' in result['reply']['text']
    assert store.read()[-1]['payload']['raw_result'] == result['raw_result']


def test_positive_judge_cannot_override_failed_deterministic_gate(tmp_path, calibration):
    # Existing wrong-final trace still has valid tooling/budget/trace dimensions.
    packet = next(p for p in calibration[0] if p['deterministic']['vector']['FINAL_DECISION_CORRECT'] is False)
    _, result = reviewed(tmp_path, packet, 'hard_conflict')
    assert not result['validation']['accepted']
    assert any('HARD_GATE_CONFLICT' in e for e in result['validation']['errors'])
    assert result['deterministic_original']['vector']['FINAL_DECISION_CORRECT'] is False


def test_abstention_is_distinct_from_zero_and_false(tmp_path, calibration):
    _, result = reviewed(tmp_path, calibration[0][0], 'abstain')
    assert result['validation']['accepted']
    assert all(v['rating'] == 'INSUFFICIENT_EVIDENCE' for v in result['raw_result']['scores'].values())
    assert judge.calibration_check(result, calibration[2][0])['human_review_required']


def test_equivalent_rationale_wording_does_not_change_validity_or_vector(tmp_path, calibration):
    _, a = reviewed(tmp_path / 'a', calibration[0][0])
    _, b = reviewed(tmp_path / 'b', calibration[0][0], 'paraphrase')
    assert a['validation'] == b['validation']
    assert {k: v['rating'] for k, v in a['raw_result']['scores'].items()} == {
        k: v['rating'] for k, v in b['raw_result']['scores'].items()}
    assert a['deterministic_original'] == b['deterministic_original']


@pytest.mark.parametrize('mutation,error', [
    ('boolean_rating', 'RATING_INVALID'), ('out_of_range', 'RATING_INVALID'),
    ('wrong_packet', 'PACKET_OR_RUBRIC_MISMATCH'), ('invented_ref', 'FABRICATED'),
    ('empty_refs', 'MISSING_EVIDENCE'), ('abstain_no_reason', 'ABSTENTION_REASON_INVALID'),
    ('false_abstain_reason', 'ABSTENTION_FACT_CONFLICT'), ('missing_observation_reason', 'ABSTENTION_FACT_CONFLICT'), ('extra_total', 'RESULT_SCHEMA_INVALID'),
    ('missing_dimension', 'DIMENSION_SET_INVALID')])
def test_result_validator_schema_refs_and_abstention(calibration, mutation, error):
    packet = calibration[0][0]
    reply = judge.JudgeAdapter(judge.MockJudgeTransport()).review(packet)
    result = json.loads(reply.text)
    score = result['scores']['FINAL_DECISION_CORRECT']
    if mutation == 'boolean_rating': score['rating'] = True
    if mutation == 'out_of_range': score['rating'] = 4
    if mutation == 'wrong_packet': result['packet_id'] = 'bad'
    if mutation == 'invented_ref': score['evidence_refs'] = ['O404']
    if mutation == 'empty_refs': score['evidence_refs'] = []
    if mutation == 'abstain_no_reason': score.update(rating='INSUFFICIENT_EVIDENCE', abstention_reason=None)
    if mutation == 'false_abstain_reason': score.update(rating='INSUFFICIENT_EVIDENCE', abstention_reason='NO_FINAL')
    if mutation == 'missing_observation_reason': score.update(rating='INSUFFICIENT_EVIDENCE', abstention_reason='MISSING_OBSERVATION')
    if mutation == 'extra_total': result['total'] = 18
    if mutation == 'missing_dimension': result['scores'].pop('BUDGET_COMPLIANT')
    checked = judge.JudgeResultValidator(packet).validate(result)
    assert not checked['accepted'] and any(error in e for e in checked['errors'])


def test_missing_final_requires_abstention_not_invented_grade(calibration):
    packet = next(p for p in calibration[0] if p['final'] is None)
    result = json.loads(judge.JudgeAdapter(judge.MockJudgeTransport()).review(packet).text)
    score = result['scores']['FINAL_DECISION_CORRECT']
    assert score['rating'] == 'INSUFFICIENT_EVIDENCE'
    score.update(rating=0, abstention_reason=None)
    checked = judge.JudgeResultValidator(packet).validate(result)
    assert any('UNKNOWN_FACT_REQUIRES_ABSTENTION' in e for e in checked['errors'])


def test_unverified_or_mutated_packet_rejected(calibration):
    packet = copy.deepcopy(calibration[0][0])
    packet['observations'][0]['result'] = {'invented': True}
    with pytest.raises(ValueError, match='BINDING'):
        judge.JudgeResultValidator(packet)
    packet = copy.deepcopy(calibration[0][0])
    packet['source_verified'] = False
    packet['packet_id'] = base.digest({k: v for k, v in packet.items() if k != 'packet_id'})
    with pytest.raises(ValueError, match='BINDING'):
        judge.JudgeAdapter(judge.MockJudgeTransport()).review(packet)


def test_append_only_repeated_judges_keep_original_scores(tmp_path, calibration):
    packet = calibration[0][0]
    store = TraceStore(tmp_path / 'trace.sqlite')
    first = judge.append_judgment(store, packet, judge.JudgeAdapter(judge.MockJudgeTransport()).review(packet), review_id='FIRST')
    prefix = copy.deepcopy(store.read())
    second = judge.append_judgment(store, packet, judge.JudgeAdapter(judge.MockJudgeTransport('wrong_score')).review(packet), review_id='SECOND')
    assert store.read()[:len(prefix)] == prefix
    assert first['deterministic_original'] == second['deterministic_original'] == packet['deterministic']
    assert len([e for e in store.read() if e['kind'] == 'JUDGE_RESULT_RECORDED']) == 2


def test_judge_no_real_transport_no_credential_and_no_duplicate_json(monkeypatch):
    with pytest.raises(ValueError, match='NOT_AUTHORIZED'):
        judge.JudgeAdapter(lambda *a: None)
    monkeypatch.setattr('os.environ.get', lambda *a: pytest.fail('KEY READ'))
    assert judge.JudgeAdapter(judge.MockJudgeTransport()).client._resolve_key() == 'synthetic-placeholder'
    with pytest.raises(ValueError, match='DUPLICATE'):
        judge.parse_result('{"scores":{},"scores":{}}')


def test_judge_replay_requires_no_model_and_preserves_failed_raw(tmp_path, calibration, monkeypatch):
    store, result = reviewed(tmp_path, calibration[0][0], 'fabricated')
    events, anchor = store.read(), store.checkpoint()
    monkeypatch.setattr(judge.JudgeAdapter, 'review', lambda *a: pytest.fail('JUDGE CALLED'))
    assert judge.replay_judgment(events, result, expected_anchor=anchor)['model_calls'] == 0
    assert store.read() == events
    damaged = copy.deepcopy(result)
    damaged['deterministic_original']['vector']['BUDGET_COMPLIANT'] = False
    with pytest.raises(ValueError, match='ORIGINAL_SCORE_CHANGED'):
        judge.replay_judgment(events, damaged, expected_anchor=anchor)
