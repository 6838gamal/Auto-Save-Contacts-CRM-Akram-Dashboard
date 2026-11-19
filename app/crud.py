from sqlalchemy.orm import Session
from . import models, schemas


def get_subscriptions(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Subscription).offset(skip).limit(limit).all()


def get_subscription(db: Session, sub_id: int):
    return db.query(models.Subscription).filter(models.Subscription.id == sub_id).first()


def create_subscription(db: Session, sub: schemas.SubscriptionCreate):
    db_sub = models.Subscription(**sub.dict())
    db.add(db_sub)
    db.commit()
    db.refresh(db_sub)
    return db_sub


def update_subscription(db: Session, sub_id: int, sub: schemas.SubscriptionUpdate):
    db_sub = get_subscription(db, sub_id)
    if not db_sub:
        return None
    for key, value in sub.dict(exclude_unset=True).items():
        setattr(db_sub, key, value)
    db.commit()
    db.refresh(db_sub)
    return db_sub


def delete_subscription(db: Session, sub_id: int):
    db_sub = get_subscription(db, sub_id)
    if db_sub:
        db.delete(db_sub)
        db.commit()
    return db_sub
