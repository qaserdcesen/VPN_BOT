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

router = Router()
logger = logging.getLogger(__name__)

# Состояния FSM для рассылки
class BroadcastStates(StatesGroup):
    waiting_for_message = State()  # Ожидание сообщения для рассылки

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
    for promo in promos:
        status = "✅ Активен" if promo.is_active else "❌ Неактивен"
        expiry = promo.expiration_date.strftime('%d.%m.%Y %H:%M') if promo.expiration_date else "Нет срока"
        
        result.append(
            f"🎟 <b>ID:</b> {promo.id} | <b>Код:</b> <code>{promo.code}</code>\n"
            f"💹 Скидка: {float(promo.discount)}%\n"
            f"📊 Использован: {promo.used_count}/{promo.usage_limit or '∞'}\n"
            f"📅 Действует до: {expiry}\n"
            f"Status: {status}\n"
        )
    
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
    
    text, markup = await paginate_results(get_promos, 1, 5, format_promos)
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

# Регистрация обработчиков
def register_admin_handlers(dp):
    """Регистрирует обработчики администратора"""
    dp.include_router(router)