
# -----------------------------
# app.py
# -----------------------------
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from typing import Any, Dict
import asyncio, json, time

import db
from matchmaking import MM, Waiter
from game import new_round, evaluate, WIN_AGAINST

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

db.ensure_db()

@app.get("/")
def root():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.post("/signup")
async def signup(username: str = Query(...), password: str = Query(...)):
    uid = db.create_user(username, password)
    if not uid:
        return {"ok": False, "error": "username_taken"}
    return {"ok": True, "user_id": uid}

@app.post("/login")
async def login(username: str = Query(...), password: str = Query(...)):
    return {"ok": db.auth(username, password), "user_id": username}

@app.post("/guest")
async def guest():
    return {"ok": True, "user_id": db.create_guest()}

@app.get("/logs")
async def logs(user_id: str):
    return {"ok": True, "logs": db.get_logs(user_id)}

# -------------- WebSockets: Online Queue --------------
@app.get("/online")
async def online_page():
    with open("static/online.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.websocket("/ws/online")
async def ws_online(ws: WebSocket):
    await ws.accept()
    payload = json.loads(await ws.receive_text())
    user_id = payload.get("user_id") or db.create_guest()
    me = Waiter(user_id=user_id, websocket=ws)

    # Try match immediately
    other = await MM.enqueue_online(me)
    if other is None:
        await ws.send_json({"type": "queued", "user_id": user_id})
        try:
            # wait until disconnected or matched (handled by when someone else joins)
            while True:
                await asyncio.sleep(1)
        except WebSocketDisconnect:
            await MM.cancel_online(me)
            return
    else:
        # I matched someone already waiting
        await run_game_pair(other.websocket, ws, other.user_id, user_id)

# When a queued player gets matched by another connection, we re-use run_game_pair
# by having the second handler call it with (ws_waiter, ws_new)

async def run_game_pair(wsA: WebSocket, wsB: WebSocket, userA: str, userB: str):
    game_id = f"g-{int(time.time()*1000)}"
    # announce match
    for ws, uid, peer in ((wsA, userA, userB), (wsB, userB, userA)):
        await ws.send_json({"type": "matched", "game_id": game_id, "you": uid, "peer": peer})

    # single round MVP
    prompt = new_round()
    for ws in (wsA, wsB):
        await ws.send_json({
            "type": "round",
            "prompt": prompt,
            "choices": [c for c in ["R","P","S"] if c != prompt]
        })

    decided = False
    start_ts = time.time()

    async def listen(ws: WebSocket, uid: str):
        nonlocal decided
        try:
            msg = await ws.receive_text()
        except WebSocketDisconnect:
            return None
        if decided:
            return None
        try:
            data = json.loads(msg)
        except Exception:
            return None
        if data.get("type") != "choice":
            return None
        choice = data.get("choice")
        rt = time.time() - start_ts
        res = evaluate(prompt, choice)
        decided = True
        return {"uid": uid, "choice": choice, "result": res, "rt": rt}

    done, pending = await asyncio.wait(
        {asyncio.create_task(listen(wsA, userA)), asyncio.create_task(listen(wsB, userB))},
        return_when=asyncio.FIRST_COMPLETED,
        timeout=10.0,
    )

    if not done:
        # timeout: no one answered
        for ws in (wsA, wsB):
            await ws.send_json({"type": "timeout"})
        return

    winner_payload = list(done)[0].result()
    if winner_payload is None:
        for ws in (wsA, wsB):
            await ws.send_json({"type": "aborted"})
        return

    uid = winner_payload["uid"]
    res = winner_payload["result"]  # "win" or "lose" from the clicker POV
    rt = winner_payload["rt"]

    # Determine winner/loser ids
    if res == "win":
        winner, loser = uid, (userB if uid == userA else userA)
    else:
        loser, winner = uid, (userB if uid == userA else userA)

    # Persist logs (per user)
    for who, outcome in ((winner, "win"), (loser, "lose")):
        db.append_log(who, {
            "game_id": game_id,
            "prompt": prompt,
            "winner_choice": WIN_AGAINST[prompt],
            "decider": uid,
            "your_outcome": outcome,
            "rt": rt if who == uid else None,
            "ts": time.time(),
        })

    # Notify clients
    try:
        await wsA.send_json({"type": "result", "winner": winner, "loser": loser, "prompt": prompt})
        await wsB.send_json({"type": "result", "winner": winner, "loser": loser, "prompt": prompt})
    except:
        pass

# -------------- (Optional) friend mode minimal REST --------------
@app.get("/friend")
async def friend_page():
    with open("static/friend.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.websocket("/ws/friend")
async def ws_friend(ws: WebSocket):
    await ws.accept()
    data = json.loads(await ws.receive_text())
    user_id = data.get("user_id") or db.create_guest()
    mode = data.get("mode")  # "offer" or "accept"
    if mode == "offer":
        await MM.friend_offer(Waiter(user_id=user_id, websocket=ws))
        await ws.send_json({"type": "waiting", "user_id": user_id})
        # park connection
        while True:
            await asyncio.sleep(1)
    elif mode == "accept":
        target = data.get("target_id")
        other = await MM.friend_accept(target)
        if not other:
            await ws.send_json({"type": "not_found"})
            return
        await run_game_pair(other.websocket, ws, other.user_id, user_id)
