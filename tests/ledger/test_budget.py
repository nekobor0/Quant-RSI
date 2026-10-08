from dataclasses import replace
import multiprocessing

import pytest

from quant_rsi.contracts.condition import (
    AgentBenchmarkRun, BenchmarkCondition, BUDGET_DIMENSIONS, RESOURCE_DIMENSIONS,
    TaskContract, decision_digest, load_decisions,
)
from quant_rsi.contracts.research import ConceptMapping, Hypothesis, ExperimentSpec, ScientificSearchFamily
from quant_rsi.ledger.budget import BudgetDenied, SearchBudget
from quant_rsi.ledger.store import TraceStore


def condition(attempts=2):
    return BenchmarkCondition(TaskContract(
        task_id='TASK-synthetic', task_version='v1', target='synthetic', horizon='1d',
        benchmark_ref='zero', universe_ref='synthetic', asof_cutoff='2000-01-01T00:00:00Z',
        execution_timing='next bar', data_spec_hash='a'*64, snapshot_hash='b'*64,
        cleaning_spec_version='v1', split_version='v1', env_version='v1', evaluator_version='v1',
        cost_model_version='COST-synthetic', market_rules_version='v1', calendar_version='v1',
        statistical_protocol_version='STAT-deferred', budget_policy_version='0.2',
        decision_registry_hash=decision_digest(), decision_snapshot_ref='sha256:'+decision_digest(), decision_registry_version=load_decisions()['version'], budget_limits={**dict.fromkeys(BUDGET_DIMENSIONS, 100), 'attempts': attempts},
        memory_limit_mb=64, frozen_at='2000-01-02T00:00:00Z', frozen_by='synthetic custodian'))


def make_run(name, family, c, **changes):
    args = dict(benchmark_run_id=name, scientific_family_id=family, condition_hash=c.condition_hash,
                agent_model='synthetic-'+name, agent_model_version='v1', prompt_hash='c'*64,
                code_hash='d'*64, dependency_hash='e'*64, budget_root_run_id=name,
                registered_at='2000-01-03T00:00:00Z')
    args.update(changes)
    return AgentBenchmarkRun(**args)


def setup(tmp_path, attempts=2):
    service = SearchBudget(TraceStore(tmp_path/'trace.sqlite'))
    c = condition(attempts)
    service.register_concept(ConceptMapping('MAP-synthetic', 'synthetic', 'synthetic', 'synthetic', ('FEAT-synthetic',)))
    service.register_hypothesis(Hypothesis('HYP-synthetic', 'CLAIM-one', 'one synthetic claim', 'reject on mismatch', 'MAP-synthetic'))
    for suffix in ('AAA', 'BBB'):
        family = 'FAM-'+suffix
        service.register_family(ScientificSearchFamily(family, 'CLAIM-one', 'synthetic selection'))
        run = make_run('RUN-'+suffix, family, c)
        service.register_run(run, c, decision_snapshot=load_decisions())
        service.register_experiment(ExperimentSpec('EXP-'+suffix, 'HYP-synthetic', 'TASK-synthetic', 'DATA-'+'a'*64,
            'COST-synthetic', 'STAT-deferred', family, run.benchmark_run_id, '2000-01-04T00:00:00Z'))
    return service, c


def envelope(**changes):
    return dict(attempts=1, candidate_trials=1, model_trials=1, input_tokens=10,
                output_tokens=10, wall_milliseconds=10, cpu_milliseconds=10, **changes)


def resources(value=1):
    return dict.fromkeys(RESOURCE_DIMENSIONS, value)


def zero_resources(**changes):
    return {**resources(0), **changes}


def reserve_candidate(service, suffix='AAA', attempt='ATT-one'):
    return service.reserve('RUN-'+suffix, attempt, envelope(), scientific_variant_id='VAR-'+suffix, experiment_id='EXP-'+suffix)


def contender(path, identity, queue):
    service = SearchBudget(TraceStore(path))
    try:
        service.reserve('RUN-AAA', identity, zero_resources(attempts=1, model_trials=1))
        queue.put('started')
    except BudgetDenied:
        queue.put('denied')


def test_other_agent_budget_untouched_when_A_exhausted_and_claim_pool_counts_both(tmp_path):
    service, c = setup(tmp_path, attempts=1)
    reserve_candidate(service)
    service.settle('ATT-one', 'FAILED', resources(), failure='synthetic falsification')
    with pytest.raises(BudgetDenied, match='EXHAUSTED'):
        service.reserve('RUN-AAA', 'ATT-denied', zero_resources(attempts=1))
    assert service.capability_accounting('RUN-BBB')['usage']['attempts'] == 0
    reserve_candidate(service, 'BBB', 'ATT-two')
    service.settle('ATT-two', 'SUCCEEDED', resources(), artifact_hashes={'synthetic-result': 'f'*64})
    service.register_family(ScientificSearchFamily('FAM-pooled', 'CLAIM-one', 'joint final claim', ('FAM-AAA', 'FAM-BBB')))
    claim = service.scientific_accounting('FAM-pooled')
    assert claim['attempt_count'] == claim['candidate_variant_count'] == 2
    assert claim['effective_independent_trials'] is None
    for name in ('RUN-AAA', 'RUN-BBB'):
        result = service.capability_accounting(name)
        assert result['usage']['attempts'] == 1
        assert result['capability_score'] is None
    assert any(e['kind'] == 'ATTEMPT_DENIED' for e in service.store.read())


def test_atomic_last_slot_across_processes(tmp_path):
    service, _ = setup(tmp_path, attempts=1)
    context = multiprocessing.get_context('spawn')
    queue = context.Queue()
    workers = [context.Process(target=contender, args=(str(service.store.path), f'ATT-race{i}', queue)) for i in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(20)
        assert worker.exitcode == 0
    assert sorted(queue.get(timeout=3) for _ in workers) == ['denied']*3 + ['started']
    assert service.capability_accounting('RUN-AAA')['usage']['attempts'] == 1
    assert len([e for e in service.store.read() if e['kind'] == 'ATTEMPT_DENIED']) == 3


def test_unknown_failure_blocks_until_append_only_reconciliation_and_retry_counts(tmp_path):
    service, _ = setup(tmp_path, attempts=3)
    reserve_candidate(service)
    service.settle('ATT-one', 'TIMEOUT', None, failure='synthetic usage unavailable')
    assert service.capability_accounting('RUN-AAA')['usage']['input_tokens'] == 10
    with pytest.raises(BudgetDenied, match='UNRESOLVED'):
        service.reserve('RUN-AAA', 'ATT-blocked', zero_resources(attempts=1))
    service.reconcile('ATT-one', resources())
    service.reserve('RUN-AAA', 'ATT-retry', zero_resources(attempts=1, retries=1), scientific_variant_id='VAR-AAA', retry_of='ATT-one', experiment_id='EXP-AAA')
    usage = service.capability_accounting('RUN-AAA')['usage']
    assert usage['attempts'] == 2 and usage['retries'] == 1 and usage['candidate_trials'] == 1
    assert service.scientific_accounting('FAM-AAA')['candidate_variant_count'] == 1
    assert len([e for e in service.store.read() if e['kind'] == 'ATTEMPT_SETTLED']) == 1
    assert len([e for e in service.store.read() if e['kind'] == 'USAGE_RECONCILED']) == 1


def test_recovery_preserves_started_attempt_and_reopen_usage(tmp_path):
    service, _ = setup(tmp_path)
    reserve_candidate(service)
    service = SearchBudget(TraceStore(service.store.path))
    assert service.recover_incomplete() == ['ATT-one']
    assert service.recover_incomplete() == []
    assert service.capability_accounting('RUN-AAA')['blocked'] is True
    assert service.capability_accounting('RUN-AAA')['usage']['attempts'] == 1


def test_usage_breach_cannot_be_hidden_or_refunded(tmp_path):
    service, _ = setup(tmp_path)
    reserve_candidate(service)
    service.settle('ATT-one', 'FAILED', resources(11), failure='synthetic resource overrun')
    assert service.capability_accounting('RUN-AAA')['blocked']
    assert service.capability_accounting('RUN-AAA')['usage']['input_tokens'] == 11
    with pytest.raises(ValueError):
        service.settle('ATT-one', 'FAILED', resources(0), failure='hide overrun')
    with pytest.raises(ValueError):
        service.reconcile('ATT-one', resources(0))


def test_idempotent_delivery_collision_and_no_fake_success(tmp_path):
    service, _ = setup(tmp_path)
    first = reserve_candidate(service)
    assert reserve_candidate(service) == first
    with pytest.raises(ValueError, match='collision'):
        service.reserve('RUN-AAA', 'ATT-one', zero_resources(attempts=1))
    with pytest.raises(ValueError):
        service.settle('ATT-one', 'SUCCEEDED', resources())
    with pytest.raises(ValueError):
        service.settle('ATT-missing', 'FAILED', resources(), failure='not started')
    with pytest.raises(ValueError):
        service.reserve('RUN-AAA', 'ATT-unregistered', envelope(), scientific_variant_id='VAR-other')


def test_continuation_inherits_root_and_model_or_family_reset_rejected(tmp_path):
    service, c = setup(tmp_path, attempts=1)
    reserve_candidate(service)
    parent = make_run('RUN-AAA', 'FAM-AAA', c)
    child = replace(parent, benchmark_run_id='RUN-resume', parent_run_id='RUN-AAA')
    service.register_run(child, c, decision_snapshot=load_decisions())
    assert service.capability_accounting('RUN-resume')['usage']['attempts'] == 1
    with pytest.raises(BudgetDenied):
        service.reserve('RUN-resume', 'ATT-resume', zero_resources(attempts=1))
    with pytest.raises(ValueError):
        service.register_run(replace(child, budget_root_run_id='RUN-resume'), c, decision_snapshot=load_decisions())
    with pytest.raises(ValueError):
        service.register_run(replace(child, agent_model='other'), c, decision_snapshot=load_decisions())
    with pytest.raises(ValueError):
        service.register_run(replace(child, scientific_family_id='FAM-BBB'), c, decision_snapshot=load_decisions())


def test_family_diamond_deduplicates_attempts_and_immutable_parent_history(tmp_path):
    service, _ = setup(tmp_path)
    reserve_candidate(service)
    for name in ('FAM-left', 'FAM-right'):
        service.register_family(ScientificSearchFamily(name, 'CLAIM-one', 'synthetic', ('FAM-AAA',)))
    merged = ScientificSearchFamily('FAM-diamond', 'CLAIM-one', 'joint', ('FAM-left', 'FAM-right'))
    service.register_family(merged)
    assert service.scientific_accounting('FAM-diamond')['attempt_count'] == 1
    with pytest.raises(ValueError):
        service.register_family(replace(merged, parent_family_ids=()))


@pytest.mark.parametrize('bad', [-1, True, 1.5, float('nan')])
def test_invalid_usage_rejected_before_dispatch(tmp_path, bad):
    service, _ = setup(tmp_path)
    with pytest.raises(ValueError):
        service.reserve('RUN-AAA', 'ATT-bad', {'attempts': 1, 'input_tokens': bad})
    assert service.capability_accounting('RUN-AAA')['usage']['attempts'] == 0


def test_condition_drift_and_posthoc_experiment_rejected(tmp_path):
    service, c = setup(tmp_path)
    run = make_run('RUN-new', 'FAM-AAA', c)
    with pytest.raises(ValueError):
        service.register_run(run, BenchmarkCondition(replace(c.task, horizon='2d')), decision_snapshot=load_decisions())
    spec = ExperimentSpec('EXP-bad', 'HYP-synthetic', 'TASK-other', 'DATA-'+'a'*64,
                         'COST-synthetic', 'STAT-deferred', 'FAM-AAA', 'RUN-AAA', '2000-01-04T00:00:00Z')
    with pytest.raises(ValueError):
        service.register_experiment(spec)


def test_critic_K01_missing_resource_envelope_must_not_start(tmp_path):
    service, _ = setup(tmp_path)
    with pytest.raises(ValueError, match='resource'):
        service.reserve('RUN-AAA', 'ATT-omitted', {'attempts': 1, 'model_trials': 1})


def test_critic_K02_orphan_hypothesis_must_not_register(tmp_path):
    service, _ = setup(tmp_path)
    orphan = ExperimentSpec('EXP-orphan', 'HYP-not-registered', 'TASK-synthetic', 'DATA-'+'a'*64,
                            'COST-synthetic', 'STAT-deferred', 'FAM-AAA', 'RUN-AAA', '2000-01-04T00:00:00Z')
    with pytest.raises(ValueError, match='hypothesis'):
        service.register_experiment(orphan)


def test_critic_K03_future_registered_at_must_not_register(tmp_path):
    service, c = setup(tmp_path)
    future = make_run('RUN-future', 'FAM-AAA', c, registered_at='2999-01-01T00:00:00Z')
    with pytest.raises(ValueError, match='future'):
        service.register_run(future, c, decision_snapshot=load_decisions())


def test_research_registration_enforces_concept_claim_and_immutability(tmp_path):
    service, _ = setup(tmp_path)
    with pytest.raises(ValueError, match='concept'):
        service.register_hypothesis(Hypothesis('HYP-orphan', 'CLAIM-new', 'one claim', 'test rejects', 'MAP-missing'))
    with pytest.raises(ValueError, match='another hypothesis'):
        service.register_hypothesis(Hypothesis('HYP-duplicate', 'CLAIM-one', 'one claim', 'test rejects', 'MAP-synthetic'))
    with pytest.raises(ValueError, match='collision'):
        service.register_hypothesis(Hypothesis('HYP-synthetic', 'CLAIM-one', 'changed claim', 'test rejects', 'MAP-synthetic'))
    with pytest.raises(ValueError, match='claim'):
        service.register_family(ScientificSearchFamily('FAM-orphan', 'CLAIM-missing', 'synthetic'))
    service.register_hypothesis(Hypothesis('HYP-other', 'CLAIM-other', 'another claim', 'test rejects', 'MAP-synthetic'))
    spec = ExperimentSpec('EXP-mismatched', 'HYP-other', 'TASK-synthetic', 'DATA-'+'a'*64,
                         'COST-synthetic', 'STAT-deferred', 'FAM-AAA', 'RUN-AAA', '2000-01-04T00:00:00Z')
    with pytest.raises(ValueError, match='hypothesis'):
        service.register_experiment(spec)


def test_stage_A_contracts_to_trace_runtime_evidence(tmp_path, monkeypatch):
    """Retain Stage A accounting assertions using the corrected A1 lineage fixture."""
    from test_provenance import synthetic_flow
    flow = synthetic_flow(tmp_path/'runtime', extra_run=True)
    service = flow['service']
    assert service.capability_accounting('RUN-AAA')['usage']['attempts'] == 1
    assert service.capability_accounting('RUN-BBB')['usage']['attempts'] == 1
    assert service.scientific_accounting('FAM-pooled')['attempt_count'] == 2
    assert flow['experiment'].execution_started_at is None


def test_A1_red_preregistered_evidence_needs_trace_lineage():
    from quant_rsi.contracts.research import Candidate
    assert 'attempt_id' in Candidate.__dataclass_fields__


def test_A1_red_run_manifest_contract_exists():
    from quant_rsi.contracts.manifest import RunManifest
    assert 'attempt_id' in RunManifest.__dataclass_fields__
