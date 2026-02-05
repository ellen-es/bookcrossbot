---
description: How to safely restart the Telegram bot to avoid multiple instances
---

Whenever you need to restart the Telegram bot (after code changes or to fix conflicts), follow these steps strictly:

// turbo
1. Stop all existing Python processes related to the bot to prevent conflicts:
   `pkill -f "python main.py" || true`

2. Wait for a second to ensure the port/token is released.

// turbo
3. Start the bot in the background using the virtual environment:
   `./.venv/bin/python main.py`

4. Use the `command_status` tool to verify that the bot has started successfully and is "polling" for updates.
