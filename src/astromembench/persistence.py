"""Atomic JSON snapshots that tolerate short Windows reader/scanner locks."""
from pathlib import Path
import errno
import json
import os
import time
import tempfile

from .schema import json_text


def _file_access(operation):
    """Retry only transient Windows sharing/replace locks, never experiment work."""
    for attempt in range(101):
        try:
            return operation()
        except OSError as exc:
            locked = (getattr(exc, 'winerror', None) in {5, 32, 33} or
                      (os.name == 'nt' and isinstance(exc, PermissionError) and exc.errno == errno.EACCES))
            if not locked or attempt == 100:
                raise
            time.sleep(.01)


def read_json(path):
    return json.loads(_file_access(lambda: Path(path).read_text(encoding='utf-8')))


def json_signature(path):
    stat = _file_access(lambda: Path(path).stat())
    return stat.st_ino, stat.st_mtime_ns, stat.st_size


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.tmp-', dir=path.parent)
    temporary = Path(name)
    # Windows readers may temporarily deny replacement. Retry only the local
    # rename, never its enclosing native call, action, or evaluation attempt.
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            stream.write(json_text(value) + '\n')
        _file_access(lambda: temporary.replace(path))
    finally:
        temporary.unlink(missing_ok=True)
