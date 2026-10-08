from dataclasses import FrozenInstanceError, fields, replace
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from quant_rsi.contracts.data import DataSpec, SnapshotFile, SnapshotManifest


RAW = b'SYNTHETIC metadata fixture only\n'
SHA = hashlib.sha256(RAW).hexdigest()


def spec():
    return DataSpec(
        source_id='SYNTHETIC', source_revision='SYNTHETIC-r1', raw_artifact_hash=SHA,
        event_time='2000-01-01T00:00:00Z', published_at='2000-01-02T00:00:00Z',
        available_at='2000-01-02T08:00:00+08:00', ingested_at='2000-01-03T00:00:00Z',
        effective_from='2000-01-01T00:00:00Z', effective_to=None, timezone='UTC',
        units={'unknown': 'SYNTHETIC unit', 'count': 'SYNTHETIC count'},
        adjustment_rule='SYNTHETIC none', universe_version='SYNTHETIC-u1',
        cleaning_spec_version='SYNTHETIC-c1', pit_version='SYNTHETIC-p1',
        pit_rule='available_at_lte_decision_at_and_membership_effective_at_decision',
        revision_rule='choose_latest_revision_available_by_decision_not_latest_download',
        source_numeric={'unknown': None, 'count': 1})


def manifest():
    return SnapshotManifest('SYNTHETIC-s1', spec(), [SnapshotFile('raw.txt', SHA)])


@pytest.mark.parametrize('obj', [spec(), SnapshotFile('raw.txt', SHA), manifest()])
def test_roundtrip_and_hash(obj):
    restored = type(obj).from_dict(json.loads(obj.to_json()))
    assert restored == obj
    assert obj.content_hash() == hashlib.sha256(obj.to_json().encode('utf-8')).hexdigest()
    assert restored.content_hash() == obj.content_hash()
    assert restored.digest == obj.content_hash()
    with pytest.raises((FrozenInstanceError, AttributeError)):
        setattr(obj, fields(obj)[0].name, 'changed')


@pytest.mark.parametrize('obj', [spec(), SnapshotFile('raw.txt', SHA), manifest()])
def test_every_field_required_and_unknown_fields_rejected(obj):
    for key in obj.to_dict():
        payload = obj.to_dict()
        del payload[key]
        with pytest.raises(ValueError, match='missing or unknown'):
            type(obj).from_dict(payload)
    with pytest.raises(ValueError, match='missing or unknown'):
        type(obj).from_dict(dict(obj.to_dict(), unexpected='SYNTHETIC'))
    with pytest.raises(TypeError):
        obj.to_dict(unexpected=True)


@pytest.mark.parametrize('name', ['source_revision', 'raw_artifact_hash', 'available_at',
                                'units', 'cleaning_spec_version', 'pit_version',
                                'pit_rule', 'revision_rule', 'published_at', 'event_time',
                                'ingested_at', 'effective_from', 'source_id', 'timezone',
                                'adjustment_rule', 'universe_version'])
@pytest.mark.parametrize('value', [None, '', float('nan')])
def test_required_metadata_cannot_be_null_empty_or_nan(name, value):
    with pytest.raises(ValueError):
        replace(spec(), **{name: value})


@pytest.mark.parametrize('name,value', [
    ('available_at', '2000-01-02'), ('available_at', '2000-01-02T00:00:00'),
    ('available_at', '2000-02-30T00:00:00Z'), ('available_at', '2000-01-02T00:00:00+01:99'),
    ('available_at', '2000-01-01T00:00:00Z'), ('ingested_at', '2000-01-01T00:00:00Z'),
    ('effective_to', '1999-01-01T00:00:00Z'), ('effective_to', '2000-01-01T00:00:00Z'),
    ('raw_artifact_hash', 'not-a-hash'), ('raw_artifact_hash', 'A' * 64),
    ('units', {}), ('units', {'x': None}), ('units', {1: 'unit'}),
    ('source_revision', 1), ('pit_rule', 'latest'), ('revision_rule', 'latest_download'),
    ('source_numeric', {'count': True}), ('source_numeric', {'count': '1'}),
    ('source_numeric', {'count': float('nan')}), ('source_numeric', {'count': float('inf')}),
    ('source_numeric', {'count': float('-inf')}), ('source_numeric', {'missing_unit': None}),
    ('source_numeric', {'count': []}), ('source_numeric', None),
])
def test_malformed_metadata(name, value):
    with pytest.raises(ValueError):
        replace(spec(), **{name: value})


def test_metadata_semantics_and_hash_binding():
    original = spec()
    assert original.source_numeric['unknown'] is None
    assert json.loads(original.to_json())['source_numeric']['unknown'] is None
    assert replace(original, event_time='2001-01-01T00:00:00Z')  # prospective event
    assert replace(original, effective_to='2001-01-01T00:00:00Z')
    for name in ('source_revision', 'cleaning_spec_version', 'pit_version', 'universe_version'):
        assert replace(original, **{name: 'SYNTHETIC-v2'}).content_hash() != original.content_hash()


def test_nested_immutability_and_mapping_order():
    payload = manifest().to_dict()
    frozen = SnapshotManifest.from_dict(payload)
    before = frozen.content_hash()
    payload['data_spec']['units']['count'] = 'changed'
    payload['data_spec']['source_numeric']['count'] = 99
    payload['files'].clear()
    assert frozen.content_hash() == before
    for mapping in (frozen.data_spec.units, frozen.data_spec.source_numeric):
        with pytest.raises(TypeError):
            mapping['count'] = 99
    with pytest.raises((FrozenInstanceError, AttributeError)):
        frozen.files[0].sha256 = '0' * 64
    with pytest.raises(TypeError):
        frozen.files[0] = SnapshotFile('new.txt', SHA)
    reordered = spec().to_dict()
    reordered['units'] = dict(reversed(list(reordered['units'].items())))
    reordered['source_numeric'] = dict(reversed(list(reordered['source_numeric'].items())))
    assert DataSpec.from_dict(dict(reversed(list(reordered.items())))).content_hash() == spec().content_hash()
    entries = [SnapshotFile('z.txt', SHA), SnapshotFile('a.txt', SHA)]
    assert replace(frozen, files=entries).content_hash() == replace(frozen, files=entries[::-1]).content_hash()


@pytest.mark.parametrize('path', ['../out', '/abs', 'a/../../out', 'a/./b', './a',
                                'C:/out', 'C:out', '\\\\host\\share', 'a\\..\\b',
                                'a//b', 'a/', 'raw.txt:stream', 'a\x00b', 'a./b', 'NUL.txt'])
def test_unsafe_paths(path):
    with pytest.raises(ValueError):
        SnapshotFile(path, SHA)


@pytest.mark.parametrize('value', [None, '', 'bad', float('nan')])
def test_file_hash_required(value):
    with pytest.raises(ValueError):
        SnapshotFile('raw.txt', value)


def test_manifest_rejects_incomplete_or_unknown_nested_metadata():
    for files_value in ([], None, ['raw.txt'], [SnapshotFile('a', SHA), SnapshotFile('A', SHA)],
                        [SnapshotFile('a', '0' * 64)]):
        with pytest.raises(ValueError):
            replace(manifest(), files=files_value)
    for name in ('data_spec', 'files'):
        value = manifest().to_dict()
        nested = value[name] if name == 'data_spec' else value[name][0]
        nested['unexpected'] = 'SYNTHETIC'
        with pytest.raises(ValueError):
            SnapshotManifest.from_dict(value)


def test_verify_actual_bytes_and_replacement(tmp_path):
    path = tmp_path / 'raw.txt'
    path.write_bytes(RAW)
    frozen = manifest()
    assert frozen.verify_files(tmp_path) is None
    other = tmp_path / 'replacement'
    other.write_bytes(b'X' * len(RAW))
    other.replace(path)
    with pytest.raises(ValueError, match='hash mismatch'):
        frozen.verify_files(tmp_path)
    path.unlink()
    with pytest.raises(FileNotFoundError):
        frozen.verify_files(tmp_path)
    path.mkdir()
    with pytest.raises(ValueError, match='regular'):
        frozen.verify_files(tmp_path)
    with pytest.raises(ValueError, match='absolute'):
        frozen.verify_files(Path('.'))


@pytest.mark.parametrize('directory', [False, True])
def test_symlink_escape(tmp_path, directory):
    root = tmp_path / 'root'
    root.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'raw.txt').write_bytes(RAW)
    link = root / ('link' if directory else 'raw.txt')
    try:
        link.symlink_to(outside if directory else outside / 'raw.txt', target_is_directory=directory)
    except OSError as exc:
        if directory and os.name == 'nt':
            result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)],
                                    capture_output=True, check=False)
            assert result.returncode == 0, result.stderr
        else:
            pytest.skip(f'symlink creation unavailable: {exc}')
    frozen = replace(manifest(), files=[SnapshotFile('link/raw.txt' if directory else 'raw.txt', SHA)])
    with pytest.raises(ValueError, match='symlink/reparse'):
        frozen.verify_files(root)
