"""Read-only replay of the supported frozen synthetic daily operation.

This does not install or execute arbitrary archived code. Unsupported local
code/runtime/dependency bindings block instead of silently using today's code.
"""
from hashlib import sha256
import importlib.metadata
import json
from pathlib import Path
import platform
import sys

from quant_rsi.contracts.condition import AgentBenchmarkRun, BenchmarkCondition
from quant_rsi.contracts.data import DataSpec, SnapshotManifest
from quant_rsi.contracts.research import Candidate, Evidence, _id
from quant_rsi.data.pit import PITView, canonical_bytes
from quant_rsi.env.daily import simulate

TOOL_VERSIONS = {'pit':'B1-v1','daily':'B1-v1','replay':'B1-v1'}


def dependency_lock():
    return {'python':platform.python_version(), 'implementation':platform.python_implementation(),
            'PyYAML':importlib.metadata.version('PyYAML')}


def installed_code_bundle():
    root=Path(__file__).resolve().parents[3]
    return {p.relative_to(root).as_posix():p.read_bytes().hex() for p in sorted((root/'src/quant_rsi').rglob('*.py'))}


def replay(manifest, *, expected_manifest_digest, replay_id, trace_store, resolve_artifact):
    """Return assurance for a new replay identity; never mutate source artifacts.

    environment-input.json declares operation/randomness/seed and freezes the
    simulator input. All contract objects resolve through existing trace/refs.
    Only exact canonical JSON comparison is supported in B1.
    """
    _id(replay_id,'replay_id')
    result={'replay_id':replay_id,'manifest_digest':manifest.manifest_digest,
            'assurance':'REPLAY_BLOCKED','formal_G2':'NOT_EVALUATED','reason':'BINDING_OR_INPUT_ERROR'}
    before=None
    try:
        if manifest.manifest_digest!=expected_manifest_digest:
            raise ValueError('manifest digest mismatch')
        before=trace_store.read()
        by_id={e['event_id']:e for e in before}
        condition=BenchmarkCondition.from_dict(by_id[manifest.condition_ref]['payload'])
        run=AgentBenchmarkRun.from_dict(by_id['run:'+manifest.benchmark_run_id]['payload'])
        def contract(ref,cls):return cls.from_dict(json.loads(resolve_artifact(ref)))
        data=contract(manifest.data_spec_ref,DataSpec)
        snapshot=contract(manifest.snapshot_ref,SnapshotManifest)
        candidates=[contract(ref,Candidate) for ref in manifest.candidate_hashes]
        evidence=[contract(ref,Evidence) for ref in manifest.evidence_hashes]
        manifest.verify_bindings(trace_store=trace_store,condition=condition,run=run,data_spec=data,snapshot=snapshot,
            candidates=candidates,evidence=evidence,resolve_artifact=resolve_artifact)
        if 'environment-input.json' not in manifest.input_artifacts:
            raise ValueError('frozen operation missing')
        operation=json.loads(resolve_artifact('environment-input.json'))
        if (operation['operation']!='synthetic-daily-v1' or operation['comparison']!='exact'
                or operation['randomness']!=manifest.randomness or operation['seed']!=manifest.seed):
            raise ValueError('operation/randomness binding mismatch')
        if manifest.randomness!='fixed_seed_deterministic':
            result.update(assurance='PROVENANCE_VERIFIED_NONDETERMINISTIC',reason='OUTPUT_REPRODUCTION_NOT_CLAIMED')
        else:
            if manifest.runtime_identity!=sys.version or dict(manifest.tool_versions)!=TOOL_VERSIONS:
                raise ValueError('runtime/tool binding mismatch')
            if json.loads(resolve_artifact(manifest.dependency_ref))!=dependency_lock():
                raise ValueError('dependency lock unavailable in current runtime')
            if json.loads(resolve_artifact(manifest.code_ref))!=installed_code_bundle():
                raise ValueError('frozen code is not the installed implementation')
            if len(candidates)!=1 or candidates[0].kind!='STRATEGY':
                raise ValueError('unsupported output contract')
            view=PITView(condition.task,data,snapshot,resolve_artifact)
            output=canonical_bytes(simulate(condition.task,view,operation['environment']))
            expected=resolve_artifact(candidates[0].artifact_ref)
            matches=output==expected
            result.update(assurance='DETERMINISTIC_REPRODUCED' if matches else 'REPLAY_FAILED',
                          reason='EXACT_OUTPUT_MATCH' if matches else 'OUTPUT_MISMATCH',
                          replay_output_hash=sha256(output).hexdigest(),expected_output_hash=sha256(expected).hexdigest())
    except (ValueError,KeyError,TypeError,OSError,OverflowError):
        pass
    if before is not None and trace_store.read()!=before:
        result.update(assurance='REPLAY_BLOCKED',reason='SOURCE_TRACE_CHANGED_DURING_REPLAY')
    return result
