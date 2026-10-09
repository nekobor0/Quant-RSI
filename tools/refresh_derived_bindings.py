"""Refresh the derived pilot's SHA-256 bindings and its authorization request.

Run this after ANY change to a bound file. It recomputes every entry in the
derived freeze's `sha256` map, rewrites the freeze, then regenerates the
authorization request so its freeze/entry bindings match.

Order matters: the freeze is written before the request is derived from it,
because the request binds the freeze digest, and the freeze deliberately does
not contain its own digest (a self-hash would never be stable).

Usage:  python -B tools/refresh_derived_bindings.py
"""
from __future__ import annotations

import json
import sys
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / 'benchmark/capability_public/pilot_v02_dsh/freeze.json'
REQUEST = ROOT / 'benchmark/capability_public/pilot_v02_dsh/authorization_request.json'
ENTRY = ROOT / 'src/quant_rsi/harness/compatibility_pilot_dsh.py'
FROZEN_BASE_ENTRY_SHA = 'cb5cef8e17e1142a3758ece4b584e0254c2e27ad64f66b1874e52a9ba4195419'


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def main():
    freeze = json.loads(FREEZE.read_text(encoding='utf-8'))

    # 1. Frozen base entry must be untouched, or the base pilot is broken.
    base_entry = digest(ROOT / 'src/quant_rsi/harness/compatibility_pilot.py')
    if base_entry != FROZEN_BASE_ENTRY_SHA:
        print('ERROR: frozen base entry changed; the base pilot is broken.', file=sys.stderr)
        return 2

    # 2. Recompute every binding listed in the derived freeze.
    refreshed = {}
    for relative in sorted(freeze['sha256']):
        target = ROOT / relative
        if not target.exists():
            print(f'ERROR: bound path missing: {relative}', file=sys.stderr)
            return 3
        refreshed[relative] = digest(target)
    freeze['sha256'] = refreshed

    # 3. Never allow a self-reference: the digest would be unstable.
    freeze['sha256'].pop('benchmark/capability_public/pilot_v02_dsh/freeze.json', None)

    FREEZE.write_text(json.dumps(freeze, sort_keys=True, indent=2, ensure_ascii=True) + '\n',
                      encoding='utf-8')
    freeze_sha = digest(FREEZE)

    # 4. Regenerate the request so it binds the freeze just written.
    request = json.loads(REQUEST.read_text(encoding='utf-8'))
    request['freeze_sha256'] = freeze_sha
    request['entry_sha256'] = digest(ENTRY)
    request['frozen_base_entry_sha256'] = base_entry
    request['money_caps_cny'] = dict(freeze['money_caps_cny'])
    request['approved'] = False
    request['keys_rotated'] = False
    REQUEST.write_text(json.dumps(request, sort_keys=True, indent=2, ensure_ascii=True) + '\n',
                       encoding='utf-8')

    print('bindings refreshed:', len(refreshed))
    print('freeze  sha256     :', freeze_sha)
    print('entry   sha256     :', digest(ENTRY))
    print('base entry verified:', base_entry)
    print('caps               :', freeze['money_caps_cny'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
