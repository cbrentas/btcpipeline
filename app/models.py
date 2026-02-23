from sqlalchemy import Column, Integer, String, Numeric, DateTime
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class Price(Base):
    __tablename__ = "prices"

    id = Column(Integer, primary_key=True)
    symbol = Column(String)
    price_usd = Column(Numeric)
    timestamp = Column(DateTime, default=datetime.utcnow)