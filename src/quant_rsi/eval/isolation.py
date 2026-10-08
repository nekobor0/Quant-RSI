"""Synthetic protocol mock ONLY. Not an OS sandbox or formal G6 evaluator."""
from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
import io
import json
from pathlib import Path
import stat

from quant_rsi.contracts.research import _id, _hash

ASSURANCE = 'SYNTHETIC_MOCK'
DEPLOYMENT_SURFACES = ('os_identity', 'filesystem_isolation', 'network_dns_metadata',
                       'credential_custody', 'log_error_timing_metadata', 'shared_cache')


class MockIsolation:
    """Trusted mock custodian owns config; client gets request() only by convention.

    Python object privacy is not a security boundary. Direct host access remains
    UNVERIFIED. No worker code is executed, credentials minted or scores released.
    The existing append-only trace is the only submission/exposure state store.
    """
    def __init__(self, store, *, condition_id, holdout_id, root, public_files, evaluator_path,
                 evaluator_hash, submission_limit, tm_review, diagnostic_mode='normal'):
        if tm_review.get('decision') != 'PASS_FOR_SYNTHETIC_MOCK' or tm_review.get('unresolved_P0_P1') != []:
            raise ValueError('TM-01 independent design review prerequisite not met')
        _id(condition_id, 'condition_id'); _id(holdout_id, 'holdout_id'); _hash(evaluator_hash)
        if type(submission_limit) is not int or submission_limit < 0:
            raise ValueError('explicit submission limit required')
        if diagnostic_mode not in ('normal', 'stdout', 'stderr', 'exception'):
            raise ValueError('unknown synthetic diagnostic mode')
        self.store, self.condition_id = store, condition_id
        self.holdout_id = holdout_id
        self.root = Path(root).resolve(strict=True)
        self.public_files = dict(public_files)
        for name,digest in self.public_files.items():
            _hash(digest); self._safe_path(name)
        self.evaluator_path = Path(evaluator_path)
        self.evaluator_hash, self.limit = evaluator_hash, submission_limit
        self.diagnostic_mode = diagnostic_mode
        config = dict(condition_id=condition_id, holdout_id=holdout_id, root=str(self.root), public_files=self.public_files,
                      evaluator_path=str(self.evaluator_path.resolve()), evaluator_hash=evaluator_hash,
                      limit=submission_limit, diagnostic_mode=diagnostic_mode, assurance=ASSURANCE)
        # Changed counters/config under the same condition cannot reset exposure.
        store.append('mock-config:'+condition_id,'MOCK_ISOLATION_CONFIG',config)
        store.append('mock-holdout:'+holdout_id,'MOCK_HOLDOUT_POLICY',dict(holdout_id=holdout_id,limit=submission_limit))

    def _safe_path(self, ref):
        if type(ref) is not str or not ref or '\\' in ref or ':' in ref:
            raise ValueError('opaque path denial')
        parts=ref.split('/')
        if any(p in ('','.','..') for p in parts): raise ValueError('opaque path denial')
        candidate=self.root
        for part in parts:
            candidate=candidate/part
            info=candidate.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400):
                raise ValueError('opaque path denial')
        if not candidate.resolve(strict=True).is_relative_to(self.root) or not candidate.is_file():
            raise ValueError('opaque path denial')
        return candidate

    @staticmethod
    def _response(allowed):
        return {'assurance':ASSURANCE,'status':'ACCEPTED' if allowed else 'BLOCKED',
                'feedback':None,'error_id':None if allowed else 'MOCK_DENIED'}

    def request(self, request_id, candidate_id, operation, payload):
        _id(request_id,'request_id');_id(candidate_id,'candidate_id')
        # Client-supplied counter, evaluator, tools, credentials or identity
        # fields cannot become trusted config. Raw values are never logged.
        event_id='mock-request:'+self.holdout_id+':'+request_id
        with self.store.transaction() as tx:
            malformed=False
            try:
                encoded=json.dumps([candidate_id,operation,payload],sort_keys=True,allow_nan=False).encode()
            except (ValueError, TypeError, OverflowError):
                malformed=True
                encoded=json.dumps([candidate_id,'INVALID_JSON_PAYLOAD']).encode()
            fingerprint=sha256(encoded).hexdigest()
            events=tx.events()
            existing=next((e for e in events if e['event_id']==event_id),None)
            if existing:
                if (existing['payload']['fingerprint']!=fingerprint
                        or existing['payload']['condition_id']!=self.condition_id
                        or existing['payload']['candidate_id']!=candidate_id):
                    tx.append('mock-compromise:'+self.holdout_id,'MOCK_COMPROMISE',{'holdout_id':self.holdout_id})
                    return self._response(False)
                return existing['payload']['response']
            prior=[e for e in events if e['kind']=='MOCK_REQUEST' and e['payload']['holdout_id']==self.holdout_id]
            blocked=any(e['kind']=='MOCK_COMPROMISE' and e['payload']['holdout_id']==self.holdout_id for e in events)
            allowed=False; compromised=malformed
            if not malformed and not blocked and len(prior)<self.limit:
                try:
                    if sha256(self.evaluator_path.read_bytes()).hexdigest()!=self.evaluator_hash:
                        raise ValueError('evaluator changed')
                    if operation=='read_public':
                        if set(payload)!={'ref'} or payload['ref'] not in self.public_files:
                            raise ValueError('unauthorized read')
                        path=self._safe_path(payload['ref'])
                        if sha256(path.read_bytes()).hexdigest()!=self.public_files[payload['ref']]:
                            raise ValueError('public input changed')
                        # Mock only acknowledges allowed access, returns no bytes/size.
                    elif operation=='submit':
                        if set(payload)!={'artifact_ref','artifact_hash'}: raise ValueError('unexpected submission fields')
                        _hash(payload['artifact_hash'])
                        if type(payload['artifact_ref']) is not str or not payload['artifact_ref']: raise ValueError('missing artifact')
                        with redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
                            if self.diagnostic_mode=='stdout': print('SYNTHETIC_PRIVATE_SEED_17')
                            if self.diagnostic_mode=='stderr':
                                import sys
                                print('SYNTHETIC_PRIVATE_PATH_SIZE',file=sys.stderr)
                            if self.diagnostic_mode=='exception': raise ValueError('SYNTHETIC_PRIVATE_SEED_17')
                    else:
                        raise ValueError('network/tools/cache/metadata/hidden access denied')
                    allowed=True
                except Exception:
                    compromised=True
            response=self._response(allowed)
            tx.append(event_id,'MOCK_REQUEST',dict(condition_id=self.condition_id,holdout_id=self.holdout_id,request_id=request_id,
                      candidate_id=candidate_id,fingerprint=fingerprint,response=response))
            if compromised:
                tx.append('mock-compromise:'+self.holdout_id,'MOCK_COMPROMISE',{'holdout_id':self.holdout_id})
            return response

    def assurance_report(self):
        compromised=any(e['kind']=='MOCK_COMPROMISE' and e['payload']['holdout_id']==self.holdout_id for e in self.store.read())
        return {'assurance':ASSURANCE,'formal_G6':'BLOCKED','results':'UNDER_REVIEW' if compromised else 'SYNTHETIC_ONLY',
                'deployment':dict.fromkeys(DEPLOYMENT_SURFACES,'UNVERIFIED / REQUIRES_DEPLOYMENT')}
