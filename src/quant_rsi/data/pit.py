"""PIT views over frozen canonical DataSpec records; synthetic conformance only."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import json
import math

from quant_rsi.contracts.data import DataSpec
from quant_rsi.contracts.research import _timestamp, _text


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def instant(value):
    return datetime.fromisoformat(_timestamp(value))


@dataclass(frozen=True)
class VisibleRecord:
    """Derived view: metadata is referenced, never separately editable."""
    data_spec: DataSpec
    entity: str
    kind: str
    value_json: str

    @property
    def value(self):
        return json.loads(self.value_json)


class PITView:
    def __init__(self, task, data_spec, snapshot, resolve_artifact):
        task.verify_data_bindings(data_spec, snapshot)
        payloads = {}
        for entry in snapshot.files:
            raw = resolve_artifact(entry.path)
            if type(raw) is not bytes or sha256(raw).hexdigest() != entry.sha256:
                raise ValueError('snapshot artifact mismatch')
            payloads[entry.sha256] = raw
        document = json.loads(payloads[data_spec.raw_artifact_hash])
        if not isinstance(document, list) or not document:
            raise ValueError('snapshot requires canonical data records')
        records, revisions, identities = [], set(), {}
        for row in document:
            if set(row) != {'data_spec', 'entity', 'kind', 'value'}:
                raise ValueError('record fields must reference canonical DataSpec metadata')
            spec = DataSpec.from_dict(row['data_spec'])
            _text(row['entity'], 'entity'); _text(row['kind'], 'kind')
            raw_payload = {k: row[k] for k in ('entity', 'kind', 'value')}
            if sha256(canonical_bytes(raw_payload)).hexdigest() != spec.raw_artifact_hash:
                raise ValueError('record DataSpec/raw binding mismatch')
            if (spec.cleaning_spec_version != data_spec.cleaning_spec_version
                    or spec.universe_version != data_spec.universe_version
                    or spec.pit_version != data_spec.pit_version):
                raise ValueError('record version mismatch')
            identity = (row['entity'], row['kind'], instant(spec.event_time))
            if spec.source_id in identities and identities[spec.source_id] != identity:
                raise ValueError('revision cannot change logical object identity')
            identities[spec.source_id] = identity
            revision = (spec.source_id, spec.source_revision)
            if revision in revisions:
                raise ValueError('duplicate revision')
            revisions.add(revision)
            records.append(VisibleRecord(spec, row['entity'], row['kind'], canonical_bytes(row['value']).decode()))
        self._records = tuple(records)
        self.snapshot_hash = snapshot.content_hash()

    def at(self, decision_at):
        """Latest available revision per object, then effective interval filtering.

        Later revisions that close an interval must not resurrect an older open
        interval. Known prospective facts may have event_time after decision_at.
        """
        at = instant(decision_at)
        latest = {}
        for record in self._records:
            spec = record.data_spec
            if instant(spec.available_at) > at:
                continue
            previous = latest.get(spec.source_id)
            if previous is None or instant(previous.data_spec.available_at) < instant(spec.available_at):
                latest[spec.source_id] = record
            elif instant(previous.data_spec.available_at) == instant(spec.available_at):
                raise ValueError('ambiguous revision availability tie')
        visible = [r for r in latest.values() if instant(r.data_spec.effective_from) <= at
                   and (r.data_spec.effective_to is None or at < instant(r.data_spec.effective_to))]
        return tuple(sorted(visible, key=lambda r: r.data_spec.source_id))

    def state(self, decision_at, entity, kind):
        rows = [r for r in self.at(decision_at) if r.entity == entity and r.kind == kind]
        if len(rows) != 1:
            raise ValueError('missing or ambiguous PIT state')
        return rows[0].value

    def universe(self, decision_at):
        """Includes historically listed securities even if absent/delisted today."""
        entities = {r.entity for r in self.at(decision_at) if r.kind == 'listing'}
        return tuple(sorted(e for e in entities if self.state(decision_at, e, 'listing') is True))


@dataclass(frozen=True)
class CleaningSpec:
    version: str
    transform: str
    winsor_lower: float
    winsor_upper: float
    imputation: str = 'mean'
    scale: str = 'standard'

    def __post_init__(self):
        _text(self.version, 'cleaning version')
        if self.transform not in ('identity', 'signed_log1p') or self.imputation != 'mean' or self.scale != 'standard':
            raise ValueError('unsupported explicitly frozen cleaning operation')
        if not (type(self.winsor_lower) in (int, float) and type(self.winsor_upper) in (int, float)
                and 0 <= self.winsor_lower <= self.winsor_upper <= 1):
            raise ValueError('explicit winsor quantiles required')


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('finite numeric feature required')
    return float(value)


def _transform(value, spec):
    return value if spec.transform == 'identity' else math.copysign(math.log1p(abs(value)), value)


@dataclass(frozen=True)
class FrozenCleaner:
    spec: CleaningSpec
    fill: float
    low: float
    high: float
    center: float
    scale: float
    training_ids: tuple[str, ...]

    def apply(self, values):
        return tuple((min(self.high, max(self.low, _transform(self.fill if v is None else _number(v), self.spec)))
                      - self.center) / self.scale for v in values)


def fit_cleaner(view, *, decision_at, task, spec, training_from, training_to, feature_kind):
    """Fit only the frozen training interval; availability is also PIT filtered."""
    if spec.version != task.cleaning_spec_version:
        raise ValueError('cleaning version must match frozen Task')
    start, end, decision = instant(training_from), instant(training_to), instant(decision_at)
    if not start < end <= decision:
        raise ValueError('training window must end by decision_at')
    rows = [r for r in view.at(training_to) if r.kind == feature_kind and start <= instant(r.data_spec.event_time) < end]
    values = [_number(r.value) for r in rows if r.value is not None]
    if not values:
        raise ValueError('no observed training values')
    fill = sum(values) / len(values)
    transformed = sorted(_transform(fill if r.value is None else _number(r.value), spec) for r in rows)
    def quantile(q):
        p = q * (len(transformed)-1); i = int(p); j = min(i+1, len(transformed)-1)
        return transformed[i] + (p-i)*(transformed[j]-transformed[i])
    low, high = quantile(spec.winsor_lower), quantile(spec.winsor_upper)
    clipped = [min(high, max(low, v)) for v in transformed]
    center = sum(clipped)/len(clipped)
    scale = math.sqrt(sum((v-center)**2 for v in clipped)/len(clipped)) or 1.0
    return FrozenCleaner(spec, fill, low, high, center, scale, tuple(r.data_spec.source_id for r in rows))


def purged_training_ids(labels, validation_ids, *, task, split_version, label_horizon_seconds,
                        information_lag_seconds, embargo_seconds):
    """Parameterized interval mechanics; no global statistical calibration.

    labels maps IDs to decision timestamps. Intervals are half-open from the
    information lookback to label maturity; embargo extends validation's end.
    """
    if split_version != task.split_version:
        raise ValueError('split version differs from Task')
    parameters = (label_horizon_seconds, information_lag_seconds, embargo_seconds)
    if any(type(v) is not int or v < 0 for v in parameters) or label_horizon_seconds == 0:
        raise ValueError('explicit positive label horizon and nonnegative lag/embargo required')
    if not validation_ids or not set(validation_ids) <= labels.keys():
        raise ValueError('validation label IDs required')
    def interval(key, embargo=0):
        t = instant(labels[key])
        return t-timedelta(seconds=information_lag_seconds), t+timedelta(seconds=label_horizon_seconds+embargo)
    excluded = [interval(k, embargo_seconds) for k in validation_ids]
    return tuple(sorted(k for k in labels if k not in validation_ids
                        and not any(interval(k)[0] < end and start < interval(k)[1] for start, end in excluded)))
