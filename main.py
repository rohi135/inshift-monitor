#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
این‌شیفت مانیتور - اپ FastAPI برای Railway
=========================================
این اپ شامل:
  - صفحه وب برای paste کردن توکن JWT
  - داشبورد وضعیت
  - Telegram Bot (همیشه روشن)
  - Scheduler برای چک هر ۳۰ دقیقه
  - Proxy Pool برای دسترسی به IP ایرانی

Deploy روی Railway:
  railway up
"""

import os
import json
import time
import asyncio
import logging
import requests
import threading
from pathlib import Path
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# ============================================================
# تنظیمات مسیر
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
TOKEN_PATH = BASE_DIR / "token.txt"
STATE_PATH = BASE_DIR / "state.json"
LOG_PATH = BASE_DIR / "monitor.log"

# ============================================================
# تایم‌زون
# ============================================================
TEHRAN_TZ = timezone(timedelta(hours=3, minutes=30))

# ============================================================
# لاگ
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================
# تنظیمات از Environment Variables
# ============================================================
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
WEB_PASSWORD = os.getenv('WEB_PASSWORD', 'admin123')  # پسورد پیش‌فرض
CHECK_INTERVAL_MINUTES = int(os.getenv('CHECK_INTERVAL_MINUTES', '30'))
PROXY_REFRESH_MINUTES = int(os.getenv('PROXY_REFRESH_MINUTES', '10'))

FILTERS = {
    "job_titles": os.getenv('FILTER_JOB_TITLES', 'Stow,Pick').split(','),
    "location": os.getenv('FILTER_LOCATION', 'دانش'),
    "start_hour": int(os.getenv('FILTER_START_HOUR', '7')),
    "start_minute": int(os.getenv('FILTER_START_MINUTE', '0')),
    "end_hour": int(os.getenv('FILTER_END_HOUR', '17')),
    "end_minute": int(os.getenv('FILTER_END_MINUTE', '0')),
    "exclude_full_capacity": os.getenv('EXCLUDE_FULL_CAPACITY', 'true').lower() == 'true',
}

API_URL = 'https://staffing.digikala.com/api/seeker/v1/jobs?page=1'

# ============================================================
# ایمپورت‌های داخلی
# ============================================================
import sys
sys.path.insert(0, str(BASE_DIR))

from proxy_pool import ProxyPool, Proxy
from inshift_monitor import (
    TokenManager, StateManager, JobFilter, Notifier
)

# ============================================================
# نمونه‌های سراسری
# ============================================================
proxy_pool: ProxyPool = None
bot_thread: threading.Thread = None
bot_stop_event = threading.Event()


# ============================================================
# توابع کمکی
# ============================================================
def now_str():
    return datetime.now(TEHRAN_TZ).strftime('%Y-%m-%d %H:%M:%S')


def send_telegram(text, parse_mode='HTML'):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': text,
        'parse_mode': parse_mode,
        'disable_web_page_preview': True
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        logger.error(f"خطا در ارسال تلگرام: {e}")
        return False


# ============================================================
# Job Monitor - اجرای چک هر ۳۰ دقیقه
# ============================================================
async def run_job_check():
    """چک شیفت‌ها با استفاده از پروکسی ایرانی."""
    logger.info("=" * 50)
    logger.info(f"شروع بررسی شیفت‌ها - {now_str()}")

    # بررسی توکن
    token = TokenManager.load()
    if not token or TokenManager.is_expired(token):
        send_telegram(
            "⚠️ <b>توکن منقضی شده!</b>\n\n"
            "لطفاً وارد صفحه وب بشو و توکن جدید رو paste کن.\n"
            "آدرس صفحه در Railway App URL شما."
        )
        logger.error("توکن یافت نشد یا منقضی شده.")
        return

    # گرفتن پروکسی
    proxy = await proxy_pool.get_proxy()
    if not proxy:
        send_telegram(
            "❌ <b>هیچ پروکسی ایرانی سالمی در دسترس نیست!</b>\n\n"
            "صبر کن تا proxy pool refresh بشه."
        )
        logger.error("پروکسی موجود نیست.")
        return

    # درخواست به API
    headers = {
        'Authorization': token,
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Origin': 'https://inshift.digikala.com',
        'Referer': 'https://inshift.digikala.com/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:155.0) Gecko/20100101 Firefox/155.0',
    }
    proxies = {'http': proxy.url, 'https': proxy.url}

    try:
        response = requests.get(
            API_URL,
            headers=headers,
            proxies=proxies,
            timeout=15,
            verify=True
        )

        if response.status_code == 401:
            send_telegram(
                "⚠️ <b>توکن منقضی شده!</b>\n\n"
                "لطفاً وارد صفحه وب بشو و توکن جدید رو paste کن."
            )
            await proxy_pool.mark_failed(proxy)
            return

        if response.status_code in (403, 451):
            logger.warning(f"پروکسی {proxy.url} بلاک شده. عوض می‌شه.")
            await proxy_pool.mark_failed(proxy)
            return

        if response.status_code != 200:
            logger.error(f"خطای HTTP {response.status_code}")
            return

        data = response.json()

    except requests.exceptions.ProxyError as e:
        logger.warning(f"پروکسی {proxy.url} کار نکرد: {e}")
        await proxy_pool.mark_failed(proxy)
        return
    except requests.exceptions.Timeout:
        logger.warning(f"تایم‌اوت با پروکسی {proxy.url}")
        await proxy_pool.mark_failed(proxy)
        return
    except Exception as e:
        logger.error(f"خطای غیرمنتظره: {e}")
        return

    # فیلتر شیفت‌ها
    job_filter = JobFilter(FILTERS)
    state = StateManager.load()

    matched_shifts = []
    new_shifts = []

    for job in data.get('data', []):
        if job_filter.matches(job):
            matched_shifts.append(job)
            if not StateManager.is_notified(state, job.get('id')):
                new_shifts.append(job)

    logger.info(f"کل شیفت‌ها: {len(data.get('data', []))}")
    logger.info(f"شیفت‌های match: {len(matched_shifts)}")
    logger.info(f"شیفت‌های جدید: {len(new_shifts)}")

    # ارسال نوتیف
    for job in new_shifts:
        notifier = Notifier(type('C', (), {
            'telegram_bot_token': TELEGRAM_BOT_TOKEN,
            'telegram_chat_id': TELEGRAM_CHAT_ID
        })())
        notifier.notify_shift_found(job)
        StateManager.mark_notified(state, job.get('id'))
        await asyncio.sleep(1)

    state['last_check'] = now_str()
    StateManager.save(state)

    logger.info("بررسی کامل شد.")


def schedule_check():
    """اجرای sync wrapper برای چک async."""
    asyncio.run(run_job_check())


def trigger_manual_check():
    """اجرا دستی چک - فراخوانی از token_updater_bot."""
    logger.info("🔍 اجرای دستی چک توسط کاربر...")
    # در یه thread جدا اجرا می‌کنیم تا بلاک نشه
    threading.Thread(target=schedule_check, daemon=True).start()


# ============================================================
# Telegram Bot در یه thread جدا
# ============================================================
def run_telegram_bot():
    """ربات تلگرام در پس‌زمینه."""
    import token_updater_bot as tub
    try:
        tub.run_bot(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, bot_stop_event)
    except Exception as e:
        logger.error(f"خطا در ربات تلگرام: {e}")


# ============================================================
# FastAPI App
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """مدیریت چرخه حیات اپ."""
    global proxy_pool, bot_thread

    logger.info("🚀 راه‌اندازی اپ...")

    # ایجاد token.txt اگه نباشه
    if not TOKEN_PATH.exists():
        TOKEN_PATH.touch()
        TOKEN_PATH.chmod(0o600)

    # راه‌اندازی proxy pool
    proxy_pool = ProxyPool(refresh_interval_minutes=PROXY_REFRESH_MINUTES)
    try:
        await proxy_pool.initialize()
    except Exception as e:
        logger.error(f"خطا در proxy pool: {e}")

    # شروع ربات تلگرام در thread جدا
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
        bot_thread.start()
        logger.info("🤖 ربات تلگرام شروع شد.")
    else:
        logger.warning("تلگرام تنظیم نشده. بدون ربات اجرا می‌شه.")

    # پیام شروع
    send_telegram(
        f"🚀 <b>این‌شیفت مانیتور فعال شد!</b>\n\n"
        f"⏰ فاصله چک: هر {CHECK_INTERVAL_MINUTES} دقیقه\n"
        f"🔄 Proxy Pool: {proxy_pool.get_stats()['alive']} پروکسی سالم\n"
        f"🎯 فیلتر: {','.join(FILTERS['job_titles'])} در {FILTERS['location']} ساعت "
        f"{FILTERS['start_hour']:02d}:{FILTERS['start_minute']:02d} تا "
        f"{FILTERS['end_hour']:02d}:{FILTERS['end_minute']:02d}\n\n"
        f"برای paste کردن توکن، به آدرس صفحه وب برو."
    )

    # شروع scheduler با APScheduler
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_job_check, 'interval', minutes=CHECK_INTERVAL_MINUTES,
        next_run_time=datetime.now()  # اجرای فوری
    )
    scheduler.start()
    logger.info(f"⏰ Scheduler شروع شد. هر {CHECK_INTERVAL_MINUTES} دقیقه.")

    yield

    # shutdown
    logger.info("🛑 توقف اپ...")
    bot_stop_event.set()
    scheduler.shutdown()


app = FastAPI(title="Inshift Monitor", lifespan=lifespan)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ============================================================
# Auth Middleware ساده
# ============================================================
def check_password(request: Request):
    """بررسی پسورد از cookie یا query param."""
    # از cookie
    auth = request.cookies.get('auth')
    if auth == WEB_PASSWORD:
        return True
    # از query
    if request.query_params.get('key') == WEB_PASSWORD:
        return True
    return False


# ============================================================
# Routes
# ============================================================
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """صفحه اصلی - لاگین یا داشبورد."""
    if not check_password(request):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": None
        })
    return RedirectResponse(url="/dashboard", status_code=302)


@app.post("/login", response_class=HTMLResponse)
async def login_post(request: Request, password: str = Form(...)):
    """بررسی پسورد."""
    if password == WEB_PASSWORD:
        response = RedirectResponse(url="/dashboard", status_code=302)
        response.set_cookie(
            key="auth", value=WEB_PASSWORD,
            httponly=True, max_age=86400 * 7, samesite='lax'
        )
        return response
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": "پسورد اشتباه است!"
    })


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """داشبورد با وضعیت سیستم."""
    if not check_password(request):
        return RedirectResponse(url="/", status_code=302)

    # اطلاعات توکن
    token = TokenManager.load()
    token_status = "❌ توکن موجود نیست"
    token_expire = None
    token_user_id = None
    days_left = None

    if token and TokenManager.is_valid_jwt_local(token):
        try:
            import base64
            payload_b64 = token.split('.')[1] + '=' * (4 - len(token.split('.')[1]) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            expire = payload.get('expire_time', 0)
            token_user_id = payload.get('user_id')
            token_expire = datetime.fromtimestamp(expire, TEHRAN_TZ).strftime('%Y-%m-%d %H:%M')
            days_left = (expire - int(time.time())) // 86400
            token_status = "✅ معتبر" if days_left > 0 else "❌ منقضی شده"
        except Exception:
            token_status = "❌ نامعتبر"

    # اطلاعات state
    state = StateManager.load()
    last_check = state.get('last_check')
    notified_count = len(state.get('notified_shifts', []))

    # اطلاعات proxy pool
    proxy_stats = proxy_pool.get_stats() if proxy_pool else None

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "token_status": token_status,
        "token_expire": token_expire,
        "token_user_id": token_user_id,
        "days_left": days_left,
        "last_check": last_check,
        "notified_count": notified_count,
        "proxy_stats": proxy_stats,
        "filters": FILTERS,
        "check_interval": CHECK_INTERVAL_MINUTES,
        "now": now_str(),
    })


@app.get("/update-token", response_class=HTMLResponse)
async def update_token_form(request: Request):
    """فرم آپدیت توکن."""
    if not check_password(request):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("update_token.html", {
        "request": request,
        "success": None,
        "error": None
    })


@app.post("/update-token", response_class=HTMLResponse)
async def update_token_submit(
    request: Request,
    token: str = Form(...)
):
    """ذخیره توکن جدید."""
    if not check_password(request):
        return RedirectResponse(url="/", status_code=302)

    token = token.strip()

    # پاک کردن پیشوند
    if token.lower().startswith('authorization:'):
        token = token.split(':', 1)[1].strip()
    if token.lower().startswith('bearer '):
        token = token[7:].strip()

    # اعتبارسنجی
    if not token or '.' not in token:
        return templates.TemplateResponse("update_token.html", {
            "request": request,
            "success": None,
            "error": "توکن معتبر نیست. باید فرمت JWT داشته باشه (سه قسمت با نقطه)."
        })

    try:
        import base64
        parts = token.split('.')
        if len(parts) != 3:
            raise ValueError("JWT باید ۳ قسمت داشته باشه")
        payload_b64 = parts[1] + '=' * (4 - len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        if 'user_id' not in payload and 'expire_time' not in payload:
            raise ValueError("payload نامعتبر")
    except Exception as e:
        return templates.TemplateResponse("update_token.html", {
            "request": request,
            "success": None,
            "error": f"توکن JWT نامعتبر: {e}"
        })

    # ذخیره
    TokenManager.save(token)
    logger.info(f"توکن جدید ذخیره شد توسط وب.")

    # نوتیف تلگرام
    send_telegram("✅ توکن جدید از طریق وب ذخیره شد!")

    return templates.TemplateResponse("update_token.html", {
        "request": request,
        "success": "توکن با موفقیت ذخیره شد!",
        "error": None
    })


@app.get("/api/status")
async def api_status(request: Request):
    """API برای گرفتن وضعیت."""
    if not check_password(request):
        raise HTTPException(status_code=401, detail="Unauthorized")

    token = TokenManager.load()
    state = StateManager.load()
    proxy_stats = proxy_pool.get_stats() if proxy_pool else None

    return {
        "now": now_str(),
        "token_valid": bool(token and not TokenManager.is_expired(token)),
        "last_check": state.get('last_check'),
        "notified_count": len(state.get('notified_shifts', [])),
        "proxy_pool": proxy_stats,
    }


@app.get("/api/test-check")
async def api_test_check(request: Request):
    """اجرای دستی چک (برای تست)."""
    if not check_password(request):
        raise HTTPException(status_code=401, detail="Unauthorized")

    # اجرای async در background
    asyncio.create_task(run_job_check())
    return {"status": "started", "message": "چک شروع شد. لاگ‌ها رو ببین."}


@app.post("/api/refresh-proxies")
async def api_refresh_proxies(request: Request):
    """Refresh دستی proxy pool."""
    if not check_password(request):
        raise HTTPException(status_code=401, detail="Unauthorized")

    if proxy_pool:
        asyncio.create_task(proxy_pool.refresh())
        return {"status": "started", "message": "در حال refresh پروکسی‌ها..."}
    return {"status": "error", "message": "proxy pool هنوز راه‌اندازی نشده."}


@app.get("/logout")
async def logout():
    """خروج."""
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie('auth')
    return response


# ============================================================
# برای اجرای مستقیم
# ============================================================
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
