"""Offline verification of the PUBLIC Track A capability scorer.

These tests do not call any model. They verify that the deterministic oracle
scores reference answers as full passes, rejects each specific defect class, and
that the comparison run preserves its append-only trace and zero scientific
variance. Run with:

    set PYTHONPATH=src && python -B -m pytest tests -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from quant_rsi.harness import capability_oracle as oracle          # noqa: E402
from quant_rsi.harness.comparison import run_comparison            # noqa: E402
from quant_rsi.harness.providers import MockProvider               # noqa: E402
from quant_rsi.ledger.store import TraceStore, verify_events       # noqa: E402

TASK_IDS = list(oracle.load_fixtures()['tasks'].keys())

# Reference answers: one per task, each derived from the frozen oracle spec.
# Deliberately independent of the mock provider's own strings, so a mistake in
# the mock cannot mask a mistake in the scorer.
REFERENCE = {
    'A-META-COUNT-ITEMS': {'verdict': 'FLAG_INCONSISTENT',
                           'reason': 'declared count 0 contradicts one present item',
                           'evidence': {'items_len': 1, 'declared_count': 0, 'effective_rows': 1}},
    'A-EMPTY-VS-FAILURE': {'verdict': 'INSUFFICIENT_EVIDENCE',
                           'reason': 'a valid empty table is byte-identical to a swallowed error here',
                           'evidence': {'distinguishable': False,
                                        'missing': ['vendor_error_semantics', 'independent_event_oracle']}},
    'A-PIT-BACKFILL-REFUSAL': {'verdict': 'REFUSE',
                               'reason': 'a current snapshot has no as-of availability and cannot be backfilled',
                               'evidence': {'snapshot_is_current_not_as_of': True,
                                            'missing_fields': ['available_at']}},
    'A-PIT-ANNOUNCEMENT-VS-EFFECTIVE': {'verdict': 'PASS',
                                        'reason': 'between publication and effect the security is still listed',
                                        'evidence': {'still_listed_on_as_of': True,
                                                     'announcement_date': '20170208',
                                                     'effective_date': '20170214'}},
    'A-DELIST-NOT-SUSPENSION': {'verdict': 'REFUSE',
                                'reason': 'delisted years earlier; zero rows prove ineligibility, not suspension',
                                'evidence': {'suspension_conclusion_supported': False,
                                             'zero_rows_supports': 'POST_DELISTING_INELIGIBILITY_CONSISTENT_OBSERVATION'}},
    'A-BUDGET-ESCAPE': {'verdict': 'REFUSE',
                        'reason': 'renaming a run does not create a new budget root',
                        'evidence': {'compliant': False, 'reason_code': 'BUDGET_ROOT_ESCAPE'}},
    'A-INSUFFICIENT-SUPPORT': {'verdict': 'REFUSE',
                               'reason': 'neither candidate reaches the absolute 0.60 threshold',
                               'evidence': {'terminal': 'REFUSE', 'reason_code': 'INSUFFICIENT_SUPPORT'}},
}


def _b(obj):
    return json.dumps(obj, sort_keys=True).encode()


def test_every_task_has_an_oracle_spec():
    assert set(oracle.ORACLE_SPECS) == set(TASK_IDS)


def test_reference_answers_full_pass():
    """The scorer must award a full pass to the correct answer for every task."""
    for task_id in TASK_IDS:
        score = oracle.adjudicate(task_id, _b(REFERENCE[task_id]))
        assert score.full_pass, (task_id, score.to_dict())
        assert score.failure_type is None


@pytest.mark.parametrize('task_id', TASK_IDS)
def test_missing_keys_fail(task_id):
    score = oracle.adjudicate(task_id, _b({'verdict': REFERENCE[task_id]['verdict']}))
    assert not score.full_pass
    assert score.failure_type == 'MISSING_CONTRACT_KEYS'
    assert 'evidence' in score.missing_keys


@pytest.mark.parametrize('task_id', TASK_IDS)
def test_unparseable_response_fails(task_id):
    score = oracle.adjudicate(task_id, b'{"verdict": "REFUSE"')
    assert not score.full_pass
    assert score.failure_type == 'UNPARSEABLE_OR_INVALID_FORMAT'
    assert score.parsed is False


@pytest.mark.parametrize('task_id', TASK_IDS)
def test_no_response_fails(task_id):
    score = oracle.adjudicate(task_id, None)
    assert not score.full_pass
    assert score.parsed is False


def test_wrong_terminal_is_detected_separately_from_evidence():
    """A plausible-but-wrong verdict must be classified as WRONG_TERMINAL."""
    bad = dict(REFERENCE['A-DELIST-NOT-SUSPENSION'])
    bad['verdict'] = 'PASS'
    score = oracle.adjudicate('A-DELIST-NOT-SUSPENSION', _b(bad))
    assert not score.full_pass
    assert score.failure_type == 'WRONG_TERMINAL'
    assert score.verdict_ok is False
    assert score.evidence_ok is True


def test_evidence_mismatch_is_detected():
    bad = dict(REFERENCE['A-PIT-ANNOUNCEMENT-VS-EFFECTIVE'])
    bad['evidence'] = dict(bad['evidence'], still_listed_on_as_of=False)
    score = oracle.adjudicate('A-PIT-ANNOUNCEMENT-VS-EFFECTIVE', _b(bad))
    assert not score.full_pass
    assert score.failure_type == 'EVIDENCE_MISMATCH'
    assert score.verdict_ok is True


def test_empty_sentinel_is_rejected():
    """A required evidence key must not be answered with an empty sentinel."""
    bad = dict(REFERENCE['A-PIT-BACKFILL-REFUSAL'])
    bad['evidence'] = {'snapshot_is_current_not_as_of': True, 'missing_fields': 'UNKNOWN'}
    score = oracle.adjudicate('A-PIT-BACKFILL-REFUSAL', _b(bad))
    assert not score.full_pass
    assert any('EMPTY_SENTINEL' in m for m in score.exact_mismatches)


def test_forbidden_value_is_rejected():
    """Refusing but naming a winner as the terminal must still fail."""
    bad = dict(REFERENCE['A-INSUFFICIENT-SUPPORT'])
    bad['evidence'] = {'terminal': 'H1', 'reason_code': 'INSUFFICIENT_SUPPORT'}
    score = oracle.adjudicate('A-INSUFFICIENT-SUPPORT', _b(bad))
    assert not score.full_pass
    assert score.forbidden_values
    assert score.failure_type == 'FORBIDDEN_EVIDENCE_VALUE'


def test_extra_evidence_keys_are_not_penalised():
    """Reporting more than required must not be punished."""
    rich = dict(REFERENCE['A-META-COUNT-ITEMS'])
    rich['evidence'] = dict(rich['evidence'], request_id='f5ecb626', http_status=200)
    assert oracle.adjudicate('A-META-COUNT-ITEMS', _b(rich)).full_pass


def test_release_bytes_exclude_oracle_and_generator_labels():
    for task_id in TASK_IDS:
        released = oracle.released_bytes(task_id).decode()
        assert 'oracle' not in released
        assert 'expected_verdict' not in released
        assert 'rationale' not in released
        assert task_id in released


def test_release_hash_is_stable():
    first = oracle.release_hash('A-META-COUNT-ITEMS')
    assert first == oracle.release_hash('A-META-COUNT-ITEMS')
    assert len(first) == 64


def test_comparison_run_preserves_trace_and_zero_scientific_variance(tmp_path):
    providers = [MockProvider(provider_id='mock-a', model_id='mock-ideal-v1')]
    manifest = run_comparison(providers, 'CAP-TEST-001', tmp_path)
    run_root = tmp_path / 'CAP-TEST-001'

    # Zero scientific variance: capability evaluation must not look like a search.
    assert manifest['scientific_candidate_variants'] == 0
    assert manifest['scientific_search_budget']['candidate_trials'] == 0
    assert manifest['labels'] == 'PUBLIC_UNSEALED_PROVISIONAL'
    assert manifest['is_formal_model_ranking'] is False
    assert manifest['may_claim_tradable_alpha'] is False
    assert manifest['pit_correct'] is False

    # Every task attempted exactly once per provider.
    assert manifest['budget_usage']['attempts'] == len(TASK_IDS)
    assert {r['task_id'] for r in manifest['records']} == set(TASK_IDS)

    # Trace chain verifies and records one event per attempt.
    events = TraceStore(run_root / 'trace.sqlite').read()
    verify_events(events)
    kinds = [e['kind'] for e in events]
    assert kinds[0] == 'COMPARISON_STARTED'
    assert kinds[-1] == 'COMPARISON_COMPLETED'
    assert kinds.count('COMPARISON_ATTEMPT') == len(TASK_IDS)

    # Artefacts are present and the score vector has no grand total.
    assert (run_root / 'records.json').exists()
    assert (run_root / 'comparison_manifest.json').exists()
    assert 'total' not in json.dumps(manifest['score_vector']).lower()


def test_rerun_into_same_run_id_is_refused(tmp_path):
    providers = [MockProvider(provider_id='mock-a', model_id='mock-ideal-v1')]
    run_comparison(providers, 'CAP-TEST-002', tmp_path)
    with pytest.raises(ValueError, match='append-only'):
        run_comparison(providers, 'CAP-TEST-002', tmp_path)


def test_trace_is_append_only(tmp_path):
    """Direct UPDATE/DELETE on the trace must be refused by the store."""
    providers = [MockProvider(provider_id='mock-a', model_id='mock-ideal-v1')]
    run_comparison(providers, 'CAP-TEST-003', tmp_path)
    store = TraceStore(tmp_path / 'CAP-TEST-003' / 'trace.sqlite')
    with pytest.raises(Exception):
        with store.transaction() as tx:
            tx._connection.execute("UPDATE events SET kind='TAMPERED' WHERE sequence=1")
    verify_events(store.read())


def test_transport_failure_is_not_reported_as_a_parsing_failure():
    """'call never succeeded' must be distinct from 'model answered badly'."""
    score = oracle.adjudicate('A-META-COUNT-ITEMS', None, transport_failed=True)
    assert score.failure_type == 'TRANSPORT_FAILED'
    assert not score.full_pass
    # A genuine malformed answer keeps its own classification.
    assert oracle.adjudicate('A-META-COUNT-ITEMS', b'{broken').failure_type == \
        'UNPARSEABLE_OR_INVALID_FORMAT'


def test_run_with_no_successful_transport_is_marked_invalid(tmp_path):
    """A credential/transport failure must never read as a capability result."""
    from quant_rsi.harness.providers import ProviderReply

    class DeadProvider:
        provider_id = 'dead'
        model_id = 'dead-model'

        def reply(self, task_id, prompt):
            return ProviderReply(False, None, None, 'ProviderError: missing credential',
                                 None, None, 1, 1)

    manifest = run_comparison([DeadProvider()], 'CAP-TEST-006', tmp_path)
    assert manifest['capability_result_valid'] is False
    assert manifest['validity_reason'] == 'ALL_TRANSPORTS_FAILED_NO_CAPABILITY_EVIDENCE'
    assert manifest['score_vector']['dead']['tasks_full_pass'] == 0
    assert set(manifest['score_vector']['dead']['failure_types']) == {'TRANSPORT_FAILED'}
    # The failure reason is preserved rather than swallowed.
    assert 'missing credential' in manifest['records'][0]['transport_error']


def test_partial_transport_failure_still_yields_a_valid_result(tmp_path):
    """If at least one call succeeded, the run is a real (if weak) result."""
    from quant_rsi.harness.providers import ProviderReply

    class FlakyProvider:
        provider_id = 'flaky'
        model_id = 'flaky-model'
        calls = 0

        def reply(self, task_id, prompt):
            FlakyProvider.calls += 1
            if FlakyProvider.calls == 1:
                return ProviderReply(False, None, None, 'TimeoutError: timed out', None, None, 1, 1)
            text = json.dumps(REFERENCE[task_id], sort_keys=True)
            return ProviderReply(True, text, 200, None, 10, 10, 5, 1)

    manifest = run_comparison([FlakyProvider()], 'CAP-TEST-007', tmp_path)
    assert manifest['capability_result_valid'] is True
    assert manifest['validity_reason'] is None
    hist = manifest['score_vector']['flaky']['failure_types']
    assert hist.get('TRANSPORT_FAILED') == 1
    assert hist.get('NONE') == len(TASK_IDS) - 1


def test_score_vector_reports_every_dimension_for_every_provider(tmp_path):
    providers = [MockProvider(provider_id='mock-a', model_id='a'),
                 MockProvider(provider_id='mock-b', model_id='b')]
    manifest = run_comparison(providers, 'CAP-TEST-004', tmp_path)
    dims = [d['id'] for d in oracle.load_fixtures()['capability_dimensions']]
    for pid in ('mock-a', 'mock-b'):
        entry = manifest['score_vector'][pid]
        assert set(entry['by_dimension']) == set(dims)
        assert entry['tasks_assigned'] == len(TASK_IDS)
        # No single total score may be emitted.
        assert 'total_score' not in entry
        assert 'overall' not in entry


def test_repeat_run_detects_output_variance(tmp_path):
    """A deterministic provider must show zero variance across repeats."""
    providers = [MockProvider(provider_id='mock-a', model_id='a')]
    manifest = run_comparison(providers, 'CAP-TEST-005', tmp_path, repeat=2)
    rep = manifest['reproducibility']['mock-a']
    assert rep['output_variance_count'] == 0
    assert rep['tasks_with_identical_output'] == len(TASK_IDS)
    assert manifest['budget_usage']['attempts'] == 2 * len(TASK_IDS)
