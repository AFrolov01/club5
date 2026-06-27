import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, BotCommand
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command

import database as db
import scheduler as sched
from handlers_clan import router as clan_router
from handlers_duel import router as duel_router

BOT_TOKEN = "8792736488:AAHQVD2N0xRsVjbZn7bFWnYQhVfV6FKr-_g"
ADMIN_ID = 1979390272

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

dp.include_router(clan_router)
dp.include_router(duel_router)


# ─── GROUP TRACKING ─────────────────────────────────────────────────────────

@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def track_group(message: Message):
    sched.register_group(message.chat.id)


# ─── /start ─────────────────────────────────────────────────────────────────

@dp.message(Command("start"))
async def cmd_start(message: Message):
    if message.chat.type in ("group", "supergroup"):
        sched.register_group(message.chat.id)
        await message.answer(
            "⚔️ <b>ClanWar Bot запущен!</b>\n\n"
            "Доступные команды:\n"
            "/createclan — создать клан\n"
            "/join — вступить в клан\n"
            "/clan — информация о своём клане\n"
            "/top — рейтинг кланов\n"
            "/minduel — принять дуэль\n\n"
            "Дуэли будут объявляться автоматически каждые 2 дня!",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "👋 Привет! Я бот войны кланов.\n"
            "Добавь меня в группу и используй /start там."
        )


# ─── ADMIN: принудительный вызов дуэли ──────────────────────────────────────

@dp.message(Command("forceduel"))
async def cmd_forceduel(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("Только в группе!")
        return
    sched.register_group(message.chat.id)
    await sched.announce_duel(bot, message.chat.id)


# ─── SETUP ──────────────────────────────────────────────────────────────────

async def set_commands():
    commands = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="createclan", description="Создать клан"),
        BotCommand(command="join", description="Вступить в клан"),
        BotCommand(command="clan", description="Мой клан"),
        BotCommand(command="top", description="Рейтинг кланов"),
        BotCommand(command="minduel", description="Принять дуэль"),
        BotCommand(command="forceduel", description="[Админ] Принудить дуэль"),
    ]
    await bot.set_my_commands(commands)


async def main():
    await db.init_db()
    await set_commands()

    # Start scheduler in background
    asyncio.create_task(sched.scheduler_loop(bot))

    logging.info("Bot started!")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
