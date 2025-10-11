
from __future__ import annotations
import json, os, tempfile, time, uuid
from pathlib import Path
from typing import Any, Dict

def secure_uuid() -> str:
    """Generate a cryptographically strong UUID4 string."""
    return str(uuid.uuid4())

def monotonic_ns() -> int:
    """Return a monotonic time in nanoseconds."""
    return time.monotonic_ns()

def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    """Atomically write JSON using a temp file + replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name, dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.remove(tmp_name)
        except Exception:
            pass
        raise

def read_json(path: Path) -> Dict[str, Any]:
    """Read JSON; return {} if missing."""
    path = Path(path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
