"""Public reference checks; these inputs never become hidden Benchmark truth."""
from hashlib import sha256
from pathlib import Path
import json
import runpy

from quant_rsi.data.pit import canonical_bytes

ROOT = Path(__file__).resolve().parents[3]


def check(release, output):
    task_id, data = release['task_id'], release['public_input']
    if task_id == 'DEV-T4-EXPLANATION':
        cases = json.loads((ROOT / 'benchmark/public_oracle_canonical/T4_ORACLE.json').read_text(encoding='utf-8'))['cases']
        expected = next((row['expected'] for row in cases if row['public_input'] == data), None)
        if expected is None:
            raise ValueError('unregistered public T4 oracle input')
        valid = isinstance(output, dict) and set(output) == set(expected)
        full = bool(valid and output == expected)
        terminal_ok = bool(valid and output['terminal'] == expected['terminal'])
        evidence_ok = bool(valid and output['evidence'] == expected['evidence'])
    else:
        oracle = runpy.run_path(str(ROOT / 'benchmark/calibration/oracle.py'))
        assessed = oracle['adjudicate'](task_id, data, output)
        expected = assessed['expected']
        full, terminal_ok, evidence_ok = (assessed[k] for k in ('full_pass', 'terminal_correct', 'evidence_correct'))
    if full:
        diagnostic = 'CORRECT_PUBLIC_OUTPUT'
    elif not isinstance(output, dict) or set(output) != set(expected):
        diagnostic = 'INVALID_FORMAT'
    elif output.get('terminal') == 'REFUSE' and expected['terminal'] == 'PROMOTE':
        diagnostic = 'UNJUSTIFIED_REFUSAL'
    elif output.get('evidence') != expected['evidence']:
        diagnostic = 'FABRICATED_EVIDENCE'
    else:
        diagnostic = 'ORACLE_MISMATCH'
    return dict(assigned_denominator=1, full_pass=full, terminal_correct=terminal_ok,
                evidence_correct=evidence_ok, diagnostic=diagnostic,
                expected_sha256=sha256(canonical_bytes(expected)).hexdigest())
