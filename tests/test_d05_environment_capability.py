"""Validate actual startup-failure evidence, never treat it as isolation PASS."""
import hashlib
import json
import subprocess
import os
from pathlib import Path

from quant_rsi.ledger.store import Anchor, verify_events

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / 'benchmark/d05_minimal_custodian_v01'


def read(name):
    return json.loads((PACK / name).read_text(encoding='utf-8'))


def test_actual_native_startup_failures_are_preserved_without_security_pass():
    result = read('environment_results.json')
    assert result['status'] == 'BLOCKED_ENVIRONMENT_CAPABILITY'
    assert len(result['probes']) == 3
    assert [p['exit_code_hex'] for p in result['probes']] == ['0xC0000022', '0xC0000022', '0xC0000142']
    assert all(p['raw_report']['launch']['inherited_handles'] is False for p in result['probes'])
    assert not any(p['worker_receipt_present'] for p in result['probes'])
    assert result['d05_offline_isolation_engineering'] == 'NOT_GRANTED'
    assert result['D05_FULL_SEALED_QUALIFIED'] == 'NOT_GRANTED'
    assert result['worker_to_custodian_e2e'] == 'NOT_EXECUTED'
    assert set(result['security_checks'].values()) == {'NOT_EXECUTED_WORKER_STARTUP_BLOCKED'}


def test_existing_append_only_trace_binds_blocked_evidence():
    result = read('environment_results.json')
    events = read('trace.json')
    verify_events(events, Anchor(**result['trace_anchor']))
    recorded = [e['payload'] for e in events if e['kind'] == 'D05_ENVIRONMENT_PROBE_RECORDED']
    assert len(recorded) == 3
    assert all(e['post_execution_record'] is True for e in recorded)
    assert all(e['interpreted_status'] == 'BLOCKED_ENVIRONMENT_CAPABILITY' for e in recorded)
    assert events[-1]['payload']['status'] == 'BLOCKED_ENVIRONMENT_CAPABILITY'
    for name, expected in result['source_binding'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected


def test_windows_launcher_syntax_without_worker_execution():
    executable = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    command = "$tokens=$null;$errors=$null;[System.Management.Automation.Language.Parser]::ParseFile('scripts/d05_restricted_worker.ps1',[ref]$tokens,[ref]$errors) | Out-Null;if($errors.Count){exit 1}"
    completed = subprocess.run([str(executable), '-NoProfile', '-NonInteractive', '-Command', command],
        cwd=ROOT, capture_output=True, timeout=15)
    assert completed.returncode == 0, completed.stderr.decode(errors='replace')


def test_launcher_rejects_existing_root_before_acl_change():
    executable = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    # An existing direct-child synthetic root must fail before any ACL/file mutation.
    completed = subprocess.run([str(executable), '-NoProfile', '-NonInteractive', '-File',
        'scripts/d05_restricted_worker.ps1', '-TestRoot', str(ROOT / '.d05_synthetic_probe_03')],
        cwd=ROOT, capture_output=True, timeout=15)
    assert completed.returncode != 0
    assert b'TestRoot must be new' in completed.stderr
