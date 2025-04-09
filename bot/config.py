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

if not BOT_TOKEN or not DATABASE_URL:
    print("Ошибка: Не найдены необходимые переменные окружения в файле .env!")
    print("Убедитесь, что файл .env содержит BOT_TOKEN и DATABASE_URL")
    sys.exit(1)
