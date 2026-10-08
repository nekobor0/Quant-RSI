"""Test configuration.

The default pytest temporary root is not writable in this environment, so
run-directory tests are given a workspace-local base directory instead. This
keeps the tests runnable without elevated filesystem permissions.
"""
from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LOCAL_TMP = ROOT / '.pytest_tmp'
_UNSAFE = re.compile(r'[^A-Za-z0-9._-]+')


def _safe_dir_name(node_name: str) -> str:
    """Windows-safe, length-bounded directory name for a test node id.

    Parametrised tests can carry very long or character-hostile ids, so the
    name is sanitised and truncated, with a digest suffix for uniqueness.
    """
    digest = hashlib.sha256(node_name.encode('utf-8')).hexdigest()[:12]
    cleaned = _UNSAFE.sub('_', node_name).strip('._-') or 'test'
    return f'{cleaned[:60]}_{digest}'


@pytest.fixture
def tmp_path(request):
    """Workspace-local drop-in replacement for the built-in tmp_path fixture."""
    LOCAL_TMP.mkdir(exist_ok=True)
    path = LOCAL_TMP / _safe_dir_name(request.node.name)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)
    return path
