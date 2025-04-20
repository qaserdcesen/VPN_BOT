from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import logging
from sqlalchemy.future import select
from bot.utils.db import async_session
from bot.models.user import User
from bot.models.client import Client
from bot.models.plan import Plan
from bot.models.payment import Payment
from bot.models.promo import Promo
from bot.config import ADMIN_IDS
from sqlalchemy import func, desc
import math
import asyncio
import random
import string
from datetime import datetime, timedelta
from decimal import Decimal

router = Router()
logger = logging.getLogger(__name__)

# Состояния FSM для рассылки
class BroadcastStates(StatesGroup):
    waiting_for_message = State()  # Ожидание сообщения для рассылки

# Состояния FSM для создания промокода
class PromoStates(StatesGroup):
    waiting_for_code = State()  # Ожидание ввода кода промокода
    waiting_for_discount = State()  # Ожидание ввода скидки
    waiting_for_expiration = State()  # Ожидание ввода срока действия
    waiting_for_limit = State()  # Ожидание ввода лимита использований
    waiting_for_confirmation = State()  # Ожидание подтверждения создания промокода

# Функция проверки является ли пользователь администратором
async def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# Общая функция для проверки прав администратора
async def check_admin(message: types.Message) -> bool:
    if not await is_admin(message.from_user.id):
        await message.answer("У вас нет прав для выполнения этой команды.")
        return False
    return True

# Команда /admin - основное меню админа
@router.message(Command("admin"))
async def admin_panel(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("У вас нет прав для выполнения этой команды.")
        return
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Пользователи", callback_data="admin_users")],
        [types.InlineKeyboardButton(text="Клиенты VPN", callback_data="admin_clients")],
        [types.InlineKeyboardButton(text="Платежи", callback_data="admin_payments")],
        [types.InlineKeyboardButton(text="Промокоды", callback_data="admin_promos")],
        [types.InlineKeyboardButton(text="Тарифы", callback_data="admin_plans")],
        [types.InlineKeyboardButton(text="Рассылка", callback_data="admin_broadcast")]
    ])
    
    await message.answer("Админ-панель. Выберите раздел:", reply_markup=keyboard)

# Функция для пагинации результатов
async def paginate_results(query_func, page, page_size, callback):
    try:
        # Получаем общее количество записей
        async with async_session() as session:
            total_count = await query_func(session, count=True)
            
            if total_count == 0:
                return "Записи не найдены.", None
            
            # Вычисляем общее количество страниц
            total_pages = math.ceil(total_count / page_size)
            
            # Проверяем корректность номера страницы
            if page < 1:
                page = 1
            elif page > total_pages:
                page = total_pages
            
            # Получаем данные для текущей страницы
            results = await query_func(session, page=page, page_size=page_size)
            
            # Форматируем результаты
            text = callback(results)
            
            # Создаем клавиатуру для пагинации
            keyboard = []
            
            # Добавляем навигационные кнопки
            nav_buttons = []
            if page > 1:
                nav_buttons.append(types.InlineKeyboardButton(
                    text="◀️ Назад", 
                    callback_data=f"{query_func.__name__}_{page-1}"
                ))
            
            if page < total_pages:
                nav_buttons.append(types.InlineKeyboardButton(
                    text="Вперёд ▶️", 
                    callback_data=f"{query_func.__name__}_{page+1}"
                ))
            
            if nav_buttons:
                keyboard.append(nav_buttons)
            
            # Добавляем статус пагинации и кнопку возврата
            info_text = f"Страница {page} из {total_pages} (всего записей: {total_count})"
            
            # Добавляем кнопку назад в меню
            keyboard.append([types.InlineKeyboardButton(text="Назад в меню", callback_data="admin_back")])
            
            return f"{text}\n\n{info_text}", types.InlineKeyboardMarkup(inline_keyboard=keyboard)
            
    except Exception as e:
        logger.error(f"Ошибка при пагинации результатов: {e}")
        return f"Ошибка при получении данных: {e}", None

# Функции для получения данных из БД
async def get_users(session, page=1, page_size=10, count=False):
    if count:
        result = await session.execute(select(func.count()).select_from(User))
        return result.scalar()
    
    result = await session.execute(
        select(User)
        .order_by(desc(User.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return result.scalars().all()

async def get_clients(session, page=1, page_size=10, count=False):
    if count:
        result = await session.execute(select(func.count()).select_from(Client))
        return result.scalar()
    
    result = await session.execute(
        select(Client, User)
        .join(User, Client.user_id == User.id)
        .order_by(desc(Client.expiry_time))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return result.all()

async def get_payments(session, page=1, page_size=10, count=False):
    if count:
        result = await session.execute(select(func.count()).select_from(Payment))
        return result.scalar()
    
    result = await session.execute(
        select(Payment, User)
        .join(User, Payment.user_id == User.id)
        .order_by(desc(Payment.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return result.all()

async def get_promos(session, page=1, page_size=10, count=False):
    if count:
        result = await session.execute(select(func.count()).select_from(Promo))
        return result.scalar()
    
    result = await session.execute(
        select(Promo)
        .order_by(desc(Promo.is_active), Promo.expiration_date)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return result.scalars().all()

async def get_plans(session, page=1, page_size=10, count=False):
    if count:
        result = await session.execute(select(func.count()).select_from(Plan))
        return result.scalar()
    
    result = await session.execute(
        select(Plan)
        .order_by(Plan.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return result.scalars().all()

# Форматеры для вывода результатов
def format_users(users):
    result = []
    for user in users:
        banned_status = "🚫 Забанен" if user.is_banned else "✅ Активен"
        ban_info = f" до {user.banned_until.strftime('%d.%m.%Y %H:%M')}" if user.banned_until else ""
        result.append(
            f"👤 <b>ID:</b> {user.id} | <b>TG ID:</b> {user.tg_id}\n"
            f"👤 @{user.username}\n"
            f"📧 {user.email or 'Нет email'}\n"
            f"📅 {user.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"Status: {banned_status}{ban_info}\n"
        )
    
    return "\n".join(result) if result else "Нет пользователей."

def format_clients(clients):
    result = []
    for client, user in clients:
        status = "✅ Активен" if client.is_active else "❌ Неактивен"
        expiry = client.expiry_time.strftime('%d.%m.%Y %H:%M') if client.expiry_time else "Нет срока"
        
        # Конвертируем трафик в понятный формат
        traffic = client.total_traffic
        if traffic is None:
            traffic_str = "не ограничен"
        else:
            if traffic >= 1024**3:
                traffic_str = f"{traffic/1024**3:.2f} GB"
            elif traffic >= 1024**2:
                traffic_str = f"{traffic/1024**2:.2f} MB"
            else:
                traffic_str = f"{traffic} B"
        
        result.append(
            f"🔑 <b>ID:</b> {client.id} | <b>Пользователь:</b> {user.tg_id} (@{user.username})\n"
            f"📧 {client.email or 'Нет email'}\n"
            f"💾 Лимит трафика: {traffic_str}\n"
            f"🖥 Лимит IP: {client.limit_ip}\n"
            f"📅 Действует до: {expiry}\n"
            f"Status: {status}\n"
        )
    
    return "\n".join(result) if result else "Нет клиентов."

def format_payments(payments):
    result = []
    for payment, user in payments:
        result.append(
            f"💰 <b>ID:</b> {payment.id} | <b>Пользователь:</b> {user.tg_id} (@{user.username})\n"
            f"💸 Сумма: {payment.amount} ₽\n"
            f"Status: {payment.status}\n"
            f"📅 Создан: {payment.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"📅 Оплачен: {payment.paid_at.strftime('%d.%m.%Y %H:%M') if payment.paid_at else 'Не оплачен'}\n"
        )
    
    return "\n".join(result) if result else "Нет платежей."

def format_promos(promos):
    result = []
    buttons = []
    
    for promo in promos:
        status = "✅ Активен" if promo.is_active else "❌ Неактивен"
        expiry = promo.expiration_date.strftime('%d.%m.%Y %H:%M') if promo.expiration_date else "Бессрочно"
        
        result.append(
            f"🎟 <b>ID:</b> {promo.id} | <b>Код:</b> <code>{promo.code}</code>\n"
            f"💹 Скидка: {float(promo.discount)}%\n"
            f"📊 Использован: {promo.used_count}/{promo.usage_limit or '∞'}\n"
            f"📅 Действует до: {expiry}\n"
            f"Status: {status}\n"
        )
        
        # Добавляем кнопки деактивации для активных промокодов
        if promo.is_active:
            buttons.append([types.InlineKeyboardButton(
                text=f"❌ Деактивировать {promo.code}",
                callback_data=f"delete_promo_{promo.id}"
            )])
    
    return "\n".join(result) if result else "Нет промокодов."

def format_plans(plans):
    result = []
    for plan in plans:
        # Конвертируем трафик в понятный формат
        traffic = plan.traffic_limit
        if traffic is None:
            traffic_str = "не ограничен"
        else:
            if traffic >= 1024**3:
                traffic_str = f"{traffic/1024**3:.2f} GB"
            elif traffic >= 1024**2:
                traffic_str = f"{traffic/1024**2:.2f} MB"
            else:
                traffic_str = f"{traffic} B"
        
        result.append(
            f"📋 <b>ID:</b> {plan.id} | <b>Название:</b> {plan.title}\n"
            f"💾 Трафик: {traffic_str}\n"
            f"📅 Длительность: {plan.duration_days} дней\n"
            f"💰 Цена: {plan.price} ₽\n"
        )
    
    return "\n".join(result) if result else "Нет тарифов."

# Обработчики для разделов админ-панели
@router.callback_query(lambda c: c.data == "admin_users")
async def process_admin_users(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("У вас нет прав администратора", show_alert=True)
        return
    
    text, markup = await paginate_results(get_users, 1, 5, format_users)
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data == "admin_clients")
async def process_admin_clients(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("У вас нет прав администратора", show_alert=True)
        return
    
    text, markup = await paginate_results(get_clients, 1, 5, format_clients)
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data == "admin_payments")
async def process_admin_payments(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("У вас нет прав администратора", show_alert=True)
        return
    
    text, markup = await paginate_results(get_payments, 1, 5, format_payments)
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data == "admin_promos")
async def process_admin_promos(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("У вас нет прав администратора", show_alert=True)
        return
    
    # Добавляем кнопку создания промокода
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin_create_promo")],
        [types.InlineKeyboardButton(text="Назад в меню", callback_data="admin_back")]
    ])
    
    text, markup = await paginate_results(get_promos, 1, 5, format_promos)
    
    # Добавляем кнопку создания промокода к существующей клавиатуре
    if markup:
        markup.inline_keyboard.insert(0, [types.InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin_create_promo")])
    else:
        markup = keyboard
    
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data == "admin_plans")
async def process_admin_plans(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("У вас нет прав администратора", show_alert=True)
        return
    
    text, markup = await paginate_results(get_plans, 1, 5, format_plans)
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer()

# Обработчики для пагинации
@router.callback_query(lambda c: c.data.startswith("get_users_"))
async def paginate_users(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("У вас нет прав администратора", show_alert=True)
        return
    
    page = int(callback.data.split("_")[-1])
    text, markup = await paginate_results(get_users, page, 5, format_users)
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("get_clients_"))
async def paginate_clients(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("У вас нет прав администратора", show_alert=True)
        return
    
    page = int(callback.data.split("_")[-1])
    text, markup = await paginate_results(get_clients, page, 5, format_clients)
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("get_payments_"))
async def paginate_payments(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("У вас нет прав администратора", show_alert=True)
        return
    
    page = int(callback.data.split("_")[-1])
    text, markup = await paginate_results(get_payments, page, 5, format_payments)
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("get_promos_"))
async def paginate_promos(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("У вас нет прав администратора", show_alert=True)
        return
    
    page = int(callback.data.split("_")[-1])
    text, markup = await paginate_results(get_promos, page, 5, format_promos)
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("get_plans_"))
async def paginate_plans(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("У вас нет прав администратора", show_alert=True)
        return
    
    page = int(callback.data.split("_")[-1])
    text, markup = await paginate_results(get_plans, page, 5, format_plans)
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer()

# Обработчик возврата в меню админ-панели
@router.callback_query(lambda c: c.data == "admin_back")
async def back_to_admin_menu(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("У вас нет прав администратора", show_alert=True)
        return
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Пользователи", callback_data="admin_users")],
        [types.InlineKeyboardButton(text="Клиенты VPN", callback_data="admin_clients")],
        [types.InlineKeyboardButton(text="Платежи", callback_data="admin_payments")],
        [types.InlineKeyboardButton(text="Промокоды", callback_data="admin_promos")],
        [types.InlineKeyboardButton(text="Тарифы", callback_data="admin_plans")],
        [types.InlineKeyboardButton(text="Рассылка", callback_data="admin_broadcast")]
    ])
    
    await callback.message.edit_text("Админ-панель. Выберите раздел:", reply_markup=keyboard)
    await callback.answer()

# Обработчики для рассылки сообщений
@router.callback_query(lambda c: c.data == "admin_broadcast")
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("У вас нет прав администратора", show_alert=True)
        return
    
    await state.set_state(BroadcastStates.waiting_for_message)
    await callback.message.edit_text(
        "📣 Введите сообщение для рассылки всем пользователям.\n"
        "Поддерживается HTML-разметка.\n\n"
        "Для отмены нажмите кнопку ниже.",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="Отмена", callback_data="admin_cancel_broadcast")]
        ])
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "admin_cancel_broadcast", BroadcastStates.waiting_for_message)
async def cancel_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("У вас нет прав администратора", show_alert=True)
        return
    
    await state.clear()
    await callback.message.edit_text("🚫 Рассылка отменена.", reply_markup=None)
    
    # Возвращаем в меню админа
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Вернуться в админ-панель", callback_data="admin_back")]
    ])
    await callback.message.answer("Выберите действие:", reply_markup=keyboard)
    await callback.answer()

@router.message(BroadcastStates.waiting_for_message)
async def process_broadcast_message(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    
    broadcast_text = message.text
    if not broadcast_text:
        await message.answer("❌ Сообщение не может быть пустым. Попробуйте снова или нажмите Отмена.")
        return
    
    # Получаем список всех пользователей
    async with async_session() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()
    
    # Подтверждение рассылки
    await message.answer(
        f"📨 Вы собираетесь отправить сообщение {len(users)} пользователям.\n\n"
        f"Текст сообщения:\n{broadcast_text}\n\n"
        f"Подтвердите рассылку:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="✅ Подтвердить", callback_data="admin_confirm_broadcast")],
            [types.InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel_broadcast")]
        ]),
        parse_mode="HTML"
    )
    
    # Сохраняем текст сообщения для дальнейшего использования
    await state.update_data(broadcast_text=broadcast_text)

@router.callback_query(lambda c: c.data == "admin_confirm_broadcast", BroadcastStates.waiting_for_message)
async def confirm_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("У вас нет прав администратора", show_alert=True)
        return
    
    # Получаем сохраненное сообщение
    user_data = await state.get_data()
    broadcast_text = user_data.get("broadcast_text", "")
    
    if not broadcast_text:
        await callback.message.edit_text("❌ Ошибка: сообщение для рассылки не найдено.")
        await state.clear()
        return
    
    # Получаем всех пользователей
    async with async_session() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()
    
    # Информируем о начале рассылки
    await callback.message.edit_text(f"🚀 Начинаем рассылку {len(users)} пользователям...")
    
    # Счетчики для статистики
    total_users = len(users)
    successful = 0
    failed = 0
    
    # Отправляем сообщения пользователям
    for user in users:
        try:
            await callback.bot.send_message(user.tg_id, broadcast_text, parse_mode="HTML")
            successful += 1
            # Небольшая пауза чтобы не перегрузить API
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения пользователю {user.tg_id}: {e}")
            failed += 1
    
    # Отчет о завершении рассылки
    await callback.message.answer(
        f"✅ Рассылка завершена!\n\n"
        f"📊 Статистика:\n"
        f"- Всего пользователей: {total_users}\n"
        f"- Успешно отправлено: {successful}\n"
        f"- Ошибок: {failed}",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="Вернуться в админ-панель", callback_data="admin_back")]
        ])
    )
    
    # Очищаем состояние
    await state.clear()

# Функция генерации случайного кода промокода
def generate_promo_code(length=8):
    """Генерирует случайный промокод из букв и цифр"""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

# Обработчики для создания промокода
@router.callback_query(lambda c: c.data == "admin_create_promo")
async def start_create_promo(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("У вас нет прав администратора", show_alert=True)
        return
    
    # Генерируем случайный код промокода
    promo_code = generate_promo_code()
    
    # Сохраняем сгенерированный код в состоянии
    await state.update_data(promo_code=promo_code)
    
    await callback.message.edit_text(
        f"🎟 Создание нового промокода\n\n"
        f"Предлагаемый код: <code>{promo_code}</code>\n\n"
        f"Введите свой код промокода или нажмите 'Использовать предложенный':",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text=f"Использовать {promo_code}", callback_data="use_suggested_code")],
            [types.InlineKeyboardButton(text="Отмена", callback_data="admin_promos")]
        ]),
        parse_mode="HTML"
    )
    
    await state.set_state(PromoStates.waiting_for_code)
    await callback.answer()

@router.callback_query(lambda c: c.data == "use_suggested_code", PromoStates.waiting_for_code)
async def use_suggested_code(callback: types.CallbackQuery, state: FSMContext):
    # Получаем сохраненный код из состояния
    user_data = await state.get_data()
    promo_code = user_data.get("promo_code", generate_promo_code())
    
    await ask_for_discount(callback.message, state, promo_code)
    await callback.answer()

@router.message(PromoStates.waiting_for_code)
async def process_promo_code(message: types.Message, state: FSMContext):
    # Получаем введенный код
    promo_code = message.text.strip().upper()
    
    # Проверяем, существует ли уже такой промокод
    async with async_session() as session:
        result = await session.execute(select(Promo).where(Promo.code == promo_code))
        existing_promo = result.scalar_one_or_none()
        
        if existing_promo:
            await message.answer(
                f"❌ Промокод <code>{promo_code}</code> уже существует. Пожалуйста, придумайте другой код.",
                parse_mode="HTML"
            )
            return
    
    await ask_for_discount(message, state, promo_code)

async def ask_for_discount(message, state, promo_code):
    # Сохраняем код промокода
    await state.update_data(promo_code=promo_code)
    
    # Запрашиваем скидку
    await message.answer(
        f"Выбран код: <code>{promo_code}</code>\n\n"
        f"Введите размер скидки в процентах (от 1 до 100):",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="10%", callback_data="discount_10")],
            [types.InlineKeyboardButton(text="20%", callback_data="discount_20")],
            [types.InlineKeyboardButton(text="30%", callback_data="discount_30")],
            [types.InlineKeyboardButton(text="50%", callback_data="discount_50")],
            [types.InlineKeyboardButton(text="Отмена", callback_data="admin_promos")]
        ]),
        parse_mode="HTML"
    )
    
    await state.set_state(PromoStates.waiting_for_discount)

@router.callback_query(lambda c: c.data.startswith("discount_"), PromoStates.waiting_for_discount)
async def process_discount_button(callback: types.CallbackQuery, state: FSMContext):
    # Получаем скидку из callback data
    discount = int(callback.data.split("_")[1])
    
    await process_discount_value(callback.message, state, discount)
    await callback.answer()

@router.message(PromoStates.waiting_for_discount)
async def process_discount_message(message: types.Message, state: FSMContext):
    try:
        discount = float(message.text.strip().replace(',', '.'))
        
        if discount <= 0 or discount > 100:
            await message.answer("❌ Скидка должна быть от 1 до 100%. Попробуйте снова.")
            return
        
        await process_discount_value(message, state, discount)
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число от 1 до 100. Попробуйте снова.")

async def process_discount_value(message, state, discount):
    # Сохраняем размер скидки
    await state.update_data(discount=discount)
    
    # Предлагаем варианты срока действия
    await message.answer(
        f"Скидка: {discount}%\n\n"
        f"Выберите срок действия промокода:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="1 день", callback_data="expiration_1")],
            [types.InlineKeyboardButton(text="1 неделя", callback_data="expiration_7")],
            [types.InlineKeyboardButton(text="1 месяц", callback_data="expiration_30")],
            [types.InlineKeyboardButton(text="3 месяца", callback_data="expiration_90")],
            [types.InlineKeyboardButton(text="Бессрочно", callback_data="expiration_0")],
            [types.InlineKeyboardButton(text="Отмена", callback_data="admin_promos")]
        ])
    )
    
    await state.set_state(PromoStates.waiting_for_expiration)

@router.callback_query(lambda c: c.data.startswith("expiration_"), PromoStates.waiting_for_expiration)
async def process_expiration(callback: types.CallbackQuery, state: FSMContext):
    # Получаем срок действия в днях
    days = int(callback.data.split("_")[1])
    
    # Рассчитываем дату истечения срока действия
    if days > 0:
        expiration_date = datetime.now() + timedelta(days=days)
        expiration_str = expiration_date.strftime("%d.%m.%Y %H:%M")
    else:
        expiration_date = None
        expiration_str = "Бессрочно"
    
    # Сохраняем дату истечения срока
    await state.update_data(expiration_date=expiration_date)
    
    # Запрашиваем лимит использований
    await callback.message.edit_text(
        f"Срок действия: {expiration_str}\n\n"
        f"Укажите лимит использования промокода (сколько раз можно использовать):",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="1 раз", callback_data="limit_1")],
            [types.InlineKeyboardButton(text="5 раз", callback_data="limit_5")],
            [types.InlineKeyboardButton(text="10 раз", callback_data="limit_10")],
            [types.InlineKeyboardButton(text="100 раз", callback_data="limit_100")],
            [types.InlineKeyboardButton(text="Без ограничений", callback_data="limit_0")],
            [types.InlineKeyboardButton(text="Отмена", callback_data="admin_promos")]
        ])
    )
    
    await state.set_state(PromoStates.waiting_for_limit)
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("limit_"), PromoStates.waiting_for_limit)
async def process_limit(callback: types.CallbackQuery, state: FSMContext):
    # Получаем лимит использований
    limit = int(callback.data.split("_")[1])
    
    await process_limit_value(callback.message, state, limit)
    await callback.answer()

@router.message(PromoStates.waiting_for_limit)
async def process_limit_message(message: types.Message, state: FSMContext):
    try:
        limit = int(message.text.strip())
        
        if limit < 0:
            await message.answer("❌ Лимит не может быть отрицательным. Попробуйте снова.")
            return
        
        await process_limit_value(message, state, limit)
    except ValueError:
        await message.answer("❌ Пожалуйста, введите целое число. Попробуйте снова.")

async def process_limit_value(message, state, limit):
    # Сохраняем лимит использований
    await state.update_data(usage_limit=limit if limit > 0 else None)
    
    # Получаем все сохраненные данные для подтверждения
    user_data = await state.get_data()
    promo_code = user_data.get("promo_code")
    discount = user_data.get("discount")
    expiration_date = user_data.get("expiration_date")
    usage_limit = user_data.get("usage_limit")
    
    # Форматируем данные для отображения
    expiration_str = expiration_date.strftime("%d.%m.%Y %H:%M") if expiration_date else "Бессрочно"
    limit_str = str(usage_limit) if usage_limit else "Без ограничений"
    
    # Запрашиваем подтверждение создания промокода
    await message.answer(
        f"📝 Создание промокода: подтверждение\n\n"
        f"Код: <code>{promo_code}</code>\n"
        f"Скидка: {discount}%\n"
        f"Срок действия: {expiration_str}\n"
        f"Лимит использований: {limit_str}\n\n"
        f"Все верно?",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="✅ Создать промокод", callback_data="confirm_create_promo")],
            [types.InlineKeyboardButton(text="❌ Отмена", callback_data="admin_promos")]
        ]),
        parse_mode="HTML"
    )
    
    await state.set_state(PromoStates.waiting_for_confirmation)

@router.callback_query(lambda c: c.data == "confirm_create_promo", PromoStates.waiting_for_confirmation)
async def create_promo(callback: types.CallbackQuery, state: FSMContext):
    # Получаем все сохраненные данные
    user_data = await state.get_data()
    promo_code = user_data.get("promo_code")
    discount = user_data.get("discount")
    expiration_date = user_data.get("expiration_date")
    usage_limit = user_data.get("usage_limit")
    
    try:
        # Создаем новый промокод в БД
        async with async_session() as session:
            # Проверяем, не существует ли уже такой промокод
            result = await session.execute(select(Promo).where(Promo.code == promo_code))
            existing_promo = result.scalar_one_or_none()
            
            if existing_promo:
                await callback.message.edit_text(
                    f"❌ Промокод <code>{promo_code}</code> уже существует. Операция отменена.",
                    parse_mode="HTML"
                )
                await state.clear()
                await callback.answer()
                return
            
            # Создаем новый промокод
            new_promo = Promo(
                code=promo_code,
                discount=Decimal(str(discount)),
                expiration_date=expiration_date,
                usage_limit=usage_limit,
                used_count=0,
                is_active=True
            )
            
            session.add(new_promo)
            await session.commit()
            
            # Подтверждаем создание промокода
            await callback.message.edit_text(
                f"✅ Промокод <code>{promo_code}</code> успешно создан!\n\n"
                f"Скидка: {discount}%\n"
                f"Срок действия: {expiration_date.strftime('%d.%m.%Y %H:%M') if expiration_date else 'Бессрочно'}\n"
                f"Лимит использований: {usage_limit if usage_limit else 'Без ограничений'}",
                reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(text="К списку промокодов", callback_data="admin_promos")],
                    [types.InlineKeyboardButton(text="В главное меню", callback_data="admin_back")]
                ]),
                parse_mode="HTML"
            )
            
            logger.info(f"Администратор {callback.from_user.id} создал новый промокод: {promo_code}")
            
    except Exception as e:
        logger.error(f"Ошибка при создании промокода: {e}")
        await callback.message.edit_text(
            f"❌ Произошла ошибка при создании промокода: {e}",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="К списку промокодов", callback_data="admin_promos")],
                [types.InlineKeyboardButton(text="В главное меню", callback_data="admin_back")]
            ])
        )
    
    # Очищаем состояние
    await state.clear()
    await callback.answer()

# Обработчик для удаления промокода
@router.callback_query(lambda c: c.data.startswith("delete_promo_"))
async def delete_promo(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("У вас нет прав администратора", show_alert=True)
        return
    
    promo_id = int(callback.data.split("_")[2])
    
    try:
        async with async_session() as session:
            # Получаем промокод
            result = await session.execute(select(Promo).where(Promo.id == promo_id))
            promo = result.scalar_one_or_none()
            
            if not promo:
                await callback.answer("Промокод не найден", show_alert=True)
                return
            
            # Деактивируем промокод (не удаляем физически)
            promo.is_active = False
            await session.commit()
            
            await callback.answer(f"Промокод {promo.code} деактивирован", show_alert=True)
            
            # Обновляем список промокодов
            text, markup = await paginate_results(get_promos, 1, 5, format_promos)
            
            # Добавляем кнопку создания промокода
            if markup:
                markup.inline_keyboard.insert(0, [types.InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin_create_promo")])
            
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
            
    except Exception as e:
        logger.error(f"Ошибка при деактивации промокода {promo_id}: {e}")
        await callback.answer("Произошла ошибка при деактивации промокода", show_alert=True)

# Регистрация обработчиков
def register_admin_handlers(dp):
    """Регистрирует обработчики администратора"""
    dp.include_router(router)