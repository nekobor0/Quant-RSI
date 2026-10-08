"""Small B2 engineering fixtures only; not W15 calibration or strategy search."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import json
import os
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'data'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'env'))
from test_pit import dataset, record
from test_daily import fixture, order

from quant_rsi.agents.worker import FakeProvider, WorkerRequest
from quant_rsi.agents.critic import Issue, ReviewIdentity, review
from quant_rsi.contracts.condition import AgentBenchmarkRun, BenchmarkCondition, RESOURCE_DIMENSIONS, load_decisions
from quant_rsi.contracts.research import ConceptMapping, Hypothesis, ScientificSearchFamily, ExperimentSpec
from quant_rsi.data.pit import canonical_bytes
from quant_rsi.eval.gates import VERSION, evaluate, pit_observations
from quant_rsi.eval.replay import installed_code_bundle, dependency_lock
from quant_rsi.ledger.budget import SearchBudget
from quant_rsi.ledger.store import TraceStore
from quant_rsi.orchestration.runner import run_once


def build_case(root, mode='success', randomness='fixed_seed_deterministic', issues=(), task_updates=None):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    rows = [record()] + [record(kind=k, value=v) for k, v in (
        ('ST', False), ('board', 'MAIN'), ('venue', 'X'), ('suspended', False), ('lagged_ADV', '100000'))]
    rows.append(record(kind='ST', value=True, revision='r2', available='2000-02-01T00:00:00Z'))
    task, data, snapshot, artifacts = dataset(rows)
    task = replace(task, **{'evaluator_version': VERSION, **(task_updates or {})})
    _, _, environment = fixture()
    environment['orders'] = [order(3, 'buy', 300), order(4, 'sell', 100)]
    environment['bars'][environment['sessions'][2]]['AAA'].pop('certified_open_volume')
    seed = 7 if randomness == 'fixed_seed_deterministic' else None
    operation = dict(operation='synthetic-daily-v1', comparison='exact', randomness=randomness,
                     seed=seed, environment=environment)
    artifacts.update({'environment-input.json': canonical_bytes(operation),
        'prompt.txt': b'fixed synthetic B2 operation; no search',
        'code-tree.json': canonical_bytes(installed_code_bundle()),
        'dependencies.json': canonical_bytes(dependency_lock()),
        'DATA-' + data.content_hash(): data.to_json().encode(),
        'SNAPSHOT-' + snapshot.content_hash(): snapshot.to_json().encode()})
    artifacts['pit-observations.json'] = canonical_bytes(pit_observations(
        task, data, snapshot, artifacts.__getitem__, environment))
    condition = BenchmarkCondition(task)
    store = TraceStore(root / 'trace.sqlite')
    budget = SearchBudget(store)
    budget.register_concept(ConceptMapping('MAP-B2', 'engineering conformance', 'fixed values', 'fixture', ('FEAT-B2',)))
    budget.register_hypothesis(Hypothesis('HYP-B2', 'CLAIM-B2', 'frozen operation conforms', 'invariant fails', 'MAP-B2'))
    budget.register_family(ScientificSearchFamily('FAM-B2', 'CLAIM-B2', 'synthetic engineering fixture only'))
    hashes = {k: sha256(v).hexdigest() for k, v in artifacts.items()}
    run = AgentBenchmarkRun('RUN-B2', 'FAM-B2', condition.condition_hash, 'fake-fixed', 'B2-v1',
        hashes['prompt.txt'], hashes['code-tree.json'], hashes['dependencies.json'], 'RUN-B2',
        '2000-01-03T00:00:00Z', provider='fake')
    budget.register_run(run, condition, decision_snapshot=load_decisions())
    experiment = ExperimentSpec('EXP-B2', 'HYP-B2', task.task_id, 'DATA-' + data.content_hash(),
        task.cost_model_version, task.statistical_protocol_version, 'FAM-B2', 'RUN-B2', '2000-01-04T00:00:00Z')
    budget.register_experiment(experiment)
    author = ReviewIdentity('AUTHOR-B2', 'CONTEXT-author', 'RUN-B2', 'candidate_author')
    critic = ReviewIdentity('CRITIC-B2', 'CONTEXT-critic', 'REVIEW-B2', 'critic')
    request = WorkerRequest(run.benchmark_run_id, author.actor_id, author.context_id, run.provider,
        run.agent_model, run.agent_model_version, run.prompt_hash, sha256(b'fixed-policy').hexdigest(),
        ('synthetic-daily-v1',), hashes)
    provider = FakeProvider(artifacts['environment-input.json'], mode=mode, randomness=randomness,
                            reported_usage=None if mode == 'unknown_usage' else dict.fromkeys(RESOURCE_DIMENSIONS, 1))
    args = dict(budget=budget, run_id=run.benchmark_run_id, experiment_id=experiment.experiment_id,
        delivery_id='DEL-B2', attempt_id='ATT-B2', scientific_variant_id='VAR-B2', candidate_id='CAN-B2',
        evidence_id='EVI-B2', manifest_id='MAN-B2',
        envelope=dict(attempts=1, candidate_trials=1, model_trials=1, **dict.fromkeys(RESOURCE_DIMENSIONS, 10)),
        request=request, provider=provider, artifacts=artifacts, author=author, critic=critic, issues=issues)
    outcome = run_once(**args)
    return dict(**outcome, outcome=outcome, store=store, artifacts=artifacts, task=task, condition=condition,
                run=run, budget=budget, author=author, critic=critic, data=data, snapshot=snapshot,
                experiment=experiment, execution_args=args)


def test_clean_engineering_path_formal_block_and_capture(tmp_path):
    b = build_case(tmp_path)
    out = b['eval_result']
    assert b['status'] == 'EVALUATED'
    assert out.engineering_conformance == 'PASS' and out.formal_verdict == 'BLOCKED'
    assert out.gates['G4']['reason'] == 'D04B_NOT_FROZEN'
    assert out.gates['G6']['reason'] == 'BENCHMARK_GRADE_SEALED_INFRASTRUCTURE_ABSENT'
    trace = b['store'].read()
    kinds = [e['kind'] for e in trace]
    assert kinds.index('ATTEMPT_STARTED') < kinds.index('WORKER_DISPATCH_BOUND') < kinds.index('WORKER_REQUEST')
    assert kinds.index('WORKER_RESPONSE') < kinds.index('ATTEMPT_SETTLED') < kinds.index('EXECUTION_MANIFEST_COMPLETED')
    assert kinds.index('EXECUTION_MANIFEST_COMPLETED') < kinds.index('ADMISSION_GRANTED') < kinds.index('EVALUATION_COMPLETED')
    assert sum(k == 'ATTEMPT_STARTED' for k in kinds) == 1
    assert 'evaluation:ATT-B2' not in b['manifest'].trace_refs
    assert b['artifacts']['MAN-B2'] == canonical_bytes(b['manifest'].to_dict())
    capture = os.environ.get('QUANT_RSI_B2_CAPTURE_DIR')
    if capture:
        target = Path(capture)
        target.mkdir(parents=True, exist_ok=True)
        values = {'trace': trace, 'result': b['result'],
                  'worker-provenance': [e for e in trace if e['kind'].startswith('WORKER_')],
                  'artifact-bytes': {k: v.hex() for k, v in b['artifacts'].items()}}
        values.update({k: b[k].to_dict() for k in ('manifest', 'candidate', 'evidence', 'critic_report')})
        values['eval'] = out.to_dict()
        for name, value in values.items():
            (target / (name + '.json')).write_text(json.dumps(value, indent=2), encoding='utf-8')


@pytest.mark.parametrize('mode,status', [('timeout', 'TIMEOUT'), ('failure', 'FAILED'),
                                        ('malformed', 'FAILED'), ('unknown_usage', 'FAILED')])
def test_worker_terminal_paths_preserve_resource_truth(tmp_path, mode, status):
    b = build_case(tmp_path, mode=mode)
    assert b['status'] == status and b['manifest'] is None and b['eval_result'] is None
    terminal = next(e['payload'] for e in b['store'].read() if e['kind'] == 'ATTEMPT_SETTLED')
    assert terminal['status'] == status and terminal['failure']
    assert b['budget'].capability_accounting('RUN-B2')['usage']['attempts'] == 1
    if mode == 'unknown_usage':
        assert terminal['actual_resources'] is None and terminal['usage_state'] == 'UNKNOWN'
        assert b['budget'].capability_accounting('RUN-B2')['blocked']
    else:
        assert terminal['actual_resources'] == dict.fromkeys(RESOURCE_DIMENSIONS, 1)


def test_critic_reject_keeps_successful_compute_without_evaluation(tmp_path):
    issue = Issue('ISS-B2', 'P1', ('EVI-B2',), 'Synthetic issue backed by this evidence', 'New reviewed evidence required')
    b = build_case(tmp_path, issues=(issue,))
    assert b['status'] == 'ADMISSION_BLOCKED' and b['eval_result'] is None
    trace = b['store'].read()
    assert next(e['payload']['status'] for e in trace if e['kind'] == 'ATTEMPT_SETTLED') == 'SUCCEEDED'
    assert any(e['kind'] == 'ADMISSION_BLOCKED' for e in trace)
    assert not any(e['kind'] == 'EVALUATION_COMPLETED' for e in trace)


@pytest.mark.parametrize('attack', ['dangling', 'fabricated'])
def test_evidence_attack_blocks_g7(tmp_path, attack):
    b = build_case(tmp_path)
    manifest, report = b['manifest'], b['critic_report']
    if attack == 'dangling':
        del b['artifacts']['EVI-B2']
    else:
        forged = replace(b['evidence'], metrics={'synthetic_final_nav': 123456789})
        b['artifacts']['EVI-B2'] = canonical_bytes(forged.to_dict())
        manifest = replace(manifest, evidence_hashes={'EVI-B2': forged.content_digest()})
        report = review(b['candidate'], [forged], author=b['author'], critic=b['critic'])
    result = evaluate(manifest, expected_manifest_digest=manifest.manifest_digest, trace_store=b['store'],
        resolve_artifact=b['artifacts'].__getitem__, critic_report=report, author=b['author'], critic=b['critic'],
        created_at=manifest.created_at)
    assert result.gates['G7']['status'] == 'BLOCK' and result.formal_verdict == 'BLOCKED'


@pytest.mark.parametrize('randomness', ['externally_nondeterministic', 'provider_randomness_unknown'])
def test_nondeterministic_declaration_blocks_g2(tmp_path, randomness):
    b = build_case(tmp_path, randomness=randomness)
    assert b['eval_result'].gates['G2']['status'] == 'BLOCK'
    assert b['eval_result'].formal_verdict == 'BLOCKED'
