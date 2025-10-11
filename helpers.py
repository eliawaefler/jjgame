"""
# helpers.py
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
import pandas as pd

from utils import atomic_write_json, read_json, secure_uuid, monotonic_ns, now_ms_epoch

DB_PATH = Path("db.json")

INIT: Dict[str, Any] = {
    "users": {},          # username -> {"password": "...", "id": "..."}
    "queues": [],         # [uid]
    "invites": [],        # [{"from": uid, "to_username": str, "ts_ms": int}]
    "live_games": {},     # gid -> {... live game state ...}
    "game_logs": {},      # uid -> [per-event logs]
    "archives": {}        # uid -> [finished game summaries]
}

RPS = ["R", "P", "S"]
WINS = {("R","S"), ("P","R"), ("S","P")}

# ---------------- DB ----------------

def load_db() -> Dict[str, Any]:
    """Load DB or create defaults; normalize keys defensively."""
    db = read_json(DB_PATH)
    if not db:
        db = INIT.copy()
        atomic_write_json(DB_PATH, db)
    # normalize
    for k, v in INIT.items():
        if k not in db:
            db[k] = v if not isinstance(v, dict) else v.copy()
    return db

def save_db(db: Dict[str, Any]) -> None:
    """Persist DB to disk atomically."""
    atomic_write_json(DB_PATH, db)

def ensure_user_logs(db: Dict[str, Any], uid: str) -> None:
    """Ensure per-user game_logs and archives exist."""
    if uid not in db["game_logs"]:
        db["game_logs"][uid] = []
    if uid not in db["archives"]:
        db["archives"][uid] = []

# ---------------- Auth ----------------

def register_user(db: Dict[str, Any], username: str, password: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Register user (MVP: plain password). Returns (uid, err).
    Security: validate username length; no streamlit dependency.
    """
    if not username or len(username) > 64:
        return None, "Invalid username."
    if username in db["users"]:
        return None, "Username already exists."
    uid = secure_uuid()
    db["users"][username] = {"password": password, "id": uid, "last_seen_ns": 0, "page": "Home"}
    ensure_user_logs(db, uid)
    save_db(db)
    return uid, None

def login_user(db: Dict[str, Any], username: str, password: str) -> Tuple[Optional[str], Optional[str]]:
    """Validate credentials; return (uid, err)."""
    u = db["users"].get(username)
    if not u or u.get("password") != password:
        return None, "Invalid credentials."
    ensure_user_logs(db, u["id"])
    return u["id"], None

# ------------- Heartbeat / Presence -------------

def heartbeat(db: Dict[str, Any], uid: str, page: str, gid: Optional[str]) -> None:
    """
    Update presence for user.
    Stores: last_seen_ns (monotonic), page (Home/LiveGame/Analyse/etc), current_gid (optional).
    """
    # reverse lookup username -> user obj doesn't matter; we store by username map, but we need to find the entry.
    # Build uid->ref index quickly:
    for name, rec in db["users"].items():
        if rec.get("id") == uid:
            rec["last_seen_ns"] = monotonic_ns()
            rec["page"] = page
            rec["gid"] = gid
            break
    save_db(db)

def is_user_active(db: Dict[str, Any], uid: str, within_ns: int, require_page: Optional[str]=None, gid: Optional[str]=None) -> bool:
    """
    Check if user sent heartbeat within the given window and (optionally) is on a required page and game.
    """
    for rec in db["users"].values():
        if rec.get("id") == uid:
            ls = rec.get("last_seen_ns", 0)
            if monotonic_ns() - ls > within_ns:
                return False
            if require_page and rec.get("page") != require_page:
                return False
            if gid is not None and rec.get("gid") != gid:
                return False
            return True
    return False

# ------------- Game Core -------------

def other_two(center: str) -> List[str]:
    """Return two symbols different from center."""
    return [x for x in RPS if x != center]

def new_round_state() -> Dict[str, Any]:
    """Fresh round; center symbol; timing and responses dict."""
    import random
    center = random.choice(RPS)
    return {"center": center, "start_ns": monotonic_ns(), "first_ns": None, "deadline_ns": None, "responses": {}}

def start_game(db: Dict[str, Any], uid1: str, uid2: str) -> str:
    """
    Create a live game between uid1 and uid2. Differential scoring; 5-lead wins.
    Returns game id.
    """
    gid = secure_uuid()
    db["live_games"][gid] = {
        "players": [uid1, uid2],
        "round": 1,
        "score": 0,               # differential (+ means players[0] leads)
        "state": new_round_state(),
        "last_result": None,
        "winner": None,
        "created_ms": now_ms_epoch()
    }
    save_db(db)
    return gid

def user_live_game(db: Dict[str, Any], uid: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Find live game the user is in."""
    for gid, g in db["live_games"].items():
        if uid in g.get("players", []):
            return gid, g
    return None, None

def enqueue_or_match(db: Dict[str, Any], uid: str) -> Optional[str]:
    """Simple queue matchmaking; returns gid if matched now else None."""
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
    """Send friend invite; delivery is in-app list for the receiver to accept."""
    db["invites"].append({"from": from_uid, "to_username": to_username, "ts_ms": now_ms_epoch()})
    save_db(db)

def accept_invite(db: Dict[str, Any], invite: Dict[str, Any], my_uid: str) -> str:
    """Accept invite -> start live game; remove invite entry."""
    gid = start_game(db, invite["from"], my_uid)
    db["invites"] = [i for i in db["invites"] if i is not invite]
    save_db(db)
    return gid

# ------------- Resolution / Posting / Forfeit -------------

def _archive_and_close(db: Dict[str, Any], gid: str) -> None:
    """Move a finished live game to each player's archive; remove from live_games."""
    g = db["live_games"].get(gid)
    if not g:
        return
    p0, p1 = g["players"]
    summary = {
        "game_id": gid,
        "created_ms": g.get("created_ms"),
        "finished_ms": now_ms_epoch(),
        "final_score_diff": g.get("score", 0),
        "winner": g.get("winner"),
        "rounds": g.get("round", 0)
    }
    for uid in [p0, p1]:
        ensure_user_logs(db, uid)
        db["archives"][uid].append(summary.copy())
    # remove from live
    db["live_games"].pop(gid, None)
    save_db(db)

def _resolve_round(db: Dict[str, Any], gid: str) -> None:
    """Resolve current round by fastest responder vs center; update score; end on 5-lead; next round otherwise."""
    g = db["live_games"].get(gid)
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

    # logs
    for who_uid, who_choice, who_ns, res in [
        (fast_uid, fast_choice, fast["ns"], "win" if fast_wins else "lose"),
        (slow_uid, stt["responses"].get(slow_uid, {}).get("choice"),
         stt["responses"].get(slow_uid, {}).get("ns", stt["start_ns"]),
         "lose" if fast_wins else "win"),
    ]:
        ensure_user_logs(db, who_uid)
        ms = int((who_ns - stt["start_ns"]) / 1_000_000)
        db["game_logs"][who_uid].append({
            "game_id": gid, "round": g["round"], "center": center,
            "choice": who_choice, "ms": ms, "result": res, "ts_ms": now_ms_epoch()
        })

    # check win by 5-lead
    if abs(g["score"]) >= 5:
        g["winner"] = p0 if g["score"] > 0 else p1
        g["last_result"] = {"round": g["round"], "center": center, "fast_uid": fast_uid, "fast_choice": fast_choice, "fast_wins": fast_wins}
        save_db(db)
        _archive_and_close(db, gid)
        return

    g["round"] += 1
    g["last_result"] = {"round": g["round"]-1, "center": center, "fast_uid": fast_uid, "fast_choice": fast_choice, "fast_wins": fast_wins}
    g["state"] = new_round_state()
    save_db(db)

def post_response(db: Dict[str, Any], gid: str, uid: str, choice: str) -> Tuple[bool, str]:
    """
    Store user's answer; return immediate confirmation.
    Starts 3s deadline after first answer; resolves on two answers or deadline.
    """
    g = db["live_games"].get(gid)
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
        stt["deadline_ns"] = now + 3_000_000_000  # 3s

    save_db(db)  # confirm

    if len(stt["responses"]) == 2:
        _resolve_round(db, gid)
        return True, "Answer saved. Round resolved."
    return True, "Answer saved. Opponent has 3 seconds."

def resolve_due_or_forfeit(db: Dict[str, Any], gid: str) -> None:
    """
    Resolve round if deadline passed OR apply forfeit if a player missed 3 heartbeats
    or is not in LiveGame view for this gid.
    """
    g = db["live_games"].get(gid)
    if not g or g.get("winner"):
        return
    # deadline-based resolution
    stt = g["state"]
    if stt.get("first_ns") and stt.get("deadline_ns") and monotonic_ns() >= stt["deadline_ns"]:
        _resolve_round(db, gid)
        return

    # forfeit check: 3 missed heartbeats (~3 * 3s = 9s window) AND not on LiveGame
    hb_window_ns = 3 * 3_000_000_000  # 9s
    p0, p1 = g["players"]
    p0_active = is_user_active(db, p0, hb_window_ns, require_page="LiveGame", gid=gid)
    p1_active = is_user_active(db, p1, hb_window_ns, require_page="LiveGame", gid=gid)
    if p0_active and not p1_active:
        g["winner"] = p0
        save_db(db)
        _archive_and_close(db, gid)
    elif p1_active and not p0_active:
        g["winner"] = p1
        save_db(db)
        _archive_and_close(db, gid)

def give_up(db: Dict[str, Any], gid: str, uid: str) -> Tuple[bool, str]:
    """Player concedes immediately; opponent wins; archive and close."""
    g = db["live_games"].get(gid)
    if not g or g.get("winner"):
        return False, "Game not found or already finished."
    if uid not in g["players"]:
        return False, "Not a player."
    p0, p1 = g["players"]
    opp = p1 if uid == p0 else p0
    g["winner"] = opp
    save_db(db)
    _archive_and_close(db, gid)
    return True, "You gave up. Game ended."

# ------------- Analytics -------------

def player_dataframe(db: Dict[str, Any], uid: str) -> pd.DataFrame:
    """Return last 500 log rows as DataFrame for a user."""
    ensure_user_logs(db, uid)
    rows = db["game_logs"][uid][-500:]
    return pd.DataFrame(rows)

def archives_dataframe(db: Dict[str, Any], uid: str) -> pd.DataFrame:
    """Return archived finished games for a user."""
    ensure_user_logs(db, uid)
    rows = db["archives"][uid][-200:]
    return pd.DataFrame(rows)

def current_score_for(db: Dict[str, Any], gid: str, perspective_uid: Optional[str]=None) -> Tuple[int,int]:
    """
    From differential score produce (mine, theirs) in user's perspective.
    Example: diff=+2 (players[0] leads) => for players[0]: (2,0); for players[1]: (0,2).
    """
    g = db["live_games"][gid]
    diff = g["score"]
    mine = max(diff, 0)
    theirs = max(-diff, 0)
    if perspective_uid and g["players"][1] == perspective_uid:
        mine, theirs = theirs, mine
    return mine, theirs
