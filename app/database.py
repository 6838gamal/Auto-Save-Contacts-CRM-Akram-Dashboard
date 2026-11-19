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
    logger.error("❌ لم يتم العثور على DATABASE_URL في ملف .env")
else:
    try:
        engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_recycle=300,
        )
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    except Exception as e:
        logger.error(f"❌ فشل إنشاء الـ engine: {e}")

Base = declarative_base()


def check_db_connection() -> tuple[bool, str]:
    """يعيد (True, "") إذا الاتصال ناجح، أو (False, رسالة) عند الفشل."""
    if engine is None:
        return False, "لم يتم إعداد DATABASE_URL في ملف .env"
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


def init_db(max_retries: int = 3, delay: int = 2) -> bool:
    """يحاول إنشاء الجداول مع إعادة المحاولة. لا يرمي استثناء."""
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
    """Dependency: يرفع HTTPException بدل أن يكسر التطبيق."""
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
