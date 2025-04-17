from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
import asyncio
import logging
from bot.config import BOT_TOKEN
from bot.handlers.start import register_handlers
from bot.handlers.payment import register_payment_handlers
from bot.utils.db import init_db
from bot.utils.middlewares import ThrottlingMiddleware, BanCheckMiddleware, AntiFloodMiddleware
from bot.services.ban_service import BanService
from bot.services.payment_service import PaymentService

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

# Инициализация сервисов
ban_service = BanService(bot)  # Передаем экземпляр бота

dp = Dispatcher()

# Инициализация middleware
throttling_middleware = ThrottlingMiddleware(rate_limit=2.0)

# Добавляем middleware
dp.message.middleware(throttling_middleware)  # Ограничение в 2 секунды
dp.callback_query.middleware(ThrottlingMiddleware(rate_limit=1.0))  # Для callback_query
dp.message.middleware(BanCheckMiddleware(ban_service))  # Проверка бана
dp.callback_query.middleware(BanCheckMiddleware(ban_service))  # Для callback_query
dp.message.middleware(AntiFloodMiddleware(ban_service))  # Защита от флуда для сообщений
dp.callback_query.middleware(AntiFloodMiddleware(ban_service))  # Защита от флуда для кнопок

# Регистрация обработчиков
register_handlers(dp)
register_payment_handlers(dp)

# Функция запуска бота
async def main() -> None:
    logger.info("Инициализация базы данных...")
    await init_db()
    
    # Запускаем задачу очистки для ThrottlingMiddleware
    await throttling_middleware.start_cleanup()
    
    # Запускаем проверку платежей в фоновой задаче
    asyncio.create_task(PaymentService.start_payment_checker(bot, check_interval=60))
    logger.info("Запущена фоновая задача проверки платежей каждые 60 секунд")
    
    logger.info("Запуск бота...")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
