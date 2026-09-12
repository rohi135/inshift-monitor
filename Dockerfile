# Dockerfile برای مانیتور شیفت
# استفاده از Python 3.11 slim برای حجم کمتر

FROM python:3.11-slim

# تنظیم محیط
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# نصب پیش‌نیازهای سیستم
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# تنظیم دایرکتوری کار
WORKDIR /app

# کپی requirements اول (برای cache بهتر)
COPY requirements.txt .

# نصب وابستگی‌های پایتون
RUN pip install --no-cache-dir -r requirements.txt

# کپی بقیه فایل‌ها
COPY . .

# ساخت فایل‌های مورد نیاز
RUN touch token.txt state.json monitor.log && \
    chmod 600 token.txt

# اکسپوز پورت
EXPOSE ${PORT}

# اجرای اپ
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
