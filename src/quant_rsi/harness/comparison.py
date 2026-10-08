"""PUBLIC_UNSEALED_AGENT_COMPARISON runner (Track A).

Runs the frozen public capability tasks against two or more model providers under
identical conditions, scores every attempt with the deterministic oracle, and emits
a per-dimension score vector plus failure traces.

Governance alignment:
  * D06   -- hard gates and a score vector; NO single total score is produced.
  * D02   -- measures the Research Agent, not strategy economics.
  * D08   -- independence is *named*: identity independence holds only when the
             providers differ. Evidence independence is NOT claimed.
  * Track A -- output is PUBLIC / UNSEALED / PROVISIONAL and must never be cited
             as PIT-correct, as tradable alpha, or as a formal model ranking.

Ledger class: capability engineering with zero scientific variance. Every attempt
is reserved with candidate_trials=0 and no scientific_variant_id, so the
scientific-family accounting reports zero candidate variants and this run can
never be mistaken for a strategy search.

The append-only trace is the existing quant_rsi.ledger.store.TraceStore, reused
rather than reimplemented.
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(ROOT / 'src'))

from quant_rsi.harness import capability_oracle as oracle          # noqa: E402
from quant_rsi.harness.providers import (MockProvider, build_prompt,  # noqa: E402
                                        planned_pairs, ProviderError)
from quant_rsi.ledger.store import TraceStore                       # noqa: E402

TRACK_A_LABEL = 'PUBLIC_UNSEALED_PROVISIONAL'

# Engineering-budget caps for one comparison run. Self-service inside these caps.
CAPS = {
    'tasks': 9,
    'attempts_per_task_per_provider': 1,
    'retries': 0,
    'input_tokens': 600_000,
    'output_tokens': 200_000,
    'wall_milliseconds': 3_600_000,
}
# Scientific-search budget for this run: deliberately and verifiably zero.
SCIENTIFIC_SEARCH = {'candidate_trials': 0, 'factor_variants': 0,
                     'parameter_trials': 0, 'hypotheses_seen': 0}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def _hash_bytes(raw):
    return sha256(raw).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _dimensions():
    return oracle.load_fixtures()['capability_dimensions']


def _task_ids():
    return list(oracle.load_fixtures()['tasks'].keys())


def _task_dimensions(task_id):
    return oracle.load_fixtures()['tasks'][task_id]['dimensions']


def run_comparison(providers, run_id, output_root, trace_path=None, repeat=1):
    """Execute one comparison run. Returns the manifest dict that was written."""
    task_ids = _task_ids()
    if len(task_ids) > CAPS['tasks']:
        raise ValueError('registered task count exceeds the frozen engineering cap')

    root = Path(output_root).resolve() / run_id
    if root.exists():
        raise ValueError(f'run directory already exists (append-only): {root}')
    root.mkdir(parents=True)
    trace = TraceStore(trace_path or (root / 'trace.sqlite'))

    prompt_hashes = {t: _hash_bytes(build_prompt(t, oracle.public_input(t)).encode())
                     for t in task_ids}
    release_hashes = {t: oracle.release_hash(t) for t in task_ids}

    trace.append(f'comparison-start:{run_id}', 'COMPARISON_STARTED', {
        'run_id': run_id,
        'track': 'A',
        'labels': TRACK_A_LABEL,
        'task_ids': task_ids,
        'providers': [{'provider_id': p.provider_id, 'model_id': p.model_id} for p in providers],
        'prompt_hashes': prompt_hashes,
        'release_hashes': release_hashes,
        'capture_timestamp_utc': _now(),
    })

    records = []
    token_usage = {'input_tokens': 0, 'output_tokens': 0}
    wall_total = 0
    budget_stop = None

    for provider in providers:
        for task_id in task_ids:
            if budget_stop:
                break
            for trial in range(1, repeat + 1):
                prompt = build_prompt(task_id, oracle.public_input(task_id))
                prompt_hash = prompt_hashes[task_id]
                attempt_id = f'{run_id}:{provider.provider_id}:{task_id}:t{trial}'
                reply = None
                transport_error = None
                try:
                    reply = provider.reply(task_id, prompt)
                except ProviderError as exc:
                    transport_error = str(exc)
                except Exception as exc:  # never let a provider crash the run
                    transport_error = f'{type(exc).__name__}: {exc}'

                response_bytes = None
                if reply is not None and reply.ok and reply.text is not None:
                    response_bytes = reply.text.encode('utf-8')
                transport_failed = response_bytes is None
                score = oracle.adjudicate(task_id, response_bytes,
                                          transport_failed=transport_failed)

                in_tok = (reply.input_tokens if reply and reply.input_tokens else 0)
                out_tok = (reply.output_tokens if reply and reply.output_tokens else 0)
                wall = reply.wall_ms if reply else 0
                token_usage['input_tokens'] += in_tok
                token_usage['output_tokens'] += out_tok
                wall_total += wall

                if wall_total > CAPS['wall_milliseconds']:
                    budget_stop = 'WALL_MILLISECONDS_EXHAUSTED'
                if token_usage['input_tokens'] > CAPS['input_tokens']:
                    budget_stop = 'INPUT_TOKENS_EXHAUSTED'
                if token_usage['output_tokens'] > CAPS['output_tokens']:
                    budget_stop = 'OUTPUT_TOKENS_EXHAUSTED'

                record = {
                    'task_id': task_id,
                    'dimensions': _task_dimensions(task_id),
                    'provider_id': provider.provider_id,
                    'model_id': provider.model_id,
                    'trial': trial,
                    'attempt_id': attempt_id,
                    'prompt_sha256': prompt_hash,
                    'release_sha256': release_hashes[task_id],
                    'transport_ok': bool(reply and reply.ok),
                    'http_status': reply.http_status if reply else None,
                    'transport_error': transport_error or (reply.transport_error if reply else None),
                    'provider_attempts': reply.attempts if reply else 0,
                    'response_sha256': None if response_bytes is None else _hash_bytes(response_bytes),
                    'response_text': None if response_bytes is None else response_bytes.decode('utf-8', 'replace'),
                    'input_tokens': in_tok,
                    'output_tokens': out_tok,
                    'wall_ms': wall,
                    'score': score.to_dict(),
                    'recorded_at': _now(),
                }
                records.append(record)
                trace.append(f'attempt:{run_id}:{provider.provider_id}:{task_id}:t{trial}',
                             'COMPARISON_ATTEMPT', {
                                 'run_id': run_id,
                                 'task_id': task_id,
                                 'provider_id': provider.provider_id,
                                 'model_id': provider.model_id,
                                 'trial': trial,
                                 'prompt_sha256': prompt_hash,
                                 'release_sha256': release_hashes[task_id],
                                 'response_sha256': record['response_sha256'],
                                 'full_pass': score.full_pass,
                                 'failure_type': score.failure_type,
                                 'input_tokens': in_tok,
                                 'output_tokens': out_tok,
                                 'wall_ms': wall,
                                 'recorded_at': record['recorded_at'],
                             })

    vector = score_vector(records, providers, task_ids)
    reproducibility = reproducibility_report(records, providers, task_ids) if repeat > 1 else None

    # A run with no successful transport measures nothing about any model, so it
    # must never be read as a capability result.
    valid = any(r['transport_ok'] for r in records)
    validity_reason = None if valid else 'ALL_TRANSPORTS_FAILED_NO_CAPABILITY_EVIDENCE'

    manifest = {
        'run_id': run_id,
        'labels': TRACK_A_LABEL,
        'track': 'A',
        'sealed': False,
        'pit_correct': False,
        'may_claim_tradable_alpha': False,
        'is_formal_model_ranking': False,
        'capability_result_valid': valid,
        'validity_reason': validity_reason,
        'generated_at': _now(),
        'environment': {
            'python': platform.python_version(),
            'platform': platform.platform(),
            'oracle_module_sha256': _hash_bytes(Path(oracle.__file__).read_bytes()),
            'fixtures_sha256': _hash_bytes(oracle.FIXTURE_PATH.read_bytes()),
        },
        'providers': [{'provider_id': p.provider_id, 'model_id': p.model_id} for p in providers],
        'task_ids': task_ids,
        'prompt_hashes': prompt_hashes,
        'release_hashes': release_hashes,
        'repeat': repeat,
        'caps': CAPS,
        'scientific_search_budget': SCIENTIFIC_SEARCH,
        'scientific_candidate_variants': 0,
        'budget_usage': {
            'attempts': len(records),
            'input_tokens': token_usage['input_tokens'],
            'output_tokens': token_usage['output_tokens'],
            'wall_milliseconds': wall_total,
            'retries': 0,
        },
        'budget_stop': budget_stop,
        'score_vector': vector,
        'reproducibility': reproducibility,
        'score_vector_is_not_a_single_total_score': True,
        'records': records,
    }
    (root / 'records.json').write_bytes(_canonical(records).encode())
    (root / 'comparison_manifest.json').write_bytes(
        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False).encode())
    trace.append(f'comparison-complete:{run_id}', 'COMPARISON_COMPLETED', {
        'run_id': run_id,
        'attempt_count': len(records),
        'full_pass_count': sum(1 for r in records if r['score']['full_pass']),
        'score_vector': vector,
        'budget_stop': budget_stop,
        'recorded_at': _now(),
    })
    return manifest


def score_vector(records, providers, task_ids):
    """Per-provider, per-dimension pass rates. Deliberately no grand total."""
    dims = [d['id'] for d in _dimensions()]
    vector = {}
    for provider in providers:
        pid = provider.provider_id
        mine = [r for r in records if r['provider_id'] == pid]
        tasks_total = len(task_ids)
        full = sum(1 for r in mine if r['score']['full_pass'])
        by_dimension = {}
        for dim in dims:
            relevant = [r for r in mine if dim in r['dimensions']]
            passed = sum(1 for r in relevant if r['score']['full_pass'])
            by_dimension[dim] = {
                'assigned': len(relevant),
                'passed': passed,
                'rate': (round(passed / len(relevant), 4) if relevant else None),
            }
        vector[pid] = {
            'model_id': provider.model_id,
            'tasks_assigned': tasks_total,
            'tasks_full_pass': full,
            'task_pass_rate': round(full / tasks_total, 4) if tasks_total else None,
            'transport_successes': sum(1 for r in mine if r['transport_ok']),
            'verdict_correct': sum(1 for r in mine if r['score']['verdict_ok']),
            'evidence_correct': sum(1 for r in mine if r['score']['evidence_ok']),
            'failure_types': _failure_histogram(mine),
            'by_dimension': by_dimension,
            'dimension_mean_rate': _mean(
                [v['rate'] for v in by_dimension.values() if v['rate'] is not None]),
        }
    return vector


def reproducibility_report(records, providers, task_ids):
    """With repeat>1, report whether identical prompts produced identical output."""
    report = {}
    for provider in providers:
        unstable = []
        stable = 0
        for task_id in task_ids:
            hashes = {r['response_sha256'] for r in records
                      if r['provider_id'] == provider.provider_id and r['task_id'] == task_id}
            if len(hashes) > 1:
                unstable.append(task_id)
            else:
                stable += 1
        report[provider.provider_id] = {
            'tasks_with_identical_output': stable,
            'tasks_with_output_variance': unstable,
            'output_variance_count': len(unstable),
        }
    return report


def _failure_histogram(records):
    hist = {}
    for r in records:
        key = r['score']['failure_type'] or 'NONE'
        hist[key] = hist.get(key, 0) + 1
    return hist


def _mean(values):
    return round(sum(values) / len(values), 4) if values else None


def _parse_args(argv):
    parser = argparse.ArgumentParser(description='PUBLIC Track A capability comparison')
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output-root',
                        default=str(ROOT / 'benchmark/capability_public/runs'))
    parser.add_argument('--providers', default='mock-a,mock-b',
                        help="comma list of: mock-a, mock-b, deepseek, xiaomi")
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('--trace', default=None, help='override trace sqlite path')
    return parser.parse_args(argv)


def _resolve_providers(spec):
    """Map provider names to provider objects. Credentials are read lazily."""
    pairs = planned_pairs()
    resolved = []
    for name in [s.strip() for s in spec.split(',') if s.strip()]:
        if name == 'mock-a':
            resolved.append(MockProvider(provider_id='mock-a', model_id='mock-ideal-v1'))
        elif name == 'mock-b':
            resolved.append(MockProvider(provider_id='mock-b', model_id='mock-variance-v1'))
        elif name in pairs:
            resolved.append(pairs[name])
        else:
            raise SystemExit(f'unknown provider: {name}')
    if not resolved:
        raise SystemExit('at least one provider is required')
    return resolved


def main(argv=None):
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    providers = _resolve_providers(args.providers)
    started = time.perf_counter()
    manifest = run_comparison(providers, args.run_id, args.output_root,
                              trace_path=args.trace, repeat=args.repeat)
    elapsed = int((time.perf_counter() - started) * 1000)
    vector = manifest['score_vector']
    print(f"run_id: {manifest['run_id']}   labels: {manifest['labels']}")
    print(f"tasks: {len(manifest['task_ids'])}   attempts: {manifest['budget_usage']['attempts']}"
          f"   elapsed_ms: {elapsed}")
    print(f"budget_stop: {manifest['budget_stop']}")
    print(f"scientific_candidate_variants: {manifest['scientific_candidate_variants']} (must be 0)")
    if not manifest['capability_result_valid']:
        print(f"*** RESULT INVALID: {manifest['validity_reason']}")
        print("*** No successful transport occurred; this is NOT a capability result.")
    print()
    header = f"{'provider':<10} {'model':<22} {'full_pass':>9} {'pass_rate':>9} {'verdict_ok':>10} {'evidence_ok':>11}"
    print(header)
    print('-' * len(header))
    for pid, v in vector.items():
        print(f"{pid:<10} {str(v['model_id'])[:22]:<22} {v['tasks_full_pass']:>9} "
              f"{str(v['task_pass_rate']):>9} {v['verdict_correct']:>10} {v['evidence_correct']:>11}")
    print()
    print('per-dimension pass rate (score vector, NOT a single total score):')
    dims = [d['id'] for d in _dimensions()]
    print(f"{'dimension':<28} " + ' '.join(f'{p:>10}' for p in vector))
    for dim in dims:
        row = f'{dim:<28} '
        for pid in vector:
            rate = vector[pid]['by_dimension'][dim]['rate']
            row += f'{("n/a" if rate is None else rate):>10} '
        print(row)
    print()
    for pid, v in vector.items():
        print(f'{pid} failure types: {v["failure_types"]}')
    if manifest['reproducibility']:
        print()
        for pid, rep in manifest['reproducibility'].items():
            print(f'{pid} reproducibility: stable={rep["tasks_with_identical_output"]} '
                  f'variance={rep["output_variance_count"]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
