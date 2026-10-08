import json
import multiprocessing
import sqlite3
import pytest

from quant_rsi.ledger.store import Anchor, TraceStore, ZERO_HASH, event_digest


def append_process(path, number):
    TraceStore(path).append(f'event-{number}', 'FAILED', {'synthetic': True, 'number': number})


def crash_process(path):
    import os
    store = TraceStore(path)
    store.append('durable-start', 'STARTED', {'synthetic': True})
    with store.transaction() as transaction:
        transaction.append('not-committed', 'FAILED', {'synthetic': True})
        os._exit(17)


def test_reopen_hash_anchor_and_idempotent_delivery(tmp_path):
    path = tmp_path/'trace.sqlite'
    store = TraceStore(path)
    first = store.append('one', 'FAILED', {'synthetic': True, 'reason': 'example'})
    assert store.append('one', 'FAILED', {'reason': 'example', 'synthetic': True}) == first
    anchor = store.checkpoint()
    reopened = TraceStore(path, trusted_anchor=anchor)
    assert reopened.read() == [first]
    assert anchor == Anchor(1, first['event_hash'])
    with pytest.raises(ValueError, match='collision'):
        reopened.append('one', 'PASSED', {'synthetic': True})
    assert len(reopened.read()) == 1


def test_transaction_exception_keeps_history_without_partial_event(tmp_path):
    store = TraceStore(tmp_path/'trace.sqlite')
    store.append('one', 'FAILED', {'synthetic': True})
    with pytest.raises(RuntimeError):
        with store.transaction() as transaction:
            transaction.append('two', 'STARTED', {'synthetic': True})
            raise RuntimeError('synthetic fault')
    assert [e['event_id'] for e in store.read()] == ['one']


def test_sql_update_delete_are_blocked(tmp_path):
    store = TraceStore(tmp_path/'trace.sqlite')
    store.append('one', 'FAILED', {})
    with sqlite3.connect(store.path) as connection:
        for statement in ('UPDATE events SET kind="PASS"', 'DELETE FROM events'):
            with pytest.raises(sqlite3.IntegrityError, match='append-only'):
                connection.execute(statement)


def test_tamper_and_rollback_below_external_anchor_fail(tmp_path):
    store = TraceStore(tmp_path/'trace.sqlite')
    store.append('one', 'FAILED', {})
    anchor = store.checkpoint()
    with sqlite3.connect(store.path) as connection:
        connection.execute('DROP TRIGGER events_no_update')
        connection.execute('UPDATE events SET payload=?', ('{"forged":true}',))
    with pytest.raises(ValueError, match='integrity'):
        store.read()
    with sqlite3.connect(store.path) as connection:
        connection.execute('DROP TRIGGER events_no_delete')
        connection.execute('DELETE FROM events')
    with pytest.raises(ValueError, match='truncated'):
        TraceStore(store.path, trusted_anchor=anchor)


def test_rehashed_history_still_disagrees_with_trusted_anchor(tmp_path):
    store = TraceStore(tmp_path/'trace.sqlite')
    event = store.append('one', 'FAILED', {})
    anchor = store.checkpoint()
    event['payload'] = {'forged': True}
    event['event_hash'] = event_digest(event)
    with sqlite3.connect(store.path) as connection:
        connection.execute('DROP TRIGGER events_no_update')
        connection.execute('UPDATE events SET payload=?,event_hash=?', (json.dumps(event['payload']), event['event_hash']))
    with pytest.raises(ValueError, match='anchor mismatch'):
        TraceStore(store.path, trusted_anchor=anchor)


def test_multiprocess_writers_preserve_every_failure_and_sequence(tmp_path):
    path = str(tmp_path/'trace.sqlite')
    TraceStore(path)
    context = multiprocessing.get_context('spawn')
    processes = [context.Process(target=append_process, args=(path, i)) for i in range(5)]
    for process in processes:
        process.start()
    for process in processes:
        process.join(20)
        assert process.exitcode == 0
    events = TraceStore(path).read()
    assert len(events) == 5
    assert [e['sequence'] for e in events] == list(range(1, 6))
    assert all(e['kind'] == 'FAILED' for e in events)


def test_process_crash_rolls_back_only_uncommitted_write(tmp_path):
    path = str(tmp_path/'trace.sqlite')
    process = multiprocessing.get_context('spawn').Process(target=crash_process, args=(path,))
    process.start()
    process.join(20)
    assert process.exitcode == 17
    assert [e['event_id'] for e in TraceStore(path).read()] == ['durable-start']


@pytest.mark.parametrize('bad', [float('nan'), float('inf')])
def test_nonfinite_payload_not_persisted(tmp_path, bad):
    store = TraceStore(tmp_path/'trace.sqlite')
    with pytest.raises(ValueError):
        store.append('bad', 'FAILED', {'value': bad})
    assert store.read() == []


def test_returned_payload_cannot_mutate_stored_events(tmp_path):
    store = TraceStore(tmp_path/'trace.sqlite')
    record = store.append('one', 'FAILED', {'nested': {'a': 1}})
    record['payload']['nested']['a'] = 99
    assert store.read()[0]['payload']['nested']['a'] == 1
    assert TraceStore(tmp_path/'empty.sqlite').checkpoint() == Anchor(0, ZERO_HASH)
