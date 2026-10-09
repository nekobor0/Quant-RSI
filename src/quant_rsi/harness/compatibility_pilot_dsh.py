"""Derived-freeze entry for the DS-Harness six-task compatibility pilot.

This module is the ONLY difference from the frozen pilot. It exists because the
base pilot freezes `deepseek-v4-pro`, while the DS-Harness task brief designates
`deepseek-flash`. Editing `compatibility_pilot.py` itself would have changed its
SHA-256 and broken the base pilot's frozen entry binding, so the override lives
here instead and the frozen module is left byte-identical.

What it does, and nothing more:

  * points the frozen module's FREEZE constant at the derived freeze;
  * reuses the frozen validate/run/replay entry points unchanged;
  * binds any real authorization to THIS module's hash and the derived freeze's
    hash, so a base-pilot authorization cannot authorize a derived run.

No new transport, trace, budget or scoring system is introduced. The frozen
serial adapter, evaluator and TraceStore are used as-is.
"""
from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

from quant_rsi.harness import compatibility_pilot as pilot
from quant_rsi.harness.comparison import ROOT

DERIVED_FREEZE = ROOT / 'benchmark/capability_public/pilot_v02_dsh/freeze.json'
DERIVED_ENTRY = Path(__file__)
DEFAULT_AUTHORIZATION = ROOT / 'benchmark/capability_public/pilot_v02_dsh/authorization_request.json'

# Captured at import time, BEFORE _bind() rebinds pilot.__file__. Reading
# pilot.__file__ after binding would return the derived entry, so the frozen
# base entry's integrity check would compare the wrong file and report a false
# change.
FROZEN_BASE_FILE = Path(pilot.__file__)


def digest(raw):
    return sha256(raw).hexdigest()


def entry_sha256():
    return digest(DERIVED_ENTRY.read_bytes())


def freeze_sha256():
    return digest(DERIVED_FREEZE.read_bytes())


def _bind():
    """Bind the frozen module to the derived freeze AND the derived entry.

    Three bindings are required, and the third is the subtle one:

      * FREEZE       -- which freeze is validated, hashed and traced;
      * ENTRY_PATH   -- which file result records name;
      * __file__     -- which file the FROZEN check_authorization() hashes.

    `check_authorization` reads `Path(__file__)`, evaluated inside the frozen
    module, so it hashes the frozen module's own path. Rebinding the module
    attribute here redirects that hash to the derived entry WITHOUT editing the
    frozen file's bytes. Editing the frozen file instead would break the base
    pilot, whose freeze pins that file's SHA-256.
    """
    pilot.FREEZE = DERIVED_FREEZE
    pilot.ENTRY_PATH = DERIVED_ENTRY
    pilot.__file__ = str(DERIVED_ENTRY)
    return DERIVED_FREEZE


def validate_derived_bindings(plan=None):
    """Verify every path in the derived freeze's sha256 map.

    The frozen validate_freeze() reads FREEZE['sha256'], but it cannot verify the
    derived module's own contract, so the derived entry enforces it here before
    anything is dispatched. Raises on the first mismatch.
    """
    plan = plan or pilot.load(DERIVED_FREEZE)
    checked = {}
    for relative, expected in plan.get('sha256', {}).items():
        target = ROOT / relative
        if not target.exists():
            raise ValueError('derived binding target missing: ' + relative)
        actual = digest(target.read_bytes())
        if actual != expected:
            raise ValueError('derived binding changed: ' + relative)
        checked[relative] = actual
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorization', type=Path, default=None)
    parser.add_argument('--run-id')
    parser.add_argument('--replay', type=Path)
    args = parser.parse_args()
    _bind()

    if args.replay:
        validate_derived_bindings()
        result = pilot.replay(args.replay)
    elif args.authorization:
        if not args.run_id:
            parser.error('--run-id required for an authorized real batch')
        checked = validate_derived_bindings()
        result = pilot.run(args.run_id, pilot.load(args.authorization))
        result['derived_bindings_verified'] = sorted(checked)
    else:
        checked = validate_derived_bindings()
        plan = pilot.validate_freeze()
        base_entry = digest(FROZEN_BASE_FILE.read_bytes())
        result = {
            'status': 'OFFLINE_PREPARED_REAL_CALLS_NOT_AUTHORIZED',
            'real_calls': 0,
            'derived_freeze': str(DERIVED_FREEZE),
            'freeze_sha256': freeze_sha256(),
            'entry_module': 'quant_rsi.harness.compatibility_pilot_dsh',
            'entry_sha256': entry_sha256(),
            'derived_bindings_verified': len(checked),
            'frozen_base_entry_sha256': base_entry,
            'frozen_base_entry_unchanged':
                base_entry == 'cb5cef8e17e1142a3758ece4b584e0254c2e27ad64f66b1874e52a9ba4195419',
            'task_ids': plan['task_ids'],
            'models': {k: v['chat_provider']['model_id'] for k, v in plan['providers'].items()},
        }
    print(json.dumps(result if 'records' not in result else
                     {'calls': result['calls'], 'stop': result['stop']}, indent=2))


if __name__ == '__main__':
    main()
