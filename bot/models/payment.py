from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey
from datetime import datetime
from bot.utils.db import Base

class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False)
    status = Column(Text)  # pending, succeeded, canceled, waiting_for_capture
    amount = Column(Integer)
    payment_id = Column(Text, nullable=False, unique=True)  # ID платежа в системе YooKassa
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime, nullable=True)  # Может быть None, если платеж не завершен
