import os
import asyncio
import logging
import random
import datetime
import sqlite3

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import StatesGroup, State
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gift_bot")

API_TOKEN = os.getenv("BOT_TOKEN")
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

DB_PATH = "gift_bot.db"
PLACEHOLDER_IMAGE_URL = "https://media1.tenor.com/m/_wvp0xzvQQgAAAAd/ape-monkey.gif"

# -------------------- DATABASE --------------------
def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                received_gift INTEGER DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS gifts (
                gift_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                method TEXT DEFAULT 'auto',
                total_count INTEGER DEFAULT 1
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS gift_codes (
                code TEXT PRIMARY KEY,
                gift_id TEXT
            )
        """)
        conn.commit()

def add_user(user_id: int):
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()

def has_received_gift(user_id: int) -> bool:
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT received_gift FROM users WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        return bool(row and row["received_gift"] == 1)

def mark_gift_received(user_id: int):
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO users (user_id, received_gift) VALUES (?, 1)", (user_id,))
        cur.execute("UPDATE users SET received_gift=1 WHERE user_id=?", (user_id,))
        conn.commit()

def add_payment(user_id: int, amount: int):
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO payments (user_id, amount) VALUES (?, ?)", (user_id, amount))
        conn.commit()

def add_gift(gift_id: str, name: str, method: str = "auto", total_count: int = 1):
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO gifts (gift_id, name, method, total_count) 
            VALUES (?, ?, ?, ?)
        """, (gift_id, name, method, total_count))
        conn.commit()

def get_available_auto_gifts():
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM gifts WHERE method='auto' AND total_count > 0")
        return cur.fetchall()

def get_gift_by_id(gift_id: str):
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM gifts WHERE gift_id=?", (gift_id,))
        return cur.fetchone()

def set_gift_total(gift_id: str, total: int):
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE gifts SET total_count=? WHERE gift_id=?", (total, gift_id))
        conn.commit()

def set_gift_method(gift_id: str, method: str):
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE gifts SET method=? WHERE gift_id=?", (method, gift_id))
        conn.commit()

def decrease_gift_count(gift_id: str):
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE gifts SET total_count = total_count - 1 WHERE gift_id = ?", (gift_id,))
        conn.commit()

def add_gift_code(code: str, gift_id: str):
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO gift_codes (code, gift_id) VALUES (?, ?)", (code, gift_id))
        conn.commit()

def get_gift_by_code(code: str):
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT gift_id FROM gift_codes WHERE code=?", (code,))
        row = cur.fetchone()
        return row["gift_id"] if row else None

def reset_raffle():
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET received_gift=0")
        conn.commit()

# -------------------- FSM STATES --------------------
class AdminStates(StatesGroup):
    awaiting_broadcast = State()
    awaiting_gift_name = State()
    awaiting_gift_id = State()
    awaiting_gift_method = State()
    awaiting_gift_total = State()
    awaiting_choose_gift_for_code = State()
    awaiting_code_quantity = State()
    awaiting_code_text = State()
    awaiting_redeem_code = State()

# -------------------- BOT --------------------
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

gift_enabled = True
redeem_enabled = False

# -------------------- ADMIN PANEL --------------------
def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"),
            InlineKeyboardButton(text="💰 Пополнение", callback_data="admin_topup")
        ],
        [
            InlineKeyboardButton(text="🎁 Добавить подарок", callback_data="admin_add_gift"),
            InlineKeyboardButton(text="🎟 Добавить код", callback_data="admin_add_code")
        ],
        [
            InlineKeyboardButton(text="👀 Просмотр подарков", callback_data="admin_view_gifts"),
            InlineKeyboardButton(text="▶️/⏸️ Выдача подарков", callback_data="admin_toggle_gifts")
        ],
        [
            InlineKeyboardButton(text="🎯 Выдача по коду", callback_data="admin_redeem_mode"),
            InlineKeyboardButton(text="🔄 Сброс розыгрыша", callback_data="admin_reset_raffle")
        ]
    ])

# -------------------- START --------------------
@dp.message(CommandStart())
async def start_handler(message: types.Message, state: FSMContext):
    global gift_enabled, redeem_enabled
    user_id = message.from_user.id
    add_user(user_id)

    await message.answer(f"🎯 Добро пожаловать, {message.from_user.full_name}!")

    if user_id == ADMIN_ID:
        await message.answer("🔧 Панель администратора:", reply_markup=admin_panel_keyboard())

    if gift_enabled and not has_received_gift(user_id):
        gifts = get_available_auto_gifts()
        if gifts:
            gift = random.choice(gifts)
            try:
                await bot.send_gift(
                    chat_id=user_id,
                    gift_id=gift["gift_id"],
                    text=f"🏆 Поздравляем! {gift['name']}",
                    pay_for_upgrade=False
                )
                decrease_gift_count(gift["gift_id"])
                mark_gift_received(user_id)
                if CHANNEL_ID != 0:
                    username = f"@{message.from_user.username}" if message.from_user.username else "Нет"
                    now_msk = (datetime.datetime.utcnow() + datetime.timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S MSK")
                    await bot.send_message(
                        CHANNEL_ID,
                        f"🎁 ВЫИГРЫШ!\n\n"
                        f"👤 Пользователь: {message.from_user.full_name}\n"
                        f"🏷 Username: {username}\n"
                        f"🆔 ID: {user_id}\n"
                        f"🎁 Получил: {gift['name']}\n"
                        f"📅 Время: {now_msk}"
                    )
            except Exception as e:
                logger.error(f"Ошибка при авто-выдаче подарка {gift['name']} пользователю {user_id}: {e}")

    elif redeem_enabled and not has_received_gift(user_id):
        await message.answer("🔑 Введите код для получения подарка:")
        await state.set_state(AdminStates.awaiting_redeem_code)

# -------------------- ADMIN CALLBACK HANDLER --------------------
@dp.callback_query(F.data.startswith("admin_"))
async def admin_menu_handler(callback: types.CallbackQuery, state: FSMContext):
    global gift_enabled, redeem_enabled
    user_id = callback.from_user.id
    if user_id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    if callback.data == "admin_broadcast":
        await callback.message.answer("Отправьте сообщение для рассылки.")
        await state.set_state(AdminStates.awaiting_broadcast)

    elif callback.data == "admin_topup":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Пополнить на 100 XTR", callback_data="topup_100")],
            [InlineKeyboardButton(text="Пополнить на 150 XTR", callback_data="topup_150")]
        ])
        await callback.message.answer("Выберите сумму пополнения:", reply_markup=kb)

    elif callback.data == "admin_add_gift":
        await callback.message.answer("Введите название подарка:")
        await state.set_state(AdminStates.awaiting_gift_name)

    elif callback.data == "admin_add_code":
        with db_connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT gift_id, name FROM gifts ORDER BY name COLLATE NOCASE")
            gifts = cur.fetchall()
        if not gifts:
            await callback.message.answer("❌ Сначала добавьте хотя бы один подарок.")
            return
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=g["name"], callback_data=f"choose_gift_{g['gift_id']}")]
                for g in gifts
            ]
        )
        await callback.message.answer("🎁 Выберите подарок для выдачи по коду:", reply_markup=kb)

    elif callback.data == "admin_view_gifts":
        with db_connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT gift_id, name, total_count, method FROM gifts ORDER BY name COLLATE NOCASE")
            rows = cur.fetchall()
        if not rows:
            await callback.message.answer("Список подарков пуст.")
        else:
            text = "🎁 Подарки:\n" + "\n".join([
                f"{r['name']} (ID: {r['gift_id']}), осталось: {r['total_count']} | метод: {('Авто' if r['method']=='auto' else 'По коду')}"
                for r in rows
            ])
            await callback.message.answer(text)

    elif callback.data == "admin_toggle_gifts":
        gift_enabled = not gift_enabled
        redeem_enabled = False
        status = "включена" if gift_enabled else "отключена"
        await callback.message.answer(f"🎯 Автовыдача подарков теперь {status}")

    elif callback.data == "admin_redeem_mode":
        redeem_enabled = not redeem_enabled
        gift_enabled = False
        status = "активна" if redeem_enabled else "выключена"
        await callback.message.answer(f"🎯 Выдача по коду {status}\n(попросите пользователей ввести код)")

    elif callback.data == "admin_reset_raffle":
        reset_raffle()
        gift_enabled = False
        redeem_enabled = False
        await callback.message.answer("🔄 Розыгрыш сброшен, выдача остановлена.")

# -------------------- ДОБАВЛЕНИЕ ПОДАРКА --------------------
@dp.message(AdminStates.awaiting_gift_name)
async def add_gift_name_handler(message: types.Message, state: FSMContext):
    await state.update_data(gift_name=message.text.strip())
    await message.answer("Введите ID подарка (gift_id):")
    await state.set_state(AdminStates.awaiting_gift_id)

@dp.message(AdminStates.awaiting_gift_id)
async def add_gift_id_handler(message: types.Message, state: FSMContext):
    await state.update_data(gift_id=message.text.strip())
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎯 Автоматически", callback_data="method_auto"),
            InlineKeyboardButton(text="🔑 По коду", callback_data="method_code")
        ]
    ])
    await message.answer("Выберите метод выдачи:", reply_markup=kb)
    await state.set_state(AdminStates.awaiting_gift_method)

@dp.callback_query(F.data.startswith("method_"))
async def choose_gift_method(callback: types.CallbackQuery, state: FSMContext):
    method = callback.data.split("_", 1)[1]
    await state.update_data(gift_method=method)
    await callback.message.answer("Введите количество подарков:")
    await state.set_state(AdminStates.awaiting_gift_total)

@dp.message(AdminStates.awaiting_gift_total)
async def add_gift_total_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    gift_name = data.get("gift_name")
    gift_id = data.get("gift_id")
    gift_method = data.get("gift_method")
    try:
        total = int(message.text.strip())
        if total < 0:
            raise ValueError
        add_gift(gift_id=gift_id, name=gift_name, method=gift_method, total_count=total)
        await message.answer(
            f"✅ Подарок '{gift_name}' (ID {gift_id}) добавлен: {total} шт., метод: {'Авто' if gift_method=='auto' else 'По коду'}."
        )
    except Exception:
        await message.answer("❌ Некорректное число. Попробуйте ещё раз командой в админке.")
    await state.clear()

# -------------------- ПРИВЯЗКА КОДА К ПОДАРКУ --------------------
@dp.callback_query(F.data.startswith("choose_gift_"))
async def choose_gift_for_code(callback: types.CallbackQuery, state: FSMContext):
    gift_id = callback.data.split("_", 2)[2]
    gift = get_gift_by_id(gift_id)
    if not gift:
        await callback.message.answer("❌ Подарок не найден.")
        return
    await state.update_data(selected_gift=gift_id)
    await callback.message.answer(f"Выбрано: {gift['name']}\nВведите количество подарков для этого кода:")
    await state.set_state(AdminStates.awaiting_code_quantity)

@dp.message(AdminStates.awaiting_code_quantity)
async def set_code_quantity(message: types.Message, state: FSMContext):
    try:
        total = int(message.text.strip())
        if total <= 0:
            raise ValueError
    except Exception:
        await message.answer("❌ Введите положительное целое число.")
        return
    await state.update_data(code_total=total)
    await message.answer("Теперь отправьте текст кода (например: SUPER2025):")
    await state.set_state(AdminStates.awaiting_code_text)

@dp.message(AdminStates.awaiting_code_text)
async def set_code_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    code = message.text.strip()
    gift_id = data.get("selected_gift")
    total = int(data.get("code_total", 0))
    if not gift_id or not code or total <= 0:
        await message.answer("❌ Ошибка данных. Начните заново через «Добавить код».")
        await state.clear()
        return
    add_gift_code(code, gift_id)
    set_gift_total(gift_id, total)
    set_gift_method(gift_id, "code")
    await message.answer(f"✅ Код «{code}» установлен для подарка (ID {gift_id}). Остаток: {total} шт. Метод: По коду.")
    await state.clear()

# -------------------- BROADCAST --------------------
@dp.message(AdminStates.awaiting_broadcast)
async def broadcast_handler(message: types.Message, state: FSMContext):
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users")
        users = [row["user_id"] for row in cur.fetchall()]
    success, fail = 0, 0
    for uid in users:
        try:
            if message.text:
                await bot.send_message(uid, message.text)
            elif message.photo:
                await bot.send_photo(uid, message.photo[-1].file_id, caption=message.caption)
            elif message.sticker:
                await bot.send_sticker(uid, message.sticker.file_id)
            elif message.animation:
                await bot.send_animation(uid, message.animation.file_id, caption=message.caption)
            elif message.video:
                await bot.send_video(uid, message.video.file_id, caption=message.caption)
            success += 1
        except Exception as e:
            logger.warning(f"Не удалось отправить пользователю {uid}: {e}")
            fail += 1
        await asyncio.sleep(0.05)
    await message.answer(f"✅ Рассылка завершена.\n📤 Успешно: {success}\n⛔ Ошибки: {fail}")
    await state.clear()

# -------------------- TOPUP --------------------
@dp.callback_query(F.data.startswith("topup_"))
async def topup_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    amount = int(callback.data.split("_")[1])
    await bot.send_invoice(
        chat_id=user_id,
        title=f"Пополнение на {amount} XTR",
        description=f"Пополнение баланса на {amount} XTR",
        payload=f"topup_{amount}",
        provider_token=PROVIDER_TOKEN,
        currency="XTR",
        prices=[LabeledPrice(label=f"Пополнение {amount} XTR", amount=amount)],
        start_parameter=f"topup_{amount}"
    )

@dp.pre_checkout_query()
async def precheckout(pre_q: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_q.id, ok=True)

@dp.message(F.content_type == "successful_payment")
async def successful_payment_handler(message: types.Message):
    amount = message.successful_payment.total_amount
    add_payment(message.from_user.id, amount)
    await message.answer(f"✅ Пополнение успешно! Сумма: {amount} XTR")

# -------------------- REDEEM CODE --------------------
@dp.message(AdminStates.awaiting_redeem_code)
async def redeem_code_handler(message: types.Message, state: FSMContext):
    global redeem_enabled
    code = message.text.strip()

    gift_id = get_gift_by_code(code)
    if not gift_id:
        await message.answer("❌ Неверный код.")
        await state.clear()
        return

    if has_received_gift(message.from_user.id):
        await message.answer("⚠️ Вы уже получали подарок.")
        await state.clear()
        return

    gift = get_gift_by_id(gift_id)
    if not gift or gift["total_count"] <= 0:
        redeem_enabled = False
        await message.answer("😢 Упс, не успел! Подарков не осталось.\nСледите за нашими ботами — скоро будут коды.")
        await asyncio.sleep(2)
        await bot.send_photo(
            chat_id=message.chat.id,
            photo=PLACEHOLDER_IMAGE_URL,
            caption="🔔 Подпишитесь, чтобы не пропустить новые подарки!"
        )
        await bot.send_message(ADMIN_ID, "⚠️ Подарки закончились. Режим выдачи по коду выключен.")
        await state.clear()
        return

    try:
        await bot.send_gift(
            chat_id=message.from_user.id,
            gift_id=gift_id,
            text=f"🏆 Вы получили: {gift['name']}!",
            pay_for_upgrade=False
        )
        mark_gift_received(message.from_user.id)
        decrease_gift_count(gift_id)
        await message.answer("✅ Подарок успешно выдан!")

        if CHANNEL_ID != 0:
            username = f"@{message.from_user.username}" if message.from_user.username else "Нет"
            now_msk = (datetime.datetime.utcnow() + datetime.timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S MSK")
            await bot.send_message(
                CHANNEL_ID,
                f"🎁 ВЫИГРЫШ ПО КОДУ!\n\n"
                f"👤 Пользователь: {message.from_user.full_name}\n"
                f"🏷 Username: {username}\n"
                f"🆔 ID: {message.from_user.id}\n"
                f"🎁 Получил: {gift['name']}\n"
                f"📅 Время: {now_msk}\n"
                f"🔑 Код: {code}"
            )

        updated = get_gift_by_id(gift_id)
        if updated and updated["total_count"] <= 0:
            redeem_enabled = False
            await bot.send_message(ADMIN_ID, "⚠️ Подарки закончились. Режим выдачи по коду выключен.")
    except Exception as e:
        await message.answer(f"❌ Ошибка при выдаче подарка: {e}")

    await state.clear()

# -------------------- RUN --------------------
if __name__ == "__main__":
    init_db()
    asyncio.run(dp.start_polling(bot))