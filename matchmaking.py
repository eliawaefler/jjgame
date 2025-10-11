# -----------------------------
# matchmaking.py
# -----------------------------
import asyncio
from dataclasses import dataclass
from typing import Optional, Dict

@dataclass
class Waiter:
    user_id: str
    websocket: Any  # set at runtime

class Matchmaker:
    def __init__(self):
        self.queue: asyncio.Queue[Waiter] = asyncio.Queue(maxsize=1000)
        self.friend_wait: Dict[str, Waiter] = {}
        self.lock = asyncio.Lock()

    async def enqueue_online(self, w: Waiter) -> Optional[Waiter]:
        # If someone is already waiting, pair immediately
        try:
            other = self.queue.get_nowait()
            return other
        except asyncio.QueueEmpty:
            await self.queue.put(w)
            return None

    async def cancel_online(self, w: Waiter):
        # naive cancel: rebuild queue without w
        items = []
        while True:
            try:
                x = self.queue.get_nowait()
                if x is not w:
                    items.append(x)
            except asyncio.QueueEmpty:
                break
        for x in items:
            await self.queue.put(x)

    async def friend_offer(self, w: Waiter):
        async with self.lock:
            self.friend_wait[w.user_id] = w

    async def friend_accept(self, target_id: str) -> Optional[Waiter]:
        async with self.lock:
            return self.friend_wait.pop(target_id, None)

MM = Matchmaker()
