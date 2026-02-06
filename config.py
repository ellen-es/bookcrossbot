import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(i.strip()) for i in os.getenv("ADMIN_IDS", "").split(",") if i.strip()]

if not BOT_TOKEN:
    print("Ошибка: Токен бота не найден! Создайте файл .env и добавьте туда BOT_TOKEN=ваш_токен")
