import os
import time
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("uvicorn.error")

DATABASE_URL = os.getenv("DATABASE_URL", "")

engine = None
SessionLocal = None

if not DATABASE_URL:
    logger.error("❌ لم يتم العثور على DATABASE_URL في متغيرات البيئة")
else:
    try:
        engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=5,
            max_overflow=10,
        )
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        logger.info("✅ تم إنشاء engine بنجاح")
    except Exception as e:
        logger.error(f"❌ فشل إنشاء الـ engine: {e}")

Base = declarative_base()


# ═══════════════════════════════════════════════════════════
#  ✨ جديد: أعمدة الجهاز — تُضاف تلقائياً عند بدء السيرفر
# ═══════════════════════════════════════════════════════════

_DEVICE_COLUMN_MIGRATIONS = [
    # أعمدة الجهاز
    "ALTER TABLE subscription_codes ADD COLUMN IF NOT EXISTS device_id TEXT DEFAULT ''",
    "ALTER TABLE subscription_codes ADD COLUMN IF NOT EXISTS android_id TEXT",
    "ALTER TABLE subscription_codes ADD COLUMN IF NOT EXISTS install_uuid TEXT",
    "ALTER TABLE subscription_codes ADD COLUMN IF NOT EXISTS public_ip TEXT",
    "ALTER TABLE subscription_codes ADD COLUMN IF NOT EXISTS local_ip TEXT",
    "ALTER TABLE subscription_codes ADD COLUMN IF NOT EXISTS location_info TEXT",
    "ALTER TABLE subscription_codes ADD COLUMN IF NOT EXISTS device_model TEXT",
    "ALTER TABLE subscription_codes ADD COLUMN IF NOT EXISTS os_version TEXT",
    "ALTER TABLE subscription_codes ADD COLUMN IF NOT EXISTS network_type TEXT",
    "ALTER TABLE subscription_codes ADD COLUMN IF NOT EXISTS saved_contacts_count INT DEFAULT 0",
    "ALTER TABLE subscription_codes ADD COLUMN IF NOT EXISTS free_contacts_used INT DEFAULT 0",
    "ALTER TABLE subscription_codes ADD COLUMN IF NOT EXISTS free_contacts_limit INT DEFAULT 100",
    "ALTER TABLE subscription_codes ADD COLUMN IF NOT EXISTS free_tier_exhausted BOOLEAN DEFAULT FALSE",
    "ALTER TABLE subscription_codes ADD COLUMN IF NOT EXISTS app_version TEXT DEFAULT '1.0'",
    "ALTER TABLE subscription_codes ADD COLUMN IF NOT EXISTS first_seen TIMESTAMPTZ DEFAULT NOW()",
    "ALTER TABLE subscription_codes ADD COLUMN IF NOT EXISTS last_seen TIMESTAMPTZ DEFAULT NOW()",
    # فهارس
    "CREATE INDEX IF NOT EXISTS idx_sub_codes_install_uuid ON subscription_codes(install_uuid)",
    "CREATE INDEX IF NOT EXISTS idx_sub_codes_user_id ON subscription_codes(bound_user_id)",
    "CREATE INDEX IF NOT EXISTS idx_sub_codes_public_ip ON subscription_codes(public_ip)",
    "CREATE INDEX IF NOT EXISTS idx_sub_codes_last_seen ON subscription_codes(last_seen DESC)",
]


def _ensure_device_columns() -> bool:
    """
    يضمن وجود أعمدة الجهاز في جدول subscription_codes.
    آمن للتشغيل المتكرر (IF NOT EXISTS).
    """
    if engine is None:
        return False
    try:
        with engine.connect() as conn:
            for stmt in _DEVICE_COLUMN_MIGRATIONS:
                conn.execute(text(stmt))
            conn.commit()
        logger.info("✅ تم التحقق من أعمدة الجهاز (device columns)")
        return True
    except Exception as e:
        logger.error(f"❌ فشل إضافة أعمدة الجهاز: {e}")
        return False


# ═══════════════════════════════════════════════════════════
#  الفحص والتهيئة
# ═══════════════════════════════════════════════════════════

def check_db_connection() -> tuple[bool, str]:
    if engine is None:
        return False, "لم يتم إعداد DATABASE_URL"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, ""
    except OperationalError as e:
        return False, f"تعذّر الاتصال بقاعدة البيانات: {e.orig}"
    except SQLAlchemyError as e:
        return False, f"خطأ في قاعدة البيانات: {str(e)}"
    except Exception as e:
        return False, f"خطأ غير متوقع: {str(e)}"


def init_db(max_retries: int = 10, delay: int = 3) -> bool:
    """مهم في Docker/Render: ننتظر حتى تجهز قاعدة البيانات."""
    if engine is None:
        logger.error("❌ لا يمكن تهيئة قاعدة البيانات: engine غير موجود")
        return False

    for attempt in range(1, max_retries + 1):
        ok, err = check_db_connection()
        if ok:
            try:
                from . import models  # noqa
                Base.metadata.create_all(bind=engine)
                logger.info("✅ تم الاتصال بقاعدة البيانات وإنشاء الجداول")

                # ✨ جديد: أضف أعمدة الجهاز إن لم تكن موجودة
                _ensure_device_columns()

                return True
            except Exception as e:
                logger.error(f"❌ فشل إنشاء الجداول: {e}")
                return False
        else:
            logger.warning(f"⚠️ محاولة {attempt}/{max_retries} فشلت: {err}")
            if attempt < max_retries:
                time.sleep(delay)

    logger.error("❌ تعذّر الاتصال بقاعدة البيانات بعد كل المحاولات")
    return False


def get_db():
    from fastapi import HTTPException, status

    if SessionLocal is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="قاعدة البيانات غير متاحة: لم يتم إعداد الاتصال.",
        )
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except (OperationalError, SQLAlchemyError) as e:
        db.close()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"تعذّر الاتصال بقاعدة البيانات: {e.__class__.__name__}",
        )
    try:
        yield db
    finally:
        db.close()
