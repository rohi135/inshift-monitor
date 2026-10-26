#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
مانیتور شیفت - ماژول اصلی
================================
این ماژول شامل کلاس‌های مشترک برای:
  - مدیریت توکن JWT
  - مدیریت وضعیت (برای جلوگیری از اسپم)
  - فیلتر شیفت‌ها
  - نوتیفیکیشن تلگرام + Termux

نحوه استفاده:
  - روی گوشی (Termux): اجرای مستقیم این فایل با cron
  - روی Railway: استفاده از main.py که این کلاس‌ها رو import می‌کنه

طرز کار:
  1) TokenManager.load() → خوندن توکن از فایل
  2) TokenManager.is_expired(token) → بررسی انقضا
  3) JobFetcher.fetch(token, proxy_url=None) → درخواست به API
  4) JobFilter.matches(job) → بررسی فیلتر
  5) Notifier.notify_shift_found(job) → ارسال نوتیف
"""

import os
import sys
import json
import time
import base64
import logging
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ============================================================
# تنظیمات مسیر فایل‌ها
# ============================================================
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
TOKEN_PATH = SCRIPT_DIR / "token.txt"
STATE_PATH = SCRIPT_DIR / "state.json"
LOG_PATH = SCRIPT_DIR / "monitor.log"

# ============================================================
# تایم‌زون تهران
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
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


# ============================================================
# کلاس مدیریت توکن
# ============================================================
class TokenManager:
    @staticmethod
    def load():
        if not TOKEN_PATH.exists():
            return None
        with open(TOKEN_PATH, 'r', encoding='utf-8') as f:
            return f.read().strip()

    @staticmethod
    def save(token):
        with open(TOKEN_PATH, 'w', encoding='utf-8') as f:
            f.write(token.strip())
        try:
            os.chmod(TOKEN_PATH, 0o600)
        except Exception:
            pass  # روی ویندوز کار نمی‌کنه
        logger.info("توکن جدید ذخیره شد.")

    @staticmethod
    def is_valid_jwt_local(token):
        """بررسی اینکه آیا این یه JWT معتبر هست."""
        if not token or '.' not in token:
            return False
        parts = token.split('.')
        if len(parts) != 3:
            return False
        try:
            payload_b64 = parts[1] + '=' * (4 - len(parts[1]) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            return 'user_id' in payload or 'expire_time' in payload
        except Exception:
            return False

    @staticmethod
    def is_expired(token):
        """بررسی انقضای توکن JWT."""
        if not token or '.' not in token:
            return True
        try:
            parts = token.split('.')
            if len(parts) != 3:
                return True
            payload_b64 = parts[1] + '=' * (4 - len(parts[1]) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            expire_time = payload.get('expire_time', 0)
            now = int(time.time())
            return now >= expire_time
        except Exception as e:
            logger.warning(f"خطا در decode توکن: {e}")
            return True

    @staticmethod
    def hours_until_expiry(token):
        """ساعت‌های باقی‌مانده تا انقضای توکن. منفی = منقضی شده."""
        if not token or '.' not in token:
            return -1
        try:
            parts = token.split('.')
            if len(parts) != 3:
                return -1
            payload_b64 = parts[1] + '=' * (4 - len(parts[1]) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            expire_time = payload.get('expire_time', 0)
            now = int(time.time())
            return max(-1, (expire_time - now) // 3600)
        except Exception:
            return -1

    @staticmethod
    def get_info(token):
        """اطلاعات توکن برای نمایش."""
        if not token or '.' not in token:
            return None
        try:
            parts = token.split('.')
            if len(parts) != 3:
                return None
            payload_b64 = parts[1] + '=' * (4 - len(parts[1]) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            return {
                'user_id': payload.get('user_id'),
                'expire_time': payload.get('expire_time'),
                'status': payload.get('payload', {}).get('status'),
            }
        except Exception:
            return None


# ============================================================
# کلاس مدیریت وضعیت
# ============================================================
class StateManager:
    @staticmethod
    def load():
        default = {
            "notified_shifts": [],
            "applied_shifts": [],
            "applied_dates": [],  # تاریخ‌هایی که برایشون شیفت رزرو کردیم
            "last_check": None
        }
        if not STATE_PATH.exists():
            return default
        try:
            with open(STATE_PATH, 'r', encoding='utf-8') as f:
                state = json.load(f)
                # اطمینان از وجود همه کلیدها
                if 'notified_shifts' not in state:
                    state['notified_shifts'] = []
                if 'applied_shifts' not in state:
                    state['applied_shifts'] = []
                if 'applied_dates' not in state:
                    state['applied_dates'] = []
                return state
        except Exception:
            return default

    @staticmethod
    def save(state):
        with open(STATE_PATH, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    @staticmethod
    def is_notified(state, shift_id):
        return str(shift_id) in state.get('notified_shifts', [])

    @staticmethod
    def mark_notified(state, shift_id):
        if 'notified_shifts' not in state:
            state['notified_shifts'] = []
        state['notified_shifts'].append(str(shift_id))
        # نگه‌داشتن فقط ۱۰۰ آی‌دی آخر
        state['notified_shifts'] = state['notified_shifts'][-100:]

    @staticmethod
    def is_applied(state, hash_id):
        """آیا قبلاً برای این شیفت درخواست ثبت شده؟"""
        return str(hash_id) in state.get('applied_shifts', [])

    @staticmethod
    def mark_applied(state, hash_id):
        """ثبت اینکه برای این شیفت درخواست دادیم."""
        if 'applied_shifts' not in state:
            state['applied_shifts'] = []
        state['applied_shifts'].append(str(hash_id))
        # نگه‌داشتن فقط ۱۰۰ آی‌دی آخر
        state['applied_shifts'] = state['applied_shifts'][-100:]

    @staticmethod
    def is_date_applied(state, date_str):
        """آیا برای این تاریخ قبلاً شیفت رزرو کردیم؟

        Args:
            date_str: تاریخ به فرمت 'YYYY-MM-DD'

        Returns:
            bool: True اگه برای این تاریخ قبلاً رزرو کردیم
        """
        return str(date_str) in state.get('applied_dates', [])

    @staticmethod
    def mark_date_applied(state, date_str):
        """ثبت اینکه برای این تاریخ شیفت رزرو کردیم."""
        if 'applied_dates' not in state:
            state['applied_dates'] = []
        if str(date_str) not in state['applied_dates']:
            state['applied_dates'].append(str(date_str))
            # نگه‌داشتن فقط ۳۰ تاریخ آخر (یک ماه)
            state['applied_dates'] = state['applied_dates'][-30:]

    @staticmethod
    def cleanup_old_dates(state):
        """پاک کردن تاریخ‌های گذشته (قدیمی‌تر از امروز).

        این کار کمک می‌کنه state.json کوچیک بمونه و
        تاریخ‌های قدیمی حذف بشن.
        """
        from datetime import datetime, timezone, timedelta
        TEHRAN_TZ = timezone(timedelta(hours=3, minutes=30))
        today = datetime.now(TEHRAN_TZ).date()
        applied_dates = state.get('applied_dates', [])
        # فقط تاریخ‌های امروز یا آینده رو نگه‌دار
        kept = []
        for d in applied_dates:
            try:
                parsed = datetime.strptime(str(d), '%Y-%m-%d').date()
                if parsed >= today:
                    kept.append(str(d))
            except Exception:
                pass  # اگه parse نشد، نگه‌دار
        state['applied_dates'] = kept


# ============================================================
# کلاس دریافت شیفت‌ها
# ============================================================
class JobFetcher:
    def __init__(self, config=None):
        self.config = config or {}
        # API URL from config or env var (don't hardcode the actual URL)
        self.url = self.config.get('api_url') or os.getenv(
            'API_URL',
            'https://staffing-api.example.com/api/seeker/v1/jobs?page=1'
        )
        self.timeout = self.config.get('request_timeout_seconds', 15)
        self.max_retries = self.config.get('max_retries', 2)

    def fetch(self, token, proxy_url=None):
        """
        درخواست به API.

        Args:
            token: توکن JWT
            proxy_url: آدرس پروکسی (مثل socks5://1.2.3.4:1080) یا None

        Returns:
            tuple: (data, error)
        """
        # Origin/Referer from env var (don't hardcode)
        origin = os.getenv('PORTAL_ORIGIN', 'https://shift-portal.example.com')
        headers = {
            'Authorization': token,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Origin': origin,
            'Referer': origin + '/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:155.0) Gecko/20100101 Firefox/155.0',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
        }

        proxies = None
        if proxy_url:
            proxies = {'http': proxy_url, 'https': proxy_url}

        for attempt in range(self.max_retries + 1):
            try:
                response = requests.get(
                    self.url,
                    headers=headers,
                    proxies=proxies,
                    timeout=self.timeout,
                    verify=True  # TLS verification روشن
                )

                if response.status_code == 200:
                    return response.json(), None

                if response.status_code == 401:
                    return None, 'TOKEN_EXPIRED'

                if response.status_code in (403, 451):
                    return None, 'IP_BLOCKED'

                if response.status_code >= 500:
                    logger.warning(f"خطای سرور {response.status_code}. تلاش {attempt+1}")
                    time.sleep(2)
                    continue

                return None, f'HTTP_{response.status_code}'

            except requests.exceptions.ProxyError as e:
                logger.warning(f"خطای پروکسی: {e}")
                return None, 'PROXY_ERROR'

            except requests.exceptions.Timeout:
                logger.warning(f"تایم‌اوت. تلاش {attempt+1}")
                time.sleep(2)

            except requests.exceptions.ConnectionError as e:
                # اگه با پروکسی بود، احتمالاً پروکسی مرده
                if proxy_url:
                    return None, 'PROXY_ERROR'
                logger.warning(f"خطای اتصال (احتمالاً اینترنت قطع): {e}")
                return None, 'NO_INTERNET'

            except Exception as e:
                logger.error(f"خطای غیرمنتظره: {e}")
                return None, 'UNKNOWN_ERROR'

        return None, 'MAX_RETRIES_EXCEEDED'


# ============================================================
# کلاس ثبت درخواست شیفت (Auto-Apply)
# ============================================================
class JobApplicator:
    """ثبت درخواست شیفت با POST به API.

    API endpoint: POST /api/seeker/v1/jobs
    Body: {"job_post_id": "<hash_id>"}
    Response success: {"message":"درخواست شیفت با موفقیت انجام شد."}
    """

    APPLY_URL_PATH = '/api/seeker/v1/jobs'  # بدون domain - از API_URL گرفته می‌شه

    def __init__(self, config=None):
        self.config = config or {}
        # ساختن URL از API_URL اصلی (به‌جای hardcode کردن)
        api_url = self.config.get('api_url') or os.getenv(
            'API_URL',
            'https://staffing-api.example.com/api/seeker/v1/jobs?page=1'
        )
        # استخراج base URL (بدون query string و path آخر)
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(api_url)
        self.base_url = f"{parsed.scheme}://{parsed.netloc}"
        self.apply_url = self.base_url + self.APPLY_URL_PATH
        # timeout کوتاه‌تر برای apply (تا سریع‌تر با پروکسی بعدی retry کنیم)
        self.timeout = int(os.getenv('APPLY_TIMEOUT_SECONDS', '10'))

    def apply(self, token, hash_id, proxy_url=None):
        """ثبت درخواست برای یه شیفت.

        Args:
            token: توکن JWT
            hash_id: hash_id شیفت (مثل "55511845536")
            proxy_url: آدرس پروکسی (اختیاری)

        Returns:
            tuple: (success: bool, message: str)
        """
        origin = os.getenv('PORTAL_ORIGIN', 'https://shift-portal.example.com')

        headers = {
            'Authorization': token,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Content-Type': 'application/json',
            'Origin': origin,
            'Referer': origin + '/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:155.0) Gecko/20100101 Firefox/155.0',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
        }

        body = {"job_post_id": str(hash_id)}
        proxies = {'http': proxy_url, 'https': proxy_url} if proxy_url else None

        try:
            logger.info(f"📝 ثبت درخواست برای شیفت {hash_id}...")
            response = requests.post(
                self.apply_url,
                headers=headers,
                json=body,
                proxies=proxies,
                timeout=self.timeout,
                verify=True
            )

            if response.status_code == 200:
                try:
                    data = response.json()
                    msg = data.get('message', 'موفق')
                    logger.info(f"✓ ثبت درخواست موفق: {msg}")
                    return True, msg
                except Exception:
                    logger.info("✓ ثبت درخواست موفق (بدون message)")
                    return True, 'موفق'

            if response.status_code == 401:
                logger.error("✗ توکن منقضی شده")
                return False, 'TOKEN_EXPIRED'

            if response.status_code in (403, 451):
                logger.error(f"✗ IP بلاک شده: {response.status_code}")
                return False, 'IP_BLOCKED'

            if response.status_code == 422 or response.status_code == 400:
                # احتمالاً duplicate_application یا تداخل زمانی یا خطای validation
                try:
                    data = response.json()
                    msg = data.get('message', data.get('error', 'خطای validation'))
                    # ★ اگه تداخل زمانی یا duplicate بود، یعنی اون روز شیفت داریم
                    # این هم به‌عنوان CONFLICT ثبت می‌شه (تا اسکریپت دونوعه اون روز رزرو نکنه)
                    msg_lower = str(msg).lower()
                    if 'duplicate' in msg_lower or 'تداخل' in str(msg) or 'conflict' in msg_lower:
                        logger.warning(f"✗ تداخل زمانی/duplicate: {msg}")
                        return False, f'CONFLICT: {msg}'
                    else:
                        logger.warning(f"✗ خطای اعتبارسنجی: {msg}")
                        return False, f'VALIDATION_ERROR: {msg}'
                except Exception:
                    return False, f'HTTP_{response.status_code}'

            logger.error(f"✗ خطای HTTP {response.status_code}: {response.text[:200]}")
            return False, f'HTTP_{response.status_code}'

        except requests.exceptions.ProxyError:
            logger.error("✗ خطای پروکسی")
            return False, 'PROXY_ERROR'
        except requests.exceptions.Timeout:
            logger.error("✗ تایم‌اوت")
            return False, 'TIMEOUT'
        except Exception as e:
            logger.error(f"✗ خطای غیرمنتظره: {e}")
            return False, f'UNKNOWN_ERROR: {e}'


# ============================================================
# کلاس فیلتر شیفت‌ها
# ============================================================
class JobFilter:
    # mapping روزهای هفته به اعداد (0=دوشنبه ... 6=یکشنبه)
    # فرمت مناسب با Python weekday()
    WEEKDAY_NAMES = {
        'monday': 0, 'mon': 0, 'دوشنبه': 0,
        'tuesday': 1, 'tue': 1, 'سه‌شنبه': 1, 'سه شنبه': 1,
        'wednesday': 2, 'wed': 2, 'چهارشنبه': 2,
        'thursday': 3, 'thu': 3, 'پنج‌شنبه': 3, 'پنج شنبه': 3,
        'friday': 4, 'fri': 4, 'جمعه': 4,
        'saturday': 5, 'sat': 5, 'شنبه': 5,
        'sunday': 6, 'sun': 6, 'یکشنبه': 6,
    }

    def __init__(self, filters):
        self.job_titles = [t.lower() for t in filters.get('job_titles', [])]
        self.location = filters.get('location', '')
        self.start_hour = filters.get('start_hour', 7)
        self.start_minute = filters.get('start_minute', 0)
        self.end_hour = filters.get('end_hour', 17)
        self.end_minute = filters.get('end_minute', 0)
        self.exclude_full_capacity = filters.get('exclude_full_capacity', True)

        # روزهای هفته مجاز
        # فرمت: ["monday", "tuesday", "friday"] یا ["دوشنبه", "سه‌شنبه", "جمعه"]
        # یا عدد: [0, 1, 4]  (0=دوشنبه)
        # اگه خالی باشه = همه روزها
        self.target_weekdays = self._parse_weekdays(filters.get('target_weekdays', []))

        # چطور تاریخ شیفت رو بررسی کنیم:
        # - 'shift_date' = تاریخ خود شیفت (توصیه شده)
        # - 'today' = فقط شیفت‌های امروز رو شمار میار
        # - 'tomorrow' = فقط شیفت‌های فردا
        # - 'this_week' = همه شیفت‌های این هفته
        self.date_filter_mode = filters.get('date_filter_mode', 'shift_date')

    def _parse_weekdays(self, weekdays):
        """تبدیل لیست روزهای هفته به اعداد 0-6"""
        if not weekdays:
            return []  # یعنی همه روزها مجازن

        result = set()
        for w in weekdays:
            if isinstance(w, int):
                if 0 <= w <= 6:
                    result.add(w)
            else:
                w_str = str(w).lower().strip()
                if w_str in self.WEEKDAY_NAMES:
                    result.add(self.WEEKDAY_NAMES[w_str])
        return sorted(list(result))

    def matches(self, job):
        # بررسی job_title
        title = (job.get('job_title') or '').lower()
        if self.job_titles:
            if not any(t in title for t in self.job_titles):
                return False

        # بررسی location
        loc = job.get('location', '')
        if self.location and self.location not in loc:
            return False

        # بررسی ساعت
        ts = job.get('time_scope', {})
        if not ts:
            return False
        if ts.get('start_hour') != self.start_hour:
            return False
        if ts.get('start_minute') != self.start_minute:
            return False
        if ts.get('end_hour') != self.end_hour:
            return False
        if ts.get('end_minute') != self.end_minute:
            return False

        # بررسی ظرفیت
        if self.exclude_full_capacity:
            tags = job.get('tags', []) or []
            if 'full_capacity' in tags:
                return False

        # بررسی روز هفته
        if self.target_weekdays:
            if not self._matches_weekday(job):
                return False

        return True

    def _matches_weekday(self, job):
        """بررسی اینکه آیا شیفت در یکی از روزهای مدنظر هست یا نه."""
        # گرفتن تاریخ شیفت
        date_str = (job.get('date', {}) or {}).get('date', '')
        if not date_str:
            return True  # اگه تاریخ نداشت، نادیده بگیر

        try:
            # فرمت: "2026-09-13 00:00:00.000000"
            shift_date = datetime.strptime(date_str[:10], '%Y-%m-%d')
            # Python weekday(): 0=Monday, 6=Sunday
            shift_weekday = shift_date.weekday()

            if self.date_filter_mode == 'today':
                # فقط شیفت‌های امروز رو شمار بگیر
                today = datetime.now(TEHRAN_TZ).date()
                if shift_date.date() != today:
                    return False
                # و روز هفته هم باید مدنظر باشه
                return shift_weekday in self.target_weekdays

            elif self.date_filter_mode == 'shift_date':
                # روز هفته خود شیفت رو چک کن
                return shift_weekday in self.target_weekdays

            elif self.date_filter_mode == 'this_week':
                # هر شیفت این هفته که روز مدنظر باشه
                return shift_weekday in self.target_weekdays

            else:
                return True
        except Exception as e:
            logger.warning(f"خطا در parse تاریخ شیفت: {e}")
            return True  # اگه نتونست parse کنه، نادیده بگیر


# ============================================================
# کلاس نوتیفیکیشن
# ============================================================
class Notifier:
    def __init__(self, config):
        # config می‌تونه dict یا object باشه
        if isinstance(config, dict):
            self.bot_token = config.get('telegram_bot_token', '')
            self.chat_id = config.get('telegram_chat_id', '')
        else:
            self.bot_token = getattr(config, 'telegram_bot_token', '')
            self.chat_id = getattr(config, 'telegram_chat_id', '')

    def send_telegram(self, text, parse_mode='HTML'):
        if not self.bot_token or not self.chat_id:
            logger.warning("تلگرام تنظیم نشده.")
            return False
        if 'PUT_YOUR' in self.bot_token or 'PUT_YOUR' in self.chat_id:
            logger.warning("تلگرام placeholder است.")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            'chat_id': self.chat_id,
            'text': text,
            'parse_mode': parse_mode,
            'disable_web_page_preview': True
        }
        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                return True
            logger.error(f"خطای تلگرام: {r.status_code} - {r.text}")
            return False
        except Exception as e:
            logger.error(f"خطا در ارسال تلگرام: {e}")
            return False

    def send_termux_notification(self, title, content):
        try:
            os.system(
                f'termux-notification --title "{title}" '
                f'--content "{content}" --sound --vibrate'
            )
        except Exception as e:
            logger.debug(f"Termux notification در دسترس نیست: {e}")

    def notify_shift_found(self, job):
        import html as html_module
        title = html_module.escape(str(job.get('job_title', '')))
        location = html_module.escape(str(job.get('location', '')))
        ts = job.get('time_scope', {})
        start = f"{ts.get('start_hour', 0):02d}:{ts.get('start_minute', 0):02d}"
        end = f"{ts.get('end_hour', 0):02d}:{ts.get('end_minute', 0):02d}"
        price = job.get('price', 0)
        price_t = f"{price:,}" if price else "0"
        date = (job.get('date', {}) or {}).get('date', '')[:10]
        hash_id = job.get('hash_id', '')

        # فرمت زیبا برای تلگرام
        tg_text = (
            "🎯 <b>شیفت مدنظر پیدا شد!</b>\n\n"
            f"💼 <b>عنوان:</b> {title}\n"
            f"📍 <b>شعبه:</b> {location}\n"
            f"📅 <b>تاریخ:</b> {date}\n"
            f"🕐 <b>ساعت:</b> {start} تا {end}\n"
            f"💰 <b>دستمزد:</b> {price_t} تومان\n"
            f"🆔 <b>کد:</b> <code>{hash_id}</code>\n\n"
            f"🔗 <a href=\"https://shift-portal.example.com/jobs\">باز کردن سایت</a>"
        )
        self.send_telegram(tg_text)

        # نوتیف گوشی (فقط روی Termux کار می‌کنه)
        notif_content = f"{title} | {location} | {start}-{end}"
        self.send_termux_notification("🎯 شیفت پیدا شد!", notif_content)

    def notify_shift_applied(self, job, message='موفق'):
        """پیام موفقیت در ثبت درخواست شیفت."""
        import html as html_module
        title = html_module.escape(str(job.get('job_title', '')))
        location = html_module.escape(str(job.get('location', '')))
        ts = job.get('time_scope', {})
        start = f"{ts.get('start_hour', 0):02d}:{ts.get('start_minute', 0):02d}"
        end = f"{ts.get('end_hour', 0):02d}:{ts.get('end_minute', 0):02d}"
        price = job.get('price', 0)
        price_t = f"{price:,}" if price else "0"
        date = (job.get('date', {}) or {}).get('date', '')[:10]
        hash_id = job.get('hash_id', '')
        safe_message = html_module.escape(str(message))

        tg_text = (
            "✅ <b>شیفت با موفقیت رزرو شد!</b>\n\n"
            f"💼 <b>عنوان:</b> {title}\n"
            f"📍 <b>شعبه:</b> {location}\n"
            f"📅 <b>تاریخ:</b> {date}\n"
            f"🕐 <b>ساعت:</b> {start} تا {end}\n"
            f"💰 <b>دستمزد:</b> {price_t} تومان\n"
            f"🆔 <b>کد:</b> <code>{hash_id}</code>\n\n"
            f"📩 <i>{safe_message}</i>"
        )
        self.send_telegram(tg_text)

        # نوتیف گوشی
        notif_content = f"رزرو شد: {title} | {location} | {date} {start}"
        self.send_termux_notification("✅ شیفت رزرو شد!", notif_content)

    def notify_apply_failed(self, job, error_msg):
        """پیام خطا در ثبت درخواست شیفت."""
        title = job.get('job_title', '')
        location = job.get('location', '')
        hash_id = job.get('hash_id', '')
        date = (job.get('date', {}) or {}).get('date', '')[:10]

        # ★ HTML escape کردن title و location و error_msg
        # (سرور ممکنه کاراکترهای < > رو تو پیام بفرسته)
        import html as html_module
        safe_title = html_module.escape(str(title))
        safe_location = html_module.escape(str(location))
        safe_error = html_module.escape(str(error_msg))

        tg_text = (
            "⚠️ <b>خطا در ثبت درخواست شیفت</b>\n\n"
            f"💼 <b>عنوان:</b> {safe_title}\n"
            f"📍 <b>شعبه:</b> {safe_location}\n"
            f"📅 <b>تاریخ:</b> {date}\n"
            f"🆔 <b>کد:</b> <code>{hash_id}</code>\n\n"
            f"❌ <b>خطا:</b> <code>{safe_error}</code>\n\n"
            f"🔗 <a href=\"https://shift-portal.example.com/jobs\">باز کردن سایت و ثبت دستی</a>"
        )
        self.send_telegram(tg_text)

    def notify_error(self, error_type, details=""):
        messages = {
            'TOKEN_EXPIRED': "⚠️ <b>توکن شما منقضی شده!</b>\n\nلطفاً وارد صفحه وب بشو و توکن جدید رو paste کن.",
            'IP_BLOCKED': "🚫 <b>IP بلاک شده.</b>\n\nاحتمالاً پروکسی خرابه یا از ایران نیستی.",
            'NO_INTERNET': "📡 <b>اینترنت قطع است.</b>\n\nاسکریپت بعد از اتصال مجدد چک خواهد کرد.",
            'MAX_RETRIES_EXCEEDED': "❌ <b>بیش از حد تلاش شد.</b>\n\nسرور پاسخ نمی‌ده.",
            'PROXY_ERROR': "🌐 <b>پروکسی خرابه.</b>\n\nدر حال عوض کردن پروکسی...",
        }
        text = messages.get(error_type, f"❌ <b>خطا:</b> {error_type}\n\n{details}")
        self.send_telegram(text)


# ============================================================
# اجرای مستقل (برای Termux)
# ============================================================
def main():
    """اجرای مستقیم این فایل - برای Termux بدون پروکسی."""
    logger.info("=" * 50)
    logger.info(f"شروع بررسی شیفت‌ها - {datetime.now(TEHRAN_TZ).strftime('%Y-%m-%d %H:%M:%S')}")

    # بارگذاری تنظیمات
    if not CONFIG_PATH.exists():
        logger.error("فایل config.json پیدا نشد!")
        return

    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # بارگذاری توکن
    token = TokenManager.load()
    if not token:
        notifier = Notifier(config)
        notifier.notify_error('TOKEN_EXPIRED', "فایل token.txt خالی است.")
        logger.error("توکن یافت نشد.")
        return

    if TokenManager.is_expired(token):
        notifier = Notifier(config)
        notifier.notify_error('TOKEN_EXPIRED', "توکن JWT منقضی شده.")
        logger.error("توکن منقضی شده.")
        return

    # دریافت شیفت‌ها (بدون پروکسی - برای Termux)
    fetcher = JobFetcher(config)
    jobs_data, error = fetcher.fetch(token)

    if error:
        notifier = Notifier(config)
        if error == 'NO_INTERNET':
            logger.warning("اینترنت قطع است. skip می‌شه.")
            return
        notifier.notify_error(error)
        logger.error(f"خطا در دریافت شیفت‌ها: {error}")
        return

    if not jobs_data or 'data' not in jobs_data:
        logger.error("پاسخ نامعتبر از سرور.")
        return

    # فیلتر
    job_filter = JobFilter(config.get('filters', {}))
    state = StateManager.load()
    notifier = Notifier(config)

    matched_shifts = []
    new_shifts = []

    for job in jobs_data['data']:
        if job_filter.matches(job):
            matched_shifts.append(job)
            if not StateManager.is_notified(state, job.get('id')):
                new_shifts.append(job)

    logger.info(f"کل شیفت‌ها: {len(jobs_data['data'])}")
    logger.info(f"شیفت‌های match شده: {len(matched_shifts)}")
    logger.info(f"شیفت‌های جدید برای نوتیف: {len(new_shifts)}")

    for job in new_shifts:
        notifier.notify_shift_found(job)
        StateManager.mark_notified(state, job.get('id'))
        time.sleep(1)

    state['last_check'] = datetime.now(TEHRAN_TZ).isoformat()
    StateManager.save(state)

    logger.info("بررسی کامل شد.")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("توسط کاربر متوقف شد.")
    except Exception as e:
        logger.exception(f"خطای غیرمنتظره: {e}")
        sys.exit(1)
