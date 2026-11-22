from sqlalchemy.orm import Session
from sqlalchemy import text, func
from datetime import datetime
from . import models, schemas


# ============================================================
# الاشتراكات (Subscriptions) — CRUD كامل
# ============================================================

def get_subscriptions(db: Session, skip: int = 0, limit: int = 1000):
    """النسخة القديمة (ORM) — تُبقي للتوافق مع أي كود قديم."""
    return (
        db.query(models.Subscription)
        .order_by(models.Subscription.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_subscriptions_full(db: Session, skip: int = 0, limit: int = 1000):
    """
    ✨ النسخة الكاملة: ترجع كل الأعمدة (بما فيها حقول الجهاز)
    + آخر جهاز استخدم الكود (last_used_user_id) لكشف التكرار.

    تعمل مع أو بدون جدول code_usage_logs — إن لم يوجد،
    يُعاد last_used_user_id = None لكل صف.
    """
    has_log = _table_exists(db, "code_usage_logs")

    if has_log:
        sql = text(f"""
            SELECT
                {_COLUMNS_PREFIXED},
                lul.last_used_user_id
            FROM subscription_codes sc
            LEFT JOIN (
                SELECT cul.code, cul.used_by_user_id AS last_used_user_id
                FROM code_usage_logs cul
                INNER JOIN (
                    SELECT code, MAX(id) AS max_id
                    FROM code_usage_logs
                    GROUP BY code
                ) m ON cul.code = m.code AND cul.id = m.max_id
            ) lul ON sc.code = lul.code
            ORDER BY sc.created_at DESC
            OFFSET :skip LIMIT :limit
        """)
        rows = db.execute(sql, {"skip": skip, "limit": limit}).fetchall()
        return [_serialize_full_row(r) for r in rows]

    # fallback: بدون جدول الاستخدامات
    sql = text(f"""
        SELECT {_DEVICE_COLUMNS_SQL}
        FROM subscription_codes
        ORDER BY created_at DESC
        OFFSET :skip LIMIT :limit
    """)
    rows = db.execute(sql, {"skip": skip, "limit": limit}).fetchall()
    result = [_serialize_full_row(r) for r in rows]
    for item in result:
        item.setdefault("last_used_user_id", None)
    return result


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
    """
    تحديث جزئي — يستخدم exclude_unset لتفادي تصفير الحقول غير المرسلة.
    """
    db_sub = get_subscription(db, code)
    if not db_sub:
        return None
    data = sub.model_dump(exclude_unset=True)
    data.pop("code", None)  # الكود لا يُعدّل من هنا (استخدم regenerate بدلاً)
    for key, value in data.items():
        setattr(db_sub, key, value)
    db_sub.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(db_sub)
    return db_sub


def delete_subscription(db: Session, code: str):
    """
    حذف اشتراك + سجلات استخدامه (يدوياً إن لم يكن CASCADE مفعّلاً).
    """
    db_sub = get_subscription(db, code)
    if db_sub:
        # احذف سجلات الاستخدام أولاً (آمن حتى لو لم يوجد الجدول)
        try:
            db.execute(
                text("DELETE FROM code_usage_logs WHERE code = :code"),
                {"code": code.strip().upper()},
            )
        except Exception:
            db.rollback()
            db_sub = get_subscription(db, code)
            if not db_sub:
                return None
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
# ✨ إعادة توليد كود اشتراك — تغيير المفتاح الأساسي في نفس السجل
# ============================================================

def rename_subscription_code(db: Session, old_code: str, new_code: str):
    """
    يغيّر كود الاشتراك مع الحفاظ على كل الحقول (بما فيها المفتاح الأساسي)
    + ينقل سجلات الاستخدام إلى الكود الجديد إن وُجد جدولها.
    يعيد السجل المحدّث أو None إن لم يوجد القديم/تكرر الجديد.
    """
    old_code = old_code.strip().upper()
    new_code = new_code.strip().upper()

    # التأكد من عدم وجود الكود الجديد مسبقًا
    exists = (
        db.query(models.Subscription)
        .filter(models.Subscription.code == new_code)
        .first()
    )
    if exists:
        return None

    db_sub = get_subscription(db, old_code)
    if not db_sub:
        return None

    # ✨ انقل سجلات الاستخدام (إن وُجد الجدول)
    if _table_exists(db, "code_usage_logs"):
        try:
            db.execute(
                text("UPDATE code_usage_logs SET code = :new WHERE code = :old"),
                {"new": new_code, "old": old_code},
            )
        except Exception:
            db.rollback()
            # أعد الجلب بعد rollback
            db_sub = get_subscription(db, old_code)
            if not db_sub:
                return None

    db_sub.code = new_code
    db_sub.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(db_sub)
    return db_sub


# ============================================================
# ✨ سجل استخدامات الأكواد (لكشف التكرار)
# ============================================================

def log_code_usage(
    db: Session,
    code: str,
    used_by_user_id: str,
    used_ip: str = None,
):
    """
    يسجّل استخدام الكود من جهاز.
    يعيد dict فيه is_duplicate لو كان الجهاز مختلف عن bound_user_id.
    يعيد None إذا لم يوجد الكود.
    """
    code = code.strip().upper()
    sub = get_subscription(db, code)
    if not sub:
        return None

    # إن لم يوجد جدول السجلات، لا نفشل — نعيد النتيجة بدون تسجيل
    if _table_exists(db, "code_usage_logs"):
        try:
            log = models.CodeUsageLog(
                code=code,
                used_by_user_id=used_by_user_id,
                used_ip=used_ip,
                used_at=datetime.utcnow(),
            )
            db.add(log)
            db.commit()
        except Exception:
            db.rollback()

    is_duplicate = (
        bool(sub.bound_user_id)
        and str(sub.bound_user_id) != str(used_by_user_id)
    )
    return {
        "code": code,
        "used_by_user_id": used_by_user_id,
        "bound_user_id": sub.bound_user_id,
        "is_duplicate": is_duplicate,
    }


def get_last_used_user_id(db: Session, code: str):
    """آخر جهاز استخدم الكود (أو None)."""
    if not _table_exists(db, "code_usage_logs"):
        return None
    try:
        row = db.execute(
            text("""
                SELECT used_by_user_id
                FROM code_usage_logs
                WHERE code = :code
                ORDER BY id DESC
                LIMIT 1
            """),
            {"code": code.strip().upper()},
        ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def get_usage_logs(db: Session, code: str, limit: int = 50):
    """كل سجلات استخدام كود معيّن (للعرض التفصيلي إن احتجت)."""
    if not _table_exists(db, "code_usage_logs"):
        return []
    try:
        rows = db.execute(
            text("""
                SELECT id, code, used_by_user_id, used_ip, used_at
                FROM code_usage_logs
                WHERE code = :code
                ORDER BY id DESC
                LIMIT :limit
            """),
            {"code": code.strip().upper(), "limit": limit},
        ).fetchall()
        return [_serialize_full_row(r) for r in rows]
    except Exception:
        return []


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

# نسخة مع بادئة sc. (تُستخدم في JOIN)
_COLUMNS_PREFIXED = ", ".join(
    f"sc.{col.strip()}"
    for col in _DEVICE_COLUMNS_SQL.split(",")
    if col.strip()
)


def get_devices(db: Session, skip: int = 0, limit: int = 500):
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
    أو اسم الجهاز أو الـ install_uuid أو android_id.
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
            OR local_ip ILIKE :q
            OR install_uuid ILIKE :q
            OR android_id ILIKE :q
            OR os_version ILIKE :q
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
# دوال مساعدة
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


def _table_exists(db: Session, table_name: str) -> bool:
    """
    يتحقق من وجود جدول (PostgreSQL عبر to_regclass).
    يعيد False بأمان إن فشل الاستعلام.
    """
    try:
        result = db.execute(
            text("SELECT to_regclass(:t)"),
            {"t": table_name},
        ).scalar()
        return result is not None
    except Exception:
        return False
