from aiogram import Router, types, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import uuid
from bot.services.vpn_service import VPNService
from bot.utils.db import async_session
from bot.models.client import Client
from bot.models.user import User
from sqlalchemy import select

router = Router()
vpn_service = VPNService()

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Получить конфиг", callback_data="get_config")]
        ]
    )
    
    await message.answer(
        "Привет! Нажми кнопку ниже, чтобы получить VPN конфигурацию",
        reply_markup=keyboard
    )

@router.callback_query(lambda c: c.data == "get_config")
async def process_get_config(callback: types.CallbackQuery):
    try:
        async with async_session() as session:
            # Проверяем существование пользователя
            result = await session.execute(
                select(User).where(User.tg_id == callback.from_user.id)
            )
            user = result.scalar_one_or_none()
            
            # Если пользователя нет - создаем
            if not user:
                user = User(
                    tg_id=callback.from_user.id,
                    username=callback.from_user.username or "none"
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
            
            # Создаем запись клиента
            user_uuid = str(uuid.uuid4())
            nickname = f"user_{callback.from_user.id}"
            
            # Создаем конфиг на сервере
            await vpn_service.create_config(nickname, user_uuid)
            
            # Сохраняем в базу
            client = Client(
                user_id=user.id,
                email=nickname,
                uuid=user_uuid,
                limit_ip=3,
                total_traffic=2 * 1024 * 1024 * 1024,
                is_active=True
            )
            session.add(client)
            await session.commit()

            # Отправляем сообщение об успехе
            await callback.message.answer(
                f"✅ VPN создан успешно!\n\n"
                f"UUID: {user_uuid}\n"
                f"Nickname: {nickname}\n"
                f"Limit IP: 3\n"
                f"Traffic: 2 GB"
            )
    
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка при создании VPN: {str(e)}")
        print(f"Ошибка: {str(e)}")
    
    await callback.answer()

def register_handlers(dp: Dispatcher):
    dp.include_router(router)
