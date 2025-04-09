from sqlalchemy import Column, Integer, Text, BigInteger
from bot.utils.db import Base

class Plan(Base):
    __tablename__ = "plans"
    
    id = Column(Integer, primary_key=True)
    title = Column(Text)
    traffic_limit = Column(BigInteger)
    duration_days = Column(Integer)
    price = Column(Integer)
