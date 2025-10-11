jj game

# File tree
# ├─ app.py # ASGI app (FastAPI + Starlette WS)
# ├─ db.py # tiny JSON “DB” (users, game_logs)
# ├─ matchmaking.py # queue + friend invites
# ├─ game.py # core game logic
# ├─ static/
# │ ├─ index.html # start menu (guest / login, play online / friend)
# │ ├─ online.html # online matchmaking screen
# │ └─ friend.html # invite/join by username
# └─ requirements.txt # fastapi, uvicorn



# -----------------------------
# Run
# -----------------------------
# 1) python -m venv .venv && . .venv/bin/activate
# 2) pip install -r requirements.txt
# 3) uvicorn app:app --reload --host 0.0.0.0 --port 8000
# Deploy: fly.io / railway render as a standard ASGI app.

.\.venv\Scripts\activate
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
