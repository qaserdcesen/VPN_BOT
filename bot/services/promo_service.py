import logging
from datetime import datetime
from sqlalchemy.future import select
from bot.utils.db import async_session
from bot.models.promo import Promo

# Настройка логирования
logger = logging.getLogger(__name__)

class PromoService:
    """Сервис для работы с промокодами"""
    
    @staticmethod
    async def check_promo(code: str, user_id: int = None):
        """
        Проверяет действительность промокода
        
        Args:
            code: Код промокода для проверки
            user_id: ID пользователя, который использует промокод
            
        Returns:
            tuple: (is_valid, discount, promo) - действителен ли промокод, размер скидки, объект промокода
        """
        try:
            async with async_session() as session:
                # Ищем промокод в базе
                query = await session.execute(
                    select(Promo).where(Promo.code == code)
                )
                promo = query.scalar_one_or_none()
                
                if not promo:
                    logger.info(f"Промокод {code} не найден")
                    return False, 0, None
                
                # Проверяем, активен ли промокод
                if not promo.is_active:
                    logger.info(f"Промокод {code} не активен")
                    return False, 0, promo
                
                # Проверяем срок действия
                current_time = datetime.now()
                if promo.expiration_date and promo.expiration_date < current_time:
                    logger.info(f"Срок действия промокода {code} истек {promo.expiration_date}")
                    return False, 0, promo
                
                # Проверяем лимит использования
                if promo.usage_limit and promo.used_count >= promo.usage_limit:
                    logger.info(f"Превышен лимит использования промокода {code}: {promo.used_count}/{promo.usage_limit}")
                    return False, 0, promo
                
                # Проверяем, привязан ли промокод к определенному пользователю
                if promo.user_id and promo.user_id != user_id:
                    logger.info(f"Промокод {code} привязан к другому пользователю {promo.user_id} (запрошен {user_id})")
                    return False, 0, promo
                
                # Промокод действителен
                discount = float(promo.discount)
                logger.info(f"Промокод {code} действителен, скидка: {discount}%")
                return True, discount, promo
                
        except Exception as e:
            logger.error(f"Ошибка при проверке промокода {code}: {e}")
            return False, 0, None
    
    @staticmethod
    async def use_promo(code: str, user_id: int):
        """
        Отмечает промокод как использованный
        
        Args:
            code: Код промокода
            user_id: ID пользователя, который использует промокод
            
        Returns:
            bool: True если успешно использован, False при ошибке
        """
        try:
            async with async_session() as session:
                # Ищем промокод в базе
                query = await session.execute(
                    select(Promo).where(Promo.code == code)
                )
                promo = query.scalar_one_or_none()
                
                if not promo:
                    logger.warning(f"Попытка использования несуществующего промокода {code}")
                    return False
                
                # Увеличиваем счетчик использования и сохраняем время использования
                promo.used_count += 1
                promo.used_at = datetime.now()
                
                # Если достигнут лимит использования, деактивируем промокод
                if promo.usage_limit and promo.used_count >= promo.usage_limit:
                    promo.is_active = False
                    logger.info(f"Промокод {code} достиг лимита использования и деактивирован")
                
                await session.commit()
                logger.info(f"Промокод {code} успешно использован пользователем {user_id}")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка при использовании промокода {code}: {e}")
            return False
