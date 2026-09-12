#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Runner برای GitHub Actions - اجرای یک‌باره با Proxy Pool
============================================================
این اسکریپت در GitHub Actions اجرا می‌شه و:
  1. توکن رو از env var (INSHIFT_TOKEN) می‌خونه
  2. Proxy Pool رو راه‌اندازی می‌کنه
  3. درخواست به API می‌فرسته
  4. فیلتر می‌کنه
  5. نوتیف تلگرام می‌فرسته
  6. state.json رو آپدیت می‌کنه (workflow بعدی commit می‌کنه)

نحوه اجرای محلی برای تست:
  INSHIFT_TOKEN=eyJ... TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... python run_monitor.py
"""

import os
import sys
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ============================================================
# تنظیمات لاگ
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

TEHRAN_TZ = timezone(timedelta(hours=3, minutes=30))

# ============================================================
# اضافه کردن مسیر فعلی
# ============================================================
sys.path.insert(0, str(Path(__file__).resolve().parent))

# ============================================================
# ایمپورت‌های داخلی
# ============================================================
from proxy_pool import ProxyPool
from inshift_monitor import (
    TokenManager, StateManager, JobFilter, Notifier, JobFetcher
)


# ============================================================
# خوندن تنظیمات از Environment Variables
# ============================================================
def get_config():
    return {
        'telegram_bot_token': os.getenv('TELEGRAM_BOT_TOKEN', ''),
        'telegram_chat_id': os.getenv('TELEGRAM_CHAT_ID', ''),
        'filters': {
            'job_titles': [
                t.strip() for t in os.getenv('FILTER_JOB_TITLES', 'Stow,Pick').split(',')
                if t.strip()
            ],
            'location': os.getenv('FILTER_LOCATION', 'دانش'),
            'start_hour': int(os.getenv('FILTER_START_HOUR', '7')),
            'start_minute': int(os.getenv('FILTER_START_MINUTE', '0')),
            'end_hour': int(os.getenv('FILTER_END_HOUR', '17')),
            'end_minute': int(os.getenv('FILTER_END_MINUTE', '0')),
            'exclude_full_capacity': os.getenv('EXCLUDE_FULL_CAPACITY', 'true').lower() == 'true',
        },
        'api_url': 'https://staffing.digikala.com/api/seeker/v1/jobs?page=1',
        'request_timeout_seconds': 15,
        'max_retries': 2,
    }


# ============================================================
# تابع اصلی
# ============================================================
async def main():
    logger.info("=" * 60)
    logger.info(f"🚀 GitHub Actions: Inshift Monitor - {datetime.now(TEHRAN_TZ).strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    config = get_config()
    notifier = Notifier(config)

    # بررسی متغیرهای ضروری
    if not config['telegram_bot_token'] or not config['telegram_chat_id']:
        logger.error("❌ TELEGRAM_BOT_TOKEN یا TELEGRAM_CHAT_ID تنظیم نشده!")
        logger.error("در GitHub repo → Settings → Secrets and variables → Actions اضافه کن")
        return False

    # خوندن توکن (از env var یا فایل)
    token = os.getenv('INSHIFT_TOKEN')
    if not token:
        # برای تست محلی، از فایل بخون
        token = TokenManager.load()

    if not token:
        logger.error("❌ توکن یافت نشد! INSHIFT_TOKEN secret رو تنظیم کن.")
        notifier.notify_error('TOKEN_EXPIRED', 'INSHIFT_TOKEN تنظیم نشده.')
        return False

    if TokenManager.is_expired(token):
        logger.error("❌ توکن منقضی شده!")
        notifier.notify_error('TOKEN_EXPIRED')
        return False

    info = TokenManager.get_info(token)
    if info:
        logger.info(f"✓ توکن معتبر. User ID: {info.get('user_id')}")

    # راه‌اندازی Proxy Pool - حالت lazy (بدون health check کامل)
    logger.info("🌐 در حال راه‌اندازی Proxy Pool (lazy mode)...")
    pool = ProxyPool(refresh_interval_minutes=60)
    try:
        await pool.initialize(lazy=True)
    except Exception as e:
        logger.error(f"خطا در proxy pool: {e}")

    stats = pool.get_stats()
    logger.info(f"✓ Proxy Pool: {stats['total']} پروکسی fetch شد (بدون تست)")

    if stats['total'] == 0:
        logger.error("❌ هیچ پروکسی‌ای fetch نشد!")
        notifier.notify_error('PROXY_ERROR', 'هیچ پروکسی‌ای از منابع fetch نشد.')
        return False

    # تابع تست پروکسی - درخواست واقعی به API دیجی‌کالا
    fetcher = JobFetcher(config)

    def test_proxy(proxy):
        """تست پروکسی با درخواست واقعی به API.

        Returns:
            - True اگه پروکسی کار کرد (HTTP 200 یا 401)
            - False در غیر این صورت
        """
        try:
            data, error = fetcher.fetch(token, proxy_url=proxy.url)
            # 200 = موفق کامل، 401 = پروکسی کار می‌کنه ولی توکن مشکل داره (برای پروکسی مهم نیست)
            if data or error == 'TOKEN_EXPIRED':
                return True
            return False
        except Exception:
            return False

    # پیدا کردن اولین پروکسی کارکردی
    logger.info("🔍 تست پروکسی‌ها یکی یکی تا پیدا کردن اولین کارکردی...")
    proxy = await pool.find_working_proxy(test_proxy, max_attempts=15)

    if not proxy:
        logger.error("❌ هیچ پروکسی کارکردی پیدا نشد!")
        notifier.notify_error('PROXY_ERROR', 'هیچ پروکسی کارکردی پیدا نشد.')
        return False

    logger.info(f"✓ استفاده از پروکسی: {proxy.url}")

    # حالا با پروکسی کارکردی، درخواست اصلی رو بزن
    data, error = fetcher.fetch(token, proxy_url=proxy.url)

    if not data:
        if error == 'TOKEN_EXPIRED':
            notifier.notify_error('TOKEN_EXPIRED')
        else:
            notifier.notify_error(error or 'UNKNOWN_ERROR')
        return False

    logger.info(f"✓ موفق! {len(data.get('data', []))} شیفت دریافت شد.")

    # فیلتر شیفت‌ها
    job_filter = JobFilter(config['filters'])
    state = StateManager.load()

    matched_shifts = []
    new_shifts = []

    for job in data.get('data', []):
        if job_filter.matches(job):
            matched_shifts.append(job)
            if not StateManager.is_notified(state, job.get('id')):
                new_shifts.append(job)

    logger.info(f"📊 کل: {len(data.get('data', []))} | Match: {len(matched_shifts)} | جدید: {len(new_shifts)}")

    # ارسال نوتیف برای شیفت‌های جدید
    for job in new_shifts:
        notifier.notify_shift_found(job)
        StateManager.mark_notified(state, job.get('id'))
        await asyncio.sleep(1)  # جلوگیری از rate limit

    # آپدیت state
    state['last_check'] = datetime.now(TEHRAN_TZ).isoformat()
    StateManager.save(state)

    logger.info("✓ بررسی کامل شد.")
    return True


if __name__ == '__main__':
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
