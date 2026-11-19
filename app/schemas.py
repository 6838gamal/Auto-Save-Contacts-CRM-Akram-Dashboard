from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional


class SubscriptionBase(BaseModel):
    subscriber_name: str
    email: str
    phone: Optional[str] = None
    plan_name: str
    price: float
    start_date: date
    end_date: date
    status: str = "active"


class SubscriptionCreate(SubscriptionBase):
    pass


class SubscriptionUpdate(BaseModel):
    subscriber_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    plan_name: Optional[str] = None
    price: Optional[float] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = None


class SubscriptionResponse(SubscriptionBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
