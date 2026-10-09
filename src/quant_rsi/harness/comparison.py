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
                                        planned_pairs, ProviderError, ChatProvider, SYSTEM_PROMPT)
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


def run_comparison(providers, run_id, output_root, trace_path=None, repeat=1,
                   suite='0.1', authorization=None):
    """One frozen batch; incomplete attempts retain assigned denominators."""
    fixtures = oracle.suite_fixtures(suite)
    task_ids = fixtures.get('task_order', list(fixtures['tasks']))
    caps = dict(CAPS)
    plan = None
    if suite == '0.2':
        plan = json.loads((oracle.V02_PATH.with_name('freeze_v02.json')).read_text(encoding='utf-8'))
        for relative, digest in plan['sha256'].items():
            if _hash_bytes((ROOT / relative).read_bytes()) != digest:
                raise ValueError('frozen file changed: ' + relative)
        caps = plan['caps']
        if repeat != 1:
            raise ValueError('v0.2 freezes one attempt per task/model')
    if repeat < 1 or len(task_ids) > caps['tasks']:
        raise ValueError('task/repeat count exceeds frozen cap')
    if not providers or len({p.provider_id for p in providers}) != len(providers):
        raise ValueError('providers must have distinct nonempty identities')
    real = [p for p in providers if isinstance(p, ChatProvider)]
    if real:
        # Caller must supply explicit human batch approval; old reports are not authority.
        if not authorization or not authorization.get('approved') or not authorization.get('keys_rotated'):
            raise ValueError('explicit fixed-batch authorization and rotated keys required')
        if plan is not None and plan['real_run_status'].startswith('DEFERRED'):
            raise ValueError('real tests deferred by user; a newly authorized execution freeze is required')
        if suite != '0.2' or authorization.get('freeze_sha256') != _hash_bytes(oracle.V02_PATH.with_name('freeze_v02.json').read_bytes()):
            raise ValueError('authorization must bind the v0.2 freeze')
        if [p.provider_id for p in providers] != list(plan['providers']):
            raise ValueError('real run requires exactly the frozen model pair')
        for p in real:
            config = plan['providers'][p.provider_id]
            if p.extra_headers or any(getattr(p, k) != v for k, v in config.items()):
                raise ValueError('provider differs from frozen config')
        rates = authorization.get('prices_per_million', {})
        import math
        if any(p.provider_id not in rates or any(
                type(rates[p.provider_id].get(k)) not in (int, float) or
                not math.isfinite(rates[p.provider_id][k]) or rates[p.provider_id][k] < 0
                for k in ('input', 'output')) for p in real):
            raise ValueError('finite nonnegative frozen prices required')
        worst = sum(24 * (caps['input_per_call'] * rates[p.provider_id]['input'] +
                          p.max_tokens * rates[p.provider_id]['output']) / 1_000_000 for p in real)
        if authorization.get('call_cap') != 48 or not authorization.get('currency') or worst > authorization.get('money_cap', -1):
            raise ValueError('approved API/money budget does not cover worst case')
    for p in providers:
        if isinstance(p, MockProvider):
            p.suite = suite
    def prompt_for(t):
        if suite == '0.2':
            return build_prompt(t, fixtures['tasks'][t]['public_input'], contract=oracle.v02_contract(t))
        return build_prompt(t, oracle.public_input(t), oracle.required_evidence_keys(t))
    prompts = {t: prompt_for(t) for t in task_ids}
    prompt_hashes = {t: _hash_bytes(v.encode()) for t, v in prompts.items()}
    release_hashes = {t: (_hash_bytes(_canonical({'input': fixtures['tasks'][t]['public_input'],
                                              'contract': oracle.v02_contract(t)}).encode())
                         if suite == '0.2' else oracle.release_hash(t)) for t in task_ids}
    if suite == '0.2' and prompt_hashes != plan['prompt_hashes']:
        raise ValueError('prompt differs from freeze')
    root = Path(output_root).resolve() / run_id
    if root.exists():
        raise ValueError(f'run directory already exists (append-only): {root}')
    root.mkdir(parents=True)
    trace = TraceStore(trace_path or (root / 'trace.sqlite'))
    trace.append(f'comparison-start:{run_id}', 'COMPARISON_STARTED', {
        'run_id': run_id, 'track': 'A', 'labels': TRACK_A_LABEL, 'suite': suite,
        'task_ids': task_ids, 'providers': [{'provider_id': p.provider_id, 'model_id': p.model_id} for p in providers],
        'prompt_hashes': prompt_hashes, 'release_hashes': release_hashes, 'capture_timestamp_utc': _now()})
    records, token_usage = [], {'input_tokens': 0, 'output_tokens': 0}
    wall_total, budget_stop, reserved_input, reserved_output = 0, None, 0, 0
    if suite == '0.2':
        schedule = [(p,t,1) for i,t in enumerate(task_ids)
                    for p in (providers if i % 2 == 0 else list(reversed(providers)))]
    else:
        schedule = [(p,t,k) for p in providers for t in task_ids for k in range(1,repeat+1)]
    for provider, task_id, trial in schedule:
        if budget_stop:
            break
        if suite == '0.2':
            in_bound, out_bound = caps['input_per_call'], caps['output_per_call']
            if (len(records) >= caps['calls'] or reserved_input+in_bound > caps['input_tokens'] or
                    reserved_output+out_bound > caps['output_tokens'] or
                    wall_total+caps['timeout_s']*1000 > caps['wall_milliseconds']):
                budget_stop = 'BUDGET_EXHAUSTED'
                break
            if len((SYSTEM_PROMPT+prompts[task_id]).encode())+1024 > in_bound:
                raise ValueError('prompt exceeds conservative input bound')
            reserved_input += in_bound
            reserved_output += out_bound
        attempt_id = f'{run_id}:{provider.provider_id}:{task_id}:t{trial}'
        trace.append('reserve:'+attempt_id, 'COMPARISON_RESERVED',
                     {'attempt_id': attempt_id, 'candidate_trials': 0, 'call_index': len(records)+1})
        reply, error, explicit_failure = None, None, None
        try:
            reply = provider.reply(task_id, prompts[task_id])
        except ProviderError:
            error, explicit_failure = 'ProviderError: missing credential', 'CREDENTIAL_UNAVAILABLE'
        except TimeoutError:
            error, explicit_failure = 'TimeoutError', 'TASK_TIMEOUT'
        except Exception:
            error, explicit_failure = 'Provider exception', 'TRANSPORT_FAILED'
        response = reply.text.encode() if reply and isinstance(reply.text, str) else None
        failure = explicit_failure or (reply.failure_type if reply else 'TRANSPORT_FAILED')
        if suite == '0.2' and reply and isinstance(provider, ChatProvider) and reply.observed_model not in (None, provider.model_id):
            failure = 'MODEL_ID_MISMATCH'
            budget_stop = 'MODEL_ID_MISMATCH'
        if suite == '0.2':
            score = oracle.adjudicate(task_id, response, suite=suite, failure_type=failure)
        else:
            score = oracle.adjudicate(task_id, response,
                                     transport_failed=not bool(reply and reply.ok),
                                     truncated=bool(reply and reply.truncated))
        in_tok = reply.input_tokens if reply else None
        out_tok = reply.output_tokens if reply else None
        wall = reply.wall_ms if reply else 0
        token_usage['input_tokens'] += in_tok or 0
        token_usage['output_tokens'] += out_tok or 0
        wall_total += wall
        if wall_total > caps['wall_milliseconds']:
            budget_stop = 'WALL_MILLISECONDS_EXHAUSTED'
        if token_usage['input_tokens'] > caps['input_tokens']:
            budget_stop = 'INPUT_TOKENS_EXHAUSTED'
        if token_usage['output_tokens'] > caps['output_tokens']:
            budget_stop = 'OUTPUT_TOKENS_EXHAUSTED'
        if suite == '0.2' and isinstance(provider, ChatProvider) and (in_tok is None or out_tok is None):
            budget_stop = 'UNKNOWN_USAGE_RECONCILIATION_REQUIRED'
        if suite == '0.2' and ((in_tok or 0) > caps['input_per_call'] or (out_tok or 0) > caps['output_per_call']):
            budget_stop = 'PER_CALL_TOKEN_BUDGET_BREACH'
        cost = None
        if real and in_tok is not None and out_tok is not None:
            rate = authorization['prices_per_million'][provider.provider_id]
            cost = (in_tok*rate['input'] + out_tok*rate['output']) / 1_000_000
        task = fixtures['tasks'][task_id]
        record = {'task_id': task_id, 'dimensions': task['dimensions'],
                  'source_incident_id': task.get('source_incident_id', task_id),
                  'provider_id': provider.provider_id, 'model_id': provider.model_id,
                  'observed_model': reply.observed_model if reply else None,
                  'trial': trial, 'attempt_id': attempt_id,
                  'prompt_sha256': prompt_hashes[task_id], 'release_sha256': release_hashes[task_id],
                  'transport_ok': bool(reply and reply.ok), 'http_status': reply.http_status if reply else None,
                  'transport_error': error or (reply.transport_error if reply else None),
                  'provider_attempts': reply.attempts if reply else 0,
                  'finish_reason': reply.finish_reason if reply else None,
                  'reasoning_chars': reply.reasoning_chars if reply else None,
                  'reasoning_tokens': reply.reasoning_tokens if reply else None,
                  'output_truncated': bool(reply and reply.truncated),
                  'response_sha256': _hash_bytes(response) if response is not None else None,
                  'response_text': reply.text if reply else None,
                  'input_tokens': in_tok, 'output_tokens': out_tok, 'wall_ms': wall,
                  'cost': cost, 'currency': authorization.get('currency') if authorization else None,
                  'cost_status': 'ESTIMATED_FROM_APPROVED_RATES' if cost is not None else 'NOT_REPORTED',
                  'score': score.to_dict(), 'recorded_at': _now()}
        if suite == '0.2':
            record['scoring_predicates'] = task['scoring_predicates']
            record['ground_truth'] = task['ground_truth']
        records.append(record)
        trace.append('attempt:'+attempt_id, 'COMPARISON_ATTEMPT', record)
        # Persist after each attempt so interrupted batches retain raw responses.
        (root / f'attempt_{len(records):03d}.json').write_text(_canonical(record), encoding='utf-8')
    unattempted = [{'provider_id':p.provider_id, 'task_id':t, 'trial':k,
                    'failure_type':'BUDGET_EXHAUSTED', 'reason':budget_stop}
                   for p,t,k in schedule[len(records):]]
    if budget_stop:
        trace.append('denial:'+run_id, 'COMPARISON_BUDGET_DENIED', {'reason':budget_stop,'unattempted':unattempted})
    vector = score_vector(records, providers, task_ids, suite=suite, repeat=repeat)
    valid = any(r['score']['parsed'] and not r['score']['missing_keys'] and
                r['score']['observed_verdict'] in oracle.VERDICT_ENUM for r in records) if suite == '0.2' else any(r['transport_ok'] for r in records)
    manifest = {
        'run_id': run_id, 'labels': TRACK_A_LABEL, 'track': 'A', 'sealed': False,
        'pit_correct': False, 'may_claim_tradable_alpha': False, 'is_formal_model_ranking': False,
        'suite_version': suite, 'evaluator_version': oracle.EVALUATOR_VERSION if suite == '0.2' else 'legacy',
        'task_kind': 'STATIC_DIAGNOSTIC', 'research_agent_workflow_verified': False,
        'capability_result_valid': valid,
        'validity_reason': None if valid else 'ALL_TRANSPORTS_FAILED_NO_CAPABILITY_EVIDENCE' if suite == '0.1' else 'NO_PARSED_RESEARCH_ANSWER',
        'generated_at': _now(), 'environment': {'python':platform.python_version(),
            'platform':platform.platform(), 'oracle_module_sha256':_hash_bytes(Path(oracle.__file__).read_bytes()),
            'fixtures_sha256':_hash_bytes((oracle.V02_PATH if suite == '0.2' else oracle.FIXTURE_PATH).read_bytes())},
        'providers':[{'provider_id':p.provider_id,'model_id':p.model_id} for p in providers],
        'task_ids':task_ids, 'prompt_hashes':prompt_hashes, 'release_hashes':release_hashes,
        'repeat':repeat, 'caps':caps, 'scientific_search_budget':SCIENTIFIC_SEARCH,
        'scientific_candidate_variants':0,
        'budget_usage':{'attempts':len(records),'input_tokens':token_usage['input_tokens'],
                        'output_tokens':token_usage['output_tokens'],'wall_milliseconds':wall_total,'retries':0,
                        'reserved_input_tokens':reserved_input,'reserved_output_tokens':reserved_output,
                        'unknown_token_usage_attempts':sum(r['input_tokens'] is None or r['output_tokens'] is None for r in records)},
        'budget_stop':budget_stop, 'unattempted':unattempted, 'score_vector':vector,
        'reproducibility':reproducibility_report(records,providers,task_ids) if repeat>1 else None,
        'score_vector_is_not_a_single_total_score':True, 'records':records,
    }
    if suite == '0.2':
        manifest['freeze_sha256'] = _hash_bytes(oracle.V02_PATH.with_name('freeze_v02.json').read_bytes())
        manifest['incident_cluster_count'] = len({t['source_incident_id'] for t in fixtures['tasks'].values()})
        manifest['paired_cluster_differences'] = paired_cluster_report(records,providers)
        manifest['anomaly_review'] = evaluator_anomalies(records,vector)
    (root / 'records.json').write_bytes(_canonical(records).encode())
    (root / 'comparison_manifest.json').write_bytes(json.dumps(manifest,sort_keys=True,indent=2).encode())
    trace.append(f'comparison-complete:{run_id}', 'COMPARISON_COMPLETED',
                 {'run_id':run_id,'attempt_count':len(records),'score_vector':vector,'budget_stop':budget_stop})
    return manifest


def score_vector(records, providers, task_ids, suite='0.1', repeat=1):
    """Per-provider, per-dimension pass rates. Deliberately no grand total."""
    fixtures = oracle.suite_fixtures(suite)
    dims = [d['id'] for d in fixtures['capability_dimensions']]
    vector = {}
    for provider in providers:
        pid = provider.provider_id
        mine = [r for r in records if r['provider_id'] == pid]
        tasks_total = len(task_ids) * repeat
        full = sum(1 for r in mine if r['score']['full_pass'])
        by_dimension = {}
        for dim in dims:
            relevant = [r for r in mine if dim in r['dimensions']]
            assigned = sum(dim in fixtures['tasks'][t]['dimensions'] for t in task_ids) * repeat
            passed = sum(1 for r in relevant if r['score']['full_pass'])
            by_dimension[dim] = {
                'assigned': assigned,
                'passed': passed,
                'rate': (round(passed / assigned, 4) if assigned else None),
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
        }
        if suite == '0.2':
            entry = vector[pid]
            failed_provider = {'HTTP_ERROR','BUSINESS_ERROR','TRANSPORT_FAILED','CREDENTIAL_UNAVAILABLE',
                               'PROVIDER_RESPONSE_INVALID','EMPTY_CONTENT','TOKEN_BUDGET_EXHAUSTED','TASK_TIMEOUT','MODEL_ID_MISMATCH'}
            fmt = sum(r['score']['failure_type'] in ('UNPARSEABLE_OR_INVALID_FORMAT','MISSING_CONTRACT_KEYS') for r in mine)
            provider_failures = sum(r['score']['failure_type'] in failed_provider for r in mine)
            entry.update({'attempts_observed':len(mine), 'unattempted':tasks_total-len(mine),
                          'verdict_accuracy':round(entry['verdict_correct']/tasks_total,4),
                          'evidence_accuracy':round(entry['evidence_correct']/tasks_total,4),
                          'provider_failure_count':provider_failures, 'provider_failure_rate':round(provider_failures/tasks_total,4),
                          'format_failure_count':fmt, 'format_failure_rate':round(fmt/tasks_total,4),
                          'answer_available_count':sum(r['score']['parsed'] for r in mine),
                          'correct_refusals':sum(r['score']['full_pass'] and r['score']['observed_verdict'] in ('REFUSE','INSUFFICIENT_EVIDENCE') for r in mine),
                          'refusal_tasks_assigned':sum('PASS' not in fixtures['tasks'][t]['ground_truth']['accept_verdicts'] and 'FLAG_INCONSISTENT' not in fixtures['tasks'][t]['ground_truth']['accept_verdicts'] for t in task_ids),
                          'input_tokens_reported':sum(r['input_tokens'] or 0 for r in mine),
                          'output_tokens_reported':sum(r['output_tokens'] or 0 for r in mine),
                          'reasoning_tokens_reported':sum(r['reasoning_tokens'] or 0 for r in mine),
                          'reasoning_usage_missing':sum(r['reasoning_tokens'] is None for r in mine),
                          'latency_ms':sum(r['wall_ms'] for r in mine),
                          'cost_reported':sum(r['cost'] or 0 for r in mine),
                          'cost_missing_attempts':sum(r['cost'] is None for r in mine)})
    return vector


def paired_cluster_report(records, providers):
    """Same-task differences, then equal-weight cluster means; no inference."""
    from itertools import combinations
    result = {}
    for a, b in combinations(providers, 2):
        left = {r['task_id']: r for r in records if r['provider_id'] == a.provider_id}
        right = {r['task_id']: r for r in records if r['provider_id'] == b.provider_id}
        clusters = {}
        pairs = []
        for tid, r in left.items():
            if tid not in right:
                continue
            other = right[tid]
            delta = int(r['score']['full_pass']) - int(other['score']['full_pass'])
            clusters.setdefault(r['source_incident_id'], []).append(delta)
            pairs.append({'task_id': tid, 'full_pass_difference': delta,
                          'both_answers_parsed': r['score']['parsed'] and other['score']['parsed']})
        means = {k: round(sum(v) / len(v), 4) for k, v in clusters.items()}
        result[a.provider_id + '-' + b.provider_id] = {
            'paired_task_count': len(pairs), 'clusters_observed': len(means),
            'task_pairs': pairs, 'cluster_mean_differences': means,
            'equal_cluster_mean_difference': _mean(list(means.values())),
            'statistical_significance': None,
        }
    return result


def evaluator_anomalies(records, vector):
    """Frozen diagnostic thresholds trigger review, never score rewriting."""
    reasons = []
    if records and all(not r['score']['full_pass'] for r in records):
        reasons.append('ALL_TASKS_ZERO')
    if records and all(r['score']['full_pass'] for r in records):
        reasons.append('ALL_TASKS_FULL_PASS')
    for pid, entry in vector.items():
        if entry['tasks_full_pass'] == 0:
            reasons.append('ALL_TASKS_ZERO:' + pid)
        elif entry['tasks_full_pass'] == entry['tasks_assigned']:
            reasons.append('ALL_TASKS_FULL_PASS:' + pid)
    if len(vector) > 1:
        for dim in next(iter(vector.values()))['by_dimension']:
            rates = [v['by_dimension'][dim]['rate'] for v in vector.values()]
            if None not in rates and len(set(rates)) == 1:
                reasons.append('ALL_MODELS_SAME_DIMENSION:' + dim)
    if records:
        parse_failures = sum(r['score']['failure_type'] in
                             ('UNPARSEABLE_OR_INVALID_FORMAT', 'MISSING_CONTRACT_KEYS') for r in records)
        if parse_failures / len(records) >= 0.25:
            reasons.append('FORMAT_FAILURE_RATE_GE_25_PERCENT')
        parsed = [r for r in records if r['score']['parsed']]
        split = sum(r['score']['verdict_ok'] != r['score']['evidence_ok'] for r in parsed)
        if parsed and split / len(parsed) >= 0.25:
            reasons.append('VERDICT_EVIDENCE_SPLIT_GE_25_PERCENT')
    return {'status': 'EVALUATOR_ANOMALY_REVIEW_REQUIRED' if reasons else 'NO_TRIGGER',
            'reasons': reasons, 'automatic_score_change': False}


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
    parser.add_argument('--suite', choices=['0.1','0.2'], default='0.1')
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
                              trace_path=args.trace, repeat=args.repeat, suite=args.suite)
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
