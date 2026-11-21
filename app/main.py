from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request, status, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy import text
from typing import List

from . import schemas, crud
from .database import get_db, init_db, check_db_connection
from .routers import mobile_api                                    # ✨ سطر 1 — جديد


@asynccontextmanager
async def lifespan(app: FastAPI):
    ok = init_db(max_retries=3, delay=2)
    if not ok:
        print("⚠️ التطبيق يعمل لكن قاعدة البيانات غير متاحة. راجع /health لمعرفة الحالة.")
    yield


app = FastAPI(title="لوحة إدارة أكواد الاشتراك", lifespan=lifespan)

app.include_router(mobile_api.router)                              # ✨ سطر 2 — جديد

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# --- معالجات أخطاء قاعدة البيانات ---
@app.exception_handler(OperationalError)
async def db_operational_error_handler(request: Request, exc: OperationalError):
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error": "database_unavailable",
            "message": "تعذّر الاتصال بقاعدة البيانات. تحقق من تشغيل PostgreSQL وإعدادات الاتصال.",
            "details": str(exc.orig) if hasattr(exc, "orig") else str(exc),
        },
    )


@app.exception_handler(SQLAlchemyError)
async def db_sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "database_error",
            "message": "حدث خطأ في قاعدة البيانات.",
            "details": str(exc),
        },
    )


# --- فحص الحالة ---
@app.get("/health")
def health():
    ok, err = check_db_connection()
    if ok:
        return {"status": "ok", "database": "connected"}
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "degraded", "database": "disconnected", "message": err},
    )


# --- الصفحة الرئيسية ---
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ============================================================
# API Endpoints — الاشتراكات (المفتاح الأساسي هو code)
# ============================================================

@app.get("/api/subscriptions", response_model=List[schemas.SubscriptionResponse])
def list_subscriptions(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_subscriptions(db, skip=skip, limit=limit)


@app.get("/api/subscriptions/{code}", response_model=schemas.SubscriptionResponse)
def get_subscription(code: str, db: Session = Depends(get_db)):
    sub = crud.get_subscription(db, code)
    if not sub:
        raise HTTPException(status_code=404, detail=f"الكود '{code}' غير موجود")
    return sub


@app.post("/api/subscriptions", response_model=schemas.SubscriptionResponse, status_code=201)
def create_subscription(sub: schemas.SubscriptionCreate, db: Session = Depends(get_db)):
    existing = crud.get_subscription(db, sub.code)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"الكود '{sub.code.strip().upper()}' موجود مسبقاً",
        )
    return crud.create_subscription(db, sub)


@app.put("/api/subscriptions/{code}", response_model=schemas.SubscriptionResponse)
def update_subscription(code: str, sub: schemas.SubscriptionUpdate, db: Session = Depends(get_db)):
    updated = crud.update_subscription(db, code, sub)
    if not updated:
        raise HTTPException(status_code=404, detail=f"الكود '{code}' غير موجود")
    return updated


@app.delete("/api/subscriptions/{code}")
def delete_subscription(code: str, db: Session = Depends(get_db)):
    deleted = crud.delete_subscription(db, code)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"الكود '{code}' غير موجود")
    return {"message": f"تم حذف الكود '{code}' بنجاح"}


# --- نقطة إضافية: جلب اشتراك نشط لمستخدم ---
@app.get("/api/subscriptions/by-user/{user_id}", response_model=schemas.SubscriptionResponse)
def get_subscription_by_user(user_id: str, db: Session = Depends(get_db)):
    sub = crud.get_subscription_by_user(db, user_id)
    if not sub:
        raise HTTPException(status_code=404, detail="لا يوجد اشتراك نشط لهذا المستخدم")
    return sub


# ============================================================
# API Endpoints — الأجهزة (مستخرجة من جدول subscription_codes)
# ============================================================

@app.get("/api/users")
def list_devices(
    skip: int = 0,
    limit: int = 5000,
    q: str = Query(None, description="بحث بالمعرف/IP/اسم الجهاز"),
    db: Session = Depends(get_db),
):
    """قائمة الأجهزة/المستخدمين المعروفين من جدول الاشتراكات."""
    if q:
        return crud.search_devices(db, q, limit=limit)
    return crud.get_devices(db, skip=skip, limit=limit)


@app.get("/api/users/{device_id}")
def device_details(device_id: str, db: Session = Depends(get_db)):
    details = crud.get_device(db, device_id)
    if not details:
        raise HTTPException(status_code=404, detail=f"الجهاز '{device_id}' غير موجود")
    return details


@app.get("/api/users/{device_id}/ips")
def device_ips(device_id: str, db: Session = Depends(get_db)):
    """كل عناوين IP المرتبطة بجهاز معيّن (من كل اشتراكاته)."""
    return {"device_id": device_id, "ips": crud.get_ips_for_device(db, device_id)}


# ============================================================
# نقطة تشخيص سريعة
# ============================================================

@app.get("/api/stats")
def stats(db: Session = Depends(get_db)):
    """إحصاءات سريعة للوحة."""
    total = db.query(crud.models.Subscription).count()
    active = (
        db.query(crud.models.Subscription)
        .filter(crud.models.Subscription.is_active == True)
        .count()
    )
    bound = (
        db.query(crud.models.Subscription)
        .filter(
            crud.models.Subscription.bound_user_id.isnot(None),
            crud.models.Subscription.bound_user_id != "",
        )
        .count()
    )
    # ✨ جديد: عدد الأجهزة المسجّلة
    devices = (
        db.query(crud.models.Subscription)
        .filter(crud.models.Subscription.install_uuid.isnot(None))
        .count()
    )
    return {
        "total_subscriptions": total,
        "active_subscriptions": active,
        "bound_subscriptions": bound,
        "registered_devices": devices,                             # ✨ جديد
    }
