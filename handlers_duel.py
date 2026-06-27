import json
import random
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

import database as db
import game_logic as gl

router = Router()

ADMIN_ID = 1979390272


# ─── HELPERS ────────────────────────────────────────────────────────────────

def mention(user_id: int, name: str) -> str:
    return f'<a href="tg://user?id={user_id}">{name}</a>'


def fmt_points(pts: float) -> str:
    return f"{pts:.1f}"


async def get_username(bot: Bot, user_id: int, chat_id: int) -> str:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        u = member.user
        return u.username or u.first_name
    except Exception:
        return f"id{user_id}"


def mines_rules_text(mines: int, clan_points: float) -> str:
    after_loss = clan_points * 0.75
    loss_note = f"Очки клана станут: {after_loss:.1f} Al" if clan_points > 0 else "Очки клана уменьшатся (уже ≤0)"
    mults = gl.get_multipliers(mines)
    chain = " ➡️ ".join(f"x{m:.2f}" for m in mults[:6])
    if len(mults) > 6:
        chain += " ➡️ ..."
    return chain


async def send_bet_choice(bot: Bot, duel: dict, player_id: int):
    """Send the mine-count selection message to a player in PM."""
    clan = await db.get_clan_by_id(
        duel["clan1_id"] if duel["player1_id"] == player_id else duel["clan2_id"]
    )
    clan_pts = clan["points"] if clan else 100
    after_loss = clan_pts * 0.75
    loss_note = f"{after_loss:.1f} Al" if clan_pts > 0 else "станет меньше (уже ≤0)"

    lines = ["<b>📋 Правила дуэли:</b>"]
    lines.append(f"• Поле 5×5, ты открываешь клетки.")
    lines.append(f"• Нашёл мину → очки клана ×0.75 ({loss_note}), игра окончена.")
    lines.append(f"• Забрал очки сам → клан получает текущий выигрыш.")
    lines.append(f"• Чем больше мин выбрал — тем выше множители!\n")

    rules_block = "\n".join(lines)

    mult_lines = ["<b>📈 Прогрессия множителей по числу мин:</b>"]
    for m in range(1, 7):
        mults = gl.get_multipliers(m)
        chain = " ➡️ ".join(f"x{v:.2f}" for v in mults[:5])
        if len(mults) > 5:
            chain += " ➡️ ..."
        mult_lines.append(f"{'💣' * m} <b>{m} мин{'а' if m==1 else 'ы' if m<5 else ''}:</b> {chain}")

    mult_block = "\n".join(mult_lines)

    text = (
        f"⚔️ <b>Тебя вызвали на дуэль!</b>\n\n"
        f"<blockquote>{rules_block}</blockquote>\n\n"
        f"<blockquote>{mult_block}</blockquote>\n\n"
        f"Выбери количество мин:"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"1️⃣", callback_data=f"bet_{duel['id']}_1"),
        InlineKeyboardButton(text=f"2️⃣", callback_data=f"bet_{duel['id']}_2"),
        InlineKeyboardButton(text=f"3️⃣", callback_data=f"bet_{duel['id']}_3"),
        InlineKeyboardButton(text=f"4️⃣", callback_data=f"bet_{duel['id']}_4"),
        InlineKeyboardButton(text=f"5️⃣", callback_data=f"bet_{duel['id']}_5"),
        InlineKeyboardButton(text=f"6️⃣", callback_data=f"bet_{duel['id']}_6"),
    ]])

    try:
        await bot.send_message(player_id, text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass  # User may not have started the bot in PM


def build_field_kb(duel_id: int, opened: list, show_collect: bool = True) -> InlineKeyboardMarkup:
    rows = []
    for r in range(5):
        row = []
        for c in range(5):
            idx = r * 5 + c
            if idx in opened:
                row.append(InlineKeyboardButton(text="✅", callback_data=f"ca_{idx}"))
            else:
                row.append(InlineKeyboardButton(text="❓", callback_data=f"cell_{duel_id}_{idx}"))
        rows.append(row)
    if show_collect:
        rows.append([InlineKeyboardButton(text="💰 Забрать очки ✅", callback_data=f"collect_{duel_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_end_field_kb(opened: list, mines: list) -> InlineKeyboardMarkup:
    rows = []
    for r in range(5):
        row = []
        for c in range(5):
            idx = r * 5 + c
            if idx in mines:
                row.append(InlineKeyboardButton(text="💣", callback_data=f"ca_{idx}"))
            elif idx in opened:
                row.append(InlineKeyboardButton(text="✅", callback_data=f"ca_{idx}"))
            else:
                row.append(InlineKeyboardButton(text="⬜", callback_data=f"ca_{idx}"))
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_field_message(bot: Bot, player_id: int, duel: dict, opened: list, step: int):
    mines = duel["mines_count"]
    mults = gl.get_multipliers(mines)
    current_mult = mults[step - 1] if step > 0 and step <= len(mults) else 1.0
    clan = await db.get_clan_by_id(
        duel["clan1_id"] if duel["player1_id"] == player_id else duel["clan2_id"]
    )
    clan_pts = clan["points"] if clan else 100
    win_pts = clan_pts * current_mult

    next_chain = gl.format_multiplier_chain(mines, step, 5)

    if step == 0:
        status_line = f"📊 Множитель: x1.00 / {clan_pts:.1f} Al"
    else:
        status_line = f"📊 Выигрыш: x{current_mult:.2f} / {win_pts:.1f} Al"

    text = (
        f"💣 Мин: {mines}\n"
        f"⚗️ Очки клана: {clan_pts:.1f} Al\n"
        f"{status_line}\n\n"
        f"🧮 <b>Следующий множитель:</b>\n{next_chain}\n\n"
        f"Открывай клетки или забери очки:"
    )
    kb = build_field_kb(duel["id"], opened)
    return text, kb


# ─── /minduel ───────────────────────────────────────────────────────────────

@router.message(Command("minduel"))
async def cmd_minduel(message: Message, bot: Bot):
    user_id = message.from_user.id
    duel = await db.get_active_duel_for_player(user_id)
    if not duel:
        await message.answer("❌ У тебя нет активной дуэли прямо сейчас.")
        return

    is_p1 = duel["player1_id"] == user_id
    my_done = duel["p1_done"] if is_p1 else duel["p2_done"]
    if my_done:
        await message.answer("✅ Ты уже отыграл свою дуэль!")
        return

    # Mark current player active
    await db.update_duel(duel["id"], current_player=user_id, state="waiting_bet")
    await message.answer("✉️ Проверь личные сообщения от бота — там выбор ставки!")
    await send_bet_choice(bot, duel, user_id)


# ─── BET SELECTION ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("bet_"))
async def bet_selected(call: CallbackQuery, bot: Bot):
    _, duel_id, mines_str = call.data.split("_")
    duel_id = int(duel_id)
    mines = int(mines_str)
    user_id = call.from_user.id

    duel = await db.get_duel(duel_id)
    if not duel:
        await call.answer("Дуэль не найдена.")
        return
    if user_id not in (duel["player1_id"], duel["player2_id"]):
        await call.answer("Это не твоя дуэль.")
        return

    is_p1 = duel["player1_id"] == user_id
    my_done = duel["p1_done"] if is_p1 else duel["p2_done"]
    if my_done:
        await call.answer("Ты уже сыграл!")
        return

    # Generate mines
    mine_positions = random.sample(range(25), mines)
    await db.update_duel(
        duel_id,
        mines_count=mines,
        mine_positions=json.dumps(mine_positions),
        opened_cells=json.dumps([]),
        current_multiplier=1.0,
        state="playing",
        current_player=user_id,
    )

    duel = await db.get_duel(duel_id)
    text, kb = await send_field_message(bot, user_id, duel, [], 0)
    msg = await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    # store field message id per player
    field_key = "field_message_id" if is_p1 else "field_message_id"
    await call.answer(f"Выбрано {mines} {'мина' if mines==1 else 'мины' if mines<5 else 'мин'}! Открывай поле.")


# ─── CELL CLICK ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cell_"))
async def cell_clicked(call: CallbackQuery, bot: Bot):
    parts = call.data.split("_")
    if len(parts) != 3:
        await call.answer()
        return
    _, duel_id_str, idx_str = parts
    duel_id = int(duel_id_str)
    idx = int(idx_str)
    user_id = call.from_user.id

    duel = await db.get_duel(duel_id)
    if not duel:
        await call.answer("Дуэль не найдена.")
        return
    if duel["current_player"] != user_id:
        await call.answer("Сейчас не твой ход!")
        return
    if duel["state"] != "playing":
        await call.answer("Игра не активна.")
        return

    mine_positions = json.loads(duel["mine_positions"])
    opened_cells = json.loads(duel["opened_cells"])

    if idx in opened_cells:
        await call.answer("Эта клетка уже открыта!")
        return

    if idx in mine_positions:
        # HIT MINE
        is_p1 = duel["player1_id"] == user_id
        clan_id = duel["clan1_id"] if is_p1 else duel["clan2_id"]
        clan = await db.get_clan_by_id(clan_id)
        old_pts = clan["points"]
        new_pts = old_pts * 0.75

        await db.update_clan_points(clan_id, new_pts)
        await db.update_clan_stats(clan_id, won=False)

        if is_p1:
            await db.update_duel(duel_id, p1_done=1, p1_result=0)
        else:
            await db.update_duel(duel_id, p2_done=1, p2_result=0)

        duel = await db.get_duel(duel_id)
        both_done = duel["p1_done"] and duel["p2_done"]
        if both_done:
            await db.update_duel(duel_id, state="finished")

        # Show exploded field
        kb = build_end_field_kb(opened_cells, mine_positions)
        loss_text = (
            f"💥 <b>БУМ! Ты нашёл мину!</b>\n\n"
            f"⚗️ Очки клана: {old_pts:.1f} → {new_pts:.1f} Al (×0.75)\n\n"
            f"💣 Вот где были все мины:"
        )
        await call.message.edit_text(loss_text, parse_mode="HTML", reply_markup=kb)
        await call.answer("💥 Мина!")

        # Notify group
        if both_done:
            await announce_duel_result(bot, duel)
        else:
            # Prompt other player
            other_id = duel["player2_id"] if is_p1 else duel["player1_id"]
            other_done = duel["p2_done"] if is_p1 else duel["p1_done"]
            if not other_done:
                try:
                    await bot.send_message(other_id,
                        "⚔️ Твой соперник уже сыграл! Иди в группу и нажми /minduel")
                except Exception:
                    pass
        return

    # SAFE CELL
    opened_cells.append(idx)
    step = len(opened_cells)
    mults = gl.get_multipliers(duel["mines_count"])
    current_mult = mults[step - 1] if step <= len(mults) else mults[-1]

    await db.update_duel(duel_id, opened_cells=json.dumps(opened_cells), current_multiplier=current_mult)
    duel = await db.get_duel(duel_id)

    # Check if all safe cells opened
    total_safe = 25 - duel["mines_count"]
    if step >= total_safe:
        # Auto-collect: all safe cells found
        await do_collect(call, bot, duel, user_id, current_mult, opened_cells, mine_positions)
        return

    text, kb = await send_field_message(bot, user_id, duel, opened_cells, step)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await call.answer(f"✅ Безопасно! x{current_mult:.2f}")


# ─── COLLECT ────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("collect_"))
async def collect_clicked(call: CallbackQuery, bot: Bot):
    duel_id = int(call.data.split("_")[1])
    user_id = call.from_user.id
    duel = await db.get_duel(duel_id)
    if not duel:
        await call.answer()
        return
    if duel["current_player"] != user_id:
        await call.answer("Сейчас не твой ход!")
        return
    opened_cells = json.loads(duel["opened_cells"])
    mine_positions = json.loads(duel["mine_positions"])
    mult = duel["current_multiplier"]
    await do_collect(call, bot, duel, user_id, mult, opened_cells, mine_positions)


async def do_collect(call: CallbackQuery, bot: Bot, duel: dict, user_id: int,
                     mult: float, opened_cells: list, mine_positions: list):
    is_p1 = duel["player1_id"] == user_id
    clan_id = duel["clan1_id"] if is_p1 else duel["clan2_id"]
    clan = await db.get_clan_by_id(clan_id)
    old_pts = clan["points"]
    new_pts = old_pts * mult

    await db.update_clan_points(clan_id, new_pts)
    username = call.from_user.username or call.from_user.first_name
    await db.update_clan_stats(clan_id, won=True, multiplier=mult, winner_name=username)

    if is_p1:
        await db.update_duel(duel["id"], p1_done=1, p1_result=mult)
    else:
        await db.update_duel(duel["id"], p2_done=1, p2_result=mult)

    duel = await db.get_duel(duel["id"])
    both_done = duel["p1_done"] and duel["p2_done"]
    if both_done:
        await db.update_duel(duel["id"], state="finished")

    kb = build_end_field_kb(opened_cells, mine_positions)
    text = (
        f"💰 <b>Очки забраны!</b>\n\n"
        f"⚗️ Очки клана: {old_pts:.1f} → {new_pts:.1f} Al (x{mult:.2f})\n"
        f"✅ Открыто клеток: {len(opened_cells)}\n\n"
        f"💣 Мины были здесь:"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await call.answer(f"💰 Забрано! x{mult:.2f}")

    if both_done:
        await announce_duel_result(bot, duel)
    else:
        other_id = duel["player2_id"] if is_p1 else duel["player1_id"]
        other_done = duel["p2_done"] if is_p1 else duel["p1_done"]
        if not other_done:
            try:
                await bot.send_message(other_id,
                    "⚔️ Твой соперник уже сыграл! Иди в группу и нажми /minduel")
            except Exception:
                pass


async def announce_duel_result(bot: Bot, duel: dict):
    """Send final result to group chat."""
    group_id = duel["group_id"]
    clan1 = await db.get_clan_by_id(duel["clan1_id"])
    clan2 = await db.get_clan_by_id(duel["clan2_id"])

    def res(done, result):
        if not done:
            return "⏳ не сыграл"
        if result == 0:
            return "💥 мина (×0.75)"
        return f"💰 ×{result:.2f}"

    text = (
        f"⚔️ <b>Дуэль завершена!</b>\n\n"
        f"🏰 <b>{clan1['name'] if clan1 else '?'}</b>: {res(duel['p1_done'], duel['p1_result'])} → {clan1['points']:.1f} Al\n"
        f"🏰 <b>{clan2['name'] if clan2 else '?'}</b>: {res(duel['p2_done'], duel['p2_result'])} → {clan2['points']:.1f} Al\n\n"
        f"📊 /top — текущий рейтинг кланов"
    )
    try:
        await bot.send_message(group_id, text, parse_mode="HTML")
    except Exception:
        pass


# ─── CA (already opened / end) ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("ca_"))
async def noop(call: CallbackQuery):
    await call.answer()
