
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
import pandas as pd

from utils import atomic_write_json, read_json, secure_uuid, monotonic_ns

DB_PATH = Path("../Downloads/db.json")

INIT: Dict[str, Any] = {
    "users": {},
    "queues": [],
    "invites": [],
    "games": {},
    "game_logs": {}
}

RPS = ["R", "P", "S"]
WINS = {("R","S"), ("P","R"), ("S","P")}

def load_db() -> Dict[str, Any]:
    """Load DB (create defaults if missing)."""
    db = read_json(DB_PATH)
    if not db:
        db = INIT.copy()
        atomic_write_json(DB_PATH, db)
    for k in INIT.keys():
        db.setdefault(k, INIT[k].__class__())
    return db

def save_db(db: Dict[str, Any]) -> None:
    """Persist DB atomically."""
    atomic_write_json(DB_PATH, db)

def ensure_user_logs(db: Dict[str, Any], uid: str) -> None:
    """Ensure per-user log list exists."""
    if uid not in db["game_logs"]:
        db["game_logs"][uid] = []

def register_user(db: Dict[str, Any], username: str, password: str) -> Tuple[Optional[str], Optional[str]]:
    """Register new user. Plain password for MVP only."""
    if not username or len(username) > 64:
        return None, "Invalid username."
    if username in db["users"]:
        return None, "Username already exists."
    uid = secure_uuid()
    db["users"][username] = {"password": password, "id": uid}
    ensure_user_logs(db, uid)
    save_db(db)
    return uid, None

def login_user(db: Dict[str, Any], username: str, password: str) -> Tuple[Optional[str], Optional[str]]:
    """Login check. Plain-text MVP; replace with hashing later."""
    user = db["users"].get(username)
    if not user or user.get("password") != password:
        return None, "Invalid credentials."
    ensure_user_logs(db, user["id"])
    return user["id"], None

def other_two(center: str) -> List[str]:
    """Return two R/P/S that are not center."""
    return [x for x in RPS if x != center]

def new_round_state() -> Dict[str, Any]:
    """Fresh round state with 3s-deadline after first answer."""
    import random
    center = random.choice(RPS)
    return {"center": center, "start_ns": monotonic_ns(), "first_ns": None, "deadline_ns": None, "responses": {}}

def start_game(db: Dict[str, Any], uid1: str, uid2: str) -> str:
    """Create live game with differential scoring."""
    gid = secure_uuid()
    db["games"][gid] = {"players": [uid1, uid2], "round": 1, "score": 0, "state": new_round_state(), "last_result": None, "winner": None}
    save_db(db)
    return gid

def user_in_game(db: Dict[str, Any], uid: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Find a game containing uid."""
    for gid, g in db["games"].items():
        if uid in g.get("players", []):
            return gid, g
    return None, None

def enqueue_or_match(db: Dict[str, Any], uid: str) -> Optional[str]:
    """Simple matchmaking. Return gid if matched now else None."""
    others = [u for u in db["queues"] if u != uid]
    if others:
        opp = others[0]
        db["queues"] = [u for u in db["queues"] if u not in (uid, opp)]
        gid = start_game(db, uid, opp)
        return gid
    if uid not in db["queues"]:
        db["queues"].append(uid)
        save_db(db)
    return None

def send_invite(db: Dict[str, Any], from_uid: str, to_username: str) -> None:
    """Send a friend invite (receiver accepts in-app)."""
    db["invites"].append({"from": from_uid, "to_username": to_username, "ts": int(monotonic_ns()//1_000_000_000)})
    save_db(db)

def accept_invite(db: Dict[str, Any], invite: Dict[str, Any], my_uid: str) -> str:
    """Accept invite and start a game; removes invite."""
    gid = start_game(db, invite["from"], my_uid)
    db["invites"] = [i for i in db["invites"] if i is not invite]
    save_db(db)
    return gid

def _resolve_round(db: Dict[str, Any], gid: str) -> None:
    """Resolve current round using fastest responder vs center; update score and logs; end at 5-lead."""
    g = db["games"].get(gid)
    if not g or g.get("winner"):
        return
    stt = g["state"]
    if len(stt["responses"]) == 0:
        return
    items = sorted(stt["responses"].items(), key=lambda x: x[1]["ns"])
    fast_uid, fast = items[0]
    slow_uid = [u for u in g["players"] if u != fast_uid][0]
    center = stt["center"]
    fast_choice = fast["choice"]
    fast_wins = (fast_choice, center) in WINS

    p0, p1 = g["players"]
    delta = +1 if (fast_uid == p0 and fast_wins) or (fast_uid == p1 and not fast_wins) else -1
    g["score"] += delta

    res_fast = "win" if fast_wins else "lose"
    res_slow = "lose" if fast_wins else "win"

    for who_uid, who_choice, who_ns, res in [
        (fast_uid, fast_choice, fast["ns"], res_fast),
        (slow_uid, stt["responses"].get(slow_uid, {}).get("choice"), stt["responses"].get(slow_uid, {}).get("ns", stt["start_ns"]), res_slow),
    ]:
        ensure_user_logs(db, who_uid)
        ms = int((who_ns - stt["start_ns"]) / 1_000_000)
        db["game_logs"][who_uid].append({
            "game_id": gid, "round": g["round"], "center": center,
            "choice": who_choice, "ms": ms, "result": res, "ts": int(monotonic_ns() // 1_000_000)
        })

    if abs(g["score"]) >= 5:
        g["winner"] = p0 if g["score"] > 0 else p1
        g["last_result"] = {"round": g["round"], "center": center, "fast_uid": fast_uid, "fast_choice": fast_choice, "fast_wins": fast_wins}
        save_db(db)
        return

    g["round"] += 1
    g["last_result"] = {"round": g["round"]-1, "center": center, "fast_uid": fast_uid, "fast_choice": fast_choice, "fast_wins": fast_wins}
    g["state"] = new_round_state()
    save_db(db)

def post_response(db: Dict[str, Any], gid: str, uid: str, choice: str) -> Tuple[bool, str]:
    """Store user's answer and set 3s deadline; resolve when due or both answered. Returns confirmation."""
    g = db["games"].get(gid)
    if not g or g.get("winner"):
        return False, "Game not found or finished."
    if uid not in g["players"]:
        return False, "Not a player."

    stt = g["state"]
    center = stt["center"]
    valid_opts = other_two(center)
    if choice not in valid_opts:
        return False, "Invalid choice."

    if uid in stt["responses"]:
        return True, "Answer already recorded."

    now = monotonic_ns()
    stt["responses"][uid] = {"choice": choice, "ns": now}
    if stt["first_ns"] is None:
        stt["first_ns"] = now
        stt["deadline_ns"] = now + 3_000_000_000

    save_db(db)

    if len(stt["responses"]) == 2:
        _resolve_round(db, gid)
        return True, "Answer saved. Round resolved."
    else:
        return True, "Answer saved. Opponent has 3 seconds."

def resolve_if_due(db: Dict[str, Any], gid: str) -> None:
    """If first answer exists and deadline passed, resolve the round."""
    g = db["games"].get(gid)
    if not g or g.get("winner"):
        return
    stt = g["state"]
    if stt["first_ns"] is None or stt["deadline_ns"] is None:
        return
    if monotonic_ns() >= stt["deadline_ns"]:
        _resolve_round(db, gid)

def player_dataframe(db: Dict[str, Any], uid: str) -> pd.DataFrame:
    """Return last 500 logs as DataFrame for a player."""
    ensure_user_logs(db, uid)
    rows = db["game_logs"][uid][-500:]
    return pd.DataFrame(rows)

def current_score_for(db: Dict[str, Any], gid: str, perspective_uid: Optional[str]=None) -> Tuple[int,int]:
    """Convert differential score to (mine, theirs), perspective-aware."""
    g = db["games"][gid]
    diff = g["score"]
    mine = max(diff, 0)
    theirs = max(-diff, 0)
    if perspective_uid and g["players"][1] == perspective_uid:
        mine, theirs = theirs, mine
    return mine, theirs
