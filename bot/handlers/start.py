from aiogram import Router, types, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import uuid
from bot.services.vpn_service import VPNService
from bot.utils.db import async_session
from bot.models.client import Client

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
        user_uuid = str(uuid.uuid4())
        nickname = f"user_{callback.from_user.id}"
        
        # Создаем конфиг через сервис
        config_result = await vpn_service.create_config(nickname, user_uuid)
        
        # Сохраняем в базу
        async with async_session() as session:
            client = Client(
                user_id=callback.from_user.id,
                email=nickname,
                uuid=user_uuid,
                limit_ip=3,
                total_traffic=2 * 1024 * 1024 * 1024,  # 2 GB
                config_data=config_result["config"]
            )
            session.add(client)
            await session.commit()
        
        await callback.message.answer("✅ Ваш VPN конфиг создан!")
        # Отправка конфига пользователю...
        
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка при создании конфига: {str(e)}")
    
    await callback.answer()

def register_handlers(dp: Dispatcher):
    dp.include_router(router)
