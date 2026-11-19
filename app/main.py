from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from typing import List

from . import schemas, crud
from .database import get_db, init_db, check_db_connection


@asynccontextmanager
async def lifespan(app: FastAPI):
    ok = init_db(max_retries=3, delay=2)
    if not ok:
        print("⚠️ التطبيق يعمل لكن قاعدة البيانات غير متاحة. راجع /health لمعرفة الحالة.")
    yield


app = FastAPI(title="لوحة إدارة الاشتراكات", lifespan=lifespan)

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


# --- API Endpoints ---
@app.get("/api/subscriptions", response_model=List[schemas.SubscriptionResponse])
def list_subscriptions(db: Session = Depends(get_db)):
    return crud.get_subscriptions(db)


@app.get("/api/subscriptions/{sub_id}", response_model=schemas.SubscriptionResponse)
def get_subscription(sub_id: int, db: Session = Depends(get_db)):
    sub = crud.get_subscription(db, sub_id)
    if not sub:
        raise HTTPException(status_code=404, detail="الاشتراك غير موجود")
    return sub


@app.post("/api/subscriptions", response_model=schemas.SubscriptionResponse, status_code=201)
def create_subscription(sub: schemas.SubscriptionCreate, db: Session = Depends(get_db)):
    return crud.create_subscription(db, sub)


@app.put("/api/subscriptions/{sub_id}", response_model=schemas.SubscriptionResponse)
def update_subscription(sub_id: int, sub: schemas.SubscriptionUpdate, db: Session = Depends(get_db)):
    updated = crud.update_subscription(db, sub_id, sub)
    if not updated:
        raise HTTPException(status_code=404, detail="الاشتراك غير موجود")
    return updated


@app.delete("/api/subscriptions/{sub_id}")
def delete_subscription(sub_id: int, db: Session = Depends(get_db)):
    deleted = crud.delete_subscription(db, sub_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="الاشتراك غير موجود")
    return {"message": "تم الحذف بنجاح"}
