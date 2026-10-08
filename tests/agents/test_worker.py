from dataclasses import FrozenInstanceError, replace
import json

import pytest

from quant_rsi.agents.worker import FakeProvider, WorkerRequest, WorkerResponse, invoke
from quant_rsi.contracts.condition import (
    AgentBenchmarkRun, BenchmarkCondition, BUDGET_DIMENSIONS, RESOURCE_DIMENSIONS,
    TaskContract, decision_digest, load_decisions,
)
from quant_rsi.contracts.research import ConceptMapping, Hypothesis, ScientificSearchFamily
from quant_rsi.ledger.budget import BudgetDenied, SearchBudget
from quant_rsi.ledger.store import TraceStore


def resources(value=1):
    return dict.fromkeys(RESOURCE_DIMENSIONS, value)


@pytest.fixture
def service(tmp_path):
    task = TaskContract(
        task_id='TASK-synthetic', task_version='v1', target='synthetic', horizon='1d',
        benchmark_ref='zero', universe_ref='synthetic', asof_cutoff='2000-01-01T00:00:00Z',
        execution_timing='next bar', data_spec_hash='a'*64, snapshot_hash='b'*64,
        cleaning_spec_version='v1', split_version='v1', env_version='v1', evaluator_version='v1',
        cost_model_version='COST-synthetic', market_rules_version='v1', calendar_version='v1',
        statistical_protocol_version='STAT-deferred', budget_policy_version='0.2',
        decision_registry_hash=decision_digest(), decision_snapshot_ref='sha256:'+decision_digest(),
        decision_registry_version=load_decisions()['version'],
        budget_limits={**dict.fromkeys(BUDGET_DIMENSIONS, 100), 'attempts': 2},
        memory_limit_mb=64, frozen_at='2000-01-02T00:00:00Z', frozen_by='synthetic custodian')
    condition = BenchmarkCondition(task)
    budget = SearchBudget(TraceStore(tmp_path/'trace.sqlite'))
    budget.register_concept(ConceptMapping('MAP-one', 'synthetic', 'synthetic', 'synthetic', ('FEAT-one',)))
    budget.register_hypothesis(Hypothesis('HYP-one', 'CLAIM-one', 'synthetic claim', 'mismatch', 'MAP-one'))
    budget.register_family(ScientificSearchFamily('FAM-one', 'CLAIM-one', 'synthetic'))
    budget.register_run(AgentBenchmarkRun('RUN-one', 'FAM-one', condition.condition_hash,
        'fake-model', None, 'c'*64, 'd'*64, 'e'*64, 'RUN-one', '2000-01-03T00:00:00Z',
        provider='fake'), condition, decision_snapshot=load_decisions())
    return budget


def request():
    return WorkerRequest('RUN-one', 'ACT-author', 'CTX-author', 'fake', 'fake-model', None,
                         'c'*64, 'd'*64, ('frozen-env-v1',), {'operation': 'a'*64})


def prepare(service, req, provider, attempt='ATT-one'):
    service.reserve(req.run_id, attempt, dict(resources(10), attempts=1, model_trials=1))
    service.store.append('worker-binding:'+attempt, 'WORKER_DISPATCH_BOUND', dict(
        attempt_id=attempt, request=req.to_dict(), provider_digest=provider.content_digest()))


def test_success_frozen_provenance_and_idempotent_delivery(service):
    req, fake = request(), FakeProvider(b'{"operation":"frozen"}', reported_usage=resources())
    prepare(service, req, fake)
    before = service.capability_accounting(req.run_id)
    first = invoke(req, fake, budget=service, attempt_id='ATT-one')
    count = len(service.store.read())
    assert invoke(req, fake, budget=service, attempt_id='ATT-one') == first
    assert len(service.store.read()) == count
    assert service.capability_accounting(req.run_id) == before
    assert first.output == fake.response and first.status == 'SUCCEEDED'
    assert first.actual_resources == resources() and first.supervisor_measured_usage is None
    assert first.usage_source == 'provider_reported'
    assert WorkerResponse.from_dict(json.loads(json.dumps(first.to_dict()))) == first
    assert WorkerRequest.from_dict(req.to_dict()) == req
    events = service.store.read()
    assert [e['kind'] for e in events[-2:]] == ['WORKER_REQUEST', 'WORKER_RESPONSE']
    assert events[-2]['payload']['request'] == req.to_dict()
    assert events[-1]['payload']['response']['output_hash'] == first.output_hash
    with pytest.raises(FrozenInstanceError):
        first.output = b'changed'
    with pytest.raises(TypeError):
        first.actual_resources['input_tokens'] = 0
    service.settle('ATT-one', 'SUCCEEDED', first.actual_resources, artifact_hashes={'response': first.output_hash})
    with pytest.raises(ValueError, match='terminal'):
        invoke(req, fake, budget=service, attempt_id='ATT-one')


@pytest.mark.parametrize('mode,status', [('timeout', 'TIMEOUT'), ('failure', 'FAILED'),
    ('malformed', 'MALFORMED'), ('unknown_usage', 'UNKNOWN_USAGE'), ('success', 'UNKNOWN_USAGE')])
def test_outcomes_preserve_bytes_errors_and_unknown_budget(service, mode, status):
    req, fake = request(), FakeProvider(b'\xfffrozen', mode=mode)
    prepare(service, req, fake)
    response = invoke(req, fake, budget=service, attempt_id='ATT-one')
    assert response.status == status and response.output == fake.response
    assert response.actual_resources is None and response.usage_source == 'unknown'
    assert response.error_metadata['code'] == status
    service.settle('ATT-one', 'TIMEOUT' if mode == 'timeout' else 'FAILED', None, failure=status)
    assert service.capability_accounting(req.run_id)['usage']['input_tokens'] == 10
    with pytest.raises(BudgetDenied, match='UNRESOLVED'):
        service.reserve(req.run_id, 'ATT-next', dict(resources(10), attempts=1))


@pytest.mark.parametrize('randomness', ['fixed_seed_deterministic', 'externally_nondeterministic',
                                      'provider_randomness_unknown'])
def test_randomness_is_declaration_not_fake_measurement(service, randomness):
    req, fake = request(), FakeProvider(b'frozen', reported_usage=resources(), randomness=randomness)
    prepare(service, req, fake)
    result = invoke(req, fake, budget=service, attempt_id='ATT-one')
    assert result.randomness == randomness and result.supervisor_measured_usage is None


def test_no_dispatch_without_reservation_or_binding(service):
    req, fake = request(), FakeProvider(b'frozen')
    before = service.store.read()
    with pytest.raises(ValueError, match='ATTEMPT_STARTED'):
        invoke(req, fake, budget=service, attempt_id='ATT-one')
    assert service.store.read() == before
    service.reserve(req.run_id, 'ATT-one', dict(resources(10), attempts=1, model_trials=1))
    with pytest.raises(ValueError, match='metadata binding'):
        invoke(req, fake, budget=service, attempt_id='ATT-one')
    assert not any(e['kind'] == 'WORKER_REQUEST' for e in service.store.read())


@pytest.mark.parametrize('change', [dict(run_id='RUN-other'), dict(actor_id='ACT-other'),
    dict(context_id='CTX-other'), dict(provider='real'), dict(model_id='different'),
    dict(model_version='v2'), dict(prompt_hash='f'*64), dict(policy_hash='f'*64),
    dict(tools=()), dict(input_hashes={'operation':'f'*64})])
def test_all_identity_and_configuration_drift_rejected(service, change):
    req, fake = request(), FakeProvider(b'frozen')
    prepare(service, req, fake)
    before = service.store.read()
    with pytest.raises(ValueError):
        invoke(replace(req, **change), fake, budget=service, attempt_id='ATT-one')
    assert service.store.read() == before


def test_callback_subclass_provider_and_fixture_drift_rejected(service):
    class PretendFake(FakeProvider):
        pass
    req, fake = request(), FakeProvider(b'frozen')
    prepare(service, req, fake)
    for provider in (lambda: b'unsafe', PretendFake(b'frozen'), FakeProvider(b'new')):
        with pytest.raises(ValueError):
            invoke(req, provider, budget=service, attempt_id='ATT-one')
    assert not any(e['kind'] == 'WORKER_REQUEST' for e in service.store.read())


@pytest.mark.parametrize('usage', [{}, {'input_tokens': 1}, resources(-1), resources(True), resources(1.5)])
def test_invalid_usage_cannot_be_disguised(usage):
    with pytest.raises(ValueError):
        FakeProvider(b'frozen', reported_usage=usage)


def test_input_and_provider_nested_immutability():
    hashes, usage = {'operation': 'a'*64}, resources()
    req = replace(request(), input_hashes=hashes)
    fake = FakeProvider(b'frozen', reported_usage=usage)
    hashes['operation'], usage['input_tokens'] = 'b'*64, 999
    assert req.input_hashes['operation'] == 'a'*64 and fake.reported_usage['input_tokens'] == 1
    with pytest.raises(ValueError):
        FakeProvider(bytearray(b'frozen'))
