import copy
import json

import pytest

from quant_rsi.harness.cp_isolation import command, check_boundary, parse_result, score_result, cp_packets, trusted_expected


def test_container_command_has_fixed_boundaries():
    args = command('sha256:' + 'a'*64, 'qrsi-test', 'submission.py', 'input.json')
    for flag in ('--pull=never', '--read-only', '--cap-drop', '--pids-limit', '--memory-swap'):
        assert flag in args
    assert args.count('--mount') == 2
    assert all('readonly' in args[i+1] for i, v in enumerate(args) if v == '--mount')
    assert '--privileged' not in args
    assert '--env' not in args
    with pytest.raises(ValueError):
        command('python:latest', 'qrsi-test', 'a', 'b')


def test_worker_cannot_submit_score_or_overwrite():
    for value in ({'score': 'PASS'}, {'records': [], 'retained': [], 'overwrite': True}, {'records': [], 'retained': 'bad'}):
        with pytest.raises(ValueError):
            parse_result(json.dumps(value))
    assert not score_result('{bad', {})['passed']
    assert not score_result('{"records":[],"records":[],"retained":[]}', {})['passed']
    assert not score_result('[' * 2000 + ']' * 2000, {})['passed']


def test_external_behavior_scoring_and_state_isolation():
    expected = trusted_expected(cp_packets()['cp04'])
    assert [r['value'][0]['event_id'] for r in expected['records']] == ['A1', 'B1', 'A1', 'A1']
    assert expected['retained'][0][0]['amount'] == 999
    assert expected['retained'][3][0]['amount'] == 2
    assert score_result(json.dumps(expected), expected)['passed']
    changed = copy.deepcopy(expected)
    changed['records'][2]['value'] += changed['records'][0]['value']
    assert not score_result(json.dumps(changed), expected)['passed']


def test_privileged_or_extra_mount_refused():
    image = 'sha256:' + 'a'*64
    inspect = dict(image=image, user='65532:65532', entrypoint=['python','-I','-S','-B','/worker/runner.py'],
        host=dict(Memory=512*1024*1024, MemorySwap=512*1024*1024, NanoCpus=500000000,
            PidsLimit=32, ReadonlyRootfs=True, Privileged=False, NetworkMode='none',
            CapDrop=['ALL'], SecurityOpt=['no-new-privileges=true'], PidMode='', IpcMode='private', Devices=[], DeviceRequests=None),
        mounts=[dict(Type='bind', RW=False, Destination='/submit/submission.py'),
                dict(Type='bind', RW=False, Destination='/public/input.json')])
    check_boundary(inspect, image)
    for key, value in [('Privileged', True), ('NetworkMode', 'host'), ('PidMode', 'host'), ('ReadonlyRootfs', False)]:
        changed = copy.deepcopy(inspect)
        changed['host'][key] = value
        with pytest.raises(ValueError):
            check_boundary(changed, image)
    inspect['mounts'].append(dict(Type='bind', RW=False, Destination='/custodian'))
    with pytest.raises(ValueError):
        check_boundary(inspect, image)
