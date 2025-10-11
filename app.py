
import streamlit as st
import json, time, random, uuid
from pathlib import Path

DB_PATH = Path("db.json")

INIT = {
    "users": {},                 # username -> {"password": "...", "id": "..."} (password in plain for MVP only)
    "queues": [],                # list of user_ids waiting for online match
    "invites": [],               # list of {"from": uid, "to_username": str, "ts": int}
    "games": {},                 # game_id -> {"players":[uid,uid], "round":0, "state": {"center": "", "start_ns": 0, "responses": {} }}
    "game_logs": {}              # uid -> [ {game_id, round, center, choice, ms, result, ts} ]
}

# ------- DB helpers (naive, file-level lock by write) --------
def load_db():
    if not DB_PATH.exists():
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump(INIT, f)
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(db):
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def ensure_user_logs(db, uid):
    if uid not in db["game_logs"]:
        db["game_logs"][uid] = []

# ------------- Auth -------------
def do_register(db, username, password):
    if username in db["users"]:
        return None, "Username already exists."
    uid = str(uuid.uuid4())
    db["users"][username] = {"password": password, "id": uid}
    ensure_user_logs(db, uid)
    save_db(db)
    return uid, None

def do_login(db, username, password):
    user = db["users"].get(username)
    if not user or user["password"] != password:
        return None, "Invalid credentials."
    ensure_user_logs(db, user["id"])
    return user["id"], None

# ------------- Game Logic -------------
RPS = ["R", "P", "S"]
WINS = {("R","S"), ("P","R"), ("S","P")}  # (attacker, defender) means attacker beats defender

def other_two(center):
    return [x for x in RPS if x != center]

def new_round_state():
    center = random.choice(RPS)
    return {"center": center, "start_ns": time.time_ns(), "responses": {}}

def start_game(db, uid1, uid2):
    gid = str(uuid.uuid4())
    db["games"][gid] = {"players": [uid1, uid2], "round": 1, "state": new_round_state()}
    save_db(db)
    return gid

def find_match(db, me):
    # If someone else is in queue, match them
    others = [u for u in db["queues"] if u != me]
    if others:
        opp = others[0]
        # remove both from queue
        db["queues"] = [u for u in db["queues"] if u not in (me, opp)]
        gid = start_game(db, me, opp)
        return gid
    # else add me to queue (if not already)
    if me not in db["queues"]:
        db["queues"].append(me)
        save_db(db)
    return None

def post_response(db, gid, uid, choice):
    game = db["games"].get(gid)
    if not game:
        return "Game not found"
    stt = game["state"]
    if uid in stt["responses"]:
        return "Already answered"
    now_ns = time.time_ns()
    stt["responses"][uid] = {"choice": choice, "ns": now_ns}
    save_db(db)
    # try resolve
    if len(stt["responses"]) == 2:
        # pick fastest
        items = list(stt["responses"].items())  # [(uid, {choice, ns}), ...]
        items.sort(key=lambda x: x[1]["ns"])
        fast_uid, fast = items[0]
        slow_uid, slow = items[1]
        center = stt["center"]
        # Evaluate: If fast picks the losing option vs center, fast loses; if winning option, fast wins.
        # Losing per spec: center beats one option and loses to the other.
        # Derive: If (fast_choice, center) in WINS => fast beats center -> fast WINS.
        # Else fast loses.
        fast_choice = fast["choice"]
        fast_win = (fast_choice, center) in WINS
        result_fast = "win" if fast_win else "lose"
        result_slow = "lose" if fast_win else "win"
        # logs
        for who_uid, who, res in [(fast_uid, fast, result_fast), (slow_uid, slow, result_slow)]:
            ms = int((who["ns"] - stt["start_ns"]) / 1_000_000)
            ensure_user_logs(db, who_uid)
            db["game_logs"][who_uid].append({
                "game_id": gid,
                "round": game["round"],
                "center": center,
                "choice": who["choice"],
                "ms": ms,
                "result": res,
                "ts": int(time.time())
            })
        # next round
        game["round"] += 1
        game["state"] = new_round_state()
        save_db(db)
    return None

def in_game_of(db, uid):
    for gid, g in db["games"].items():
        if uid in g["players"]:
            return gid, g
    return None, None

# ------------- UI -------------
st.set_page_config(page_title="RPS-Kahoot MVP", page_icon="✊", layout="centered")

if "uid" not in st.session_state:
    st.session_state.uid = None
if "username" not in st.session_state:
    st.session_state.username = None

db = load_db()

st.title("RPS × Kahoot — MVP")

# Auth area
if st.session_state.uid is None:
    st.subheader("Login / Gast")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**Login**")
        li_user = st.text_input("Username", key="li_u")
        li_pw = st.text_input("Password", type="password", key="li_p")
        st.warning("MOCK PW only, it is PLAINTEXT!!, secure lgin will be implementet late!!!")
        if st.button("Login"):
            uid, err = do_login(db, li_user, li_pw)
            if err:
                st.error(err)
            else:
                st.session_state.uid = uid
                st.session_state.username = li_user
                st.rerun()
    with col2:
        st.markdown("**Register**")
        re_user = st.text_input("Neuer Username", key="re_u")
        re_pw = st.text_input("Neues Passwort", type="password", key="re_p")
        if st.button("Create account"):
            uid, err = do_register(db, re_user, re_pw)
            if err:
                st.error(err)
            else:
                st.success("Account erstellt. Bitte einloggen.")
    with col3:
        st.markdown("**Gast**")
        if st.button("Play as guest"):
            guest_name = f"guest_{str(uuid.uuid4())[:8]}"
            uid, _ = do_register(db, guest_name, "")
            st.session_state.uid = uid
            st.session_state.username = guest_name
            st.rerun()
    st.stop()

# Sidebar menu
page = st.sidebar.radio("Menü", ["Home", "Play online", "Play friend", "Analyse", "Logout"])

if page == "Logout":
    st.session_state.uid = None
    st.session_state.username = None
    st.rerun()

st.caption(f"Angemeldet als **{st.session_state.username}**")

# Invites panel
my_invites = [inv for inv in db["invites"] if inv["to_username"] == st.session_state.username]
if my_invites:
    st.info(f"Offene Einladungen: {len(my_invites)}")
    for inv in my_invites:
        colA, colB = st.columns([3,1])
        with colA:
            st.write(f"Einladung von **{inv['from']}** (UID), an {inv['to_username']}")
        with colB:
            if st.button("Annehmen", key=f"acc_{inv['from']}"):
                gid = start_game(db, inv["from"], st.session_state.uid)
                db = load_db()  # refresh
                # remove the invite
                db["invites"] = [i for i in db["invites"] if i is not inv]
                save_db(db)
                st.success("Match gestartet.")
                st.rerun()

# Page: Home
if page == "Home":
    st.subheader("Startmenü")
    st.write("- **Play online**: schnelles Matchmaking")
    st.write("- **Play friend**: Freund via Username einladen")
    st.write("- **Analyse**: Stats & Antwortzeiten")

# Page: Play online
if page == "Play online":
    gid, g = in_game_of(db, st.session_state.uid)
    if gid is None:
        st.write("Nicht im Spiel. Matchmaking starten:")
        if st.button("🔎 Find Match"):
            db = load_db()
            gid = find_match(db, st.session_state.uid)
            if gid:
                st.success("Match gefunden!")
            else:
                st.info("Warte auf Gegner… (lass die Seite offen)")
            st.rerun()
        waiters = len(db["queues"])
        st.caption(f"Warteschlange: {waiters}")
        st.stop()
    # in game
    st.subheader(f"Im Spiel — Runde {g['round']}")
    st.caption(f"Game-ID: {gid}")
    st.divider()
    st.markdown("**Oben angezeigt:**")
    center = g["state"]["center"]
    st.markdown(f"# {center}")
    opts = other_two(center)
    st.markdown("**Deine Optionen:**")
    c1, c2 = st.columns(2)
    if c1.button(opts[0], use_container_width=True):
        db = load_db()
        err = post_response(db, gid, st.session_state.uid, opts[0])
        if err: st.error(err)
        st.rerun()
    if c2.button(opts[1], use_container_width=True):
        db = load_db()
        err = post_response(db, gid, st.session_state.uid, opts[1])
        if err: st.error(err)
        st.rerun()
    st.caption("Ergebnis erscheint automatisch nach beiden Antworten; nächste Runde startet direkt.")

# Page: Play friend
elif page == "Play friend":
    st.subheader("Freund einladen")
    to_user = st.text_input("Freundes-Username")
    if st.button("Einladung senden"):
        db = load_db()
        db["invites"].append({"from": st.session_state.uid, "to_username": to_user, "ts": int(time.time())})
        save_db(db)
        st.success("Einladung gesendet.")
    st.info("Der Freund muss eingeloggt sein und die Einladung im Home-Bereich annehmen.")

# Page: Analyse
elif page == "Analyse":
    st.subheader("Deine Stats")
    db = load_db()
    ensure_user_logs(db, st.session_state.uid)
    logs = db["game_logs"][st.session_state.uid][-200:]
    if not logs:
        st.write("Noch keine Daten.")
    else:
        import pandas as pd
        df = pd.DataFrame(logs)
        st.dataframe(df)
        winrate = (df["result"]=="win").mean()*100
        st.metric("Winrate", f"{winrate:.1f}%")
        st.metric("Ø Antwortzeit (ms)", f"{df['ms'].mean():.0f}")
        st.metric("Median Antwortzeit (ms)", f"{df['ms'].median():.0f}")
        st.bar_chart(df["ms"])
