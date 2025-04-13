from dotenv import load_dotenv
import os
import sys
from pathlib import Path

# Получаем путь к корневой директории проекта (на уровень выше папки bot)
BASE_DIR = Path(__file__).resolve().parent.parent

# Загружаем переменные окружения из .env файла
if not load_dotenv(BASE_DIR / ".env"):
    print(f"Ошибка: Файл .env не найден в {BASE_DIR}")
    sys.exit(1)

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
API_BASE_URL = os.getenv("API_BASE_URL")
INBOUND_ID = os.getenv("INBOUND_ID")
API_USERNAME = os.getenv("API_USERNAME")
API_PASSWORD = os.getenv("API_PASSWORD")

# Проверяем все необходимые переменные
required_vars = {
    "BOT_TOKEN": BOT_TOKEN,
    "DATABASE_URL": DATABASE_URL,
    "API_BASE_URL": API_BASE_URL,
    "INBOUND_ID": INBOUND_ID,
    "API_USERNAME": API_USERNAME,
    "API_PASSWORD": API_PASSWORD
}

missing_vars = [var for var, value in required_vars.items() if not value]

if missing_vars:
    print("Ошибка: Не найдены следующие переменные окружения в файле .env:")
    for var in missing_vars:
        print(f"- {var}")
    sys.exit(1)

COOKIES_FILE = "bot/data/cookies.json"  # путь для сохранения куки
