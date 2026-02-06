import asyncio
import logging
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile

from config import BOT_TOKEN, ADMIN_IDS
from models import (
    init_db, add_user, add_book, get_all_books, 
    get_book, create_booking, get_user_books, get_user_bookings,
    delete_book, update_book_status, update_book_info,
    search_books, get_unique_genres, get_unique_age_ratings,
    confirm_transfer, return_book, get_books_on_shelf,
    add_to_waitlist, get_waitlist, remove_from_waitlist,
    get_incoming_requests, reject_booking, get_book_history,
    request_book_return, cancel_return_request, add_review, get_book_reviews,
    update_user_profile, update_user_status, set_admin_status, get_user,
    get_all_users, log_admin_action, delete_review, get_stats, get_admin_logs
)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN); dp = Dispatcher()

# Каталоги
GENRES = ["Роман", "Детектив", "Фэнтези", "Научная фантастика", "Приключения", "Научпоп", "Ужасы", "Биография", "Классика", "Детское", "Поэзия"]
AGE_RATINGS = ["0+", "6+", "12+", "16+", "18+"]

class AddBook(StatesGroup):
    waiting_for_method = State()
    waiting_for_isbn = State()
    waiting_for_title = State(); waiting_for_author = State(); waiting_for_genre = State()
    waiting_for_tags = State(); waiting_for_age_rating = State(); waiting_for_description = State(); waiting_for_photo = State()

class Registration(StatesGroup):
    waiting_for_name = State()
    waiting_for_district = State()

async def fetch_book_by_isbn(isbn):
    isbn = "".join(filter(str.isdigit, isbn))
    if not isbn: return None
    
    # Сначала пробуем Google Books
    async with aiohttp.ClientSession() as session:
        try:
            url_gb = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
            async with session.get(url_gb, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("totalItems", 0) > 0:
                        item = data["items"][0]["volumeInfo"]
                        return {
                            "title": item.get("title", ""),
                            "author": ", ".join(item.get("authors", [])),
                            "description": item.get("description", ""),
                            "photo_url": item.get("imageLinks", {}).get("thumbnail")
                        }
        except: pass

        # Если Google не сработал (квота или нет книги), пробуем Open Library
        try:
            url_ol = f"https://openlibrary.org/search.json?isbn={isbn}"
            async with session.get(url_ol, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("numFound", 0) > 0:
                        book = data["docs"][0]
                        title = book.get("title", "")
                        author = ", ".join(book.get("author_name", []))
                        # У Open Library нет прямого описания в поиске, но есть ID обложки
                        cover_id = book.get("cover_i")
                        photo_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else None
                        return {
                            "title": title,
                            "author": author,
                            "description": "", # В поиске OL нет описания
                            "photo_url": photo_url
                        }
        except: pass
        
    return None

class EditBook(StatesGroup):
    waiting_for_title = State(); waiting_for_author = State(); waiting_for_genre = State()
    waiting_for_tags = State(); waiting_for_age_rating = State(); waiting_for_description = State()

class Search(StatesGroup):
    waiting_for_text = State(); waiting_for_tag = State(); waiting_for_status = State()

class AddReview(StatesGroup):
    waiting_for_text = State()

def main_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📚 Поиск книг"), KeyboardButton(text="➕ Добавить книгу")],
        [KeyboardButton(text="👤 Мой профиль"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="❓ Помощь"), KeyboardButton(text="🏠 Домой")]
    ], resize_keyboard=True)

def get_genres_keyboard():
    buttons = [[KeyboardButton(text=g)] for g in GENRES]
    buttons.append([KeyboardButton(text="Другое (ввести вручную)")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=True)

def get_age_ratings_keyboard():
    buttons = [[KeyboardButton(text=r)] for r in AGE_RATINGS]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=True)

@dp.message(F.text == "🏠 Домой")
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user = await get_user(message.from_user.id)
    
    # Авто-назначение админов из конфига
    if message.from_user.id in ADMIN_IDS:
        if not user:
            await add_user(message.from_user.id, message.from_user.username, message.from_user.full_name, status='approved')
            await set_admin_status(message.from_user.id, True)
            user = await get_user(message.from_user.id)
        elif not user['is_admin']:
            await set_admin_status(message.from_user.id, True)
            await update_user_status(message.from_user.id, 'approved')
            user = await get_user(message.from_user.id)

    if not user:
        await add_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
        await message.answer("👋 Привет! Чтобы начать пользоваться ботом, нужно заполнить небольшую анкету для вступления в клуб.\n\nКак вас зовут? (Имя и Фамилия):")
        await state.set_state(Registration.waiting_for_name)
        return

    if user['status'] == 'pending':
        if not user['real_name']:
            await message.answer("Пожалуйста, заполните анкету для вступления.\n\nКак вас зовут?")
            await state.set_state(Registration.waiting_for_name)
        else:
            await message.answer("⏳ Ваша заявка находится на рассмотрении у администраторов. Мы сообщим вам, когда доступ будет открыт!")
        return
    
    if user['status'] == 'blocked':
        await message.answer("⛔️ Ваш доступ к боту заблокирован администратором.")
        return

    await message.answer(f"Привет, {user['real_name'] or message.from_user.first_name}! 👋\nБот готов к работе.", reply_markup=main_menu())

# --- Регистрация ---
@dp.message(Registration.waiting_for_name)
async def reg_name(message: types.Message, state: FSMContext):
    await state.update_data(real_name=message.text.strip())
    await message.answer("Ваш примерный район проживания (например, Centro, Ciudad Naranco):")
    await state.set_state(Registration.waiting_for_district)

@dp.message(Registration.waiting_for_district)
async def reg_district(message: types.Message, state: FSMContext):
    data = await state.get_data()
    real_name = data['real_name']
    district = message.text.strip()
    
    await update_user_profile(message.from_user.id, real_name, district, "")
    await message.answer("✨ Спасибо! Ваша заявка отправлена администраторам. Ожидайте подтверждения.")
    
    # Уведомляем админов
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Принять", callback_data=f"adm_appr_{message.from_user.id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"adm_rejt_{message.from_user.id}")
    ]])
    caption = f"🆕 <b>Новая заявка!</b>\n\n👤 Юзер: @{message.from_user.username}\n📝 Имя: {real_name}\n📍 Район: {district}"
    for admin_id in ADMIN_IDS:
        try: await bot.send_message(admin_id, caption, parse_mode="HTML", reply_markup=kb)
        except: pass
    await state.clear()

async def is_approved(user_id):
    user = await get_user(user_id)
    return user and user['status'] == 'approved'

# --- Добавление ---
@dp.message(F.text.in_({"➕ Добавить книгу", "➕ Добавить свою книгу"}))
async def start_add_book(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔢 По ISBN (быстро)"), KeyboardButton(text="✍️ Вручную")]
    ], resize_keyboard=True, one_time_keyboard=True)
    await message.answer("Как добавить книгу?", reply_markup=kb)
    await state.set_state(AddBook.waiting_for_method)

@dp.message(AddBook.waiting_for_method)
async def p_method(message: types.Message, state: FSMContext):
    if message.text == "🔢 По ISBN (быстро)":
        await message.answer("Введите или отсканируйте ISBN-код (10 или 13 цифр):", reply_markup=main_menu())
        await state.set_state(AddBook.waiting_for_isbn)
    else:
        await message.answer("Назовите книгу:", reply_markup=main_menu())
        await state.set_state(AddBook.waiting_for_title)

@dp.message(AddBook.waiting_for_isbn)
async def p_isbn(message: types.Message, state: FSMContext):
    isbn = message.text.strip()
    await message.answer("🔍 Ищу книгу в базе Google Books...")
    book = await fetch_book_by_isbn(isbn)
    
    if not book:
        await message.answer("❌ Книга не найдена. Давайте введем вручную.\nНазовите книгу:")
        await state.set_state(AddBook.waiting_for_title)
        return

    await state.update_data(**book)
    text = f"✨ <b>Нашел книгу!</b>\n\n📖 {book['title']}\n👤 {book['author']}\n\nОна?\n(0 - продолжить, либо введите другое название)"
    
    # Пытаемся получить фото
    if book['photo_url']:
        async with aiohttp.ClientSession() as session:
            async with session.get(book['photo_url']) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    photo = BufferedInputFile(content, filename="cover.jpg")
                    try:
                        msg = await message.answer_photo(photo, caption=text, parse_mode="HTML")
                        await state.update_data(photo_id=msg.photo[-1].file_id)
                    except:
                        await message.answer(text, parse_mode="HTML")
                else: await message.answer(text, parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")
        
    await state.set_state(AddBook.waiting_for_title)

@dp.message(AddBook.waiting_for_title)
async def p_title(message: types.Message, state: FSMContext):
    data = await state.get_data(); val = message.text.strip()
    if val != "0": await state.update_data(title=val); data = await state.get_data()
    
    hint = f" ({data.get('author')})" if data.get('author') else ""
    await message.answer(f"Автор{hint}?\n(0 - оставить/пропустить)")
    await state.set_state(AddBook.waiting_for_author)

@dp.message(AddBook.waiting_for_author)
async def p_author(message: types.Message, state: FSMContext):
    data = await state.get_data(); val = message.text.strip()
    if val != "0": await state.update_data(author=val); data = await state.get_data()
    
    await message.answer("Выберите жанр:", reply_markup=get_genres_keyboard())
    await state.set_state(AddBook.waiting_for_genre)

@dp.message(AddBook.waiting_for_genre)
async def p_genre(message: types.Message, state: FSMContext):
    if message.text == "Другое (ввести вручную)": await message.answer("Введите жанр вручную:"); return
    await state.update_data(genre=message.text); await message.answer("Теги через запятую:", reply_markup=main_menu()); await state.set_state(AddBook.waiting_for_tags)

@dp.message(AddBook.waiting_for_tags)
async def p_tags(message: types.Message, state: FSMContext):
    tags = ", ".join([t.strip().lower() for t in message.text.split(",")])
    await state.update_data(tags=tags); await message.answer("Выберите рейтинг:", reply_markup=get_age_ratings_keyboard()); await state.set_state(AddBook.waiting_for_age_rating)

@dp.message(AddBook.waiting_for_age_rating)
async def p_age(message: types.Message, state: FSMContext):
    await state.update_data(age_rating=message.text); data = await state.get_data()
    desc_val = data.get('description', '')
    hint = f"\n(0 - оставить из базы: {desc_val[:50]}...)" if desc_val else ""
    await message.answer(f"Описание:{hint}\n(0 - оставить/пропустить)", reply_markup=main_menu())
    await state.set_state(AddBook.waiting_for_description)

@dp.message(AddBook.waiting_for_description)
async def p_desc(message: types.Message, state: FSMContext):
    data = await state.get_data(); val = message.text.strip()
    if val != "0": await state.update_data(description=val); data = await state.get_data()
    
    hint = "\n(0 - оставить обложку из базы)" if data.get('photo_id') else ""
    await message.answer(f"Пришлите фото обложки:{hint}")
    await state.set_state(AddBook.waiting_for_photo)

@dp.message(AddBook.waiting_for_photo)
async def p_photo_text_check(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if message.text == "0" and data.get('photo_id'):
        await add_book(message.from_user.id, data['title'], data['author'], data['genre'], data['tags'], data['age_rating'], data['description'], data['photo_id'])
        await message.answer("🎉 Книга добавлена!", reply_markup=main_menu()); await state.clear()
    elif message.text == "0":
        await message.answer("Фото не найдено в базе. Пожалуйста, пришлите фото обложки.")
    else:
        # If user sends something else, just keep waiting for photo
        pass

@dp.message(AddBook.waiting_for_photo, F.photo)
async def p_photo(message: types.Message, state: FSMContext):
    data = await state.get_data(); pid = message.photo[-1].file_id
    await add_book(message.from_user.id, data['title'], data['author'], data['genre'], data['tags'], data['age_rating'], data['description'], pid)
    await message.answer("🎉 Книга добавлена!", reply_markup=main_menu()); await state.clear()

# --- Поиск и Библиотека ---
async def display_books(message, books, user_id):
    if not books: await message.answer("Ничего не найдено. 🤷‍♂️"); return
    for b in books:
        own = f"@{b['owner_username']}" if b['owner_username'] else b['owner_name']
        t_str = f"🏷 Теги: {b['tags']}\n" if b['tags'] and b['tags'] != "None" else ""
        a_str = f"🔞 Рейтинг: {b['age_rating']}\n" if b['age_rating'] and b['age_rating'] != "None" else ""
        
        status_line = ""
        waitlist = await get_waitlist(b['id'])
        queue_str = f"\n👥 Очередь: {len(waitlist)} чел." if waitlist else ""
        
        if b['current_holder_id']:
            h_name = f"@{b['holder_username']}" if b['holder_username'] else b['holder_name']
            status_line = f"\n📖 <b>Сейчас читает: {h_name}</b>"
            
        cap = f"📖 <b>{b['title']}</b>\n👤 Автор: {b['author']}\n🎭 Жанр: {b['genre']}\n{t_str}{a_str}🏠 Вл.: {own}{status_line}{queue_str}\n\n📝 {b['description']}"
        
        buttons = []
        if b['current_holder_id']:
            if b['current_holder_id'] != user_id and b['owner_id'] != user_id:
                is_in_queue = any(w['user_id'] == user_id for w in waitlist)
                if is_in_queue:
                    buttons.append([InlineKeyboardButton(text="✅ Вы в очереди", callback_data="none")])
                else:
                    buttons.append([InlineKeyboardButton(text="✨ Встать в очередь", callback_data=f"queue_{b['id']}")])
        else:
            if b['owner_id'] != user_id:
                buttons.append([InlineKeyboardButton(text="✨ Хочу прочитать", callback_data=f"book_{b['id']}")])
        
        # Кнопка истории
        buttons.append([InlineKeyboardButton(text="📜 История перемещений", callback_data=f"hist_{b['id']}")])
        
        # Кнопка отзывов
        buttons.append([InlineKeyboardButton(text="💬 Отзывы", callback_data=f"reviews_{b['id']}")])

        if waitlist and (b['owner_id'] == user_id or b['current_holder_id'] == user_id):
            q_names = ", ".join([f"@{w['username']}" if w['username'] else w['full_name'] for w in waitlist])
            cap += f"\n\n👥 <b>Очередь:</b> {q_names}"

        # Админ-кнопки
        user = await get_user(user_id)
        if user and user['is_admin']:
            buttons.append([
                InlineKeyboardButton(text="⚙️ Ред. (Админ)", callback_data=f"edit_{b['id']}"),
                InlineKeyboardButton(text="🗑 Уд. (Админ)", callback_data=f"delete_{b['id']}")
            ])

        kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
        await message.answer_photo(photo=b['photo_id'], caption=cap, parse_mode="HTML", reply_markup=kb)

@dp.message(F.text.in_({"📚 Поиск книг", "📚 Каталог", "🔍 Поиск"}))
async def cmd_library(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Только доступные", callback_data="lib_available"),
         InlineKeyboardButton(text="📖 У читателей", callback_data="lib_held")],
        [InlineKeyboardButton(text="🎭 По жанру", callback_data="lib_genre"),
         InlineKeyboardButton(text="🏷 По тегу", callback_data="lib_tag")],
        [InlineKeyboardButton(text="🔞 По рейтингу", callback_data="lib_age"),
         InlineKeyboardButton(text="🔍 По тексту", callback_data="lib_text")],
        [InlineKeyboardButton(text="📜 Весь список", callback_data="lib_all")]
    ])
    await message.answer("Как будем искать книги?", reply_markup=kb)

@dp.callback_query(F.data.startswith("lib_"))
async def process_library_filter(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split("_")[1]
    if action == "available": await display_books(callback.message, await get_all_books(status_filter='available'), callback.from_user.id)
    elif action == "held": await display_books(callback.message, await get_all_books(status_filter='held'), callback.from_user.id)
    elif action == "all": await display_books(callback.message, await get_all_books(status_filter='all'), callback.from_user.id)
    elif action == "genre":
        gs = await get_unique_genres(); btns = [[InlineKeyboardButton(text=g, callback_data=f"libgenre_{g}")] for g in gs]
        await callback.message.edit_text("Выберите жанр:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))
    elif action == "tag": await callback.message.edit_text("Введите тег:"); await state.set_state(Search.waiting_for_tag)
    elif action == "age": await callback.message.edit_text("Рейтинг:", reply_markup=get_age_ratings_kb_inline())
    elif action == "text": await callback.message.edit_text("Что искать?"); await state.set_state(Search.waiting_for_text)
    await callback.answer()

def get_age_ratings_kb_inline():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=r, callback_data=f"libage_{r}")] for r in AGE_RATINGS])

@dp.callback_query(F.data.startswith("libgenre_"))
async def s_genre_proc_lib(callback: types.CallbackQuery):
    g = callback.data.split("_")[1]; await display_books(callback.message, await search_books(genre=g), callback.from_user.id); await callback.answer()

@dp.callback_query(F.data.startswith("libage_"))
async def s_age_proc_lib(callback: types.CallbackQuery):
    a = callback.data.split("_")[1]; await display_books(callback.message, await search_books(age_rating=a), callback.from_user.id); await callback.answer()

@dp.message(Search.waiting_for_tag)
async def s_tag_proc(message: types.Message, state: FSMContext):
    await display_books(message, await search_books(tag=message.text.strip()), message.from_user.id); await state.clear()

@dp.message(Search.waiting_for_text)
async def s_txt_proc(message: types.Message, state: FSMContext):
    await display_books(message, await search_books(text_query=message.text.strip()), message.from_user.id); await state.clear()

# --- История перемещений ---
@dp.callback_query(F.data.startswith("hist_"))
async def process_view_history(callback: types.CallbackQuery):
    bid = int(callback.data.split("_")[1]); b = await get_book(bid)
    if not b: return
    history = await get_book_history(bid)
    owner_name = f"@{b['owner_username']}" if b['owner_username'] else b['owner_name']
    text = f"📜 <b>История книги «{b['title']}»</b>\n"
    text += f"🏠 Владелец: {owner_name}\n\n"
    if not history: text += "Эта книга пока не покидала полку владельца. 🌱"
    else:
        for idx, m in enumerate(history, 1):
            date = m['created_at'].split()[0]
            from_u = f"@{m['from_username']}" if m['from_username'] else m['from_name']
            to_u = f"@{m['to_username']}" if m['to_username'] else m['to_name']
            text += f"{idx}. 📅 {date}: {from_u} ➔ {to_u} ({'Передача' if m['event_type'] == 'transfer' else 'Возврат'})\n"
    await callback.message.answer(text, parse_mode="HTML"); await callback.answer()

@dp.callback_query(F.data.startswith("recall_"))
async def p_recall(c: types.CallbackQuery):
    bid = int(c.data.split("_")[1]); b = await get_book(bid)
    if not b: return
    await request_book_return(bid, c.from_user.id)
    await c.message.edit_text(f"🏠 Вы отозвали книгу «{b['title']}». Теперь читатель сможет только вернуть её вам.")
    if b['current_holder_id']:
        try: await bot.send_message(b['current_holder_id'], f"📦 Владелец просит вернуть книгу «{b['title']}». Пожалуйста, занесите её хозяину при возможности.")
        except: pass
    await c.answer()

@dp.callback_query(F.data.startswith("cancelrecall_"))
async def p_cancelrecall(c: types.CallbackQuery):
    bid = int(c.data.split("_")[1]); b = await get_book(bid)
    if not b: return
    await cancel_return_request(bid, c.from_user.id)
    await c.message.edit_text(f"✅ Отзыв книги «{b['title']}» отменен.")
    await c.answer()

# --- Очередь ---
@dp.callback_query(F.data.startswith("queue_"))
async def process_queue_join(c: types.CallbackQuery):
    bid = int(c.data.split("_")[1]); b = await get_book(bid)
    if not b: return
    added = await add_to_waitlist(bid, c.from_user.id)
    if added:
        await c.answer("Вы встали в очередь!", show_alert=True)
        name = f"@{c.from_user.username}" if c.from_user.username else c.from_user.full_name
        msg = f"👥 Новый в очереди на «{b['title']}»: {name}"
        try: await bot.send_message(b['owner_id'], msg)
        except: pass
        if b['current_holder_id']:
            try: await bot.send_message(b['current_holder_id'], msg)
            except: pass
    else: await c.answer("Вы уже в очереди.", show_alert=True)

# --- Бронирование ---
@dp.callback_query(F.data.startswith("book_"))
async def p_book(c: types.CallbackQuery):
    bid = int(c.data.split("_")[1]); b = await get_book(bid)
    if not b: return
    if b['owner_id'] == c.from_user.id: await c.answer("Это ваша книга!", show_alert=True); return
    await create_booking(bid, c.from_user.id)
    u = c.from_user; name = f"@{u.username}" if u.username else u.full_name
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Выдать", callback_data=f"give_{bid}_{u.id}")]])
    await bot.send_message(b['owner_id'], f"🔔 <b>{name}</b> хочет взять «{b['title']}».\nПодтвердите выдачу в профиле или здесь:", parse_mode="HTML", reply_markup=kb)
    await c.answer("Заявка отправлена!", show_alert=True)

@dp.callback_query(F.data.startswith("give_"))
async def p_give(c: types.CallbackQuery):
    _, bid, uid = c.data.split("_"); bid = int(bid); uid = int(uid)
    await confirm_transfer(bid, uid); await remove_from_waitlist(bid, uid)
    await c.message.edit_text("✅ Книга передана читателю.")
    try: await bot.send_message(uid, f"🎉 Владелец подтвердил передачу книги! Она теперь на вашей «Полке».")
    except: pass
    await c.answer()

@dp.callback_query(F.data.startswith("handover_"))
async def p_handover(c: types.CallbackQuery):
    _, bid, uid = c.data.split("_"); bid = int(bid); uid = int(uid)
    b = await get_book(bid)
    if not b: return
    owner_id = await confirm_transfer(bid, uid)
    await remove_from_waitlist(bid, uid)
    old_holder_name = f"@{c.from_user.username}" if c.from_user.username else c.from_user.full_name
    await c.message.edit_text(f"🤝 Книга «{b['title']}» передана.")
    try: await bot.send_message(uid, f"🎉 Вам передали книгу «{b['title']}» от {old_holder_name}! Она на вашей «Полке».")
    except: pass
    try: await bot.send_message(owner_id, f"🔄 Книга «{b['title']}» совершила переезд! {old_holder_name} передал её новому читателю.")
    except: pass
    await c.answer("Передача подтверждена!")

@dp.callback_query(F.data.startswith("rej_"))
async def p_rej(c: types.CallbackQuery):
    _, bid, uid = c.data.split("_"); bid = int(bid); uid = int(uid)
    await reject_booking(bid, uid)
    await c.message.edit_text("❌ Запрос отклонен.")
    try: await bot.send_message(uid, "😔 Владелец отклонил ваш запрос на книгу.")
    except: pass
    await c.answer()

@dp.callback_query(F.data.startswith("return_"))
async def p_return(c: types.CallbackQuery):
    bid = int(c.data.split("_")[1]); b = await get_book(bid); u = c.from_user; name = f"@{u.username}" if u.username else u.full_name
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Получил назад", callback_data=f"gotback_{bid}")]])
    await bot.send_message(b['owner_id'], f"📦 <b>{name}</b> вернул «{b['title']}».\nПодтвердите:", parse_mode="HTML", reply_markup=kb)
    await c.answer("Владелец уведомлен!", show_alert=True)

@dp.callback_query(F.data.startswith("gotback_"))
async def p_gotback(c: types.CallbackQuery):
    bid = int(c.data.split("_")[1]); b = await get_book(bid); await return_book(bid)
    await c.message.edit_text("✅ Возврат подтвержден."); await c.answer()
    if b['current_holder_id']:
        try: await bot.send_message(b['current_holder_id'], "📖 Владелец подтвердил возврат. Спасибо!")
        except: pass
    waitlist = await get_waitlist(bid)
    if waitlist:
        next_user = waitlist[0]
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏭ Пропустить ход", callback_data=f"skipqueue_{bid}")]])
        try: await bot.send_message(next_user['user_id'], f"📚 Книга «{b['title']}» освободилась! Вы первый в очереди.", reply_markup=kb)
        except: pass

@dp.callback_query(F.data.startswith("skipqueue_"))
async def p_skipqueue(c: types.CallbackQuery):
    bid = int(c.data.split("_")[1]); b = await get_book(bid); await remove_from_waitlist(bid, c.from_user.id)
    await c.message.edit_text("⏭ Вы пропустили очередь на эту книгу.")
    waitlist = await get_waitlist(bid)
    if waitlist:
        next_user = waitlist[0]
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏭ Пропустить ход", callback_data=f"skipqueue_{bid}")]])
        try: await bot.send_message(next_user['user_id'], f"📚 Книга «{b['title']}» освободилась! Вы первый в очереди.", reply_markup=kb)
        except: pass
    await c.answer()

@dp.callback_query(F.data.startswith("reviews_"))
async def p_reviews(c: types.CallbackQuery):
    bid = int(c.data.split("_")[1]); b = await get_book(bid); reviews = await get_book_reviews(bid)
    text = f"💬 <b>Отзывы о книге «{b['title']}»</b>\n\n"
    if not reviews: text += "Пока никто не оставил отзыв. Будьте первым! 😊"
    else:
        for r in reviews:
            name = f"@{r['username']}" if r['username'] else r['full_name']
            date = r['created_at'].split()[0]
            text += f"👤 {name} ({date}):\n«{r['text']}»\n\n"
    kb_btns = [[InlineKeyboardButton(text="📝 Написать отзыв", callback_data=f"addreview_{bid}")]]
    
    # Админ-удаление отзывов
    user = await get_user(c.from_user.id)
    if user and user['is_admin'] and reviews:
        for r in reviews:
            name = f"@{r['username']}" if r['username'] else r['full_name']
            kb_btns.append([InlineKeyboardButton(text=f"🗑 Уд. отзыв {name}", callback_data=f"adm_delrev_{r['id']}_{bid}")])

    kb = InlineKeyboardMarkup(inline_keyboard=kb_btns)
    await c.message.answer(text, parse_mode="HTML", reply_markup=kb); await c.answer()

@dp.callback_query(F.data.startswith("adm_delrev_"))
async def adm_delreview(c: types.CallbackQuery):
    _, _, rid, bid = c.data.split("_"); rid = int(rid); bid = int(bid)
    await delete_review(rid)
    await log_admin_action(c.from_user.id, "delete_review", f"Review ID: {rid}")
    await c.answer("Отзыв удален"); await p_reviews(c)

@dp.callback_query(F.data.startswith("addreview_"))
async def p_addreview_start(c: types.CallbackQuery, state: FSMContext):
    bid = int(c.data.split("_")[1]); await state.update_data(review_bid=bid)
    await c.message.answer("Напишите ваше впечатление о книге:"); await state.set_state(AddReview.waiting_for_text); await c.answer()

@dp.message(AddReview.waiting_for_text)
async def p_addreview_finish(message: types.Message, state: FSMContext):
    data = await state.get_data(); bid = data['review_bid']
    await add_review(bid, message.from_user.id, message.text.strip())
    await message.answer("✅ Спасибо за отзыв! Он теперь виден всем в карточке книги.", reply_markup=main_menu()); await state.clear()

# --- Профиль ---
@dp.message(F.text == "👤 Мой профиль")
async def cmd_profile(message: types.Message):
    await message.answer("👤 <b>Ваш профиль</b>", parse_mode="HTML")
    # 1. Мои книги
    my_books = await get_user_books(message.from_user.id)
    await message.answer("📚 <b>Мои книги (в базе):</b>", parse_mode="HTML")
    if my_books:
        for b in my_books:
            waitlist = await get_waitlist(b['id'])
            q_info = f"\n👥 Очередь: {len(waitlist)} чел." if waitlist else ""
            st = "🤝 У читателя" if b['current_holder_id'] else ("✅ Доступна" if b['status']=='available' else "🔒 Скрыта")
            row1 = [
                InlineKeyboardButton(text="⏸" if b['status']=='available' else "▶️", callback_data=f"toggle_{b['id']}"),
                InlineKeyboardButton(text="✏️", callback_data=f"edit_{b['id']}"),
                InlineKeyboardButton(text="🗑", callback_data=f"delete_{b['id']}"),
                InlineKeyboardButton(text="📜", callback_data=f"hist_{b['id']}"),
                InlineKeyboardButton(text="💬", callback_data=f"reviews_{b['id']}")
            ]
            row2 = []
            if b['current_holder_id']:
                if b['return_requested']:
                    row2.append(InlineKeyboardButton(text="🏠 Отмена отзыва", callback_data=f"cancelrecall_{b['id']}"))
                    st += " (Ожидается возврат)"
                else:
                    row2.append(InlineKeyboardButton(text="🏠 Отозвать книгу", callback_data=f"recall_{b['id']}"))
            kb = InlineKeyboardMarkup(inline_keyboard=[row1, row2] if row2 else [row1])
            await message.answer(f"📖 <b>{b['title']}</b>\nСтатус: {st}{q_info}", parse_mode="HTML", reply_markup=kb)
    else: await message.answer("Пока нет своих книг.")

    # 2. Моя полка
    my_shelf = await get_books_on_shelf(message.from_user.id)
    await message.answer("✨ <b>Моя полка (читаю):</b>", parse_mode="HTML")
    if my_shelf:
        for b in my_shelf:
            waitlist = await get_waitlist(b['id'])
            q_info = f"\n👥 Ждут: {len(waitlist)} чел." if waitlist else ""
            info_text = f"📖 <b>{b['title']}</b>{q_info}"
            row1 = [
                InlineKeyboardButton(text="📦 Вернуть хозяину", callback_data=f"return_{b['id']}"),
                InlineKeyboardButton(text="📜 История", callback_data=f"hist_{b['id']}"),
                InlineKeyboardButton(text="💬 Отзывы", callback_data=f"reviews_{b['id']}")
            ]
            row2 = []
            if b['return_requested']: info_text += "\n⚠️ <b>Владелец просит вернуть книгу!</b>"
            elif waitlist:
                next_u = waitlist[0]; target_name = f"@{next_u['username']}" if next_u['username'] else next_u['full_name']
                row2.append(InlineKeyboardButton(text=f"🤝 Передать {target_name}", callback_data=f"handover_{b['id']}_{next_u['user_id']}"))
            kb = InlineKeyboardMarkup(inline_keyboard=[row1, row2] if row2 else [row1])
            await message.answer(info_text, parse_mode="HTML", reply_markup=kb)
    else: await message.answer("На полке пусто.")

    # 3. Запросы
    await message.answer("📥 <b>Запросы от других:</b>", parse_mode="HTML")
    reqs = await get_incoming_requests(message.from_user.id)
    if reqs:
        for r in reqs:
            r_name = f"@{r['renter_username']}" if r['renter_username'] else r['renter_name']
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Выдать", callback_data=f"give_{r['book_id']}_{r['renter_id']}"), InlineKeyboardButton(text="❌ Откл.", callback_data=f"rej_{r['book_id']}_{r['renter_id']}") ]])
            await message.answer(f"👤 {r_name} хочет взять:\n📖 <b>{r['title']}</b>", parse_mode="HTML", reply_markup=kb)
    else: await message.answer("Новых запросов нет.")

@dp.callback_query(F.data.startswith("toggle_"))
async def p_toggle_btn(c: types.CallbackQuery):
    bid = int(c.data.split("_")[1]); b = await get_book(bid)
    if not b: return
    ns = 'unavailable' if b['status']=='available' else 'available'
    await update_book_status(bid, c.from_user.id, ns); await c.answer("Статус изменен!"); await cmd_profile(c.message)

# --- Редактирование ---
@dp.callback_query(F.data.startswith("edit_"))
async def s_edit(c: types.CallbackQuery, state: FSMContext):
    bid = int(c.data.split("_")[1]); b = await get_book(bid)
    await state.update_data(edit_book_id=bid, ot=b['title'], oa=b['author'], og=b['genre'], otg=b['tags'], orat=b['age_rating'], od=b['description'])
    await c.message.answer(f"🛠 Ред.: {b['title']}\n(0 - нет)\nНазвание:"); await state.set_state(EditBook.waiting_for_title); await c.answer()

@dp.message(EditBook.waiting_for_title)
async def e_title(message: types.Message, state: FSMContext):
    data = await state.get_data(); v = message.text.strip(); await state.update_data(nt=data['ot'] if v=="0" else v); await message.answer("Автор:"); await state.set_state(EditBook.waiting_for_author)

@dp.message(EditBook.waiting_for_author)
async def e_author(message: types.Message, state: FSMContext):
    data = await state.get_data(); v = message.text.strip(); await state.update_data(na=data['oa'] if v=="0" else v); await message.answer("Жанр:", reply_markup=get_genres_keyboard()); await state.set_state(EditBook.waiting_for_genre)

@dp.message(EditBook.waiting_for_genre)
async def e_genre(message: types.Message, state: FSMContext):
    data = await state.get_data(); v = message.text.strip(); await state.update_data(ng=data['og'] if v=="0" else v); await message.answer("Теги:"); await state.set_state(EditBook.waiting_for_tags)

@dp.message(EditBook.waiting_for_tags)
async def e_tags(message: types.Message, state: FSMContext):
    data = await state.get_data(); v = message.text.strip(); t = data['otg'] if v=="0" else ", ".join([x.strip().lower() for x in v.split(",")]); await state.update_data(ntg=t); await message.answer("Рейтинг:", reply_markup=get_age_ratings_keyboard()); await state.set_state(EditBook.waiting_for_age_rating)

@dp.message(EditBook.waiting_for_age_rating)
async def e_age(message: types.Message, state: FSMContext):
    data = await state.get_data(); v = message.text.strip(); await state.update_data(nr=data['orat'] if v=="0" else v); await message.answer("Описание:"); await state.set_state(EditBook.waiting_for_description)

@dp.message(EditBook.waiting_for_description)
async def e_desc(message: types.Message, state: FSMContext):
    data = await state.get_data(); v = message.text.strip(); nd = data['od'] if v=="0" else v; await update_book_info(data['edit_book_id'], message.from_user.id, data['nt'], data['na'], data['ng'], data['ntg'], data['nr'], nd); await message.answer("✅ Готово!"); await state.clear()

@dp.callback_query(F.data.startswith("delete_"))
async def p_del(c: types.CallbackQuery):
    bid = c.data.split('_')[1]; kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Удалить", callback_data=f"c_del_{bid}"), InlineKeyboardButton(text="🔙 Отмена", callback_data="c_canc")]]); await c.message.edit_reply_markup(reply_markup=kb)

@dp.callback_query(F.data.startswith("c_del_"))
async def p_c_del(c: types.CallbackQuery):
    bid = int(c.data.split("_")[2]); await delete_book(bid, c.from_user.id); await c.message.delete(); await c.answer("Удалено")

@dp.callback_query(F.data == "c_canc")
async def p_c_canc(c: types.CallbackQuery): await c.answer("Отменено")

@dp.message(Command("help"))
@dp.message(F.text == "❓ Помощь")
async def cmd_help(message: types.Message):
    await message.answer("📖 <b>Помощь по боту</b>\n\n1. Находите книги через «Поиск».\n2. Добавляйте свои через «Добавить книгу».\n3. Если книга занята — встаньте в очередь.\n4. Передать книгу можно прямо из «Моего профиля».\n\nПриятного чтения! 📚", parse_mode="HTML")

@dp.message(F.text == "📊 Статистика")
@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if not await is_approved(message.from_user.id): return
    s = await get_stats()
    
    text = "📊 <b>Статистика нашего клуба</b>\n\n"
    text += f"👥 Участников: {s['total_users']}\n"
    text += f"📚 Книг в библиотеке: {s['total_books']}\n"
    text += f"🔄 Всего обменов: {s['total_transfers']}\n\n"
    
    if s['top_books']:
        text += "🔥 <b>Самые популярные книги:</b>\n"
        for idx, b in enumerate(s['top_books'], 1):
            text += f"{idx}. {b['title']} ({b['count']} раз)\n"
        text += "\n"
    else:
        text += "🔥 <b>Самые популярные книги:</b>\n<i>Скоро здесь появятся любимцы клуба!</i>\n\n"
        
    if s['top_readers']:
        text += "📖 <b>Самые активные читатели:</b>\n"
        for idx, r in enumerate(s['top_readers'], 1):
            name = r['real_name'] or r['username'] or "Anon"
            text += f"{idx}. {name} ({r['count']} книг взял)\n"
    else:
        text += "📖 <b>Самые активные читатели:</b>\n<i>Станьте первым активным читателем!</i>\n"
            
    await message.answer(text, parse_mode="HTML")

# --- Админка ---
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    user = await get_user(message.from_user.id)
    if not user or not user['is_admin']: return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Список юзеров", callback_data="adm_users")],
        [InlineKeyboardButton(text="📜 Логи действий", callback_data="adm_logs")]
    ])
    await message.answer("🛡 <b>Панель администратора</b>", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "adm_users")
async def adm_users_list(c: types.CallbackQuery):
    users = await get_all_users()
    text = "👥 <b>Все пользователи:</b>\n\n"
    for u in users:
        icon = "✅" if u['status'] == 'approved' else ("⏳" if u['status'] == 'pending' else "🚫")
        admin_at = " ⭐" if u['is_admin'] else ""
        text += f"{icon} {u['real_name'] or 'Не указано'} (@{u['username'] or 'no_user'}){admin_at}\n"
        text += f"└ 📍 {u['district'] or '-'}\n"
        text += f"└ Действия: /u_{u['user_id']}\n\n"
    await c.message.answer(text, parse_mode="HTML"); await c.answer()

@dp.callback_query(F.data == "adm_logs")
async def adm_logs_list(c: types.CallbackQuery):
    logs = await get_admin_logs()
    text = "📜 <b>Последние действия админов:</b>\n\n"
    if not logs: text += "Логов пока нет."
    else:
        for l in logs:
            text += f"🔹 {l['created_at']}\nID {l['admin_id']}: {l['action_type']}\n{l['details']}\n\n"
    await c.message.answer(text, parse_mode="HTML"); await c.answer()

@dp.message(F.text.startswith("/u_"))
async def adm_user_detail(message: types.Message):
    admin = await get_user(message.from_user.id)
    if not admin or not admin['is_admin']: return
    try:
        uid = int(message.text.split("_")[1]); user = await get_user(uid)
    except: return
    if not user: return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"adm_appr_{uid}"),
         InlineKeyboardButton(text="🚫 Блокировать", callback_data=f"adm_block_{uid}")],
        [InlineKeyboardButton(text="⭐ Сделать админом", callback_data=f"adm_make_{uid}")] if not user['is_admin'] else []
    ])
    text = f"👤 <b>Детали пользователя:</b>\n\nИмя: {user['real_name']}\nНик: @{user['username']}\nРайон: {user['district']}\nСтатус: {user['status']}"
    await message.answer(text, parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data.startswith("adm_appr_"))
async def adm_approve(c: types.CallbackQuery):
    uid = int(c.data.split("_")[2])
    await update_user_status(uid, 'approved')
    await log_admin_action(c.from_user.id, "approve_user", f"User ID: {uid}")
    try: await bot.send_message(uid, "🎉 Ваша заявка одобрена! Добро пожаловать в клуб. Теперь бот полностью доступен.")
    except: pass
    await c.message.edit_text("✅ Пользователь одобрен."); await c.answer()

@dp.callback_query(F.data.startswith("adm_rejt_"))
async def adm_reject(c: types.CallbackQuery):
    uid = int(c.data.split("_")[2])
    await update_user_status(uid, 'rejected')
    await log_admin_action(c.from_user.id, "reject_user", f"User ID: {uid}")
    try: await bot.send_message(uid, "😔 К сожалению, ваша заявка на вступление отклонена.")
    except: pass
    await c.message.edit_text("❌ Заявка отклонена."); await c.answer()

@dp.callback_query(F.data.startswith("adm_block_"))
async def adm_block(c: types.CallbackQuery):
    uid = int(c.data.split("_")[2])
    await update_user_status(uid, 'blocked')
    await log_admin_action(c.from_user.id, "block_user", f"User ID: {uid}")
    await c.message.edit_text("🚫 Пользователь заблокирован."); await c.answer()

@dp.callback_query(F.data.startswith("adm_make_"))
async def adm_make_admin(c: types.CallbackQuery):
    uid = int(c.data.split("_")[2])
    await set_admin_status(uid, True)
    await log_admin_action(c.from_user.id, "make_admin", f"User ID: {uid}")
    await c.message.edit_text("⭐ Пользователь назначен администратором."); await c.answer()

async def main(): await init_db(); await dp.start_polling(bot)
if __name__ == "__main__":
    try: asyncio.run(main())
    except: pass
