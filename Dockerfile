# ================================
# Stage 1: بناء التبعيات
# ================================
FROM python:3.11-slim AS builder

WORKDIR /build

# تثبيت أدوات البناء المطلوبة لـ psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --user -r requirements.txt


# ================================
# Stage 2: الصورة النهائية
# ================================
FROM python:3.11-slim

# متغيرات بيئة
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/home/app/.local/bin:$PATH

# مكتبات runtime لـ psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# مستخدم غير جذري
RUN useradd -m -u 1000 app

WORKDIR /app

# نسخ التبعيات المثبتة من المرحلة السابقة
COPY --from=builder --chown=app:app /root/.local /home/app/.local

# نسخ كود المشروع
COPY --chown=app:app . .

USER app

EXPOSE 8000

# فحص صحة الحاوية عبر /health
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
