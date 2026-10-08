"""C2 public fixture builder; canonical objects remain owned by the Harness."""
from hashlib import sha256
from pathlib import Path
import json
import runpy
import sys
import yaml

from quant_rsi.agents.critic import Issue, ReviewIdentity
from quant_rsi.agents.worker import FakeProvider, WorkerRequest
from quant_rsi.contracts.condition import (AgentBenchmarkRun, BenchmarkCondition,
    BUDGET_DIMENSIONS, TaskContract, decision_digest, load_decisions)
from quant_rsi.contracts.data import DataSpec, SnapshotFile, SnapshotManifest
from quant_rsi.contracts.research import ConceptMapping, ExperimentSpec, Hypothesis, ScientificSearchFamily
from quant_rsi.data.pit import canonical_bytes
from quant_rsi.ledger.budget import SearchBudget
from quant_rsi.ledger.store import TraceStore
from quant_rsi.orchestration.runner import run_public_once

ROOT = Path(__file__).resolve().parents[3]
PILOT = ROOT / 'benchmark/public_oracle_pilot/PROTOTYPES.yaml'


def _hash(raw):
    return sha256(raw).hexdigest()


def _t4_worker(data):
    # The oracle is a separately frozen literal table, not this selection code.
    winner = max(sorted(data['observations']), key=lambda key: data['observations'][key])
    if data['observations'][winner] < data['minimum_support']:
        return dict(terminal='REFUSE', hypothesis=None, evidence={},
                    falsification=data['falsification_rule'], reason='INSUFFICIENT_SUPPORT')
    other = next(key for key in data['observations'] if key != winner)
    return dict(terminal='PROMOTE', hypothesis=winner,
                evidence=dict(observation_id=winner, support=data['observations'][winner],
                              competing_support=data['observations'][other]),
                falsification=data['falsification_rule'], reason=None)


def _case(tier, variant):
    bindings = yaml.safe_load((ROOT / 'benchmark/public_oracle_canonical/BENCHMARK_TASK_BINDINGS.yaml').read_text(encoding='utf-8'))
    schema = yaml.safe_load((ROOT / bindings['schema_ref']).read_text(encoding='utf-8'))
    if schema['schema_id'] != 'BenchmarkTaskSpec' or schema['status'] != 'DESIGN_ONLY_NOT_RUNTIME':
        raise ValueError('unsupported public BenchmarkTaskSpec reference')
    entries = yaml.safe_load(PILOT.read_text(encoding='utf-8'))['prototypes']
    selected = next((row for row in entries if row['tier'] == tier), None)
    if selected is None:
        raise ValueError('unregistered public tier')
    task_id = selected['task_id']
    binding = bindings['tiers'].get(tier)
    if binding is None or binding['task_id'] != task_id:
        raise ValueError('public task reference differs from frozen tier binding')
    if tier == 'T4':
        data = json.loads((ROOT / 'benchmark/public_oracle_canonical/T4_PUBLIC_CASES.json').read_text(encoding='utf-8')).get(variant)
    elif tier == 'T3' and variant == 'positive_transfer':
        data = json.loads((ROOT / 'benchmark/public_oracle_canonical/T3_TRANSFER.json').read_text(encoding='utf-8'))
    else:
        data = json.loads((ROOT / selected['fixture_ref']).read_text(encoding='utf-8'))['variants'].get(variant)
    if data is None:
        raise ValueError('unregistered public variant')
    public_input = {k: v for k, v in data.items() if k not in ('seed', 'mechanism')}
    spec = ROOT / binding['task_spec_ref']
    return task_id, selected['exposure'], public_input, spec


def run_canonical(*, tier, variant, policy, output_root):
    """Create one append-only public run and persist its canonical trace/artifacts."""
    root = Path(output_root).resolve()
    if root.exists():
        raise ValueError('append-only public run requires a fresh output directory')
    root.mkdir(parents=True)
    task_id, exposure, data, spec = _case(tier, variant)
    release = dict(task_id=task_id, exposure=exposure, public_input=data,
                   task_spec_sha256=_hash(spec.read_bytes()),
                   benchmark_task_schema_ref='benchmark/BENCHMARK_TASK_SCHEMA.yaml',
                   benchmark_task_binding_sha256=_hash((ROOT / 'benchmark/public_oracle_canonical/BENCHMARK_TASK_BINDINGS.yaml').read_bytes()))
    release_raw = canonical_bytes(release)
    data_spec = DataSpec('C2-PUBLIC-SYNTHETIC', 'v1', _hash(release_raw),
        '2000-01-01T00:00:00Z', '2000-01-01T00:00:00Z', '2000-01-01T00:00:00Z',
        '2000-01-01T00:00:00Z', '2000-01-01T00:00:00Z', None, 'UTC',
        {'public_fixture': 'json'}, 'none', 'public-synthetic', 'PUBLIC-C2', 'v1',
        'available_at_lte_decision_at_and_membership_effective_at_decision',
        'choose_latest_revision_available_by_decision_not_latest_download')
    snapshot = SnapshotManifest('SNAP-' + _hash(release_raw)[:20], data_spec,
                                (SnapshotFile('public-input.json', _hash(release_raw)),))
    registry = load_decisions()
    task = TaskContract(task_id, '0.1', 'public oracle output', 'one synthetic decision',
        'public synthetic control', 'public synthetic fixture', '2000-01-10T00:00:00Z',
        'scripted response after public release', data_spec.content_hash(), snapshot.content_hash(),
        'PUBLIC-C2', 'PUBLIC-NO-SEALED', 'PUBLIC-ORACLE-C2', 'C2-public-v1',
        'PUBLIC-UNCALIBRATED', 'SYNTHETIC', 'SYNTHETIC', 'DEFERRED-D04B', '0.2',
        decision_digest(), {**dict.fromkeys(BUDGET_DIMENSIONS, 0), 'attempts': 1,
                            'model_trials': 1, 'wall_milliseconds': 60000,
                            'cpu_milliseconds': 60000}, 128, '2000-01-02T00:00:00Z',
        'C2-public-custodian', decision_snapshot_ref='sha256:' + decision_digest(),
        decision_registry_version=registry['version'])
    task.verify_data_bindings(data_spec, snapshot)
    condition = BenchmarkCondition(task)
    name = '-'.join((tier, variant, policy)).replace('_', '-')
    run_id, family_id, attempt_id = 'RUN-' + name, 'FAM-' + name, 'ATT-' + name
    experiment_id, candidate_id = 'EXP-' + name, 'CAN-' + name
    evidence_id, manifest_id = 'EVI-' + name, 'MAN-' + name
    store = TraceStore(root / 'trace.sqlite')
    budget = SearchBudget(store)
    budget.register_concept(ConceptMapping('MAP-' + name, 'public engineering',
        'visible fixture outcome', 'frozen public case', ('FEAT-PUBLIC',)))
    budget.register_hypothesis(Hypothesis('HYP-' + name, 'CLAIM-' + name,
        'public conformance only', 'reference mismatch', 'MAP-' + name))
    budget.register_family(ScientificSearchFamily(family_id, 'CLAIM-' + name,
        'public engineering only; no strategy selection'))
    prompt_raw = spec.read_bytes()
    code_raw = canonical_bytes({'script': 'C2-public-fixture-v1'})
    dependency_raw = canonical_bytes({'python': 'stdlib', 'provider': 'fake'})
    run = AgentBenchmarkRun(run_id, family_id, condition.condition_hash, 'scripted-public',
        'C2-v1', _hash(prompt_raw), _hash(code_raw), _hash(dependency_raw), run_id,
        '2000-01-03T00:00:00Z', provider='fake')
    budget.register_run(run, condition, decision_snapshot=registry)
    budget.register_experiment(ExperimentSpec(experiment_id, 'HYP-' + name, task_id,
        'DATA-' + data_spec.content_hash(), 'PUBLIC-UNCALIBRATED', 'DEFERRED-D04B',
        family_id, run_id, '2000-01-04T00:00:00Z'))
    artifacts = {'public-input.json': release_raw, 'DATA-' + task.data_spec_hash: canonical_bytes(data_spec.to_dict()),
                 'SNAPSHOT-' + task.snapshot_hash: canonical_bytes(snapshot.to_dict()),
                 'prompt.txt': prompt_raw, 'code-tree.json': code_raw, 'dependencies.json': dependency_raw}
    request = WorkerRequest(run_id, 'AUTHOR-' + run_id, 'CONTEXT-' + run_id,
        'fake', 'scripted-public', 'C2-v1', run.prompt_hash, _hash(b'C2-public-script'),
        ('public-oracle-v1',), {'public-input.json': _hash(release_raw)})
    if tier == 'T4':
        output = _t4_worker(data)
    else:
        output = runpy.run_path(str(ROOT / 'benchmark/calibration/manual_expected.py'))['compute'](task_id, data)
    if policy == 'fabricated_evidence' and tier == 'T4':
        output['evidence']['support'] += 1
    elif policy == 'unjustified_refusal' and tier == 'T4':
        output = dict(terminal='REFUSE', hypothesis=None, evidence={},
                      falsification=data['falsification_rule'], reason='NO_CLAIM')
    elif policy not in ('correct', 'invalid_format', 'timeout', 'critic_rejection'):
        raise ValueError('unsupported public policy')
    response_raw = b'{broken-json' if policy == 'invalid_format' else canonical_bytes(output)
    resources = dict(input_tokens=0, output_tokens=0, wall_milliseconds=0, cpu_milliseconds=0)
    provider = FakeProvider(response_raw, mode='timeout' if policy == 'timeout' else 'success',
                            reported_usage=resources)
    author = ReviewIdentity(request.actor_id, request.context_id, run_id, 'candidate_author')
    critic = ReviewIdentity('CRITIC-' + run_id, 'CRITIC-CONTEXT-' + run_id,
                            'CRITIC-RUN-' + run_id, 'critic')
    issues = ((Issue('ISSUE-' + name, 'P1', (evidence_id,), 'synthetic critic rejection',
                     'preserve as rejection'),) if policy == 'critic_rejection' else ())
    envelope = dict(attempts=1, candidate_trials=0, model_trials=1,
                    input_tokens=0, output_tokens=0, wall_milliseconds=60000, cpu_milliseconds=60000)
    result = run_public_once(budget=budget, run_id=run_id, experiment_id=experiment_id,
        attempt_id=attempt_id, candidate_id=candidate_id, evidence_id=evidence_id,
        manifest_id=manifest_id, envelope=envelope, request=request, provider=provider,
        artifacts=artifacts, author=author, critic=critic, issues=issues)
    files = root / 'files'
    files.mkdir()
    index = {}
    for ref, raw in artifacts.items():
        filename = _hash(ref.encode()) + '.bin'
        (files / filename).write_bytes(raw)
        index[ref] = dict(path='files/' + filename, sha256=_hash(raw))
    (root / 'artifact_index.json').write_text(json.dumps(index, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    summary = dict(tier=tier, variant=variant, policy=policy, status=result['status'],
        task_id=task_id, run_id=run_id, attempt_id=attempt_id,
        candidate_ref=candidate_id, evidence_ref=evidence_id,
        manifest_ref=manifest_id, eval_result_ref=result['eval_result'].eval_result_id,
        trace_ref='trace.sqlite', assigned_denominator=1,
        diagnostic=result['eval_result'].research_behavior_metrics['terminal_diagnostic'],
        public_oracle_full_pass=result['eval_result'].research_behavior_metrics['public_oracle_full_pass'],
        formal_verdict=result['eval_result'].formal_verdict,
        scientific_candidate_trials=budget.capability_accounting(run_id)['usage']['candidate_trials'],
        scientific_variant_count=budget.scientific_accounting(family_id)['candidate_variant_count'],
        provider_calls=0, hidden_submissions=0)
    (root / 'summary.json').write_text(json.dumps(summary, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    return summary
