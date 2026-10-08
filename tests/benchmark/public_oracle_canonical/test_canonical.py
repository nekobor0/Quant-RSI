import json
from pathlib import Path

import pytest

from quant_rsi.agents.critic import CriticReport
from quant_rsi.benchmark_public.canonical import run_canonical
from quant_rsi.contracts.condition import (AgentBenchmarkRun, BenchmarkCondition, BUDGET_DIMENSIONS,
    TaskContract, decision_digest, load_decisions)
from quant_rsi.contracts.evaluation import EvalResult
from quant_rsi.contracts.manifest import RunManifest
from quant_rsi.contracts.research import (Candidate, ConceptMapping, Evidence, ExperimentSpec,
    Hypothesis, ScientificSearchFamily)
from quant_rsi.eval.gates import evaluate_public
from quant_rsi.ledger.budget import SearchBudget
from quant_rsi.ledger.store import TraceStore

ROOT = Path(__file__).resolve().parents[3]


def artifacts(path):
    index = json.loads((path / 'artifact_index.json').read_text(encoding='utf-8'))
    return {ref: (path / row['path']).read_bytes() for ref, row in index.items()}


def public_budget(path):
    budget = SearchBudget(TraceStore(path / 'trace.sqlite'))
    task = TaskContract('TASK-public', 'v1', 'public', 'one fixture', 'zero', 'public',
        '2000-01-10T00:00:00Z', 'scripted', 'a'*64, 'b'*64, 'PUBLIC', 'PUBLIC',
        'PUBLIC', 'C2-public-v1', 'PUBLIC', 'SYNTHETIC', 'SYNTHETIC', 'DEFERRED-D04B',
        '0.2', decision_digest(), {**dict.fromkeys(BUDGET_DIMENSIONS, 100)}, 128,
        '2000-01-02T00:00:00Z', 'public-custodian',
        decision_snapshot_ref='sha256:' + decision_digest(),
        decision_registry_version=load_decisions()['version'])
    condition = BenchmarkCondition(task)
    budget.register_concept(ConceptMapping('MAP-public', 'public', 'visible', 'fixture', ('FEAT-public',)))
    budget.register_hypothesis(Hypothesis('HYP-public', 'CLAIM-public', 'public', 'mismatch', 'MAP-public'))
    for suffix in ('AAA', 'BBB'):
        family = 'FAM-' + suffix
        run = 'RUN-' + suffix
        budget.register_family(ScientificSearchFamily(family, 'CLAIM-public', 'public engineering'))
        budget.register_run(AgentBenchmarkRun(run, family, condition.condition_hash,
            'fake-public', 'v1', 'c'*64, 'd'*64, 'e'*64, run,
            '2000-01-03T00:00:00Z', provider='fake'), condition, decision_snapshot=load_decisions())
        budget.register_experiment(ExperimentSpec('EXP-' + suffix, 'HYP-public', 'TASK-public',
            'DATA-' + 'a'*64, 'PUBLIC', 'DEFERRED-D04B', family, run,
            '2000-01-04T00:00:00Z'))
    return budget


def envelope(candidate_trials=0):
    return dict(attempts=1, candidate_trials=candidate_trials, model_trials=1,
                input_tokens=0, output_tokens=0, wall_milliseconds=10, cpu_milliseconds=10)


def test_public_budget_typed_branch_and_fail_closed(tmp_path):
    budget = public_budget(tmp_path)
    with pytest.raises(ValueError, match='reserved'):
        budget.record_output('ATT-missing', 'CAN-missing', 'raw.json', 'f'*64, kind='PUBLIC_FIXTURE')
    started = budget.reserve('RUN-AAA', 'ATT-public', envelope(), experiment_id='EXP-AAA')
    assert started['kind'] == 'ATTEMPT_STARTED'
    assert started['payload']['scientific_variant_id'] is None
    assert started['payload']['envelope']['candidate_trials'] == 0
    budget.record_output('ATT-public', 'CAN-public', 'raw.json', 'f'*64, kind='PUBLIC_FIXTURE')
    with pytest.raises(ValueError, match='one candidate output'):
        budget.record_output('ATT-public', 'CAN-public', 'raw.json', 'f'*64, kind='PUBLIC_FIXTURE')
    with pytest.raises(ValueError, match='one candidate output'):
        budget.record_output('ATT-public', 'CAN-second', 'raw2.json', 'e'*64, kind='PUBLIC_FIXTURE')
    with pytest.raises(ValueError, match='scientific output'):
        budget.record_output('ATT-public', 'CAN-strategy', 'raw2.json', 'e'*64, kind='STRATEGY')
    budget.settle('ATT-public', 'SUCCEEDED', dict(input_tokens=0, output_tokens=0,
        wall_milliseconds=0, cpu_milliseconds=0), artifact_hashes={'raw.json': 'f'*64})
    with pytest.raises(ValueError, match='open reserved'):
        budget.record_output('ATT-public', 'CAN-late', 'raw2.json', 'e'*64, kind='PUBLIC_FIXTURE')
    with pytest.raises(ValueError, match='open reserved'):
        budget.record_output('ATT-public', 'CAN-public', 'raw.json', 'f'*64, kind='PUBLIC_FIXTURE')
    budget.reserve('RUN-AAA', 'ATT-mismatch', envelope(), experiment_id='EXP-BBB')
    with pytest.raises(ValueError, match='run/experiment'):
        budget.record_output('ATT-mismatch', 'CAN-mismatch', 'raw.json', 'f'*64, kind='PUBLIC_FIXTURE')
    budget.reserve('RUN-BBB', 'ATT-scientific', envelope(1), scientific_variant_id='VAR-BBB',
                   experiment_id='EXP-BBB')
    with pytest.raises(ValueError, match='zero-trial'):
        budget.record_output('ATT-scientific', 'CAN-escape', 'raw.json', 'f'*64, kind='PUBLIC_FIXTURE')
    budget.record_output('ATT-scientific', 'CAN-scientific', 'raw.json', 'f'*64, kind='STRATEGY')
    assert budget.capability_accounting('RUN-AAA')['usage']['candidate_trials'] == 0
    assert budget.capability_accounting('RUN-BBB')['usage']['candidate_trials'] == 1
    assert budget.scientific_accounting('FAM-AAA')['candidate_variant_count'] == 0


def test_four_tiers_canonical_objects_transfer_and_gates(tmp_path):
    cases = [('T1', 'base'), ('T2', 'base'), ('T3', 'base'),
             ('T3', 'positive_transfer'), ('T4', 'base'), ('T4', 'refusal')]
    results = {}
    for tier, variant in cases:
        path = tmp_path / f'{tier}-{variant}'
        row = run_canonical(tier=tier, variant=variant, policy='correct', output_root=path)
        files = artifacts(path)
        candidate = Candidate.from_dict(json.loads(files[row['candidate_ref']]))
        evidence = Evidence.from_dict(json.loads(files[row['evidence_ref']]))
        manifest = RunManifest.from_dict(json.loads(files[row['manifest_ref']]))
        evaluated = EvalResult.from_dict(json.loads(files[row['eval_result_ref']]))
        events = TraceStore(path / 'trace.sqlite').read()
        assert row['assigned_denominator'] == 1 and row['scientific_candidate_trials'] == 0
        assert row['scientific_variant_count'] == 0 and row['formal_verdict'] == 'BLOCKED'
        assert candidate.kind == evidence.kind == 'PUBLIC_FIXTURE'
        assert candidate.candidate_id in manifest.candidate_hashes
        assert evidence.evidence_id in manifest.evidence_hashes
        assert evaluated.research_behavior_metrics['public_oracle_full_pass'] is True
        assert all(evaluated.gates[g]['status'] == 'PASS' for g in ('G0', 'G1', 'G3', 'G5', 'G7'))
        assert evaluated.gates['G4']['status'] == evaluated.gates['G6']['status'] == 'BLOCK'
        assert evaluated.gates['G2']['status'] == 'BLOCK'
        assert any(e['kind'] == 'ATTEMPT_OUTPUT' for e in events)
        assert next(e for e in events if e['kind'] == 'ATTEMPT_STARTED')['payload']['scientific_variant_id'] is None
        output_record = json.loads(files[candidate.artifact_ref])
        results[(tier, variant)] = dict(release=json.loads(files['public-input.json']),
                                        output=json.loads(bytes.fromhex(output_record['response_hex'])))
    assert results[('T3', 'base')]['output']['terminal'] == 'REFUSE'
    assert results[('T3', 'positive_transfer')]['output']['terminal'] == 'PROMOTE'
    assert results[('T4', 'refusal')]['output']['terminal'] == 'REFUSE'
    assert results[('T4', 'refusal')]['output']['reason'] == 'INSUFFICIENT_SUPPORT'
    assert 'ATTEMPT_OUTPUT' not in (ROOT / 'src/quant_rsi/orchestration/runner.py').read_text(encoding='utf-8')
    assert 'ATTEMPT_OUTPUT' not in (ROOT / 'src/quant_rsi/benchmark_public/canonical.py').read_text(encoding='utf-8')


def test_distinct_public_terminal_diagnostics(tmp_path):
    policies = {'fabricated_evidence': 'FABRICATED_EVIDENCE',
                'unjustified_refusal': 'UNJUSTIFIED_REFUSAL',
                'invalid_format': 'INVALID_FORMAT', 'timeout': 'TIMEOUT',
                'critic_rejection': 'CRITIC_REJECTION'}
    for policy, expected in policies.items():
        row = run_canonical(tier='T4', variant='base', policy=policy,
                            output_root=tmp_path / policy)
        assert row['diagnostic'] == expected
        assert row['assigned_denominator'] == 1
        evaluated = EvalResult.from_dict(json.loads(artifacts(tmp_path / policy)[row['eval_result_ref']]))
        assert evaluated.gates['G3']['status'] == 'PASS'
    unregistered = run_canonical(tier='T4', variant='unregistered_oracle', policy='correct',
                                 output_root=tmp_path / 'unregistered')
    assert unregistered['diagnostic'] == 'EVALUATOR_BLOCK'
    path = tmp_path / 'evaluator-block'
    row = run_canonical(tier='T4', variant='base', policy='correct', output_root=path)
    files = artifacts(path)
    manifest = RunManifest.from_dict(json.loads(files[row['manifest_ref']]))
    report = CriticReport.from_dict(json.loads(files['critic:' +
        next(e for e in TraceStore(path/'trace.sqlite').read() if e['kind']=='ADMISSION_GRANTED')['payload']['critic_report_digest']]))
    blocked = evaluate_public(manifest, expected_manifest_digest='0'*64,
        trace_store=TraceStore(path/'trace.sqlite'), resolve_artifact=files.__getitem__,
        critic_report=report, author=report.author, critic=report.critic,
        created_at='2026-09-30T00:00:00Z')
    assert blocked.research_behavior_metrics['terminal_diagnostic'] == 'EVALUATOR_BLOCK'
    assert blocked.formal_verdict == 'BLOCKED'
