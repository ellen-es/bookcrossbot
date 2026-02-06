import aiosqlite
import os

DB_PATH = 'books_bot.db'

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Таблица пользователей
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                real_name TEXT,
                district TEXT,
                street TEXT,
                status TEXT DEFAULT 'pending', -- 'pending', 'approved', 'blocked'
                is_admin INTEGER DEFAULT 0
            )
        """)
        
        # Добавляем колонки если их нет (для миграции)
        for col, col_type in [("real_name", "TEXT"), ("district", "TEXT"), ("street", "TEXT"), ("status", "TEXT DEFAULT 'pending'"), ("is_admin", "INTEGER DEFAULT 0")]:
            try:
                await db.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
            except: pass

        # Таблица книг
        await db.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                title TEXT,
                author TEXT,
                genre TEXT,
                tags TEXT,
                age_rating TEXT,
                description TEXT,
                photo_id TEXT,
                current_holder_id INTEGER,
                status TEXT DEFAULT 'available',
                return_requested INTEGER DEFAULT 0,
                FOREIGN KEY (owner_id) REFERENCES users (user_id),
                FOREIGN KEY (current_holder_id) REFERENCES users (user_id)
            )
        """)
        
        # Таблица очереди (waitlist)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS waitlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER,
                user_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (book_id) REFERENCES books (id),
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)
        
        # Таблица бронирований
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER,
                renter_id INTEGER,
                status TEXT DEFAULT 'pending',
                FOREIGN KEY (book_id) REFERENCES books (id),
                FOREIGN KEY (renter_id) REFERENCES users (user_id)
            )
        """)

        # Таблица истории перемещений
        await db.execute("""
            CREATE TABLE IF NOT EXISTS movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER,
                from_user_id INTEGER,
                to_user_id INTEGER,
                event_type TEXT, -- 'transfer', 'return'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (book_id) REFERENCES books (id),
                FOREIGN KEY (from_user_id) REFERENCES users (user_id),
                FOREIGN KEY (to_user_id) REFERENCES users (user_id)
            )
        """)
        
        # Таблица отзывов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER,
                user_id INTEGER,
                text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (book_id) REFERENCES books (id),
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)

        # Таблица логов админа
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                action_type TEXT,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def add_user(user_id, username, full_name, status='pending'):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, full_name, status) VALUES (?, ?, ?, ?)",
            (user_id, username, full_name, status)
        )
        await db.commit()

async def update_user_profile(user_id, real_name, district, street):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET real_name = ?, district = ?, street = ? WHERE user_id = ?",
            (real_name, district, street, user_id)
        )
        await db.commit()

async def update_user_status(user_id, status):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET status = ? WHERE user_id = ?", (status, user_id))
        await db.commit()

async def set_admin_status(user_id, is_admin):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_admin = ? WHERE user_id = ?", (1 if is_admin else 0, user_id))
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()

async def get_all_users():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users") as cursor:
            return await cursor.fetchall()

async def log_admin_action(admin_id, action_type, details):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO admin_logs (admin_id, action_type, details) VALUES (?, ?, ?)",
            (admin_id, action_type, details)
        )
        await db.commit()

async def get_admin_logs(limit=50):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM admin_logs ORDER BY created_at DESC LIMIT ?", (limit,)) as cursor:
            return await cursor.fetchall()

async def add_book(owner_id, title, author, genre, tags, age_rating, description, photo_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO books (owner_id, title, author, genre, tags, age_rating, description, photo_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (owner_id, title, author, genre, tags, age_rating, description, photo_id))
        await db.commit()

async def get_all_books(status_filter='available'):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = """
            SELECT b.*, u.username as owner_username, u.full_name as owner_name,
                   h.username as holder_username, h.full_name as holder_name
            FROM books b
            JOIN users u ON b.owner_id = u.user_id
            LEFT JOIN users h ON b.current_holder_id = h.user_id
            WHERE 1=1
        """
        if status_filter == 'available':
            query += " AND b.status = 'available' AND b.current_holder_id IS NULL"
        elif status_filter == 'held':
            query += " AND b.current_holder_id IS NOT NULL"
        elif status_filter == 'all':
            query += " AND (b.status = 'available' OR b.current_holder_id IS NOT NULL)"

        async with db.execute(query) as cursor:
            return await cursor.fetchall()

async def search_books(genre=None, tag=None, age_rating=None, text_query=None, status_filter='all'):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = """
            SELECT b.*, u.username as owner_username, u.full_name as owner_name,
                   h.username as holder_username, h.full_name as holder_name
            FROM books b
            JOIN users u ON b.owner_id = u.user_id
            LEFT JOIN users h ON b.current_holder_id = h.user_id
            WHERE 1=1
        """
        params = []
        
        if status_filter == 'available':
            query += " AND b.status = 'available' AND b.current_holder_id IS NULL"
        elif status_filter == 'held':
            query += " AND b.current_holder_id IS NOT NULL"
        elif status_filter == 'all':
            query += " AND (b.status = 'available' OR b.current_holder_id IS NOT NULL)"

        if genre:
            query += " AND b.genre LIKE ?"
            params.append(f"%{genre}%")
        if tag:
            query += " AND b.tags LIKE ?"
            params.append(f"%{tag}%")
        if age_rating:
            query += " AND b.age_rating = ?"
            params.append(age_rating)
        if text_query:
            query += " AND (b.title LIKE ? OR b.author LIKE ? OR b.description LIKE ?)"
            params.extend([f"%{text_query}%", f"%{text_query}%", f"%{text_query}%"])
            
        async with db.execute(query, tuple(params)) as cursor:
            return await cursor.fetchall()

async def get_unique_genres():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT DISTINCT genre FROM books WHERE genre IS NOT NULL AND status = 'available'") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows if row[0]]

async def get_unique_age_ratings():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT DISTINCT age_rating FROM books WHERE age_rating IS NOT NULL AND status = 'available'") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows if row[0]]

async def get_book(book_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = """
            SELECT b.*, u.username as owner_username, u.full_name as owner_name,
                   h.username as holder_username, h.full_name as holder_name
            FROM books b
            JOIN users u ON b.owner_id = u.user_id
            LEFT JOIN users h ON b.current_holder_id = h.user_id
            WHERE b.id = ?
        """
        async with db.execute(query, (book_id,)) as cursor:
            return await cursor.fetchone()

async def confirm_transfer(book_id, holder_id):
    async with aiosqlite.connect(DB_PATH) as db:
        # Получаем владельца и текущего держателя
        async with db.execute("SELECT owner_id, current_holder_id FROM books WHERE id = ?", (book_id,)) as cursor:
            row = await cursor.fetchone()
            if not row: return None
            owner_id, old_holder_id = row
            
        from_id = old_holder_id if old_holder_id else owner_id
        
        await db.execute("UPDATE books SET current_holder_id = ?, status = 'unavailable' WHERE id = ?", (holder_id, book_id))
        # Записываем историю: от текущего держателя к новому читателю
        await db.execute("INSERT INTO movements (book_id, from_user_id, to_user_id, event_type) VALUES (?, ?, ?, 'transfer')", (book_id, from_id, holder_id))
        # Обновляем статус бронирования на 'completed' (если оно было)
        await db.execute("UPDATE bookings SET status = 'completed' WHERE book_id = ? AND renter_id = ? AND status = 'pending'", (book_id, holder_id))
        await db.commit()
        return owner_id

async def reject_booking(book_id, renter_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE bookings SET status = 'rejected' WHERE book_id = ? AND renter_id = ? AND status = 'pending'", (book_id, renter_id))
        await db.commit()

async def return_book(book_id):
    async with aiosqlite.connect(DB_PATH) as db:
        # Получаем текущего холдера и владельца для истории
        async with db.execute("SELECT owner_id, current_holder_id FROM books WHERE id = ?", (book_id,)) as cursor:
            row = await cursor.fetchone()
            if not row: return
            owner_id, holder_id = row
            
        await db.execute("UPDATE books SET current_holder_id = NULL, status = 'available', return_requested = 0 WHERE id = ?", (book_id,))
        # Записываем историю: от читателя к владельцу
        if holder_id:
            await db.execute("INSERT INTO movements (book_id, from_user_id, to_user_id, event_type) VALUES (?, ?, ?, 'return')", (book_id, holder_id, owner_id))
        await db.commit()

async def get_book_history(book_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = """
            SELECT m.*, 
                   u_from.full_name as from_name, u_from.username as from_username,
                   u_to.full_name as to_name, u_to.username as to_username
            FROM movements m
            LEFT JOIN users u_from ON m.from_user_id = u_from.user_id
            LEFT JOIN users u_to ON m.to_user_id = u_to.user_id
            WHERE m.book_id = ?
            ORDER BY m.created_at ASC
        """
        async with db.execute(query, (book_id,)) as cursor:
            return await cursor.fetchall()

async def get_books_on_shelf(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = """
            SELECT b.*, u.username as owner_username, u.full_name as owner_name
            FROM books b
            JOIN users u ON b.owner_id = u.user_id
            WHERE b.current_holder_id = ?
        """
        async with db.execute(query, (user_id,)) as cursor:
            return await cursor.fetchall()

async def add_to_waitlist(book_id, user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id FROM waitlist WHERE book_id = ? AND user_id = ?", (book_id, user_id)) as cursor:
            if await cursor.fetchone(): return False
        await db.execute("INSERT INTO waitlist (book_id, user_id) VALUES (?, ?)", (book_id, user_id))
        await db.commit()
        return True

async def get_waitlist(book_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = """
            SELECT w.*, u.username, u.full_name
            FROM waitlist w
            JOIN users u ON w.user_id = u.user_id
            WHERE w.book_id = ?
            ORDER BY w.created_at ASC
        """
        async with db.execute(query, (book_id,)) as cursor:
            return await cursor.fetchall()

async def remove_from_waitlist(book_id, user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM waitlist WHERE book_id = ? AND user_id = ?", (book_id, user_id))
        await db.commit()

async def add_review(book_id, user_id, text):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO reviews (book_id, user_id, text) VALUES (?, ?, ?)", (book_id, user_id, text))
        await db.commit()

async def get_book_reviews(book_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = """
            SELECT r.*, u.username, u.full_name
            FROM reviews r
            JOIN users u ON r.user_id = u.user_id
            WHERE r.book_id = ?
            ORDER BY r.created_at DESC
        """
        async with db.execute(query, (book_id,)) as cursor:
            return await cursor.fetchall()

async def delete_review(review_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
        await db.commit()

async def create_booking(book_id, renter_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO bookings (book_id, renter_id) VALUES (?, ?)", (book_id, renter_id))
        await db.commit()

async def get_user_books(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM books WHERE owner_id = ?", (user_id,)) as cursor:
            return await cursor.fetchall()

async def get_user_bookings(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT b.id as booking_id, bk.title, bk.author, u.username as owner_username
            FROM bookings b
            JOIN books bk ON b.book_id = bk.id
            JOIN users u ON bk.owner_id = u.user_id
            WHERE b.renter_id = ? AND b.status = 'pending'
        """, (user_id,)) as cursor:
            return await cursor.fetchall()

async def get_incoming_requests(owner_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = """
            SELECT b.id as booking_id, b.renter_id, bk.id as book_id, bk.title, u.username as renter_username, u.full_name as renter_name
            FROM bookings b
            JOIN books bk ON b.book_id = bk.id
            JOIN users u ON b.renter_id = u.user_id
            WHERE bk.owner_id = ? AND b.status = 'pending'
        """
        async with db.execute(query, (owner_id,)) as cursor:
            return await cursor.fetchall()

async def delete_book(book_id, owner_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        if owner_id:
            await db.execute("DELETE FROM books WHERE id = ? AND owner_id = ?", (book_id, owner_id))
        else:
            await db.execute("DELETE FROM books WHERE id = ?", (book_id,))
        await db.commit()

async def update_book_status(book_id, owner_id, status):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE books SET status = ? WHERE id = ? AND owner_id = ?", (status, book_id, owner_id))
        await db.commit()

async def update_book_info(book_id, title, author, genre, tags, age_rating, description, owner_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        if owner_id:
            await db.execute("""
                UPDATE books SET title=?, author=?, genre=?, tags=?, age_rating=?, description=?
                WHERE id=? AND owner_id=?
            """, (title, author, genre, tags, age_rating, description, book_id, owner_id))
        else:
            await db.execute("""
                UPDATE books SET title=?, author=?, genre=?, tags=?, age_rating=?, description=?
                WHERE id=?
            """, (title, author, genre, tags, age_rating, description, book_id))
        await db.commit()

async def request_book_return(book_id, owner_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE books SET return_requested = 1 WHERE id = ? AND owner_id = ?", (book_id, owner_id))
        await db.commit()

async def cancel_return_request(book_id, owner_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE books SET return_requested = 0 WHERE id = ? AND owner_id = ?", (book_id, owner_id))
        await db.commit()

async def get_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        stats = {}
        
        # Общие цифры
        async with db.execute("SELECT COUNT(*) FROM users WHERE status = 'approved'") as c:
            stats['total_users'] = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM books") as c:
            stats['total_books'] = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM movements WHERE event_type = 'transfer'") as c:
            stats['total_transfers'] = (await c.fetchone())[0]

        # Топ-5 популярных книг (по количеству перемещений)
        query_top_books = """
            SELECT b.title, COUNT(m.id) as count
            FROM movements m
            JOIN books b ON m.book_id = b.id
            WHERE m.event_type = 'transfer'
            GROUP BY m.book_id
            ORDER BY count DESC
            LIMIT 5
        """
        async with db.execute(query_top_books) as c:
            stats['top_books'] = await c.fetchall()

        # Топ-5 активных читателей (кто получил больше всего книг)
        query_top_readers = """
            SELECT u.real_name, u.username, COUNT(m.id) as count
            FROM movements m
            JOIN users u ON m.to_user_id = u.user_id
            WHERE m.event_type = 'transfer'
            GROUP BY m.to_user_id
            ORDER BY count DESC
            LIMIT 5
        """
        async with db.execute(query_top_readers) as c:
            stats['top_readers'] = await c.fetchall()
            
        return stats
