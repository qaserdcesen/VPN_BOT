import time
import datetime
from sqlalchemy.future import select
from sqlalchemy import update
from bot.utils.db import async_session
from bot.models.user import User

class BanService:
    def __init__(self, bot=None):
        self.cache = {}  # Временный кэш
        self.bot = bot  # Экземпляр бота для отправки уведомлений
    
    async def is_banned(self, user_id: int) -> tuple[bool, str, datetime.datetime]:
        """
        Проверяет, забанен ли пользователь, учитывая временный банОтлично! Добавляю функционал создания промокодов для администратора.
        Возвращает: (is_banned, reason, expiry_time)
        """
        # Проверяем кэш
        if user_id in self.cache:
            if time.time() - self.cache[user_id]["timestamp"] < 300:  # Кэш на 5 минут
                # Если был временный бан и срок истек
                if self.cache[user_id]["banned"] and self.cache[user_id].get("ban_until"):
                    if datetime.datetime.now() > self.cache[user_id]["ban_until"]:
                        # Разбаниваем пользователя, т.к. срок истек
                        await self.unban_user(user_id)
                        return False, "", None
                return (
                    self.cache[user_id]["banned"], 
                    self.cache[user_id].get("reason", ""), 
                    self.cache[user_id].get("ban_until")
                )
        
        # Проверяем БД
        async with async_session() as session:
            result = await session.execute(
                select(User.is_banned, User.ban_reason, User.banned_until)
                .where(User.tg_id == user_id)
            )
            data = result.one_or_none()
            
            # Если пользователя нет, считаем, что он не забанен
            if data is None:
                return False, "", None
            
            is_banned, ban_reason, ban_until = data
            
            # Если бан временный и срок истек
            if is_banned and ban_until and ban_until < datetime.datetime.now():
                # Разбаниваем пользователя
                await self.unban_user(user_id)
                return False, "", None
        
        # Обновляем кэш
        self.cache[user_id] = {
            "banned": is_banned,
            "reason": ban_reason,
            "ban_until": ban_until,
            "timestamp": time.time()
        }
        
        return is_banned, ban_reason, ban_until
    
    async def ban_user(self, user_id: int, reason: str = "спам", hours: float = 24, notify: bool = True) -> bool:
        """Банит пользователя на указанное количество часов"""
        # Рассчитываем время окончания бана
        ban_until = datetime.datetime.now() + datetime.timedelta(hours=hours) if hours > 0 else None
        
        async with async_session() as session:
            # Проверяем существование пользователя
            result = await session.execute(
                select(User).where(User.tg_id == user_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                # Пользователя нет, создаем и сразу баним
                user = User(
                    tg_id=user_id,
                    username="banned_user",
                    is_banned=True,
                    ban_reason=reason,
                    banned_at=datetime.datetime.now(),
                    banned_until=ban_until
                )
                session.add(user)
            else:
                # Обновляем существующего пользователя
                await session.execute(
                    update(User)
                    .where(User.tg_id == user_id)
                    .values(
                        is_banned=True, 
                        ban_reason=reason, 
                        banned_at=datetime.datetime.now(),
                        banned_until=ban_until
                    )
                )
            
            await session.commit()
            
            # Обновляем кэш
            self.cache[user_id] = {
                "banned": True,
                "reason": reason,
                "ban_until": ban_until,
                "timestamp": time.time()
            }
            
            # Уведомляем пользователя, если необходимо
            if notify and self.bot:
                ban_duration = int(hours * 60) if hours > 0 else 0
                ban_period = f"на {ban_duration} минут" if ban_duration > 0 else "бессрочно"
                try:
                    await self.bot.send_message(
                        user_id,
                        f"⚠️ Вы были заблокированы в боте {ban_period}.\n"
                        f"Причина: {reason}\n"
                        f"Доступ будет восстановлен: {'автоматически по истечении срока' if hours > 0 else 'после рассмотрения администрацией'}"
                    )
                except Exception as e:
                    # Игнорируем ошибки при отправке сообщения (пользователь мог заблокировать бота)
                    pass
            
            return True
    
    async def unban_user(self, user_id: int) -> bool:
        """Снимает бан с пользователя"""
        async with async_session() as session:
            # Проверяем существование пользователя
            result = await session.execute(
                select(User).where(User.tg_id == user_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                return False
            
            # Снимаем бан
            await session.execute(
                update(User)
                .where(User.tg_id == user_id)
                .values(is_banned=False, ban_reason=None, banned_until=None)
            )
            
            await session.commit()
            
            # Обновляем кэш
            if user_id in self.cache:
                self.cache[user_id] = {
                    "banned": False,
                    "reason": "",
                    "ban_until": None,
                    "timestamp": time.time()
                }
            
            return True 