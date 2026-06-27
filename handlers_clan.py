from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import database as db

router = Router()


class CreateClanFSM(StatesGroup):
    waiting_name = State()
    waiting_avatar = State()
    waiting_motto = State()


class JoinClanFSM(StatesGroup):
    browsing = State()


@router.message(F.text == "/createclan")
async def cmd_createclan(message: Message, state: FSMContext):
    existing = await db.get_user_clan(message.from_user.id)
    if existing:
        await message.answer(f"⚔️ Ты уже в клане <b>{existing['name']}</b>!\nВыйди из него прежде чем создать новый.", parse_mode="HTML")
        return
    await state.set_state(CreateClanFSM.waiting_name)
    await message.answer("🏰 <b>Создание клана</b>\n\nВведи название клана:", parse_mode="HTML")


@router.message(CreateClanFSM.waiting_name)
async def clan_name_received(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) > 32:
        await message.answer("❌ Название слишком длинное! Максимум 32 символа.")
        return
    existing = await db.get_clan_by_name(name)
    if existing:
        await message.answer("❌ Клан с таким названием уже существует. Придумай другое:")
        return
    await state.update_data(name=name)
    await state.set_state(CreateClanFSM.waiting_avatar)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip_avatar")]
    ])
    await message.answer("🖼 Отправь аватарку клана (фото) или нажми Пропустить:", reply_markup=kb)


@router.callback_query(F.data == "skip_avatar", CreateClanFSM.waiting_avatar)
async def skip_avatar(call: CallbackQuery, state: FSMContext):
    await state.update_data(avatar=None)
    await state.set_state(CreateClanFSM.waiting_motto)
    await call.message.edit_text("💬 Введи девиз клана:")
    await call.answer()


@router.message(CreateClanFSM.waiting_avatar, F.photo)
async def avatar_received(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    await state.update_data(avatar=file_id)
    await state.set_state(CreateClanFSM.waiting_motto)
    await message.answer("💬 Введи девиз клана:")


@router.message(CreateClanFSM.waiting_avatar)
async def avatar_wrong(message: Message):
    await message.answer("❌ Пожалуйста, отправь фото или нажми кнопку Пропустить.")


@router.message(CreateClanFSM.waiting_motto)
async def motto_received(message: Message, state: FSMContext):
    motto = message.text.strip()
    if len(motto) > 128:
        await message.answer("❌ Девиз слишком длинный! Максимум 128 символов.")
        return
    data = await state.get_data()
    username = message.from_user.username or message.from_user.first_name
    clan_id = await db.create_clan(
        name=data["name"],
        motto=motto,
        avatar_file_id=data.get("avatar"),
        creator_id=message.from_user.id,
        creator_username=username,
    )
    await state.clear()
    text = (
        f"✅ <b>Клан создан!</b>\n\n"
        f"🏰 <b>{data['name']}</b>\n"
        f"💬 <i>{motto}</i>\n\n"
        f"Теперь другие игроки могут вступить командой /join"
    )
    if data.get("avatar"):
        await message.answer_photo(data["avatar"], caption=text, parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")


# ─── JOIN ───────────────────────────────────────────────────────────────────

@router.message(F.text == "/join")
async def cmd_join(message: Message, state: FSMContext):
    existing = await db.get_user_clan(message.from_user.id)
    if existing:
        await message.answer(f"⚔️ Ты уже в клане <b>{existing['name']}</b>!", parse_mode="HTML")
        return
    clans = await db.get_all_clans()
    if not clans:
        await message.answer("😔 Пока нет ни одного клана. Создай первый — /createclan")
        return
    await state.set_state(JoinClanFSM.browsing)
    await state.update_data(index=0)
    await show_clan_card(message, state, clans, 0, edit=False)


async def show_clan_card(message_or_call, state: FSMContext, clans, index: int, edit: bool):
    clan = clans[index]
    total = len(clans)
    members = await db.get_clan_members(clan["id"])
    text = (
        f"🏰 <b>{clan['name']}</b>  [{index + 1}/{total}]\n"
        f"💬 <i>{clan['motto'] or '—'}</i>\n"
        f"👥 Участников: {len(members)}\n"
        f"⚗️ Очки (Al): {clan['points']:.0f}"
    )
    buttons = []
    nav = []
    if index > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"join_nav_{index - 1}"))
    nav.append(InlineKeyboardButton(text="✅ Вступить", callback_data=f"join_select_{clan['id']}"))
    if index < total - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"join_nav_{index + 1}"))
    buttons.append(nav)
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    if clan.get("avatar_file_id"):
        if edit:
            # Can't edit photo easily — delete and resend
            try:
                await message_or_call.message.delete()
            except Exception:
                pass
            await message_or_call.message.answer_photo(clan["avatar_file_id"], caption=text, parse_mode="HTML", reply_markup=kb)
        else:
            await message_or_call.answer_photo(clan["avatar_file_id"], caption=text, parse_mode="HTML", reply_markup=kb)
    else:
        if edit:
            await message_or_call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        else:
            await message_or_call.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("join_nav_"), JoinClanFSM.browsing)
async def join_nav(call: CallbackQuery, state: FSMContext):
    idx = int(call.data.split("_")[2])
    clans = await db.get_all_clans()
    idx = max(0, min(idx, len(clans) - 1))
    await state.update_data(index=idx)
    await show_clan_card(call, state, clans, idx, edit=True)
    await call.answer()


@router.callback_query(F.data.startswith("join_select_"), JoinClanFSM.browsing)
async def join_select(call: CallbackQuery, state: FSMContext):
    clan_id = int(call.data.split("_")[2])
    clan = await db.get_clan_by_id(clan_id)
    username = call.from_user.username or call.from_user.first_name
    await db.join_clan(call.from_user.id, username, clan_id)
    await state.clear()
    text = f"🎉 Ты вступил в клан <b>{clan['name']}</b>!\n\n💬 <i>{clan['motto'] or ''}</i>"
    try:
        await call.message.edit_text(text, parse_mode="HTML")
    except Exception:
        await call.message.answer(text, parse_mode="HTML")
    await call.answer("Добро пожаловать!")


# ─── CLAN INFO ──────────────────────────────────────────────────────────────

@router.message(F.text == "/clan")
async def cmd_clan(message: Message):
    clan = await db.get_user_clan(message.from_user.id)
    if not clan:
        await message.answer("❌ Ты не состоишь ни в одном клане. /join — вступить, /createclan — создать.")
        return
    members = await db.get_clan_members(clan["id"])
    member_lines = []
    for m in members:
        name = f"@{m['username']}" if m['username'] else f"id{m['user_id']}"
        crown = " 👑" if m["user_id"] == clan["creator_id"] else ""
        member_lines.append(f"  • {name}{crown}")

    max_mult = clan["max_multiplier"]
    max_mult_user = clan["max_multiplier_user"] or "—"
    text = (
        f"🏰 <b>{clan['name']}</b>\n"
        f"💬 <i>{clan['motto'] or '—'}</i>\n\n"
        f"👥 <b>Участники:</b>\n" + "\n".join(member_lines) + "\n\n"
        f"⚗️ <b>Очки (Al):</b> {clan['points']:.1f}\n"
        f"🏆 <b>Побед в войне:</b> {clan['wins']}\n"
        f"🔥 <b>Макс. серия побед:</b> {clan['max_win_streak']}\n"
        f"⚡ <b>Текущая серия:</b> {clan['current_win_streak']}\n"
        f"💎 <b>Макс. множитель:</b> x{max_mult:.2f} ({max_mult_user})"
    )
    if clan.get("avatar_file_id"):
        await message.answer_photo(clan["avatar_file_id"], caption=text, parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")


# ─── TOP ────────────────────────────────────────────────────────────────────

@router.message(F.text == "/top")
async def cmd_top(message: Message):
    clans = await db.get_all_clans()
    if not clans:
        await message.answer("😔 Нет ни одного клана.")
        return
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, c in enumerate(clans):
        medal = medals[i] if i < 3 else f"{i + 1}."
        lines.append(f"{medal} <b>{c['name']}</b> — {c['points']:.1f} Al")
    text = "🏆 <b>Топ кланов — текущая война</b>\n\n" + "\n".join(lines)
    await message.answer(text, parse_mode="HTML")
