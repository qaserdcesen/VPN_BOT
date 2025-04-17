import logging
from datetime import datetime
import uuid
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.future import select
from bot.utils.db import async_session
from bot.models.payment import Payment as PaymentModel
from bot.models.user import User
from bot.models.plan import Plan
from bot.config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, PAYMENT_RETURN_URL
from bot.keyboards.subscription_kb import TARIFFS

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
    logger.info("YooKassa module imported successfully")
except ImportError:
    logger.warning("YooKassa module not found. Using mock implementation.")
    
    # Mock classes for YooKassa
    class Configuration:
        account_id = None
        secret_key = None
        
        @staticmethod
        def configure(*args, **kwargs):
            logger.error("YooKassa module not available. Cannot configure.")
    
    class Payment:
        @staticmethod
        def create(*args, **kwargs):
            logger.error("YooKassa module not available. Cannot create payment.")
            return None
        
        @staticmethod
        def cancel(*args, **kwargs):
            logger.error("YooKassa module not available. Cannot cancel payment.")
            return None
        
        @staticmethod
        def find_one(*args, **kwargs):
            logger.error("YooKassa module not available. Cannot find payment.")
            return None

# Инициализация YooKassa
try:
    if yookassa_available and YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY:
        logger.info(f"Инициализация YooKassa с ID магазина: {YOOKASSA_SHOP_ID}")
        Configuration.account_id = YOOKASSA_SHOP_ID
        Configuration.secret_key = YOOKASSA_SECRET_KEY
        logger.info("YooKassa initialized successfully")
        yookassa_configured = True
    else:
        yookassa_configured = False
        if not yookassa_available:
            logger.warning("YooKassa не инициализирована: модуль не найден")
        elif not (YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY):
            logger.warning("YooKassa не инициализирована: отсутствуют учетные данные")
except Exception as e:
    yookassa_configured = False
    logger.error(f"YooKassa initialization error: {e}")

class PaymentService:
    """Сервис для работы с платежами YooKassa"""
    
    @staticmethod
    async def get_plan_by_tariff(tariff_key: str) -> Plan:
        """Получает план по ключу тарифа"""
        async with async_session() as session:
            tariff_info = TARIFFS.get(tariff_key)
            if not tariff_info:
                raise ValueError(f"Тариф {tariff_key} не найден")
            
            # Находим или создаем план в БД
            plan_query = await session.execute(
                select(Plan).where(Plan.title == tariff_info["name"])
            )
            plan = plan_query.scalar_one_or_none()
            
            if not plan:
                # Если план не существует, создаем его
                traffic_limit = 0
                if "ГБ" in tariff_info["traffic"]:
                    # Например "25ГБ/месяц" -> 25 * 1024*1024*1024
                    gb_value = int(tariff_info["traffic"].split("ГБ")[0])
                    traffic_limit = gb_value * 1024 * 1024 * 1024
                
                plan = Plan(
                    title=tariff_info["name"],
                    traffic_limit=traffic_limit if traffic_limit > 0 else -1,  # -1 для безлимита
                    duration_days=30,  # 30 дней по умолчанию
                    price=tariff_info["price"]
                )
                session.add(plan)
                await session.commit()
                await session.refresh(plan)
            
            return plan
    
    @staticmethod
    async def create_payment(user_id: int, tariff_key: str, contact: str = None):
        """
        Создает платеж в YooKassa и сохраняет в БД
        
        Args:
            user_id: Telegram ID пользователя
            tariff_key: Ключ тарифа (например, "base", "middle", "unlimited")
            contact: Email или телефон для чека (опционально)
            
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
                    
                    logger.info(f"Создан тестовый платеж {payment_id} для пользователя {user_id}, тариф: {tariff_key}")
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
                    "description": f"Оплата тарифа {tariff_info['name']}",
                    "metadata": {
                        "tg_user_id": user_id,
                        "tariff": tariff_key,
                        "db_user_id": user.id,
                        "plan_id": plan.id
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
                
                logger.info(f"Создан платеж {payment_id} для пользователя {user_id}, тариф: {tariff_key}")
                return payment_id, payment_url, markup
                
        except Exception as e:
            logger.error(f"Ошибка при создании платежа для пользователя {user_id}: {e}")
            return None, None, None
    
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
                
                db_payment.status = "succeeded"
                db_payment.paid_at = datetime.now()
                await session.commit()
                
                logger.info(f"Платеж {payment_id} успешно обработан")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка при обработке платежа {payment_id}: {e}")
            return False 