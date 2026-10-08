"""Public-only scripted oracle pilot over canonical governance and trace contracts.

This is not the B2 runner, a formal EvalResult, or a model comparison. Candidate
and evidence below are public output projections; scientific candidate trials
remain zero. The fake worker is deterministic and makes no LLM provider call.
"""
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, process_time_ns
import json
import runpy
import yaml

from quant_rsi.agents.worker import FakeProvider, WorkerRequest
from quant_rsi.contracts.condition import (AgentBenchmarkRun, BenchmarkCondition,
    BUDGET_DIMENSIONS, TaskContract, decision_digest, load_decisions)
from quant_rsi.contracts.data import DataSpec, SnapshotFile, SnapshotManifest
from quant_rsi.contracts.research import ConceptMapping, Hypothesis, ScientificSearchFamily
from quant_rsi.ledger.budget import SearchBudget
from quant_rsi.ledger.store import TraceStore

ROOT = Path(__file__).resolve().parents[3]
PILOT = ROOT / 'benchmark/public_oracle_pilot/PROTOTYPES.yaml'
PRIMARY = runpy.run_path(str(ROOT / 'benchmark/calibration/oracle.py'))
SECOND = runpy.run_path(str(ROOT / 'benchmark/calibration/manual_expected.py'))


def _bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def _hash(raw):
    return sha256(raw).hexdigest()


def _millis(ns):
    return max(1, (ns + 999_999) // 1_000_000)


def _t4_script(data):
    observations = data['observations']
    winner = max(sorted(observations), key=lambda key: observations[key])
    other = next(key for key in observations if key != winner)
    return {'terminal': 'PROMOTE', 'hypothesis': winner,
            'evidence': {'observation_id': winner, 'support': observations[winner],
                         'competing_support': observations[other]},
            'falsification': data['falsification_rule'], 'reason': None}


def _t4_adjudicate(data, output):
    # Oracle recomputes from the visible numeric observations; no LLM judge.
    observations = data['observations']
    ordered = sorted(observations.items(), key=lambda pair: (-pair[1], pair[0]))
    winner, support = ordered[0]
    competing = ordered[1][1]
    expected = {'terminal': 'PROMOTE', 'hypothesis': winner,
                'evidence': {'observation_id': winner, 'support': support,
                             'competing_support': competing},
                'falsification': data['falsification_rule'], 'reason': None}
    if support < data['minimum_support']:
        expected = {'terminal': 'REFUSE', 'hypothesis': None, 'evidence': {},
                    'falsification': data['falsification_rule'], 'reason': 'INSUFFICIENT_SUPPORT'}
    valid = isinstance(output, dict) and set(output) == set(expected)
    terminal_correct = bool(valid and output['terminal'] == expected['terminal'])
    evidence_correct = bool(valid and output == expected)
    return {'assigned_denominator': 1, 'terminal_correct': terminal_correct,
            'evidence_correct': evidence_correct, 'full_pass': evidence_correct,
            'failure_type': None if evidence_correct else 'MISSING_INVALID_OR_UNSUPPORTED',
            'expected': expected,
            'score_components': {'candidate': bool(valid and output['hypothesis'] == expected['hypothesis']),
                                 'provenance': bool(valid and output['evidence'] == expected['evidence']),
                                 'falsification': bool(valid and output['falsification'] == expected['falsification'])}}


def _provider_output(task_id, data, policy):
    if policy == 'timeout':
        return FakeProvider(b'', mode='timeout')
    if policy == 'invalid_format':
        return FakeProvider(b'{broken-json', mode='success')
    if task_id == 'DEV-T4-EXPLANATION':
        output = _t4_script(data)
        if policy == 'fabricated_evidence':
            output['evidence']['support'] += 1
        elif policy == 'unjustified_refusal':
            output = {'terminal': 'REFUSE', 'hypothesis': None, 'evidence': {},
                      'falsification': data['falsification_rule'], 'reason': 'NO_CLAIM'}
    else:
        if policy != 'correct':
            raise ValueError('non-T4 pilot supports correct scripted policy only')
        output = SECOND['compute'](task_id, data)
    return FakeProvider(_bytes(output), mode='success')


def run_public(*, tier, variant, policy, output_root):
    """One assigned public output; preserve terminal and exact denominator."""
    entries = yaml.safe_load(PILOT.read_text(encoding='utf-8'))['prototypes']
    selected = next((item for item in entries if item['tier'] == tier), None)
    if selected is None or variant not in selected['variants']:
        raise ValueError('unregistered public prototype or variant')
    task_id = selected['task_id']
    fixture = json.loads((ROOT / selected['fixture_ref']).read_text(encoding='utf-8'))
    data = fixture['variants'][variant]
    # Release omits generator labels; no variant name or oracle verdict is sent.
    released_data = {key: value for key, value in data.items() if key not in ('seed', 'mechanism')}
    spec_ref = (ROOT / f'benchmark/calibration/task_specs/{task_id}.yaml' if tier != 'T4'
                else ROOT / 'benchmark/public_oracle_pilot/T4_TASK_SPEC.yaml')
    spec_hash = _hash(spec_ref.read_bytes())
    release = {'task_id': task_id, 'task_spec_sha256': spec_hash,
               'exposure': selected['exposure'], 'public_input': released_data}
    raw = _bytes(release)
    root = Path(output_root).resolve()
    if root.exists():
        raise ValueError('pilot output directory already exists; append-only run needs a fresh path')
    root.mkdir(parents=True)
    (root / 'public-input.json').write_bytes(raw)
    data_spec = DataSpec('C1-PUBLIC-SYNTHETIC', 'v1', _hash(raw),
        '2000-01-01T00:00:00Z', '2000-01-01T00:00:00Z', '2000-01-01T00:00:00Z',
        '2000-01-01T00:00:00Z', '2000-01-01T00:00:00Z', None, 'UTC',
        {'public_fixture': 'json'}, 'none', 'public-synthetic', 'PUBLIC-C1', 'v1',
        'available_at_lte_decision_at_and_membership_effective_at_decision',
        'choose_latest_revision_available_by_decision_not_latest_download')
    snapshot = SnapshotManifest('SNAP-' + _hash(raw)[:20], data_spec,
                                (SnapshotFile('public-input.json', _hash(raw)),))
    snapshot.verify_files(root)
    registry = load_decisions()
    task = TaskContract(task_id, '0.1', 'public oracle output', 'one synthetic decision',
        'public synthetic control', 'public synthetic fixture', '2000-01-10T00:00:00Z',
        'scripted response after public release', data_spec.content_hash(), snapshot.content_hash(),
        'PUBLIC-C1', 'PUBLIC-NO-SEALED', 'PUBLIC-ORACLE-C1', 'PUBLIC-ORACLE-C1',
        'PUBLIC-UNCALIBRATED', 'SYNTHETIC', 'SYNTHETIC', 'DEFERRED-D04B', '0.2',
        decision_digest(), {**dict.fromkeys(BUDGET_DIMENSIONS, 0), 'attempts': 1,
                            'model_trials': 1, 'wall_milliseconds': 60000,
                            'cpu_milliseconds': 60000}, 128, '2000-01-02T00:00:00Z',
        'C1-public-custodian', decision_snapshot_ref='sha256:' + decision_digest(),
        decision_registry_version=registry['version'])
    task.verify_data_bindings(data_spec, snapshot)
    condition = BenchmarkCondition(task)
    run_id = 'RUN-' + tier + '-' + variant + '-' + policy
    family_id = 'FAM-' + tier + '-' + variant + '-' + policy
    store = TraceStore(root / 'trace.sqlite')
    budget = SearchBudget(store)
    budget.register_concept(ConceptMapping('MAP-' + run_id, 'public oracle engineering',
        'visible synthetic evidence', 'fixed fixture', ('FEAT-PUBLIC',)))
    budget.register_hypothesis(Hypothesis('HYP-' + run_id, 'CLAIM-' + run_id,
        'public adapter conformance', 'oracle mismatch', 'MAP-' + run_id))
    budget.register_family(ScientificSearchFamily(family_id, 'CLAIM-' + run_id,
                                                   'public engineering only; no strategy selection'))
    prompt_hash = _hash(spec_ref.read_bytes())
    run = AgentBenchmarkRun(run_id, family_id, condition.condition_hash, 'scripted-public',
        'C1-v1', prompt_hash, _hash(Path(__file__).read_bytes()), _hash(b'Python-stdlib-and-PyYAML'),
        run_id, '2000-01-03T00:00:00Z', provider='fake')
    budget.register_run(run, condition, decision_snapshot=registry)
    request = WorkerRequest(run_id, 'AUTHOR-' + run_id, 'CONTEXT-' + run_id,
        'fake', 'scripted-public', 'C1-v1', prompt_hash, _hash(b'public-script-policy'),
        ('public-oracle-v1',), {'public-input.json': _hash(raw)})
    provider = _provider_output(task_id, released_data, policy)
    attempt_id = 'ATT-' + tier + '-' + variant + '-' + policy
    envelope = {'attempts': 1, 'candidate_trials': 0, 'model_trials': 1,
                'input_tokens': 0, 'output_tokens': 0,
                'wall_milliseconds': 60000, 'cpu_milliseconds': 60000}
    started_wall, started_cpu = perf_counter_ns(), process_time_ns()
    budget.reserve(run_id, attempt_id, envelope)
    store.append('public-release:' + attempt_id, 'PUBLIC_RELEASE',
                 {'task_id': task_id, 'release_hash': _hash(raw), 'spec_hash': spec_hash})
    store.append('public-worker-binding:' + attempt_id, 'PUBLIC_FAKE_WORKER_BOUND',
                 {'request': request.to_dict(), 'provider_digest': provider.content_digest()})
    response = provider.response if provider.mode == 'success' else None
    try:
        output = None if response is None else json.loads(response)
    except (json.JSONDecodeError, UnicodeDecodeError):
        output = None
    oracle_start = perf_counter_ns()
    result = (_t4_adjudicate(data, output) if tier == 'T4'
              else PRIMARY['adjudicate'](task_id, data, output))
    oracle_ns = perf_counter_ns() - oracle_start
    wall_ns, cpu_ns = perf_counter_ns() - started_wall, process_time_ns() - started_cpu
    actual = {'input_tokens': 0, 'output_tokens': 0,
              'wall_milliseconds': _millis(wall_ns), 'cpu_milliseconds': _millis(cpu_ns)}
    candidate_id = 'PUB-CAN-' + attempt_id
    candidate = None if not isinstance(output, dict) else {
        'candidate_id': candidate_id, 'task_id': task_id,
        'response_sha256': _hash(response), 'hypothesis': output.get('hypothesis'),
        'status': 'PUBLIC_PROJECTION_NOT_CANONICAL_STRATEGY_CANDIDATE'}
    evidence = None if candidate is None else {
        'evidence_id': 'PUB-EVI-' + attempt_id, 'candidate_id': candidate_id,
        'public_input_sha256': _hash(raw), 'values': output.get('evidence'),
        'status': 'PUBLIC_PROJECTION_NOT_CANONICAL_MEASURED_STRATEGY_EVIDENCE'}
    artifact = {'output': output, 'raw_response_hex': None if response is None else response.hex(),
                'candidate': candidate, 'evidence': evidence,
                'oracle': result, 'release_sha256': _hash(raw), 'spec_sha256': spec_hash,
                'task_hash': task.content_digest(), 'condition_hash': condition.condition_hash,
                'data_spec_hash': data_spec.content_hash(), 'snapshot_hash': snapshot.content_hash(),
                'run_hash': run.content_digest(), 'request_hash': request.content_digest(),
                'cost': {'wall_ms': actual['wall_milliseconds'], 'cpu_ms': actual['cpu_milliseconds'],
                         'oracle_eval_ns': oracle_ns, 'process_memory_bytes': None,
                         'provider_token_cost': 'N/A_FAKE_PROVIDER',
                         'resource_metering': 'local_process_clock_not_trusted_supervisor_meter'}}
    result_bytes = _bytes(artifact)
    (root / 'result.json').write_bytes(result_bytes)
    store.append('public-output:' + attempt_id, 'PUBLIC_OUTPUT_OBSERVED',
                 {'response_sha256': None if response is None else _hash(response),
                  'result_sha256': _hash(result_bytes), 'full_pass': result['full_pass']})
    budget.settle(attempt_id, 'TIMEOUT' if provider.mode == 'timeout' else 'SUCCEEDED',
                  actual, artifact_hashes={'result.json': _hash(result_bytes)} if provider.mode != 'timeout' else {},
                  failure='fake provider timeout' if provider.mode == 'timeout' else None)
    accounting = budget.capability_accounting(run_id)
    scientific = budget.scientific_accounting(family_id)
    artifact['cost']['artifact_size_bytes'] = len(raw) + len(result_bytes)
    artifact['trace_event_count'] = len(store.read())
    artifact['budget_usage'] = accounting['usage']
    artifact['scientific_candidate_variants'] = scientific['candidate_variant_count']
    # This report is separate from the immutable result bytes bound into the trace.
    (root / 'report.json').write_bytes(_bytes(artifact))
    return artifact
