import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    print("Ошибка: Токен бота не найден! Создайте файл .env и добавьте туда BOT_TOKEN=ваш_токен")
