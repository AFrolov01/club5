"""
Scheduler: fires a duel announcement every 2 days in every registered group.
Also handles AFK turn-passing: if a player hasn't played within 30 minutes,
the duel passes to the other player (who gets a bonus turn after their own).
"""
import asyncio
import json
from datetime import datetime, timedelta

from aiogram import Bot

import database as db
from matchmaking import pick_next_duel

# How often the scheduler ticks (seconds)
TICK_INTERVAL = 60

# Duel interval: 2 days
DUEL_INTERVAL_HOURS = 48

# AFK timeout: 30 minutes
AFK_TIMEOUT_MINUTES = 30

# Store next duel timestamps per group  {group_id: datetime}
_next_duel_time: dict[int, datetime] = {}
# Track when current_player last acted {duel_id: datetime}
_last_action: dict[int, datetime] = {}
# Groups the bot has seen  {group_id}
_known_groups: set[int] = set()


def register_group(group_id: int):
    if group_id not in _known_groups:
        _known_groups.add(group_id)
        if group_id not in _next_duel_time:
            _next_duel_time[group_id] = datetime.utcnow() + timedelta(hours=DUEL_INTERVAL_HOURS)


def record_action(duel_id: int):
    _last_action[duel_id] = datetime.utcnow()


def mention(user_id: int, name: str) -> str:
    return f'<a href="tg://user?id={user_id}">{name}</a>'


async def get_display_name(bot: Bot, group_id: int, user_id: int) -> str:
    try:
        member = await bot.get_chat_member(group_id, user_id)
        u = member.user
        return u.username or u.first_name
    except Exception:
        return f"id{user_id}"


async def announce_duel(bot: Bot, group_id: int):
    """Pick players and announce a new duel in the group."""
    # Get last players from queue to avoid repeats
    q = await db.get_queue(group_id)
    last_p1 = q["last_p1_id"] if q else None
    last_p2 = q["last_p2_id"] if q else None

    result = await pick_next_duel(group_id, last_p1, last_p2)
    if not result:
        await bot.send_message(
            group_id,
            "⚔️ <b>Война кланов</b>\n\n"
            "Недостаточно кланов или участников для дуэли. "
            "Создайте клан (/createclan) или вступите (/join)!",
            parse_mode="HTML"
        )
        return

    p1_id, p2_id, clan1_id, clan2_id = result

    clan1 = await db.get_clan_by_id(clan1_id)
    clan2 = await db.get_clan_by_id(clan2_id)
    p1_name = await get_display_name(bot, group_id, p1_id)
    p2_name = await get_display_name(bot, group_id, p2_id)

    # Check for any unfinished duel and cancel it
    old = await db.get_active_duel_for_group(group_id)
    if old and old["state"] not in ("finished", "cancelled"):
        await db.update_duel(old["id"], state="cancelled")

    duel_id = await db.create_duel(group_id, p1_id, p2_id, clan1_id, clan2_id)

    # Save queue
    next_time = (datetime.utcnow() + timedelta(hours=DUEL_INTERVAL_HOURS)).isoformat()
    await db.set_queue(group_id, next_time, p1_id, p2_id)
    record_action(duel_id)

    text = (
        f"⚔️✨ <b>ВОЙНА КЛАНОВ — ДУЭЛЬ!</b> ✨⚔️\n\n"
        f"🏰 {mention(p1_id, p1_name)} (<b>{clan1['name'] if clan1 else '?'}</b>)\n"
        f"      ⚔️  VS  ⚔️\n"
        f"🏰 {mention(p2_id, p2_name)} (<b>{clan2['name'] if clan2 else '?'}</b>)\n\n"
        f"🎯 На кону — очки клана (Al)!\n\n"
        f"Оба игрока, нажмите /minduel чтобы перейти к выбору ставки.\n"
        f"⏳ На ответ у каждого <b>{AFK_TIMEOUT_MINUTES} минут</b>, иначе ход перейдёт!"
    )
    msg = await bot.send_message(group_id, text, parse_mode="HTML")
    await db.update_duel(duel_id, message_id=msg.message_id)


async def handle_afk(bot: Bot):
    """Check all active duels for AFK players and pass turns if needed."""
    # We iterate over all in-progress duels
    # Since we don't have a list endpoint, we rely on known groups
    for group_id in list(_known_groups):
        duel = await db.get_active_duel_for_group(group_id)
        if not duel:
            continue
        if duel["state"] in ("finished", "cancelled"):
            continue

        duel_id = duel["id"]
        last = _last_action.get(duel_id)
        if last is None:
            _last_action[duel_id] = datetime.utcnow()
            continue

        elapsed = (datetime.utcnow() - last).total_seconds() / 60
        if elapsed < AFK_TIMEOUT_MINUTES:
            continue

        # Who is AFK?
        current = duel["current_player"]
        p1_done = duel["p1_done"]
        p2_done = duel["p2_done"]

        if p1_done and p2_done:
            continue

        # Determine which player is AFK
        afk_id = None
        if not p1_done and current == duel["player1_id"]:
            afk_id = duel["player1_id"]
        elif not p2_done and current == duel["player2_id"]:
            afk_id = duel["player2_id"]
        else:
            # No one is actively expected right now
            continue

        # Mark AFK player as done with 0 result (loss by timeout)
        clan_id = duel["clan1_id"] if afk_id == duel["player1_id"] else duel["clan2_id"]
        clan = await db.get_clan_by_id(clan_id)
        if clan:
            new_pts = clan["points"] * 0.75
            await db.update_clan_points(clan_id, new_pts)

        afk_name = await get_display_name(bot, group_id, afk_id)

        if afk_id == duel["player1_id"]:
            await db.update_duel(duel_id, p1_done=1, p1_result=0)
        else:
            await db.update_duel(duel_id, p2_done=1, p2_result=0)

        duel = await db.get_duel(duel_id)
        both_done = duel["p1_done"] and duel["p2_done"]

        try:
            await bot.send_message(
                group_id,
                f"⏰ <b>AFK!</b> {mention(afk_id, afk_name)} не сыграл вовремя.\n"
                f"Очки его клана ×0.75 (штраф за пропуск).",
                parse_mode="HTML"
            )
        except Exception:
            pass

        if both_done:
            await db.update_duel(duel_id, state="finished")
            # Import here to avoid circular
            from handlers_duel import announce_duel_result
            await announce_duel_result(bot, duel)
        else:
            # Give other player a bonus turn prompt
            other_id = duel["player2_id"] if afk_id == duel["player1_id"] else duel["player1_id"]
            other_done = duel["p2_done"] if afk_id == duel["player1_id"] else duel["p1_done"]
            if not other_done:
                other_name = await get_display_name(bot, group_id, other_id)
                try:
                    await bot.send_message(
                        group_id,
                        f"➡️ {mention(other_id, other_name)}, соперник пропустил!\n"
                        f"Нажми /minduel чтобы сыграть.",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
                await db.update_duel(duel_id, current_player=other_id)
                _last_action[duel_id] = datetime.utcnow()


async def check_war_end(bot: Bot):
    """After 30 days — end war, announce results, reset."""
    for group_id in list(_known_groups):
        war = await db.get_active_war(group_id)
        if not war:
            await db.create_war(group_id)
            continue
        start = datetime.fromisoformat(war["start_date"])
        if (datetime.utcnow() - start).days >= 30:
            # End war
            clans = await db.get_all_clans()
            if clans:
                medals = ["🥇", "🥈", "🥉"]
                lines = []
                for i, c in enumerate(clans):
                    medal = medals[i] if i < 3 else f"{i+1}."
                    lines.append(f"{medal} <b>{c['name']}</b> — {c['points']:.1f} Al")
                winner = clans[0]
                text = (
                    f"🏆 <b>ВОЙНА КЛАНОВ ЗАВЕРШЕНА!</b>\n\n"
                    f"Победитель: 🎉 <b>{winner['name']}</b>!\n\n"
                    + "\n".join(lines) +
                    f"\n\n⚗️ Все кланы начинают со 100 Al. Новая война начинается!"
                )
                try:
                    await bot.send_message(group_id, text, parse_mode="HTML")
                except Exception:
                    pass
            # Reset
            async with __import__("aiosqlite").connect(db.DB_PATH) as conn:
                await conn.execute(
                    "UPDATE war_sessions SET active=0, end_date=CURRENT_TIMESTAMP WHERE group_id=? AND active=1",
                    (group_id,)
                )
                await conn.commit()
            await db.reset_all_clan_points()
            await db.create_war(group_id)


async def scheduler_loop(bot: Bot):
    """Main scheduler tick."""
    while True:
        await asyncio.sleep(TICK_INTERVAL)
        try:
            now = datetime.utcnow()

            # Check AFK in all groups
            await handle_afk(bot)

            # Check war end
            await check_war_end(bot)

            # Check duel timers
            for group_id in list(_known_groups):
                next_time = _next_duel_time.get(group_id)
                if next_time is None:
                    _next_duel_time[group_id] = now + timedelta(hours=DUEL_INTERVAL_HOURS)
                    continue
                if now >= next_time:
                    _next_duel_time[group_id] = now + timedelta(hours=DUEL_INTERVAL_HOURS)
                    await announce_duel(bot, group_id)

        except Exception as e:
            print(f"[scheduler] error: {e}")
