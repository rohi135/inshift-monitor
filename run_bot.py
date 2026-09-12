#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ربات تلگرام برای GitHub Actions - اجرای یک‌باره
==================================================
این اسکریپت در GitHub Actions هر ۵ دقیقه اجرا می‌شه و:
  1. پیام‌های جدید تلگرام رو چک می‌کنه
  2. اگه کاربر توکن JWT فرستاده باشه، اون رو به‌عنوان GitHub Secret ذخیره می‌کنه
  3. پیام تایید به کاربر می‌فرسته

نیازها:
  - GH_PAT secret: Personal Access Token با scope `repo`
  - TELEGRAM_BOT_TOKEN secret
  - TELEGRAM_CHAT_ID secret

نحوه کار:
  - offset در state.json ذخیره می‌شه تا پیام‌های قبلی دوباره پردازش نشن
  - توکن با libsodium encrypt می‌شه قبل از ارسال به GitHub API
"""

import os
import sys
import json
import base64
import logging
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ============================================================
# لاگ
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

TEHRAN_TZ = timezone(timedelta(hours=3, minutes=30))

# ============================================================
# مسیرها
# ============================================================
SCRIPT_DIR = Path(__file__).resolve().parent
STATE_PATH = SCRIPT_DIR / "state.json"
BOT_STATE_PATH = SCRIPT_DIR / "bot_state.json"

# ============================================================
# تنظیمات از env
# ============================================================
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
GH_PAT = os.getenv('GH_PAT', '')
GH_REPO = os.getenv('GITHUB_REPOSITORY', '')  # auto-set by GitHub Actions
SECRET_NAME = os.getenv('SECRET_NAME', 'INSHIFT_TOKEN')

# ============================================================
# ایمپورت کمکی
# ============================================================
sys.path.insert(0, str(SCRIPT_DIR))


def is_valid_jwt(token):
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


# ============================================================
# مدیریت state بات
# ============================================================
def load_bot_state():
    if not BOT_STATE_PATH.exists():
        return {"offset": 0}
    try:
        with open(BOT_STATE_PATH, 'r') as f:
            return json.load(f)
    except Exception:
        return {"offset": 0}


def save_bot_state(state):
    with open(BOT_STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2)


# ============================================================
# توابع تلگرام
# ============================================================
def send_message(text, parse_mode='HTML'):
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


def get_updates(offset=0):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {'offset': offset, 'timeout': 1, 'limit': 10}
    try:
        r = requests.get(url, params=params, timeout=5)
        if r.status_code == 200:
            return r.json().get('result', [])
        return []
    except Exception as e:
        logger.error(f"خطا در getUpdates: {e}")
        return []


# ============================================================
# آپدیت GitHub Secret
# ============================================================
def update_github_secret(token_value):
    """
    آپدیت GitHub Secret با استفاده از PAT.

    نیاز به pynacl برای encryption داره.
    """
    if not GH_PAT or not GH_REPO:
        logger.error("GH_PAT یا GITHUB_REPOSITORY تنظیم نشده!")
        return False

    try:
        from nacl import public, encoding
    except ImportError:
        logger.error("pynacl نصب نیست! در requirements.txt باید باشه.")
        return False

    headers = {
        'Authorization': f'token {GH_PAT}',
        'Accept': 'application/vnd.github.v3+json'
    }

    # 1) گرفتن public key
    key_url = f"https://api.github.com/repos/{GH_REPO}/actions/secrets/public-key"
    try:
        r = requests.get(key_url, headers=headers, timeout=10)
        r.raise_for_status()
        key_data = r.json()
    except Exception as e:
        logger.error(f"خطا در گرفتن public key: {e}")
        return False

    # 2) Encrypt کردن secret
    try:
        public_key = public.PublicKey(
            key_data['key'].encode(),
            encoding.Base64Encoder()
        )
        sealed_box = public.SealedBox(public_key)
        encrypted = sealed_box.encrypt(token_value.encode())
        encrypted_b64 = base64.b64encode(encrypted).decode()
    except Exception as e:
        logger.error(f"خطا در encryption: {e}")
        return False

    # 3) آپدیت secret
    secret_url = f"https://api.github.com/repos/{GH_REPO}/actions/secrets/{SECRET_NAME}"
    data = {
        'encrypted_value': encrypted_b64,
        'key_id': key_data['key_id']
    }
    try:
        r = requests.put(secret_url, headers=headers, json=data, timeout=10)
        if r.status_code in (201, 204):
            return True
        logger.error(f"خطا در آپدیت secret: {r.status_code} - {r.text}")
        return False
    except Exception as e:
        logger.error(f"خطا در API call: {e}")
        return False


# ============================================================
# تابع اصلی
# ============================================================
def main():
    logger.info(f"🤖 Telegram Bot run - {datetime.now(TEHRAN_TZ).strftime('%Y-%m-%d %H:%M:%S')}")

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("تلگرام تنظیم نشده!")
        return

    state = load_bot_state()

    # ============================================================
    # چک انقضای توکن (هر ۱۵ دقیقه)
    # ============================================================
    # این بخش به‌صورت جداگانه چک می‌کنه که آیا توکن منقضی شده یا نزدیک انقضا
    # تا کاربر سریع خبردار بشه (بدون صبر کردن برای اجرای monitor)
    sent_warnings = state.get('sent_warnings', {})
    current_token = os.getenv('INSHIFT_TOKEN', '')

    if current_token:
        # ایمپورت محلی برای جلوگیری از circular import
        sys.path.insert(0, str(SCRIPT_DIR))
        from inshift_monitor import TokenManager

        hours_left = TokenManager.hours_until_expiry(current_token)
        logger.info(f"⏰ ساعت‌های باقی‌مانده تا انقضای توکن: {hours_left}")

        if hours_left < 0:
            # توکن منقضی شده - اگه قبلاً اخطار_EXPIRED نفرستاده بودیم، بفرست
            if not sent_warnings.get('expired'):
                send_message(
                    "🚨 <b>توکن شما منقضی شده!</b>\n\n"
                    "اسکریپت دیگه نمی‌تونه شیفت‌ها رو چک کنه.\n"
                    "همین الان یه توکن جدید بگیر و بفرست برام:\n\n"
                    "1. با Kiwi Browser وارد inshift.digikala.com شو\n"
                    "2. لاگین کن و برو به صفحه Jobs\n"
                    "3. F12 → Network → jobs?page=1 → Headers\n"
                    "4. مقدار Authorization رو کپی کن\n"
                    "5. همینجا بفرست برام",
                    parse_mode='HTML'
                )
                sent_warnings['expired'] = True
                # وقتی توکن جدید داد، این flag پاک می‌شه (در بخش دریافت توکن)
                logger.info("🚨 پیام انقضای توکن ارسال شد.")
            else:
                logger.info("ℹ️ پیام انقضا قبلاً ارسال شده، skip.")

        elif hours_left < 24:
            # کمتر از ۲۴ ساعت - اخطار زودهنگام (فقط یه بار)
            warning_key = f'warn_{hours_left // 6}'  # هر ۶ ساعت یه اخطار
            if not sent_warnings.get(warning_key):
                send_message(
                    f"⚠️ <b>توکن شما کمتر از ۲۴ ساعت اعتبار داره!</b>\n\n"
                    f"⏰ زمان باقی‌مانده: <b>{hours_left} ساعت</b>\n\n"
                    f"بهتره زودتر توکن جدید بگیری و بفرستی.\n"
                    f"برای راهنما: /help",
                    parse_mode='HTML'
                )
                sent_warnings[warning_key] = True
                # پاک کردن flag انقضا اگه توکن تازه آپدیت شده
                sent_warnings.pop('expired', None)
                logger.info(f"⚠️ اخطار زودهنگام ارسال شد ({hours_left} ساعت).")
            else:
                logger.info(f"ℹ️ اخطار {hours_left} ساعت قبلاً ارسال شده.")

        else:
            # توکن سالمه - پاک کردن همه warning flags
            if sent_warnings:
                logger.info("✓ توکن سالمه. پاک کردن warning flags.")
                sent_warnings.clear()

        state['sent_warnings'] = sent_warnings

    # ذخیره state قبل از ادامه (برای حفظ warning flags)
    save_bot_state(state)

    # ============================================================
    # چک پیام‌های تلگرام
    # ============================================================
    offset = state.get('offset', 0)

    updates = get_updates(offset)
    logger.info(f"📥 {len(updates)} پیام جدید.")

    for update in updates:
        offset = update['update_id'] + 1

        if 'message' not in update:
            continue

        msg = update['message']
        chat_id = str(msg.get('chat', {}).get('id', ''))
        text = msg.get('text', '').strip()

        # فقط کاربر مجاز
        if chat_id != str(TELEGRAM_CHAT_ID):
            logger.warning(f"چت غیرمجاز: {chat_id}")
            continue

        # دستورات
        if text == '/start':
            send_message(
                "👋 سلام!\n\n"
                "من ربات این‌شیفت مانیتور هستم.\n"
                "هر زمان توکن منقضی شد، فقط بفرستش برام.\n\n"
                "📖 /help - راهنما\n"
                "📊 /status - وضعیت توکن"
            )

        elif text == '/help':
            send_message(
                "📖 <b>راهنما</b>\n\n"
                "<b>چطور توکن جدید بگیرم؟</b>\n"
                "1. با مرورگر Kiwi وارد inshift.digikala.com شو\n"
                "2. لاگین کن و برو به صفحه Jobs\n"
                "3. منوی Kiwi → Developer Tools\n"
                "4. تب Network → Fetch/XHR\n"
                "5. صفحه رو رفرش کن\n"
                "6. روی درخواست <code>jobs?page=1</code> کلیک کن\n"
                "7. تب Headers → Request Headers\n"
                "8. مقدار <code>Authorization</code> رو کپی کن\n"
                "9. همینجا بفرست برام\n\n"
                "توکن خودکار در GitHub Secrets ذخیره می‌شه.",
                parse_mode='HTML'
            )

        elif text == '/status':
            # بررسی توکن فعلی
            current_token = os.getenv('INSHIFT_TOKEN', '')
            if current_token and is_valid_jwt(current_token):
                try:
                    parts = current_token.split('.')
                    payload_b64 = parts[1] + '=' * (4 - len(parts[1]) % 4)
                    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                    expire = payload.get('expire_time', 0)
                    user_id = payload.get('user_id', '?')
                    now = int(datetime.now().timestamp())
                    days_left = max(0, (expire - now) // 86400)
                    status = "✅ معتبر" if days_left > 0 else "❌ منقضی"
                    send_message(
                        f"📊 <b>وضعیت توکن</b>\n\n"
                        f"وضعیت: {status}\n"
                        f"User ID: <code>{user_id}</code>\n"
                        f"روزهای باقی‌مانده: <b>{days_left}</b> روز",
                        parse_mode='HTML'
                    )
                except Exception as e:
                    send_message(f"⚠️ خطا: {e}")
            else:
                send_message("❌ توکن معتبر نیست یا تنظیم نشده.")

        elif text.startswith('/'):
            send_message("دستور ناشناخته. /help رو بزن.")

        else:
            # احتمالاً توکن جدید
            token = text
            # پاک کردن پیشوند
            if token.lower().startswith('authorization:'):
                token = token.split(':', 1)[1].strip()
            if token.lower().startswith('bearer '):
                token = token[7:].strip()

            if is_valid_jwt(token):
                # آپدیت GitHub Secret
                if GH_PAT and GH_REPO:
                    send_message("⏳ در حال ذخیره توکن در GitHub Secrets...")
                    if update_github_secret(token):
                        # پاک کردن warning flags چون توکن جدید داد
                        state['sent_warnings'] = {}
                        save_bot_state(state)

                        send_message(
                            "✅ <b>توکن با موفقیت در GitHub Secrets ذخیره شد!</b>\n\n"
                            "از اجرای بعدی monitor، از توکن جدید استفاده می‌شه.\n"
                            "🔍 چک شیفت‌ها ادامه پیدا می‌کنه.",
                            parse_mode='HTML'
                        )
                        logger.info("✓ توکن در GitHub Secret ذخیره شد. warning flags پاک شد.")
                    else:
                        send_message(
                            "❌ خطا در ذخیره توکن. لاگ‌های GitHub Actions رو چک کن."
                        )
                else:
                    # اگه PAT نبود، توکن رو در فایل ذخیره کن (برای تست محلی)
                    with open('token.txt', 'w') as f:
                        f.write(token)
                    send_message(
                        "✅ توکن در فایل ذخیره شد. (در GitHub Actions، باید GH_PAT تنظیم بشه تا به‌صورت secret ذخیره بشه.)"
                    )
            else:
                send_message(
                    "❌ <b>این یه JWT معتبر نیست.</b>\n\n"
                    "مطمئن شو که:\n"
                    "• کل مقدار Authorization رو کپی کردی\n"
                    "• سه قسمت با نقطه جدا شده\n\n"
                    "برای راهنمایی: /help",
                    parse_mode='HTML'
                )

    # ذخیره offset
    state['offset'] = offset
    save_bot_state(state)
    logger.info(f"✓ offset آپدیت شد: {offset}")


if __name__ == '__main__':
    main()
