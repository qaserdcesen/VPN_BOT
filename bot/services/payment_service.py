import logging
from datetime import datetime, timedelta
import uuid
import asyncio
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.future import select
from bot.utils.db import async_session
from bot.models.payment import Payment as PaymentModel
from bot.models.user import User
from bot.models.plan import Plan
from bot.models.client import Client
from bot.config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, PAYMENT_RETURN_URL
from bot.keyboards.subscription_kb import TARIFFS
from bot.services.vpn_service import VPNService
from bot.services.promo_service import PromoService

# Настройка логирования
logger = logging.getLogger(__name__)

# Почта администратора по умолчанию
DEFAULT_EMAIL = "qaserd@gmail.com"

# Проверка доступности YooKassa
yookassa_available = False
yookassa_configured = False
TEST_MODE = False  # Для переключения на тестовый режим без YooKassa

try:
    import yookassa
    from yookassa import Configuration, Payment
    yookassa_available = True
    logger.info("YooKassa модуль успешно импортирован")
except ImportError:
    logger.warning("YooKassa модуль не найден. Используем тестовый режим.")
    
    # Mock classes for YooKassa
    class Configuration:
        account_id = None
        secret_key = None
        
        @staticmethod
        def configure(*args, **kwargs):
            logger.error("YooKassa модуль недоступен. Невозможно настроить.")
    
    class Payment:
        @staticmethod
        def create(*args, **kwargs):
            logger.error("YooKassa модуль недоступен. Невозможно создать платеж.")
            return None
        
        @staticmethod
        def cancel(*args, **kwargs):
            logger.error("YooKassa модуль недоступен. Невозможно отменить платеж.")
            return None
        
        @staticmethod
        def find_one(*args, **kwargs):
            logger.error("YooKassa модуль недоступен. Невозможно найти платеж.")
            return None

# Инициализация YooKassa
try:
    if yookassa_available and YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY:
        logger.info(f"Инициализация YooKassa с ID магазина: {YOOKASSA_SHOP_ID}")
        logger.info(f"Секретный ключ: {YOOKASSA_SECRET_KEY[:5]}...{YOOKASSA_SECRET_KEY[-5:]}")
        Configuration.account_id = YOOKASSA_SHOP_ID
        Configuration.secret_key = YOOKASSA_SECRET_KEY
        yookassa_configured = True
        logger.info("YooKassa успешно инициализирована")
    else:
        yookassa_configured = False
        if not yookassa_available:
            logger.warning("YooKassa не инициализирована: модуль не найден")
        elif not (YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY):
            logger.warning("YooKassa не инициализирована: отсутствуют учетные данные")
        logger.warning(f"Будет использован тестовый режим оплаты: TEST_MODE={TEST_MODE}, yookassa_configured={yookassa_configured}")
except Exception as e:
    yookassa_configured = False
    logger.error(f"Ошибка инициализации YooKassa: {e}")
    logger.warning(f"Будет использован тестовый режим оплаты: TEST_MODE={TEST_MODE}, yookassa_configured={yookassa_configured}")

class PaymentService:
    """Сервис для работы с платежами YooKassa"""
    
    # Хранилище активных задач проверки платежей
    _payment_check_tasks = {}  # {payment_id: task}
    
    @staticmethod
    async def get_plan_by_tariff(tariff_key: str) -> Plan:
        """Получает план по ключу тарифа"""
        async with async_session() as session:
            tariff_info = TARIFFS.get(tariff_key)
            if not tariff_info:
                raise ValueError(f"Тариф {tariff_key} не найден")
            
            # Находим план в БД
            plan_query = await session.execute(
                select(Plan).where(Plan.title == tariff_info["name"])
            )
            plan = plan_query.scalar_one_or_none()
            
            if not plan:
                logger.warning(f"План для тарифа {tariff_key} ({tariff_info['name']}) не найден в БД")
                raise ValueError(f"План для тарифа {tariff_key} не найден в базе данных")
            
            return plan
    
    @staticmethod
    async def create_payment(user_id: int, tariff_key: str, contact: str = None, promo_code: str = None, bot=None):
        """
        Создает платеж в YooKassa и сохраняет в БД
        
        Args:
            user_id: Telegram ID пользователя
            tariff_key: Ключ тарифа (например, "base", "middle", "unlimited")
            contact: Email или телефон для чека (опционально)
            promo_code: Промокод для скидки (опционально)
            bot: Экземпляр бота для отправки уведомлений (опционально)
            
        Returns:
            tuple: (payment_id, payment_url, markup) или (None, None, None) при ошибке
        """
        try:
            # Получаем план и пользователя
            async with async_session() as session:
                user_query = await session.execute(
                    select(User).where(User.tg_id == user_id)
                )
                user = user_query.scalar_one_or_none()
                
                if not user:
                    logger.error(f"Пользователь {user_id} не найден в БД")
                    return None, None, None
                
                # Получаем план по тарифу
                plan = await PaymentService.get_plan_by_tariff(tariff_key)
                
                # Применяем промокод, если он указан
                discount_percent = 0
                original_price = plan.price
                
                if promo_code:
                    is_valid, discount_percent, promo = await PromoService.check_promo(promo_code, user.id)
                    if is_valid:
                        # Применяем скидку
                        plan.price = int(plan.price * (100 - discount_percent) / 100)
                        logger.info(f"Применен промокод {promo_code}: цена снижена с {original_price} до {plan.price} руб. (скидка {discount_percent}%)")
                    else:
                        logger.warning(f"Недействительный промокод {promo_code} для пользователя {user_id}")
                
                # Используем тестовый режим, если YooKassa не настроена или включен тестовый режим
                if TEST_MODE or not yookassa_configured:
                    # Создаем тестовый платеж
                    payment_id = f"test_payment_{uuid.uuid4()}"
                    payment_url = "https://example.com/test-payment"
                    
                    # Сохраняем информацию о платеже в БД
                    db_payment = PaymentModel(
                        user_id=user.id,
                        plan_id=plan.id,
                        status="pending",
                        amount=plan.price,
                        payment_id=payment_id
                    )
                    session.add(db_payment)
                    await session.commit()
                    
                    # Создаем клавиатуру с кнопками для оплаты
                    markup = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="✅ Тестовая оплата", callback_data=f"test_success_{payment_id}")],
                            [InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_payment_{payment_id}")],
                        ]
                    )
                    
                    # Если был применен промокод, отмечаем его как использованный
                    if promo_code and discount_percent > 0:
                        await PromoService.use_promo(promo_code, user.id)
                    
                    logger.info(f"Создан тестовый платеж {payment_id} для пользователя {user_id}, тариф: {tariff_key}" + 
                                (f", с промокодом {promo_code} (скидка {discount_percent}%)" if promo_code and discount_percent > 0 else ""))
                    
                    return payment_id, payment_url, markup
                
                # Подготовка данных для платежа
                tariff_info = TARIFFS.get(tariff_key)
                payment_data = {
                    "amount": {
                        "value": str(plan.price),
                        "currency": "RUB"
                    },
                    "confirmation": {
                        "type": "redirect",
                        "return_url": PAYMENT_RETURN_URL
                    },
                    "capture": True,
                    "description": f"Оплата тарифа {tariff_info['name']}" + 
                                   (f" со скидкой {discount_percent}%" if discount_percent > 0 else ""),
                    "metadata": {
                        "tg_user_id": user_id,
                        "tariff": tariff_key,
                        "db_user_id": user.id,
                        "plan_id": plan.id,
                        "original_price": original_price,
                        "discount_percent": discount_percent,
                        "promo_code": promo_code if promo_code and discount_percent > 0 else None
                    }
                }
                
                # Добавляем данные для чека, если указан контакт
                if contact:
                    if '@' in contact:
                        contact_type = "email"
                    else:
                        contact_type = "phone"
                        # Нормализация телефона (удаление символов кроме цифр)
                        contact = ''.join(filter(str.isdigit, contact))
                    
                    payment_data["receipt"] = {
                        "customer": {
                            contact_type: contact
                        },
                        "items": [
                            {
                                "description": f"Тариф {tariff_info['name']}",
                                "quantity": "1.00",
                                "amount": {
                                    "value": str(plan.price),
                                    "currency": "RUB"
                                },
                                "vat_code": "1",
                                "payment_mode": "full_prepayment",
                                "payment_subject": "service"
                            }
                        ]
                    }
                
                # Создаем платеж в YooKassa
                payment = Payment.create(payment_data)
                payment_id = payment.id
                payment_url = payment.confirmation.confirmation_url
                
                # Сохраняем информацию о платеже в БД
                db_payment = PaymentModel(
                    user_id=user.id,
                    plan_id=plan.id,
                    status="pending",
                    amount=plan.price,
                    payment_id=payment_id
                )
                session.add(db_payment)
                await session.commit()
                
                # Создаем клавиатуру с кнопками для оплаты
                markup = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="💳 Оплатить", url=payment_url)],
                        [InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_payment_{payment_id}")],
                    ]
                )
                
                # Если был применен промокод, отмечаем его как использованный
                if promo_code and discount_percent > 0:
                    await PromoService.use_promo(promo_code, user.id)
                
                logger.info(f"Создан платеж {payment_id} для пользователя {user_id}, тариф: {tariff_key}" + 
                            (f", с промокодом {promo_code} (скидка {discount_percent}%)" if promo_code and discount_percent > 0 else ""))
                
                return payment_id, payment_url, markup
                
        except Exception as e:
            logger.error(f"Ошибка при создании платежа для пользователя {user_id}: {e}")
            return None, None, None
    
    @staticmethod
    async def schedule_payment_checking(payment_id: str, bot):
        """
        Планирует проверки платежа с динамическим интервалом
        
        Args:
            payment_id: ID платежа в YooKassa
            bot: Экземпляр бота для отправки уведомлений
        """
        logger.info(f"Начинаем планирование проверок для платежа {payment_id}")
        
        # Если задача проверки уже существует, отменяем ее
        if payment_id in PaymentService._payment_check_tasks:
            if not PaymentService._payment_check_tasks[payment_id].done():
                PaymentService._payment_check_tasks[payment_id].cancel()
                logger.info(f"Отменена предыдущая задача проверки для платежа {payment_id}")
        
        # Запускаем новую задачу проверки
        task = asyncio.create_task(
            PaymentService._check_payment_with_schedule(payment_id, bot)
        )
        PaymentService._payment_check_tasks[payment_id] = task
        logger.info(f"Запланирована проверка платежа {payment_id}")
    
    @staticmethod
    async def _check_payment_with_schedule(payment_id: str, bot):
        """
        Проверяет платеж по расписанию: часто в начале, реже потом
        
        Args:
            payment_id: ID платежа
            bot: Экземпляр бота
        """
        # Расписание проверок: интервал в секундах и длительность этапа в секундах
        # (интервал_между_проверками, длительность_этапа)
        schedule = [
            (5, 60),    # Первую минуту - каждые 5 секунд
            (15, 120),  # Следующие 2 минуты - каждые 15 секунд
            (30, 180),  # Следующие 3 минуты - каждые 30 секунд
            (60, 300),  # Следующие 5 минут - раз в минуту
            (120, 600)  # Последние 10 минут - раз в 2 минуты
        ]
        
        start_time = datetime.now()
        elapsed_time = 0
        
        try:
            # Проверяем платеж согласно расписанию
            for interval, duration in schedule:
                # Проверяем, не превысили ли мы длительность текущего этапа
                while (datetime.now() - start_time).total_seconds() < elapsed_time + duration:
                    # Проверяем платеж
                    async with async_session() as session:
                        # Получаем платеж из БД
                        result = await session.execute(
                            select(PaymentModel).filter(PaymentModel.payment_id == payment_id)
                        )
                        payment = result.scalars().first()
                        
                        if not payment:
                            logger.error(f"Платеж {payment_id} не найден в базе данных")
                            return
                        
                        # Если платеж уже в финальном статусе, завершаем проверку
                        if payment.status in ["succeeded", "canceled"]:
                            logger.info(f"Платеж {payment_id} уже в финальном статусе: {payment.status}")
                            return
                        
                        # Получаем актуальный статус платежа из YooKassa
                        if not yookassa_configured and not TEST_MODE:
                            logger.warning("YooKassa не настроена, пропускаем проверку платежа")
                            return
                        
                        try:
                            # Для тестовых платежей просто продолжаем ждать
                            if payment_id.startswith("test_payment_"):
                                logger.info(f"Тестовый платеж {payment_id}, ждем действий пользователя")
                            else:
                                # Получаем информацию о платеже из YooKassa
                                payment_info = Payment.find_one(payment_id)
                                
                                if not payment_info:
                                    logger.warning(f"Платеж {payment_id} не найден в YooKassa")
                                    # Ждем указанный интервал перед следующей проверкой
                                    await asyncio.sleep(interval)
                                    continue
                                
                                logger.info(f"Платеж {payment_id}: Статус в YooKassa - {payment_info.status}, Статус в БД - {payment.status}")
                                
                                # Если статус платежа изменился, обновляем в БД
                                if payment_info.status != payment.status:
                                    old_status = payment.status
                                    payment.status = payment_info.status
                                    
                                    # Если платеж успешно оплачен, устанавливаем время оплаты и обновляем клиента
                                    if payment_info.status == "succeeded" and payment_info.paid:
                                        payment.paid_at = datetime.now()
                                        logger.info(f"Платеж {payment_id} успешно оплачен. Статус изменен с {old_status} на {payment_info.status}")
                                        
                                        # Получаем информацию о пользователе для уведомления
                                        user_query = await session.execute(
                                            select(User).where(User.id == payment.user_id)
                                        )
                                        user = user_query.scalar_one_or_none()
                                        
                                        if user:
                                            # Получаем информацию о плане
                                            plan_query = await session.execute(
                                                select(Plan).where(Plan.id == payment.plan_id)
                                            )
                                            plan = plan_query.scalar_one_or_none()
                                            
                                            # Обновляем клиента в соответствии с тарифом
                                            await PaymentService.update_client_after_payment(session, user.id, plan)
                                            
                                            plan_info = f"«{plan.title}»" if plan else ""
                                            
                                            # Отправляем уведомление пользователю
                                            try:
                                                await bot.send_message(
                                                    user.tg_id,
                                                    f"✅ Оплата успешно выполнена!\n\n"
                                                    f"Ваш тариф {plan_info} активирован.\n"
                                                    f"Сумма: {payment.amount} ₽"
                                                )
                                                logger.info(f"Отправлено уведомление пользователю {user.tg_id} об успешной оплате")
                                            except Exception as e:
                                                logger.error(f"Ошибка отправки уведомления пользователю {user.tg_id}: {e}")
                                        
                                        # Завершаем проверку, так как платеж успешно обработан
                                        await session.commit()
                                        return
                                    
                                    elif payment_info.status == "canceled":
                                        logger.info(f"Платеж {payment_id} отменен. Статус изменен с {old_status} на {payment_info.status}")
                                        await session.commit()
                                        return
                                    
                                    await session.commit()
                        
                        except Exception as e:
                            logger.error(f"Ошибка при проверке платежа {payment_id}: {e}")
                    
                    # Ждем указанный интервал перед следующей проверкой
                    await asyncio.sleep(interval)
                
                # Обновляем прошедшее время
                elapsed_time += duration
            
            logger.info(f"Прекращаем проверку платежа {payment_id} по истечении времени")
            
        except asyncio.CancelledError:
            logger.info(f"Проверка платежа {payment_id} отменена")
        except Exception as e:
            logger.error(f"Ошибка при проверке платежа {payment_id}: {e}")
        finally:
            # Удаляем задачу из словаря
            PaymentService._payment_check_tasks.pop(payment_id, None)
    
    @staticmethod
    async def cancel_payment(payment_id: str):
        """
        Отменяет платеж в YooKassa и обновляет статус в БД
        
        Args:
            payment_id: ID платежа в YooKassa
            
        Returns:
            bool: True если успешно, False при ошибке
        """
        try:
            # Для тестовых платежей просто обновляем статус в БД
            if payment_id.startswith("test_payment_"):
                async with async_session() as session:
                    payment_query = await session.execute(
                        select(PaymentModel).where(PaymentModel.payment_id == payment_id)
                    )
                    db_payment = payment_query.scalar_one_or_none()
                    
                    if db_payment:
                        db_payment.status = "canceled"
                        await session.commit()
                        logger.info(f"Тестовый платеж {payment_id} отменен")
                        return True
                    
                    return False
            
            # Для реальных платежей через YooKassa
            if yookassa_configured:
                try:
                    # Отмена платежа в YooKassa (может не работать для тестового магазина)
                    Payment.cancel(payment_id)
                except Exception as e:
                    logger.warning(f"Не удалось отменить платеж в YooKassa: {e}")
            
            # В любом случае обновляем статус в БД
            async with async_session() as session:
                payment_query = await session.execute(
                    select(PaymentModel).where(PaymentModel.payment_id == payment_id)
                )
                db_payment = payment_query.scalar_one_or_none()
                
                if db_payment:
                    db_payment.status = "canceled"
                    await session.commit()
                    logger.info(f"Платеж {payment_id} отменен в БД")
                    return True
                
                return False
                
        except Exception as e:
            logger.error(f"Ошибка при отмене платежа {payment_id}: {e}")
            return False
    
    @staticmethod
    async def process_test_payment(payment_id: str):
        """
        Обрабатывает тестовый платеж как успешный
        
        Args:
            payment_id: ID тестового платежа
            
        Returns:
            bool: True если успешно обработано
        """
        try:
            async with async_session() as session:
                payment_query = await session.execute(
                    select(PaymentModel).where(PaymentModel.payment_id == payment_id)
                )
                db_payment = payment_query.scalar_one_or_none()
                
                if not db_payment:
                    logger.warning(f"Платеж {payment_id} не найден в БД")
                    return False
                
                # Устанавливаем статус succeeded и время оплаты
                old_status = db_payment.status
                db_payment.status = "succeeded"
                db_payment.paid_at = datetime.now()
                
                # Получаем информацию о плане для обновления клиента
                plan_query = await session.execute(
                    select(Plan).where(Plan.id == db_payment.plan_id)
                )
                plan = plan_query.scalar_one_or_none()
                
                if plan:
                    # Обновляем клиента в соответствии с тарифом
                    await PaymentService.update_client_after_payment(session, db_payment.user_id, plan)
                else:
                    logger.warning(f"План не найден для платежа {payment_id}")
                
                await session.commit()
                
                logger.info(f"Тестовый платеж {payment_id} успешно обработан: статус изменен с {old_status} на succeeded")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка при обработке тестового платежа {payment_id}: {e}")
            return False
    
    @staticmethod
    async def process_notification(payment_data: dict):
        """
        Обрабатывает уведомление от YooKassa
        
        Args:
            payment_data: Данные уведомления от YooKassa
            
        Returns:
            bool: True если успешно обработано
        """
        try:
            # Получаем событие и объект платежа из уведомления
            event = payment_data.get("event")
            payment = payment_data.get("object")
            
            if not event or not payment:
                logger.warning("Некорректное уведомление: отсутствует event или object")
                return False
                
            payment_id = payment.get("id")
            status = payment.get("status")
            paid = payment.get("paid", False)
            
            logger.info(f"Обработка уведомления: event={event}, payment_id={payment_id}, status={status}, paid={paid}")
            
            # Проверяем, что это уведомление о платеже и что платеж не в статусе pending
            if "payment" not in event:
                logger.warning(f"Неподдерживаемый тип события: {event}")
                return False
                
            # Находим платеж в базе данных
            async with async_session() as session:
                payment_query = await session.execute(
                    select(PaymentModel).where(PaymentModel.payment_id == payment_id)
                )
                db_payment = payment_query.scalar_one_or_none()
                
                if not db_payment:
                    logger.warning(f"Платеж {payment_id} не найден в БД")
                    return False
                    
                # Обновляем статус платежа
                old_status = db_payment.status
                db_payment.status = status
                
                # Если платеж успешно завершен, устанавливаем время оплаты
                if status == "succeeded" and paid:
                    db_payment.paid_at = datetime.now()
                    logger.info(f"Платеж {payment_id} успешно оплачен. Статус изменен с {old_status} на {status}")
                    
                    # Получаем информацию о плане для обновления клиента
                    plan_query = await session.execute(
                        select(Plan).where(Plan.id == db_payment.plan_id)
                    )
                    plan = plan_query.scalar_one_or_none()
                    
                    if plan:
                        # Обновляем клиента в соответствии с тарифом
                        await PaymentService.update_client_after_payment(session, db_payment.user_id, plan)
                    else:
                        logger.warning(f"План не найден для платежа {payment_id}")
                    
                    # Дополнительно проверяем статус из API YooKassa для подтверждения
                    if yookassa_configured:
                        try:
                            payment_info = Payment.find_one(payment_id)
                            if payment_info and payment_info.status == "succeeded" and payment_info.paid:
                                logger.info(f"Подтверждено через API: платеж {payment_id} в статусе succeeded и оплачен")
                            else:
                                logger.warning(f"Несоответствие данных: webhook={status}/{paid}, API={payment_info.status if payment_info else 'None'}/{payment_info.paid if payment_info else 'None'}")
                        except Exception as e:
                            logger.warning(f"Ошибка при проверке платежа через API: {e}")
                else:
                    logger.info(f"Статус платежа {payment_id} изменен с {old_status} на {status}, paid={paid}")
                
                await session.commit()
                return True
                
        except Exception as e:
            logger.error(f"Ошибка при обработке уведомления от YooKassa: {e}")
            return False
            
    @staticmethod
    async def check_payments(bot):
        """
        Проверяет статусы платежей через API YooKassa и обновляет их в БД
        Этот метод больше не используется для регулярных проверок, так как
        мы используем проверки по запросу пользователя
        
        Args:
            bot: Экземпляр бота для отправки уведомлений
        """
        logger.info("Общая проверка платежей отключена. Используется проверка по запросу пользователя.")
        return
            
    @staticmethod
    async def update_client_after_payment(session, user_id, plan):
        """
        Обновляет информацию о клиенте после успешной оплаты
        
        Args:
            session: Активная сессия SQLAlchemy
            user_id: ID пользователя в БД
            plan: Объект плана с информацией о тарифе
        """
        try:
            # Находим клиента пользователя
            client_query = await session.execute(
                select(Client).where(Client.user_id == user_id)
            )
            client = client_query.scalar_one_or_none()
            
            if not client:
                logger.error(f"Клиент для пользователя {user_id} не найден в БД")
                return False
            
            logger.info(f"Найден клиент: uuid={client.uuid}, email={client.email}, "
                        f"текущий traffic={client.total_traffic}, limit_ip={client.limit_ip}, "
                        f"expiry_time={client.expiry_time}, is_active={client.is_active}")
            
            # Проверяем план
            if not plan:
                logger.error(f"План не передан для обновления клиента (user_id={user_id})")
                return False
                
            logger.info(f"План для обновления: title={plan.title}, "
                        f"traffic_limit={plan.traffic_limit}, duration_days={plan.duration_days}")
            
            # Определяем лимит IP в зависимости от тарифа
            limit_ip = 3  # Базовый лимит
            tariff_id = 0  # Начальный тариф ftw.none по умолчанию
            
            if "base" in plan.title.lower():
                tariff_id = 1
                limit_ip = 3
            elif "middle" in plan.title.lower():
                tariff_id = 2
                limit_ip = 3
            elif "unlimited" in plan.title.lower():
                tariff_id = 3
                limit_ip = 6
            
            # Обновляем информацию о клиенте
            client.total_traffic = plan.traffic_limit  # Устанавливаем лимит трафика из плана
            client.limit_ip = limit_ip  # Обновляем лимит IP
            client.is_active = True  # Активируем клиента
            client.tariff_id = tariff_id  # Сохраняем номер типа тарифа
            
            # Устанавливаем срок действия (30 дней от текущей даты)
            client.expiry_time = datetime.now() + timedelta(days=plan.duration_days)
            
            logger.info(f"Клиент (user_id={user_id}) обновлен в БД согласно тарифу {plan.title}: "
                        f"лимит трафика={plan.traffic_limit}, лимит IP={limit_ip}, "
                        f"номер тарифа={tariff_id}, срок действия до {client.expiry_time}")
            
            # Сохраняем изменения в БД
            await session.commit()
            
            # Проверка UUID и email перед обновлением на сервере
            if not client.uuid:
                logger.error(f"UUID клиента не определен для user_id={user_id}")
                return False
                
            if not client.email:
                logger.error(f"Email клиента не определен для user_id={user_id}")
                return False
            
            # Вызываем метод update_client_on_server для обновления клиента на сервере
            vpn_service = VPNService()
            expiry_timestamp = int(client.expiry_time.timestamp() * 1000) if client.expiry_time else 0
            
            logger.info(f"Отправляем запрос на обновление клиента на сервере VPN: "
                        f"user_uuid={client.uuid}, nickname={client.email}, "
                        f"traffic_limit={client.total_traffic}, limit_ip={client.limit_ip}, "
                        f"expiry_timestamp={expiry_timestamp}")
            
            # Обновляем клиента на сервере VPN
            update_result = await vpn_service.update_client_on_server(
                user_uuid=client.uuid,
                nickname=client.email,
                traffic_limit=client.total_traffic,
                limit_ip=client.limit_ip,
                expiry_time=expiry_timestamp
            )
            
            if update_result:
                logger.info(f"Клиент {client.email} ({client.uuid}) успешно обновлен на VPN сервере")
            else:
                logger.error(f"Не удалось обновить клиента {client.email} ({client.uuid}) на VPN сервере")
                # Попробуем еще раз с другими параметрами - обходной путь
                logger.info("Пробуем повторную попытку обновления клиента с другими параметрами...")
                update_result = await vpn_service.update_client_on_server(
                    user_uuid=client.uuid,
                    nickname=client.email,
                    traffic_limit=0 if client.total_traffic == 0 else client.total_traffic,
                    limit_ip=client.limit_ip,
                    expiry_time=expiry_timestamp
                )
                if update_result:
                    logger.info(f"Клиент {client.email} ({client.uuid}) успешно обновлен на VPN сервере при повторной попытке")
                else:
                    logger.error(f"Повторная попытка обновления клиента {client.email} ({client.uuid}) на VPN сервере также не удалась")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении клиента для user_id={user_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    @staticmethod
    async def start_payment_checker(bot, check_interval=30):
        """
        Запускает проверку платежей каждые check_interval секунд
        
        Args:
            bot: Экземпляр бота для отправки уведомлений
            check_interval: Интервал проверки в секундах
        """
        logger.info(f"Запущена проверка платежей каждые {check_interval} секунд")
        while True:
            try:
                # Получаем все незавершенные платежи из БД
                async with async_session() as session:
                    result = await session.execute(
                        select(PaymentModel).where(
                            PaymentModel.status.in_(["pending", "waiting_for_capture"])
                        )
                    )
                    payments = result.scalars().all()
                    
                    if payments:
                        logger.info(f"Найдено {len(payments)} незавершенных платежей")
                        
                        for payment in payments:
                            # Пропускаем тестовые платежи - ими пользователь управляет вручную
                            if payment.payment_id.startswith("test_payment_"):
                                continue
                                
                            # Получаем информацию о платеже из YooKassa
                            try:
                                if not yookassa_configured:
                                    logger.warning("YooKassa не настроена, пропускаем проверку платежа")
                                    continue
                                    
                                payment_info = Payment.find_one(payment.payment_id)
                                
                                if not payment_info:
                                    logger.warning(f"Платеж {payment.payment_id} не найден в YooKassa")
                                    continue
                                
                                logger.info(f"Платеж {payment.payment_id}: YooKassa статус={payment_info.status}, БД статус={payment.status}")
                                
                                # Если статус платежа изменился, обновляем в БД
                                if payment_info.status != payment.status:
                                    old_status = payment.status
                                    payment.status = payment_info.status
                                    
                                    # Если платеж успешно оплачен
                                    if payment_info.status == "succeeded" and payment_info.paid:
                                        payment.paid_at = datetime.now()
                                        logger.info(f"Платеж {payment.payment_id} успешно оплачен. Статус изменен с {old_status} на {payment_info.status}")
                                        
                                        # Получаем пользователя
                                        user_query = await session.execute(
                                            select(User).where(User.id == payment.user_id)
                                        )
                                        user = user_query.scalar_one_or_none()
                                        
                                        if user:
                                            # Получаем план
                                            plan_query = await session.execute(
                                                select(Plan).where(Plan.id == payment.plan_id)
                                            )
                                            plan = plan_query.scalar_one_or_none()
                                            
                                            # Обновляем клиента
                                            await PaymentService.update_client_after_payment(session, user.id, plan)
                                            
                                            # Отправляем уведомление пользователю
                                            plan_info = f"«{plan.title}»" if plan else ""
                                            try:
                                                await bot.send_message(
                                                    user.tg_id,
                                                    f"✅ Оплата успешно выполнена!\n\n"
                                                    f"Ваш тариф {plan_info} активирован.\n"
                                                    f"Сумма: {payment.amount} ₽"
                                                )
                                                logger.info(f"Отправлено уведомление пользователю {user.tg_id} об успешной оплате")
                                            except Exception as e:
                                                logger.error(f"Ошибка отправки уведомления пользователю {user.tg_id}: {e}")
                                    
                                    # Если платеж отменен
                                    elif payment_info.status == "canceled":
                                        logger.info(f"Платеж {payment.payment_id} отменен. Статус изменен с {old_status} на {payment_info.status}")
                                    
                                    # Сохраняем изменения
                                    await session.commit()
                            except Exception as e:
                                logger.error(f"Ошибка при проверке платежа {payment.payment_id}: {e}")
                    else:
                        logger.info("Нет незавершенных платежей")
            except Exception as e:
                logger.error(f"Ошибка при проверке платежей: {e}")
            
            # Ждем перед следующей проверкой
            await asyncio.sleep(check_interval) 