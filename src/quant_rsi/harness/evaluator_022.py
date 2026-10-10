"""Versioned evaluator 0.2.2-period-tolerant, and a unified offline re-evaluation.

PURPOSE
-------
Pilot 002 exposed punctuation sensitivity in the frozen evaluator 0.2.0. Its reason
clause check is exact string equality against the published explanation
sentences (`capability_oracle.py:559-567`), and the frozen contract publishes
those sentences WITH a trailing period. Both models wrote the same sentence
without it. This version changes that policy; it does not establish that an
answer satisfied the original literal contract.

This module does NOT modify the frozen evaluator. It builds a *new version* that
specifies tolerant semantics, and it re-scores already-captured responses
offline. No network call, no credential read, and no original score is altered:
`score_original` and `score_0_2_2` are reported side by side.

TOLERANCE RULE (deliberately narrow)
------------------------------------
A clause that fails exact matching is accepted as a listed explanation only when
it differs from exactly one listed sentence by exactly one trailing '.'.
Nothing else is tolerated: no case folding, no whitespace collapsing, no prefix
matching, no fuzzy distance. The reason is that any wider tolerance would start
guessing at model intent, which this evaluator exists to avoid.

Everything else -- evidence aliases, fact values, negation, sources, verdict
acceptance -- is delegated unchanged to the frozen 0.2.0 implementation.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from hashlib import sha256
from pathlib import Path

from quant_rsi.harness import capability_oracle as oracle
from quant_rsi.harness.comparison import ROOT
from quant_rsi.ledger.store import Anchor, _read, verify_events

EVALUATOR_VERSION = '0.2.2-period-tolerant'
FROZEN_EVALUATOR_VERSION = '0.2.0'
FROZEN_ORACLE_SHA256 = 'ac42a75593e7c3535831c78ada304ffaddf251eb846c17414a940093cd7e4297'
FROZEN_FIXTURE_SHA256 = '655819304aea4036c153ac2489a99cef8c06b062165a206d368a8bfb31a00a27'
BOUND_REPORT = ROOT / 'benchmark/capability_public/pilot_v02_clarified/REEVAL_0_2_2_BOUND.json'

PILOT_002_RUN = (ROOT / 'benchmark/capability_public/runs/compatibility_pilot'
                 / 'TRACK_A_V02_CLARIFIED_COMPATIBILITY_PILOT_002')
PILOT_001_RUN = (ROOT / 'benchmark/capability_public/runs/compatibility_pilot'
                 / 'TRACK_A_V02_DSH_COMPATIBILITY_PILOT_001')


def _period_variants(explanations):
    """Accept omission of one final period with exactly one published match."""
    variants = set(explanations)
    for sentence in explanations:
        if (sentence.endswith('.') and not sentence.endswith('..')
                and explanations.count(sentence) == 1):
            variants.add(sentence[:-1])
    return variants


def tolerant_contract(contract):
    """A copy of the task contract whose listed sentences tolerate a final period."""
    patched = dict(contract)
    original = contract['reason_explanations']
    patched['reason_explanations'] = sorted(_period_variants(original))
    patched['_period_tolerance_applied'] = True
    patched['_original_reason_explanations'] = list(original)
    return patched


def frozen_contract(task_id):
    """The untouched 0.2.0 contract for one task, read from the frozen fixture."""
    task = oracle.suite_fixtures('0.2')['tasks'][task_id]
    return {'task': task, 'contract': task['input_contract']}


def verify_bindings():
    """Fail before scoring or writing if either frozen scoring input changed."""
    bindings = {}
    for label, path, expected in (
            ('frozen_evaluator', Path(oracle.__file__), FROZEN_ORACLE_SHA256),
            ('fixture', oracle.V02_PATH, FROZEN_FIXTURE_SHA256)):
        actual = sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError('frozen binding changed: ' + label)
        bindings[label] = {'path': str(path.relative_to(ROOT)), 'sha256': actual}
    bindings['new_evaluator'] = {
        'path': str(Path(__file__).relative_to(ROOT)),
        'version': EVALUATOR_VERSION,
        'sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    return bindings


def adjudicate_tolerant(task_id, response_bytes, *, failure_type=None):
    """Frozen 0.2.0 adjudication run against the tolerant contract.

    `capability_oracle.suite_fixtures` re-parses the fixture file on every call
    (there is no cache), so mutating a previously loaded dict has no effect --
    that was a real bug in an earlier version of this module, caught because the
    re-score reported zero changed rows. The only seam that actually reaches the
    evaluator is `load_fixtures`, so that is what gets substituted.
    """
    # Offline serial entry only: this scoped patch must not overlap live scoring.
    verify_bindings()
    from unittest.mock import patch

    original_load = oracle.load_fixtures
    target = str(oracle.V02_PATH)

    def tolerant_load(path=None):
        data = original_load(path)
        if path is None or str(path) != target:
            return data
        for tid, task in data['tasks'].items():
            task['input_contract'] = tolerant_contract(task['input_contract'])
        return data

    if not any(s.endswith('.') for s in
               frozen_contract(task_id)['contract']['reason_explanations']):
        # Nothing to tolerate for this task; delegate untouched.
        return oracle.adjudicate_v02(task_id, response_bytes, failure_type=failure_type)
    with patch.object(oracle, 'load_fixtures', tolerant_load):
        return oracle.adjudicate_v02(task_id, response_bytes, failure_type=failure_type)


def period_tolerant_clauses(task_id, response_text):
    """Which clauses were accepted ONLY because of the trailing-period tolerance.

    Reported so the tolerance is visible per record instead of silently absorbed.
    """
    if not response_text:
        return []
    try:
        text = response_text.strip()
        if text.startswith('```'):
            import re
            fenced = re.fullmatch(r'```(?:json)?[ \t]*\r?\n([\s\S]*?)\r?\n```', text)
            if not fenced:
                return []
            text = fenced[1]
        reason = json.loads(text).get('reason')
    except (ValueError, UnicodeDecodeError, AttributeError):
        return []
    if not isinstance(reason, str):
        return []
    published = set(frozen_contract(task_id)['contract']['reason_explanations'])
    rescued = []
    for clause in reason.split(';'):
        clause = clause.strip()
        if clause in published or not clause:
            continue
        if clause in _period_variants(list(published)):
            rescued.append(clause)
    return rescued


def rescore_record(record):
    """Re-score one captured record both ways. Pure function over stored bytes."""
    verify_bindings()
    task_id = record['task_id']
    text = record.get('response_text')
    raw = text.encode('utf-8') if text is not None else None
    failure = record.get('provider_failure')
    original = oracle.adjudicate_v02(task_id, raw, failure_type=failure).to_dict()
    if original != record['score']:
        raise ValueError('stored original score differs: ' + task_id)
    tolerant = adjudicate_tolerant(task_id, raw, failure_type=failure).to_dict()
    return {
        'provider_id': record['provider_id'],
        'task_id': task_id,
        'score_original': original,
        'score_0_2_2': tolerant,
        'period_rescued_clauses': period_tolerant_clauses(task_id, text),
        'changed': original != tolerant,
    }


def load_bound_run(run_root):
    """Reuse the original trace verifier; read evidence without modifying it."""
    verify_bindings()
    root = Path(run_root)
    result = json.loads((root / 'result.json').read_bytes())
    # Only the two captured pilot formats are supported, not arbitrary new runs.
    for directory, entry in (
            ('pilot_v02_clarified', 'compatibility_pilot_clarified.py'),
            ('pilot_v02_dsh', 'compatibility_pilot_dsh.py')):
        freeze = ROOT / 'benchmark/capability_public' / directory / 'freeze.json'
        if sha256(freeze.read_bytes()).hexdigest() == result['freeze_sha256']:
            break
    else:
        raise ValueError('unknown or changed pilot freeze')
    entry_path = ROOT / 'src/quant_rsi/harness' / entry
    if sha256(entry_path.read_bytes()).hexdigest() != result['entry_sha256']:
        raise ValueError('original pilot entry changed')
    plan = json.loads(freeze.read_bytes())
    prompt = json.loads((root / 'prompts.json').read_bytes())
    if (sha256(prompt['system'].encode()).hexdigest() != plan['system_prompt_sha256']
            or {tid: sha256(text.encode()).hexdigest() for tid, text in prompt['user'].items()}
            != plan['prompt_hashes']):
        raise ValueError('stored prompt differs from frozen prompt')
    with sqlite3.connect((root / 'trace.sqlite').resolve().as_uri() + '?mode=ro', uri=True) as conn:
        events = _read(conn)
    verify_events(events, Anchor(len(events), result['trace_anchor']))
    records = [event['payload'] for event in events if event['kind'] == 'PILOT_ATTEMPT']
    if records != result['records']:
        raise ValueError('record/trace mismatch')
    files = [root / name for name in ('result.json', 'prompts.json', 'trace.sqlite')]
    evidence = []
    for index, record in enumerate(records, 1):
        attempt = root / f'attempt_{index:02d}.json'
        if json.loads(attempt.read_bytes()) != record:
            raise ValueError('attempt file mismatch')
        files.append(attempt)
        text = record['response_text']
        response_hash = sha256(text.encode()).hexdigest() if text is not None else None
        if (response_hash != record['response_sha256']
                or record['prompt_sha256'] != plan['prompt_hashes'][record['task_id']]):
            raise ValueError('response or prompt hash mismatch')
        if record['raw_ref']:
            if record['raw_ref'] != f'raw_{index:02d}.json':
                raise ValueError('unexpected raw reference')
            raw = root / record['raw_ref']
            raw_bytes = raw.read_bytes()
            if sha256(raw_bytes).hexdigest() != record['raw_sha256']:
                raise ValueError('raw response hash mismatch')
            files.append(raw)
            # Error/partial bodies are evidence, never model answers.
            if record.get('transport_error'):
                if text is not None or record['transport_ok']:
                    raise ValueError('failed transport admitted as an answer')
            else:
                try:
                    envelope = json.loads(raw_bytes)
                    content = ((envelope.get('choices') or [{}])[0].get('message') or {}).get('content')
                    content = content if isinstance(content, str) and content.strip() else None
                except (ValueError, UnicodeError, AttributeError, TypeError):
                    content = None
                if record['provider_failure'] in ('BUSINESS_ERROR', 'PROVIDER_RESPONSE_INVALID'):
                    content = None
                if content != text:
                    raise ValueError('response/envelope mismatch')
        elif text is not None:
            raise ValueError('answer lacks original response evidence')
        evidence.append({key: record[key] for key in (
            'provider_id', 'task_id', 'prompt_sha256', 'response_sha256',
            'raw_ref', 'raw_sha256')})
    provenance = {
        'freeze': {'path': str(freeze.relative_to(ROOT)), 'sha256': result['freeze_sha256']},
        'entry': {'path': str(entry_path.relative_to(ROOT)), 'sha256': result['entry_sha256']},
        'trace_anchor': result['trace_anchor'],
        'files_sha256': {file.name: sha256(file.read_bytes()).hexdigest() for file in files},
        'records': evidence,
        'admission': 'NONCOMPLIANT_CONTROLLER_BUDGET_ENGINEERING_EVIDENCE_ONLY'
                     if directory == 'pilot_v02_clarified' else 'PARTIAL_ENGINEERING_EVIDENCE_ONLY',
    }
    return records, provenance


def load_records(run_root):
    return load_bound_run(run_root)[0]


def summarise(rows, label):
    assigned = len(rows)
    passed = sum(1 for r in rows if r['score_0_2_2']['full_pass'])
    passed_before = sum(1 for r in rows if r['score_original']['full_pass'])
    return {
        'batch': label,
        'records': assigned,
        'full_pass_original': passed_before,
        'full_pass_0_2_2': passed,
        'newly_passing': passed - passed_before,
        'verdict_correct_original': sum(1 for r in rows if r['score_original']['verdict_ok']),
        'verdict_correct_0_2_2': sum(1 for r in rows if r['score_0_2_2']['verdict_ok']),
        'reason_unsupported_original': sum(
            'reason:UNSUPPORTED_CLAUSE' in r['score_original']['exact_mismatches'] for r in rows),
        'reason_unsupported_0_2_2': sum(
            'reason:UNSUPPORTED_CLAUSE' in r['score_0_2_2']['exact_mismatches'] for r in rows),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, action='append', default=None,
                        help='run directory to re-score; repeatable')
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args(argv)

    try:
        bindings = verify_bindings()
    except (ValueError, OSError) as exc:
        print('REVALUATION_REFUSED:', str(exc), file=sys.stderr)
        return 1

    runs = args.run or [PILOT_002_RUN, PILOT_001_RUN]
    report = {
        'evaluator_version_new': EVALUATOR_VERSION,
        'evaluator_version_frozen': FROZEN_EVALUATOR_VERSION,
        'frozen_evaluator_sha256': bindings['frozen_evaluator']['sha256'],
        'frozen_evaluator_unchanged': True,
        'bindings': bindings,
        'status': 'OFFLINE_REEVALUATION_CANDIDATE_NOT_REAL_RUN_FREEZE',
        'confirmed_legal_answer_misjudgments': None,
        'network_calls': 0,
        'real_credentials_read': 0,
        'tolerance_rule': 'a listed sentence is also accepted without exactly one trailing period',
        'batches': [],
    }

    try:
        for run_root in runs:
            run_root = Path(run_root)
            records, provenance = load_bound_run(run_root)
            rows = [rescore_record(r) for r in records]
            report['batches'].append({
                'run_dir': str(run_root.resolve()),
                'summary': summarise(rows, run_root.name),
                'provenance': provenance,
                'rows': rows,
            })
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as exc:
        print('REVALUATION_REFUSED:', str(exc), file=sys.stderr)
        return 1

    if args.write:
        out = BOUND_REPORT
        data = json.dumps(report, sort_keys=True, indent=2).encode()
        if out.exists():
            if out.read_bytes() != data:
                print('REVALUATION_REFUSED: existing bound report differs; preserve it', file=sys.stderr)
                return 1
        else:
            with out.open('xb') as handle:
                handle.write(data)
        report['written_to'] = str(out)

    for batch in report['batches']:
        s = batch['summary']
        print(f"\n=== {s['batch']} ===")
        for key in ('records', 'full_pass_original', 'full_pass_0_2_2', 'newly_passing',
                    'verdict_correct_original', 'verdict_correct_0_2_2',
                    'reason_unsupported_original', 'reason_unsupported_0_2_2'):
            print(f'  {key:32} {s[key]}')
        for row in batch['rows']:
            if row['changed']:
                print(f"    CHANGED {row['provider_id']:9} {row['task_id']:26} "
                      f"pass {row['score_original']['full_pass']} -> {row['score_0_2_2']['full_pass']}"
                      f"  rescued={row['period_rescued_clauses']}")
    print('\nfrozen evaluator unchanged:', report['frozen_evaluator_unchanged'])
    if report.get('written_to'):
        print('written:', report['written_to'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
