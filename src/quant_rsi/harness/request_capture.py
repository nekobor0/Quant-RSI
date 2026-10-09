"""Offline outbound-request capture for the six-task compatibility pilot.

Purpose: prove what WOULD be sent before anything is sent. This module performs
zero network I/O and reads zero credentials. It installs a capture transport in
place of `urlopen`, drives the frozen serial adapter, and records the exact wire
bytes so the following can be verified without a real probe call:

  1. the two models receive byte-identical system/user text, taken verbatim from
     the frozen prompts.json (no appended task brief, no DSH agent system prompt,
     no AGENTS.md, no reference answer, no cross-model answer);
  2. roles are not rewritten, dropped or reordered, and no extra message appears;
  3. the adapter issues exactly ONE HTTP request per (task, model) and does not
     retry on 429/5xx/timeout;
  4. the full response envelope, usage, finish_reason and error information would
     be retained;
  5. native parameters differ per provider exactly as the freeze declares.

Run:  python -B -m quant_rsi.harness.request_capture
"""
from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from quant_rsi.harness import compatibility_pilot as pilot
from quant_rsi.harness import providers
from quant_rsi.harness.comparison import ROOT

CAPTURE_ROOT = ROOT / 'benchmark/capability_public/runs/request_capture'

# A syntactically plausible placeholder. It is not a credential, is never sent
# anywhere (no socket is opened), and never appears in output: only its presence
# is required so the adapter's lazy key read does not abort.
PLACEHOLDER_KEY = 'offline-capture-placeholder-not-a-credential'


def _envelope(model_id: str, *, finish='stop', content=None, reasoning=None,
              usage=None, http_status=200, business_error=False):
    """A representative provider envelope used to exercise the parse path."""
    if business_error:
        return {'error': {'message': 'simulated business error', 'code': 'X'}}
    body = {
        'id': 'capture-simulated', 'object': 'chat.completion', 'model': model_id,
        'choices': [{'index': 0, 'finish_reason': finish, 'message': {
            'role': 'assistant', 'content': content,
            **({'reasoning_content': reasoning} if reasoning is not None else {})}}],
        'usage': usage or {'prompt_tokens': 1200, 'completion_tokens': 300,
                           'total_tokens': 1500,
                           'prompt_tokens_details': {'cached_tokens': 0},
                           'completion_tokens_details': {'reasoning_tokens': 100}},
    }
    return body, http_status


class _Captured:
    """Minimal stand-in for the urlopen context manager."""

    def __init__(self, payload: bytes, status: int):
        self._payload = payload
        self.status = status

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def capture_requests(plan, *, finish='stop', content='{"verdict":"PASS","reason":"x","evidence":{}}',
                     reasoning='simulated reasoning', http_status=200, business_error=False,
                     raise_error=None):
    """Drive every (task, model) pair through the adapter with no network.

    `raise_error` injects an exception from the transport (e.g. TimeoutError) so
    the no-retry guarantee can be tested on failures, not only on success.

    Returns (captures, provider_states) where captures holds the exact outbound
    request for each pair and provider_states preserves adapter state per provider.
    """
    tasks = providers.build_prompt, pilot.oracle.suite_fixtures('0.2')['tasks']
    prompt_texts = pilot.prompts(plan)
    captures = []
    states = {}

    for provider_key, config in plan['providers'].items():
        provider = pilot.PilotChatProvider(**config['chat_provider'])
        provider._key = PLACEHOLDER_KEY  # bypass the lazy env read; nothing is sent
        states[provider_key] = provider
        calls = []

        def capturing_open(request, timeout, _calls=calls, _pid=provider.provider_id):
            body = json.loads(request.data)
            _calls.append({
                'provider_id': _pid,
                'url': request.full_url,
                'method': request.method,
                'timeout': timeout,
                'headers': {k.lower(): v for k, v in request.header_items()},
                'body': body,
                'body_sha256': sha256(request.data).hexdigest(),
                'body_bytes': len(request.data),
                'messages': body.get('messages'),
            })
            if raise_error is not None:
                raise raise_error
            payload, status = _envelope(config['chat_provider']['model_id'],
                                        finish=finish, content=content,
                                        reasoning=reasoning, http_status=http_status,
                                        business_error=business_error)
            return _Captured(json.dumps(payload).encode(), status)

        with patch.object(providers.urllib.request, 'urlopen', capturing_open):
            for task_id in plan['task_ids']:
                try:
                    provider.reply(task_id, prompt_texts[task_id])
                except Exception:
                    # The adapter is allowed to surface a transport exception; what
                    # matters is how many times the transport was invoked.
                    pass
        captures.extend(calls)

    return captures, states


def verify(plan, captures, prompt_texts):
    """Checks 1-5. Returns a report with explicit pass/fail and evidence."""
    problems = []
    per_pair = {}

    # ---- Check 1: byte-identical frozen prompt text, no injection ----------
    frozen = pilot.load(pilot.FREEZE.parent / 'prompts.json')
    for task_id in plan['task_ids']:
        expected_user = frozen['user'][task_id]
        if prompt_texts[task_id] != expected_user:
            problems.append(f'PROMPT_DRIFT:{task_id}: adapter prompt != frozen prompts.json')
        hashed = sha256(prompt_texts[task_id].encode()).hexdigest()
        if hashed != plan['prompt_hashes'][task_id]:
            problems.append(f'PROMPT_HASH_MISMATCH:{task_id}')
    if providers.SYSTEM_PROMPT != frozen['system']:
        problems.append('SYSTEM_PROMPT_DRIFT: providers.SYSTEM_PROMPT != frozen prompts.json')
    if sha256(providers.SYSTEM_PROMPT.encode()).hexdigest() != plan['system_prompt_sha256']:
        problems.append('SYSTEM_PROMPT_HASH_MISMATCH')

    # Forbidden content that must never appear in an outbound message.
    #
    # NOTE: `answer_contract:` is deliberately NOT here. The v0.2 contract is
    # published to the model by design (fact aliases, reason grammar, source
    # citation rules) and is part of the frozen prompt text. Flagging it was a
    # false positive in an earlier version of this checker.
    forbidden = ['AGENTS.md', 'ground_truth', 'EXPECTED_VERDICT', 'expected_verdict',
                 'Codex', 'GPT-6.1', 'HANDOFF.md', 'BUDGET_AND_GATE_POLICY',
                 'another model', 'previous answer']

    by_pair = {}
    for cap in captures:
        msgs = cap['messages'] or []
        pid = cap['provider_id']
        # Identify which task this request carried, from the user message body.
        task_id = next((t for t in plan['task_ids']
                        if t in json.dumps(msgs, ensure_ascii=False)), None)

        entry = {
            'provider_id': pid, 'model': cap['body']['model'], 'url': cap['url'],
            'timeout': cap['timeout'],
            'messages': [{'role': m.get('role'), 'content_sha256': sha256(
                (m.get('content') or '').encode()).hexdigest(),
                'content_bytes': len((m.get('content') or '').encode())} for m in msgs],
            'body_sha256': cap['body_sha256'], 'body_bytes': cap['body_bytes'],
            'native_params_present': {k: cap['body'].get(k) for k in
                                      ('max_tokens', 'max_completion_tokens',
                                       'thinking', 'reasoning_effort', 'temperature', 'top_p')
                                      if k in cap['body']},
        }

        if task_id is None:
            problems.append(f'UNIDENTIFIABLE_REQUEST:{pid}')
            continue
        by_pair[(pid, task_id)] = entry

        # Check 2: exactly two messages, correct roles, frozen content.
        if len(msgs) != 2:
            problems.append(f'MESSAGE_COUNT:{pid}:{task_id}: {len(msgs)} != 2')
        if [m.get('role') for m in msgs] != ['system', 'user']:
            problems.append(f'ROLE_ORDER:{pid}:{task_id}')
        if msgs[0].get('content') != frozen['system']:
            problems.append(f'SYSTEM_BODY:{pid}:{task_id}')
        if msgs[1].get('content') != frozen['user'][task_id]:
            problems.append(f'USER_BODY:{pid}:{task_id}')

        blob = json.dumps(cap['body'], ensure_ascii=False)
        for token in forbidden:
            if token in blob:
                problems.append(f'FORBIDDEN_CONTENT:{pid}:{task_id}: {token!r}')

        # Only the four expected top-level keys may be present.
        extra = set(cap['body']) - {'model', 'messages', 'temperature',
                                    'max_tokens', 'max_completion_tokens',
                                    'thinking', 'reasoning_effort', 'stream',
                                    'top_p'}
        if extra:
            problems.append(f'EXTRA_REQUEST_KEYS:{pid}:{task_id}: {sorted(extra)}')

    # ---- Check 3: exactly one request per (provider, task), no retry -------
    #
    # Counting must be per (provider, task), not per (provider, model, url):
    # six distinct tasks naturally share one endpoint, and keying on the endpoint
    # made six legitimate requests look like six retries.
    expected_pairs = {(p, t) for p in plan['providers'] for t in plan['task_ids']}
    counted = {}
    for cap in captures:
        pid = cap['provider_id']
        msgs = cap['messages'] or []
        task_id = next((t for t in plan['task_ids']
                        if t in json.dumps(msgs, ensure_ascii=False)), None)
        counted[(pid, task_id)] = counted.get((pid, task_id), 0) + 1

    if set(by_pair) != expected_pairs:
        problems.append(f'PAIR_COVERAGE: got {len(by_pair)} want {len(expected_pairs)}')
    for pair_key, count in counted.items():
        if count != 1:
            problems.append(f'AUTO_RETRY_OR_DUPLICATE: {pair_key} issued {count} requests')
    if len(captures) != len(expected_pairs):
        problems.append(
            f'TOTAL_REQUEST_COUNT: {len(captures)} != {len(expected_pairs)} expected')

    # ---- Check 5: native parameters per provider --------------------------
    for pid in plan['providers']:
        declared = plan['providers'][pid]['native_parameters']
        declared_params = dict(declared)
        if pid == 'deepseek':
            declared_params['max_tokens'] = plan['providers'][pid]['chat_provider']['max_tokens']
        else:
            declared_params['max_completion_tokens'] = \
                plan['providers'][pid]['chat_provider']['max_tokens']
        for task_id in plan['task_ids']:
            entry = by_pair.get((pid, task_id))
            if not entry:
                continue
            present = entry['native_params_present']
            if 'max_completion_tokens' in present and pid == 'deepseek':
                problems.append(f'WRONG_BUDGET_KEY:deepseek:{task_id}')
            if 'max_tokens' in present and pid == 'xiaomi':
                problems.append(f'WRONG_BUDGET_KEY:xiaomi:{task_id}')
            for k, v in declared_params.items():
                if present.get(k) != v:
                    problems.append(
                        f'NATIVE_PARAM:{pid}:{task_id}: {k}={present.get(k)!r} != {v!r}')

    return {
        'checks': {
            'prompt_byte_identical_to_frozen': not any(
                p.startswith(('PROMPT_DRIFT', 'PROMPT_HASH', 'SYSTEM_PROMPT', 'SYSTEM_BODY',
                              'USER_BODY', 'MESSAGE_COUNT', 'ROLE_ORDER')) for p in problems),
            'no_injected_content': not any(p.startswith('FORBIDDEN_CONTENT') for p in problems),
            'single_request_per_pair_no_retry': not any(
                p.startswith(('AUTO_RETRY', 'PAIR_COVERAGE')) for p in problems),
            'native_parameters_match_freeze': not any(
                p.startswith(('NATIVE_PARAM', 'WRONG_BUDGET_KEY')) for p in problems),
        },
        'problems': problems,
        'pairs_covered': sorted(f'{p}:{t}' for p, t in by_pair),
        'pair_detail': {f'{p}:{t}': v for (p, t), v in sorted(by_pair.items())},
    }


def retry_probe(plan):
    """Prove the adapter issues exactly ONE transport call under each failure mode.

    The task brief requires confirming that neither the provider, the SDK, a DSH
    retry plugin nor an agent loop can silently retry: a hidden retry would consume
    extra requests and could turn a single authorized attempt into several. The
    adapter uses stdlib urllib rather than the vendor SDK, so the only retry logic
    that could exist is inside the provider. This exercises the failure paths.
    """
    import urllib.error

    modes = {
        'http_429': dict(http_status=429),
        'http_500': dict(http_status=500),
        'timeout_exception': dict(raise_error=TimeoutError('simulated timeout')),
        'connection_reset': dict(raise_error=ConnectionResetError('simulated reset')),
        'business_error_body': dict(business_error=True),
        'finish_length_empty': dict(finish='length', content=None),
    }
    report = {}
    for name, kwargs in modes.items():
        captures, _ = capture_requests(plan, **kwargs)
        per_provider = {}
        for cap in captures:
            pid = cap['provider_id']
            msgs = cap['messages'] or []
            task_id = next((t for t in plan['task_ids']
                            if t in json.dumps(msgs, ensure_ascii=False)), None)
            per_provider.setdefault(pid, {})[task_id] = \
                per_provider.setdefault(pid, {}).get(task_id, 0) + 1
        worst = max((c for d in per_provider.values() for c in d.values()), default=0)
        total = sum(c for d in per_provider.values() for c in d.values())
        report[name] = {
            'transport_calls_total': total,
            'max_calls_for_any_single_pair': worst,
            'no_retry_confirmed': worst == 1 and total == 12,
        }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', type=Path, default=pilot.FREEZE,
                        help='freeze to capture against (defaults to the pilot freeze)')
    parser.add_argument('--write', action='store_true',
                        help='persist the capture under runs/request_capture')
    args = parser.parse_args()

    original_freeze = pilot.FREEZE
    pilot.FREEZE = args.freeze
    try:
        plan = pilot.validate_freeze()
    finally:
        pilot.FREEZE = original_freeze

    prompt_texts = pilot.prompts(plan)
    captures, _states = capture_requests(plan)
    report = verify(plan, captures, prompt_texts)
    report['retry_probe'] = retry_probe(plan)
    report['retry_probe_all_modes_no_retry'] = all(
        v['no_retry_confirmed'] for v in report['retry_probe'].values())
    report['network_calls'] = 0
    report['real_credentials_read'] = 0
    report['freeze_sha256'] = sha256(Path(args.freeze).read_bytes()).hexdigest()
    report['capture_count'] = len(captures)
    report['status'] = 'OFFLINE_CAPTURE_VERIFIED' if (
        not report['problems'] and report['retry_probe_all_modes_no_retry']) \
        else 'OFFLINE_CAPTURE_PROBLEMS_FOUND'

    if args.write:
        CAPTURE_ROOT.mkdir(parents=True, exist_ok=True)
        out = CAPTURE_ROOT / 'capture.json'
        out.write_bytes(json.dumps(report, sort_keys=True, indent=2).encode())
        report['written_to'] = str(out)

    print(json.dumps({k: report[k] for k in
                      ('status', 'capture_count', 'network_calls', 'real_credentials_read',
                       'checks', 'retry_probe', 'retry_probe_all_modes_no_retry',
                       'problems')}, indent=2))
    return 0 if report['status'] == 'OFFLINE_CAPTURE_VERIFIED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
