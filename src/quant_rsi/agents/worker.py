"""Frozen synthetic adapter; trusted supervisor protocol, not OS authentication."""
from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from types import MappingProxyType

from quant_rsi.contracts.condition import RESOURCE_DIMENSIONS
from quant_rsi.contracts.research import _Contract, _hash, _id, _text
from quant_rsi.ledger.budget import SearchBudget


RANDOMNESS = ('fixed_seed_deterministic', 'externally_nondeterministic',
              'provider_randomness_unknown')
STATUSES = dict(success='SUCCEEDED', timeout='TIMEOUT', failure='FAILED',
                malformed='MALFORMED', unknown_usage='UNKNOWN_USAGE')


def _usage(value):
    if value is None:
        return None
    if (not isinstance(value, Mapping) or set(value) != set(RESOURCE_DIMENSIONS)
            or any(type(v) is not int or v < 0 for v in value.values())):
        raise ValueError('synthetic usage requires every resource dimension as nonnegative integers')
    return MappingProxyType(dict(value))


@dataclass(frozen=True)
class WorkerRequest(_Contract):
    run_id: str
    actor_id: str
    context_id: str
    provider: str
    model_id: str
    model_version: str | None
    prompt_hash: str
    policy_hash: str
    tools: tuple[str, ...]
    input_hashes: Mapping[str, str]

    def __post_init__(self):
        for name in ('run_id', 'actor_id', 'context_id'):
            _id(getattr(self, name), name)
        for name in ('provider', 'model_id'):
            _text(getattr(self, name), name)
        if self.model_version is not None:
            _text(self.model_version, 'model_version')
        _hash(self.prompt_hash)
        _hash(self.policy_hash)
        if not isinstance(self.tools, (tuple, list)):
            raise ValueError('tools must be a sequence of frozen configuration identifiers')
        for tool in self.tools:
            _text(tool, 'tool')
        if len(set(self.tools)) != len(self.tools):
            raise ValueError('duplicate tools')
        object.__setattr__(self, 'tools', tuple(self.tools))
        if not isinstance(self.input_hashes, Mapping) or not self.input_hashes:
            raise ValueError('input hashes required')
        for name, digest in self.input_hashes.items():
            _text(name, 'input reference')
            _hash(digest)
        object.__setattr__(self, 'input_hashes', MappingProxyType(dict(self.input_hashes)))


@dataclass(frozen=True)
class FakeProvider(_Contract):
    response: bytes
    mode: str = 'success'
    reported_usage: Mapping[str, int] | None = None
    randomness: str = 'fixed_seed_deterministic'

    def __post_init__(self):
        if type(self.response) is not bytes:
            raise ValueError('frozen response bytes required')
        if self.mode not in STATUSES or self.randomness not in RANDOMNESS:
            raise ValueError('explicit supported mode and randomness required')
        if self.mode == 'unknown_usage' and self.reported_usage is not None:
            raise ValueError('unknown usage cannot carry known counters')
        object.__setattr__(self, 'reported_usage', _usage(self.reported_usage))

    def to_dict(self):
        return dict(response_hex=self.response.hex(), mode=self.mode,
                    reported_usage=None if self.reported_usage is None else dict(self.reported_usage),
                    randomness=self.randomness)


@dataclass(frozen=True)
class WorkerResponse(_Contract):
    status: str
    output: bytes
    randomness: str
    provider_reported_usage: Mapping[str, int] | None
    supervisor_measured_usage: None = None
    error_metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if self.status not in STATUSES.values() or type(self.output) is not bytes:
            raise ValueError('valid status and output bytes required')
        if self.randomness not in RANDOMNESS or self.supervisor_measured_usage is not None:
            raise ValueError('randomness required; no supervisor measurement exists')
        object.__setattr__(self, 'provider_reported_usage', _usage(self.provider_reported_usage))
        if not isinstance(self.error_metadata, Mapping):
            raise ValueError('error metadata must be an object')
        for key, value in self.error_metadata.items():
            _text(key, 'error key')
            _text(value, 'error value')
        if (self.status == 'SUCCEEDED') != (not self.error_metadata):
            raise ValueError('failure metadata required exactly for non-success responses')
        if self.status == 'UNKNOWN_USAGE' and self.provider_reported_usage is not None:
            raise ValueError('unknown usage cannot carry counters')
        object.__setattr__(self, 'error_metadata', MappingProxyType(dict(self.error_metadata)))

    @property
    def actual_resources(self):
        return self.provider_reported_usage

    @property
    def usage_source(self):
        return 'unknown' if self.actual_resources is None else 'provider_reported'

    @property
    def output_hash(self):
        return sha256(self.output).hexdigest()

    def to_dict(self):
        return dict(status=self.status, output_hex=self.output.hex(), output_hash=self.output_hash,
                    randomness=self.randomness, usage_source=self.usage_source,
                    provider_reported_usage=None if self.actual_resources is None else dict(self.actual_resources),
                    supervisor_measured_usage=None, error_metadata=dict(self.error_metadata))

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, Mapping):
            raise ValueError('response object required')
        data = dict(value)
        try:
            digest = data.pop('output_hash')
            source = data.pop('usage_source')
            data['output'] = bytes.fromhex(data.pop('output_hex'))
            result = cls(**data)
        except (KeyError, TypeError) as exc:
            raise ValueError('invalid response fields') from exc
        if digest != result.output_hash or source != result.usage_source:
            raise ValueError('response provenance mismatch')
        return result


def invoke(request, provider, *, budget, attempt_id):
    """Consume an existing reservation, without owning reservation or settlement.

    The exact fake bytes represent a pre-frozen environment operation interpreted
    only by the runner. The transaction serializes duplicate delivery with settle.
    """
    if type(request) is not WorkerRequest or type(provider) is not FakeProvider:
        raise ValueError('WorkerRequest and exact FakeProvider required')
    if type(budget) is not SearchBudget:
        raise ValueError('canonical SearchBudget required')
    _id(attempt_id, 'attempt_id')
    with budget.store.transaction() as tx:
        events = tx.events()
        starts = [e for e in events if e['kind'] == 'ATTEMPT_STARTED'
                  and e['payload']['attempt_id'] == attempt_id]
        if len(starts) != 1 or starts[0]['event_id'] != 'attempt:' + attempt_id:
            raise ValueError('canonical reserved ATTEMPT_STARTED required')
        start = starts[0]
        if any(e['kind'] in ('ATTEMPT_SETTLED', 'USAGE_RECONCILED')
               and e['payload']['attempt_id'] == attempt_id for e in events):
            raise ValueError('terminal attempt cannot dispatch')
        runs = [e for e in events if e['kind'] == 'RUN_REGISTERED'
                and e['payload']['benchmark_run_id'] == request.run_id]
        if len(runs) != 1:
            raise ValueError('canonical run required')
        run = runs[0]['payload']
        if (runs[0]['sequence'] >= start['sequence']
                or start['payload']['benchmark_run_id'] != request.run_id
                or (run['agent_model'], run['agent_model_version'], run['provider'], run['prompt_hash'])
                != (request.model_id, request.model_version, request.provider, request.prompt_hash)
                or start['payload']['condition_hash'] != run['condition_hash']
                or start['payload']['budget_root_run_id'] != run['budget_root_run_id']):
            raise ValueError('request/run/reservation binding mismatch')
        binding = dict(attempt_id=attempt_id, request=request.to_dict(),
                       provider_digest=provider.content_digest())
        bound = next((e for e in events if e['event_id'] == 'worker-binding:' + attempt_id), None)
        if (bound is None or bound['kind'] != 'WORKER_DISPATCH_BOUND'
                or bound['payload'] != binding or bound['sequence'] <= start['sequence']):
            raise ValueError('supervisor request metadata binding required')
        request_event = tx.append('worker-request:' + attempt_id, 'WORKER_REQUEST', binding)
        if request_event['sequence'] <= bound['sequence']:
            raise ValueError('binding must precede invocation')
        # There is no external code, clock measurement, RNG draw, or callback here.
        status = STATUSES[provider.mode]
        if status == 'SUCCEEDED' and provider.reported_usage is None:
            status = 'UNKNOWN_USAGE'
        response = WorkerResponse(status, provider.response, provider.randomness,
                                  provider.reported_usage, error_metadata={} if status == 'SUCCEEDED'
                                  else {'code': status, 'detail': 'Frozen synthetic provider outcome'})
        saved = tx.append('worker-response:' + attempt_id, 'WORKER_RESPONSE', dict(
            attempt_id=attempt_id, request_digest=request.content_digest(),
            provider_digest=provider.content_digest(), response=response.to_dict()))
        return WorkerResponse.from_dict(saved['payload']['response'])
