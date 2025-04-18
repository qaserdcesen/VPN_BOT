from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from bot.config import DATABASE_URL
from bot.utils.base import Base
from sqlalchemy.future import select

# Создаем асинхронный движок
engine = create_async_engine(DATABASE_URL, echo=True)

# Фабрика сессий для работы с асинхронной БД
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    """Инициализирует базу данных, создавая все таблицы по моделям, наследующим Base."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Заполняем таблицу планов
    await fill_plans_table()

async def fill_plans_table():
    """Заполняет таблицу plans данными из словаря TARIFFS."""
    from bot.keyboards.subscription_kb import TARIFFS
    from bot.models.plan import Plan
    
    async with async_session() as session:
        # Проверяем, есть ли уже записи в таблице
        result = await session.execute(select(Plan))
        existing_plans = result.scalars().all()
        
        if not existing_plans:
            # Если таблица пуста, добавляем планы
            for key, tariff in TARIFFS.items():
                # Преобразуем описание трафика в байты
                traffic_limit = 0  # По умолчанию 0 для безлимита
                
                if "ГБ" in tariff["traffic"]:
                    # Например "25ГБ/месяц" -> 25 * 1024*1024*1024
                    gb_value = int(tariff["traffic"].split("ГБ")[0])
                    traffic_limit = gb_value * 1024 * 1024 * 1024
                
                plan = Plan(
                    title=tariff["name"],
                    traffic_limit=traffic_limit,  # 0 для безлимита
                    duration_days=30,  # 30 дней по умолчанию
                    price=tariff["price"]
                )
                session.add(plan)
            
            await session.commit()
            print(f"Таблица plans заполнена начальными данными: {len(TARIFFS)} тарифов")
        else:
            print(f"Таблица plans уже содержит данные: {len(existing_plans)} тарифов")
