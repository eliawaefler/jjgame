from __future__ import annotations
from typing import List, Tuple
import random

RPS = ["R", "P", "S"]
WINS = {("R","S"), ("P","R"), ("S","P")}
EMOJI = {"R": "🪨", "P": "📄", "S": "✂️"}
WORD_DE = {"R": "Stein", "P": "Papier", "S": "Schere"}

def new_center(symbols: List[str]=None) -> str:
    return random.choice(symbols or RPS)

def other_two(center: str) -> List[str]:
    return [x for x in RPS if x != center]

def evaluate(attacker_choice: str, center: str) -> bool:
    return (attacker_choice, center) in WINS

def pretty(symbol: str, style: str) -> Tuple[str, str]:
    if style == "emoji":
        return "emoji", EMOJI[symbol]
    if style == "text":
        return "letter", symbol
    if style == "desc":
        return "word_de", WORD_DE[symbol]
    if style == "img":
        return "letter", symbol
    return "letter", symbol