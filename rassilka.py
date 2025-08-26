# -*- coding: utf-8 -*-
import asyncio
import json
import os
import re
from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.client.default import DefaultBotProperties
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

TOKEN = '7959177931:AAE951wMTOXJM7vowe5VOKiPktG86npCQGU' # token @botfather
OWNER_ID ='7794270699'# admin id
DATA_FILE = 'users.json'
SESSION_DIR = 'sessions'

os.makedirs(SESSION_DIR, exist_ok=True)

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

class Form(StatesGroup):
    add_user = State()
    api_id = State()
    api_hash = State()
    phone = State()
    code = State()
    password = State()
    text = State()
    chat_id = State()
    delete_chat = State()
    interval = State()


def load_users():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'w') as f:
            json.dump({}, f)
    with open(DATA_FILE) as f:
        return json.load(f)

def save_users(users):
    with open(DATA_FILE, 'w') as f:
        json.dump(users, f, indent=4)

def is_user(uid):
    users = load_users()
    return str(uid) in users or uid == OWNER_ID

def get_user(uid):
    return load_users().get(str(uid))

def set_user(uid, data):
    users = load_users()
    users[str(uid)] = data
    save_users(users)


def main_menu(is_admin=False):
    kb = [
        [InlineKeyboardButton(text="рџ”ђ Р”РѕР±Р°РІРёС‚СЊ Р°РєРєР°СѓРЅС‚", callback_data="input_api")],
        [InlineKeyboardButton(text="рџ“Ё Р’РІРµСЃС‚Рё С‚РµРєСЃС‚", callback_data="text")],
        [InlineKeyboardButton(text="вћ• Р”РѕР±Р°РІРёС‚СЊ РєР°РЅР°Р»", callback_data="chat_id"),
         InlineKeyboardButton(text="вћ– РЈРґР°Р»РёС‚СЊ РєР°РЅР°Р»", callback_data="del_chat")],
        [InlineKeyboardButton(text="в–¶пёЏ РЎС‚Р°СЂС‚", callback_data="start"),
         InlineKeyboardButton(text="вЏ№ РЎС‚РѕРї", callback_data="stop")],
        [InlineKeyboardButton(text="вљ™пёЏ РќР°СЃС‚СЂРѕР№РєРё", callback_data="settings"),
         InlineKeyboardButton(text="вЏ± РРЅС‚РµСЂРІР°Р»", callback_data="interval")],
        [InlineKeyboardButton(text="вќ“ РљР°Рє РїРѕР»СЊР·РѕРІР°С‚СЊСЃСЏ", callback_data="how_to_use")]  # РґРѕР±Р°РІР»РµРЅР° РєРЅРѕРїРєР° "РљР°Рє РїРѕР»СЊР·РѕРІР°С‚СЊСЃСЏ"
    ]
    if is_admin:
        kb.append([InlineKeyboardButton(text="рџ‘‘ Р”РѕР±Р°РІРёС‚СЊ", callback_data="add_user")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    if not is_user(message.from_user.id):
        await message.answer("Р”РѕСЃС‚СѓРї Р·Р°РїСЂРµС‰РµРЅ")
        return
    await message.answer("Р”РѕР±СЂРѕ РїРѕР¶Р°Р»РѕРІР°С‚СЊ!", reply_markup=main_menu(message.from_user.id == OWNER_ID))


@router.callback_query(F.data == "add_user")
async def add_user_start(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != OWNER_ID:
        await call.answer("РўРѕР»СЊРєРѕ РґР»СЏ Р°РґРјРёРЅР°.", show_alert=True)
        return
    await call.message.answer("Р’РІРµРґРё user_id РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ РґР»СЏ РґРѕСЃС‚СѓРїР°:")
    await state.set_state(Form.add_user)

@router.message(Form.add_user)
async def add_user_finish(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
        users = load_users()
        if str(uid) in users:
            await message.answer("РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ СѓР¶Рµ РµСЃС‚СЊ.")
        else:
            users[str(uid)] = {}
            save_users(users)
            await message.answer("вњ… РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ РґРѕР±Р°РІР»РµРЅ.")
    except:
        await message.answer("вќЊ РќРµРІРµСЂРЅС‹Р№ user_id")
    await state.clear()


@router.callback_query(F.data == "input_api")
async def input_api_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("рџ”ђ Р’РІРµРґРёС‚Рµ РІР°С€ API ID:")
    await state.set_state(Form.api_id)

@router.message(Form.api_id)
async def input_api_hash(message: types.Message, state: FSMContext):
    await state.update_data(api_id=int(message.text.strip()))
    await message.answer("рџ”‘ РўРµРїРµСЂСЊ РІРІРµРґРёС‚Рµ API Hash:")
    await state.set_state(Form.api_hash)

@router.message(Form.api_hash)
async def input_phone(message: types.Message, state: FSMContext):
    await state.update_data(api_hash=message.text.strip())
    await message.answer("рџ“± Р’РІРµРґРёС‚Рµ РІР°С€ РЅРѕРјРµСЂ С‚РµР»РµС„РѕРЅР° РІ С„РѕСЂРјР°С‚Рµ +7...")
    await state.set_state(Form.phone)

@router.message(Form.phone)
async def send_code_request(message: types.Message, state: FSMContext):
    data = await state.get_data()
    api_id = data["api_id"]
    api_hash = data["api_hash"]
    phone = message.text.strip()

    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()
    try:
        result = await client.send_code_request(phone)
        await state.update_data(phone=phone, session=client.session.save(), phone_code_hash=result.phone_code_hash)
        await message.answer("рџ“© РљРѕРґ РѕС‚РїСЂР°РІР»РµРЅ. Р’РІРµРґРёС‚Рµ РµРіРѕ:")
        await state.set_state(Form.code)
    except Exception as e:
        await message.answer(f"вќЊ РћС€РёР±РєР° РѕС‚РїСЂР°РІРєРё РєРѕРґР°: {e}")
        await client.disconnect()

@router.message(Form.code)
async def input_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    data = await state.get_data()
    client = TelegramClient(StringSession(data['session']), data['api_id'], data['api_hash'])
    await client.connect()
    try:
        await client.sign_in(data['phone'], code, phone_code_hash=data['phone_code_hash'])
        set_user(message.from_user.id, {
            'api_id': data['api_id'],
            'api_hash': data['api_hash'],
            'session': client.session.save(),
            'text': 'РўРµСЃС‚РѕРІРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ',
            'chats': [],
            'interval': 60
        })
        await message.answer("вњ… РђРІС‚РѕСЂРёР·Р°С†РёСЏ РїСЂРѕС€Р»Р° СѓСЃРїРµС€РЅРѕ!")
        await state.clear()
    except SessionPasswordNeededError:
        await message.answer("рџ”’ Р’РєР»СЋС‡РµРЅР° РґРІСѓС…С„Р°РєС‚РѕСЂРЅР°СЏ Р°РІС‚РѕСЂРёР·Р°С†РёСЏ. Р’РІРµРґРёС‚Рµ РїР°СЂРѕР»СЊ:")
        await state.set_state(Form.password)
    except Exception as e:
        await message.answer(f"вќЊ РћС€РёР±РєР° Р°РІС‚РѕСЂРёР·Р°С†РёРё: {e}")
        await client.disconnect()

@router.message(Form.password)
async def input_2fa_password(message: types.Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()
    client = TelegramClient(StringSession(data['session']), data['api_id'], data['api_hash'])
    await client.connect()
    try:
        await client.sign_in(password=password)
        set_user(message.from_user.id, {
            'api_id': data['api_id'],
            'api_hash': data['api_hash'],
            'session': client.session.save(),
            'text': 'РўРµСЃС‚РѕРІРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ',
            'chats': [],
            'interval': 60
        })
        await message.answer("вњ… РђРІС‚РѕСЂРёР·Р°С†РёСЏ РїСЂРѕС€Р»Р° СѓСЃРїРµС€РЅРѕ!")
    except Exception as e:
        await message.answer(f"вќЊ РћС€РёР±РєР° РїСЂРё РІРІРѕРґРµ РїР°СЂРѕР»СЏ: {e}")
    await client.disconnect()
    await state.clear()


@router.callback_query(F.data == "text")
async def set_text_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("вњЏпёЏ Р’РІРµРґРёС‚Рµ С‚РµРєСЃС‚ СЂР°СЃСЃС‹Р»РєРё:")
    await state.set_state(Form.text)

@router.message(Form.text)
async def save_text(message: types.Message, state: FSMContext):
    user = get_user(message.from_user.id)
    user['text'] = message.text
    set_user(message.from_user.id, user)
    await message.answer("вњ… РўРµРєСЃС‚ СЃРѕС…СЂР°РЅС‘РЅ.")
    await state.clear()


@router.callback_query(F.data == "chat_id")
async def set_chat_id_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer(
        "рџ’¬ Р’РІРµРґРёС‚Рµ chat_id РёР»Рё @username РєР°РЅР°Р»Р°/С‡Р°С‚Р°. Р Р°Р·РґРµР»СЏР№С‚Рµ РїСЂРѕР±РµР»РѕРј, Р·Р°РїСЏС‚С‹РјРё РёР»Рё РїРµСЂРµРЅРѕСЃР°РјРё РµСЃР»Рё РёС… Р±РѕР»СЊС€Рµ 1"

    )
    await state.set_state(Form.chat_id)

@router.message(Form.chat_id)
async def save_chat_id(message: types.Message, state: FSMContext):
    user = get_user(message.from_user.id)
    text = message.text.strip()
    # Р Р°Р·Р±РёРІР°РµРј РїРѕ Р·Р°РїСЏС‚С‹Рј, РїСЂРѕР±РµР»Р°Рј, РїРµСЂРµРЅРѕСЃР°Рј
    items = re.split(r'[\s,]+', text)
    added = []
    duplicates = []

    for item in items:
        if not item:
            continue
        clean_item = item.lstrip('@')

        try:
            cid = int(clean_item)
            if cid not in user['chats']:
                user['chats'].append(cid)
                added.append(str(cid))
            else:
                duplicates.append(str(cid))
        except:
            username = '@' + clean_item
            if username not in user['chats']:
                user['chats'].append(username)
                added.append(username)
            else:
                duplicates.append(username)

    set_user(message.from_user.id, user)

    response = ""
    if added:
        response += "вњ… Р”РѕР±Р°РІР»РµРЅС‹:\n" + "\n".join(added) + "\n"
    if duplicates:
        response += "вљ пёЏ РЈР¶Рµ Р±С‹Р»Рё РґРѕР±Р°РІР»РµРЅС‹:\n" + "\n".join(duplicates) + "\n"
    if not added and not duplicates:
        response = "вќЊ РќРёС‡РµРіРѕ РЅРµ РґРѕР±Р°РІР»РµРЅРѕ. РџСЂРѕРІРµСЂСЊС‚Рµ РІРІРѕРґ."

    await message.answer(response)
    await state.clear()

@router.callback_query(F.data == "del_chat")
async def delete_chat_start(call: types.CallbackQuery, state: FSMContext):
    user = get_user(call.from_user.id)
    if not user['chats']:
        await call.message.answer("вљ пёЏ РќРµС‚ РґРѕР±Р°РІР»РµРЅРЅС‹С… С‡Р°С‚РѕРІ.")
        return
    chat_list = '\n'.join(f"{i+1}. {cid}" for i, cid in enumerate(user['chats']))
    await call.message.answer(f"Р’РІРµРґРёС‚Рµ РЅРѕРјРµСЂ С‡Р°С‚Р° РґР»СЏ СѓРґР°Р»РµРЅРёСЏ:\n{chat_list}")
    await state.set_state(Form.delete_chat)

@router.message(Form.delete_chat)
async def delete_chat_finish(message: types.Message, state: FSMContext):
    user = get_user(message.from_user.id)
    try:
        idx = int(message.text.strip()) - 1
        cid = user['chats'].pop(idx)
        set_user(message.from_user.id, user)
        await message.answer(f"вњ… Chat ID {cid} СѓРґР°Р»С‘РЅ.")
    except:
        await message.answer("вќЊ РќРµРІРµСЂРЅС‹Р№ РЅРѕРјРµСЂ")
    await state.clear()

@router.callback_query(F.data == "settings")
async def view_settings(call: types.CallbackQuery):
    user = get_user(call.from_user.id)
    await call.message.answer(f"рџ“Ё РўРµРєСЃС‚: {user.get('text')}\nрџ’¬ Р§Р°С‚С‹: {user.get('chats')}\nвЏ± РРЅС‚РµСЂРІР°Р»: {user.get('interval')} СЃРµРє.")

@router.callback_query(F.data == "interval")
async def interval_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("вЏ± Р’РІРµРґРёС‚Рµ РёРЅС‚РµСЂРІР°Р» РјРµР¶РґСѓ СЃРѕРѕР±С‰РµРЅРёСЏРјРё РІ СЃРµРєСѓРЅРґР°С…:")
    await state.set_state(Form.interval)

@router.message(Form.interval)
async def interval_finish(message: types.Message, state: FSMContext):
    try:
        seconds = int(message.text.strip())
        user = get_user(message.from_user.id)
        user['interval'] = max(5, seconds)
        set_user(message.from_user.id, user)
        await message.answer(f"вњ… РРЅС‚РµСЂРІР°Р» СѓСЃС‚Р°РЅРѕРІР»РµРЅ: {seconds} СЃРµРє")
    except:
        await message.answer("вќЊ Р’РІРµРґРёС‚Рµ С‡РёСЃР»Рѕ")
    await state.clear()

@router.callback_query(F.data == "how_to_use")
async def how_to_use_handler(call: types.CallbackQuery):
    instruction = (
        "**РџРѕРґСЂРѕР±РЅР°СЏ РёРЅСЃС‚СЂСѓРєС†РёСЏ:**\n"
        "1. Р’РѕР№С‚Рё РІ Р°РєРєР°СѓРЅС‚ С‡РµСЂРµР· **API id** Рё **HASH**\n"
        "2. РќР° Р°РєРєР°СѓРЅС‚Рµ СЃ РєРѕС‚РѕСЂРѕРіРѕ РґРѕР»Р¶РЅР° РёРґС‚Рё СЂР°СЃСЃС‹Р»РєР° РІРѕР№С‚Рё РІ РЅСѓР¶РЅС‹Р№ РєР°РЅР°Р»\n"
        "3. Р”РѕР±Р°РІРёС‚СЊ РІ Р±РѕС‚Р° Р°Р№РґРё РёР»Рё @username РєР°РЅР°Р»Р°\n"
        "4. РџРѕСЃР»Рµ РІСЃРµС… РЅР°СЃС‚СЂРѕРµРє Р·Р°РїСѓСЃРєР°РµРј"
    )
    await call.message.answer(instruction)


tasks = {}

async def send_loop(uid):
    user = get_user(uid)
    client = TelegramClient(StringSession(user['session']), user['api_id'], user['api_hash'])
    await client.connect()
    while True:
        for chat in user['chats']:
            try:
                await client.send_message(chat, user['text'])
            except Exception as e:
                print(f"РћС€РёР±РєР° РѕС‚РїСЂР°РІРєРё: {e}")
        await asyncio.sleep(user.get('interval', 60))

@router.callback_query(F.data == "start")
async def start_sending(call: types.CallbackQuery):
    uid = call.from_user.id
    if uid in tasks and not tasks[uid].done():
        await call.message.answer("вљ пёЏ РЈР¶Рµ Р·Р°РїСѓС‰РµРЅРѕ.")
        return
    tasks[uid] = asyncio.create_task(send_loop(uid))
    await call.message.answer("рџљЂ Р Р°СЃСЃС‹Р»РєР° РЅР°С‡Р°Р»Р°СЃСЊ.")

@router.callback_query(F.data == "stop")
async def stop_sending(call: types.CallbackQuery):
    uid = call.from_user.id
    if uid in tasks:
        tasks[uid].cancel()
        await call.message.answer("рџ›‘ Р Р°СЃСЃС‹Р»РєР° РѕСЃС‚Р°РЅРѕРІР»РµРЅР°.")
    else:
        await call.message.answer("вќ— Р Р°СЃСЃС‹Р»РєР° РЅРµ Р·Р°РїСѓС‰РµРЅР°.")


async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())