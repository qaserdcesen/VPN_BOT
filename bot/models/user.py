from sqlalchemy import Column, Integer, BigInteger, Text, Boolean, DateTime, Float
from datetime import datetime
from bot.utils.db import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    tg_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(Text)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime)
    last_login = Column(DateTime)
    contact = Column(Text)
    balace = Column(Float, default=0.0)
