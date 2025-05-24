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
            # Получаем текущую дату и дату "завтра"
            now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            yesterday = now - timedelta(days=1)
            tomorrow = now + timedelta(days=1)
            today_end = now.replace(hour=23, minute=59, second=59)
            tomorrow_end = tomorrow.replace(hour=23, minute=59, second=59)
            
            async with async_session() as session:
                # Находим клиентов, у которых срок действия истекает сегодня, завтра или уже истек
                # и для которых не отправлялись уведомления
                query = select(Client, User).join(User).where(
                    (
                        # Подписка уже истекла (вчера)
                        ((Client.expiry_time >= yesterday) & (Client.expiry_time < now)) |
                        # Подписка истекает сегодня
                        ((Client.expiry_time >= now) & (Client.expiry_time <= today_end)) |
                        # Подписка истекает завтра
                        ((Client.expiry_time >= tomorrow) & (Client.expiry_time <= tomorrow_end))
                    ) &
                    (Client.is_active == True) &
                    (Client.tg_notified == False)
                )
                
                result = await session.execute(query)
                clients_with_users = result.all()
                
                logger.info(f"Найдено {len(clients_with_users)} клиентов с истекающими подписками")
                
                for client, user in clients_with_users:
                    try:
                        # Определяем, когда истекает подписка
                        expiry_date = client.expiry_time.date()
                        today_date = now.date()
                        yesterday_date = yesterday.date()
                        
                        if expiry_date == yesterday_date:
                            expires_status = "expired"
                        elif expiry_date == today_date:
                            expires_status = "today"
                        else:
                            expires_status = "tomorrow"
                        
                        # Отправляем уведомление пользователю
                        sent = await NotificationService._send_notification(
                            bot, 
                            user.tg_id, 
                            client.expiry_time, 
                            expires_status
                        )
                        
                        if sent:
                            # Отмечаем, что уведомление отправлено
                            client.tg_notified = True
                            await session.commit()
                            
                            status_text = {
                                "expired": "вчера",
                                "today": "сегодня",
                                "tomorrow": "завтра"
                            }[expires_status]
                            
                            logger.info(f"Отправлено уведомление пользователю {user.tg_id} об истечении подписки {status_text}")
                    except Exception as e:
                        logger.error(f"Ошибка при обработке клиента {client.id}: {e}")
                        await session.rollback()
                        continue
                
        except Exception as e:
            logger.error(f"Ошибка при проверке истекающих подписок: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    @staticmethod
    async def reset_notification_flags():
        """
        Сбрасывает флаги уведомлений для продленных подписок
        """
        try:
            logger.info("Сброс флагов уведомлений для продленных подписок...")
            
            # Получаем текущую дату и дату через 3 дня
            now = datetime.now()
            future_date = now + timedelta(days=3)
            
            async with async_session() as session:
                try:
                    # Находим клиентов с флагом уведомления, но дата истечения более 3 дней
                    query = select(Client).where(
                        (Client.expiry_time > future_date) &  # Подписка продлена (истекает не скоро)
                        (Client.tg_notified == True) &        # Уведомление было отправлено
                        (Client.is_active == True)            # Клиент активен
                    )
                    
                    result = await session.execute(query)
                    clients = result.scalars().all()
                    
                    logger.info(f"Найдено {len(clients)} клиентов с продленными подписками")
                    
                    if clients:
                        for client in clients:
                            client.tg_notified = False
                        
                        await session.commit()
                        logger.info(f"Сброшены флаги уведомлений для {len(clients)} клиентов")
                except Exception as e:
                    logger.error(f"Ошибка при сбросе флагов уведомлений: {e}")
                    await session.rollback()
                    raise
                
        except Exception as e:
            logger.error(f"Ошибка при сбросе флагов уведомлений: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    @staticmethod
    async def _send_notification(bot: Bot, user_id: int, expiry_time: datetime, expires_status: str):
        """
        Отправляет уведомление пользователю
        
        Args:
            bot: Экземпляр бота
            user_id: Telegram ID пользователя
            expiry_time: Время окончания подписки
            expires_status: Статус истечения ("expired", "today", "tomorrow")
        """
        try:
            # Форматируем дату и время окончания
            formatted_date = expiry_time.strftime("%d.%m.%Y")
            
            # Формируем текст сообщения в зависимости от типа уведомления
            if expires_status == "expired":
                message_text = (
                    f"⚠️ Уведомление о подписке\n\n"
                    f"Срок действия вашей подписки истек вчера - {formatted_date}.\n\n"
                )
            elif expires_status == "today":
                message_text = (
                    f"⚠️ Уведомление о подписке\n\n"
                    f"Срок действия вашей подписки истекает сегодня - {formatted_date}.\n\n"
                )
            else:  # tomorrow
                message_text = (
                    f"⚠️ Уведомление о подписке\n\n"
                    f"Срок действия вашей подписки истекает завтра - {formatted_date}.\n\n"
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
                import traceback
                logger.error(traceback.format_exc())
            
            # Ждем до следующей проверки
            await asyncio.sleep(check_interval) 