from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, BigInteger
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from bot.utils.db import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    tg_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Поля для бана
    is_banned = Column(Boolean, default=False)
    ban_reason = Column(Text, nullable=True)
    banned_at = Column(DateTime(timezone=True), nullable=True)
    banned_until = Column(DateTime(timezone=True), nullable=True)  # Когда истекает бан
    
    # Отношение с клиентами
    clients = relationship("Client", back_populates="user", cascade="all, delete-orphan")
