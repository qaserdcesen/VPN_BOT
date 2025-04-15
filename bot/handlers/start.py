from aiogram import Router, types, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import uuid
from bot.services.vpn_service import VPNService
from bot.utils.db import async_session
from bot.models.client import Client
from bot.models.user import User
from sqlalchemy import select
from bot.keyboards.instruction_kb import get_instruction_keyboard
from bot.keyboards.user_menu_kb import get_user_menu_keyboard

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

# Функция для форматирования информации о клиенте
def format_client_info(client):
    return (
        f"UUID: {client.uuid}\n"
        f"Nickname: {client.email}\n"
        f"Limit IP: {client.limit_ip}\n"
        f"Traffic: {client.total_traffic / (1024 * 1024 * 1024):.1f} GB"
    )

@router.callback_query(lambda c: c.data == "get_config")
async def process_get_config(callback: types.CallbackQuery):
    try:
        async with async_session() as session:
            # Проверяем существование пользователя и его конфига в одной транзакции
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
            
            # Проверяем, есть ли уже конфиг у этого пользователя
            client_result = await session.execute(
                select(Client).where(Client.user_id == user.id)
            )
            existing_client = client_result.scalar_one_or_none()
            
            if existing_client:
                # У пользователя уже есть конфиг
                await callback.message.answer(
                    f"⚠️ У вас уже есть активный VPN конфиг!\n\n{format_client_info(existing_client)}"
                )
                await callback.answer()
                return
            
            # Создаем новый конфиг
            user_uuid = str(uuid.uuid4())
            nickname = f"user_{callback.from_user.id}"
            
            # Создаем конфиг на сервере и получаем URL
            success, vpn_url = await vpn_service.create_config(nickname, user_uuid)
            
            # Сохраняем в базу
            client = Client(
                user_id=user.id,
                email=nickname,
                uuid=user_uuid,
                limit_ip=3,
                total_traffic=2 * 1024 * 1024 * 1024,
                is_active=True,
                config_data=vpn_url  # Сохраняем URL конфига
            )
            session.add(client)
            await session.commit()

            # Отправляем сообщение об успехе с конфигом И устанавливаем клавиатуру меню
            await callback.message.answer(
                f"✅ VPN создан успешно!\n\n{format_client_info(client)}\n\n"
                f"<code>{vpn_url}</code>",
                parse_mode="HTML",
                reply_markup=get_user_menu_keyboard()  # Добавляем клавиатуру к первому сообщению
            )
            
            # Отправляем последнее сообщение с инструкциями
            await callback.message.answer(
                "📱 Выберите устройство для просмотра инструкции по установке VPN:",
                reply_markup=get_instruction_keyboard()
            )
    
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка при создании VPN: {str(e)}")
        print(f"Ошибка: {str(e)}")
    
    await callback.answer()

# Обновляем обработчики для кнопок меню, теперь используем текст сообщения вместо callback_data
@router.message(lambda message: message.text == "Мой профиль")
async def process_profile(message: types.Message):
    await message.answer("Информация о вашем профиле...")

@router.message(lambda message: message.text == "Подписка и оплата")
async def process_subscription(message: types.Message):
    await message.answer("Информация о подписке и оплате...")

@router.message(lambda message: message.text == "Бонусы")
async def process_bonuses(message: types.Message):
    await message.answer("Информация о бонусах...")

@router.message(lambda message: message.text == "Инфо")
async def process_info(message: types.Message):
    await message.answer("Общая информация...")

def register_handlers(dp: Dispatcher):
    dp.include_router(router)
