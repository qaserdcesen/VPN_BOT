from dotenv import load_dotenv
import os
import sys
from pathlib import Path
import logging

# Получаем путь к корневой директории проекта (на уровень выше папки bot)
BASE_DIR = Path(__file__).resolve().parent.parent

# Настройка логгера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загружаем переменные окружения из .env файла
logger.info(f"Путь к .env файлу: {BASE_DIR / '.env'}")
if not load_dotenv(BASE_DIR / ".env"):
    logger.error(f"Ошибка: Файл .env не найден в {BASE_DIR}")
    sys.exit(1)

# Выводим все переменные окружения для отладки
logger.info("Чтение переменных окружения из .env:")
logger.info(f"BOT_TOKEN: {os.getenv('BOT_TOKEN', 'Не найден')}")
logger.info(f"DATABASE_URL: {os.getenv('DATABASE_URL', 'Не найден')}")
logger.info(f"API_BASE_URL: {os.getenv('API_BASE_URL', 'Не найден')}")
logger.info(f"INBOUND_ID: {os.getenv('INBOUND_ID', 'Не найден')}")
logger.info(f"API_USERNAME: {os.getenv('API_USERNAME', 'Не найден')}")
logger.info(f"API_PASSWORD: {os.getenv('API_PASSWORD', 'Не найден')}")
logger.info(f"YOOKASSA_SHOP_ID: {os.getenv('YOOKASSA_SHOP_ID', 'Не найден')}")
logger.info(f"YOOKASSA_SECRET_KEY: {os.getenv('YOOKASSA_SECRET_KEY', 'Не найден')}")
logger.info(f"OOKASSA_SHOP_ID: {os.getenv('OOKASSA_SHOP_ID', 'Не найден')}")

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
API_BASE_URL = os.getenv("API_BASE_URL")
INBOUND_ID = os.getenv("INBOUND_ID")
API_USERNAME = os.getenv("API_USERNAME")
API_PASSWORD = os.getenv("API_PASSWORD")

# Настройки для платежной системы
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
if not YOOKASSA_SHOP_ID:
    logger.warning("YOOKASSA_SHOP_ID не найден")
    
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
if not YOOKASSA_SECRET_KEY:
    logger.warning("YOOKASSA_SECRET_KEY не найден")
    
PAYMENT_RETURN_URL = os.getenv("PAYMENT_RETURN_URL", "https://t.me/ftwVPN_BOT")

# Печатаем финальные значения переменных (безопасно)
logger.info("Финальные значения переменных:")
logger.info(f"YOOKASSA_SHOP_ID: {'Настроен' if YOOKASSA_SHOP_ID else 'Не настроен'}")
logger.info(f"YOOKASSA_SECRET_KEY: {'Настроен' if YOOKASSA_SECRET_KEY else 'Не настроен'}")

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
    logger.error("Ошибка: Не найдены следующие переменные окружения в файле .env:")
    for var in missing_vars:
        logger.error(f"- {var}")
    sys.exit(1)

COOKIES_FILE = "bot/data/cookies.json"  # путь для сохранения куки

# Список ID администраторов (Telegram ID)
ADMIN_IDS = [1320701464, 854523535]  # Ваш Telegram ID
