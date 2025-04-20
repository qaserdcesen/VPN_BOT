from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import re
import logging
from bot.services.payment_service import PaymentService
from bot.keyboards.subscription_kb import get_tariffs_info, get_tariffs_keyboard
from sqlalchemy import select
from bot.models.user import User
from bot.utils.db import async_session
from bot.services.payment_service import DEFAULT_EMAIL
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.services.promo_service import PromoService

router = Router()
logger = logging.getLogger(__name__)

class ContactState(StatesGroup):
    waiting_for_contact = State()
    tariff_selected = State()
    waiting_for_promo = State()  # Новое состояние для ввода промокода

# Обработчик для выбора тарифа
@router.callback_query(lambda c: c.data.startswith("tariff_"))
async def process_tariff_selection(callback: types.CallbackQuery, state: FSMContext):
    tariff_key = callback.data.replace("tariff_", "")
    
    # Проверим пользователя в базе и его email
    async with async_session() as session:
        user_query = await session.execute(
            select(User).where(User.tg_id == callback.from_user.id)
        )
        user = user_query.scalar_one_or_none()
        
        if not user:
            logger.info(f"Создаем пользователя {callback.from_user.id} в БД")
            user = User(
                tg_id=callback.from_user.id,
                username=callback.from_user.username or "none"
            )
            session.add(user)
            await session.commit()
            has_email = False
        else:
            has_email = bool(user.email)
    
    # Сохраняем выбранный тариф
    await state.update_data(selected_tariff=tariff_key)
    await state.set_state(ContactState.tariff_selected)
    
    # Если у пользователя уже есть email, спрашиваем, хочет ли он его использовать
    if has_email:
        await callback.message.edit_text(
            f"У вас уже есть сохраненный email: {user.email}\n\n"
            f"Хотите использовать его для чека или указать новый?",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text=f"Использовать {user.email}", callback_data="use_saved_email")],
                [types.InlineKeyboardButton(text="Указать новый email", callback_data="new_email")],
                [types.InlineKeyboardButton(text="Пропустить (без чека)", callback_data="skip_email")],
                [types.InlineKeyboardButton(text="Назад", callback_data="back_to_tariffs")],
            ])
        )
    else:
        # Если email нет, запрашиваем его
        await callback.message.edit_text(
            f"Для создания чека нам нужен ваш email.\n\n"
            f"Если вы не хотите получать чек, просто нажмите кнопку 'Пропустить'.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="Пропустить", callback_data="skip_email")],
                [types.InlineKeyboardButton(text="Назад", callback_data="back_to_tariffs")],
            ])
        )
        
        # Переходим в состояние ожидания контакта
        await state.set_state(ContactState.waiting_for_contact)
    
    await callback.answer()

# Обработчик для использования сохраненного email
@router.callback_query(F.data == "use_saved_email", ContactState.tariff_selected)
async def use_saved_email(callback: types.CallbackQuery, state: FSMContext):
    # Получаем пользователя и его email
    async with async_session() as session:
        user_query = await session.execute(
            select(User).where(User.tg_id == callback.from_user.id)
        )
        user = user_query.scalar_one_or_none()
        
        if not user or not user.email:
            # Если по какой-то причине email не найден
            await callback.message.edit_text(
                "❌ Произошла ошибка: email не найден. Пожалуйста, укажите новый email.",
                reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(text="Пропустить", callback_data="skip_email")],
                    [types.InlineKeyboardButton(text="Назад", callback_data="back_to_tariffs")],
                ])
            )
            await state.set_state(ContactState.waiting_for_contact)
            await callback.answer()
            return
        
        email = user.email
    
    # Спрашиваем о промокоде
    await ask_for_promo(callback, state, email)

# Обработчик для ввода промокода
@router.callback_query(F.data == "enter_promo")
async def request_promo(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Введите промокод или нажмите кнопку 'Пропустить':",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="Пропустить", callback_data="skip_promo")],
            [types.InlineKeyboardButton(text="Назад", callback_data="back_to_tariffs")],
        ])
    )
    
    # Переходим в состояние ожидания промокода
    await state.set_state(ContactState.waiting_for_promo)
    await callback.answer()

# Обработчик для пропуска промокода
@router.callback_query(F.data == "skip_promo")
async def skip_promo(callback: types.CallbackQuery, state: FSMContext):
    # Получаем данные из состояния
    user_data = await state.get_data()
    email = user_data.get("email")
    
    # Создаем платеж без промокода
    await create_payment_with_email(callback, state, email, None)

# Обработчик для обработки введенного промокода
@router.message(ContactState.waiting_for_promo)
async def process_promo(message: types.Message, state: FSMContext):
    promo_code = message.text.strip()
    
    # Получаем данные из состояния
    user_data = await state.get_data()
    email = user_data.get("email")
    user_id = message.from_user.id
    
    # Проверяем промокод
    is_valid, discount, promo = await PromoService.check_promo(promo_code, user_id)
    
    if is_valid:
        # Создаем платеж с промокодом
        await message.answer(
            f"✅ Промокод применен. Скидка: {discount}%",
        )
        await create_payment_with_email(message, state, email, promo_code)
    else:
        # Если промокод невалидный
        await message.answer(
            "❌ Недействительный промокод. Попробуйте другой или нажмите 'Пропустить'.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="Пропустить", callback_data="skip_promo")],
                [types.InlineKeyboardButton(text="Назад", callback_data="back_to_tariffs")],
            ])
        )

# Функция для запроса промокода
async def ask_for_promo(callback_or_message, state, email):
    is_callback = isinstance(callback_or_message, types.CallbackQuery)
    message = callback_or_message.message if is_callback else callback_or_message
    
    # Сохраняем email в состоянии
    await state.update_data(email=email)
    
    # Спрашиваем, хочет ли пользователь ввести промокод
    await message.edit_text(
        "Хотите использовать промокод для скидки?",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="Ввести промокод", callback_data="enter_promo")],
            [types.InlineKeyboardButton(text="Продолжить без промокода", callback_data="skip_promo")],
            [types.InlineKeyboardButton(text="Назад", callback_data="back_to_tariffs")],
        ])
    ) if is_callback else await message.answer(
        "Хотите использовать промокод для скидки?",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="Ввести промокод", callback_data="enter_promo")],
            [types.InlineKeyboardButton(text="Продолжить без промокода", callback_data="skip_promo")],
            [types.InlineKeyboardButton(text="Назад", callback_data="back_to_tariffs")],
        ])
    )
    
    if is_callback:
        await callback_or_message.answer()

# Обработчик для ввода нового email
@router.callback_query(F.data == "new_email", ContactState.tariff_selected)
async def request_new_email(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Пожалуйста, укажите ваш новый email для чека:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="Отмена", callback_data="back_to_tariffs")],
        ])
    )
    
    # Переходим в состояние ожидания контакта
    await state.set_state(ContactState.waiting_for_contact)
    await callback.answer()

# Обработчик для получения email
@router.message(ContactState.waiting_for_contact)
async def process_contact(message: types.Message, state: FSMContext):
    email = message.text.strip()
    
    # Проверка валидности email
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        await message.answer(
            "❌ Некорректный email. Пожалуйста, введите правильный email или нажмите 'Пропустить'.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="Пропустить", callback_data="skip_email")],
                [types.InlineKeyboardButton(text="Назад", callback_data="back_to_tariffs")],
            ])
        )
        return
    
    # Сохраняем email в базе данных
    async with async_session() as session:
        user_query = await session.execute(
            select(User).where(User.tg_id == message.from_user.id)
        )
        user = user_query.scalar_one_or_none()
        
        if user:
            # Обновляем email пользователя
            user.email = email
            await session.commit()
            logger.info(f"Email пользователя {message.from_user.id} обновлен: {email}")
        else:
            # Если пользователя нет - создаем нового с email
            user = User(
                tg_id=message.from_user.id,
                username=message.from_user.username or "none",
                email=email
            )
            session.add(user)
            await session.commit()
            logger.info(f"Создан пользователь {message.from_user.id} с email {email}")
    
    # Спрашиваем о промокоде
    await ask_for_promo(message, state, email)

# Обработчик для пропуска email (общий для обоих состояний)
@router.callback_query(F.data == "skip_email")
async def skip_email(callback: types.CallbackQuery, state: FSMContext):
    # Проверим, существует ли пользователь
    async with async_session() as session:
        user_query = await session.execute(
            select(User).where(User.tg_id == callback.from_user.id)
        )
        user = user_query.scalar_one_or_none()
        
        if not user:
            logger.info(f"Создаем пользователя {callback.from_user.id} в БД")
            user = User(
                tg_id=callback.from_user.id,
                username=callback.from_user.username or "none"
            )
            session.add(user)
            await session.commit()
    
    # Спрашиваем о промокоде
    await ask_for_promo(callback, state, DEFAULT_EMAIL)

# Обработчик для отмены платежа
@router.callback_query(lambda c: c.data.startswith("cancel_payment_"))
async def cancel_payment(callback: types.CallbackQuery):
    payment_id = callback.data.replace("cancel_payment_", "")
    
    try:
        success = await PaymentService.cancel_payment(payment_id)
        
        if success:
            # Показываем снова список тарифов
            await callback.message.edit_text(
                "❌ Платёж отменён\n\nВыберите тариф:",
                reply_markup=get_tariffs_keyboard()
            )
            logger.info(f"Платёж {payment_id} отменен пользователем {callback.from_user.id}")
        else:
            await callback.answer("Ошибка при отмене платежа", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при отмене платежа {payment_id}: {e}")
        await callback.answer("Произошла ошибка, попробуйте позже", show_alert=True)

# Обработчик для возврата к выбору тарифов
@router.callback_query(F.data == "back_to_tariffs")
async def back_to_tariffs(callback: types.CallbackQuery, state: FSMContext):
    # Сбрасываем состояние
    await state.clear()
    
    # Возвращаемся к выбору тарифов
    await callback.message.edit_text(
        get_tariffs_info(),
        reply_markup=get_tariffs_keyboard()
    )
    await callback.answer()

# Обработчик для тестовой оплаты
@router.callback_query(lambda c: c.data.startswith("test_success_"))
async def process_test_success(callback: types.CallbackQuery):
    payment_id = callback.data.replace("test_success_", "")
    
    try:
        # Показываем пользователю временное сообщение о проверке
        await callback.message.edit_text(
            "⏳ Обрабатываем тестовую оплату...",
            reply_markup=None
        )
        
        # Обрабатываем тестовый платеж
        success = await PaymentService.process_test_payment(payment_id)
        
        if success:
            # Показываем сообщение об успешной оплате
            await callback.message.edit_text(
                "✅ Тестовая оплата успешно выполнена!\n\n"
                "Ваш тариф активирован.",
                reply_markup=None
            )
            logger.info(f"Тестовый платеж {payment_id} успешно завершен пользователем {callback.from_user.id}")
        else:
            await callback.answer("Ошибка при обработке тестовой оплаты", show_alert=True)
            await callback.message.edit_text(
                "❌ Произошла ошибка при обработке платежа.\n\n"
                "Пожалуйста, попробуйте позже.",
                reply_markup=get_tariffs_keyboard()
            )
    except Exception as e:
        logger.error(f"Ошибка при обработке тестового платежа {payment_id}: {e}")
        await callback.answer("Произошла ошибка, попробуйте позже", show_alert=True)
    
    await callback.answer()

# Обработчик для возврата успешной оплаты YooKassa
@router.callback_query(lambda c: c.data.startswith("yookassa_success_"))
async def process_yookassa_success(callback: types.CallbackQuery):
    payment_id = callback.data.replace("yookassa_success_", "")
    
    try:
        success = await PaymentService.process_test_payment(payment_id)
        
        if success:
            # Показываем сообщение об успешной оплате
            await callback.message.edit_text(
                "✅ Оплата успешно выполнена!\n\n"
                "Ваш тариф активирован.",
                reply_markup=None
            )
            logger.info(f"Платеж YooKassa {payment_id} успешно завершен пользователем {callback.from_user.id}")
        else:
            await callback.answer("Ошибка при обработке оплаты", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при обработке платежа YooKassa {payment_id}: {e}")
        await callback.answer("Произошла ошибка, попробуйте позже", show_alert=True)
    
    await callback.answer()

# Функция для создания платежа с указанным email
async def create_payment_with_email(callback_or_message, state, email, promo_code=None):
    is_callback = isinstance(callback_or_message, types.CallbackQuery)
    message = callback_or_message.message if is_callback else callback_or_message
    user_id = callback_or_message.from_user.id
    
    # Получаем выбранный тариф
    user_data = await state.get_data()
    tariff_key = user_data.get("selected_tariff")
    
    # Сбрасываем состояние
    await state.clear()
    
    # Создаем платеж
    try:
        payment_id, payment_url, markup = await PaymentService.create_payment(
            user_id=user_id,
            tariff_key=tariff_key,
            contact=email,
            bot=callback_or_message.bot,
            promo_code=promo_code
        )
        
        if payment_id and payment_url and markup:
            text = (
                f"💳 Для оплаты нажмите кнопку 'Оплатить'.\n"
                f"После оплаты ваш тариф будет активирован автоматически."
            )
            
            if is_callback:
                await message.edit_text(text, reply_markup=markup)
            else:
                await message.answer(text, reply_markup=markup)
        else:
            text = "❌ Не удалось создать платеж. Пожалуйста, попробуйте позже."
            
            if is_callback:
                await message.edit_text(text)
            else:
                await message.answer(text)
    except ValueError as e:
        text = f"❌ Ошибка: {str(e)}"
        
        if is_callback:
            await message.edit_text(text)
        else:
            await message.answer(text)
    except Exception as e:
        logger.error(f"Ошибка при создании платежа: {e}")
        text = "❌ Произошла ошибка при обработке платежа. Пожалуйста, попробуйте позже."
        
        if is_callback:
            await message.edit_text(text)
        else:
            await message.answer(text)
    
    if is_callback:
        await callback_or_message.answer()

def register_payment_handlers(dp):
    """Регистрирует обработчики платежей"""
    dp.include_router(router) 