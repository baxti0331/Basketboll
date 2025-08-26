import sqlite3
import asyncio
import logging
import os
import random
from itertools import islice
from contextlib import closing
import datetime

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

from aiogram.exceptions import (
    TelegramForbiddenError,
    TelegramBadRequest,
    TelegramRetryAfter,
    TelegramNetworkError,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("basketball_bot")

# -------------------- ENV --------------------
API_TOKEN = os.getenv("BOT_TOKEN")
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
GIFT_ID = os.getenv("GIFT_ID")
GIFT_IDS = [gift.strip() for gift in GIFT_ID.split(",")] if GIFT_ID else []
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

# -------------------- ПАРАМЕТРЫ ОТПРАВКИ --------------------
BROADCAST_BATCH_SIZE = int(os.getenv("BROADCAST_BATCH_SIZE", "100"))
BROADCAST_DELAY_BETWEEN_BATCHES = float(os.getenv("BROADCAST_DELAY", "3"))
BROADCAST_PROGRESS_EVERY_BATCHES = int(os.getenv("BROADCAST_PROGRESS_EVERY", "10"))

# -------------------- ИГРОВАЯ ЭКОНОМИКА --------------------
# Стоимость набора бросков в XTR (внутр. оплата инвойсом)
COSTS = {
    5: 1,
    3: 5,
    2: 7,
    1: 10,
}

# Порог звёзд за рефералов для автоматического подарка
REFERRAL_GIFT_THRESHOLD = 200
REFERRAL_REWARD_PER_FRIEND = 2

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

DB_PATH = "basketball_bot.db"

# -------------------- DB UTILS --------------------
def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.execute("PRAGMA temp_store=MEMORY;")
        cur.execute("PRAGMA mmap_size=30000000000;")

        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                stars INTEGER DEFAULT 0
            )
        ''')
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_id ON users(user_id)")

        cur.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                user_id INTEGER PRIMARY KEY,
                referrer_id INTEGER
            )
        ''')
        cur.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id)")

        cur.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount INTEGER
            )
        ''')

        cur.execute('''
            CREATE TABLE IF NOT EXISTS gifts_sent (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                gift_id TEXT,
                reason TEXT, -- 'game' | 'referral'
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cur.execute('''
            CREATE TABLE IF NOT EXISTS inactive_users (
                user_id INTEGER PRIMARY KEY,
                reason TEXT,
                marked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cur.execute("CREATE INDEX IF NOT EXISTS idx_inactive_users_id ON inactive_users(user_id)")

        conn.commit()

def ensure_user_exists(user_id: int):
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO users (user_id, stars) VALUES (?, COALESCE((SELECT stars FROM users WHERE user_id=?), 0))", (user_id, user_id))
        conn.commit()

def get_user_stars(user_id: int) -> int:
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT stars FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        if row:
            return row[0]
        else:
            cur.execute("INSERT INTO users (user_id, stars) VALUES (?, ?)", (user_id, 0))
            conn.commit()
            return 0

def set_user_stars(user_id: int, stars: int):
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET stars = ? WHERE user_id = ?", (stars, user_id))
        conn.commit()

def increment_user_stars(user_id: int, delta: int) -> int:
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET stars = COALESCE(stars,0) + ? WHERE user_id = ?", (delta, user_id))
        conn.commit()
        cur.execute("SELECT stars FROM users WHERE user_id=?", (user_id,))
        return cur.fetchone()[0] or 0

def set_referrer_if_not_exists(user_id: int, referrer_id: int) -> bool:
    """
    Регистрирует реферала один раз и начисляет +3⭐️ только пригласившему (если он не помечен неактивным).
    Возвращает True, если реферал записан и звёзды начислены.
    """
    if user_id == referrer_id:
        return False
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT referrer_id FROM referrals WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        if row is None:
            # записываем реферала
            cur.execute("INSERT INTO referrals (user_id, referrer_id) VALUES (?, ?)", (user_id, referrer_id))
            # проверяем активность реферера
            cur.execute("SELECT 1 FROM inactive_users WHERE user_id=?", (referrer_id,))
            inactive = cur.fetchone() is not None
            if not inactive:
                # начисляем +3⭐️ ТОЛЬКО пригласившему
                cur.execute("UPDATE users SET stars = COALESCE(stars,0) + ? WHERE user_id=?", (REFERRAL_REWARD_PER_FRIEND, referrer_id))
            conn.commit()
            return not inactive
        return False

def add_payment(amount: int):
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO payments (amount) VALUES (?)", (amount,))
        conn.commit()

def record_gift_sent(user_id: int, gift_id: str, reason: str):
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO gifts_sent (user_id, gift_id, reason) VALUES (?, ?, ?)", (user_id, gift_id, reason))
        conn.commit()

def mark_user_inactive(user_id: int, reason: str):
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO inactive_users (user_id, reason) VALUES (?, ?)", (user_id, reason))
        conn.commit()

def get_active_user_ids():
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT u.user_id
            FROM users u
            LEFT JOIN inactive_users iu ON iu.user_id = u.user_id
            WHERE iu.user_id IS NULL
        """)
        return [row[0] for row in cur.fetchall()]

def get_counts_for_stats():
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        total_users = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM inactive_users")
        inactive_users = cur.fetchone()[0]
        active_users = total_users - inactive_users

        cur.execute("SELECT IFNULL(SUM(amount),0) FROM payments")
        income = cur.fetchone()[0] or 0

        cur.execute("SELECT COUNT(*) FROM gifts_sent")
        gifts_count = cur.fetchone()[0]
        expense = gifts_count * 15

        return total_users, active_users, inactive_users, income, expense, gifts_count

def get_top_referrers(limit: int = 10):
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT referrer_id, COUNT(*) AS cnt
            FROM referrals
            GROUP BY referrer_id
            ORDER BY cnt DESC
            LIMIT ?
        """, (limit,))
        return cur.fetchall()

# -------------------- UI --------------------
def format_main_menu_text(user_id: int) -> str:
    return (
        "🏀 Баскет за подарки\n\n"
        "Попади в корзину каждым броском\n"
        "и получи один из крутых подарков 🧸💝🎁🌹\n\n"
        f"💰 Баланс: {get_user_stars(user_id)} ⭐️"
    )

def throw_keyboard(user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for count in sorted(COSTS.keys(), reverse=True):
        builder.button(
            text=f"🏀 {count} {'бросок' if count == 1 else 'броска' if 2 <= count <= 4 else 'бросков'} • {COSTS[count]}⭐️",
            callback_data=f"throw_{count}"
        )
    builder.button(text="🏆 Топ ", callback_data="top_referrals")
    builder.button(text="Пригласить", callback_data=f"referral_{user_id}")
    builder.button(text="  🎳 Боулинг ", url="https://t.me/bowlinggivsbot")
    builder.button(text="Купить⭐️", url="https://t.me/bankstarstgbot")
    if user_id == ADMIN_ID and ADMIN_ID != 0:
        builder.button(text="⚙️ Админ панель", callback_data="admin_menu")
    builder.adjust(2)
    return builder.as_markup()

def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
            InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu"),
        ]
    ])

def admin_stats_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_menu")]
    ])

def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")]
    ])

# -------------------- GIFT HELPERS --------------------
def gift_name_by_id(gift_id: str) -> str:
    if gift_id == "5170233102089322756":
        return "Мишка 🧸"
    elif gift_id == "5170145012310081615":
        return "Сердечко 💝"
    else:
        return "Подарок 🎁"

async def publish_channel_win(user: types.User, gift_id: str, reason: str):
    if CHANNEL_ID == 0:
        return
    now_msk = (datetime.datetime.utcnow() + datetime.timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S MSK")
    username = f"@{user.username}" if user.username else "Нет"
    if reason == "referral":
        header = "🎉 ПОДАРОК ЗА РЕФЕРАЛОВ!"
    else:
        header = "🏆 ВЫИГРЫШ ПОДАРКА!"
    gift_name = gift_name_by_id(gift_id)
    channel_text = (
        f"{header}\n\n"
        f"👤 Пользователь: {user.full_name}\n"
        f"🏷 Username: {username}\n"
        f"🆔 ID: {user.id}\n"
        f"🎁 Подарок: {gift_name}\n"
        f"🤖Получил от:@basketbollgivsbot\n"
        f"📅 Время: {now_msk}"
    )
    try:
        await bot.send_message(CHANNEL_ID, channel_text)
    except Exception as e:
        logger.error(f"Ошибка публикации в канал: {e}")

async def give_referral_reward(user_id: int):
    """Выдаёт подарок за рефералов при достижении порога, обнуляет баланс и публикует в канал."""
    try:
        # Если нет звёзд — убедимся, что юзер в таблице
        ensure_user_exists(user_id)
        stars = get_user_stars(user_id)
        if stars < REFERRAL_GIFT_THRESHOLD:
            return False

        gift_to_send = random.choice(GIFT_IDS) if GIFT_IDS else None
        # отправляем сообщение пользователю
        if gift_to_send:
            try:
                await bot.send_gift(
                    chat_id=user_id,
                    gift_id=gift_to_send,
                    text="За приглашение друзей — спасибо! 🎉",
                    pay_for_upgrade=False
                )
                record_gift_sent(user_id, gift_to_send, "referral")
                # публикация в канал
                try:
                    user = await bot.get_chat(user_id)
                    # aiogram.get_chat -> Chat, нет .username у некоторых, но есть .username/first_name/title
                    user_as_user = types.User(id=user.id, is_bot=False, first_name=getattr(user, "first_name", user.id), last_name=getattr(user, "last_name", None), username=getattr(user, "username", None), language_code=None, is_premium=None, added_to_attachment_menu=None, can_join_groups=None, can_read_all_group_messages=None, supports_inline_queries=None)
                    await publish_channel_win(user_as_user, gift_to_send, "referral")
                except Exception as e:
                    logger.error(f"Не удалось получить данные пользователя для канала: {e}")
            except Exception as e:
                logger.error(f"Ошибка отправки подарка за рефералов {gift_to_send} пользователю {user_id}: {e}")
        else:
            # Фолбэк, если GIFT_IDS не задан
            await bot.send_message(user_id, "🎁 Подарок за рефералов! (настройте GIFT_ID для реальных подарков)")

        # Обнуляем баланс и отправляем меню
        set_user_stars(user_id, 0)
        await bot.send_message(user_id, "🎉 Подарок за приглашённых друзей получен! Баланс обнулён.")
        await send_menu_with_admin(user_id, user_id)
        return True
    except Exception as e:
        logger.error(f"Ошибка в give_referral_reward: {e}")
        return False

# -------------------- ADMIN HANDLERS --------------------
@dp.callback_query(F.data.startswith("admin_"))
async def admin_menu_handler(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    data = callback.data
    if data == "admin_menu":
        await callback.message.edit_text("⚙️ Админ панель:", reply_markup=admin_panel_keyboard())
        await callback.answer()

    elif data == "admin_stats":
        total_users, active_users, inactive_users, income, expense, gifts_count = get_counts_for_stats()
        text = (
            "📊 Статистика бота:\n"
            f"👥 Всего пользователей: {total_users}\n"
            f"✅ Активных: {active_users}\n"
            f"🚫 Неактивных: {inactive_users}\n"
            f"🎁 Подарков отправлено: {gifts_count}\n"
            f"💸 Доход: {income} XTR\n"
            f"🧾 Расход: {expense} XTR"
        )
        await callback.message.edit_text(text, reply_markup=admin_stats_keyboard())
        await callback.answer()

    elif data == "admin_broadcast":
        await callback.message.edit_text("📝 Пришлите медиа для рассылки или отправьте 'нет' если без медиа.")
        await state.set_state(BroadcastStates.waiting_media)
        await callback.answer()

# -------------------- START / MENU --------------------
@dp.message(Command("start"))
async def start_handler_with_referral(message: types.Message, command: CommandObject):
    args = command.args
    user_id = message.from_user.id
    ensure_user_exists(user_id)

    if args and args.isdigit():
        ref_id = int(args)
        # Регистрируем реферала и начисляем +3⭐️ пригласившему (если можно)
        awarded = set_referrer_if_not_exists(user_id, ref_id)
        # Проверка порога для реферера и возможная выдача подарка
        if awarded:
            try:
                # После начисления звёзд проверяем и выдаём подарок, если достигнут порог
                await give_referral_reward(ref_id)
            except Exception as e:
                logger.error(f"Ошибка автоподарка за рефералов для {ref_id}: {e}")

    await send_menu_with_admin(user_id, message.chat.id)

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback_query: CallbackQuery):
    await callback_query.message.edit_text(
        format_main_menu_text(callback_query.from_user.id),
        reply_markup=throw_keyboard(callback_query.from_user.id)
    )
    await callback_query.answer()

# -------------------- REFERRALS --------------------
@dp.callback_query(F.data == "top_referrals")
async def show_top_referrals(callback_query: CallbackQuery):
    rows = get_top_referrers(10)
    lines = []
    rank = 1
    for row in rows:
        referrer_id, cnt = row["referrer_id"], row["cnt"]
        # пытаемся получить имя пользователя
        display = f"ID {referrer_id}"
        try:
            chat = await bot.get_chat(referrer_id)
            if getattr(chat, "username", None):
                display = f"@{chat.username}"
            else:
                # first_name / title
                if getattr(chat, "first_name", None):
                    display = chat.first_name
                elif getattr(chat, "title", None):
                    display = chat.title
        except Exception:
            pass
        lines.append(f"{rank}. {display} — {cnt} 👥")
        rank += 1

    if not lines:
        text = "🏆 Топ приглашений пока пуст."
    else:
        text = "🏆 Топ-10 по приглашениям:\n\n" + "\n".join(lines)

    await callback_query.message.edit_text(text, reply_markup=back_keyboard())
    await callback_query.answer()

@dp.callback_query(F.data.startswith("referral_"))
async def process_referral(callback_query: CallbackQuery):
    inviter_id = int(callback_query.data.split("_")[1])
    bot_info = await bot.get_me()
    url = f"https://t.me/{bot_info.username}?start={inviter_id}"

    text = (
        "🏀 Бросай точные броски и выиграй крутые подарки!\n"
        "🎁 Подарки за каждый страйк!\n\n"
        "👫 Пригласи друзей:\n"
        f"— За каждого друга +{REFERRAL_REWARD_PER_FRIEND} ⭐️\n\n"
        "🔥 Твой шанс выиграть уже здесь!\n"
        f"{url}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться", switch_inline_query=text)],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")]
    ])

    await callback_query.message.answer(text, reply_markup=kb)
    await callback_query.answer()

# -------------------- PAYMENTS / GAME --------------------
@dp.callback_query(F.data.startswith("throw_"))
async def process_throw(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    count = int(callback_query.data.split("_")[1])
    price_stars = COSTS.get(count)
    if price_stars is None:
        await callback_query.answer("⛔ Некорректный набор бросков")
        return

    add_payment(price_stars)  # Добавляем в доход (учёт XTR сумм)

    await bot.send_invoice(
        chat_id=user_id,
        title=f"{count} бросков для игры",
        description=f"Набор для страйков - {count} бросков",
        payload=f"basket_{count}",
        provider_token=PROVIDER_TOKEN,
        currency="XTR",
        prices=[LabeledPrice(label=f"{count} бросков", amount=price_stars)],
        start_parameter=f"basket_{count}"
    )
    await callback_query.answer()

@dp.pre_checkout_query()
async def checkout(pre_q: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_q.id, ok=True)

@dp.message(F.content_type == types.ContentType.SUCCESSFUL_PAYMENT)
async def successful_payment(msg: types.Message):
    user_id = msg.from_user.id
    payload = msg.successful_payment.invoice_payload

    if payload.startswith("basket_"):
        count = int(payload.split("_")[1])
        results = []
        hits = 0

        for i in range(count):
            dice = await bot.send_dice(user_id, emoji="🏀")
            await asyncio.sleep(2)
            if dice.dice.value >= 5:
                results.append((i + 1, "попал ✅"))
                hits += 1
            else:
                results.append((i + 1, "мимо ❌"))

        throws_text = "\n".join([f"Бросок #{i} – {res}" for i, res in results])
        quote_msg = f"Результаты игры 🏀 {count} {'бросок' if count == 1 else 'броска' if 2 <= count <= 4 else 'бросков'}\n\n{throws_text}"
        await bot.send_message(user_id, f"```{quote_msg}```", parse_mode="Markdown")

        if hits == count:
            await asyncio.sleep(0.5)
            await bot.send_message(user_id, "🎉 Отличная игра! Все броски попали в кольцо!")
            await asyncio.sleep(0.5)
            await bot.send_message(user_id, "🎁 Ваш подарок уже в пути...")

            if GIFT_IDS:
                gift_to_send = random.choice(GIFT_IDS)
                try:
                    await bot.send_gift(
                        chat_id=user_id,
                        gift_id=gift_to_send,
                        text="Подарок за Выигрыш От @basketbollgivsbot",
                        pay_for_upgrade=False
                    )
                    record_gift_sent(user_id, gift_to_send, "game")

                    # Отправка сообщения о выигрыше в канал
                    if CHANNEL_ID != 0:
                        user = msg.from_user
                        await publish_channel_win(user, gift_to_send, "game")

                except Exception as e:
                    logger.error(f"Ошибка отправки подарка {gift_to_send} пользователю {user_id}: {e}")

            # Всегда возвращаем ПОЛНОЕ главное меню
            await send_menu_with_admin(user_id, user_id)
        else:
            await bot.send_message(user_id, "🟡 в этот раз не вышло,сыграем еще раз?")
            # Всегда возвращаем ПОЛНОЕ главное меню после неудачи
            await send_menu_with_admin(user_id, user_id)

# -------------------- BROADCAST FSM --------------------
class BroadcastStates(StatesGroup):
    waiting_media = State()
    waiting_content = State()
    waiting_button_text = State()
    waiting_button_url = State()

@dp.message(BroadcastStates.waiting_media)
async def process_broadcast_media(message: types.Message, state: FSMContext):
    if message.text and message.text.lower() == "нет":
        await message.answer("Отправьте текст для рассылки.")
        await state.set_state(BroadcastStates.waiting_content)
        await state.update_data(media=None)
    else:
        await state.update_data(media=message)
        await message.answer("Отправьте текст для рассылки.")
        await state.set_state(BroadcastStates.waiting_content)

@dp.message(BroadcastStates.waiting_content)
async def process_broadcast_content(message: types.Message, state: FSMContext):
    await state.update_data(content=message.text)
    await message.answer("Отправьте текст кнопки для рассылки или 'нет' чтобы без кнопки.")
    await state.set_state(BroadcastStates.waiting_button_text)

@dp.message(BroadcastStates.waiting_button_text)
async def process_broadcast_button_text(message: types.Message, state: FSMContext):
    text = message.text
    if text.lower() == "нет":
        await state.update_data(button_text=None, button_url=None)
        await send_broadcast(state, message)
    else:
        await state.update_data(button_text=text)
        await message.answer("Теперь отправьте ссылку для кнопки.")
        await state.set_state(BroadcastStates.waiting_button_url)

@dp.message(BroadcastStates.waiting_button_url)
async def process_broadcast_button_url(message: types.Message, state: FSMContext):
    url = message.text
    await state.update_data(button_url=url)
    await send_broadcast(state, message)

# -------------------- BROADCAST CORE --------------------
def chunks(seq, size):
    it = iter(seq)
    for first in it:
        yield [first] + list(islice(it, size - 1))

async def safe_send_to_user(user_id: int, media_msg, content, kb):
    try:
        if media_msg:
            if getattr(media_msg, "photo", None):
                await bot.send_photo(chat_id=user_id, photo=media_msg.photo[-1].file_id, caption=content, reply_markup=kb)
            elif getattr(media_msg, "video", None):
                await bot.send_video(chat_id=user_id, video=media_msg.video.file_id, caption=content, reply_markup=kb)
            elif getattr(media_msg, "sticker", None):
                await bot.send_sticker(chat_id=user_id, sticker=media_msg.sticker.file_id)
                if content:
                    await bot.send_message(chat_id=user_id, text=content, reply_markup=kb)
            elif getattr(media_msg, "animation", None):
                await bot.send_animation(chat_id=user_id, animation=media_msg.animation.file_id, caption=content, reply_markup=kb)
            else:
                await bot.send_message(chat_id=user_id, text=content, reply_markup=kb)
        else:
            await bot.send_message(chat_id=user_id, text=content, reply_markup=kb)
        return True, None

    except TelegramRetryAfter as e:
        wait_for = max(1, int(getattr(e, "retry_after", 3)))
        await asyncio.sleep(wait_for)
        try:
            if media_msg:
                if getattr(media_msg, "photo", None):
                    await bot.send_photo(chat_id=user_id, photo=media_msg.photo[-1].file_id, caption=content, reply_markup=kb)
                elif getattr(media_msg, "video", None):
                    await bot.send_video(chat_id=user_id, video=media_msg.video.file_id, caption=content, reply_markup=kb)
                elif getattr(media_msg, "sticker", None):
                    await bot.send_sticker(chat_id=user_id, sticker=media_msg.sticker.file_id)
                    if content:
                        await bot.send_message(chat_id=user_id, text=content, reply_markup=kb)
                elif getattr(media_msg, "animation", None):
                    await bot.send_animation(chat_id=user_id, animation=media_msg.animation.file_id, caption=content, reply_markup=kb)
                else:
                    await bot.send_message(chat_id=user_id, text=content, reply_markup=kb)
            else:
                await bot.send_message(chat_id=user_id, text=content, reply_markup=kb)
            return True, None
        except Exception as e2:
            logger.warning(f"Повтор после RetryAfter не удался для {user_id}: {e2}")
            return False, None

    except TelegramForbiddenError:
        return False, "forbidden"
    except TelegramBadRequest as e:
        return False, f"bad_request:{e}"
    except TelegramNetworkError as e:
        logger.warning(f"Сетевой сбой для {user_id}: {e}")
        return False, None
    except Exception as e:
        logger.error(f"Неожиданная ошибка отправки {user_id}: {e}")
        return False, None

async def send_broadcast(state: FSMContext, message: types.Message):
    data = await state.get_data()
    media_msg = data.get("media")
    content = data.get("content")
    button_text = data.get("button_text")
    button_url = data.get("button_url")

    kb = None
    if button_text and button_url:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=button_text, url=button_url)]])

    users = get_active_user_ids()
    total = len(users)
    sent = 0
    failed = 0
    newly_inactivated = 0

    await message.answer(
        "📢 Начинаю рассылку...\n"
        f"👥 Получателей (активных): {total}\n"
        f"📦 Батч: {BROADCAST_BATCH_SIZE}\n"
        f"⏳ Пауза между батчами: {BROADCAST_DELAY_BETWEEN_BATCHES} сек."
    )

    batch_index = 0
    for batch in chunks(users, BROADCAST_BATCH_SIZE):
        batch_index += 1
        results = await asyncio.gather(*[safe_send_to_user(uid, media_msg, content, kb) for uid in batch])
        for uid, (ok, reason) in zip(batch, results):
            if ok:
                sent += 1
            else:
                failed += 1
                if reason in ("forbidden",) or (reason and reason.startswith("bad_request")):
                    mark_user_inactive(uid, reason)
                    newly_inactivated += 1

        if batch_index % BROADCAST_PROGRESS_EVERY_BATCHES == 0:
            await bot.send_message(message.chat.id, f"📤 Прогресс: {sent + failed}/{total} (✅ {sent} | ⛔ {failed} | 🚫 деактивировано: {newly_inactivated})")

        await asyncio.sleep(BROADCAST_DELAY_BETWEEN_BATCHES)

    await message.answer(
        "✅ Рассылка завершена.\n"
        f"👥 Получателей (активных на момент старта): {total}\n"
        f"📨 Успешно: {sent}\n"
        f"⛔ Ошибки: {failed}\n"
        f"🚫 Новых неактивных помечено: {newly_inactivated}"
    )
    await state.clear()

# -------------------- MENU SENDER --------------------
async def send_menu_with_admin(user_id: int, chat_id: int):
    text = format_main_menu_text(user_id)
    await bot.send_message(chat_id=chat_id, text=text, reply_markup=throw_keyboard(user_id))

# -------------------- FALLBACK: ЛЮБОЕ СООБЩЕНИЕ = ГЛАВНОЕ МЕНЮ --------------------
@dp.message()
async def any_message_handler(message: types.Message):
    """
    Любой апдейт (цифра, слово, стикер, фото и т.д.) — отправляем главное меню.
    Исключение: события, которые уже перехвачены специфичными хендлерами (инвойсы, FSM и т.п.).
    """
    user_id = message.from_user.id
    ensure_user_exists(user_id)
    await send_menu_with_admin(user_id, message.chat.id)

# -------------------- ENTRY --------------------
async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())