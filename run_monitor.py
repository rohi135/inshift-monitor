#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Runner برای GitHub Actions - اجرای یک‌باره با Proxy Pool
============================================================
این اسکریپت در GitHub Actions اجرا می‌شه و:
  1. توکن رو از env var (PORTAL_TOKEN) می‌خونه
  2. Proxy Pool رو راه‌اندازی می‌کنه
  3. درخواست به API می‌فرسته
  4. فیلتر می‌کنه
  5. نوتیف تلگرام می‌فرسته
  6. state.json رو آپدیت می‌کنه (workflow بعدی commit می‌کنه)

نحوه اجرای محلی برای تست:
  PORTAL_TOKEN=eyJ... TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... python run_monitor.py
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
from shift_monitor import (
    TokenManager, StateManager, JobFilter, Notifier, JobFetcher
)


# ============================================================
# خوندن تنظیمات از Environment Variables
# ============================================================
def get_config():
    # پارس کردن target_weekdays از env var
    # فرمت‌های قابل قبول:
    #   "monday,tuesday,friday"
    #   "دوشنبه,سه‌شنبه,جمعه"
    #   "0,1,4"
    #   "" (خالی = همه روزها)
    weekdays_str = os.getenv('FILTER_TARGET_WEEKDAYS', '')
    target_weekdays = [w.strip() for w in weekdays_str.split(',') if w.strip()] if weekdays_str else []

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
            'target_weekdays': target_weekdays,
            'date_filter_mode': os.getenv('FILTER_DATE_MODE', 'shift_date'),
        },
        'api_url': os.getenv('API_URL', 'https://staffing-api.example.com/api/seeker/v1/jobs?page=1'),
        'request_timeout_seconds': 15,
        'max_retries': 2,
    }


# ============================================================
# تابع اصلی
# ============================================================
async def main():
    logger.info("=" * 60)
    logger.info(f"🚀 GitHub Actions: Shift Monitor - {datetime.now(TEHRAN_TZ).strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    config = get_config()
    notifier = Notifier(config)

    # بررسی متغیرهای ضروری
    if not config['telegram_bot_token'] or not config['telegram_chat_id']:
        logger.error("❌ TELEGRAM_BOT_TOKEN یا TELEGRAM_CHAT_ID تنظیم نشده!")
        logger.error("در GitHub repo → Settings → Secrets and variables → Actions اضافه کن")
        return False

    # خوندن توکن (از env var یا فایل)
    token = os.getenv('PORTAL_TOKEN')
    if not token:
        # برای تست محلی، از فایل بخون
        token = TokenManager.load()

    if not token:
        logger.error("❌ توکن یافت نشد! PORTAL_TOKEN secret رو تنظیم کن.")
        notifier.notify_error('TOKEN_EXPIRED', 'PORTAL_TOKEN تنظیم نشده.')
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

    # تابع تست پروکسی - درخواست واقعی به API
    fetcher = JobFetcher(config)
    final_data = [None]  # برای ذخیره data موفق

    def test_proxy(proxy):
        """تست پروکسی با درخواست واقعی به API.

        این تابع همزمان هم پروکسی رو تست می‌کنه هم درخواست اصلی رو انجام می‌ده.
        اگه موفق بشه، data رو در final_data ذخیره می‌کنه.

        Returns:
            - True اگه پروکسی کار کرد و data دریافت شد
            - False در غیر این صورت
        """
        try:
            data, error = fetcher.fetch(token, proxy_url=proxy.url)
            # 200 = موفق کامل
            if data:
                final_data[0] = data
                return True
            # 401 = توکن منقضی شده (پروکسی کار می‌کنه ولی توکن مشکل داره)
            if error == 'TOKEN_EXPIRED':
                return True  # پروکسی سالمه، توکن مشکل داره
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

    # اگه data رو از تابع تست گرفتیم، استفاده کنیم
    data = final_data[0]

    if not data:
        # یعنی پروکسی کار کرد ولی توکن منقضی شده (error = TOKEN_EXPIRED)
        notifier.notify_error('TOKEN_EXPIRED')
        return False

    logger.info(f"✓ موفق! {len(data.get('data', []))} شیفت دریافت شد.")


    # فیلتر شیفت‌ها
    job_filter = JobFilter(config['filters'])
    state = StateManager.load()

    # آیا auto-apply فعال هست؟
    auto_apply = os.getenv('AUTO_APPLY', 'false').lower() == 'true'
    if auto_apply:
        logger.info("🤖 Auto-apply فعال هست. شیفت‌های match شده خودکار رزرو می‌شن.")
    else:
        logger.info("📢 Auto-Apply غیرفعال. فقط نوتیف تلگرام ارسال می‌شه.")

    matched_shifts = []
    new_shifts = []

    for job in data.get('data', []):
        if job_filter.matches(job):
            matched_shifts.append(job)
            # فقط شیفت‌هایی که قبلاً نوتیف ندادیم
            if not StateManager.is_notified(state, job.get('id')):
                new_shifts.append(job)

    logger.info(f"📊 کل: {len(data.get('data', []))} | Match: {len(matched_shifts)} | جدید: {len(new_shifts)}")

    # پردازش شیفت‌های جدید
    applicator = None
    if auto_apply:
        from shift_monitor import JobApplicator
        applicator = JobApplicator(config)

    for job in new_shifts:
        hash_id = job.get('hash_id', '')

        if auto_apply and hash_id:
            # بررسی اینکه قبلاً رزرو نکردیم
            if StateManager.is_applied(state, hash_id):
                logger.info(f"⏭️ شیفت {hash_id} قبلاً رزرو شده، skip.")
                StateManager.mark_notified(state, job.get('id'))
                continue

            # تلاش برای ثبت درخواست
            success, msg = applicator.apply(token, hash_id, proxy_url=proxy.url)

            if success:
                # ثبت موفق
                StateManager.mark_applied(state, hash_id)
                StateManager.mark_notified(state, job.get('id'))
                notifier.notify_shift_applied(job, msg)
                logger.info(f"✓ رزرو شد: {hash_id}")
            else:
                # ثبت ناموفق
                StateManager.mark_notified(state, job.get('id'))
                notifier.notify_apply_failed(job, msg)
                logger.warning(f"✗ رزرو ناموفق: {hash_id} - {msg}")

                # اگه توکن منقضی شده، بقیه رو هم نزن
                if 'TOKEN_EXPIRED' in msg:
                    notifier.notify_error('TOKEN_EXPIRED')
                    break

            await asyncio.sleep(2)  # جلوگیری از rate limit
        else:
            # فقط نوتیف بده (بدون رزرو)
            notifier.notify_shift_found(job)
            StateManager.mark_notified(state, job.get('id'))
            await asyncio.sleep(1)

    # آپدیت state
    state['last_check'] = datetime.now(TEHRAN_TZ).isoformat()
    StateManager.save(state)

    logger.info("✓ بررسی کامل شد.")
    return True


if __name__ == '__main__':
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
