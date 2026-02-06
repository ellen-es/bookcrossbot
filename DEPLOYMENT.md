# 🚀 Инструкция по развертыванию — BookCrossing Bot

Этот документ описывает процесс установки и запуска бота на удаленном сервере (VPS/VDS) под управлением Linux (Ubuntu/Debian) для работы в режиме 24/7.

---

## 🛠 1. Подготовка сервера

1. Обновите пакеты:
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```
2. Установите Python 3.9+ и необходимые утилиты:
   ```bash
   sudo apt install python3-pip python3-venv git sqlite3 -y
   ```

---

## 📥 2. Клонирование и установка

1. Склонируйте репозиторий:
   ```bash
   git clone https://github.com/ellen-es/bookcrossbot.git
   cd bookcrossbot
   ```
2. Создайте виртуальное окружение и установите зависимости:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Создайте файл конфигурации:
   ```bash
   cp .env.example .env
   nano .env
   ```
   *Вставьте ваш `BOT_TOKEN` и `ADMIN_IDS`.*

---

## ⚙️ 3. Настройка автоматического запуска (systemd)

Для того чтобы бот автоматически запускался после перезагрузки сервера и восстанавливался после сбоев, используйте системную службу.

1. Создайте файл службы:
   ```bash
   sudo nano /etc/systemd/system/bookbot.service
   ```
2. Вставьте следующее содержимое (замените `USER` и `/path/to/bot` на свои данные):
   ```ini
   [Unit]
   Description=BookCrossing Telegram Bot
   After=network.target

   [Service]
   User=USER
   Group=USER
   WorkingDirectory=/path/to/bookcrossbot
   EnvironmentFile=/path/to/bookcrossbot/.env
   ExecStart=/path/to/bookcrossbot/.venv/bin/python main.py
   Restart=always
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```
3. Активируйте службу:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable bookbot
   sudo systemctl start bookbot
   ```

---

## 📊 4. Мониторинг и управление

* **Проверка статуса**: `sudo systemctl status bookbot`
* **Просмотр логов**: `journalctl -u bookbot -f`
* **Перезапуск**: `sudo systemctl restart bookbot`

---

## 💾 5. Резервное копирование

База данных хранится в одном файле `books_bot.db`. Рекомендуется периодически копировать этот файл. Самый простой способ — настроить `cron` задачу для отправки файла в облако или на другой сервер.

Пример ручного копирования:
```bash
cp books_bot.db books_bot_backup_$(date +%F).db
```
---

## 🔄 6. Обновление кода

Если вы внесли изменения в репозиторий на GitHub:
```bash
git pull origin main
sudo systemctl restart bookbot
```
