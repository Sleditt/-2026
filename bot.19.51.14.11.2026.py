import asyncio
import sqlite3
import aiohttp
import random
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery, 
    InlineKeyboardMarkup, InlineKeyboardButton, 
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.client.default import DefaultBotProperties

# ==========================================
BOT_TOKEN = "9201844998:AAFAgwN7i5Cmps_J8aOAuydaM8mGr2iqgsw"
API_BASE_URL = "http://127.0.0.1:8080"
# ==========================================

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher()

# --- 1. FSM СОСТОЯНИЯ ---
class AuthState(StatesGroup):
    waiting_for_email = State()
    waiting_for_password = State()

class RegState(StatesGroup):
    waiting_for_name = State()
    waiting_for_surname = State()
    waiting_for_email = State()
    waiting_for_password = State()

# --- 2. БАЗА ДАННЫХ БОТА (Локальный кэш) ---
def init_db():
    conn = sqlite3.connect('bot_local.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            name TEXT, email TEXT, access_token TEXT,
            score INTEGER DEFAULT 0, tasks_done INTEGER DEFAULT 0
        )
    ''')
    
    new_columns = [
        ("last_learned_id", "INTEGER DEFAULT 0"),
        ("learned_ids", "TEXT DEFAULT ''"),
        ("mastered_ids", "TEXT DEFAULT ''"),
        ("mistakes_ids", "TEXT DEFAULT ''")
    ]
    for col, col_type in new_columns:
        try: c.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError: pass
            
    conn.commit()
    conn.close()

def save_auth_data(telegram_id, name, email, token):
    conn = sqlite3.connect('bot_local.db')
    c = conn.cursor()
    c.execute('SELECT telegram_id FROM users WHERE telegram_id = ?', (telegram_id,))
    if c.fetchone():
        c.execute('UPDATE users SET name = ?, email = ?, access_token = ? WHERE telegram_id = ?', 
                  (name, email, token, telegram_id))
    else:
        c.execute('INSERT INTO users (telegram_id, name, email, access_token, score, tasks_done, last_learned_id, learned_ids, mastered_ids, mistakes_ids) VALUES (?, ?, ?, ?, 0, 0, 0, "", "", "")', 
                  (telegram_id, name, email, token))
    conn.commit()
    conn.close()

def get_user_data(telegram_id):
    conn = sqlite3.connect('bot_local.db')
    c = conn.cursor()
    c.execute('SELECT access_token, name, email, score, last_learned_id, learned_ids, mastered_ids, mistakes_ids FROM users WHERE telegram_id = ?', (telegram_id,))
    res = c.fetchone()
    conn.close()
    return res

def update_user_field(telegram_id, field, value):
    conn = sqlite3.connect('bot_local.db')
    c = conn.cursor()
    c.execute(f'UPDATE users SET {field} = ? WHERE telegram_id = ?', (value, telegram_id))
    conn.commit()
    conn.close()

def add_score(telegram_id, points):
    conn = sqlite3.connect('bot_local.db')
    c = conn.cursor()
    c.execute('UPDATE users SET score = score + ? WHERE telegram_id = ?', (points, telegram_id))
    conn.commit()
    conn.close()

# --- 3. ВЗАИМОДЕЙСТВИЕ И СИНХРОНИЗАЦИЯ С GO-СЕРВЕРОМ ---
async def api_register(name, surname, email, password):
    async with aiohttp.ClientSession() as session:
        try:
            payload = {"name": name, "surname": surname, "email": email, "password": password}
            async with session.post(f"{API_BASE_URL}/api/register", json=payload, timeout=2) as resp:
                if resp.status in (200, 201): return await resp.json()
        except: pass
    return None

async def api_login(email, password):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(f"{API_BASE_URL}/api/login", json={"email": email, "password": password}, timeout=2) as resp:
                if resp.status == 200: return await resp.json()
        except: pass
    return None

async def api_get_task_by_id(task_id):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{API_BASE_URL}/api/task/{task_id}", timeout=2) as resp:
                if resp.status == 200: return await resp.json()
        except: pass
    return None

async def push_sync_to_go(telegram_id):
    u = get_user_data(telegram_id)
    if u and u[2]:
        payload = {
            "email": u[2], "score": u[3], 
            "learned_ids": u[5], "mastered_ids": u[6] if u[6] else "", "mistakes_ids": u[7] if u[7] else ""
        }
        async with aiohttp.ClientSession() as s:
            try: await s.post(f"{API_BASE_URL}/api/sync", json=payload)
            except: pass

async def pull_sync_from_go(telegram_id):
    u = get_user_data(telegram_id)
    if u and u[2]:
        async with aiohttp.ClientSession() as s:
            try:
                async with s.get(f"{API_BASE_URL}/api/sync?email={u[2]}") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        update_user_field(telegram_id, "score", data.get("score", 0))
                        update_user_field(telegram_id, "learned_ids", data.get("learned_ids", ""))
                        update_user_field(telegram_id, "mastered_ids", data.get("mastered_ids", ""))
                        update_user_field(telegram_id, "mistakes_ids", data.get("mistakes_ids", ""))
            except: pass

# --- 4. КЛАВИАТУРЫ ---
def get_auth_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Войти (Уже есть аккаунт)", callback_data="auth_login")],
        [InlineKeyboardButton(text="📝 Регистрация (Новый аккаунт)", callback_data="auth_register")]
    ])

def get_main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📖 Изучить новые слова"), KeyboardButton(text="📚 Практика")],
            [KeyboardButton(text="🗂 Мой словарь"), KeyboardButton(text="👤 Мой профиль")],
            [KeyboardButton(text="🏆 Рейтинг")]
        ], resize_keyboard=True
    )

def get_dict_kb(page: int, total_pages: int):
    buttons = []
    if page > 0: buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"dict_page_{page-1}"))
    buttons.append(InlineKeyboardButton(text=f"📄 {page+1}/{total_pages}", callback_data="dict_noop"))
    if page < total_pages - 1: buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"dict_page_{page+1}"))
    return InlineKeyboardMarkup(inline_keyboard=[buttons])

# --- 5. АВТОРИЗАЦИЯ И РЕГИСТРАЦИЯ ---
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_data = get_user_data(message.from_user.id)
    if user_data and user_data[0]:
        await pull_sync_from_go(message.from_user.id)
        await message.answer("С возвращением! Выберите действие в меню 👇", reply_markup=get_main_menu())
        return

    text = ("💎 <b>BASHWORD | Образовательная платформа</b>\n〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️\n\n"
            "Добро пожаловать! Войдите в единый аккаунт или создайте новый (он подойдет и для веб-сайта).")
    await message.answer(text, reply_markup=get_auth_menu())

@dp.callback_query(F.data == "auth_register")
async def reg_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📝 <b>Регистрация (1/4)</b>\n\nВведите ваше <b>Имя</b>:")
    await state.set_state(RegState.waiting_for_name)

@dp.message(RegState.waiting_for_name)
async def reg_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("📝 <b>Регистрация (2/4)</b>\n\nВведите вашу <b>Фамилию</b>:")
    await state.set_state(RegState.waiting_for_surname)

@dp.message(RegState.waiting_for_surname)
async def reg_surname(message: Message, state: FSMContext):
    await state.update_data(surname=message.text)
    await message.answer("📝 <b>Регистрация (3/4)</b>\n\nВведите ваш <b>Email</b> (он будет логином на сайте):")
    await state.set_state(RegState.waiting_for_email)

@dp.message(RegState.waiting_for_email)
async def reg_email(message: Message, state: FSMContext):
    if "@" not in message.text:
        await message.answer("⚠️ Ошибка: Email должен содержать @")
        return
    await state.update_data(email=message.text)
    await message.answer("📝 <b>Регистрация (4/4)</b>\n\nПридумайте <b>Пароль</b>:")
    await state.set_state(RegState.waiting_for_password)

@dp.message(RegState.waiting_for_password)
async def reg_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    msg = await message.answer("⏳ Создаем единый аккаунт...")
    resp = await api_register(data['name'], data['surname'], data['email'], message.text)
    
    if resp and ("access_token" in resp or "email" in resp):
        save_auth_data(message.from_user.id, data['name'], data['email'], resp.get("access_token", "demo_token"))
        await msg.edit_text("✅ <b>Аккаунт успешно создан!</b>")
        await message.answer("Главное меню разблокировано 👇", reply_markup=get_main_menu())
    else:
        await msg.edit_text("❌ Ошибка регистрации (возможно, Email уже занят).", reply_markup=get_auth_menu())
    await state.clear()

@dp.callback_query(F.data == "auth_login")
async def login_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🔑 <b>Авторизация</b>\n\nВведите ваш <b>Email</b>:")
    await state.set_state(AuthState.waiting_for_email)

@dp.message(AuthState.waiting_for_email)
async def login_email(message: Message, state: FSMContext):
    await state.update_data(email=message.text)
    await message.answer("🔑 Введите ваш <b>Пароль</b>:")
    await state.set_state(AuthState.waiting_for_password)

@dp.message(AuthState.waiting_for_password)
async def login_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    msg = await message.answer("⏳ Проверка данных...")
    resp = await api_login(data['email'], message.text)
    
    if resp and ("access_token" in resp or "email" in resp):
        save_auth_data(message.from_user.id, message.from_user.first_name, data['email'], resp.get("access_token", "demo_token"))
        await pull_sync_from_go(message.from_user.id)
        await msg.edit_text("✅ <b>Успешный вход!</b>")
        await message.answer("Главное меню разблокировано 👇", reply_markup=get_main_menu())
    else:
        await msg.edit_text("❌ Неверный Email или пароль.", reply_markup=get_auth_menu())
    await state.clear()

# --- 6. МОДУЛЬ: ИЗУЧЕНИЕ СЛОВ ---
@dp.message(F.text == "📖 Изучить новые слова")
async def learn_new_word(message: Message):
    await pull_sync_from_go(message.from_user.id)
    u_data = get_user_data(message.from_user.id)
    if not u_data: return await message.answer("Сначала войдите в систему /start")
    
    learned_ids = u_data[5]
    l_list = learned_ids.split(",") if learned_ids else []
    
    # Берем строго следующее слово по порядку
    next_id = len(l_list) + 1 
    
    task_data = await api_get_task_by_id(next_id)
    if not task_data:
        return await message.answer("🎉 Вы выучили все слова базы!")

    if str(next_id) not in l_list:
        new_learned = f"{learned_ids},{next_id}" if learned_ids else str(next_id)
        update_user_field(message.from_user.id, 'last_learned_id', next_id)
        update_user_field(message.from_user.id, 'learned_ids', new_learned)
    
    text = (
        "🌟 <b>НОВОЕ СЛОВО</b>\n〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️\n\n"
        f"<blockquote>🗣 <b>{task_data.get('text_ba', '')}</b>\n"
        f"🇷🇺 <i>{task_data.get('translation', '')}</i></blockquote>\n\n"
        "💡 <i>Нажмите кнопку снова, чтобы изучить следующее, или перейдите в Практику.</i>"
    )
    await message.answer(text, reply_markup=get_main_menu())
    await push_sync_to_go(message.from_user.id)

# --- 7. МОДУЛЬ: ПРАКТИКА И КВИЗ ---
@dp.message(F.text == "📚 Практика")
@dp.callback_query(F.data == "next_practice")
async def practice_words(event, state: FSMContext):
    user_id = event.from_user.id
    await pull_sync_from_go(user_id)
    
    is_callback = isinstance(event, CallbackQuery)
    u_data = get_user_data(user_id)
    
    if not u_data or not u_data[5]:
        msg = "⚠️ <b>Словарь пуст!</b> Сначала изучите новые слова."
        if is_callback: await event.message.answer(msg); await event.answer()
        else: await event.answer(msg)
        return
        
    l_list = u_data[5].split(",")
    m_list = u_data[7].split(",") if u_data[7] else []
    
    word_id = random.choice(m_list) if (m_list and random.random() < 0.7) else random.choice(l_list)
    task_data = await api_get_task_by_id(word_id)
    if not task_data: return
    
    correct_ru = task_data.get("translation", "")
    ba_text = task_data.get("text_ba", "")
    
    options = [correct_ru]
    attempts = 0
    while len(options) < 4 and attempts < 15:
        rid = random.randint(1, 1300)
        if str(rid) == str(word_id): continue
        dist = await api_get_task_by_id(rid)
        if dist and dist["translation"] not in options: options.append(dist["translation"])
        attempts += 1
        
    random.shuffle(options)
    await state.update_data(correct_translation=correct_ru, current_word_id=word_id, ba_text=ba_text)
    
    buttons = [[InlineKeyboardButton(text=opt, callback_data="quiz_correct" if opt == correct_ru else "quiz_wrong")] for opt in options]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    text = f"🎯 <b>ПРАКТИКА</b>\n〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️\n\nВыберите перевод:\n<blockquote>🗣 <b>«{ba_text}»</b></blockquote>"
    
    if is_callback:
        await event.message.edit_text(text, reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("quiz_"))
async def process_quiz(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    correct_ru, word_id, ba_text = data.get("correct_translation", ""), str(data.get("current_word_id")), data.get("ba_text", "")
    if not word_id: return await callback.answer("Задание устарело!", show_alert=True)

    u_data = get_user_data(callback.from_user.id)
    mastered, mistakes = u_data[6] if u_data[6] else "", u_data[7] if u_data[7] else ""
    m_list, err_list = mastered.split(",") if mastered else [], mistakes.split(",") if mistakes else []
    
    next_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➡️ Следующее слово", callback_data="next_practice")]])

    if callback.data == "quiz_correct":
        if word_id in err_list:
            err_list.remove(word_id)
            update_user_field(callback.from_user.id, "mistakes_ids", ",".join(err_list))
            
        if word_id not in m_list:
            new_mastered = f"{mastered},{word_id}" if mastered else word_id
            update_user_field(callback.from_user.id, "mastered_ids", new_mastered)
            add_score(callback.from_user.id, 10)
            txt = f"✅ <b>Дөрөҫ! (Верно!)</b>\n\n<blockquote>🗣 <i>{ba_text}</i>\n🇷🇺 <b>{correct_ru}</b></blockquote>\n\n➕ <b>+10 XP</b> (Слово закреплено!)"
        else:
            txt = f"✅ <b>Дөрөҫ!</b>\n\n<blockquote>🗣 <i>{ba_text}</i>\n🇷🇺 <b>{correct_ru}</b></blockquote>\n\n<i>Отличная память!</i>"
    else:
        if word_id not in err_list:
            new_err = f"{mistakes},{word_id}" if mistakes else word_id
            update_user_field(callback.from_user.id, "mistakes_ids", new_err)
        txt = f"❌ <b>Ошибка!</b>\n\n<blockquote>🗣 <i>{ba_text}</i>\nПравильно: <b>{correct_ru}</b></blockquote>\n\n<i>Добавлено в список повторения.</i>"
        
    await callback.message.edit_text(txt, reply_markup=next_kb)
    await push_sync_to_go(callback.from_user.id)
    await callback.answer()

# --- 8. СЛОВАРЬ, ПРОФИЛЬ, РЕЙТИНГ ---
@dp.message(F.text == "🗂 Мой словарь")
async def menu_dictionary(message: Message):
    await pull_sync_from_go(message.from_user.id)
    u_data = get_user_data(message.from_user.id)
    if not u_data or not u_data[5]: return await message.answer("🗂 Ваш словарь пуст!")
    
    l_list = u_data[5].split(","); l_list.reverse()
    m_list = u_data[6].split(",") if u_data[6] else []
    
    page_ids = l_list[0:10]
    tasks = [api_get_task_by_id(w_id) for w_id in page_ids]
    results = await asyncio.gather(*tasks)

    lines = []
    for idx, res in enumerate(results):
        if res:
            w_id = page_ids[idx]
            icon = "✅" if str(w_id) in m_list else "🔹"
            lines.append(f"{len(l_list) - idx}. {icon} <b>{res.get('text_ba', '')}</b> — <i>{res.get('translation', '')}</i>")

    total_pages = (len(l_list) + 9) // 10
    text = f"🗂 <b>ВАШ СЛОВАРЬ</b> (Выучено: {len(l_list)})\n<i>✅ — надежно закреплено</i>\n\n" + "\n".join(lines)
    await message.answer(text, reply_markup=get_dict_kb(0, total_pages) if total_pages > 1 else None)

@dp.message(F.text == "👤 Мой профиль")
async def menu_profile(message: Message):
    await pull_sync_from_go(message.from_user.id)
    update_user_field(message.from_user.id, "name", message.from_user.first_name)
    
    u_data = get_user_data(message.from_user.id)
    if not u_data: return
    score = u_data[3]
    words_count = len(u_data[5].split(",")) if u_data[5] else 0
    mastered = len(u_data[6].split(",")) if u_data[6] else 0
    
    text = (
        "👤 <b>ВАШ ПРОФИЛЬ</b>\n〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️\n"
        f"Имя: <b>{u_data[1]}</b>\nEmail: <i>{u_data[2]}</i>\n\n"
        f"<blockquote>🏆 Опыт: <b>{score} XP</b>\n"
        f"🧠 Выучено фраз: <b>{words_count}</b>\n"
        f"✅ Закреплено в практике: <b>{mastered}</b></blockquote>"
    )
    await message.answer(text)

@dp.message(F.text == "🏆 Рейтинг")
async def menu_rating(message: Message):
    # Рейтинг запрашиваем прямо из Go-сервера, чтобы совпадать с сайтом
    async with aiohttp.ClientSession() as s:
        try:
            async with s.get(f"{API_BASE_URL}/api/rating") as resp:
                if resp.status == 200:
                    top = await resp.json()
                    if not top: return await message.answer("🏆 Таблица лидеров пока пуста.")
                    
                    lines = []
                    for i, u in enumerate(top):
                        prefix = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."
                        name = u.get("name", "Студент")
                        score = u.get("score", 0)
                        if name == message.from_user.first_name:
                            lines.append(f"{prefix} 👉 <b>{name}</b> — {score} XP")
                        else:
                            lines.append(f"{prefix} <b>{name}</b> — {score} XP")
                            
                    await message.answer("🏆 <b>ГЛОБАЛЬНЫЙ ТОП-10</b>\n\n" + "\n".join(lines))
                    return
        except: pass
    await message.answer("❌ Ошибка связи с сервером.")

# --- 9. ЗАГЛУШКА ---
@dp.message()
async def fallback(message: Message):
    await message.answer("Воспользуйтесь меню ниже 👇", reply_markup=get_main_menu())

async def main():
    init_db()
    print("Бот 100% собран и синхронизирован с Go-сервером!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
 
