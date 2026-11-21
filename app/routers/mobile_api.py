"""
Mobile API — نقاط النهاية التي يتصل بها تطبيق Android.

- تعمل بجانب لوحة الإدارة في نفس السيرفر (Render).
- تستخدم جدول subscription_codes فقط (لا جدول منفصل).
- تتحقق من X-API-Key في كل طلب.
- أسماء الحقول مطابقة تماماً لـ SubscriptionConnectRequest في Kotlin.

المسارات الناتجة (لأن prefix="/api"):
    POST /api/subscription/connect
    POST /api/subscription/activate
    POST /api/subscription/verify
    POST /api/subscription/usage
    POST /api/subscription/review-request
    POST /api/clients/sync
"""
import os
import uuid as _uuid
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..database import get_db


router = APIRouter(prefix="/api", tags=["Mobile App"])

# ═══════════════════════════════════════════════════════════
#  التحقق من مفتاح API
# ═══════════════════════════════════════════════════════════

MOBILE_API_KEY = os.getenv("MOBILE_API_KEY", "").strip()


def verify_mobile_key(x_api_key: Optional[str] = Header(None)):
    """
    - إذا لم يُعرّف MOBILE_API_KEY في البيئة → يسمح (للتطوير فقط).
    - إذا عُرّف → يجب أن يطابق X-API-Key.
    """
    if not MOBILE_API_KEY:
        return
    if not x_api_key or x_api_key != MOBILE_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


# ═══════════════════════════════════════════════════════════
#  Pydantic Models — مطابقة لحقول التطبيق (Kotlin)
# ═══════════════════════════════════════════════════════════

class ConnectRequest(BaseModel):
    user_id: str
    device_id: str = ""
    android_id: str
    install_uuid: str
    public_ip: str
    local_ip: str
    location_info: str
    device_model: str
    os_version: str
    network_type: str
    saved_contacts_count: int = 0
    free_contacts_used: int = 0
    free_contacts_limit: int = 100
    free_tier_exhausted: bool = False
    plan_type: str = "FREE"
    active_code: Optional[str] = None
    app_version: str = "1.0"


class ActivateRequest(BaseModel):
    code: str
    user_id: str
    device_id: str = ""
    android_id: str
    install_uuid: str
    public_ip: str
    local_ip: str
    location_info: str
    device_model: str
    os_version: str
    network_type: str
    saved_contacts_count: int = 0
    app_version: str = "1.0"


class VerifyRequest(BaseModel):
    code: str
    user_id: str
    device_id: str = ""
    android_id: str
    public_ip: str
    local_ip: str
    device_model: str
    saved_contacts_count: int = 0
    used_quota_count: int = 0


class UsageRequest(BaseModel):
    code: str
    user_id: str
    device_id: str = ""
    public_ip: str
    used_contacts: int
    total_contacts: int
    plan_type: str = "SUBSCRIBED"


class ReviewRequest(BaseModel):
    user_id: str
    device_id: str = ""
    requested_code: str = ""
    public_ip: str
    local_ip: str
    device_model: str
    location_info: str
    saved_contacts_count: int = 0
    notes: str = ""


class ClientItem(BaseModel):
    phone: str
    original_phone: str
    name: str
    source: str
    created_at: int
    last_activity: int
    interaction_count: int
    is_synced_to_phone: bool
    is_deleted: bool = False


class ClientSyncRequest(BaseModel):
    user_id: str
    device_id: str = ""
    public_ip: str
    plan_type: str = "FREE"
    clients: list[ClientItem]


# ═══════════════════════════════════════════════════════════
#  دوال مساعدة
# ═══════════════════════════════════════════════════════════

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _epoch_ms_to_iso(ms: Optional[int]) -> Optional[str]:
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()
    except Exception:
        return None


def _find_row_by_identity(db: Session, req: ConnectRequest) -> Optional[str]:
    """
    يبحث عن صف موجود بـ:
    1) install_uuid
    2) bound_user_id (غير فارغ)
    3) active_code
    يعيد code إن وجد.
    """
    row = db.execute(text("""
        SELECT code FROM subscription_codes
        WHERE install_uuid = :uuid
           OR (bound_user_id = :uid AND bound_user_id IS NOT NULL AND bound_user_id != '')
           OR (code = :active_code AND :active_code IS NOT NULL AND :active_code != '')
        ORDER BY
            CASE WHEN install_uuid = :uuid THEN 0
                 WHEN bound_user_id = :uid THEN 1
                 ELSE 2 END
        LIMIT 1
    """), {
        "uuid": req.install_uuid,
        "uid": req.user_id,
        "active_code": (req.active_code or "").strip().upper(),
    }).fetchone()
    return row[0] if row else None


# ═══════════════════════════════════════════════════════════
#  Endpoints
# ═══════════════════════════════════════════════════════════

@router.post("/subscription/connect", dependencies=[Depends(verify_mobile_key)])
def connect(req: ConnectRequest, db: Session = Depends(get_db)):
    """
    عند بدء التطبيق: يسجّل/يُحدّث الجهاز.
    - إذا وُجد صف (install_uuid / bound_user_id / active_code) → يحدّثه.
    - إذا لا → يُنشئ صفاً جديداً بكود مؤقت DEV-XXXX.
    """
    code = _find_row_by_identity(db, req)

    if code:
        # حدّث الصف الموجود
        db.execute(text("""
            UPDATE subscription_codes SET
                bound_user_id = COALESCE(NULLIF(bound_user_id, ''), :user_id),
                device_id = :device_id,
                android_id = :android_id,
                install_uuid = :install_uuid,
                public_ip = :public_ip,
                local_ip = :local_ip,
                location_info = :location_info,
                device_model = :device_model,
                os_version = :os_version,
                network_type = :network_type,
                saved_contacts_count = :saved_contacts_count,
                free_contacts_used = :free_contacts_used,
                free_contacts_limit = :free_contacts_limit,
                free_tier_exhausted = :free_tier_exhausted,
                app_version = :app_version,
                last_seen = NOW(),
                updated_at = NOW()
            WHERE code = :code
        """), {**req.model_dump(), "code": code})
    else:
        # أنشئ صفاً جديداً
        code = f"DEV-{_uuid.uuid4().hex[:12].upper()}"
        db.execute(text("""
            INSERT INTO subscription_codes (
                code, plan_label, is_subscribed, is_active, is_trial, is_lifetime,
                duration_minutes, max_contacts, used_contacts,
                bound_user_id, bound_ip,
                activated_at, expires_at, notes,
                created_at, updated_at,
                device_id, android_id, install_uuid,
                public_ip, local_ip, location_info, device_model,
                os_version, network_type, saved_contacts_count,
                free_contacts_used, free_contacts_limit, free_tier_exhausted,
                app_version, first_seen, last_seen
            ) VALUES (
                :code, 'FREE', TRUE, FALSE, FALSE, FALSE,
                43200, NULL, 0,
                :user_id, :public_ip,
                NULL, NULL, '',
                NOW(), NOW(),
                :device_id, :android_id, :install_uuid,
                :public_ip, :local_ip, :location_info, :device_model,
                :os_version, :network_type, :saved_contacts_count,
                :free_contacts_used, :free_contacts_limit, :free_tier_exhausted,
                :app_version, NOW(), NOW()
            )
        """), {**req.model_dump(), "code": code})

    db.commit()

    return {
        "valid": True,
        "is_subscribed": True,
        "is_active": True,
        "status": "connected",
        "message": "Device registered successfully",
        "code": code,
    }


@router.post("/subscription/activate", dependencies=[Depends(verify_mobile_key)])
def activate(req: ActivateRequest, db: Session = Depends(get_db)):
    """
    يفعّل كود اشتراك ويربطه بالجهاز.
    - الكود يجب أن يكون موجوداً في subscription_codes.
    - إذا كان مربوطاً بمستخدم آخر → يرفض.
    - بعد التفعيل: يُحدّث نفس الصف ببيانات الجهاز ويجعله نشطاً.
    """
    code_clean = req.code.strip().upper()

    row = db.execute(text("""
        SELECT code, bound_user_id, plan_label, activated_at, expires_at
        FROM subscription_codes
        WHERE code = :code
    """), {"code": code_clean}).fetchone()

    if not row:
        return {
            "valid": False,
            "is_active": False,
            "is_subscribed": False,
            "message": "الكود غير موجود",
        }

    code_found, bound_user, plan_label, _activated_at, expires_at = row

    # هل مربوط بمستخدم آخر؟
    if bound_user and bound_user != req.user_id:
        return {
            "valid": False,
            "is_active": False,
            "is_subscribed": False,
            "message": "الكود مستخدم من جهاز آخر",
        }

    # ربط + تحديث بيانات الجهاز
    db.execute(text("""
        UPDATE subscription_codes SET
            bound_user_id = :user_id,
            bound_ip = :public_ip,
            activated_at = COALESCE(activated_at, :now_ms),
            device_id = :device_id,
            android_id = :android_id,
            install_uuid = :install_uuid,
            public_ip = :public_ip,
            local_ip = :local_ip,
            location_info = :location_info,
            device_model = :device_model,
            os_version = :os_version,
            network_type = :network_type,
            saved_contacts_count = :saved_contacts_count,
            app_version = :app_version,
            is_active = TRUE,
            is_subscribed = TRUE,
            last_seen = NOW(),
            updated_at = NOW()
        WHERE code = :code
    """), {
        **req.model_dump(),
        "code": code_clean,
        "now_ms": int(_now_utc().timestamp() * 1000),
    })
    db.commit()

    return {
        "valid": True,
        "is_active": True,
        "is_subscribed": True,
        "status": "activated",
        "message": "تم تفعيل الاشتراك بنجاح",
        "code": code_clean,
        "plan_label": plan_label or "",
        "activated_at": int(_now_utc().timestamp() * 1000),
        "expires_at": expires_at,
    }


@router.post("/subscription/verify", dependencies=[Depends(verify_mobile_key)])
def verify(req: VerifyRequest, db: Session = Depends(get_db)):
    """
    يتحقق من صلاحية الكود ويحدّث last_seen + saved_contacts_count.
    """
    code_clean = req.code.strip().upper()

    row = db.execute(text("""
        SELECT code, is_active, is_subscribed, activated_at, expires_at, plan_label
        FROM subscription_codes
        WHERE code = :code
    """), {"code": code_clean}).fetchone()

    if not row:
        return {
            "valid": False,
            "is_active": False,
            "is_subscribed": False,
            "message": "الكود غير موجود",
        }

    _code, is_active, is_subscribed, activated_at, expires_at, _plan = row

    # expires_at في القاعدة BigInteger (epoch ms) حسب models.py
    is_expired = False
    if expires_at:
        try:
            is_expired = int(expires_at) < int(_now_utc().timestamp() * 1000)
        except Exception:
            is_expired = False

    final_active = bool(is_active) and not is_expired

    # حدّث بيانات الاتصال
    db.execute(text("""
        UPDATE subscription_codes SET
            last_seen = NOW(),
            saved_contacts_count = :cnt,
            public_ip = :ip,
            local_ip = :lip,
            device_model = :dm,
            updated_at = NOW()
        WHERE code = :code
    """), {
        "cnt": req.saved_contacts_count,
        "ip": req.public_ip,
        "lip": req.local_ip,
        "dm": req.device_model,
        "code": code_clean,
    })
    db.commit()

    return {
        "valid": final_active,
        "is_active": final_active,
        "is_subscribed": bool(is_subscribed),
        "status": "active" if final_active else "expired",
        "message": "صالح" if final_active else "منتهي أو غير مفعّل",
        "code": code_clean,
        "activated_at": activated_at,
        "expires_at": expires_at,
    }


@router.post("/subscription/usage", dependencies=[Depends(verify_mobile_key)])
def usage(req: UsageRequest, db: Session = Depends(get_db)):
    """
    يُسجّل استخدام الحصص على نفس صف الكود.
    """
    code_clean = req.code.strip().upper()

    db.execute(text("""
        UPDATE subscription_codes SET
            saved_contacts_count = :used,
            used_contacts = :used,
            last_seen = NOW(),
            updated_at = NOW()
        WHERE code = :code
    """), {"used": req.used_contacts, "code": code_clean})
    db.commit()

    return {
        "valid": True,
        "message": "تم تحديث الاستخدام",
        "used_contacts": req.used_contacts,
        "code": code_clean,
    }


@router.post("/subscription/review-request", dependencies=[Depends(verify_mobile_key)])
def review_request(req: ReviewRequest, db: Session = Depends(get_db)):
    """
    يستقبل طلب مراجعة/تفعيل يدوي.
    يُحفظ كصف بكود REV-XXXX مع notes.
    """
    code = f"REV-{_uuid.uuid4().hex[:12].upper()}"

    db.execute(text("""
        INSERT INTO subscription_codes (
            code, plan_label, is_subscribed, is_active, is_trial, is_lifetime,
            duration_minutes, max_contacts, used_contacts,
            bound_user_id, bound_ip,
            activated_at, expires_at, notes,
            created_at, updated_at,
            device_id, android_id, install_uuid,
            public_ip, local_ip, location_info, device_model,
            os_version, network_type, saved_contacts_count,
            app_version, first_seen, last_seen
        ) VALUES (
            :code, 'طلب مراجعة', FALSE, FALSE, FALSE, FALSE,
            0, NULL, 0,
            :user_id, :public_ip,
            NULL, NULL, :notes,
            NOW(), NOW(),
            :device_id, NULL, NULL,
            :public_ip, :local_ip, :location_info, :device_model,
            NULL, NULL, :saved_contacts_count,
            NULL, NOW(), NOW()
        )
    """), {**req.model_dump(), "code": code, "notes": req.notes or "طلب مراجعة"})
    db.commit()

    return {
        "valid": True,
        "message": "تم استلام طلبك، سيتم مراجعته قريباً",
        "code": code,
    }


@router.post("/clients/sync", dependencies=[Depends(verify_mobile_key)])
def sync_clients(req: ClientSyncRequest, db: Session = Depends(get_db)):
    """
    مزامنة عملاء.
    - لا يوجد جدول عملاء → نحدّث فقط saved_contacts_count في صف bound_user_id.
    - إذا لم يوجد صف بهذا user_id → نبحث بـ public_ip.
    """
    count = len(req.clients)

    # 1) حاول التحديث عبر bound_user_id
    result = db.execute(text("""
        UPDATE subscription_codes SET
            saved_contacts_count = :count,
            public_ip = :ip,
            last_seen = NOW(),
            updated_at = NOW()
        WHERE bound_user_id = :uid
    """), {"count": count, "ip": req.public_ip, "uid": req.user_id})

    # 2) إذا لم يتأثر أي صف → جرّب عبر public_ip
    if result.rowcount == 0 and req.public_ip:
        db.execute(text("""
            UPDATE subscription_codes SET
                saved_contacts_count = :count,
                last_seen = NOW(),
                updated_at = NOW()
            WHERE public_ip = :ip
        """), {"count": count, "ip": req.public_ip})

    db.commit()

    return {
        "valid": True,
        "message": f"تم استلام {count} عميل (العدد محفوظ في saved_contacts_count)",
        "count": count,
    }
