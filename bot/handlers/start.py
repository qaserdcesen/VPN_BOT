from aiogram import Router, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy.future import select
from datetime import datetime

from bot.utils.db import async_session
from bot.models.user import User

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    tg_id = message.from_user.id
    username = message.from_user.username or "none"

    async with async_session() as session:
        # Проверяем наличие пользователя в БД
        result = await session.execute(select(User).filter_by(tg_id=tg_id))
        user = result.scalar_one_or_none()
        
        if not user:
            # Создаем нового пользователя
            user = User(
                tg_id=tg_id,
                username=username,
                created_at=datetime.utcnow(),
                last_login=datetime.utcnow()
            )
            session.add(user)
            await session.commit()
            await message.answer("Вы успешно зарегистрированы!")
        else:
            # Обновляем время последнего входа
            user.last_login = datetime.utcnow()
            await session.commit()
            await message.answer("Добро пожаловать обратно!")

def register_handlers(dp: Dispatcher):
    dp.include_router(router)
