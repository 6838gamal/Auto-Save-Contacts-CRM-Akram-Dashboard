from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional


class SubscriptionBase(BaseModel):
    # ---- مفتاح الكود ----
    code: str = Field(..., description="كود الاشتراك (المفتاح الأساسي)")
    plan_label: str = Field(default="اشتراك مفعل", description="اسم الباقة المعروض")

    # ---- أعلام الاشتراك ----
    is_subscribed: bool = True
    is_active: bool = True
    is_trial: bool = False
    is_lifetime: bool = False

    # ---- المدة والحصص ----
    duration_minutes: int = 43200
    max_contacts: Optional[int] = None
    used_contacts: int = 0

    # ---- الربط بالجهاز/الشبكة ----
    bound_user_id: Optional[str] = None
    bound_ip: Optional[str] = None

    # ---- التواريخ (epoch ms كما في Kotlin) ----
    activated_at: Optional[int] = None
    expires_at: Optional[int] = None

    # ---- ملاحظات ----
    notes: str = ""

    # ═══════════════════════════════════════════════════════
    #  بيانات الجهاز
    # ═══════════════════════════════════════════════════════
    device_id: Optional[str] = ""
    android_id: Optional[str] = None
    install_uuid: Optional[str] = None
    public_ip: Optional[str] = None
    local_ip: Optional[str] = None
    location_info: Optional[str] = None
    device_model: Optional[str] = None
    os_version: Optional[str] = None
    network_type: Optional[str] = None

    saved_contacts_count: int = 0
    free_contacts_used: int = 0
    free_contacts_limit: int = 100
    free_tier_exhausted: bool = False

    app_version: Optional[str] = "1.0"

    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None

    # ---- طوابع زمنية ----
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # ✨ جديد: آخر جهاز استخدم الكود (للكشف عن التكرار)
    last_used_user_id: Optional[str] = None


class SubscriptionCreate(SubscriptionBase):
    """لإنشاء كود جديد — كل الحقول الأساسية مطلوبة/افتراضية من Base"""
    pass


class SubscriptionUpdate(BaseModel):
    """تحديث جزئي — كل الحقول اختيارية"""
    plan_label: Optional[str] = None
    is_subscribed: Optional[bool] = None
    is_active: Optional[bool] = None
    is_trial: Optional[bool] = None
    is_lifetime: Optional[bool] = None
    duration_minutes: Optional[int] = None
    max_contacts: Optional[int] = None
    used_contacts: Optional[int] = None
    bound_user_id: Optional[str] = None
    bound_ip: Optional[str] = None
    activated_at: Optional[int] = None
    expires_at: Optional[int] = None
    notes: Optional[str] = None

    device_id: Optional[str] = None
    android_id: Optional[str] = None
    install_uuid: Optional[str] = None
    public_ip: Optional[str] = None
    local_ip: Optional[str] = None
    location_info: Optional[str] = None
    device_model: Optional[str] = None
    os_version: Optional[str] = None
    network_type: Optional[str] = None
    app_version: Optional[str] = None


class SubscriptionResponse(SubscriptionBase):
    """
    استجابة القراءة — كل الحقول بما فيها بيانات الجهاز + آخر جهاز مستخدم.
    """
    model_config = ConfigDict(from_attributes=True)
