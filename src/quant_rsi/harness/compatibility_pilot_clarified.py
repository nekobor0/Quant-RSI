"""Versioned public-contract clarification and failure capture; no default API calls.

Reuse the frozen pilot's runner, reservations, evaluator and TraceStore. Scoped
bindings leave every original module and freeze unchanged after execution.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sqlite3
import urllib.error
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from http.client import IncompleteRead
from pathlib import Path
from unittest.mock import patch

from quant_rsi.harness import capability_oracle as oracle, compatibility_pilot as pilot, providers
from quant_rsi.harness.comparison import ROOT
from quant_rsi.ledger.store import Anchor, TraceStore, _read, verify_events

FREEZE = ROOT / 'benchmark/capability_public/pilot_v02_clarified/freeze.json'
ENTRY = Path(__file__)
CONTRACT_VERSION = 'PUBLIC_ANSWER_CONTRACT_V0.2.1_CLARIFIED'
FAILURE_CAPTURE_LIMIT = 1024 * 1024
ORIGINAL_OUTPUT_SAFE = pilot.output_safe


def failure_bytes_safe(raw, keys):
    # Partial/error bodies may not be valid JSON: still recognize escaped keys.
    decoded = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m[1], 16)),
                     raw.decode('utf-8', errors='replace'))
    return (ORIGINAL_OUTPUT_SAFE(raw, keys)
            and ORIGINAL_OUTPUT_SAFE(decoded.encode('utf-8', errors='replace'), keys)
            and not any(k and len(k) >= 12 and k[:12] in decoded for k in keys))


def clarified_contract(task_id):
    contract = copy.deepcopy(oracle.v02_contract(task_id))
    contract['version'] = CONTRACT_VERSION
    contract['reason_role'] = (
        'Semicolon-separated clauses: a listed reason_explanations sentence, '
        '<canonical_fact_name>=<JSON value of the declared fact type>, or '
        'NOT(<canonical_fact_name>=<JSON value of the declared fact type>). '
        'Replace canonical_fact_name with a key from facts, for example items_len; '
        'it is a placeholder, not the literal word fact. Do not write fact={...}. '
        'Use one named fact per clause. Evidence aliases are accepted only in evidence; '
        'reason requires canonical names. NOT denies that single assertion; do not '
        'deny a true fact. Arbitrary prose assertions are unsupported. '
        'A listed non-factual explanation alone is permitted; evidence remains mandatory.'
    )
    contract['reason_syntax_examples'] = {
        name: f'{name}=<JSON {rule["type"]} value>'
        for name, rule in contract['facts'].items()
    }
    name, rule = next(iter(contract['facts'].items()))
    example = json.dumps({'number': 7, 'boolean': True, 'string_set': ['SYNTAX_ONLY']}.get(
        rule['type'], 'SYNTAX_ONLY'))
    contract['reason_example_note'] = (
        f'Angle brackets mark placeholders, not literal answer text. Syntax examples: '
        f'{name}={example} or NOT({name}={example}). These example values are arbitrary, '
        'not answers; obtain actual values from input. JSON strings use double quotes, '
        'numbers are unquoted, booleans are true/false.'
    )
    contract['identifier_policy'] = (
        'Copy string identifiers and timestamps exactly from the supplied input. '
        'Do not insert hyphens, change timezone spelling, or reformat date/time strings.'
    )
    contract['sources'] = (
        'evidence must contain sources: an array of every source ID in input, exactly '
        'once. The singular field source is not accepted. Unknown sources are rejected.'
    )
    return contract


def prompts(plan):
    tasks = oracle.suite_fixtures('0.2')['tasks']
    return {tid: providers.build_prompt(tid, tasks[tid]['public_input'],
                                       contract=clarified_contract(tid))
            for tid in plan['task_ids']}


def utc_now():
    return datetime.now(timezone.utc)


def require_offpeak_room(plan):
    # Conservatively treat all weekdays as working days: no holiday calendar fetch.
    start = utc_now()
    for seconds in range(0, plan['wall_seconds'] + plan['timeout_s'] + 1, 60):
        instant = start + timedelta(seconds=seconds)
        if instant.weekday() < 5 and (1 <= instant.hour < 4 or 6 <= instant.hour < 10):
            raise ValueError('verified off-peak window must cover the execution window plus timeout')


class FailureCaptureProvider(pilot.PilotChatProvider):
    """Observe failures around the frozen transport; never serialize exception text."""

    def safety_keys(self):
        return (self._key,)

    def reply(self, task_id, prompt):
        self.transport_observation = None
        self.partial_body = False
        self.retention_rejected = False
        original_open = providers.urllib.request.urlopen

        def retain(raw, partial):
            if not isinstance(raw, bytes):
                return
            # Scan available bytes before cutting: do not retain a prefix of a
            # credential split at the limit. The frozen runner rejects unsafe raw.
            self.retention_rejected = not failure_bytes_safe(raw, self.safety_keys())
            self.raw = None if self.retention_rejected else raw[:FAILURE_CAPTURE_LIMIT]
            self.partial_body = partial
            self.transport_observation.update(
                available_bytes=len(raw), retained_bytes=len(self.raw or b''),
                retention_truncated=len(raw) > FAILURE_CAPTURE_LIMIT)

        def observe(exc, stage):
            kind = next((name for cls, name in (
                (urllib.error.HTTPError, 'HTTPError'), (IncompleteRead, 'IncompleteRead'),
                (TimeoutError, 'TimeoutError'), (ConnectionResetError, 'ConnectionResetError'),
                (urllib.error.URLError, 'URLError'), (OSError, 'OSError'))
                         if isinstance(exc, cls)), 'OTHER_EXCEPTION')
            self.transport_observation = dict(exception_type=kind, stage=stage)
            if isinstance(exc, IncompleteRead) and type(exc.expected) is int:
                self.transport_observation['expected_remaining_bytes'] = exc.expected
            retain(getattr(exc, 'partial', None), True)

        def observed_open(request, timeout):
            try:
                response = original_open(request, timeout=timeout)
            except Exception as exc:
                observe(exc, 'http_dispatch')
                if isinstance(exc, urllib.error.HTTPError):
                    try:
                        margin = max((len(k.encode()) for k in self.safety_keys() if k), default=0)
                        raw = exc.read(FAILURE_CAPTURE_LIMIT + margin + 1)
                        retain(raw, len(raw) > FAILURE_CAPTURE_LIMIT)
                    except Exception as body_exc:
                        observe(body_exc, 'http_error_body_read')
                raise

            owner = self

            class ObservedResponse:
                status = response.status

                def __enter__(self):
                    try:
                        response.__enter__()
                    except Exception as exc:
                        observe(exc, 'response_context_enter')
                        raise
                    return self

                def __exit__(self, *args):
                    try:
                        return response.__exit__(*args)
                    except Exception as exc:
                        observe(exc, 'response_context_exit')
                        raise

                def read(self):
                    try:
                        raw = response.read()
                        if not failure_bytes_safe(raw, owner.safety_keys()):
                            owner.retention_rejected = True
                        return raw
                    except Exception as exc:
                        observe(exc, 'response_body_read')
                        raise

            return ObservedResponse()

        with patch.object(providers.urllib.request, 'urlopen', observed_open):
            reply = super().reply(task_id, prompt)
        if not reply.ok and self.transport_observation is None:
            self.transport_observation = dict(
                exception_type=reply.failure_type, stage='response_parse_or_validation')
        return reply


@contextmanager
def bindings():
    """Append observations to the existing attempt event, using the same writer."""
    active = {}

    def safe_output(raw, keys=()):
        if any(getattr(p, 'retention_rejected', False) and raw is p.raw for p in active.values()):
            return False
        return ORIGINAL_OUTPUT_SAFE(raw, keys)

    class Provider(FailureCaptureProvider):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            active[self.provider_id] = self

        def safety_keys(self):
            return tuple(p._key for p in active.values())

    class ObservedTrace(TraceStore):
        def append(self, event_id, kind, payload):
            if kind == 'PILOT_STARTED':
                payload.update(contract_version=CONTRACT_VERSION,
                               evaluator_version='0.2.0', transport='PYTHON_CHAT_PROVIDER_URLLIB')
            elif kind == 'PILOT_ATTEMPT':
                provider = active[payload['provider_id']]
                payload['transport_error'] = provider.transport_observation
                payload['raw_partial'] = provider.partial_body
            return super().append(event_id, kind, payload)

    with ExitStack() as stack:
        for name, value in dict(FREEZE=FREEZE, __file__=str(ENTRY), prompts=prompts,
                                PilotChatProvider=Provider, TraceStore=ObservedTrace,
                                output_safe=safe_output).items():
            stack.enter_context(patch.object(pilot, name, value))
        yield


def validate():
    with bindings():
        plan = pilot.validate_freeze()
    if pilot.load(FREEZE.with_name('prompts.json')) != {
            'system': providers.SYSTEM_PROMPT, 'user': prompts(plan)}:
        raise ValueError('clarified prompt artifact changed')
    return plan


def run(run_id, authorization, output_root=None):
    plan = validate()
    with bindings():
        pilot.check_authorization(plan, authorization)
        if (run_id != plan['run_id'] or authorization.get('run_id') != run_id
                or authorization.get('total_money_cap_cny') != plan['total_money_cap_cny']
                or sum(map(Decimal, plan['money_caps_cny'].values())) > Decimal(plan['total_money_cap_cny'])):
            raise ValueError('new batch requires exact run ID and total monetary cap')
        require_offpeak_room(plan)
        return pilot.run(run_id, authorization, output_root)


def replay(root):
    """Read-only verification, including partial/error bodies that are not answers."""
    plan = validate()
    root = Path(root)
    result = pilot.load(root / 'result.json')
    with sqlite3.connect((root / 'trace.sqlite').resolve().as_uri() + '?mode=ro', uri=True) as conn:
        events = _read(conn)
    verify_events(events, Anchor(len(events), result['trace_anchor']))
    if (result['freeze_sha256'] != pilot.digest(FREEZE.read_bytes())
            or result['entry_sha256'] != pilot.digest(ENTRY.read_bytes())):
        raise ValueError('run binding changed')
    records = [e['payload'] for e in events if e['kind'] == 'PILOT_ATTEMPT']
    if records != result['records'] or pilot.load(root / 'prompts.json') != {
            'system': providers.SYSTEM_PROMPT, 'user': prompts(plan)}:
        raise ValueError('record/trace or prompt mismatch')
    for index, record in enumerate(records, 1):
        if pilot.load(root / f'attempt_{index:02d}.json') != record:
            raise ValueError('attempt file mismatch')
        if record['raw_ref']:
            if record['raw_ref'] != f'raw_{index:02d}.json':
                raise ValueError('unexpected raw reference')
            raw = (root / record['raw_ref']).read_bytes()
            if not pilot.output_safe(raw) or pilot.digest(raw) != record['raw_sha256']:
                raise ValueError('unsafe or changed raw output')
            if record['transport_error'] and (record['transport_ok'] or record['response_text'] is not None):
                raise ValueError('failed transport body admitted as an answer')
            if not record['transport_error']:
                try:
                    envelope = json.loads(raw)
                    content = ((envelope.get('choices') or [{}])[0].get('message') or {}).get('content')
                    content = content if isinstance(content, str) and content.strip() else None
                except (ValueError, UnicodeError, AttributeError, TypeError):
                    content = None
                if content != record['response_text']:
                    raise ValueError('response/envelope mismatch')
        score, diagnostics = pilot.score_record(record['task_id'], record['response_text'],
                                               record['provider_failure'])
        if score != record['score'] or diagnostics != record['diagnostics']:
            raise ValueError('frozen score or diagnostics drift')
    return {'status': 'OFFLINE_REPLAY_VERIFIED', 'attempts': len(records), 'real_calls': 0}


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
            parser.error('--run-id required')
        result = run(args.run_id, pilot.load(args.authorization))
    else:
        plan = validate()
        result = dict(status='OFFLINE_PREPARED_REAL_CALLS_NOT_AUTHORIZED', real_calls=0,
                      freeze_sha256=pilot.digest(FREEZE.read_bytes()),
                      entry_sha256=pilot.digest(ENTRY.read_bytes()), run_id=plan['run_id'])
    print(json.dumps({k: result[k] for k in ('status', 'calls', 'stop') if k in result}
                     if 'records' in result else result, indent=2))


if __name__ == '__main__':
    main()
