"""Versioned CP execution fix: retain capture at the exit/kill race.

The original pinned executor and image are unchanged. CPU below is supervisor
process CPU, never Worker aggregate usage. Container bounds remain identical.
"""
import re
import subprocess
import time
from datetime import datetime
from unittest.mock import patch

from quant_rsi.harness import cp_isolation as kernel
from quant_rsi.harness.agent_workflow import save, digest


def collect(container):
    original = kernel.docker
    def safe_docker(*args):
        if args[0] == 'kill':
            try:
                return original(*args)
            except RuntimeError as exc:
                # Only suppress the actual exit/kill race, never a permission/error failure.
                if 'is not running' not in str(exc) or kernel.inspection(container)['state']['Running']:
                    raise
                return ''
        return original(*args)
    with patch.object(kernel, 'docker', safe_docker):
        captured = kernel.collect(container)
    state = kernel.inspection(container)['state']
    duration = (datetime.fromisoformat(state['FinishedAt'].replace('Z', '+00:00')) -
                datetime.fromisoformat(state['StartedAt'].replace('Z', '+00:00'))).total_seconds()
    captured['worker_wall_seconds'] = duration
    # CLI attachment latency is not Worker lifetime. Preserve both observations.
    if captured['supervisor_stop'] == 'WALL_TIMEOUT' and duration <= kernel.POLICY['timeout_seconds'] and not state['Running']:
        captured['attach_deadline_after_worker_exit'] = True
        captured['supervisor_stop'] = None
    return captured


def execute(pack, run, store, budget, freeze, label, source, packet):
    if not re.fullmatch('[a-z0-9-]+', label):
        raise ValueError('LABEL_REQUIRED')
    path = pack / 'synthetic_work' / label
    if path.exists():
        raise ValueError('SESSION_EXISTS_APPEND_ONLY')
    path.mkdir(parents=True)
    code, public = path / 'submission.py', path / 'input.json'
    code.write_bytes(source.encode('utf-8'))
    save(public, packet)
    attempt = 'CP-ISO-' + label
    used = budget.capability_accounting(run)['usage']['attempts']
    budget.reserve(run, attempt, dict(attempts=1, candidate_trials=0, model_trials=int(used == 0),
        validation_queries=1, input_tokens=0, output_tokens=0, wall_milliseconds=60000, cpu_milliseconds=60000))
    started, cpu = time.perf_counter(), time.process_time()
    container, record = None, {}
    try:
        if len(code.read_bytes()) > kernel.POLICY['submission_bytes']:
            record = dict(status='SUBMISSION_LIMIT_EXCEEDED', container_started=False)
        else:
            cmd = kernel.command(freeze['image']['worker_content_id'], 'qrsi-' + label, code.resolve(), public.resolve())
            reply = subprocess.run(cmd, capture_output=True, timeout=30)
            if reply.returncode:
                raise RuntimeError(reply.stderr.decode('utf-8', errors='replace')[:2048])
            container = reply.stdout.decode().strip()
            if not re.fullmatch('[0-9a-f]{64}', container):
                raise ValueError('UNEXPECTED_CONTAINER_ID')
            before = kernel.inspection(container)
            kernel.check_boundary(before, freeze['image']['worker_content_id'])
            captured = collect(container)
            after = kernel.inspection(container)
            status = captured['supervisor_stop'] or ('WORKER_OOM' if after['state']['OOMKilled'] else
                'WORKER_FAILED' if after['state']['ExitCode'] else 'COMPLETED')
            record = dict(status=status, container_started=True, container_id=container, before=before, after=after, **captured)
    except BaseException as exc:
        record = dict(status='SUPERVISOR_FAILURE', error=type(exc).__name__ + ':' + str(exc)[:2048])
    finally:
        if container and re.fullmatch('[0-9a-f]{64}', container):
            try:
                kernel.docker('rm', '--force', container)
            except Exception as exc:
                record['cleanup_error'] = str(exc)[:2048]
        from hashlib import sha256
        record.update(label=label, submission_sha256=sha256(code.read_bytes()).hexdigest(),
            public_sha256=sha256(public.read_bytes()).hexdigest(), worker_cpu_milliseconds=None,
            worker_cpu_state='UNKNOWN_NOT_ZERO', real_model_calls=0,
            freeze_sha256=sha256((pack / 'freeze.json').read_bytes()).hexdigest())
        actual = dict(input_tokens=0, output_tokens=0, wall_milliseconds=int((time.perf_counter()-started)*1000),
            cpu_milliseconds=int((time.process_time()-cpu)*1000))
        record['supervisor_measured_usage'] = actual
        store.append('cp-evidence:' + label, 'CP_CONTAINER_EVIDENCE', record)
        good = record['status'] == 'COMPLETED'
        budget.settle(attempt, 'SUCCEEDED' if good else 'TIMEOUT' if record['status'] == 'WALL_TIMEOUT' else 'FAILED',
            actual, artifact_hashes={'container_evidence': digest(record)}, failure=None if good else record['status'])
    if record['status'] == 'SUPERVISOR_FAILURE' or 'cleanup_error' in record or budget.capability_accounting(run)['blocked']:
        save(pack / ('failure-' + label + '.json'), record)
        raise RuntimeError('SUPERVISOR_FAILURE_STOP_BATCH')
    return record
