from bot.models.user import User
from bot.models.client import Client
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from bot.config import DATABASE_URL

# Базовый класс для моделей
Base = declarative_base()

# Создаем асинхронный движок
engine = create_async_engine(DATABASE_URL, echo=True)

# Фабрика сессий для работы с асинхронной БД
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    """Инициализирует базу данных, создавая все таблицы по моделям, наследующим Base."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
