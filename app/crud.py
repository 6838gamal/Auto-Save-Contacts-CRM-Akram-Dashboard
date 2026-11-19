from sqlalchemy.orm import Session
from . import models, schemas


def get_subscriptions(db: Session, skip: int = 0, limit: int = 100):
    return (
        db.query(models.Subscription)
        .order_by(models.Subscription.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_subscription(db: Session, code: str):
    """جلب كود اشتراك بواسطة الكود (المفتاح الأساسي)."""
    return (
        db.query(models.Subscription)
        .filter(models.Subscription.code == code.strip().upper())
        .first()
    )


def create_subscription(db: Session, sub: schemas.SubscriptionCreate):
    data = sub.model_dump()
    # توحيد صيغة الكود (نفس ما يفعله Kotlin: trim().uppercase())
    if data.get("code"):
        data["code"] = data["code"].strip().upper()
    db_sub = models.Subscription(**data)
    db.add(db_sub)
    db.commit()
    db.refresh(db_sub)
    return db_sub


def update_subscription(db: Session, code: str, sub: schemas.SubscriptionUpdate):
    db_sub = get_subscription(db, code)
    if not db_sub:
        return None
    data = sub.model_dump(exclude_unset=True)
    # منع تغيير المفتاح الأساسي عبر التحديث
    data.pop("code", None)
    for key, value in data.items():
        setattr(db_sub, key, value)
    db.commit()
    db.refresh(db_sub)
    return db_sub


def delete_subscription(db: Session, code: str):
    db_sub = get_subscription(db, code)
    if db_sub:
        db.delete(db_sub)
        db.commit()
    return db_sub


def get_subscription_by_user(db: Session, user_id: str):
    """جلب اشتراك نشط مرتبط بمستخدم معيّن (مطابق لـ findApprovedCodeForUser في Kotlin)."""
    return (
        db.query(models.Subscription)
        .filter(
            models.Subscription.bound_user_id == user_id,
            models.Subscription.is_subscribed == True,
            models.Subscription.is_active == True,
        )
        .order_by(models.Subscription.updated_at.desc())
        .first()
    )
