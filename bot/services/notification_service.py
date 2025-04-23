import logging
import asyncio
from datetime import datetime, timedelta
from sqlalchemy import select
from aiogram import Bot
from bot.utils.db import async_session
from bot.models.client import Client
from bot.models.user import User

logger = logging.getLogger(__name__)

class NotificationService:
    """Сервис для отправки уведомлений об истечении подписки"""

    @staticmethod
    async def check_expiring_subscriptions(bot):
        """
        Проверяет подписки, срок действия которых истекает, и отправляет уведомления
        
        Args:
            bot: Экземпляр бота для отправки уведомлений
        """
        logger.info("Проверка истекающих подписок...")
        
        try:
            async with async_session() as session:
                # Получаем текущую дату и дату "завтра"
                now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                tomorrow = now + timedelta(days=1)
                today_end = now.replace(hour=23, minute=59, second=59)
                tomorrow_end = tomorrow.replace(hour=23, minute=59, second=59)
                
                # Находим клиентов, у которых срок действия истекает сегодня или завтра
                # и для которых не отправлялись уведомления
                query = select(Client).join(User).where(
                    (
                        # Подписка истекает сегодня
                        ((Client.expiry_time >= now) & (Client.expiry_time <= today_end)) |
                        # Подписка истекает завтра
                        ((Client.expiry_time >= tomorrow) & (Client.expiry_time <= tomorrow_end))
                    ) &
                    (Client.is_active == True) &
                    (Client.tg_notified == False)
                )
                
                result = await session.execute(query)
                clients = result.scalars().all()
                
                logger.info(f"Найдено {len(clients)} клиентов с истекающими подписками")
                
                for client in clients:
                    # Получаем пользователя
                    user = client.user
                    
                    if not user:
                        logger.warning(f"Пользователь не найден для клиента {client.id}")
                        continue
                    
                    # Определяем, когда истекает подписка
                    expiry_date = client.expiry_time.date()
                    today_date = now.date()
                    expires_today = expiry_date == today_date
                    
                    # Отправляем уведомление пользователю
                    sent = await NotificationService._send_notification(
                        bot, 
                        user.tg_id, 
                        client.expiry_time, 
                        expires_today
                    )
                    
                    if sent:
                        # Отмечаем, что уведомление отправлено
                        client.tg_notified = True
                        await session.commit()
                        
                        days_left = "сегодня" if expires_today else "завтра"
                        logger.info(f"Отправлено уведомление пользователю {user.tg_id} об истечении подписки {days_left}")
                
        except Exception as e:
            logger.error(f"Ошибка при проверке истекающих подписок: {e}")
    
    @staticmethod
    async def reset_notification_flags():
        """
        Сбрасывает флаги уведомлений для продленных подписок
        """
        try:
            logger.info("Сброс флагов уведомлений для продленных подписок...")
            
            async with async_session() as session:
                # Получаем текущую дату и дату через 3 дня
                now = datetime.now()
                future_date = now + timedelta(days=3)
                
                # Находим клиентов с флагом уведомления, но дата истечения более 3 дней
                # Это означает, что подписка была продлена после отправки уведомления
                query = select(Client).where(
                    (Client.expiry_time > future_date) &  # Подписка продлена (истекает не скоро)
                    (Client.tg_notified == True) &        # Уведомление было отправлено
                    (Client.is_active == True)            # Клиент активен
                )
                
                result = await session.execute(query)
                clients = result.scalars().all()
                
                logger.info(f"Найдено {len(clients)} клиентов с продленными подписками")
                
                for client in clients:
                    # Сбрасываем флаг уведомления
                    client.tg_notified = False
                
                if clients:
                    await session.commit()
                    logger.info(f"Сброшены флаги уведомлений для {len(clients)} клиентов")
                
        except Exception as e:
            logger.error(f"Ошибка при сбросе флагов уведомлений: {e}")
    
    @staticmethod
    async def _send_notification(bot: Bot, user_id: int, expiry_time: datetime, is_today: bool):
        """
        Отправляет уведомление пользователю
        
        Args:
            bot: Экземпляр бота
            user_id: Telegram ID пользователя
            expiry_time: Время окончания подписки
            is_today: True если подписка истекает сегодня, False если завтра
        """
        try:
            # Форматируем дату и время окончания
            formatted_date = expiry_time.strftime("%d.%m.%Y")
            
            # Формируем текст сообщения в зависимости от типа уведомления
            if is_today:
                message_text = (
                    f"⚠️ Уведомление о подписке\n\n"
                    f"Срок действия вашей подписки истекает сегодня - {formatted_date}.\n\n"
                    f"Для продления доступа выберите '💼 Подписка и оплата' в меню бота."
                )
            else:
                message_text = (
                    f"⚠️ Уведомление о подписке\n\n"
                    f"Срок действия вашей подписки истекает завтра - {formatted_date}.\n\n"
                    f"Для продления доступа выберите '💼 Подписка и оплата' в меню бота."
                )
            
            # Отправляем сообщение
            await bot.send_message(
                chat_id=user_id,
                text=message_text
            )
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления пользователю {user_id}: {e}")
            return False

    @staticmethod
    async def start_notification_checker(bot, check_interval=3600):
        """
        Запускает проверку истекающих подписок каждые check_interval секунд
        
        Args:
            bot: Экземпляр бота для отправки уведомлений
            check_interval: Интервал проверки в секундах (по умолчанию - 1 час)
        """
        logger.info(f"Запущена проверка истекающих подписок каждые {check_interval} секунд")
        
        while True:
            try:
                # Проверяем истекающие подписки
                await NotificationService.check_expiring_subscriptions(bot)
                
                # Сбрасываем флаги для продленных подписок
                await NotificationService.reset_notification_flags()
            except Exception as e:
                logger.error(f"Ошибка в цикле проверки истекающих подписок: {e}")
            
            # Ждем до следующей проверки
            await asyncio.sleep(check_interval) 