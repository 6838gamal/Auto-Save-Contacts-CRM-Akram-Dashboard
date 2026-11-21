from sqlalchemy.orm import Session
from sqlalchemy import text, func
from datetime import datetime
from . import models, schemas


# ============================================================
# الاشتراكات (Subscriptions) — CRUD كامل
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
    if data.get("code"):
        data["code"] = data["code"].strip().upper()
    if not data.get("plan_label"):
        data["plan_label"] = "اشتراك سنوي"
    if not data.get("duration_minutes"):
        data["duration_minutes"] = 525600
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
    data.pop("code", None)
    for key, value in data.items():
        setattr(db_sub, key, value)
    db_sub.updated_at = datetime.utcnow()
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
    """جلب اشتراك نشط مرتبط بجهاز معيّن."""
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
# الأجهزة / المستخدمون — جلب كافة البيانات دون شروط
# ============================================================
# ملاحظة: لا يوجد جدول مستخدمين منفصل، لذا نجلب كل الصفوف
# من subscription_codes ونعيد كل بياناتها بما فيها بيانات الجهاز.
# ============================================================

# ── قائمة الأعمدة (مركزية — تُستخدم في كل الاستعلامات) ──
_DEVICE_COLUMNS_SQL = """
    code,
    plan_label,
    is_subscribed,
    is_active,
    is_trial,
    is_lifetime,
    duration_minutes,
    max_contacts,
    used_contacts,
    bound_user_id,
    bound_ip,
    activated_at,
    expires_at,
    notes,
    created_at,
    updated_at,
    device_id,
    android_id,
    install_uuid,
    public_ip,
    local_ip,
    location_info,
    device_model,
    os_version,
    network_type,
    saved_contacts_count,
    free_contacts_used,
    free_contacts_limit,
    free_tier_exhausted,
    app_version,
    first_seen,
    last_seen
"""


def get_devices(db: Session, skip: int = 0, limit: int = 5000):
    """
    جلب كافة البيانات من جدول subscription_codes (بدون أي شرط).
    يعيد كل صف بكل أعمدته بما فيها بيانات الجهاز.
    """
    sql = text(f"""
        SELECT {_DEVICE_COLUMNS_SQL}
        FROM subscription_codes
        ORDER BY COALESCE(last_seen, created_at) DESC
        OFFSET :skip LIMIT :limit
    """)
    rows = db.execute(sql, {"skip": skip, "limit": limit}).fetchall()
    return [_serialize_full_row(r) for r in rows]


def get_device(db: Session, device_id: str):
    """
    جلب صف واحد بواسطة bound_user_id أو install_uuid أو code.
    """
    sql = text(f"""
        SELECT {_DEVICE_COLUMNS_SQL}
        FROM subscription_codes
        WHERE bound_user_id = :device_id
           OR install_uuid = :device_id
           OR code = :device_id
        ORDER BY updated_at DESC
        LIMIT 1
    """)
    row = db.execute(sql, {"device_id": device_id}).fetchone()
    return _serialize_full_row(row) if row else None


def search_devices(db: Session, query: str, limit: int = 50):
    """
    البحث في كافة الصفوف بالكود أو bound_user_id أو IP
    أو اسم الجهاز أو الـ install_uuid.
    """
    q = f"%{query.strip()}%"
    sql = text(f"""
        SELECT {_DEVICE_COLUMNS_SQL}
        FROM subscription_codes
        WHERE
            code ILIKE :q
            OR bound_user_id ILIKE :q
            OR bound_ip ILIKE :q
            OR device_model ILIKE :q
            OR public_ip ILIKE :q
            OR install_uuid ILIKE :q
            OR android_id ILIKE :q
        ORDER BY COALESCE(last_seen, updated_at) DESC
        LIMIT :limit
    """)
    rows = db.execute(sql, {"q": q, "limit": limit}).fetchall()
    return [_serialize_full_row(r) for r in rows]


def get_ips_for_device(db: Session, device_id: str, limit: int = 20):
    """
    جلب عناوين IP المرتبطة بجهاز معيّن (من كل صفوفه).
    يبحث في bound_ip و public_ip.
    """
    rows = (
        db.query(
            models.Subscription.bound_ip,
            models.Subscription.public_ip,
            func.max(models.Subscription.updated_at).label("last_seen"),
        )
        .filter(
            models.Subscription.bound_user_id == device_id,
        )
        .group_by(
            models.Subscription.bound_ip,
            models.Subscription.public_ip,
        )
        .order_by(func.max(models.Subscription.updated_at).desc())
        .limit(limit)
        .all()
    )
    ips = []
    for r in rows:
        if r.bound_ip:
            ips.append(r.bound_ip)
        if r.public_ip and r.public_ip not in ips:
            ips.append(r.public_ip)
    return ips


# ============================================================
# دالة مساعدة: تحويل صف كامل إلى dict JSON-friendly
# ============================================================

def _serialize_full_row(row) -> dict:
    """
    تحويل صف SQLAlchemy Row إلى قاموس يحتوي كل الأعمدة.
    يدعم القيم الناقصة والتواريخ (datetime → ISO string).
    """
    if row is None:
        return {}
    m = dict(row._mapping)
    for k, v in m.items():
        if isinstance(v, datetime):
            m[k] = v.isoformat()
    return m
