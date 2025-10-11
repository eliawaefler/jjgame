
# -----------------------------
# game.py
# -----------------------------
import random, time
from typing import Tuple

RPS = ["R", "P", "S"]

# Prompt rule: top symbol X, valid answers are the other 2.
# If player chooses the losing option vs X, they insta-lose.
# If chooses the winning option vs X, they insta-win. First click decides.

# who_wins_against[X] -> symbol that beats X
WIN_AGAINST = {"R": "P", "P": "S", "S": "R"}
LOSE_AGAINST = {v: k for k, v in WIN_AGAINST.items()}  # what loses to X


def new_round() -> str:
    return random.choice(RPS)


def evaluate(prompt: str, choice: str) -> str:
    # returns "win" | "lose"
    if choice == WIN_AGAINST[prompt]:
        return "win"
    elif choice == LOSE_AGAINST[prompt]:
        return "lose"
    else:
        # should never happen (choice equal prompt not offered in UI)
        return "lose"
