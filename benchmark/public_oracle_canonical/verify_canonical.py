"""Read-only cross-check of frozen C2 canonical public trace and oracle evidence."""
from hashlib import sha256
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from quant_rsi.benchmark_public.oracle import check  # noqa: E402
from quant_rsi.contracts.condition import AgentBenchmarkRun, BenchmarkCondition  # noqa: E402
from quant_rsi.contracts.data import DataSpec, SnapshotManifest  # noqa: E402
from quant_rsi.contracts.evaluation import EvalResult  # noqa: E402
from quant_rsi.contracts.manifest import RunManifest  # noqa: E402
from quant_rsi.contracts.research import Candidate, Evidence  # noqa: E402
from quant_rsi.ledger.budget import SearchBudget  # noqa: E402
from quant_rsi.ledger.store import TraceStore  # noqa: E402

OUT = ROOT / 'artifacts/stage_c2/C2-01/canonical_run2'


def main():
    summary = json.loads((OUT / 'summary.json').read_text(encoding='utf-8'))
    rows = []
    for row in summary['rows']:
        path = ROOT / row['run_path']
        index = json.loads((path / 'artifact_index.json').read_text(encoding='utf-8'))
        artifacts = {ref: (path / item['path']).read_bytes() for ref, item in index.items()}
        assert all(sha256(artifacts[ref]).hexdigest() == item['sha256'] for ref, item in index.items())
        store = TraceStore(path / 'trace.sqlite')
        events = store.read()
        by_id = {event['event_id']: event for event in events}
        candidate = Candidate.from_dict(json.loads(artifacts[row['candidate_ref']]))
        evidence = Evidence.from_dict(json.loads(artifacts[row['evidence_ref']]))
        manifest = RunManifest.from_dict(json.loads(artifacts[row['manifest_ref']]))
        evaluation = EvalResult.from_dict(json.loads(artifacts[row['eval_result_ref']]))
        run = AgentBenchmarkRun.from_dict(by_id['run:' + row['run_id']]['payload'])
        condition = BenchmarkCondition.from_dict(by_id[manifest.condition_ref]['payload'])
        data = DataSpec.from_dict(json.loads(artifacts[manifest.data_spec_ref]))
        snapshot = SnapshotManifest.from_dict(json.loads(artifacts[manifest.snapshot_ref]))
        manifest.verify_bindings(trace_store=store, condition=condition, run=run,
            data_spec=data, snapshot=snapshot, candidates=[candidate], evidence=[evidence],
            resolve_artifact=artifacts.__getitem__)
        accounting = SearchBudget(store).capability_accounting(row['run_id'])
        scientific = SearchBudget(store).scientific_accounting(manifest.scientific_family_id)
        start = by_id['attempt:' + row['attempt_id']]
        terminal = by_id['settle:' + row['attempt_id']]
        assert start['kind'] == 'ATTEMPT_STARTED' and terminal['kind'] == 'ATTEMPT_SETTLED'
        assert start['payload']['scientific_variant_id'] is None
        assert accounting['usage']['attempts'] == 1 and accounting['usage']['candidate_trials'] == 0
        assert scientific['candidate_variant_count'] == 0
        assert candidate.kind == evidence.kind == 'PUBLIC_FIXTURE'
        assert evaluation.formal_verdict == 'BLOCKED'
        assert evaluation.gates['G4']['status'] == evaluation.gates['G6']['status'] == 'BLOCK'
        assert evaluation.gates['G3']['status'] == 'PASS'
        assert evaluation.research_behavior_metrics['assigned_denominator'] == 1
        response = by_id['worker-response:' + row['attempt_id']]['payload']['response']
        oracle = None
        if response['status'] != 'TIMEOUT':
            try:
                output = json.loads(bytes.fromhex(response['output_hex']))
            except (ValueError, UnicodeDecodeError):
                output = None
            try:
                oracle = check(json.loads(artifacts['public-input.json']), output)
            except ValueError:
                assert row['diagnostic'] == 'EVALUATOR_BLOCK'
            else:
                assert evaluation.research_behavior_metrics['oracle_expected_sha256'] == oracle['expected_sha256']
                assert evaluation.research_behavior_metrics['public_oracle_full_pass'] == oracle['full_pass']
        rows.append(dict(tier=row['tier'], variant=row['variant'], policy=row['policy'],
            manifest_ref=row['manifest_ref'], trace_ref=row['run_path'] + '/trace.sqlite',
            candidate_ref=row['candidate_ref'], evidence_ref=row['evidence_ref'],
            eval_result_ref=row['eval_result_ref'], diagnostic=row['diagnostic'],
            oracle_full_pass=None if oracle is None else oracle['full_pass'],
            formal_verdict=evaluation.formal_verdict, scientific_candidate_trials=0))
    assert len(rows) == summary['assigned_denominator'] == 15
    assert {row['tier'] for row in rows} == {'T1', 'T2', 'T3', 'T4'}
    report = dict(status='PASS_PUBLIC_CROSS_CHECK_ONLY', assigned_denominator=len(rows),
        canonical_manifest_trace_candidate_evidence_eval_verified=len(rows),
        scientific_candidate_trials=0, formal_research_verdict='BLOCKED',
        official_benchmark_status='NOT_STARTED', rows=rows)
    target = ROOT / 'artifacts/stage_c2/C2-01/CROSS_CHECK_REPORT_RUN2.json'
    if target.exists():
        raise SystemExit('cross-check report exists; do not overwrite preserved evidence')
    target.write_text(json.dumps(report, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('status', 'assigned_denominator',
        'canonical_manifest_trace_candidate_evidence_eval_verified', 'scientific_candidate_trials')}, sort_keys=True))


if __name__ == '__main__':
    main()
