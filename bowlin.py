import sqlite3
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ContentType
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv("BOT_TOKEN")
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
GIFT_ID = os.getenv("GIFT_ID")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Стоимость наборов шаров
COSTS = {
    3: 1,
    2: 4,
    1: 1,
}

# Инициализация базы данных
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

# Получить баланс пользователя
def get_user_stars(user_id):
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

# Обновить баланс пользователя
def set_user_stars(user_id, stars):
    with sqlite3.connect("basketball_bot.db") as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET stars = ? WHERE user_id = ?", (stars, user_id))
        conn.commit()

# Установить реферала, если нет
def set_referrer_if_not_exists(user_id, referrer_id):
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

# Добавить запись о платеже
def add_payment(amount):
    with sqlite3.connect("basketball_bot.db") as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO payments (amount) VALUES (?)", (amount,))
        conn.commit()

# Записать отправку подарка
def record_gift_sent(user_id, gift_id):
    with sqlite3.connect("basketball_bot.db") as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO gifts_sent (user_id, gift_id) VALUES (?, ?)", (user_id, gift_id))
        conn.commit()

# Получить статистику для админа
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

# Клавиатура для выбора наборов бросков
def throw_keyboard(user_id):
    builder = InlineKeyboardBuilder()
    for count in sorted(COSTS.keys(), reverse=True):
        suffix = "шара"
        builder.button(
            text=f"🎳 {count} {suffix} • {COSTS[count]}⭐️",
            callback_data=f"throw_{count}"
        )
    builder.button(text="+ 3 ⭐️ за друга", callback_data=f"referral_{user_id}")
    builder.button(text="🏀 для подарков 🎁", url="https://t.me/bankstars_support_bot")
    builder.adjust(2)
    return builder.as_markup()

# Клавиатура админ панели
def admin_panel_keyboard():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
         InlineKeyboardButton("📢 Отправить сообщение", callback_data="admin_broadcast")]
    ])
    return kb

# Отправка меню с балансом и админ панелью если админ
async def send_menu_with_admin(user_id: int, chat_id: int):
    stars = get_user_stars(user_id)
    await bot.send_message(
        chat_id,
        
        text = (
        
        "🎳 боулинг за подарки оформи страйк каждым броском и получи крутой подарок 🧸💝🎁🌹\n\n"
        f"💰 Баланс: {stars} ⭐️",
        
        reply_markup=throw_keyboard(user_id)
    )
    if user_id == ADMIN_ID and ADMIN_ID != 0:
        await bot.send_message(
            chat_id,
            "⚙️ Админ панель:",
            reply_markup=admin_panel_keyboard()
        )

# Состояния для рассылки
class BroadcastStates(StatesGroup):
    waiting_media = State()
    waiting_content = State()
    waiting_button_text = State()
    waiting_button_url = State()

# Обработчик /start с реферальным параметром
@dp.message(Command("start"))
async def start_handler_with_referral(message: types.Message, command: CommandObject):
    args = command.args
    user_id = message.from_user.id
    if args and args.isdigit():
        ref_id = int(args)
        set_referrer_if_not_exists(user_id, ref_id)

    await send_menu_with_admin(user_id, message.chat.id)

# Обработка реферального меню
@dp.callback_query(F.data.startswith("referral_"))
async def process_referral(callback_query: types.CallbackQuery):
    inviter_id = int(callback_query.data.split("_")[1])
    bot_info = await bot.get_me()
    url = f"https://t.me/{bot_info.username}?start={inviter_id}"

    text = (
        "🎳 Бросай вызов удаче в игре боулинг!\n"
        "🎁 Выигрывай классные подарки за каждый страйк! 🎁\n\n"
        "👫 Пригласи друзей:\n"
        "— За каждого друга +3 ⭐️\n\n"
        "🔥 Не упусти свой шанс!\n"
        f"{url}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться", switch_inline_query=text)],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")]
    ])

    await callback_query.message.answer(text, reply_markup=kb)
    await callback_query.answer()

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback_query: types.CallbackQuery):
    await send_menu_with_admin(callback_query.from_user.id, callback_query.message.chat.id)
    await callback_query.answer()

# Обработка нажатия на набор шаров для броска
@dp.callback_query(F.data.startswith("throw_"))
async def process_throw(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    count = int(callback_query.data.split("_")[1])
    price_stars = COSTS.get(count)
    if price_stars is None:
        await callback_query.answer("⛔ Некорректный набор шаров")
        return

    await bot.send_invoice(
        chat_id=user_id,
        title=f"{count} шаров для броска",
        description=f"🏆 Набор для страйка - {count} бросков",
        payload=f"bowling_{count}",
        provider_token=PROVIDER_TOKEN,
        currency="XTR",
        prices=[LabeledPrice(label=f"{count} бросков", amount=price_stars)],
        start_parameter=f"bowling_{count}"
    )
    await callback_query.answer()

# Подтверждение оплаты
@dp.pre_checkout_query()
async def checkout(pre_q: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_q.id, ok=True)

# Обработка успешной оплаты и бросков
@dp.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def successful_payment(msg: types.Message):
    user_id = msg.from_user.id
    payload = msg.successful_payment.invoice_payload

    if payload.startswith("bowling_"):
        count = int(payload.split("_")[1])
        results = []
        hits = 0

        for i in range(count):
            dice = await bot.send_dice(user_id, emoji="🎳")
            await asyncio.sleep(2)
            if dice.dice.value >= 6:
                results.append((i + 1, "страйк ✅"))
                hits += 1
            else:
                results.append((i + 1, "неудача ❌"))

        throws_text = "\n".join([f"Бросок #{i} – {res}" for i, res in results])
        quote_msg = f"Результаты игры 🎳 {count} бросков\n\n{throws_text}"
        await bot.send_message(user_id, f"```{quote_msg}```", parse_mode="Markdown")

        if hits == count:
            await asyncio.sleep(0.5)
            await bot.send_message(user_id, "🎉 Поздравляем! Все броски были страйками!")
            await asyncio.sleep(0.5)
            await bot.send_message(user_id, "🎁 Ваш подарок готовится...")

            if GIFT_ID:
                try:
                    await bot.send_gift(
                        chat_id=user_id,
                        gift_id=GIFT_ID,
                        text="🧸",
                        pay_for_upgrade=False
                    )
                    record_gift_sent(user_id, GIFT_ID)
                except Exception as e:
                    logging.error(f"Ошибка отправки подарка пользователю {user_id}: {e}")

            await asyncio.sleep(0.5)
            await bot.send_message(user_id, "🧸")
        else:
            await bot.send_message(user_id, "В этот раз не повезло. Попробуем ещё раз?")

        stars = get_user_stars(user_id)
        await bot.send_message(user_id, f"💰 Баланс: {stars} ⭐️", reply_markup=throw_keyboard(user_id))

# Обработка нажатий админских кнопок
@dp.callback_query(F.data.startswith("admin_"))
async def admin_menu_handler(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    data = callback.data
    if data == "admin_stats":
        users_count, income, expense = get_stats()
        text = (
            f"📊 Статистика бота:\n"
            f"Пользователей: {users_count}\n"
            f"Доход: {income} XTR\n"
            f"Расход: {expense} XTR"
        )
        await callback.message.answer(text)
        await callback.answer()
    elif data == "admin_broadcast":
        await callback.message.answer("📝 Пришли мне медиа (фото, видео, гиф или документ) для рассылки, или /skip чтобы пропустить")
        await state.set_state(BroadcastStates.waiting_media)
        await callback.answer()

# Получаем медиа для рассылки
@dp.message(BroadcastStates.waiting_media, F.content_type.in_({ContentType.PHOTO, ContentType.VIDEO, ContentType.DOCUMENT, ContentType.ANIMATION}))
async def broadcast_receive_media(message: types.Message, state: FSMContext):
    if message.photo:
        file_id = message.photo[-1].file_id
        media_type = "photo"
    elif message.video:
        file_id = message.video.file_id
        media_type = "video"
    elif message.animation:
        file_id = message.animation.file_id
        media_type = "animation"
    else:
        file_id = message.document.file_id
        media_type = "document"

    await state.update_data(media_file_id=file_id, media_type=media_type)
    await message.answer("Отлично! Теперь пришли текст сообщения для рассылки.")
    await state.set_state(BroadcastStates.waiting_content)

# Пропускаем медиа, если /skip
@dp.message(BroadcastStates.waiting_media, F.text == "/skip")
async def broadcast_skip_media(message: types.Message, state: FSMContext):
    await message.answer("Хорошо, медиа не будет. Пришли текст сообщения для рассылки.")
    await state.set_state(BroadcastStates.waiting_content)

# Получаем текст рассылки
@dp.message(BroadcastStates.waiting_content, F.text)
async def broadcast_receive_text(message: types.Message, state: FSMContext):
    await state.update_data(broadcast_text=message.text)
    await message.answer("Пришли текст кнопки для сообщения, или /skip чтобы отправить без кнопки.")
    await state.set_state(BroadcastStates.waiting_button_text)

# Получаем текст кнопки или пропускаем
@dp.message(BroadcastStates.waiting_button_text, F.text)
async def broadcast_receive_button_text(message: types.Message, state: FSMContext):
    text = message.text
    if text == "/skip":
        await state.update_data(button_text=None, button_url=None)
        await send_broadcast(message, state)
    else:
        await state.update_data(button_text=text)
        await message.answer("Теперь пришли URL для кнопки.")
        await state.set_state(BroadcastStates.waiting_button_url)

# Получаем URL кнопки и отправляем рассылку
@dp.message(BroadcastStates.waiting_button_url, F.text)
async def broadcast_receive_button_url(message: types.Message, state: FSMContext):
    url = message.text
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer("⚠️ Неверный URL. Попробуй еще раз.")
        return
    await state.update_data(button_url=url)
    await send_broadcast(message, state)

# Функция отправки рассылки всем пользователям
async def send_broadcast(message: types.Message, state: FSMContext):
    data = await state.get_data()
    text = data.get("broadcast_text", "")
    media_file_id = data.get("media_file_id")
    media_type = data.get("media_type")
    button_text = data.get("button_text")
    button_url = data.get("button_url")

    keyboard = None
    if button_text and button_url:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=button_text, url=button_url)]
        ])

    with sqlite3.connect("basketball_bot.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        users = [row[0] for row in cursor.fetchall()]

    sent_count = 0
    failed_count = 0

    for user_id in users:
        try:
            if media_file_id:
                if media_type == "photo":
                    await bot.send_photo(user_id, photo=media_file_id, caption=text, reply_markup=keyboard)
                elif media_type == "video":
                    await bot.send_video(user_id, video=media_file_id, caption=text, reply_markup=keyboard)
                elif media_type == "animation":
                    await bot.send_animation(user_id, animation=media_file_id, caption=text, reply_markup=keyboard)
                else:
                    await bot.send_document(user_id, document=media_file_id, caption=text, reply_markup=keyboard)
            else:
                await bot.send_message(user_id, text, reply_markup=keyboard)
            sent_count += 1
        except Exception as e:
            logging.error(f"Ошибка при отправке пользователю {user_id}: {e}")
            failed_count += 1

    await message.answer(f"Рассылка завершена!\nОтправлено: {sent_count}\nНе доставлено: {failed_count}")
    await state.clear()

if __name__ == "__main__":
    init_db()
    dp.run_polling(bot)