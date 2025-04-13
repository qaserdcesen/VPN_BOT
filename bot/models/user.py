from sqlalchemy import Column, Integer, Text, DateTime, BigInteger
from datetime import datetime
from bot.utils.base import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    tg_id = Column(BigInteger, unique=True)
    username = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, default=datetime.utcnow)
