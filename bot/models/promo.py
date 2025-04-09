from sqlalchemy import Column, Integer, Text, DECIMAL, DateTime, Boolean, ForeignKey
from bot.utils.db import Base

class Promo(Base):
    __tablename__ = "promik"  # Название таблицы согласно схеме
    
    id = Column(Integer, primary_key=True)
    code = Column(Text)
    discount = Column(DECIMAL)  # Например, 20.0 для 20%
    expiration_date = Column(DateTime)
    usage_limit = Column(Integer)
    used_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Если привязан к конкретному пользователю
    used_at = Column(DateTime, nullable=True)
