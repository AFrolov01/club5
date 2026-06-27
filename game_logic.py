import math
import random

# Multiplier progression table per mine count
# Formula: each step the multiplier grows based on probability of not hitting a mine
# P(safe) = (25 - mines - opened) / (25 - opened)
# multiplier[n] = multiplier[n-1] / P(safe at step n)

TOTAL_CELLS = 25  # 5x5

def compute_multipliers(mines: int, steps: int = 10) -> list[float]:
    """Compute progressive multipliers for given mine count."""
    mults = []
    current = 1.0
    for step in range(steps):
        safe_remaining = TOTAL_CELLS - mines - step
        total_remaining = TOTAL_CELLS - step
        if total_remaining <= 0 or safe_remaining <= 0:
            break
        prob_safe = safe_remaining / total_remaining
        # House edge ~2%
        current = current / (prob_safe * 0.98)
        mults.append(round(current, 2))
    return mults

# Pre-computed tables
MULTIPLIER_TABLE: dict[int, list[float]] = {
    m: compute_multipliers(m) for m in range(1, 7)
}

def get_multipliers(mines: int) -> list[float]:
    return MULTIPLIER_TABLE.get(mines, [])

def place_mines(mines: int, opened_cells: list[int]) -> list[int]:
    """Randomly place mines on cells not yet opened."""
    available = [i for i in range(TOTAL_CELLS) if i not in opened_cells]
    return random.sample(available, mines)

def format_multiplier_chain(mines: int, from_step: int, count: int = 5) -> str:
    mults = get_multipliers(mines)
    chunk = mults[from_step:from_step + count]
    if not chunk:
        return "—"
    parts = " ➡️ ".join(f"x{m:.2f}" for m in chunk)
    if from_step + count < len(mults):
        parts += " ➡️ ..."
    return parts

def build_field_keyboard(opened: list[int], mine_hit: int = -1):
    """Build 5x5 inline keyboard. opened = safe cells revealed, mine_hit = index of mine if lost."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    for row in range(5):
        row_btns = []
        for col in range(5):
            idx = row * 5 + col
            if idx in opened:
                row_btns.append(InlineKeyboardButton(text="✅", callback_data=f"cell_already_{idx}"))
            elif idx == mine_hit:
                row_btns.append(InlineKeyboardButton(text="💥", callback_data=f"cell_already_{idx}"))
            else:
                row_btns.append(InlineKeyboardButton(text="❓", callback_data=f"cell_{idx}"))
        buttons.append(row_btns)
    return buttons

def build_full_field_keyboard(opened: list[int], mines: list[int]):
    """Show all mines after game ends."""
    from aiogram.types import InlineKeyboardButton
    buttons = []
    for row in range(5):
        row_btns = []
        for col in range(5):
            idx = row * 5 + col
            if idx in mines:
                row_btns.append(InlineKeyboardButton(text="💣", callback_data=f"end_{idx}"))
            elif idx in opened:
                row_btns.append(InlineKeyboardButton(text="✅", callback_data=f"end_{idx}"))
            else:
                row_btns.append(InlineKeyboardButton(text="⬜", callback_data=f"end_{idx}"))
        buttons.append(row_btns)
    return buttons
