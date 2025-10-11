# -----------------------------
# db.py
# -----------------------------
import json, time, threading, os
from typing import Dict, Any, Optional, List

_DB_PATH = os.environ.get("DB_FILE", "db.json")
_LOCK = threading.RLock()

_EMPTY = {"users": {}, "game_logs": {}}  # game_logs per user

def _load() -> Dict[str, Any]:
    if not os.path.exists(_DB_PATH):
        with open(_DB_PATH, "w", encoding="utf-8") as f:
            json.dump(_EMPTY, f)
    with open(_DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def _save(data: Dict[str, Any]):
    with open(_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def ensure_db():
    with _LOCK:
        _ = _load()

# --- users ---

def create_guest() -> str:
    with _LOCK:
        data = _load()
        uid = f"guest-{int(time.time()*1000)}"
        data["users"][uid] = {"id": uid, "guest": True, "created_at": time.time()}
        data["game_logs"].setdefault(uid, [])
        _save(data)
        return uid


def create_user(username: str, password: str) -> Optional[str]:
    with _LOCK:
        d = _load()
        if username in d["users"]:
            return None
        d["users"][username] = {
            "id": username,
            "guest": False,
            "password": password,
            "created_at": time.time(),
        }
        d["game_logs"].setdefault(username, [])
        _save(d)
        return username


def auth(username: str, password: str) -> bool:
    with _LOCK:
        d = _load()
        u = d["users"].get(username)
        return bool(u and not u.get("guest") and u.get("password") == password)


def append_log(user_id: str, entry: Dict[str, Any]):
    with _LOCK:
        d = _load()
        d["game_logs"].setdefault(user_id, [])
        d["game_logs"][user_id].append(entry)
        _save(d)


def get_logs(user_id: str) -> List[Dict[str, Any]]:
    with _LOCK:
        d = _load()
        return d["game_logs"].get(user_id, [])
