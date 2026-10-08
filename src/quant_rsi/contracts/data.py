"""Immutable data metadata contracts; no data acquisition or PIT execution."""

from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import stat
from types import MappingProxyType

__all__ = ['DataSpec', 'SnapshotFile', 'SnapshotManifest']


def _text(value, name):
    if type(value) is not str or not value.strip():
        raise ValueError(f'{name} must be a nonempty string')


def _hash(value):
    if type(value) is not str or re.fullmatch(r'[0-9a-f]{64}', value) is None:
        raise ValueError('hash must be lowercase SHA-256 hex')


def _timestamp(value, name):
    _text(value, name)
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})', value) is None:
        raise ValueError(f'{name} must be an ISO timestamp with timezone')
    offset = value[-6:]
    if offset[0] in '+-' and (int(offset[1:3]) > 23 or int(offset[4:]) > 59):
        raise ValueError(f'{name} has an invalid offset')
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def _mapping(value, name, numeric=False):
    if not isinstance(value, Mapping) or (not numeric and not value):
        raise ValueError(f'{name} must be a mapping' + ('' if numeric else ' with units'))
    copied = dict(value)
    for key, item in copied.items():
        _text(key, name)
        if numeric:
            if item is not None and (type(item) not in (int, float) or
                                     (type(item) is float and not math.isfinite(item))):
                raise ValueError('source numeric values must be finite numbers or None')
        else:
            _text(item, name)
    return MappingProxyType(copied)


def _plain(value):
    if isinstance(value, _Contract):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


class _Contract:
    __slots__ = ()

    def to_dict(self):
        return {f.name: _plain(getattr(self, f.name)) for f in fields(self)}

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, Mapping) or set(value) != {f.name for f in fields(cls)}:
            raise ValueError(f'{cls.__name__}: missing or unknown fields')
        return cls(**dict(value))

    def to_json(self):
        return json.dumps(self.to_dict(), sort_keys=True, separators=(',', ':'),
                          ensure_ascii=True, allow_nan=False)

    def content_hash(self):
        return hashlib.sha256(self.to_json().encode('utf-8')).hexdigest()

    @property
    def digest(self):
        """SHA-256 of canonical JSON; suitable for W04 content references."""
        return self.content_hash()


@dataclass(frozen=True, slots=True)
class DataSpec(_Contract):
    """Metadata for one source revision, not rows or a PIT query engine.

    event_time describes the underlying event (which may be prospective).
    published_at is this revision's release; available_at is its earliest
    usable instant; ingested_at records capture, never substitutes availability.
    Membership validity is [effective_from, effective_to); None means open-ended.
    timezone is the source's declared zone label; timestamps carry their offsets.
    source_numeric contains optional source measurements, with unknowns as None.
    """

    source_id: str
    source_revision: str
    raw_artifact_hash: str
    event_time: str
    published_at: str
    available_at: str
    ingested_at: str
    effective_from: str
    effective_to: str | None
    timezone: str
    units: Mapping[str, str]
    adjustment_rule: str
    universe_version: str
    cleaning_spec_version: str
    pit_version: str
    pit_rule: str
    revision_rule: str
    source_numeric: Mapping[str, int | float | None] = field(default_factory=dict)

    def __post_init__(self):
        for name in ('source_id', 'source_revision', 'timezone', 'adjustment_rule',
                     'universe_version', 'cleaning_spec_version', 'pit_version'):
            _text(getattr(self, name), name)
        _hash(self.raw_artifact_hash)
        times = {name: _timestamp(getattr(self, name), name) for name in
                 ('event_time', 'published_at', 'available_at', 'ingested_at', 'effective_from')}
        if not times['published_at'] <= times['available_at'] <= times['ingested_at']:
            raise ValueError('require published_at <= available_at <= ingested_at')
        if self.effective_to is not None:
            if _timestamp(self.effective_to, 'effective_to') <= times['effective_from']:
                raise ValueError('effective_to must follow effective_from')
        if self.pit_rule != 'available_at_lte_decision_at_and_membership_effective_at_decision':
            raise ValueError('unsupported PIT rule')
        if self.revision_rule != 'choose_latest_revision_available_by_decision_not_latest_download':
            raise ValueError('unsupported revision rule')
        object.__setattr__(self, 'units', _mapping(self.units, 'units'))
        object.__setattr__(self, 'source_numeric', _mapping(self.source_numeric, 'source_numeric', True))
        if not self.source_numeric.keys() <= self.units.keys():
            raise ValueError('source numeric fields require units')


@dataclass(frozen=True, slots=True)
class SnapshotFile(_Contract):
    """Portable relative POSIX path and expected SHA-256 of the actual bytes."""

    path: str
    sha256: str

    def __post_init__(self):
        _text(self.path, 'path')
        parts = self.path.split('/')
        if (any(p in ('', '.', '..') or p.endswith((' ', '.')) for p in parts)
                or any(c in self.path for c in '\\:<>"|?*')
                or any(ord(c) < 32 for c in self.path)
                or any(re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', p, re.I)
                       for p in parts)):
            raise ValueError('path must be a safe relative file path')
        _hash(self.sha256)


@dataclass(frozen=True, slots=True)
class SnapshotManifest(_Contract):
    snapshot_id: str
    data_spec: DataSpec
    files: tuple[SnapshotFile, ...]

    def __post_init__(self):
        _text(self.snapshot_id, 'snapshot_id')
        spec = self.data_spec
        if isinstance(spec, Mapping):
            spec = DataSpec.from_dict(spec)
        if type(spec) is not DataSpec:
            raise ValueError('data_spec must be DataSpec')
        if type(self.files) not in (tuple, list) or not self.files:
            raise ValueError('files must be a nonempty sequence')
        entries = tuple(SnapshotFile.from_dict(f) if isinstance(f, Mapping) else f for f in self.files)
        if any(type(f) is not SnapshotFile for f in entries):
            raise ValueError('files must contain SnapshotFile')
        if len({f.path.casefold() for f in entries}) != len(entries):
            raise ValueError('duplicate file paths')
        if spec.raw_artifact_hash not in {f.sha256 for f in entries}:
            raise ValueError('raw_artifact_hash must be included in files')
        object.__setattr__(self, 'data_spec', spec)
        object.__setattr__(self, 'files', tuple(sorted(entries, key=lambda f: f.path)))

    def verify_files(self, root):
        """Rehash regular files under an explicit absolute root; raise on failure.

        Symlinks/reparse points below root are rejected, even internal ones.
        The caller must keep the root stable during verification; this is not
        an OS sandbox against concurrent hostile filesystem mutation.
        """
        root = Path(root)
        if not root.is_absolute():
            raise ValueError('root must be absolute')
        root = root.resolve(strict=True)
        if not root.is_dir():
            raise ValueError('root must be a directory')
        for entry in self.files:
            candidate = root
            for part in entry.path.split('/'):
                candidate = candidate / part
                info = candidate.lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                    raise ValueError('symlink/reparse point forbidden')
            resolved = candidate.resolve(strict=True)
            if not resolved.is_relative_to(root) or not stat.S_ISREG(info.st_mode):
                raise ValueError('file must be regular and contained under root')
            digest = hashlib.sha256()
            with resolved.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
            if digest.hexdigest() != entry.sha256:
                raise ValueError(f'file hash mismatch: {entry.path}')
