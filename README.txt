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