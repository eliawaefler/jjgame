# asgi.py (keep this name)
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def ok(): return {"ok": True}
