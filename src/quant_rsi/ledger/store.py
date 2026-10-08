"""Local atomic append-only trace. External Anchor custody is a deployment boundary.

SQLite triggers/hash chains detect accidental or anchored historical mutation;
they do not secure a database against its OS file owner. No sealed claim here.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

ZERO_HASH = '0' * 64


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def event_digest(event):
    return hashlib.sha256(encoded({k: v for k, v in event.items() if k != 'event_hash'}).encode()).hexdigest()


@dataclass(frozen=True)
class Anchor:
    sequence: int
    event_hash: str

    def __post_init__(self):
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError('invalid anchor sequence')
        if (not isinstance(self.event_hash, str) or len(self.event_hash) != 64
                or any(c not in '0123456789abcdef' for c in self.event_hash)):
            raise ValueError('invalid anchor digest')
        if self.sequence == 0 and self.event_hash != ZERO_HASH:
            raise ValueError('empty anchor must use zero hash')


def verify_events(events, anchor=None):
    previous = ZERO_HASH
    ids = set()
    for sequence, event in enumerate(events, 1):
        if (event['sequence'] != sequence or event['previous_hash'] != previous
                or event['event_hash'] != event_digest(event) or event['event_id'] in ids):
            raise ValueError('trace chain integrity failure')
        previous = event['event_hash']
        ids.add(event['event_id'])
    if anchor is not None:
        if anchor.sequence > len(events):
            raise ValueError('trace truncated below trusted anchor')
        observed = ZERO_HASH if anchor.sequence == 0 else events[anchor.sequence - 1]['event_hash']
        if observed != anchor.event_hash:
            raise ValueError('trusted anchor mismatch')
    return Anchor(len(events), previous)


def _read(connection):
    return [dict(sequence=row[0], event_id=row[1], kind=row[2], payload=json.loads(row[3]),
                 previous_hash=row[4], event_hash=row[5], created_at=row[6])
            for row in connection.execute('SELECT sequence,event_id,kind,payload,previous_hash,event_hash,created_at FROM events ORDER BY sequence')]


class TraceTransaction:
    """Trusted writer transaction, used by the budget service for atomic decisions."""
    def __init__(self, connection, events):
        self._connection = connection
        self._events = events

    def events(self):
        return json.loads(encoded(self._events))

    def append(self, event_id, kind, payload):
        if any(type(x) is not str or not x.strip() or x != x.strip() for x in (event_id, kind)):
            raise ValueError('event ID and kind must be nonblank trimmed strings')
        if type(payload) is not dict:
            raise ValueError('event payload must be a JSON object')
        clean = json.loads(encoded(payload))
        for old in self._events:
            if old['event_id'] == event_id:
                if old['kind'] != kind or old['payload'] != clean:
                    raise ValueError('event ID collision with different content')
                return json.loads(encoded(old))
        event = dict(sequence=len(self._events) + 1, event_id=event_id, kind=kind, payload=clean,
                     previous_hash=self._events[-1]['event_hash'] if self._events else ZERO_HASH,
                     created_at=datetime.now(timezone.utc).isoformat())
        event['event_hash'] = event_digest(event)
        self._connection.execute(
            'INSERT INTO events(sequence,event_id,kind,payload,previous_hash,event_hash,created_at) VALUES(?,?,?,?,?,?,?)',
            (event['sequence'], event_id, kind, encoded(clean), event['previous_hash'], event['event_hash'], event['created_at']))
        self._events.append(event)
        return json.loads(encoded(event))


class TraceStore:
    def __init__(self, path, trusted_anchor=None):
        self.path = Path(path).resolve()
        self.trusted_anchor = trusted_anchor
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL,
                    kind TEXT NOT NULL, payload TEXT NOT NULL, previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
                    BEGIN SELECT RAISE(ABORT, 'append-only trace'); END;
                CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
                    BEGIN SELECT RAISE(ABORT, 'append-only trace'); END;
            ''')
        finally:
            connection.close()
        self.read()

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.execute('PRAGMA synchronous=FULL')
        return connection

    @contextmanager
    def transaction(self):
        connection = self._connect()
        try:
            connection.execute('BEGIN IMMEDIATE')
            events = _read(connection)
            verify_events(events, self.trusted_anchor)
            yield TraceTransaction(connection, events)
            connection.execute('COMMIT')
        except BaseException:
            if connection.in_transaction:
                connection.execute('ROLLBACK')
            raise
        finally:
            connection.close()

    def append(self, event_id, kind, payload):
        with self.transaction() as transaction:
            return transaction.append(event_id, kind, payload)

    def read(self):
        connection = self._connect()
        try:
            events = _read(connection)
            verify_events(events, self.trusted_anchor)
            return events
        finally:
            connection.close()

    def checkpoint(self):
        """Return a digest for independent custody; keeping it beside DB is not custody."""
        return verify_events(self.read(), self.trusted_anchor)
