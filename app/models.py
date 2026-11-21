from sqlalchemy import Column, Integer, String, Boolean, BigInteger, DateTime, Text, text
from datetime import datetime
from .database import Base


class Subscription(Base):
    __tablename__ = "subscription_codes"

    # ---- المفتاح الأساسي: الكود ----
    code = Column(String, primary_key=True, index=True)

    # ---- اسم الباقة ----
    plan_label = Column(String, nullable=False, server_default="اشتراك مفعل")

    # ---- أعلام الاشتراك ----
    is_subscribed = Column(Boolean, nullable=False, server_default=text("TRUE"))
    is_active = Column(Boolean, nullable=False, server_default=text("TRUE"))
    is_trial = Column(Boolean, nullable=False, server_default=text("FALSE"))
    is_lifetime = Column(Boolean, nullable=False, server_default=text("FALSE"))

    # ---- المدة والحصص ----
    duration_minutes = Column(BigInteger, nullable=False, server_default=text("43200"))
    max_contacts = Column(Integer, nullable=True)
    used_contacts = Column(Integer, nullable=False, server_default=text("0"))

    # ---- الربط بالجهاز/الشبكة ----
    bound_user_id = Column(String, nullable=True)
    bound_ip = Column(String, nullable=True)

    # ---- التواريخ (epoch ms) ----
    activated_at = Column(BigInteger, nullable=True)
    expires_at = Column(BigInteger, nullable=True)

    # ---- ملاحظات ----
    notes = Column(String, nullable=False, server_default="")

    # ═══════════════════════════════════════════════════════
    #  ✨ جديد: أعمدة الجهاز (يستخدمها mobile_api.py)
    # ═══════════════════════════════════════════════════════
    device_id = Column(String, nullable=True, server_default="")
    android_id = Column(String, nullable=True)
    install_uuid = Column(String, nullable=True, index=True)
    public_ip = Column(String, nullable=True)
    local_ip = Column(String, nullable=True)
    location_info = Column(String, nullable=True)
    device_model = Column(String, nullable=True)
    os_version = Column(String, nullable=True)
    network_type = Column(String, nullable=True)

    saved_contacts_count = Column(Integer, nullable=False, server_default=text("0"))
    free_contacts_used = Column(Integer, nullable=False, server_default=text("0"))
    free_contacts_limit = Column(Integer, nullable=False, server_default=text("100"))
    free_tier_exhausted = Column(Boolean, nullable=False, server_default=text("FALSE"))

    app_version = Column(String, nullable=True, server_default="1.0")

    first_seen = Column(DateTime(timezone=True), nullable=True, server_default=text("NOW()"))
    last_seen = Column(DateTime(timezone=True), nullable=True, server_default=text("NOW()"))

    # ---- طوابع زمنية (موجودة) ----
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"), onupdate=datetime.utcnow)
