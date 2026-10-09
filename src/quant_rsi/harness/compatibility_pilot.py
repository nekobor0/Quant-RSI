"""Fixed six-task compatibility pilot; default operation is credential-free.

The serial request adapter delegates transport/parsing to the frozen ChatProvider.
It only supplies native parameters and captures the non-sensitive response envelope.
No retry, model discovery, mutable evaluator, or general-purpose harness is added.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.request
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from quant_rsi.harness import capability_oracle as oracle
from quant_rsi.harness import providers
from quant_rsi.harness.comparison import ROOT, evaluator_anomalies, score_vector
from quant_rsi.ledger.store import TraceStore

FREEZE = ROOT / 'benchmark/capability_public/pilot_v02/freeze.json'


def digest(raw):
    return sha256(raw).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, obj):
    Path(path).write_bytes(json.dumps(obj, sort_keys=True, indent=2,
                                    ensure_ascii=True, allow_nan=False).encode())


def prompts(plan):
    tasks = oracle.suite_fixtures('0.2')['tasks']
    return {tid: providers.build_prompt(tid, tasks[tid]['public_input'],
                                       contract=oracle.v02_contract(tid))
            for tid in plan['task_ids']}


def validate_freeze():
    plan = load(FREEZE)
    for relative, expected in plan['sha256'].items():
        if digest((ROOT / relative).read_bytes()) != expected:
            raise ValueError('pilot binding changed: ' + relative)
    base = load(oracle.V02_PATH.with_name('freeze_v02.json'))
    for relative, expected in base['sha256'].items():
        if digest((ROOT / relative).read_bytes()) != expected:
            raise ValueError('base v0.2 binding changed: ' + relative)
    texts = prompts(plan)
    if {t: digest(p.encode()) for t, p in texts.items()} != plan['prompt_hashes']:
        raise ValueError('pilot prompt changed')
    if digest(providers.SYSTEM_PROMPT.encode()) != plan['system_prompt_sha256']:
        raise ValueError('system prompt changed')
    for text in texts.values():
        if len((providers.SYSTEM_PROMPT + text).encode()) + 1024 > plan['input_per_call']:
            raise ValueError('conservative prompt input bound exceeded')
    return plan


class PilotChatProvider(providers.ChatProvider):
    """Scoped serial adapter; the original urlopen is restored even on failure."""

    def reply(self, task_id, prompt):
        self.raw = None
        self.envelope = {}
        self.request_sha256 = None
        native = load(FREEZE)['providers'][self.provider_id]['native_parameters']
        original_open = providers.urllib.request.urlopen

        def configured_open(request, timeout):
            body = json.loads(request.data)
            if self.provider_id == 'xiaomi':
                body['max_completion_tokens'] = body.pop('max_tokens')
            body.update(native)
            wire = json.dumps(body, sort_keys=True, separators=(',', ':')).encode()
            self.request_sha256 = digest(wire)  # body only, never authorization headers
            configured = urllib.request.Request(request.full_url, data=wire,
                                                headers=dict(request.header_items()), method='POST')
            response = original_open(configured, timeout=timeout)
            owner = self

            class Capture:
                status = response.status

                def __enter__(self):
                    response.__enter__()
                    return self

                def __exit__(self, *args):
                    return response.__exit__(*args)

                def read(self):
                    raw = response.read()
                    owner.raw = raw
                    try:
                        obj = json.loads(raw)
                        owner.envelope = obj if isinstance(obj, dict) else {}
                    except (ValueError, UnicodeError):
                        pass
                    return raw

            return Capture()

        with patch.object(providers.urllib.request, 'urlopen', configured_open):
            return super().reply(task_id, prompt)


def output_safe(raw, keys=()):
    if raw is None:
        return True
    # Only newly authorized in-process credentials are compared, never hashed.
    decoded = raw.decode('utf-8', errors='replace')
    try:
        decoded += json.dumps(json.loads(raw), ensure_ascii=False)
    except (ValueError, UnicodeError):
        pass
    return not any(k and k in decoded for k in keys) and not re.search(
        r'\bsk-[A-Za-z0-9_-]{16,}\b|Bearer\s+[A-Za-z0-9._-]{16,}', decoded)


def failure_for(reply):
    if reply.failure_type:
        return reply.failure_type
    if reply.finish_reason != 'stop':
        return 'PROVIDER_FINISH_INCOMPLETE'
    return None


def budget_stage(reply):
    if reply.finish_reason != 'length':
        return None
    if reply.text:
        return 'OUTPUT_TRUNCATED'
    if (type(reply.reasoning_tokens) is int and type(reply.output_tokens) is int
            and reply.reasoning_tokens == reply.output_tokens and reply.output_tokens >= 24000):
        return 'REASONING_EXHAUSTED_NO_CONTENT'
    return 'COMBINED_TOKEN_EXHAUSTION_STAGE_UNKNOWN'


def usage_cost(reply, envelope, config):
    values = (reply.input_tokens, reply.output_tokens)
    if any(type(v) is not int or v < 0 for v in values):
        return None, 'UNKNOWN_USAGE'
    usage = envelope.get('usage') or {}
    if not isinstance(usage, dict) or not isinstance(usage.get('prompt_tokens_details', {}), dict):
        return None, 'INVALID_USAGE'
    total = usage.get('total_tokens')
    if total is not None and (type(total) is not int or total != sum(values)):
        return None, 'INVALID_TOTAL_USAGE'
    if reply.reasoning_tokens is not None and (
            type(reply.reasoning_tokens) is not int or not 0 <= reply.reasoning_tokens <= values[1]):
        return None, 'INVALID_REASONING_USAGE'
    cached = (usage.get('prompt_tokens_details') or {}).get('cached_tokens',
                                                              usage.get('prompt_cache_hit_tokens'))
    if cached is not None and (type(cached) is not int or not 0 <= cached <= values[0]):
        return None, 'INVALID_CACHE_USAGE'
    rates = config['prices_cny_per_million']
    hit = cached or 0
    cost = ((Decimal(values[0] - hit) * Decimal(rates['input_miss'])
             + Decimal(hit) * Decimal(rates['input_hit'])
             + Decimal(values[1]) * Decimal(rates['output'])) / Decimal(1000000))
    # DeepSeek peak rates are an upper estimate; API usage is not a settled invoice.
    return str(cost), 'PUBLISHED_RATE_UPPER_ESTIMATE' if config['peak_rate'] else (
        'PUBLISHED_RATE_ESTIMATE' if cached is not None else 'CACHE_UNKNOWN_UPPER_ESTIMATE')


def score_record(task_id, text, failure):
    score = oracle.adjudicate(task_id, text.encode() if text is not None else None,
                             suite='0.2', failure_type=failure).to_dict()
    issues = score['exact_mismatches'] + score['forbidden_values']
    # Frozen evidence_ok includes reason. These diagnostics expose that coupling.
    reason_failed = [x for x in issues if x.startswith('reason:')]
    diagnostics = {
        'verdict_ok': score['verdict_ok'], 'evidence_and_reason_ok': score['evidence_ok'],
        'evidence_only_ok': score['parsed'] and not score['missing_keys'] and not [
            x for x in issues if not x.startswith('reason:')],
        'reason_ok': score['parsed'] and not score['missing_keys'] and not reason_failed,
        'reason_failed_predicates': reason_failed,
        'failed_predicates': score['missing_keys'] + issues + (
            ['verdict:WRONG_TERMINAL'] if score['parsed'] and not score['verdict_ok'] else []),
        'human_semantic_review': 'PENDING' if score['parsed'] else 'NO_COMPLETE_ANSWER',
        'confirmed_legal_answer_misjudgments': None,
    }
    return score, diagnostics


def check_authorization(plan, authorization):
    expected = {'approved': True, 'keys_rotated': True, 'call_cap': 12,
                'freeze_sha256': digest(FREEZE.read_bytes()),
                'entry_sha256': digest(Path(__file__).read_bytes()),
                'money_caps_cny': plan['money_caps_cny']}
    if any(authorization.get(k) != v for k, v in expected.items()):
        raise ValueError('explicit human batch approval, key rotation and exact freeze/entry binding required')


def run(run_id, authorization, output_root=None):
    plan = validate_freeze()
    check_authorization(plan, authorization)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', run_id):
        raise ValueError('invalid run id')
    pair = [PilotChatProvider(**c['chat_provider']) for c in plan['providers'].values()]
    # Credentials are touched only after the authorization gate above.
    if not all(os.environ.get(p.api_key_env) for p in pair):
        raise ValueError('credential unavailable; no request dispatched')
    keys = [p._resolve_key() for p in pair]
    root = Path(output_root or ROOT / 'benchmark/capability_public/runs/compatibility_pilot') / run_id
    root.mkdir(parents=True, exist_ok=False)  # a crashed run cannot be restarted/retried
    trace = TraceStore(root / 'trace.sqlite')
    texts = prompts(plan)
    save(root / 'prompts.json', {'system': providers.SYSTEM_PROMPT, 'user': texts})
    trace.append('start', 'PILOT_STARTED', {'freeze_sha256': digest(FREEZE.read_bytes()),
                                         'entry_sha256': digest(Path(__file__).read_bytes()),
                                         'task_ids': plan['task_ids'], 'real_api_authorized': True})
    records, stop = [], None
    reserved = {p.provider_id: Decimal(0) for p in pair}
    schedule = [(p, t) for i, t in enumerate(plan['task_ids'])
                for p in (pair if i % 2 == 0 else pair[::-1])]
    started = time.monotonic()
    for index, (p, tid) in enumerate(schedule, 1):
        config = plan['providers'][p.provider_id]
        ceiling = Decimal(config['worst_cost_cny_per_call'])
        if (index > 12 or reserved[p.provider_id] + ceiling > Decimal(plan['money_caps_cny'][p.provider_id])
                or time.monotonic() - started + p.timeout_s > plan['wall_seconds']):
            stop = 'BUDGET_DENIED'
            break
        reserved[p.provider_id] += ceiling
        trace.append(f'reserve:{index}', 'PILOT_RESERVED', {
            'index': index, 'task_id': tid, 'provider_id': p.provider_id,
            'candidate_trials': 0, 'input_tokens': plan['input_per_call'],
            'output_tokens': p.max_tokens, 'cost_cny': str(ceiling)})
        reply = p.reply(tid, texts[tid])
        safe = output_safe(p.raw, keys)
        failure = failure_for(reply) if safe else 'SECURITY_OUTPUT_NOT_RETAINABLE'
        text = reply.text if safe else None
        raw_ref = None
        if safe and p.raw is not None:
            raw_ref = f'raw_{index:02d}.json'
            (root / raw_ref).write_bytes(p.raw)
        cost, cost_status = usage_cost(reply, p.envelope, config) if safe else (None, 'NOT_RETAINED')
        if safe and reply.ok and reply.observed_model != p.model_id:
            failure = 'MODEL_ID_MISMATCH' if reply.observed_model else 'MODEL_METADATA_MISSING'
            stop = failure
        if not safe:
            stop = 'SECURITY_OUTPUT_NOT_RETAINABLE'
        elif reply.http_status in (401, 403, 429):
            stop = 'RATE_LIMIT_STOP' if reply.http_status == 429 else 'AUTHENTICATION_STOP'
        if cost is None:
            stop = stop or 'UNKNOWN_USAGE_RECONCILIATION_REQUIRED'
        elif reply.input_tokens > plan['input_per_call'] or reply.output_tokens > p.max_tokens:
            stop = 'PER_CALL_TOKEN_BUDGET_BREACH'
        if reply.wall_ms > p.timeout_s * 1000:
            stop = stop or 'SOCKET_TIMEOUT_NOT_A_WALL_DEADLINE'
        score, diagnostics = score_record(tid, text, failure)
        task = oracle.suite_fixtures('0.2')['tasks'][tid]
        record = dict(task_id=tid, provider_id=p.provider_id, model_id=p.model_id,
                      observed_model=reply.observed_model if safe else None,
                      source_incident_id=task['source_incident_id'], dimensions=task['dimensions'],
                      prompt_sha256=plan['prompt_hashes'][tid], request_sha256=p.request_sha256,
                      raw_ref=raw_ref, raw_sha256=digest(p.raw) if raw_ref else None,
                      response_text=text, response_sha256=digest(text.encode()) if text is not None else None,
                      transport_ok=reply.ok, http_status=reply.http_status,
                      provider_failure=failure, finish_reason=reply.finish_reason if safe else None,
                      complete=not failure, budget_stage=budget_stage(reply) if safe else None,
                      input_tokens=reply.input_tokens if safe else None,
                      output_tokens=reply.output_tokens if safe else None,
                      reasoning_tokens=reply.reasoning_tokens if safe else None, wall_ms=reply.wall_ms,
                      provider_attempts=reply.attempts, cost=float(cost) if cost is not None else None,
                      cost_cny_decimal=cost, currency='CNY', cost_status=cost_status,
                      settled_invoice_cost='UNKNOWN', score=score, diagnostics=diagnostics)
        records.append(record)
        trace.append(f'answer:{index}', 'PILOT_ATTEMPT', record)
        save(root / f'attempt_{index:02d}.json', record)
        if stop:
            break
    vector = score_vector(records, pair, plan['task_ids'], suite='0.2')
    # Add compatibility rates without presenting model rankings or inferential statistics.
    for p in pair:
        mine = [r for r in records if r['provider_id'] == p.provider_id]
        vector[p.provider_id]['completion_rate_assigned'] = sum(r['complete'] for r in mine) / 6
        vector[p.provider_id]['task_completion_rate_assigned'] = sum(
            r['complete'] and r['score']['parsed'] and not r['score']['missing_keys'] for r in mine) / 6
        vector[p.provider_id]['provider_failure_rate_assigned'] = sum(bool(r['provider_failure']) for r in mine) / 6
        vector[p.provider_id]['provider_failure_count'] = sum(bool(r['provider_failure']) for r in mine)
        vector[p.provider_id]['provider_failure_rate'] = vector[p.provider_id]['provider_failure_rate_assigned']
        reason_failures = sum(not r['diagnostics']['reason_ok'] for r in mine if r['score']['parsed'])
        vector[p.provider_id]['reason_contract_failures'] = reason_failures
        vector[p.provider_id]['reason_contract_failure_rate_assigned'] = reason_failures / 6
        contract_failures = sum(not r['provider_failure'] and (
            not r['score']['parsed'] or bool(r['score']['missing_keys']) or any(
                x in ('extra_contract_keys', 'unsupported_evidence_field', 'evidence:NOT_AN_OBJECT',
                      'reason:EMPTY_OR_INVALID', 'reason:UNSUPPORTED_CLAUSE', 'reason:INVALID_ASSERTION')
                for x in r['score']['exact_mismatches'])) for r in mine)
        vector[p.provider_id]['format_or_contract_failure_rate_assigned'] = contract_failures / 6
        vector[p.provider_id]['estimated_cost_cny'] = str(sum((Decimal(r['cost_cny_decimal']) for r in mine if r['cost_cny_decimal'] is not None), Decimal(0)))
        vector[p.provider_id]['cost_basis'] = 'USAGE_ESTIMATE_NOT_SETTLED_INVOICE'
    result = {'status': 'REAL_PILOT_EXECUTED', 'labels': 'PUBLIC_UNSEALED_PROVISIONAL',
              'is_formal_model_ranking': False, 'source_cluster_count': 6,
              'source_independence_caveat': plan['source_independence_caveat'],
              'freeze_sha256': digest(FREEZE.read_bytes()), 'entry_sha256': digest(Path(__file__).read_bytes()),
              'records': records, 'unattempted': [{'provider_id': p.provider_id, 'task_id': t,
                                                  'failure_type': 'BUDGET_DENIED', 'stop': stop}
                                                 for p, t in schedule[len(records):]],
              'stop': stop, 'calls': len(records), 'reserved_cost_cny': {k: str(v) for k, v in reserved.items()},
              'score_vector': vector, 'anomaly_review': evaluator_anomalies(records, vector),
              'confirmed_legal_answer_misjudgments': None, 'human_review_status': 'PENDING',
              'conditions_not_equivalent': plan['conditions_not_equivalent']}
    trace.append('complete', 'PILOT_COMPLETED', {'calls': len(records), 'stop': stop})
    result['trace_anchor'] = trace.read()[-1]['event_hash']
    save(root / 'result.json', result)
    return result


def replay(root):
    """No credentials/network; verify original trace, raw outputs and unchanged scores."""
    plan = validate_freeze()
    root = Path(root)
    result = load(root / 'result.json')
    events = TraceStore(root / 'trace.sqlite').read()
    if result['freeze_sha256'] != digest(FREEZE.read_bytes()) or events[-1]['event_hash'] != result['trace_anchor']:
        raise ValueError('run freeze or trace anchor changed')
    traced = [e['payload'] for e in events if e['kind'] == 'PILOT_ATTEMPT']
    if traced != result['records']:
        raise ValueError('record/trace mismatch')
    if load(root / 'prompts.json') != {'system': providers.SYSTEM_PROMPT, 'user': prompts(plan)}:
        raise ValueError('stored prompt mismatch')
    for i, record in enumerate(traced, 1):
        if load(root / f'attempt_{i:02d}.json') != record:
            raise ValueError('attempt file mismatch')
        if record['raw_ref']:
            if record['raw_ref'] != f'raw_{i:02d}.json':
                raise ValueError('unexpected raw reference')
            raw = (root / record['raw_ref']).read_bytes()
            if not output_safe(raw) or digest(raw) != record['raw_sha256']:
                raise ValueError('unsafe or changed raw output')
            try:
                obj = json.loads(raw)
                content = ((obj.get('choices') or [{}])[0].get('message') or {}).get('content')
                if record['provider_failure'] in ('BUSINESS_ERROR', 'PROVIDER_RESPONSE_INVALID'):
                    content = None
                normalized = content if isinstance(content, str) and content.strip() else None
            except (ValueError, UnicodeError, AttributeError, TypeError):
                normalized = None
            if normalized != record['response_text']:
                raise ValueError('response/envelope mismatch')
        score, _ = score_record(record['task_id'], record['response_text'], record['provider_failure'])
        if score != record['score']:
            raise ValueError('frozen score drift; review required')
    return {'status': 'OFFLINE_REPLAY_VERIFIED', 'attempts': len(traced), 'real_calls': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorization', type=Path)
    parser.add_argument('--run-id')
    parser.add_argument('--replay', type=Path)
    args = parser.parse_args()
    if args.replay:
        result = replay(args.replay)
    elif args.authorization:
        if not args.run_id:
            parser.error('--run-id required for an authorized real batch')
        result = run(args.run_id, load(args.authorization))
    else:
        plan = validate_freeze()
        result = {'status': 'OFFLINE_PREPARED_REAL_CALLS_NOT_AUTHORIZED', 'real_calls': 0,
                  'task_ids': plan['task_ids'], 'freeze_sha256': digest(FREEZE.read_bytes()),
                  'entry_sha256': digest(Path(__file__).read_bytes())}
    print(json.dumps(result if 'records' not in result else {'calls': result['calls'], 'stop': result['stop']}, indent=2))


if __name__ == '__main__':
    main()
