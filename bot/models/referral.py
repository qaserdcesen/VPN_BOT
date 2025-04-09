from sqlalchemy import Column, Integer, DECIMAL, Boolean, DateTime, ForeignKey
from datetime import datetime
from bot.utils.db import Base

class Referral(Base):
    __tablename__ = "referals"  # Согласно схеме
    
    id = Column(Integer, primary_key=True)
    referrer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    referred_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    bonus_amount = Column(DECIMAL)
    is_paid = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
