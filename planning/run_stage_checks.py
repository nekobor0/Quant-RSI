"""Capture offline pytest evidence without hiding failures. Not Harness runtime code."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    'W01': ['contracts/decisions.yaml', 'tests/contracts/test_decisions.py'],
    'W02': ['src/quant_rsi/contracts/research.py', 'tests/contracts/test_research.py'],
    'W03': ['src/quant_rsi/contracts/data.py', 'tests/contracts/test_data.py'],
    'W04': ['src/quant_rsi/contracts/condition.py', 'tests/contracts/test_condition.py'],
    'W05': ['src/quant_rsi/ledger/store.py', 'tests/ledger/test_store.py'],
    'W06': ['src/quant_rsi/ledger/budget.py', 'tests/ledger/test_budget.py'],
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('label')
    parser.add_argument('work_items', nargs='+', choices=FILES)
    args = parser.parse_args()
    if not args.label.replace('_', '').isalnum():
        raise ValueError('label must be alphanumeric with underscores')
    target = ROOT / 'artifacts/stage_a'
    target.mkdir(parents=True, exist_ok=True)
    log = target / (args.label + '.log')
    if log.exists():
        raise ValueError('evidence label already used; never overwrite failed attempts')
    command = [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider']
    command += [FILES[w][1] for w in args.work_items]
    command += ['--junitxml=' + str(target / (args.label + '.xml'))]
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'), PYTHONDONTWRITEBYTECODE='1')
    env['QUANT_RSI_CAPTURE_DIR'] = str(target / (args.label + '_runtime'))
    start = datetime.now(timezone.utc).isoformat()
    completed = subprocess.run(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
    with log.open('x', encoding='utf-8') as handle:
        handle.write(completed.stdout)
    hashes = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for w in args.work_items for p in FILES[w]}
    record = {'label': args.label, 'work_items': args.work_items, 'command': command, 'started_at': start,
              'finished_at': datetime.now(timezone.utc).isoformat(), 'exit_code': completed.returncode,
              'log': log.relative_to(ROOT).as_posix(), 'junit': f'artifacts/stage_a/{args.label}.xml', 'artifact_hashes': hashes,
              'environment_overrides': {k: env[k] for k in ('PYTHONPATH', 'PYTHONDONTWRITEBYTECODE', 'QUANT_RSI_CAPTURE_DIR')}}
    with (target / 'test_attempts.jsonl').open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + '\n')
    print(completed.stdout)
    print('exit_code=' + str(completed.returncode))
    return completed.returncode


if __name__ == '__main__':
    raise SystemExit(main())
