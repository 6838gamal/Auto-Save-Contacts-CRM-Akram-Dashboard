from sqlalchemy.orm import Session
from sqlalchemy import text
from . import models, schemas


# ============================================================
# الاشتراكات (Subscriptions)
# ============================================================

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


# ============================================================
# المستخدمون (Users) — لجلب البيانات من قاعدة البيانات
# ============================================================

def get_users(db: Session, skip: int = 0, limit: int = 5000):
    """
    جلب قائمة المستخدمين مع بيانات الحساب والـ IP.
    يعيد قائمة من القواميس جاهزة للـ JSON.
    """
    users = (
        db.query(models.User)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_serialize_user(u) for u in users]


def get_user(db: Session, user_id: str):
    """جلب مستخدم واحد بواسطة المعرف."""
    return (
        db.query(models.User)
        .filter(models.User.user_id == user_id)
        .first()
    )


def get_user_details(db: Session, user_id: str):
    """
    جلب تفاصيل مستخدم واحد (بما فيها IP وتفاصيل الحساب)
    جاهزة للاستخدام في الواجهة.
    """
    u = get_user(db, user_id)
    if not u:
        return None
    return _serialize_user(u)


def search_users(db: Session, query: str, limit: int = 50):
    """
    البحث في المستخدمين بالاسم أو المعرف أو الـ IP.
    مفيد للـ API عند الكتابة في حقل البحث.
    """
    q = f"%{query.strip()}%"
    users = (
        db.query(models.User)
        .filter(
            (models.User.name.ilike(q))
            | (models.User.user_id.ilike(q))
            | (models.User.ip.ilike(q))
        )
        .limit(limit)
        .all()
    )
    return [_serialize_user(u) for u in users]


# ============================================================
# دالة مساعدة: تحويل كائن المستخدم إلى dict
# ============================================================

def _serialize_user(u) -> dict:
    """
    تحويل كائن User إلى قاموس JSON-friendly.
    تدعم أسماء أعمدة متعددة (name/full_name/first_name... إلخ)
    حتى تعمل مع هياكل مختلفة لقواعد البيانات.
    """
    return {
        "user_id": str(getattr(u, "user_id", None) or getattr(u, "id", None) or ""),
        "name": (
            getattr(u, "name", None)
            or getattr(u, "full_name", None)
            or getattr(u, "first_name", None)
            or getattr(u, "username", None)
            or str(getattr(u, "user_id", None) or getattr(u, "id", None) or "")
        ),
        "username": getattr(u, "username", None),
        "ip": (
            getattr(u, "ip", None)
            or getattr(u, "last_ip", None)
            or getattr(u, "bound_ip", None)
        ),
        "phone": (
            getattr(u, "phone", None)
            or getattr(u, "mobile", None)
            or getattr(u, "phone_number", None)
        ),
        "created_at": (
            getattr(u, "created_at", None).isoformat()
            if getattr(u, "created_at", None) and hasattr(getattr(u, "created_at", None), "isoformat")
            else getattr(u, "created_at", None)
        ),
    }
