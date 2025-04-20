from aiogram import Router, types, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import uuid
import logging
from bot.services.vpn_service import VPNService
from bot.utils.db import async_session
from bot.models.client import Client
from bot.models.user import User
from sqlalchemy import select
from bot.keyboards.instruction_kb import get_instruction_keyboard
from bot.keyboards.user_menu_kb import get_user_menu_keyboard
from bot.keyboards.subscription_kb import get_tariffs_info, get_tariffs_keyboard, get_payment_keyboard, TARIFFS

router = Router()
vpn_service = VPNService()
logger = logging.getLogger(__name__)

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
    # Формирование строки лимита трафика
    if client.total_traffic == 0:
        traffic_info = "Безлимит"
    else:
        traffic_info = f"{client.total_traffic / (1024 * 1024 * 1024):.1f} GB"
    
    return (
        f"UUID: {client.uuid}\n"
        f"Nickname: {client.email}\n"
        f"Limit IP: {client.limit_ip}\n"
        f"Traffic: {traffic_info}"
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
            
            # Устанавливаем начальные лимиты для бесплатного тарифа
            limit_ip = 3
            traffic_limit = 2 * 1024 * 1024 * 1024  # 2 ГБ по умолчанию
            
            # Создаем конфиг на сервере и получаем URL
            success, vpn_url = await vpn_service.create_config(
                nickname=nickname,
                user_uuid=user_uuid,
                traffic_limit=traffic_limit,
                limit_ip=limit_ip
            )
            
            # Сохраняем в базу
            client = Client(
                user_id=user.id,
                email=nickname,
                uuid=user_uuid,
                limit_ip=limit_ip,
                total_traffic=traffic_limit,
                is_active=True,
                config_data=vpn_url,  # Сохраняем URL конфига
                tariff_id=0  # Базовый тариф ftw.none для новых пользователей
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

# Функция для определения названия тарифа по его ID
def get_tariff_name_by_id(tariff_id):
    if tariff_id == 0:
        return "ftw.none"
    elif tariff_id == 1:
        return "ftw.base"
    elif tariff_id == 2:
        return "ftw.middle"
    elif tariff_id == 3:
        return "ftw.unlimited"
    else:
        return "Не определен"

# Обновляем обработчики для кнопок меню, теперь используем текст сообщения вместо callback_data
@router.message(lambda message: message.text == "Мой профиль")
async def process_profile(message: types.Message):
    try:
        async with async_session() as session:
            # Получаем пользователя
            user_query = await session.execute(
                select(User).where(User.tg_id == message.from_user.id)
            )
            user = user_query.scalar_one_or_none()
            
            if not user:
                await message.answer("❌ Ваш профиль не найден. Пожалуйста, запустите бота снова с помощью команды /start")
                return
            
            # Получаем клиента пользователя
            client_query = await session.execute(
                select(Client).where(Client.user_id == user.id)
            )
            client = client_query.scalar_one_or_none()
            
            if not client:
                await message.answer("📱 У вас еще нет активной подписки. Выберите 'Подписка и оплата' для приобретения тарифа.")
                return
            
            # Форматируем срок действия
            expiry_date = "Не ограничен"
            if client.expiry_time:
                expiry_date = client.expiry_time.strftime("%d.%m.%Y %H:%M")
            
            # Получаем название тарифа
            tariff_name = get_tariff_name_by_id(client.tariff_id)
            
            # Формируем сообщение профиля
            profile_text = (
                f"<b>📱 Мой профиль</b>\n\n"
                f"<b>Telegram ID:</b> {message.from_user.id}\n"
                f"<b>Тип подписки:</b> {tariff_name}\n"
                f"<b>Действует до:</b> {expiry_date}\n"
            )
            
            # Добавляем URL конфигурации, если он есть
            if client.config_data:
                profile_text += f"\n<b>Ваша VPN конфигурация:</b>\n<code>{client.config_data}</code>"
            else:
                profile_text += "\n⚠️ У вас нет активной VPN конфигурации"
            
            await message.answer(profile_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка при отображении профиля: {e}")
        await message.answer("❌ Произошла ошибка при загрузке профиля. Пожалуйста, попробуйте позже.")

@router.message(lambda message: message.text == "Подписка и оплата")
async def show_subscription_info(message: types.Message):
    # Отправляем информацию о тарифах и кнопки выбора
    await message.answer(
        get_tariffs_info(),
        reply_markup=get_tariffs_keyboard()
    )

@router.callback_query(lambda c: c.data == "pay_bonus")
async def process_bonus_payment(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Оплата с бонусного баланса выбрана. Проверяем баланс..."
    )
    # Здесь будет логика проверки баланса и проведения оплаты
    # ...
    await callback.answer()

@router.callback_query(lambda c: c.data == "pay_card")
async def process_card_payment(callback: types.CallbackQuery):
    # Отображаем список тарифов
    await callback.message.edit_text(
        get_tariffs_info(),
        reply_markup=get_tariffs_keyboard()
    )
    await callback.answer()

# Обработчик для кнопки "Назад" при выборе способа оплаты
@router.callback_query(lambda c: c.data == "back_to_tariffs")
async def back_to_tariffs(callback: types.CallbackQuery):
    # Возвращаемся к выбору тарифов
    await callback.message.edit_text(
        get_tariffs_info(),
        reply_markup=get_tariffs_keyboard()
    )
    await callback.answer()

def register_handlers(dp: Dispatcher):
    dp.include_router(router)
