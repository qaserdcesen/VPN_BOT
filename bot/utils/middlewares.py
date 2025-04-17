from typing import Dict, Any, Callable, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
import time
import asyncio
from collections import defaultdict
import datetime
import logging

logger = logging.getLogger(__name__)

class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate_limit=2.0):
        self.rate_limit = rate_limit  # лимит в секундах
        self.user_rates = defaultdict(lambda: {"last_time": 0, "count": 0})
        super().__init__()
        # Не создаем задачу сразу, запустим её в main
        self.cleanup_task = None
    
    async def start_cleanup(self):
        """Запускает задачу очистки"""
        self.cleanup_task = asyncio.create_task(self.periodic_cleanup())
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        # Получаем user_id
        user_id = event.from_user.id
        
        # Текущее время
        now = time.time()
        
        # Получаем данные пользователя
        user_data = self.user_rates[user_id]
        
        # Прошедшее время с последнего запроса
        elapsed = now - user_data["last_time"]
        
        # Сбрасываем счетчик, если прошло достаточно времени
        if elapsed > self.rate_limit:
            user_data["count"] = 0
        
        # Увеличиваем счетчик
        user_data["count"] += 1
        user_data["last_time"] = now
        
        # Если превышен лимит, игнорируем запрос
        if user_data["count"] > 5 and elapsed < self.rate_limit:
            if isinstance(event, CallbackQuery):
                await event.answer("Слишком много запросов. Пожалуйста, подождите...", show_alert=True)
                return None
            else:
                await event.answer("⚠️ Пожалуйста, не отправляйте сообщения так часто!")
                return None
        
        # Иначе пропускаем запрос
        return await handler(event, data)
    
    async def periodic_cleanup(self):
        """Периодически очищает устаревшие записи"""
        while True:
            await asyncio.sleep(3600)  # Каждый час
            now = time.time()
            # Удаляем записи для пользователей, неактивных более 1 часа
            old_users = [user_id for user_id, data in self.user_rates.items() 
                        if now - data["last_time"] > 3600]
            for user_id in old_users:
                del self.user_rates[user_id]

class BanCheckMiddleware(BaseMiddleware):
    def __init__(self, ban_service):
        self.ban_service = ban_service
        super().__init__()
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        # Проверяем, забанен ли пользователь
        user_id = event.from_user.id
        
        try:
            # Пробуем получить расширенную информацию о бане
            ban_result = await self.ban_service.is_banned(user_id)
            
            # Если результат - кортеж, распаковываем его
            if isinstance(ban_result, tuple) and len(ban_result) == 3:
                is_banned, reason, ban_until = ban_result
            else:
                # Если вернулся только флаг (старая версия)
                is_banned = ban_result
                reason = "нарушение правил"
                ban_until = None
                
            if is_banned:
                # Формируем сообщение о бане
                ban_msg = "❌ Вы временно заблокированы в боте"
                if reason:
                    ban_msg += f" из-за: {reason}"
                
                if ban_until:
                    # Форматируем оставшееся время
                    time_left = ban_until - datetime.datetime.now()
                    minutes_left = max(1, int(time_left.total_seconds() / 60))
                    ban_msg += f"\nБлокировка будет снята через {minutes_left} мин."
                
                # Если пользователь забанен, игнорируем запрос
                if isinstance(event, CallbackQuery):
                    await event.answer(ban_msg, show_alert=True)
                    return None
                else:
                    await event.answer(ban_msg)
                    return None
        except Exception as e:
            # В случае ошибки, пропускаем запрос
            logger.error(f"Ошибка при проверке бана: {e}")
            
        # Если не забанен, пропускаем запрос
        return await handler(event, data)

class AntiFloodMiddleware(BaseMiddleware):
    def __init__(self, ban_service):
        self.ban_service = ban_service
        self.message_history = defaultdict(list)
        self.callback_history = defaultdict(list)  # Отслеживание callback_query
        super().__init__()
    
    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        # Получаем user_id
        user_id = event.from_user.id
        now = time.time()
        
        # Обработка для текстовых сообщений
        if isinstance(event, Message) and event.text:
            # Очищаем старые сообщения (старше 10 секунд)
            self.message_history[user_id] = [
                msg for msg in self.message_history[user_id] 
                if now - msg["time"] < 10
            ]
            
            # Добавляем текущее сообщение
            self.message_history[user_id].append({
                "text": event.text,
                "time": now
            })
            
            # Проверяем на флуд
            if len(self.message_history[user_id]) >= 5:
                texts = [msg["text"] for msg in self.message_history[user_id]]
                if texts.count(event.text) >= 5:
                    await event.answer("⚠️ Обнаружен флуд! Пожалуйста, не отправляйте одинаковые сообщения.")
                    
                    # Баним на 1 минуту за флуд с уведомлением
                    await self.ban_service.ban_user(
                        user_id, 
                        "временная блокировка за отправку одинаковых сообщений", 
                        hours=1/60,  # 1 минута (1/60 часа)
                        notify=True
                    )
                    return None
        
        # Обработка для callback_query (кнопок)
        elif isinstance(event, CallbackQuery):
            # Очищаем старые callback (старше 5 секунд)
            self.callback_history[user_id] = [
                cb for cb in self.callback_history[user_id]
                if now - cb["time"] < 5
            ]
            
            # Добавляем текущий callback
            self.callback_history[user_id].append({
                "data": event.data,
                "time": now
            })
            
            # Проверяем на флуд кнопок (более 8 нажатий за 5 секунд)
            if len(self.callback_history[user_id]) >= 8:
                await event.answer("⚠️ Обнаружено слишком много нажатий кнопок! Пожалуйста, не спамьте.", show_alert=True)
                
                # Баним на 1 минуту за флуд с уведомлением
                await self.ban_service.ban_user(
                    user_id, 
                    "временная блокировка за слишком частое нажатие кнопок", 
                    hours=1/60,  # 1 минута
                    notify=True
                )
                return None
        
        return await handler(event, data) 