import asyncio
import sqlite3
import os
import logging
from typing import Optional
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, InputMediaPhoto, InputMediaDocument
)
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0")) if os.getenv("ADMIN_ID") else 0
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0")) if os.getenv("CHANNEL_ID") else 0

if not BOT_TOKEN:
    logger.error("BOT_TOKEN не найден в переменных окружения!")
    exit(1)

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_number INTEGER UNIQUE,
    user_id INTEGER,
    username TEXT,
    stars INTEGER,
    price REAL,
    destination TEXT,
    proof_file TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'pending'
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

conn.commit()

def get_setting(key: str, default: str = "") -> str:
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    return row[0] if row else default

def set_setting(key: str, value: str):
    cursor.execute("REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()

if not get_setting("price_under_500"):
    set_setting("price_under_500", "1,40")

if not get_setting("price_over_500"):
    set_setting("price_over_500", "1,35")

if not get_setting("review_group"):
    set_setting("review_group", "")

if not get_setting("requisites"):
    set_setting("requisites", "Переведите на карту 1234 5678 9012 3456, Иван Иванов (Сбербанк)")

class OrderStars(StatesGroup):
    WaitingForCustomAmount = State()
    WaitingForUsername = State()
    WaitingForPaymentProof = State()

class AdminState(StatesGroup):
    WaitingForNewPriceUnder500 = State()
    WaitingForNewPriceOver500 = State()
    WaitingForNewRequisites = State()
    WaitingForBroadcastText = State()
    WaitingForBroadcastButtonText = State()
    WaitingForBroadcastButtonURL = State()
    WaitingForBroadcastMedia = State()
    WaitingForReviewGroupLink = State()

def price_str_to_float(price_str: str) -> float:
    return float(price_str.replace(',', '.'))

def float_to_price_str(price_float: float) -> str:
    return f"{price_float:.2f}".replace('.', ',')

def get_price(stars: int) -> str:
    price_under_500 = get_setting("price_under_500", "1,40")
    price_over_500 = get_setting("price_over_500", "1,35")
    
    if stars >= 500:
        price_per_star = price_str_to_float(price_over_500)
    else:
        price_per_star = price_str_to_float(price_under_500)
    
    total = stars * price_per_star
    return float_to_price_str(total)

def save_user(user_id: int):
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()

def main_menu(is_admin: bool = False):
    keyboard = [
        [
            InlineKeyboardButton(text="⭐ 50", callback_data="stars_50"),
            InlineKeyboardButton(text="⭐ 100", callback_data="stars_100"),
            InlineKeyboardButton(text="⭐ 150", callback_data="stars_150")
        ],
        [
            InlineKeyboardButton(text="⭐ 200", callback_data="stars_200"),
            InlineKeyboardButton(text="⭐ 250", callback_data="stars_250"),
            InlineKeyboardButton(text="⭐ 300", callback_data="stars_300")
        ],
        [
            InlineKeyboardButton(text="⭐ 400", callback_data="stars_400"),
            InlineKeyboardButton(text="⭐ 500", callback_data="stars_500"),
            InlineKeyboardButton(text="⭐ 1000", callback_data="stars_1000")
        ],
        [InlineKeyboardButton(text="🔢 Указать своё количество", callback_data="custom_amount")],
        [InlineKeyboardButton(text="💰 Прайс-лист", callback_data="price_list")]
    ]
    
    if is_admin:
        keyboard.append([InlineKeyboardButton(text="⚙️ Админ-панель", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
            InlineKeyboardButton(text="💰 Цены", callback_data="admin_prices")
        ],
        [
            InlineKeyboardButton(text="🏦 Реквизиты", callback_data="admin_requisites"),
            InlineKeyboardButton(text="📝 Отзывы", callback_data="admin_reviews")
        ],
        [
            InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"),
            InlineKeyboardButton(text="📋 Заказы", callback_data="admin_orders")
        ],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
    ])

def price_settings_menu():
    price_under_500 = get_setting("price_under_500", "1,40")
    price_over_500 = get_setting("price_over_500", "1,35")
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"До 500⭐: {price_under_500}₽", callback_data="edit_price_under_500")],
        [InlineKeyboardButton(text=f"От 500⭐: {price_over_500}₽", callback_data="edit_price_over_500")],
        [InlineKeyboardButton(text="🔙 Админ-панель", callback_data="admin_panel")]
    ])

def broadcast_options_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 Только текст", callback_data="broadcast_text_only"),
            InlineKeyboardButton(text="🔗 Текст + кнопка", callback_data="broadcast_text_button")
        ],
        [
            InlineKeyboardButton(text="🖼 Фото + текст", callback_data="broadcast_photo"),
            InlineKeyboardButton(text="🖼➕ Фото + текст + кнопка", callback_data="broadcast_photo_button")
        ],
        [
            InlineKeyboardButton(text="🎬 Видео + текст", callback_data="broadcast_video"),
            InlineKeyboardButton(text="🎬➕ Видео + текст + кнопка", callback_data="broadcast_video_button")
        ],
        [
            InlineKeyboardButton(text="🎭 Стикер + текст", callback_data="broadcast_sticker"),
            InlineKeyboardButton(text="🎭➕ Стикер + текст + кнопка", callback_data="broadcast_sticker_button")
        ],
        [
            InlineKeyboardButton(text="🎨 GIF + текст", callback_data="broadcast_animation"),
            InlineKeyboardButton(text="🎨➕ GIF + текст + кнопка", callback_data="broadcast_animation_button")
        ],
        [
            InlineKeyboardButton(text="📎 Документ + текст", callback_data="broadcast_document"),
            InlineKeyboardButton(text="📎➕ Документ + текст + кнопка", callback_data="broadcast_document_button")
        ],
        [InlineKeyboardButton(text="🔙 Админ-панель", callback_data="admin_panel")]
    ])

def order_confirmation_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💸 Оплачено", callback_data="payment_done"),
            InlineKeyboardButton(text="🔄 Изменить username", callback_data="change_username")
        ],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
    ])

def back_to_admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Админ-панель", callback_data="admin_panel")]
    ])

def back_to_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
    ])

@router.message(CommandStart())
async def start_command(message: Message, state: FSMContext):
    if not message.from_user:
        return
        
    save_user(message.from_user.id)
    await state.clear()
    
    is_admin = message.from_user.id == ADMIN_ID
    welcome_text = (
        f"🌟 <b>Добро пожаловать, {message.from_user.full_name}!</b>\n\n"
        f"🎯 Выберите количество звёзд для покупки:\n"
        f"⚡ Быстрая доставка в течение 1-2 минут\n"
        f"🔒 Безопасная оплата\n"
        f"⭐ Лучшие цены на рынке"
    )
    
    await message.answer(welcome_text, reply_markup=main_menu(is_admin))
    logger.info(f"Пользователь {message.from_user.id} запустил бота")

@router.callback_query(F.data == "main_menu")
async def show_main_menu(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user or not callback.message:
        return
        
    await state.clear()
    is_admin = callback.from_user.id == ADMIN_ID
    
    welcome_text = (
        f"🌟 <b>Главное меню</b>\n\n"
        f"🎯 Выберите количество звёзд для покупки:\n"
        f"⚡ Быстрая доставка в течение 1-2 минут\n"
        f"🔒 Безопасная оплата\n"
        f"⭐ Лучшие цены на рынке"
    )
    
    await callback.message.edit_text(welcome_text, reply_markup=main_menu(is_admin))
    await callback.answer()

@router.callback_query(F.data.startswith("stars_"))
async def select_stars(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user or not callback.message or not callback.data:
        return
        
    stars = int(callback.data.split("_")[1])
    await state.update_data(stars=stars)
    
    price = get_price(stars)
    text = (
        f"⭐ <b>Выбрано: {stars} звёзд</b>\n"
        f"💰 <b>Стоимость: {price} руб.</b>\n\n"
        f"📝 Укажите @username получателя:"
    )
    
    await callback.message.edit_text(text)
    await state.set_state(OrderStars.WaitingForUsername)
    await callback.answer()

@router.callback_query(F.data == "custom_amount")
async def custom_amount(callback: CallbackQuery, state: FSMContext):
    if not callback.message:
        return
        
    text = (
        f"🔢 <b>Свое количество звёзд</b>\n\n"
        f"📝 Введите нужное количество звёзд\n"
        f"(минимум 50, максимум 10000):"
    )
    
    await callback.message.edit_text(text)
    await state.set_state(OrderStars.WaitingForCustomAmount)
    await callback.answer()

@router.callback_query(F.data == "price_list")
async def show_price_list(callback: CallbackQuery):
    if not callback.message:
        return
        
    price_under_500 = get_setting("price_under_500", "1,40")
    price_over_500 = get_setting("price_over_500", "1,35")
    
    text = (
        f"💰 <b>Прайс-лист</b>\n\n"
        f"⭐ До 500 звёзд: <b>{price_under_500} руб/звезда</b>\n"
        f"⭐ От 500 звёзд: <b>{price_over_500} руб/звезда</b>\n\n"
        f"📊 <b>Примеры:</b>\n"
        f"• 50⭐ = {get_price(50)} руб.\n"
        f"• 100⭐ = {get_price(100)} руб.\n"
        f"• 500⭐ = {get_price(500)} руб.\n"
        f"• 1000⭐ = {get_price(1000)} руб."
    )
    
    await callback.message.edit_text(text, reply_markup=back_to_main_menu())
    await callback.answer()

@router.message(OrderStars.WaitingForCustomAmount)
async def process_custom_amount(message: Message, state: FSMContext):
    if not message.text or not message.from_user:
        return
        
    try:
        stars = int(message.text)
        if stars < 1 or stars > 10000:
            await message.answer("❌ Количество должно быть от 1 до 10000 звёзд")
            return
            
        await state.update_data(stars=stars)
        price = get_price(stars)
        
        text = (
            f"⭐ <b>Выбрано: {stars} звёзд</b>\n"
            f"💰 <b>Стоимость: {price} руб.</b>\n\n"
            f"📝 Укажите @username получателя:"
        )
        
        await message.answer(text)
        await state.set_state(OrderStars.WaitingForUsername)
        
    except ValueError:
        await message.answer("❌ Введите корректное число")

@router.message(OrderStars.WaitingForUsername)
async def process_username(message: Message, state: FSMContext):
    if not message.text or not message.from_user:
        return
        
    username = message.text.strip()
    if not username.startswith("@") or len(username) < 2:
        await message.answer("❌ Введите корректный @username (например: @username)")
        return
    
    data = await state.get_data()
    stars = data.get("stars", 0)
    price = get_price(stars)
    requisites = get_setting("requisites", "Переведите на карту")
    
    await state.update_data(username=username, price=price)
    
    text = (
        f"📋 <b>Детали заказа:</b>\n\n"
        f"⭐ Количество: <b>{stars} звёзд</b>\n"
        f"👤 Получатель: <b>{username}</b>\n"
        f"💰 К оплате: <b>{price} руб.</b>\n\n"
        f"💳 <b>Реквизиты для оплаты:</b>\n{requisites}\n\n"
        f"⚠️ После оплаты нажмите кнопку \"Оплачено\" и отправьте чек"
    )
    
    await message.answer(text, reply_markup=order_confirmation_menu())
    logger.info(f"Заказ {stars} звёзд для {username} от пользователя {message.from_user.id}")

@router.callback_query(F.data == "change_username")
async def change_username(callback: CallbackQuery, state: FSMContext):
    if not callback.message:
        return
        
    text = "📝 Введите новый @username получателя:"
    
    await callback.message.edit_text(text)
    await state.set_state(OrderStars.WaitingForUsername)
    await callback.answer()

@router.callback_query(F.data == "payment_done")
async def payment_done(callback: CallbackQuery, state: FSMContext):
    if not callback.message:
        return
        
    text = (
        f"📸 <b>Подтверждение оплаты</b>\n\n"
        f"📎 Отправьте скриншот или PDF чека об оплате\n"
        f"⚡ После проверки заказ будет обработан в течение 1-2 минут"
    )
    
    back_menu = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 К заказу", callback_data="back_to_order")]
    ])
    
    await callback.message.edit_text(text, reply_markup=back_menu)
    await state.set_state(OrderStars.WaitingForPaymentProof)
    await callback.answer()

@router.callback_query(F.data == "back_to_order")
async def back_to_order(callback: CallbackQuery, state: FSMContext):
    if not callback.message:
        return
        
    data = await state.get_data()
    stars = data.get("stars", 0)
    username = data.get("username", "")
    price = data.get("price", "0")
    requisites = get_setting("requisites", "Переведите на карту")
    
    text = (
        f"📋 <b>Детали заказа:</b>\n\n"
        f"⭐ Количество: <b>{stars} звёзд</b>\n"
        f"👤 Получатель: <b>{username}</b>\n"
        f"💰 К оплате: <b>{price} руб.</b>\n\n"
        f"💳 <b>Реквизиты для оплаты:</b>\n{requisites}\n\n"
        f"⚠️ После оплаты нажмите кнопку \"Оплачено\" и отправьте чек"
    )
    
    await callback.message.edit_text(text, reply_markup=order_confirmation_menu())
    await callback.answer()

@router.message(OrderStars.WaitingForPaymentProof, F.photo | F.document)
async def process_payment_proof(message: Message, state: FSMContext):
    if not message.from_user:
        return
        
    data = await state.get_data()
    stars = data.get("stars", 0)
    username_dest = data.get("username", "")
    price_str = data.get("price", "0")
    
    if not stars or not username_dest:
        await message.answer("❌ Ошибка данных заказа. Начните заново с /start")
        await state.clear()
        return
    
    price = price_str_to_float(price_str)
    user_username = message.from_user.username or "Без username"
    
    file_id = None
    file_type = None
    
    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = 'photo'
    elif message.document:
        if message.document.mime_type == "application/pdf":
            file_id = message.document.file_id
            file_type = 'document'
        else:
            await message.answer("❌ Принимаются только фото или PDF файлы")
            return
    
    if not file_id:
        await message.answer("❌ Ошибка при получении файла")
        return
    
    cursor.execute("SELECT MAX(order_number) FROM orders")
    result = cursor.fetchone()
    last_order_number = result[0] if result and result[0] else 0
    order_number = last_order_number + 1
    
    cursor.execute(
        "INSERT INTO orders (order_number, user_id, username, stars, price, destination, proof_file) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (order_number, message.from_user.id, user_username, stars, price, username_dest, file_id)
    )
    conn.commit()
    order_id = cursor.lastrowid
    
    caption = (
        f"🆕 <b>Новый заказ #{order_number}</b>\n\n"
        f"👤 Заказчик: @{user_username}\n"
        f"⭐ Звёзды: <b>{stars}</b>\n"
        f"📥 Получатель: <b>{username_dest}</b>\n"
        f"💰 Сумма: <b>{price_str} руб.</b>\n"
        f"📅 Время: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    
    admin_menu_inline = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Выполнен", callback_data=f"complete_order_{order_id}")]
    ])
    
    try:
        if file_type == 'photo' and CHANNEL_ID:
            await bot.send_photo(CHANNEL_ID, file_id, caption=caption, reply_markup=admin_menu_inline)
        elif file_type == 'document' and CHANNEL_ID:
            await bot.send_document(CHANNEL_ID, file_id, caption=caption, reply_markup=admin_menu_inline)
    except Exception as e:
        logger.error(f"Ошибка отправки в канал: {e}")
    
    success_text = (
        f"✅ <b>Заказ #{order_number} принят!</b>\n\n"
        f"⚡ Ваш заказ отправлен на обработку\n"
        f"🕐 Ожидайте выполнения в течение 1-2 минут\n"
        f"📨 Вы получите уведомление о готовности"
    )
    
    await message.answer(success_text, reply_markup=back_to_main_menu())
    await state.clear()
    logger.info(f"Заказ #{order_number} создан пользователем {message.from_user.id}")

@router.callback_query(F.data.startswith("complete_order_"))
async def complete_order(callback: CallbackQuery):
    if not callback.from_user or callback.from_user.id != ADMIN_ID or not callback.data:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    order_id = int(callback.data.split("_")[2])
    
    cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    
    user_id, order_number = order[2], order[1]
    
    cursor.execute("UPDATE orders SET status = 'completed' WHERE id = ?", (order_id,))
    conn.commit()
    
    review_group = get_setting("review_group", "")
    
    if review_group:
        user_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Оставить отзыв", url=review_group)]
        ])
        completion_text = (
            f"🎉 <b>Заказ #{order_number} выполнен!</b>\n\n"
            f"✅ Звёзды успешно доставлены\n"
            f"💫 Спасибо за покупку!\n\n"
            f"⭐ Будем рады вашему отзыву"
        )
    else:
        user_keyboard = back_to_main_menu()
        completion_text = (
            f"🎉 <b>Заказ #{order_number} выполнен!</b>\n\n"
            f"✅ Звёзды успешно доставлены\n"
            f"💫 Спасибо за покупку!"
        )
    
    try:
        await bot.send_message(user_id, completion_text, reply_markup=user_keyboard)
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")
    
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("✅ Заказ отмечен как выполненный")

@router.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    if not callback.from_user or callback.from_user.id != ADMIN_ID or not callback.message:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    text = (
        f"⚙️ <b>Админ-панель</b>\n\n"
        f"🛠 Управление ботом и настройками"
    )
    
    await callback.message.edit_text(text, reply_markup=admin_menu())
    await callback.answer()

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if not callback.from_user or callback.from_user.id != ADMIN_ID or not callback.message:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM orders")
    total_orders = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'completed'")
    completed_orders = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(price) FROM orders WHERE status = 'completed'")
    result = cursor.fetchone()
    total_revenue = result[0] if result and result[0] else 0
    
    cursor.execute("SELECT COUNT(*) FROM orders WHERE DATE(created_at) = DATE('now')")
    today_orders = cursor.fetchone()[0]
    
    text = (
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 Пользователей: <b>{total_users}</b>\n"
        f"📦 Всего заказов: <b>{total_orders}</b>\n"
        f"✅ Выполнено: <b>{completed_orders}</b>\n"
        f"💰 Выручка: <b>{float_to_price_str(total_revenue)} руб.</b>\n"
        f"📅 Сегодня заказов: <b>{today_orders}</b>"
    )
    
    await callback.message.edit_text(text, reply_markup=back_to_admin_menu())
    await callback.answer()

@router.callback_query(F.data == "admin_prices")
async def admin_prices(callback: CallbackQuery):
    if not callback.from_user or callback.from_user.id != ADMIN_ID or not callback.message:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    text = "💰 <b>Настройка цен</b>\n\nВыберите тип цены для изменения:"
    
    await callback.message.edit_text(text, reply_markup=price_settings_menu())
    await callback.answer()

@router.callback_query(F.data == "edit_price_under_500")
async def edit_price_under_500(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user or callback.from_user.id != ADMIN_ID or not callback.message:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    current_price = get_setting("price_under_500", "1,40")
    text = (
        f"💰 <b>Цена до 500 звёзд</b>\n\n"
        f"Текущая цена: <b>{current_price} руб/⭐</b>\n\n"
        f"📝 Введите новую цену (например: 1,50):"
    )
    
    await callback.message.edit_text(text)
    await state.set_state(AdminState.WaitingForNewPriceUnder500)
    await callback.answer()

@router.callback_query(F.data == "edit_price_over_500")
async def edit_price_over_500(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user or callback.from_user.id != ADMIN_ID or not callback.message:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    current_price = get_setting("price_over_500", "1,35")
    text = (
        f"💰 <b>Цена от 500 звёзд</b>\n\n"
        f"Текущая цена: <b>{current_price} руб/⭐</b>\n\n"
        f"📝 Введите новую цену (например: 1,30):"
    )
    
    await callback.message.edit_text(text)
    await state.set_state(AdminState.WaitingForNewPriceOver500)
    await callback.answer()

@router.message(AdminState.WaitingForNewPriceUnder500)
async def set_price_under_500(message: Message, state: FSMContext):
    if not message.from_user or message.from_user.id != ADMIN_ID or not message.text:
        return
    
    try:
        price_str = message.text.replace('.', ',').strip()
        price_float = price_str_to_float(price_str)
        
        if price_float <= 0:
            raise ValueError
        
        set_setting("price_under_500", price_str)
        
        await message.answer(
            f"✅ Цена до 500 звёзд изменена на <b>{price_str} руб/⭐</b>",
            reply_markup=price_settings_menu()
        )
        await state.clear()
        
    except ValueError:
        await message.answer("❌ Введите корректную цену (например: 1,50)")

@router.message(AdminState.WaitingForNewPriceOver500)
async def set_price_over_500(message: Message, state: FSMContext):
    if not message.from_user or message.from_user.id != ADMIN_ID or not message.text:
        return
    
    try:
        price_str = message.text.replace('.', ',').strip()
        price_float = price_str_to_float(price_str)
        
        if price_float <= 0:
            raise ValueError
        
        set_setting("price_over_500", price_str)
        
        await message.answer(
            f"✅ Цена от 500 звёзд изменена на <b>{price_str} руб/⭐</b>",
            reply_markup=price_settings_menu()
        )
        await state.clear()
        
    except ValueError:
        await message.answer("❌ Введите корректную цену (например: 1,30)")

@router.callback_query(F.data == "admin_requisites")
async def admin_requisites(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user or callback.from_user.id != ADMIN_ID or not callback.message:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    current_requisites = get_setting("requisites", "")
    text = (
        f"🏦 <b>Реквизиты для оплаты</b>\n\n"
        f"Текущие реквизиты:\n{current_requisites}\n\n"
        f"📝 Введите новые реквизиты:"
    )
    
    await callback.message.edit_text(text)
    await state.set_state(AdminState.WaitingForNewRequisites)
    await callback.answer()

@router.message(AdminState.WaitingForNewRequisites)
async def set_requisites(message: Message, state: FSMContext):
    if not message.from_user or message.from_user.id != ADMIN_ID or not message.text:
        return
    
    new_requisites = message.text.strip()
    set_setting("requisites", new_requisites)
    
    await message.answer(
        "✅ Реквизиты обновлены!",
        reply_markup=admin_menu()
    )
    await state.clear()

@router.callback_query(F.data == "admin_reviews")
async def admin_reviews(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user or callback.from_user.id != ADMIN_ID or not callback.message:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    current_group = get_setting("review_group", "")
    text = (
        f"📝 <b>Группа для отзывов</b>\n\n"
        f"Текущая ссылка: {current_group or 'Не установлена'}\n\n"
        f"📝 Введите новую ссылку на группу:"
    )
    
    await callback.message.edit_text(text)
    await state.set_state(AdminState.WaitingForReviewGroupLink)
    await callback.answer()

@router.message(AdminState.WaitingForReviewGroupLink)
async def set_review_group(message: Message, state: FSMContext):
    if not message.from_user or message.from_user.id != ADMIN_ID or not message.text:
        return
    
    new_group = message.text.strip()
    set_setting("review_group", new_group)
    
    await message.answer(
        "✅ Группа для отзывов обновлена!",
        reply_markup=admin_menu()
    )
    await state.clear()

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery):
    if not callback.from_user or callback.from_user.id != ADMIN_ID or not callback.message:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    text = "📢 <b>Рассылка сообщений</b>\n\nВыберите тип рассылки:"
    
    await callback.message.edit_text(text, reply_markup=broadcast_options_menu())
    await callback.answer()

@router.callback_query(F.data == "broadcast_text_only")
async def broadcast_text_only(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user or callback.from_user.id != ADMIN_ID or not callback.message:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    text = "📝 Введите текст для рассылки:"
    
    await callback.message.edit_text(text)
    await state.set_state(AdminState.WaitingForBroadcastText)
    await callback.answer()

# Обработчики для рассылок с текстом и кнопкой
@router.callback_query(F.data == "broadcast_text_button")
async def broadcast_text_button(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user or callback.from_user.id != ADMIN_ID or not callback.message:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    text = "📝 Введите текст для рассылки:"
    
    await callback.message.edit_text(text)
    await state.set_state(AdminState.WaitingForBroadcastText)
    await state.update_data(broadcast_type="text_button")
    await callback.answer()

# Обработчики для рассылок только с медиа
@router.callback_query(F.data == "broadcast_photo")
async def broadcast_photo(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user or callback.from_user.id != ADMIN_ID or not callback.message:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    text = "📝 Введите текст, затем отправьте фото:"
    
    await callback.message.edit_text(text)
    await state.set_state(AdminState.WaitingForBroadcastText)
    await state.update_data(broadcast_type="photo")
    await callback.answer()

@router.callback_query(F.data == "broadcast_video")
async def broadcast_video(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user or callback.from_user.id != ADMIN_ID or not callback.message:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    text = "📝 Введите текст, затем отправьте видео:"
    
    await callback.message.edit_text(text)
    await state.set_state(AdminState.WaitingForBroadcastText)
    await state.update_data(broadcast_type="video")
    await callback.answer()

@router.callback_query(F.data == "broadcast_sticker")
async def broadcast_sticker(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user or callback.from_user.id != ADMIN_ID or not callback.message:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    text = "📝 Введите текст, затем отправьте стикер:"
    
    await callback.message.edit_text(text)
    await state.set_state(AdminState.WaitingForBroadcastText)
    await state.update_data(broadcast_type="sticker")
    await callback.answer()

@router.callback_query(F.data == "broadcast_animation")
async def broadcast_animation(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user or callback.from_user.id != ADMIN_ID or not callback.message:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    text = "📝 Введите текст, затем отправьте GIF/анимацию:"
    
    await callback.message.edit_text(text)
    await state.set_state(AdminState.WaitingForBroadcastText)
    await state.update_data(broadcast_type="animation")
    await callback.answer()

@router.callback_query(F.data == "broadcast_document")
async def broadcast_document(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user or callback.from_user.id != ADMIN_ID or not callback.message:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    text = "📝 Введите текст, затем отправьте документ:"
    
    await callback.message.edit_text(text)
    await state.set_state(AdminState.WaitingForBroadcastText)
    await state.update_data(broadcast_type="document")
    await callback.answer()

# Обработчики для рассылок с медиа и кнопкой
@router.callback_query(F.data == "broadcast_photo_button")
async def broadcast_photo_button(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user or callback.from_user.id != ADMIN_ID or not callback.message:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    text = "📝 Введите текст, затем отправьте фото:"
    
    await callback.message.edit_text(text)
    await state.set_state(AdminState.WaitingForBroadcastText)
    await state.update_data(broadcast_type="photo_button")
    await callback.answer()

@router.callback_query(F.data == "broadcast_video_button")
async def broadcast_video_button(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user or callback.from_user.id != ADMIN_ID or not callback.message:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    text = "📝 Введите текст, затем отправьте видео:"
    
    await callback.message.edit_text(text)
    await state.set_state(AdminState.WaitingForBroadcastText)
    await state.update_data(broadcast_type="video_button")
    await callback.answer()

@router.callback_query(F.data == "broadcast_sticker_button")
async def broadcast_sticker_button(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user or callback.from_user.id != ADMIN_ID or not callback.message:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    text = "📝 Введите текст, затем отправьте стикер:"
    
    await callback.message.edit_text(text)
    await state.set_state(AdminState.WaitingForBroadcastText)
    await state.update_data(broadcast_type="sticker_button")
    await callback.answer()

@router.callback_query(F.data == "broadcast_animation_button")
async def broadcast_animation_button(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user or callback.from_user.id != ADMIN_ID or not callback.message:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    text = "📝 Введите текст, затем отправьте GIF/анимацию:"
    
    await callback.message.edit_text(text)
    await state.set_state(AdminState.WaitingForBroadcastText)
    await state.update_data(broadcast_type="animation_button")
    await callback.answer()

@router.callback_query(F.data == "broadcast_document_button")
async def broadcast_document_button(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user or callback.from_user.id != ADMIN_ID or not callback.message:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    text = "📝 Введите текст, затем отправьте документ:"
    
    await callback.message.edit_text(text)
    await state.set_state(AdminState.WaitingForBroadcastText)
    await state.update_data(broadcast_type="document_button")
    await callback.answer()

@router.message(AdminState.WaitingForBroadcastText)
async def process_broadcast_text(message: Message, state: FSMContext):
    if not message.from_user or message.from_user.id != ADMIN_ID or not message.text:
        return
    
    data = await state.get_data()
    broadcast_type = data.get("broadcast_type", "text")
    
    await state.update_data(broadcast_text=message.text)
    
    if broadcast_type == "text":
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        
        success_count = 0
        for user in users:
            try:
                await bot.send_message(user[0], message.text)
                success_count += 1
            except Exception as e:
                logger.warning(f"Не удалось отправить сообщение пользователю {user[0]}: {e}")
        
        await message.answer(
            f"✅ Рассылка завершена!\nОтправлено {success_count} из {len(users)} сообщений",
            reply_markup=admin_menu()
        )
        await state.clear()
    
    elif broadcast_type == "text_button":
        await message.answer("📝 Введите текст кнопки:")
        await state.set_state(AdminState.WaitingForBroadcastButtonText)
        
    elif broadcast_type in ["photo", "video", "sticker", "animation", "document"]:
        media_names = {
            "photo": "фото",
            "video": "видео", 
            "sticker": "стикер",
            "animation": "GIF/анимацию",
            "document": "документ"
        }
        await message.answer(f"📎 Теперь отправьте {media_names[broadcast_type]}:")
        await state.set_state(AdminState.WaitingForBroadcastMedia)
        
    elif broadcast_type.endswith("_button"):
        media_type = broadcast_type.replace("_button", "")
        media_names = {
            "photo": "фото",
            "video": "видео", 
            "sticker": "стикер",
            "animation": "GIF/анимацию",
            "document": "документ"
        }
        await message.answer(f"📎 Теперь отправьте {media_names[media_type]}:")
        await state.set_state(AdminState.WaitingForBroadcastMedia)

@router.message(AdminState.WaitingForBroadcastButtonText)
async def process_broadcast_button_text(message: Message, state: FSMContext):
    if not message.from_user or message.from_user.id != ADMIN_ID or not message.text:
        return
    
    await state.update_data(button_text=message.text)
    await message.answer("🔗 Введите URL для кнопки:")
    await state.set_state(AdminState.WaitingForBroadcastButtonURL)

@router.message(AdminState.WaitingForBroadcastButtonURL)
async def process_broadcast_button_url(message: Message, state: FSMContext):
    if not message.from_user or message.from_user.id != ADMIN_ID or not message.text:
        return
    
    data = await state.get_data()
    broadcast_text = data.get("broadcast_text", "")
    button_text = data.get("button_text", "")
    button_url = message.text
    broadcast_type = data.get("broadcast_type", "")
    media_id = data.get("media_id", "")
    media_type = data.get("media_type", "")
    
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=button_text, url=button_url)]
    ])
    
    success_count = 0
    for user in users:
        try:
            if broadcast_type == "text_button":
                await bot.send_message(user[0], broadcast_text, reply_markup=keyboard)
            elif media_id and media_type:
                if media_type == "photo":
                    await bot.send_photo(user[0], media_id, caption=broadcast_text, reply_markup=keyboard)
                elif media_type == "video":
                    await bot.send_video(user[0], media_id, caption=broadcast_text, reply_markup=keyboard)
                elif media_type == "animation":
                    await bot.send_animation(user[0], media_id, caption=broadcast_text, reply_markup=keyboard)
                elif media_type == "sticker":
                    await bot.send_sticker(user[0], media_id)
                    if broadcast_text:
                        await bot.send_message(user[0], broadcast_text, reply_markup=keyboard)
                elif media_type == "document":
                    await bot.send_document(user[0], media_id, caption=broadcast_text, reply_markup=keyboard)
            success_count += 1
        except Exception as e:
            logger.warning(f"Не удалось отправить сообщение пользователю {user[0]}: {e}")
    
    if media_type and media_type in ["photo", "video", "animation", "sticker", "document"]:
        media_names = {
            "photo": "фото",
            "video": "видео",
            "animation": "GIF",
            "sticker": "стикер",
            "document": "документ"
        }
        result_text = f"✅ Рассылка с {media_names[media_type]} и кнопкой завершена!"
    else:
        result_text = "✅ Рассылка с кнопкой завершена!"
    
    await message.answer(
        f"{result_text}\nОтправлено {success_count} из {len(users)} сообщений",
        reply_markup=admin_menu()
    )
    await state.clear()

@router.message(AdminState.WaitingForBroadcastMedia, F.photo | F.video | F.animation | F.sticker | F.document)
async def process_broadcast_media(message: Message, state: FSMContext):
    if not message.from_user or message.from_user.id != ADMIN_ID:
        return
    
    data = await state.get_data()
    broadcast_text = data.get("broadcast_text", "")
    broadcast_type = data.get("broadcast_type", "")
    
    file_id = None
    media_type = None
    
    if message.photo:
        file_id = message.photo[-1].file_id
        media_type = "photo"
    elif message.video:
        file_id = message.video.file_id
        media_type = "video"
    elif message.animation:
        file_id = message.animation.file_id
        media_type = "animation"
    elif message.sticker:
        file_id = message.sticker.file_id
        media_type = "sticker"
    elif message.document:
        file_id = message.document.file_id
        media_type = "document"
    
    if not file_id:
        await message.answer("❌ Ошибка при получении файла")
        return
    
    await state.update_data(media_id=file_id, media_type=media_type)
    
    # Если это рассылка с кнопкой
    if broadcast_type.endswith("_button"):
        await message.answer("📝 Введите текст кнопки:")
        await state.set_state(AdminState.WaitingForBroadcastButtonText)
    else:
        # Обычная рассылка с медиа
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        
        success_count = 0
        for user in users:
            try:
                if media_type == "photo":
                    await bot.send_photo(user[0], file_id, caption=broadcast_text)
                elif media_type == "video":
                    await bot.send_video(user[0], file_id, caption=broadcast_text)
                elif media_type == "animation":
                    await bot.send_animation(user[0], file_id, caption=broadcast_text)
                elif media_type == "sticker":
                    await bot.send_sticker(user[0], file_id)
                    if broadcast_text:
                        await bot.send_message(user[0], broadcast_text)
                elif media_type == "document":
                    await bot.send_document(user[0], file_id, caption=broadcast_text)
                success_count += 1
            except Exception as e:
                logger.warning(f"Не удалось отправить {media_type} пользователю {user[0]}: {e}")
        
        media_names = {
            "photo": "фото",
            "video": "видео",
            "animation": "GIF",
            "sticker": "стикер",
            "document": "документ"
        }
        
        await message.answer(
            f"✅ Рассылка с {media_names[media_type]} завершена!\nОтправлено {success_count} из {len(users)} сообщений",
            reply_markup=admin_menu()
        )
        await state.clear()

@router.callback_query(F.data == "admin_orders")
async def admin_orders(callback: CallbackQuery):
    if not callback.from_user or callback.from_user.id != ADMIN_ID or not callback.message:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    cursor.execute("SELECT order_number, username, stars, destination, status FROM orders ORDER BY created_at DESC LIMIT 10")
    orders = cursor.fetchall()
    
    if not orders:
        text = "📋 <b>Последние заказы</b>\n\nЗаказов пока нет"
    else:
        text = "📋 <b>Последние 10 заказов</b>\n\n"
        for order in orders:
            status_emoji = "✅" if order[4] == "completed" else "⏳"
            text += f"{status_emoji} #{order[0]} - @{order[1]} - {order[2]}⭐ → {order[3]}\n"
    
    await callback.message.edit_text(text, reply_markup=back_to_admin_menu())
    await callback.answer()

async def main():
    logger.info("Запуск бота...")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    asyncio.run(main())