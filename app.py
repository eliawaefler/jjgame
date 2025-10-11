
import streamlit as st
import pandas as pd

from helpers import (
    load_db, register_user, login_user, send_invite, accept_invite,
    enqueue_or_match, user_in_game, post_response, resolve_if_due,
    other_two, player_dataframe, current_score_for
)

st.set_page_config(page_title="RPS × Kahoot — Live", page_icon="⚡", layout="centered")

if "uid" not in st.session_state:
    st.session_state.uid = None
if "username" not in st.session_state:
    st.session_state.username = None

db = load_db()

st.title("RPS × Kahoot — Live MVP")
st.caption("Live: 3s-Deadline nach erster Antwort. 5-Punkte-Vorsprung = Sieg. Antworten werden bestätigt.")

# -------- Auth --------
if st.session_state.uid is None:
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("### Login")
        li_user = st.text_input("Username", key="li_u")
        li_pw = st.text_input("Password", type="password", key="li_p")
        if st.button("Login"):
            uid, err = login_user(db, li_user, li_pw)
            if err: st.error(err)
            else:
                st.session_state.uid = uid; st.session_state.username = li_user; st.rerun()
    with c2:
        st.markdown("### Register")
        re_user = st.text_input("New username", key="re_u")
        re_pw = st.text_input("New password", type="password", key="re_p")
        if st.button("Create account"):
            uid, err = register_user(db, re_user, re_pw)
            if err: st.error(err)
            else: st.success("Account created. Please login.")
    with c3:
        st.markdown("### Gast")
        if st.button("Play as guest"):
            import uuid
            uname = f"guest_{str(uuid.uuid4())[:8]}"
            uid, _ = register_user(db, uname, "")
            st.session_state.uid = uid; st.session_state.username = uname; st.rerun()
    st.stop()

page = st.sidebar.radio("Menü", ["Home", "Play online", "Play friend", "Analyse", "Logout"])

if page == "Logout":
    st.session_state.uid = None
    st.session_state.username = None
    st.experimental_rerun()

st.caption(f"Angemeldet als **{st.session_state.username}**")

# Invites
db = load_db()
my_invites = [inv for inv in db["invites"] if inv["to_username"] == st.session_state.username]
if my_invites:
    st.info(f"Offene Einladungen: {len(my_invites)}")
    for inv in list(my_invites):
        c1, c2 = st.columns([3,1])
        with c1: st.write(f"Einladung von UID **{inv['from']}**")
        with c2:
            if st.button("Annehmen", key=f"acc_{inv['from']}"):
                accept_invite(db, inv, st.session_state.uid)
                st.success("Match gestartet.")
                st.rerun()

if page == "Home":
    st.subheader("Startmenü")
    st.write("- **Play online**: Queue & Auto-Match")
    st.write("- **Play friend**: Freund per Username")
    st.write("- **Analyse**: Antwortzeiten & Resultate")
    st.stop()

if page == "Play online":
    gid, g = user_in_game(db, st.session_state.uid)
    if gid is None:
        st.write("Nicht im Spiel. Matchmaking:")
        if st.button("🔎 Find Match"):
            gid = enqueue_or_match(load_db(), st.session_state.uid)
            if gid: st.success("Match gefunden!")
            else: st.info("Warte auf Gegner… Seite offen lassen.")
            st.rerun()
        st.caption(f"Warteschlange: {len(load_db()['queues'])}")
        st.stop()

    # Deadline check + refresh
    resolve_if_due(load_db(), gid)
    db = load_db()
    gid, g = user_in_game(db, st.session_state.uid)

    st.subheader(f"Im Spiel — Runde {g['round']}")
    st.caption(f"Game-ID: {gid}")

    mine, theirs = current_score_for(db, gid, st.session_state.uid)
    sc1, sc2 = st.columns(2)
    sc1.metric("Dein Score", mine)
    sc2.metric("Gegner Score", theirs)
    if g.get("winner"):
        st.success("Spiel vorbei! " + ("🏆 Du hast gewonnen." if g["winner"]==st.session_state.uid else "Du hast verloren."))
        st.stop()

    st.markdown("**Oben angezeigt:**")
    center = g["state"]["center"]
    st.markdown(f"# {center}")
    opts = other_two(center)

    answered = st.session_state.uid in g["state"]["responses"]
    if answered:
        st.info("✅ Antwort gespeichert. Gegner hat 3s Zeit.")
    else:
        c1, c2 = st.columns(2)
        if c1.button(opts[0], use_container_width=True):
            ok, msg = post_response(load_db(), gid, st.session_state.uid, opts[0])
            st.toast(msg); st.rerun()
        if c2.button(opts[1], use_container_width=True):
            ok, msg = post_response(load_db(), gid, st.session_state.uid, opts[1])
            st.toast(msg); st.rerun()

    st.caption("Live-Spiel: Runde endet spätestens 3s nach erster Antwort (Auto-Weiter).")

elif page == "Play friend":
    st.subheader("Freund einladen")
    to_user = st.text_input("Freundes-Username")
    if st.button("Einladung senden"):
        send_invite(load_db(), st.session_state.uid, to_user)
        st.success("Einladung gesendet.")
    st.info("Freund muss eingeloggt sein und im Home annehmen.")

elif page == "Analyse":
    st.subheader("Deine Stats")
    df = player_dataframe(load_db(), st.session_state.uid)
    if df.empty:
        st.write("Noch keine Daten.")
    else:
        st.dataframe(df)
        if "result" in df and not df.empty:
            winrate = (df["result"]=="win").mean()*100
            st.metric("Winrate", f"{winrate:.1f}%")
        if "ms" in df and not df["ms"].empty:
            st.metric("Ø Antwortzeit (ms)", f"{df['ms'].mean():.0f}")
            st.metric("Median Antwortzeit (ms)", f"{df['ms'].median():.0f}")
            st.bar_chart(df["ms"])
