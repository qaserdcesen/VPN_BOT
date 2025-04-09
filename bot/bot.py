from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
import asyncio
import logging
from bot.config import BOT_TOKEN
from bot.handlers.start import register_handlers
from bot.utils.db import init_db

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Регистрация обработчиков
register_handlers(dp)

# Функция запуска бота
async def main() -> None:
    logger.info("Инициализация базы данных...")
    await init_db()
    
    logger.info("Запуск бота...")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
