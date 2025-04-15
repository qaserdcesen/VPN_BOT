from sqlalchemy import Column, Integer, Text, Boolean, DateTime, BigInteger, ForeignKey
from sqlalchemy.orm import relationship
from bot.utils.db import Base  # Импортируем Base из base.py

class Client(Base):
    __tablename__ = "clients"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    email = Column(Text)
    uuid = Column(Text)
    limit_ip = Column(Integer)
    total_traffic = Column(BigInteger)
    expiry_time = Column(DateTime)
    is_active = Column(Boolean, default=True)
    tg_notified = Column(Boolean, default=False)
    reset = Column(Integer)
    config_data = Column(Text, nullable=True)  # Оставляем на будущее
    
    # Добавляем отношение с пользователем
    user = relationship("User", back_populates="clients")
