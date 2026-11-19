from sqlalchemy import Column, Integer, String, Float, Date, DateTime
from datetime import datetime
from .database import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    subscriber_name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String)
    plan_name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
