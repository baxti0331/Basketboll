import sqlite3
import asyncio
import logging
import os
import random

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv("BOT_TOKEN")
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
GIFT_ID = os.getenv("GIFT_ID")

GIFT_IDS = [gift.strip() for gift in GIFT_ID.split(",")] if GIFT_ID else []

COSTS = {
    5: 1,
    3: 3,
    2: 5,
    1: 8,
}

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

def init_db():
    with sqlite3.connect("basketball_bot.db") as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                stars INTEGER DEFAULT 20
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                user_id INTEGER PRIMARY KEY,
                referrer_id INTEGER
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount INTEGER
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS gifts_sent (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                gift_id TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

def get_user_stars(user_id: int) -> int:
    with sqlite3.connect("basketball_bot.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT stars FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            return row[0]
        else:
            cursor.execute("INSERT INTO users (user_id, stars) VALUES (?, ?)", (user_id, 0))
            conn.commit()
            return 0

def set_user_stars(user_id: int, stars: int):
    with sqlite3.connect("basketball_bot.db") as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET stars = ? WHERE user_id = ?", (stars, user_id))
        conn.commit()

def set_referrer_if_not_exists(user_id: int, referrer_id: int):
    if user_id == referrer_id:
        return
    with sqlite3.connect("basketball_bot.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT referrer_id FROM referrals WHERE user_id=?", (user_id,))
        row = cursor.fetchone()
        if row is None:
            cursor.execute("INSERT INTO referrals (user_id, referrer_id) VALUES (?, ?)", (user_id, referrer_id))
            cursor.execute("UPDATE users SET stars = stars + 3 WHERE user_id=?", (referrer_id,))
            conn.commit()

def add_payment(amount: int):
    with sqlite3.connect("basketball_bot.db") as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO payments (amount) VALUES (?)", (amount,))
        conn.commit()

def record_gift_sent(user_id: int, gift_id: str):
    with sqlite3.connect("basketball_bot.db") as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO gifts_sent (user_id, gift_id) VALUES (?, ?)", (user_id, gift_id))
        conn.commit()

def get_stats():
    with sqlite3.connect("basketball_bot.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        users_count = cursor.fetchone()[0]
        cursor.execute("SELECT IFNULL(SUM(amount),0) FROM payments")
        income = cursor.fetchone()[0] or 0
        cursor.execute("SELECT COUNT(*) FROM gifts_sent")
        gifts_count = cursor.fetchone()[0]
        expense = gifts_count * 15
        return users_count, income, expense

def throw_keyboard(user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for count in sorted(COSTS.keys(), reverse=True):
        builder.button(
            text=f"🏀 {count} бросков • {COSTS[count]}⭐️",
            callback_data=f"throw_{count}"
        )
    builder.button(text="+ 3 ⭐️ за друга", callback_data=f"referral_{user_id}")
    builder.button(text="  🎳 Боулинг ", url="https://t.me/bowlinggivsbot")
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
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_menu"),
        ]
    ])

@dp.callback_query(F.data.startswith("admin_"))
async def admin_menu_handler(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    data = callback.data

    if data == "admin_menu":
        await callback.message.edit_text(
            "⚙️ Админ панель:",
            reply_markup=admin_panel_keyboard()
        )
        await callback.answer()

    elif data == "admin_stats":
        users_count, income, expense = get_stats()
        text = (
            f"📊 Статистика бота:\n"
            f"Пользователей: {users_count}\n"
            f"Доход: {income} XTR\n"
            f"Расход: {expense} XTR"
        )
        await callback.message.edit_text(text, reply_markup=admin_stats_keyboard())
        await callback.answer()

    elif data == "admin_broadcast":
        await callback.message.edit_text("📝 Пришлите медиа для рассылки или отправьте 'нет' если без медиа.")
        await state.set_state(BroadcastStates.waiting_media)
        await callback.answer()

@dp.message(Command("start"))
async def start_handler_with_referral(message: types.Message, command: CommandObject):
    args = command.args
    user_id = message.from_user.id
    if args and args.isdigit():
        ref_id = int(args)
        set_referrer_if_not_exists(user_id, ref_id)

    await send_menu_with_admin(user_id, message.chat.id)

@dp.callback_query(F.data.startswith("referral_"))
async def process_referral(callback_query: CallbackQuery):
    inviter_id = int(callback_query.data.split("_")[1])
    bot_info = await bot.get_me()
    url = f"https://t.me/{bot_info.username}?start={inviter_id}"

    text = (
        "🏀 Бросай точные броски и выиграй крутые подарки!\n"
        "🎁 Подарки за каждый страйк!\n\n"
        "👫 Пригласи друзей:\n"
        "— За каждого друга +3 ⭐️\n\n"
        "🔥 Твой шанс выиграть уже здесь!\n"
        f"{url}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться", switch_inline_query=text)],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")]
    ])

    await callback_query.message.answer(text, reply_markup=kb)
    await callback_query.answer()

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback_query: CallbackQuery):
    await callback_query.message.edit_text(
        "🏀 Баскет за подарки\n\n"
        "Попади в корзину каждым броском\n"
        "и получи один из крутых подарков 🧸💝🎁🌹\n\n"
        f"💰 Баланс: {get_user_stars(callback_query.from_user.id)} ⭐️",
        reply_markup=throw_keyboard(callback_query.from_user.id)
    )
    await callback_query.answer()

@dp.callback_query(F.data.startswith("throw_"))
async def process_throw(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    count = int(callback_query.data.split("_")[1])
    price_stars = COSTS.get(count)
    if price_stars is None:
        await callback_query.answer("⛔ Некорректный набор бросков")
        return

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
            if dice.dice.value >= 4:
                results.append((i + 1, "попал ✅"))
                hits += 1
            else:
                results.append((i + 1, "мимо ❌"))

        throws_text = "\n".join([f"Бросок #{i} – {res}" for i, res in results])
        quote_msg = f"Результаты игры 🏀 {count} бросков\n\n{throws_text}"
        await bot.send_message(user_id, f"```{quote_msg}```", parse_mode="Markdown")

        if hits == count:
            await asyncio.sleep(0.5)
            await bot.send_message(user_id, "🎉 Отличная игра! Все броски были страйками!")
            await asyncio.sleep(0.5)
            await bot.send_message(user_id, "🎁 Ваш подарок уже в пути...")

            if GIFT_IDS:
                gift_to_send = random.choice(GIFT_IDS)
                try:
                    await bot.send_gift(
                        chat_id=user_id,
                        gift_id=gift_to_send,
                        text="🏆",
                        pay_for_upgrade=False
                    )
                    record_gift_sent(user_id, gift_to_send)
                except Exception as e:
                    logging.error(f"Ошибка отправки подарка {gift_to_send} пользователю {user_id}: {e}")

            await asyncio.sleep(0.5)
            await bot.send_message(user_id, "")
        else:
            await bot.send_message(user_id, "Попробуйте ещё раз! В следующий раз повезёт.")

        stars = get_user_stars(user_id)
        await bot.send_message(user_id, f"💰 Баланс: {stars} ⭐️", reply_markup=throw_keyboard(user_id))

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

async def send_broadcast(state: FSMContext, message: types.Message):
    data = await state.get_data()
    media_msg = data.get("media")
    content = data.get("content")
    button_text = data.get("button_text")
    button_url = data.get("button_url")

    kb = None
    if button_text and button_url:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=button_text, url=button_url)]
        ])

    users = []
    with sqlite3.connect("basketball_bot.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        users = [row[0] for row in cursor.fetchall()]

    for user_id in users:
        try:
            if media_msg:
                if media_msg.photo:
                    await bot.send_photo(chat_id=user_id, photo=media_msg.photo[-1].file_id, caption=content, reply_markup=kb)
                elif media_msg.video:
                    await bot.send_video(chat_id=user_id, video=media_msg.video.file_id, caption=content, reply_markup=kb)
                elif media_msg.sticker:
                    await bot.send_sticker(chat_id=user_id, sticker=media_msg.sticker.file_id)
                    if content:
                        await bot.send_message(chat_id=user_id, text=content, reply_markup=kb)
                elif media_msg.animation:
                    await bot.send_animation(chat_id=user_id, animation=media_msg.animation.file_id, caption=content, reply_markup=kb)
                else:
                    await bot.send_message(chat_id=user_id, text=content, reply_markup=kb)
            else:
                await bot.send_message(chat_id=user_id, text=content, reply_markup=kb)
        except Exception as e:
            logging.error(f"Ошибка при рассылке пользователю {user_id}: {e}")

    await message.answer("✅ Рассылка завершена.")
    await state.clear()

async def send_menu_with_admin(user_id: int, chat_id: int):
    text = (
        "🏀 Баскет за подарки\n\n"
        "Попади в корзину каждым броском\n"
        "и получи один из крутых подарков 🧸💝🎁🌹\n\n"
        f"💰 Баланс: {get_user_stars(user_id)} ⭐️"
    )
    await bot.send_message(chat_id=chat_id, text=text, reply_markup=throw_keyboard(user_id))

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main()) 