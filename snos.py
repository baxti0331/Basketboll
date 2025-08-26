import aiohttp
import asyncio
import logging
import time
import os
import random
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from telethon import TelegramClient, errors
from telethon.tl.functions.messages import ReportRequest
from telethon.tl.types import (
    InputReportReasonSpam,
    InputReportReasonViolence,
    InputReportReasonPornography,
    InputReportReasonChildAbuse,
    InputReportReasonCopyright,
    InputReportReasonGeoIrrelevant,
    InputReportReasonFake,
    InputReportReasonIllegalDrugs,
    InputReportReasonPersonalDetails
)
from telethon.tl.functions.channels import JoinChannelRequest
from datetime import datetime, timedelta
import re

from config import api_id, api_hash, bot_token, admin_chat_ids, CRYPTO_PAY_TOKEN, senders, receivers, smtp_servers
from proxies import proxies
from user_agents import user_agents
from emails import mail, phone_numbers

class InputReportReasonThreats:
    def __init__(self):
        self.reason = "threats"

class InputReportReasonInsults:
    def __init__(self):
        self.reason = "insults"

class InputReportReasonLinkSpam:
    def __init__(self):
        self.reason = "link_spam"

class InputReportReasonTerrorism:
    def __init__(self):
        self.reason = "terrorism"

class InputReportReasonNoViolationButDelete:
    def __init__(self):
        self.reason = "no_violation_but_delete"

class InputReportReasonDislike:
    def __init__(self):
        self.reason = "dislike"

class InputReportReasonPhishing:
    def __init__(self):
        self.reason = "phishing"
# оставил обозначение потому что я заебался путатся и вы чтобы знали где какая тема 
option_mapping = {
    '1': "1",  # InputReportReasonSpam
    '2': "2",  # InputReportReasonViolence
    '3': "3",  # InputReportReasonChildAbuse
    '4': "4",  # InputReportReasonPornography
    '5': "5",  # InputReportReasonCopyright
    '6': "6",  # InputReportReasonPersonalDetails
    '7': "7",  # InputReportReasonGeoIrrelevant
    '8': "8",  # InputReportReasonFake
    '9': "9",  # InputReportReasonIllegalDrugs
}

reason_mapping = {
    '1': "Спам",
    '2': "Насилие",
    '3': "Насилие над детьми",
    '4': "Порнография",
    '5': "Нарушение авторских прав",
    '6': "Раскрытие личных данных",
    '7': "Геонерелевантный контент",
    '8': "Фальшивка",
    '9': "Незаконные наркотики"
}
        
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

bot = Bot(token=bot_token)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())

script_dir = os.path.dirname(os.path.abspath(__file__))
session_dir = os.path.join(script_dir, 'Session')
if not os.path.exists(session_dir):
    os.makedirs(session_dir)
# для прыватных чтобы нельза было снести 
private_users = {
    "ids": [id, id2],  # тут id
    "usernames": ["username", "username2"]  # тут user и без @ 
}

class ComplaintStates(StatesGroup):
    subject = State()
    body = State()
    photos = State()
    count = State()
    text_for_site = State()
    count_for_site = State()

class RestoreAccountStates(StatesGroup):
    phone = State()
    send_count = State()

class SupportStates(StatesGroup):
    message = State()

class CreateAccountStates(StatesGroup):
    client = State()
    phone = State()
    code = State()
    password = State()

class ReportStates(StatesGroup):
    message_link = State()
    option = State()
    user_id = State()
    message_count = State()
    report_count = State()

def register_handlers_spam_code(dp: Dispatcher):
    dp.register_message_handler(process_spam_code, state=SpamCodeStates.phone_and_count)

banned_users_file = 'banned_users.txt'
class BanState(StatesGroup):
    waiting_for_ban_user_id = State()
    waiting_for_unban_user_id = State()
def load_banned_users():
    try:
        with open(banned_users_file, 'r') as file:
            return set(map(int, file.read().splitlines()))
    except FileNotFoundError:
        return set()
def save_banned_users(banned_users):
    with open(banned_users_file, 'w') as file:
        for user_id in banned_users:
            file.write(f'{user_id}\n')

banned_users = load_banned_users()

class SendMessage(StatesGroup):
    text = State()
    media_type = State()
    media = State()

def add_user_to_file(user_id: int):
    try:
        with open('users.txt', 'r') as file:
            users = file.readlines()
        users = [line.strip() for line in users if line.strip()]
        user_ids = [line.split()[0] for line in users if line.split()]
        
        if str(user_id) not in user_ids:
            with open('users.txt', 'a') as file:
                file.write(f"{user_id}\n")
    except Exception as e:
        print(f"Ошибка при добавлении пользователя в файл: {e}")
# ценю меняйте сами 
CURRENCY_PRICES = {
    "1_day": {
        "TON": 1.5,
        "BTC": 0.0001,
        "ETH": 0.001,
        "USDT": 0.6,
        "BNB": 0.01,
        "LTC": 0.02,
        "DOGE": 50,
        "TRX": 10,
        "NOT": 2,
    },
    "2_days": {
        "TON": 2.5,
        "BTC": 0.0002,
        "ETH": 0.002,
        "USDT": 3.0,
        "BNB": 0.02,
        "LTC": 0.03,
        "DOGE": 75,
        "TRX": 15,
        "NOT": 3,
    },
    "5_days": {
        "TON": 5.0,
        "BTC": 0.0005,
        "ETH": 0.005,
        "USDT": 5.0,
        "BNB": 0.05,
        "LTC": 0.05,
        "DOGE": 100,
        "TRX": 20,
        "NOT": 5,
    },
    "30_days": {
        "TON": 10.0,
        "BTC": 0.001,
        "ETH": 0.01,
        "USDT": 10.0,
        "BNB": 0.1,
        "LTC": 0.1,
        "DOGE": 200,
        "TRX": 30,
        "NOT": 10,
    },
    "1_year": {
        "TON": 50.0,
        "BTC": 0.005,
        "ETH": 0.05,
        "USDT": 50.0,
        "BNB": 0.5,
        "LTC": 0.5,
        "DOGE": 500,
        "TRX": 100,
        "NOT": 50,
    },
}

async def check_payment(user_id):
    if not os.path.exists('paid_users.txt'):
        print("Файл paid_users.txt не существует.")
        return False
    
    with open('paid_users.txt', 'r') as file:
        lines = file.readlines()
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        try:
            paid_user_id, expiry_time_str = line.split(',')
            if paid_user_id == str(user_id):
                expiry_time = datetime.strptime(expiry_time_str, '%Y-%m-%d %H:%M:%S')
                print(f"Найден пользователь {user_id}, время истечения: {expiry_time_str}, текущее время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                if expiry_time > datetime.now():
                    print("Подписка активна.")
                    return True
                else:
                    print("Подписка истекла.")
                    return False
        except ValueError as e:
            print(f"Ошибка при обработке строки '{line}': {e}")
            continue
    
    print(f"Пользователь {user_id} не найден в файле.")
    return False
    
from datetime import datetime, timedelta

async def save_paid_user(user_id, duration_days):
    expiry_time = datetime.now() + timedelta(days=duration_days)
    expiry_time_str = expiry_time.strftime('%Y-%m-%d %H:%M:%S')
    
    if not os.path.exists('paid_users.txt'):
        with open('paid_users.txt', 'w') as file:
            file.write(f"{user_id},{expiry_time_str}\n")
        return
    
    with open('paid_users.txt', 'r') as file:
        lines = file.readlines()
    
    updated = False
    updated_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        try:
            paid_user_id, paid_expiry_time_str = line.split(',')
            paid_expiry_time = datetime.strptime(paid_expiry_time_str, '%Y-%m-%d %H:%M:%S')
            if paid_user_id == str(user_id):
                if paid_expiry_time > datetime.now():
                    expiry_time += paid_expiry_time - datetime.now()
                    expiry_time_str = expiry_time.strftime('%Y-%m-%d %H:%M:%S')
                updated_lines.append(f"{paid_user_id},{expiry_time_str}\n")
                updated = True
            else:
                updated_lines.append(line + '\n')
        except ValueError as e:
            print(f"Ошибка при обработке строки '{line}': {e}")
            continue
    
    if not updated:
        updated_lines.append(f"{user_id},{expiry_time_str}\n")
    
    with open('paid_users.txt', 'w') as file:
        file.writelines(updated_lines)

async def update_time():
    if not os.path.exists('paid_users.txt'):
        return
    with open('paid_users.txt', 'r') as file:
        lines = file.readlines()
    updated_lines = []
    for line in lines:
        user_id, expiry_time_str = line.strip().split(',')
        expiry_time = datetime.strptime(expiry_time_str, '%Y-%m-%d %H:%M:%S')
        if expiry_time > datetime.now():
            expiry_time -= timedelta(seconds=1)
            expiry_time_str = expiry_time.strftime('%Y-%m-%d %H:%M:%S')
        updated_lines.append(f"{user_id},{expiry_time_str}\n")
    with open('paid_users.txt', 'w') as file:
        file.writelines(updated_lines)

async def check_and_notify():
    if not os.path.exists('paid_users.txt'):
        return
    with open('paid_users.txt', 'r') as file:
        lines = file.readlines()
    for line in lines:
        user_id, expiry_time_str = line.strip().split(',')
        expiry_time = datetime.strptime(expiry_time_str, '%Y-%m-%d %H:%M:%S')
        if expiry_time <= datetime.now():
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("Купить время", callback_data="go_to_payment"))
            await bot.send_message(user_id, "⏳ Ваше время истекло. Пожалуйста, купите дополнительное время.", reply_markup=markup)

def create_invoice(asset, amount, description):
    url = "https://pay.crypt.bot/api/createInvoice"
    headers = {
        "Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN,
        "Content-Type": "application/json"
    }
    data = {
        "asset": asset,
        "amount": str(amount),
        "description": description,
        "payload": "custom_payload"
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        return response.json()
    else:
        logging.error(f"Ошибка при создании счета: {response.status_code} - {response.text}")
        return None

def check_invoice_status(invoice_id):
    url = "https://pay.crypt.bot/api/getInvoices"
    headers = {
        "Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN,
        "Content-Type": "application/json"
    }
    params = {"invoice_ids": invoice_id}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        logging.error(f"Ошибка при проверке статуса счета: {response.status_code} - {response.text}")
        return None

async def handle_welcome(user_id: int, chat_id: int, from_user: types.User, reply_photo_method):
    add_user_to_file(user_id)

    if not os.path.exists('paid_users.txt'):
        with open('paid_users.txt', 'w') as file:
            pass

    if not await check_payment(user_id) and str(user_id) not in admin_chat_ids:  
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("💳 Перейти к оплате", callback_data="go_to_payment"))
        
        await reply_photo_method(
            photo=open('unnamed.jpg', 'rb'),
            caption="✨ <b>Добро пожаловать!</b> ✨\n\n🚀 Чтобы получить доступ к боту, необходимо оплатить подписку. Нажмите кнопку ниже, чтобы перейти к оплате.\n\n💎 <b>Премиум доступ открывает:</b>\n- 🔐 Полная защита от сноса через бота\n- 🎁 Эксклюзивные возможности",
            reply_markup=markup,
            parse_mode="HTML"
        )
        return
    
    first_name = from_user.first_name if from_user.first_name else ''
    last_name = from_user.last_name if from_user.last_name else ''
    username = f"@{from_user.username}" if from_user.username else f"id{from_user.id}"
    
    welcome_message = f"""
🌟 <b>Добро пожаловать, {first_name} {last_name} {username}!</b> 🌟
Мы рады видеть вас здесь! Если у вас есть вопросы или нужна помощь, не стесняйтесь обращаться к поддержке. 😊
"""
    
    await send_menu(chat_id, welcome_message)

@dp.message_handler(commands=['start'], state='*')
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    await handle_welcome(
        user_id=message.from_user.id,
        chat_id=message.chat.id,
        from_user=message.from_user,
        reply_photo_method=message.reply_photo
    )

@dp.callback_query_handler(lambda c: c.data == 'send_welcome', state='*')
async def process_callback_send_welcome(callback_query: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await handle_welcome(
        user_id=callback_query.from_user.id,
        chat_id=callback_query.message.chat.id,
        from_user=callback_query.from_user,
        reply_photo_method=callback_query.message.reply_photo
    )
    await callback_query.answer()

async def send_menu(chat_id: int, welcome_message: str):
    markup = InlineKeyboardMarkup(row_width=2)
    btn_support = InlineKeyboardButton('📩 Написать поддержку', callback_data='support')
    btn_demolition = InlineKeyboardButton('💣 Снос', callback_data='demolition')  
    btn_restore_account = InlineKeyboardButton('🔄 Восстановить аккаунт', callback_data='restore_account')
    btn_my_time = InlineKeyboardButton('⏳ Моё время', callback_data='my_time')  
    markup.add(btn_support, btn_demolition, btn_restore_account, btn_my_time)
    if str(chat_id) in admin_chat_ids:
        btn_admin_panel = InlineKeyboardButton('🛠 Админ панель', callback_data='admin_panel')
        markup.add(btn_admin_panel)
    
    await bot.send_photo(
        chat_id=chat_id,
        photo=open('welcome_photo.jpg', 'rb'),
        caption=welcome_message,
        reply_markup=markup,
        parse_mode="HTML"
    )

@dp.callback_query_handler(lambda c: c.data == 'extract_users', state='*')
async def extract_users_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()

    with open('users.txt', 'r', encoding='utf-8') as file:
        users_data = file.read()
    user_count = len(users_data.splitlines())
    document = types.InputFile('users.txt')
    await callback_query.message.answer_document(document)
    await callback_query.message.answer(f'📝В файле содержится {user_count} пользователей.')

@dp.callback_query_handler(lambda c: c.data == 'stats', state='*')
async def stats_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    with open('users.txt', 'r', encoding='utf-8') as file:
        lines = file.readlines()
        total_users = len(lines)
        active_users = sum(1 for line in lines if 'id' not in line)
    await callback_query.message.answer(f'📊Статистика:\n\n👤Всего пользователей: {total_users}\n✅Активных пользователей: {active_users}')

@dp.callback_query_handler(lambda c: c.data == 'send_message', state='*')
async def send_message_start(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.answer('Введите текст сообщения:')
    await SendMessage.text.set()

@dp.message_handler(state=SendMessage.text)
async def process_text(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['text'] = message.text
    markup = InlineKeyboardMarkup(row_width=2)
    btn_yes = InlineKeyboardButton('Да', callback_data='yes')
    btn_no = InlineKeyboardButton('Нет', callback_data='no')
    markup.add(btn_yes, btn_no)
    await message.answer('Хотите добавить фото или видео?', reply_markup=markup)
    await SendMessage.media_type.set()

@dp.callback_query_handler(lambda c: c.data in ['yes', 'no'], state=SendMessage.media_type)
async def process_media_type(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    async with state.proxy() as data:
        if callback_query.data == 'yes':
            await callback_query.message.answer('Отправьте фото или видео:')
            await SendMessage.media.set()
        else:
            await send_message_to_users(data['text'], None, None)
            await state.finish()
            await callback_query.message.answer('✅Сообщение отправлено всем пользователям.')

@dp.message_handler(content_types=['photo', 'video'], state=SendMessage.media)
async def process_media(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        if message.photo:
            data['media_type'] = 'photo'
            data['media'] = message.photo[-1].file_id
        elif message.video:
            data['media_type'] = 'video'
            data['media'] = message.video.file_id
        await send_message_to_users(data['text'], data['media_type'], data['media'])
        await state.finish()
        await message.answer('✅Сообщение отправлено всем пользователям.')

async def send_message_to_users(text, media_type, media_id):
    with open('users.txt', 'r', encoding='utf-8') as file:
        for line in file:
            user_id = line.split()[0]
            try:
                if media_type == 'photo':
                    await bot.send_photo(user_id, media_id, caption=text)
                elif media_type == 'video':
                    await bot.send_video(user_id, media_id, caption=text)
                else:
                    await bot.send_message(user_id, text)
            except Exception as e:
                logging.error(f'Error sending message to user {user_id}: {e}')
    
@dp.callback_query_handler(lambda c: c.data == 'demolition', state='*')
async def demolition_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    markup = InlineKeyboardMarkup(row_width=2)
    btn_email_complaint = InlineKeyboardButton('📫Email-Снос📫', callback_data='email_complaint')
    btn_website_complaint = InlineKeyboardButton('💻Web-Снос💻', callback_data='website_complaint')
    btn_report_message = InlineKeyboardButton('🚨Ботнет-Снос🚨', callback_data='report_message')
    btn_back = InlineKeyboardButton('🔙 Назад', callback_data='back_to_main_menu')  
    markup.add(btn_email_complaint, btn_website_complaint, btn_report_message, btn_back)
    
    await callback_query.message.edit_reply_markup(reply_markup=markup)

@dp.callback_query_handler(lambda c: c.data == 'admin_panel', state='*')
async def admin_panel_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    markup = InlineKeyboardMarkup(row_width=2)
    btn_ban = InlineKeyboardButton('🚫 Бан', callback_data='ban_user')
    btn_unban = InlineKeyboardButton('🔓 Снять бан', callback_data='unban_user')
    btn_extract_users = InlineKeyboardButton('📥 Извлечь ID пользователей', callback_data='extract_users')
    btn_stats = InlineKeyboardButton('📊 Статистика', callback_data='stats')
    btn_send_message = InlineKeyboardButton('📨 Отправить сообщение', callback_data='send_message')
    btn_add_private = InlineKeyboardButton('➕ Добавить прывата', callback_data='add_private')
    btn_remove_private = InlineKeyboardButton('➖ Удалить прывата', callback_data='remove_private')
    btn_view_private = InlineKeyboardButton('👀 Кто под прыватом', callback_data='view_private')
    btn_create_account = InlineKeyboardButton('🔑 Создать .session', callback_data='create_account')  
    btn_back = InlineKeyboardButton('🔙 Назад', callback_data='back_to_main_menu')  
    markup.add(btn_ban, btn_unban, btn_extract_users, btn_stats, btn_send_message, btn_add_private, btn_remove_private, btn_view_private, btn_create_account, btn_back)
    await callback_query.message.edit_reply_markup(reply_markup=markup)

@dp.callback_query_handler(lambda c: c.data == 'back_to_main_menu', state='*')
async def back_to_main_menu_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    markup = InlineKeyboardMarkup(row_width=2)
    btn_support = InlineKeyboardButton('📢Написать поддержку📢', callback_data='support')
    btn_demolition = InlineKeyboardButton('💣 Снос💣', callback_data='demolition')  
    btn_restore_account = InlineKeyboardButton('🔄Восстановить аккаунт🔄', callback_data='restore_account')
    btn_my_time = InlineKeyboardButton('⏳Моё время⏳', callback_data='my_time')
    
    if str(callback_query.from_user.id) in admin_chat_ids:
        btn_admin_panel = InlineKeyboardButton('🛠Админ панель🛠', callback_data='admin_panel')
        markup.add(btn_admin_panel)
    
    markup.add(btn_support, btn_demolition, btn_restore_account, btn_my_time)
    await callback_query.message.edit_reply_markup(reply_markup=markup)
    
@dp.callback_query_handler(lambda c: c.data == 'add_private', state='*')
async def add_private_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.answer("➕ Введите ID или username пользователя для добавления в прыват:")
    await state.set_state("waiting_for_private_add")
    
@dp.message_handler(state="waiting_for_private_add")
async def process_add_private(message: types.Message, state: FSMContext):
    user_input = message.text.strip()
    if user_input.isdigit():
        private_users["ids"].append(int(user_input))
    else:
        private_users["usernames"].append(user_input.lstrip('@'))
    await message.answer(f"✅ Пользователь {user_input} успешно добавлен в прыват.")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == 'remove_private', state='*')
async def remove_private_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.answer("➖ Введите ID или username пользователя для удаления из прывата:")
    await state.set_state("waiting_for_private_remove")

@dp.message_handler(state="waiting_for_private_remove")
async def process_remove_private(message: types.Message, state: FSMContext):
    user_input = message.text.strip()
    if user_input.isdigit():
        if int(user_input) in private_users["ids"]:
            private_users["ids"].remove(int(user_input))
            await message.answer(f"✅ Пользователь {user_input} успешно удален из прывата.")
        else:
            await message.answer(f"❌ Пользователь {user_input} не найден в прывате.")
    else:
        if user_input.lstrip('@') in private_users["usernames"]:
            private_users["usernames"].remove(user_input.lstrip('@'))
            await message.answer(f"✅ Пользователь {user_input} успешно удален из прывата.")
        else:
            await message.answer(f"❌ Пользователь {user_input} не найден в прывате.")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == 'view_private', state='*')
async def view_private_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    users_list = "👥 Список пользователей под прыватом:\n"
    users_list += "🆔 IDs: " + ", ".join(map(str, private_users["ids"])) + "\n"
    users_list += "📛 Usernames: " + ", ".join(private_users["usernames"])
    await callback_query.message.answer(users_list)    

@dp.callback_query_handler(lambda c: c.data == 'ban_user', state='*')
async def ban_user_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.answer('📝Введите ID пользователя, которого хотите забанить:')
    await BanState.waiting_for_ban_user_id.set()

@dp.message_handler(state=BanState.waiting_for_ban_user_id)
async def ban_user_input(message: types.Message, state: FSMContext):
    user_id = message.text
    if user_id.isdigit():
        user_id = int(user_id)
        if user_id in banned_users:
            await message.answer(f'🚫 Пользователь с ID {user_id} уже забанен.')
        else:
            banned_users.add(user_id)
            save_banned_users(banned_users)
            await message.answer(f'✅ Пользователь с ID {user_id} забанен.')
            try:
                await bot.send_message(user_id, '📢Администратор посчитал ваш аккаунт подозрительным и вы были забанены📢')
            except Exception as e:
                logging.error(f'Error sending ban message to user {user_id}: {e}')
    else:
        await message.answer('❌ Неверный формат ID. Пожалуйста, введите числовой ID.')
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == 'unban_user', state='*')
async def unban_user_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.answer('📝Введите ID пользователя, которого хотите разбанить:')
    await BanState.waiting_for_unban_user_id.set()

@dp.message_handler(state=BanState.waiting_for_unban_user_id)
async def unban_user_input(message: types.Message, state: FSMContext):
    user_id = message.text
    if user_id.isdigit():
        user_id = int(user_id)
        if user_id not in banned_users:
            await message.answer(f'🚫 Пользователь с ID {user_id} не забанен.')
        else:
            banned_users.remove(user_id)
            save_banned_users(banned_users)
            await message.answer(f'✅ Пользователь с ID {user_id} разбанен.')
            try:
                await bot.send_message(user_id, '📢Ваш аккаунт был разбанен администратором📢')
            except Exception as e:
                logging.error(f'Error sending unban message to user {user_id}: {e}')
    else:
        await message.answer('❌ Неверный формат ID. Пожалуйста, введите числовой ID.')
    await state.finish()        

@dp.callback_query_handler(lambda c: c.data == "go_to_payment")
async def process_go_to_payment(callback_query: types.CallbackQuery):
    await callback_query.answer()
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("1 день 🕐", callback_data="period_1_day"))
    markup.add(InlineKeyboardButton("2 дня 🕑", callback_data="period_2_days"))
    markup.add(InlineKeyboardButton("5 дней 🕔", callback_data="period_5_days"))
    markup.add(InlineKeyboardButton("30 дней 🗓️", callback_data="period_30_days"))
    markup.add(InlineKeyboardButton("1 год 📅", callback_data="period_1_year"))
    markup.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_start"))
    
    if callback_query.message.photo:
        await callback_query.message.edit_caption(
            caption="💸 *Выберите период доступа:* 💸",
            reply_markup=markup,
            parse_mode="Markdown"
        )
    else:
        await callback_query.message.edit_text(
            text="💸 *Выберите период доступа:* 💸",
            reply_markup=markup,
            parse_mode="Markdown"
        )

@dp.callback_query_handler(lambda c: c.data.startswith('period_'))
async def process_callback_period(callback_query: types.CallbackQuery):
    period = callback_query.data.split('_')[1] + "_" + callback_query.data.split('_')[2]
    keyboard = InlineKeyboardMarkup(row_width=2)
    for currency, price in CURRENCY_PRICES[period].items():
        keyboard.add(InlineKeyboardButton(f"{currency} 💳 ({price})", callback_data=f"pay_{period}_{currency}"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_periods"))
    
    await bot.answer_callback_query(callback_query.id)
    if callback_query.message.photo:
        await callback_query.message.edit_caption(
            caption=f"💸 *Выберите валюту для оплаты* ({period.replace('_', ' ')}) 💸",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    else:
        await callback_query.message.edit_text(
            text=f"💸 *Выберите валюту для оплаты* ({period.replace('_', ' ')}) 💸",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

@dp.callback_query_handler(lambda c: c.data.startswith('pay_'))
async def process_callback_currency(callback_query: types.CallbackQuery):
    parts = callback_query.data.split('_')
    period = parts[1] + "_" + parts[2]
    asset = parts[3]
    amount = CURRENCY_PRICES[period].get(asset, 0)
    duration_days = int(period.split('_')[0])  
    invoice = create_invoice(asset=asset, amount=amount, description=f"Оплата через CryptoBot на {duration_days} дней")
    
    if invoice and 'result' in invoice:
        invoice_id = invoice['result']['invoice_id']
        pay_url = invoice['result']['pay_url']
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton("💳 Оплатить", url=pay_url))
        markup.add(InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_{invoice_id}_{duration_days}"))
        markup.add(InlineKeyboardButton("🔙 Назад", callback_data=f"back_to_currencies_{period}"))
        
        await bot.answer_callback_query(callback_query.id)
        if callback_query.message.photo:
            await callback_query.message.edit_caption(
                caption="💸 *Оплатите по кнопке ниже и нажмите кнопку 'Проверить оплату'* 💸",
                reply_markup=markup,
                parse_mode="Markdown"
            )
        else:
            await callback_query.message.edit_text(
                text="💸 *Оплатите по кнопке ниже и нажмите кнопку 'Проверить оплату'* 💸",
                reply_markup=markup,
                parse_mode="Markdown"
            )
    else:
        await bot.answer_callback_query(callback_query.id, "❌ Ошибка при создании счета")

@dp.callback_query_handler(lambda c: c.data.startswith('back_to_'))
async def process_callback_back(callback_query: types.CallbackQuery):
    data = callback_query.data.split('_')
    if data[2] == "periods":
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("1 день 🕐", callback_data="period_1_day"))
        markup.add(InlineKeyboardButton("2 дня 🕑", callback_data="period_2_days"))
        markup.add(InlineKeyboardButton("5 дней 🕔", callback_data="period_5_days"))
        markup.add(InlineKeyboardButton("30 дней 🗓️", callback_data="period_30_days"))
        markup.add(InlineKeyboardButton("1 год 📅", callback_data="period_1_year"))
        markup.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_start"))
        
        if callback_query.message.photo:
            await callback_query.message.edit_caption(
                caption="💸 *Выберите период доступа:* 💸",
                reply_markup=markup,
                parse_mode="Markdown"
            )
        else:
            await callback_query.message.edit_text(
                text="💸 *Выберите период доступа:* 💸",
                reply_markup=markup,
                parse_mode="Markdown"
            )
    elif data[2] == "currencies":
        period = data[3] + "_" + data[4]
        keyboard = InlineKeyboardMarkup(row_width=2)
        for currency, price in CURRENCY_PRICES[period].items():
            keyboard.add(InlineKeyboardButton(f"{currency} 💳 ({price})", callback_data=f"pay_{period}_{currency}"))
        keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_periods"))
        
        await bot.answer_callback_query(callback_query.id)
        if callback_query.message.photo:
            await callback_query.message.edit_caption(
                caption=f"💸 *Выберите валюту для оплаты* ({period.replace('_', ' ')}) 💸",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        else:
            await callback_query.message.edit_text(
                text=f"💸 *Выберите валюту для оплаты* ({period.replace('_', ' ')}) 💸",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
    elif data[2] == "start":
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("Перейти к оплате", callback_data="go_to_payment"))
        
        if callback_query.message.photo:
            await callback_query.message.edit_caption(
                caption="🚀 Чтобы получить доступ к боту, необходимо оплатить подписку. Нажмите кнопку ниже, чтобы перейти к оплате.",
                reply_markup=markup
            )
        else:
            await callback_query.message.edit_text(
                text="🚀 Чтобы получить доступ к боту, необходимо оплатить подписку. Нажмите кнопку ниже, чтобы перейти к оплате.",
                reply_markup=markup
            )


import asyncio

@dp.callback_query_handler(lambda c: c.data.startswith('check_'))
async def process_callback_check(callback_query: types.CallbackQuery):
    logging.info(f"Processing callback with data: {callback_query.data}")  
    parts = callback_query.data.split('_')
    if len(parts) != 3:
        logging.error(f"Invalid callback data format: {callback_query.data}")
        await bot.answer_callback_query(callback_query.id, "❌ Ошибка: неверный формат данных.")
        return

    invoice_id = parts[1]
    duration_days = int(parts[2])
    logging.info(f"Checking invoice status for ID: {invoice_id}")
    status = check_invoice_status(invoice_id)
    if status and 'result' in status:
        invoice_status = status['result']['items'][0]['status']
        logging.info(f"Invoice status: {invoice_status}")
        if invoice_status == 'paid':
            await save_paid_user(callback_query.from_user.id, duration_days)
            await bot.answer_callback_query(callback_query.id)
            await bot.send_message(callback_query.from_user.id, "✅ Оплата подтверждена! Теперь вы можете пользоваться ботом.",
                                  reply_markup=InlineKeyboardMarkup().add(
                                      InlineKeyboardButton("Запуск", callback_data="send_welcome")
                                  ))
        elif invoice_status == 'active':
            await bot.answer_callback_query(callback_query.id)
            msg = await bot.send_message(callback_query.from_user.id, "❌ Оплата еще не выполнена. Пожалуйста, оплатите чек и нажмите 'Проверить оплату' снова.")
            await asyncio.sleep(3)
            await bot.delete_message(callback_query.from_user.id, msg.message_id)
        elif invoice_status in ['expired', 'failed']:
            await bot.answer_callback_query(callback_query.id)
            msg = await bot.send_message(callback_query.from_user.id, "❌ Вы не оплатили чек. Пожалуйста, оплатите чек для начала.")
            await asyncio.sleep(3)
            await bot.delete_message(callback_query.from_user.id, msg.message_id)
    else:
        await bot.answer_callback_query(callback_query.id)
        msg = await bot.send_message(callback_query.from_user.id, "❌ Вы не оплатили чек. Пожалуйста, оплатите чек для начала.")
        await asyncio.sleep(3)
        await bot.delete_message(callback_query.from_user.id, msg.message_id)

async def save_paid_user(user_id, duration_days):
    expiry_time = datetime.now() + timedelta(days=duration_days)
    expiry_time_str = expiry_time.strftime('%Y-%m-%d %H:%M:%S')
    
    if not os.path.exists('paid_users.txt'):
        with open('paid_users.txt', 'w') as file:
            file.write(f"{user_id},{expiry_time_str}\n")
        return
    
    with open('paid_users.txt', 'r') as file:
        lines = file.readlines()
    
    updated = False
    updated_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        try:
            paid_user_id, paid_expiry_time_str = line.split(',')
            paid_expiry_time = datetime.strptime(paid_expiry_time_str, '%Y-%m-%d %H:%M:%S')
            if paid_user_id == str(user_id):
                if paid_expiry_time > datetime.now():
                    expiry_time += paid_expiry_time - datetime.now()
                    expiry_time_str = expiry_time.strftime('%Y-%m-%d %H:%M:%S')
                updated_lines.append(f"{paid_user_id},{expiry_time_str}\n")
                updated = True
            else:
                updated_lines.append(line + '\n')
        except ValueError as e:
            print(f"Ошибка при обработке строки '{line}': {e}")
            continue
    
    if not updated:
        updated_lines.append(f"{user_id},{expiry_time_str}\n")
    
    with open('paid_users.txt', 'w') as file:
        file.writelines(updated_lines)

async def get_remaining_time(user_id):
    if str(user_id) in admin_chat_ids:
        return "∞ (Администратор)"
    if not os.path.exists('paid_users.txt'):
        return "Нет доступа"
    with open('paid_users.txt', 'r') as file:
        lines = file.readlines()
        for line in lines:
            paid_user_id, expiry_time_str = line.strip().split(',')
            if paid_user_id == str(user_id):
                expiry_time = datetime.strptime(expiry_time_str, '%Y-%m-%d %H:%M:%S')
                remaining_time = expiry_time - datetime.now()
                if remaining_time.total_seconds() > 0:
                    days = remaining_time.days
                    hours, remainder = divmod(remaining_time.seconds, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    return f"{days} дней, {hours} часов, {minutes} минут, {seconds} секунд"
                else:
                    return "Время истекло"
    return "Нет доступа"

@dp.callback_query_handler(lambda c: c.data == 'my_time')
async def process_callback_my_time(callback_query: types.CallbackQuery):
    remaining_time = await get_remaining_time(callback_query.from_user.id)
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, f"⏳ Ваше оставшееся время: {remaining_time}")

@dp.callback_query_handler(lambda call: True)
async def handle_callbacks(call: types.CallbackQuery, state: FSMContext):
    user_id = call.from_user.id    
    if str(user_id) in admin_chat_ids:
        pass
    else:
        if user_id in banned_users:
            await call.answer('🚨 Вы забанены администратором 🚨')
            return
        if call.data != 'pay' and not await check_payment(user_id):
            await call.answer('⏳ Ваше время доступа истекло. Пожалуйста, оплатите снова.')
            await call.message.answer(
                "⏳ Ваше время доступа истекло. Пожалуйста, оплатите снова.",
                reply_markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("Оплатить", callback_data="go_to_payment")  
                )
            )
            return  
    if call.data == 'support':
        await call.message.answer('📝 Пожалуйста, напишите ваше сообщение для поддержки:')
        await SupportStates.message.set()
    elif call.data == 'email_complaint':
        await call.message.answer('📧 Введите тему письма:')
        await ComplaintStates.subject.set()
    elif call.data == 'website_complaint':
        await call.message.answer('🌐 Введите текст для отправки на сайт:')()
        await ComplaintStates.text_for_site.set()
    elif call.data == 'create_account':
        await call.message.answer('📱 Введите ваш номер телефона:')
        await CreateAccountStates.phone.set()
    elif call.data == 'report_message':
        await call.message.answer('🔗 Введите ссылку на сообщение:')
        await ReportStates.message_link.set()
    elif call.data == 'restore_account':
        await call.message.answer('📱 Введите номер телефона для восстановления аккаунта:')
        await RestoreAccountStates.phone.set()
    elif call.data == 'go_to_payment':  
        await call.message.answer("ℹ️ Выберите способ оплаты:", reply_markup=payment_keyboard)
    await call.answer()

@dp.message_handler(state=RestoreAccountStates.phone)
async def process_restore_phone(message: types.Message, state: FSMContext):
    phone_number = message.text
    await state.update_data(phone_number=phone_number)
    await message.answer("📝Введите количество отправок:")
    await RestoreAccountStates.send_count.set()

@dp.message_handler(state=RestoreAccountStates.send_count)
async def process_send_count(message: types.Message, state: FSMContext):
    try:
        send_count = int(message.text)
        if send_count <= 0:
            raise ValueError("Количество отправок должно быть больше 0")
    except ValueError as e:
        await message.answer(f"❌ Ошибка: {e}. Пожалуйста, введите корректное число.")
        return

    data = await state.get_data()
    phone_number = data.get("phone_number")
    target_email = "recover@telegram.org"
    subject = f"Banned phone number: {phone_number}"
    body = (
        f"I'm trying to use my mobile phone number: {phone_number}\n"
        "But Telegram says it's banned. Please help.\n\n"
        "App version: 11.4.3 (54732)\n"
        "OS version: SDK 33\n"
        "Device Name: samsungSM-A325F\n"
        "Locale: ru"
    )

    for _ in range(send_count):
        sender_email, sender_password = random.choice(list(senders.items()))
        success, result = await send_email(
            receiver=target_email,
            sender_email=sender_email,
            sender_password=sender_password,
            subject=subject,
            body=body
        )
        if success:
            await message.answer(f'✅ Письмо успешно отправлено на [{target_email}] от [{sender_email}]')
        else:
            await message.answer(f'❌ Ошибка при отправке письма на [{target_email}] от [{sender_email}]: {result}')
            break

    await state.finish()
        
@dp.message_handler(state=CreateAccountStates.phone)
async def process_phone_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢Администратор посчитал ваш аккаунт подозрительным и вы были забанены📢')
        return
    
    phone = message.text.replace('+', '') 
    if not phone or not phone.isdigit():
        await message.answer('❌ Введите корректный номер телефона.')
        return
    
    session_name = f"session_{phone}"
    session_path = os.path.join(session_dir, session_name)
    client = TelegramClient(session_path, api_id=api_id, api_hash=api_hash)
    
    await client.connect()
    if not await client.is_user_authorized():
        try:
            result = await client.send_code_request(phone)
            phone_code_hash = result.phone_code_hash
            async with state.proxy() as data:
                data['phone'] = phone
                data['phone_code_hash'] = phone_code_hash
            await message.answer('📩 Введите код подтверждения:', reply_markup=create_code_keyboard())
            await CreateAccountStates.next()
        except errors.PhoneNumberInvalidError:
            await message.answer('❌ Неверный номер телефона. Пожалуйста, попробуйте еще раз.')
        finally:
            await client.disconnect()
    else:
        await message.answer('❌ Аккаунт уже авторизован.')
        await state.finish()
        await client.disconnect()

def create_code_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=3)
    keyboard.row(
        InlineKeyboardButton("1", callback_data="code_1"),
        InlineKeyboardButton("2", callback_data="code_2"),
        InlineKeyboardButton("3", callback_data="code_3")
    )
    keyboard.row(
        InlineKeyboardButton("4", callback_data="code_4"),
        InlineKeyboardButton("5", callback_data="code_5"),
        InlineKeyboardButton("6", callback_data="code_6")
    )
    keyboard.row(
        InlineKeyboardButton("7", callback_data="code_7"),
        InlineKeyboardButton("8", callback_data="code_8"),
        InlineKeyboardButton("9", callback_data="code_9")
    )
    keyboard.row(
        InlineKeyboardButton("Очистить", callback_data="code_clear"),
        InlineKeyboardButton("0", callback_data="code_0"),
        InlineKeyboardButton("Подтвердить", callback_data="code_confirm")
    )
    return keyboard

@dp.callback_query_handler(lambda c: c.data.startswith('code_'), state=CreateAccountStates.code)
async def process_code_callback(callback_query: types.CallbackQuery, state: FSMContext):
    action = callback_query.data.split('_')[1]
    async with state.proxy() as data:
        code = data.get('code', '')
        
        if action == 'clear':
            code = ''
        elif action == 'confirm':
            if len(code) == 5:
                data['code'] = code
                await bot.answer_callback_query(callback_query.id)
                await process_code_step(callback_query.message, state)
                return
            else:
                await bot.answer_callback_query(callback_query.id, text="Код должен состоять из 5 цифр.")
                return
        else:
            if len(code) < 5:
                code += action
        
        data['code'] = code
    
    await bot.edit_message_text(f'📩 Введите код подтверждения: {code}', callback_query.from_user.id, callback_query.message.message_id, reply_markup=create_code_keyboard())

@dp.message_handler(state=CreateAccountStates.code)
async def process_code_step(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        code = data.get('code', '')
    
    if not code or len(code) != 5:
        await message.answer('❌ Введите корректный код подтверждения.')
        return
    
    async with state.proxy() as data:
        phone = data['phone']
        phone_code_hash = data['phone_code_hash']
    session_name = f"session_{phone}"
    session_path = os.path.join(session_dir, session_name)
    client = TelegramClient(session_path, api_id=api_id, api_hash=api_hash)
    
    await client.connect()
    try:
        await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
    except errors.SessionPasswordNeededError:
        await message.answer('🔒 Введите пароль от 2FA:')
        await CreateAccountStates.next()
    except Exception as e:
        await message.answer(f'❌ Ошибка при авторизации: {e}')
        await state.finish()
    else:
        await message.answer(f'✅ Аккаунт успешно создан и сохранен как {session_name}.session')
        await state.finish()
    finally:
        await client.disconnect()

@dp.message_handler(state=CreateAccountStates.password)
async def process_password_step(message: types.Message, state: FSMContext):
    password = message.text
    async with state.proxy() as data:
        phone = data['phone']
    session_name = f"session_{phone}"
    session_path = os.path.join(session_dir, session_name)
    client = TelegramClient(session_path, api_id=api_id, api_hash=api_hash)
    
    await client.connect()
    try:
        await client.sign_in(password=password)
    except Exception as e:
        await message.answer(f'❌ Ошибка при авторизации: {e}')
    else:
        await message.answer(f'✅ Аккаунт успешно создан и сохранен как {session_name}.session')
    finally:
        await state.finish()
        await client.disconnect()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dp.message_handler(state=ReportStates.message_link)
async def process_message_link_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢 Администратор посчитал ваш аккаунт подозрительным, и вы были забанены. 📢')
        return
    
    message_links = message.text.split()
    if not all(re.match(r'^https://t\.me/[^/]+/\d+(/\d+)?$|^https://t\.me/c/\d+/\d+$', link) for link in message_links):
        await message.answer(
            '❌ *Неверный формат ссылки на сообщение.*\n'
            'Пожалуйста, введите ссылки в формате:\n'
            '`https://t.me/username/message_id`\n'
            '`https://t.me/username/message_id/additional_info`\n'
            '`https://t.me/c/channel_id/message_id`',
            parse_mode="Markdown"
        )
        return
    
    async with state.proxy() as data:
        data['message_links'] = message_links
    
    session_files = [f for f in os.listdir(session_dir) if f.endswith('.session')]
    if not session_files:
        await message.answer('❌ Нет доступных сессий. Пожалуйста, создайте аккаунт сначала.')
        await state.finish()
        return
    
    client = TelegramClient(os.path.join(session_dir, session_files[0]), api_id=api_id, api_hash=api_hash)
    await client.connect()
    
    try:
        users_info = {}
        target_user_ids = set()

        for message_link in message_links:
            parts = message_link.split('/')
            if parts[3] == 'c':
                chat_id = int(f"-100{parts[4]}")
                message_id = int(parts[5])
                try:
                    chat = await client.get_entity(chat_id)
                except errors.ChannelPrivateError:
                    await message.answer(f'❌ Канал или группа является приватным. Доступ запрещен.')
                    continue
                except Exception as e:
                    logger.error(f"Ошибка при получении информации о канале/группе: {e}")
                    await message.answer(f'❌ Ошибка при обработке ссылки на канал/группу.')
                    continue
            else:
                chat_username = parts[3]
                message_id = int(parts[4])
                try:
                    chat = await client.get_entity(chat_username)
                except errors.UsernameNotOccupiedError:
                    await message.answer(f'❌ Группа или канал с именем `{chat_username}` не существует.', parse_mode="Markdown")
                    continue
                except errors.ChannelPrivateError:
                    await message.answer(f'❌ Группа или канал `{chat_username}` является приватным. Доступ запрещен.', parse_mode="Markdown")
                    continue

            try:
                await client(JoinChannelRequest(chat))
            except errors.ChannelPrivateError:
                await message.answer(f'❌ Группа или канал `{chat_username}` является приватной. Доступ запрещен.', parse_mode="Markdown")
                continue
            except errors.UserAlreadyParticipantError:
                pass  

            try:
                full_chat = await client(GetFullChannelRequest(chat))
                chat_members_count = full_chat.full_chat.participants_count if hasattr(full_chat.full_chat, 'participants_count') else "Скрыто"
            except Exception as e:
                logger.error(f"Ошибка при получении информации о группе/канале: {e}")
                chat_members_count = "Скрыто"
            
            target_message = await client.get_messages(chat_id if parts[3] == 'c' else chat, ids=message_id)
            if not target_message:
                await message.answer(f'❌ Сообщение по ссылке `{message_link}` не найдено. Пожалуйста, проверьте правильность ссылки.', parse_mode="Markdown")
                continue
            
            user_id = target_message.sender_id
            user = await client.get_entity(user_id)
            user_info = f"@{user.username}" if user.username else f"ID: {user.id}"            
            if user.id in private_users["ids"] or (user.username and user.username in private_users["usernames"]):
                await message.answer(f'❌ Это приватный пользователь: `{user_info}`. Жалоба на него невозможна.', parse_mode="Markdown")
                continue
            
            premium_status = "✅" if user.premium else "❌"
            is_bot = "🤖 Бот" if user.bot else "👤 Человек"
            user_phone = user.phone if user.phone else "Не указан"
            user_first_name = user.first_name if user.first_name else "Не указано"
            user_last_name = user.last_name if user.last_name else "Не указано"
            
            chat_title = (await client.get_entity(chat_id if parts[3] == 'c' else chat)).title
            
            if user_info not in users_info:
                users_info[user_info] = {
                    "premium_status": premium_status,
                    "is_bot": is_bot,
                    "chat_title": chat_title,
                    "chat_members_count": chat_members_count,
                    "user_phone": user_phone,
                    "user_first_name": user_first_name,
                    "user_last_name": user_last_name,
                    "messages": []
                }
            
            message_type = target_message.media.__class__.__name__ if target_message.media else 'text'
            message_text = target_message.text if message_type == 'text' else f"{message_type.capitalize()}"
            message_date = target_message.date.strftime("%Y-%m-%d %H:%M:%S")
            
            users_info[user_info]["messages"].append(f"{message_text} (ID: {message_id}, Дата: {message_date})")
            target_user_ids.add(user_id)
        
        async with state.proxy() as data:
            data['target_user_ids'] = list(target_user_ids)
        
        report_message = ""
        for user_info, details in users_info.items():
            messages_text = "\n".join(details["messages"])
            report_message += (
                f"👤 *Пользователь:* `{user_info}`\n"
                f"📄 *Сообщение:*\n`{messages_text}`\n"
                f"✅ *Робочих сессий:* `{len(session_files)}`\n"
                f"👑 *Премиум:* {details['premium_status']}\n"
                f"👤/🤖 *Тип:* {details['is_bot']}\n"
                f"👥 *Группа:* `{details['chat_title']}`\n"
                f"👥 *Участников в группе:* `{details['chat_members_count']}`\n"
                f"📱 *Телефон:* `{details['user_phone']}`\n"
                f"👤 *Имя:* `{details['user_first_name']}`\n"
                f"👤 *Фамилия:* `{details['user_last_name']}`\n\n"
            )
        
        await message.answer(report_message.strip(), parse_mode="Markdown")
        markup = InlineKeyboardMarkup(row_width=2)
        btn_spam = InlineKeyboardButton('🚫 1. Спам', callback_data='option_1')
        btn_violence = InlineKeyboardButton('🔪 2. Насилие', callback_data='option_2')
        btn_child_abuse = InlineKeyboardButton('👶 3. Насилие над детьми', callback_data='option_3')
        btn_pornography = InlineKeyboardButton('🔞 4. Порнография', callback_data='option_4')
        btn_copyright = InlineKeyboardButton('©️ 5. Нарушение авторских прав', callback_data='option_5')
        btn_personal_details = InlineKeyboardButton('👤 6. Личные данные', callback_data='option_6')
        btn_geo_irrelevant = InlineKeyboardButton('🌍 7. Геонерелевантный', callback_data='option_7')
        btn_fake = InlineKeyboardButton('🎭 8. Фальшивка', callback_data='option_8')
        btn_illegal_drugs = InlineKeyboardButton('💊 9. Наркотики', callback_data='option_9')

        markup.row(btn_spam, btn_violence)
        markup.row(btn_child_abuse, btn_pornography)
        markup.row(btn_copyright, btn_personal_details)
        markup.row(btn_geo_irrelevant, btn_fake)
        markup.row(btn_illegal_drugs)
        
        await message.answer('🚨 *Выберите причину репорта:*', reply_markup=markup, parse_mode="Markdown")
        await ReportStates.next()
    except errors.FloodWaitError as e:
        logger.error(f"FloodWaitError: {e}")
        await asyncio.sleep(e.seconds)
        await message.answer('❌ Ошибка при получении сообщений. Попробуйте позже.')
        await state.finish()
    except Exception as e:
        logger.error(f"Error: {e}")
        await message.answer('❌ Ошибка при получении сообщений.')
        await state.finish()
    finally:
        await client.disconnect()

@dp.callback_query_handler(lambda c: c.data.startswith('option_'), state=ReportStates.option)
async def process_option_step(call: types.CallbackQuery, state: FSMContext):
    option = call.data.split('_')[1]
    async with state.proxy() as data:
        data['option'] = option

    await call.message.answer('🚨 *Начинаем отправку репортов...* 🚨', parse_mode="Markdown")
    await send_reports(call, call.message, state)


async def send_reports(call: types.CallbackQuery, message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        message_links = data['message_links']
        option = data['option']
    
    session_files = [f for f in os.listdir(session_dir) if f.endswith('.session')]
    if not session_files:
        await message.answer('❌ Нет доступных сессий. Пожалуйста, создайте аккаунт сначала.')
        await state.finish()
        return
    
    total_reports = 0
    failed_reports = 0
    session_count = 0
    target_user_ids = set()
    private_users_skipped = []
    sent_reports_details = []  

    result_message = await message.answer(
        "📊 *Статус отправки репортов:*\n"
        "✅ Успешно отправлено репортов: `0`\n"
        "❌ Неудачно отправлено репортов: `0`\n"
        "?? Отправлено с сессий: `0`\n"
        "📝 *Последний текст репорта:*\n"
        "`Нет данных`",
        parse_mode="Markdown"
    )

    async def process_message_link(message_link, session_file):
        nonlocal total_reports, failed_reports
        parts = message_link.split('/')
        if parts[3] == 'c':
            chat_id = int(f"-100{parts[4]}")
            message_id = int(parts[5])
        else:
            chat_username = parts[3]
            message_id = int(parts[4])
        
        session_name = session_file.replace('.session', '')
        client = TelegramClient(os.path.join(session_dir, session_file), api_id=api_id, api_hash=api_hash)
        
        try:
            await client.connect()

            if not await client.is_user_authorized():
                failed_reports += 1
                return

            try:
                if parts[3] == 'c':
                    chat = await client.get_entity(chat_id)
                else:
                    chat = await client.get_entity(chat_username)
                    await client(JoinChannelRequest(chat))
                
                target_message = await client.get_messages(chat, ids=message_id)
                if not target_message:
                    failed_reports += 1
                    return
                
                user = await client.get_entity(target_message.sender_id)
                if user.id in private_users["ids"] or (user.username and user.username in private_users["usernames"]):
                    private_users_skipped.append(f"❌ Это приватный пользователь: {user.username or user.id}. Репорт на него не отправлен.")
                    return
                
                report_text = generate_report_text(user, message_link, option, target_message, chat)
                report_option = option_mapping.get(option, "0")  
                await client(ReportRequest(
                    peer=chat,  
                    id=[message_id],  
                    option=report_option,  
                    message=report_text  
                ))
                
                total_reports += 1
                target_user_ids.add(target_message.sender_id)
                sent_reports_details.append(report_text) 
            except errors.FloodWaitError as e:
                await asyncio.sleep(e.seconds)
                failed_reports += 1
            except errors.UsernameNotOccupiedError:
                failed_reports += 1
            except errors.ChatWriteForbiddenError:
                failed_reports += 1
            except Exception as e:
                failed_reports += 1
                print(f"Ошибка при обработке сообщения: {e}")
        finally:
            await client.disconnect()

    async def update_result_message():
        private_users_info = "\n".join(private_users_skipped) if private_users_skipped else ""
        last_report_text = sent_reports_details[-1] if sent_reports_details else "`Нет данных`"
        try:
            await result_message.edit_text(
                "📊 *Статус отправки репортов:*\n"
                f"✅ Успешно отправлено репортов: `{total_reports}`\n"
                f"❌ Неудачно отправлено репортов: `{failed_reports}`\n"
                f"🔄 Отправлено с сессий: `{session_count}`\n"
                f"📝 *Последний текст репорта:*\n"
                f"`{last_report_text}`\n\n"
                f"{private_users_info}",
                parse_mode="Markdown"
            )
        except exceptions.MessageNotModified:
            pass

    for session_file in session_files:
        for link in message_links:
            await process_message_link(link, session_file)
            await update_result_message()

        session_count += 1
        await update_result_message()

    async with state.proxy() as data:
        data['target_user_ids'] = list(target_user_ids)

    try:
        private_users_info = "\n".join(private_users_skipped) if private_users_skipped else ""
        sent_reports_info = "\n\n".join(sent_reports_details) if sent_reports_details else "`Нет данных`"
        await result_message.edit_text(
            "🎉 *Репорты отправлены!*\n"
            f"✅ Успешно отправлено репортов: `{total_reports}`\n"
            f"🔄 Использовано сессий: `{session_count}`\n\n"
            "📝 *Тексты отправленных репортов:*\n"
            f"`{sent_reports_info}`\n\n"
            f"{private_users_info}",
            parse_mode="Markdown"
        )
    except exceptions.MessageNotModified:
        pass

    async with state.proxy() as data:
        user_id = call.from_user.id
        target_user_ids = data.get('target_user_ids', [])
        tracking_list = load_tracking_list()

        new_accounts_added = 0

        for target_user_id in target_user_ids:
            if target_user_id in private_users["ids"]:
                private_users_skipped.append(f'❌ Это приватный пользователь: ID {target_user_id}. Добавление в список отслеживания невозможно.')
                continue

            if target_user_id in tracking_list.get(user_id, []):
                await call.message.answer(f"🚨 Вы уже следите за аккаунтом {target_user_id}.")
            else:
                await add_to_tracking_list(user_id, target_user_id)
                await call.message.answer(f"✅ Вы начали следить за аккаунтом {target_user_id}.")
                new_accounts_added += 1

        if new_accounts_added > 0:
            await call.message.answer(f"✅ Вы начали следить за {new_accounts_added} аккаунтами.")
            
def generate_report_text(user, message_link, option, target_message, chat):
    if user.username:
        user_mention = f"@{user.username}"
    else:
        user_mention = f"пользователь с ID {user.id}"
    user_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    if user_name:
        user_info = f"{user_name} ({user_mention})"
    else:
        user_info = user_mention
    if target_message.media:
        message_type = target_message.media.__class__.__name__.lower()
        if message_type == "messagemediadocument":
            message_type = "документ"
        elif message_type == "messagemediaphoto":
            message_type = "фото"
        elif message_type == "messagemediawebpage":
            message_type = "ссылка на веб-страницу"
        else:
            message_type = "медиафайл"
    else:
        message_type = "текстовое сообщение"
    message_date = target_message.date.strftime("%d.%m.%Y в %H:%M")
    chat_title = chat.title if hasattr(chat, 'title') else "неизвестном чате"
    reason_text = reason_mapping.get(option, "неизвестная причина")
    report_templates = [
        f"Пользователь {user_info} нарушил правила платформы, отправив {message_type} в {chat_title} {message_date}. "
        f"Ссылка на сообщение: {message_link}. Причина жалобы: {reason_text}. Прошу принять меры.",

        f"Обнаружено нарушение от {user_info}. {message_type.capitalize()} было отправлено {message_date} в {chat_title}. "
        f"Ссылка на сообщение: {message_link}. Причина: {reason_text}. Пожалуйста, рассмотрите эту жалобу.",

        f"Жалоба на {user_info}. Пользователь отправил {message_type} {message_date} в {chat_title}. "
        f"Ссылка на сообщение: {message_link}. Причина: {reason_text}. Требуются соответствующие меры.",

        f"{user_info} отправил неподобающее сообщение в {chat_title} {message_date}. "
        f"Тип сообщения: {message_type}. Ссылка: {message_link}. Причина жалобы: {reason_text}. Прошу разобраться.",

        f"Нарушение правил платформы. {user_info} отправил {message_type} {message_date} в {chat_title}. "
        f"Ссылка на сообщение: {message_link}. Причина: {reason_text}. Пожалуйста, примите меры."
    ]
    return random.choice(report_templates)
 #####                       
async def add_to_tracking_list(user_id, target_user_id):
    tracking_list = load_tracking_list()
    if user_id not in tracking_list:
        tracking_list[user_id] = []
    if target_user_id not in tracking_list[user_id]:
        tracking_list[user_id].append(target_user_id)
        save_tracking_list(tracking_list)


def save_tracking_list(tracking_list):
    with open('tracking_list.txt', 'w') as file:
        for user_id, target_user_ids in tracking_list.items():
            file.write(f"{user_id}:{','.join(map(str, target_user_ids))}\n")


def load_tracking_list():
    try:
        with open('tracking_list.txt', 'r') as file:
            tracking_list = {}
            for line in file:
                user_id, target_user_ids = line.strip().split(':')
                tracking_list[int(user_id)] = [int(uid) for uid in target_user_ids.split(',')]
            return tracking_list
    except FileNotFoundError:
        with open('tracking_list.txt', 'w') as file:
            pass
        return {}
    except (ValueError, PermissionError, IsADirectoryError) as e:
        print(f"Error loading tracking list: {e}")
        return {}


async def notify_users_about_status():
    tracking_list = load_tracking_list()
    for user_id, target_user_ids in tracking_list.items():
        for target_user_id in target_user_ids:
            status, _ = await check_account_status(target_user_id)
            if status is False:
                await bot.send_message(user_id, f"✅ Аккаунт {target_user_id} был успешно удален.")
                tracking_list[user_id].remove(target_user_id)
                if not tracking_list[user_id]:
                    del tracking_list[user_id]
    save_tracking_list(tracking_list)


async def background_status_checker():
    while True:
        await notify_users_about_status()
        await asyncio.sleep(3600)


async def on_startup(dp):
    asyncio.create_task(background_status_checker())

@dp.message_handler(state=ComplaintStates.subject)
async def process_subject_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢Администратор посчитал ваш аккаунт подозрительным и вы были забанены📢')
        return
    
    async with state.proxy() as data:
        data['subject'] = message.text
    await message.answer('📝 Введите текст жалобы:')
    await ComplaintStates.next()

@dp.message_handler(state=ComplaintStates.body)
async def process_body_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢Администратор посчитал ваш аккаунт подозрительным и вы были забанены📢')
        return
    
    async with state.proxy() as data:
        data['body'] = message.text
    
    await message.answer('🖼 Хотите добавить фотографии? (Да/Нет):')
    await ComplaintStates.photos.set()  

@dp.message_handler(state=ComplaintStates.photos)
async def process_photo_choice_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢Администратор посчитал ваш аккаунт подозрительным и вы были забанены📢')
        return
    
    add_photo = message.text.lower()
    if add_photo == 'да':
        await message.answer('📎 Пожалуйста, отправьте фотографии:')
    elif add_photo == 'нет':
        await message.answer('🔢 Введите количество отправок (не больше 50):')
        await ComplaintStates.count.set()  
    else:
        await message.answer('❌ Неверный ввод. Пожалуйста, ответьте "Да" или "Нет":')

@dp.message_handler(content_types=['photo'], state=ComplaintStates.photos)
async def process_photos_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢Администратор посчитал ваш аккаунт подозрительным и вы были забанены📢')
        return
    
    photos = []
    for photo in message.photo:
        file_info = await bot.get_file(photo.file_id)
        downloaded_file = await bot.download_file(file_info.file_path)
        photos.append(downloaded_file.read())  
    
    async with state.proxy() as data:
        data['photos'] = photos
    
    await message.answer('🔢 Введите количество отправок (не больше 50):')
    await ComplaintStates.next()

@dp.message_handler(state=ComplaintStates.count)
async def process_count_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢 Администратор посчитал ваш аккаунт подозрительным, и вы были забанены! 📢')
        return
    
    try:
        count = int(message.text)
        if count > 50:
            await message.answer('🚫 Количество отправок не должно превышать 50. Повторите ввод:')
            return
    except ValueError:
        await message.answer('🔢 Пожалуйста, введите число. Повторите ввод:')
        return
    
    async with state.proxy() as data:
        subject = data['subject']
        body = data['body']
        photos = data.get('photos', []) 
    
    for word in body.split():
        if word.startswith('@') and word[1:] in private_users["usernames"]:
            await message.answer(f'❌ Это приватный пользователь: {word}. Жалоба на него невозможна.')
            return
        if word.isdigit() and int(word) in private_users["ids"]:
            await message.answer(f'❌ Это приватный пользователь: ID {word}. Жалоба на него невозможна.')
            return
    
    success_count = 0
    fail_count = 0
    status_message = await message.answer("🔄 Начинаю отправку...")
    
    for _ in range(count):
        receiver = random.choice(receivers)
        sender_email, sender_password = random.choice(list(senders.items()))
        success, error_message = await send_email(
            receiver, sender_email, sender_password, subject, body, photos,
            chat_id=message.chat.id, message_id=status_message.message_id, bot=bot
        )
        send_result_message = (
            f"📌 Тема письма: {subject}\n"
            f"📝 Текст письма: {body}\n"
            f"📩 Отправитель: {sender_email}\n"
            f"📨 Получатель: {receiver}\n"
            f"📷 Фото: {'С фото' if photos else 'Без фото'}\n"  
            f"📌 Статус отправки: {'✅ Успешно' if success else '❌ Не удачно'}\n"
            f"💬 Сообщение: {error_message if not success else 'Письмо отправлено'}"
        )
        
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=status_message.message_id,
            text=send_result_message
        )
        
        if success:
            success_count += 1
        else:
            fail_count += 1    
    final_message = (
        f"📊 Итоговый результат:\n"
        f"✅ Количество отправлено: {success_count}\n"
        f"❌ Не удачно отправлено: {fail_count}"
    )
    
    await bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=status_message.message_id,
        text=final_message
    )
    
    await state.finish()
    
async def send_email(receiver, sender_email, sender_password, subject, body, photos=None, chat_id=None, message_id=None, bot=None):
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    
    if photos:
        for photo in photos:
            image = MIMEImage(photo)
            msg.attach(image)
    
    try:
        domain = sender_email.split('@')[1]
        if domain not in smtp_servers:
            error_message = f'❌ Отправка не удалась в почте {sender_email}: Неизвестный домен'
            return False, error_message
        
        smtp_server, smtp_port = smtp_servers[domain]
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver, msg.as_string())
        
        logging.info(f'Email sent to {receiver} from {sender_email}')
        return True, None
    except Exception as e:
        error_message = f'❌ Ошибка при отправке письма на [{receiver}] от [{sender_email}]: {e}'
        logging.error(f'Error sending email: {e}')
        return False, error_message
            
@dp.message_handler(state=ComplaintStates.text_for_site)
async def process_text_for_site_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢Администратор посчитал ваш аккаунт подозрительным и вы были забанены📢')
        return
    
    async with state.proxy() as data:
        data['text_for_site'] = message.text
    await message.answer('🔢 Введите количество отправок (не больше 50):')
    await ComplaintStates.next()

@dp.message_handler(state=ComplaintStates.count_for_site)
async def process_count_for_site_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢Администратор посчитал ваш аккаунт подозрительным и вы были забанены📢')
        return
    
    try:
        count = int(message.text)
        if count > 50:
            await message.answer('🚫 Количество отправок не должно превышать 50. Повторите ввод:')
            return
    except ValueError:
        await message.answer('🔢 Пожалуйста, введите число. Повторите ввод:')
        return
    
    async with state.proxy() as data:
        text = data['text_for_site']
    
    words = text.split()
    for word in words:
        if word.isdigit() and int(word) in private_users["ids"]:
            await message.answer('🚫 Нельзя отправлять жалобы на приватных пользователей.')
            await state.finish()
            return
        if word in private_users["usernames"]:
            await message.answer('🚫 Нельзя отправлять жалобы на приватных пользователей.')
            await state.finish()
            return    
    status_message = await message.answer("🔄 Начинаю отправку...")
    
    success_count = 0
    fail_count = 0
    
    for _ in range(count):
        email = random.choice(mail)
        phone = random.choice(phone_numbers)
        proxy = await get_working_proxy()
        if not proxy:
            await message.answer('❌ В данный момент отсутствуют работоспособные прокси для отправки.')
            break
        
        success = await send_to_site(text, email, phone, proxy)
        if success:
            success_count += 1
        else:
            fail_count += 1
        
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=status_message.message_id,
            text=(
                f"🔄 Отправка...\n"
                f"✅ Успешно: {success_count}\n"
                f"❌ Не удачно: {fail_count}\n"
                f"📝 Текст: {text}\n"
                f"📧 Почта: {email}\n"
                f"📞 Телефон: {phone}\n"
                f"🌐 Прокси: {proxy}"
            )
        )
    final_message = (
        f"📊 Итоговый результат:\n"
        f"✅ Успешно отправлено: {success_count}\n"
        f"❌ Не удачно отправлено: {fail_count}"
    )
    
    await bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=status_message.message_id,
        text=final_message
    )
    
    await state.finish()

async def get_working_proxy():
    for proxy in proxies:
        try:
            response = requests.get('https://www.google.com', proxies=proxy, timeout=5)
            if response.status_code == 200:
                return proxy
        except Exception as e:
            logging.error(f'Proxy {proxy} is not working: {e}')
    return None

async def send_to_site(text, email, phone, proxy):
    url = "https://telegram.org/support"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": random.choice(user_agents)
    }
    data = {
        "message": text,
        "email": email,
        "phone": phone,
        "setln": "ru"
    }
    
    try:
        response = requests.post(url, headers=headers, data=data, proxies=proxy, timeout=10)
        if response.status_code == 200:
            logging.info(f'Data sent to site: {text}, email: {email}, phone: {phone}')
            return True
        else:
            logging.error(f'Error sending data to site: {response.status_code}')
            return False
    except Exception as e:
        logging.error(f'Error sending data to site: {e}')
        return False

from aiogram.types import ParseMode

@dp.message_handler(content_types=[
    'text', 'photo', 'document', 'audio', 'voice', 'video', 'video_note', 'sticker', 'animation', 'contact', 'location', 'poll', 'dice'
], state=SupportStates.message)
async def process_support_message(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢Администратор посчитал ваш аккаунт подозрительным, и вы были забанены! 📢')
        return
    
    username = message.from_user.username or f'id{user_id}'
    content_type = message.content_type
    text = message.text or message.caption

    header = f"📨 *Новое сообщение от пользователя* @{username} (ID: `{user_id}`):\n\n"
    footer = "\n\n_Это сообщение отправлено автоматически._"

    for admin_id in admin_chat_ids:
        try:
            if content_type == 'text':
                await bot.send_message(
                    admin_id,
                    f"{header}📝 *Текст сообщения:*\n{text}{footer}",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif content_type == 'photo':
                await bot.send_photo(
                    admin_id,
                    message.photo[-1].file_id,
                    caption=f"{header}📷 *Фото с подписью:*\n{text}{footer}",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif content_type == 'document':
                await bot.send_document(
                    admin_id,
                    message.document.file_id,
                    caption=f"{header}📄 *Документ с подписью:*\n{text}{footer}",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif content_type == 'audio':
                await bot.send_audio(
                    admin_id,
                    message.audio.file_id,
                    caption=f"{header}🎵 *Аудио с подписью:*\n{text}{footer}",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif content_type == 'voice':
                await bot.send_voice(
                    admin_id,
                    message.voice.file_id,
                    caption=f"{header}🎤 *Голосовое сообщение с подписью:*\n{text}{footer}",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif content_type == 'video':
                await bot.send_video(
                    admin_id,
                    message.video.file_id,
                    caption=f"{header}🎥 *Видео с подписью:*\n{text}{footer}",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif content_type == 'video_note':
                await bot.send_video_note(
                    admin_id,
                    message.video_note.file_id
                )
                await bot.send_message(
                    admin_id,
                    f"{header}🎬 *Видеосообщение (кружок) отправлено.*{footer}",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif content_type == 'sticker':
                await bot.send_sticker(
                    admin_id,
                    message.sticker.file_id
                )
                await bot.send_message(
                    admin_id,
                    f"{header}🖼 *Стикер отправлен.*{footer}",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif content_type == 'animation':
                await bot.send_animation(
                    admin_id,
                    message.animation.file_id,
                    caption=f"{header}🎞 *GIF-анимация с подписью:*\n{text}{footer}",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif content_type == 'contact':
                contact = message.contact
                await bot.send_contact(
                    admin_id,
                    phone_number=contact.phone_number,
                    first_name=contact.first_name,
                    last_name=contact.last_name
                )
                await bot.send_message(
                    admin_id,
                    f"{header}📱 *Контакт отправлен.*{footer}",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif content_type == 'location':
                location = message.location
                await bot.send_location(
                    admin_id,
                    latitude=location.latitude,
                    longitude=location.longitude
                )
                await bot.send_message(
                    admin_id,
                    f"{header}📍 *Локация отправлена.*{footer}",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif content_type == 'poll':
                poll = message.poll
                await bot.send_message(
                    admin_id,
                    f"{header}📊 *Опрос:*\n*Вопрос:* {poll.question}\n*Варианты:* {', '.join([option.text for option in poll.options])}\n{text}{footer}",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif content_type == 'dice':
                dice = message.dice
                await bot.send_message(
                    admin_id,
                    f"{header}🎲 *Игральная кость:*\n*Значение:* {dice.value}\n{text}{footer}",
                    parse_mode=ParseMode.MARKDOWN
                )
        except Exception as e:
            logging.error(f"Ошибка при отправке сообщения администратору {admin_id}: {e}")

    await message.answer('✅ Ваше сообщение отправлено в поддержку. Спасибо за обращение!')
    await state.finish()

import asyncio

async def check_and_clean_sessions():
    session_files = [f for f in os.listdir(session_dir) if f.endswith('.session')]
    for session_file in session_files:
        session_path = os.path.join(session_dir, session_file)
        client = TelegramClient(session_path, api_id=api_id, api_hash=api_hash)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                logging.info(f"Сессия {session_file} не авторизована. Удаляем.")
                os.remove(session_path)
            else:
                user = await client.get_me()
                if isinstance(user, types.User) and hasattr(user, 'is_bot') and user.is_bot:
                    logging.info(f"Сессия {session_file} принадлежит боту. Удаляем.")
                    os.remove(session_path)
        except errors.AuthKeyDuplicatedError:
            logging.error(f"Сессия {session_file} была использована под разными IP-адресами. Удаляем.")
            os.remove(session_path)
        except errors.FloodWaitError as e:
            logging.warning(f"FloodWaitError для сессии {session_file}: {e}. Повтор через {e.seconds} секунд.")
            await asyncio.sleep(e.seconds)
        except errors.RPCError as e:
            if "database is locked" in str(e):
                logging.warning(f"База данных заблокирована для сессии {session_file}. Повтор через 5 секунд.")
                await asyncio.sleep(5)
                continue
            else:
                logging.error(f"Ошибка при проверке сессии {session_file}: {e}")
                os.remove(session_path)
        except Exception as e:
            logging.error(f"Ошибка при проверке сессии {session_file}: {e}")
            os.remove(session_path)
        finally:
            try:
                await client.disconnect()
            except Exception as e:
                if "disk I/O error" in str(e):
                    logging.error(f"Ошибка при отключении сессии {session_file}: {e}. Повтор через 5 секунд.")
                    await asyncio.sleep(5)
                    try:
                        await client.disconnect()
                    except Exception as e:
                        logging.error(f"Ошибка при повторном отключении сессии {session_file}: {e}")
                else:
                    logging.error(f"Ошибка при отключении сессии {session_file}: {e}")

if __name__ == '__main__':
    loop = asyncio.get_event_loop()    
    loop.run_until_complete(check_and_clean_sessions())
    executor.start_polling(dp, skip_updates=True)
    asyncio.set_event_loop(loop)
    loop.create_task(start_background_tasks())
    try:
        executor.start_polling(dp, skip_updates=True)
    finally:
        loop.close()
    
