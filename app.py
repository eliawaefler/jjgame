
import streamlit as st
import pandas as pd

from helpers import *

st.set_page_config(page_title="RPS × Kahoot — Live", page_icon="⚡", layout="centered")

# ---------------- Session ----------------
if "uid" not in st.session_state: st.session_state.uid = None
if "username" not in st.session_state: st.session_state.username = None
if "view" not in st.session_state: st.session_state.view = "Home"  # Home | LiveGame | Analyse | Friend | Login
if "gid" not in st.session_state: st.session_state.gid = None

def rerun():
    st.rerun()

db = load_db()

st.title("RPS × Kahoot — Live")
st.caption("Live: Antworten bestätigen, 3s-Deadline, Heartbeat-Checks, 5-Punkte-Vorsprung gewinnt.")

# ---------------- Auth ----------------
if st.session_state.uid is None:
    st.subheader("Login / Register / Gast")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Login**")
        li_user = st.text_input("Username", key="li_u")
        li_pw = st.text_input("Password", type="password", key="li_p")
        if st.button("Login"):
            uid, err = login_user(db, li_user, li_pw)
            if err: st.error(err)
            else:
                st.session_state.uid = uid
                st.session_state.username = li_user
                st.session_state.view = "Home"
                rerun()
    with c2:
        st.markdown("**Register**")
        re_user = st.text_input("New username", key="re_u")
        re_pw = st.text_input("New password", type="password", key="re_p")
        if st.button("Create account"):
            uid, err = register_user(db, re_user, re_pw)
            if err: st.error(err)
            else: st.success("Account created. Login now.")
    with c3:
        st.markdown("**Gast**")
        if st.button("Play as guest"):
            import uuid
            uname = f"guest_{str(uuid.uuid4())[:8]}"
            uid, _ = register_user(db, uname, "")
            st.session_state.uid = uid
            st.session_state.username = uname
            st.session_state.view = "Home"
            rerun()
    st.stop()

# Heartbeat every render
heartbeat(load_db(), st.session_state.uid, st.session_state.view, st.session_state.gid)

# ---------------- Home (interactive menu, no sidebar) ----------------
def home():
    st.subheader("Startmenü")
    b1, b2, b3, b4 = st.columns(4)
    if b1.button("Play online", use_container_width=True):
        st.session_state.view = "LiveGame"
        # try to find/join game
        gid, g = user_live_game(load_db(), st.session_state.uid)
        if gid is None:
            gid = enqueue_or_match(load_db(), st.session_state.uid)
        st.session_state.gid = gid
        rerun()
    if b2.button("Play friend", use_container_width=True):
        st.session_state.view = "Friend"; rerun()
    if b3.button("Analyse", use_container_width=True):
        st.session_state.view = "Analyse"; rerun()
    if b4.button("Logout", use_container_width=True):
        st.session_state.uid = None
        st.session_state.username = None
        st.session_state.view = "Login"
        st.session_state.gid = None
        rerun()

    # Pending invites
    db = load_db()
    my_name = st.session_state.username
    invs = [i for i in db["invites"] if i["to_username"] == my_name]
    if invs:
        st.info(f"Offene Einladungen: {len(invs)}")
        for inv in list(invs):
            c1, c2 = st.columns([3,1])
            with c1: st.write(f"Einladung von UID **{inv['from']}**")
            with c2:
                if st.button("Annehmen", key=f"acc_{inv['from']}"):
                    gid = accept_invite(load_db(), inv, st.session_state.uid)
                    st.session_state.view = "LiveGame"
                    st.session_state.gid = gid
                    rerun()

def live_game():
    db = load_db()
    gid, g = user_live_game(db, st.session_state.uid)
    if gid is None:
        # maybe just matched?
        gid = st.session_state.gid
        if gid is None:
            st.info("Suche Gegner…")
            # Try again enqueue
            gid = enqueue_or_match(load_db(), st.session_state.uid)
            st.session_state.gid = gid
            st.button("Refresh", on_click=rerun)
            return
        else:
            # resolve forfeit/deadline and refresh view
            resolve_due_or_forfeit(load_db(), gid)
            db = load_db()
            gid, g = user_live_game(db, st.session_state.uid)
            if gid is None:
                st.info("Noch kein Spiel aktiv.")
                if st.button("Zurück zum Home"):
                    st.session_state.view = "Home"; st.session_state.gid = None; rerun()
                return

    # Ensure heartbeat marks this page + gid
    heartbeat(load_db(), st.session_state.uid, "LiveGame", gid)

    # Deadline/forfeit polling
    resolve_due_or_forfeit(load_db(), gid)
    db = load_db()
    gid, g = user_live_game(db, st.session_state.uid)
    if g is None:
        st.success("Spiel beendet (Archiviert).")
        if st.button("Zur Analyse"):
            st.session_state.view = "Analyse"; st.session_state.gid=None; rerun()
        if st.button("Zurück zum Home"):
            st.session_state.view = "Home"; rerun()
        return

    st.subheader(f"Im Spiel — Runde {g['round']}")
    st.caption(f"Game-ID: {gid}")
    p_mine, p_theirs = current_score_for(db, gid, st.session_state.uid)
    c1, c2, c3 = st.columns(3)
    c1.metric("Dein Score", p_mine)
    c2.metric("Gegner Score", p_theirs)

    if g.get("winner"):
        st.success("Spiel vorbei! " + ("🏆 Du hast gewonnen." if g["winner"]==st.session_state.uid else "Du hast verloren."))
        if st.button("Zurück zum Home"):
            st.session_state.view = "Home"; st.session_state.gid=None; rerun()
        return

    center = g["state"]["center"]
    st.markdown("**Oben angezeigt:**")
    st.markdown(f"# {center}")
    opts = other_two(center)

    answered = st.session_state.uid in g["state"]["responses"]
    if answered:
        st.info("✅ Antwort gespeichert. Gegner hat max. 3s.")
    else:
        b1, b2 = st.columns(2)
        if b1.button(opts[0], use_container_width=True):
            ok, msg = post_response(load_db(), gid, st.session_state.uid, opts[0]); st.toast(msg); rerun()
        if b2.button(opts[1], use_container_width=True):
            ok, msg = post_response(load_db(), gid, st.session_state.uid, opts[1]); st.toast(msg); rerun()

    st.write("")
    gup, ref = st.columns(2)
    if gup.button("Aufgeben"):
        ok, msg = give_up(load_db(), gid, st.session_state.uid)
        st.toast(msg); rerun()
    if ref.button("Refresh"):
        rerun()

def friend():
    st.subheader("Freund einladen")
    to_user = st.text_input("Freundes-Username")
    if st.button("Einladung senden"):
        send_invite(load_db(), st.session_state.uid, to_user)
        st.success("Einladung gesendet.")
    if st.button("Zurück"):
        st.session_state.view="Home"; st.session_state.gid=None; rerun()

def analyse():
    st.subheader("Deine Stats & Archive")
    df = player_dataframe(load_db(), st.session_state.uid)
    if df.empty:
        st.write("Noch keine Logs.")
    else:
        st.dataframe(df)
        if "result" in df and not df.empty:
            winrate = (df["result"]=="win").mean()*100
            st.metric("Winrate", f"{winrate:.1f}%")
        if "ms" in df and not df["ms"].empty:
            st.metric("Ø Antwortzeit (ms)", f"{df['ms'].mean():.0f}")
            st.metric("Median Antwortzeit (ms)", f"{df['ms'].median():.0f}")
            st.bar_chart(df["ms"])
    st.markdown("---")
    ar = archives_dataframe(load_db(), st.session_state.uid)
    st.write("**Archive**")
    if ar.empty:
        st.write("Noch keine beendeten Spiele.")
    else:
        st.dataframe(ar)
    if st.button("Zurück"):
        st.session_state.view="Home"; rerun()

# -------------- Router --------------
st.caption(f"Angemeldet als **{st.session_state.username}** — View: {st.session_state.view}")
if st.session_state.view == "Home":
    home()
elif st.session_state.view == "LiveGame":
    live_game()
elif st.session_state.view == "Friend":
    friend()
elif st.session_state.view == "Analyse":
    analyse()
else:
    st.session_state.view = "Home"; rerun()
