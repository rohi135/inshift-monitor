#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ربات آپدیت توکن تلگرام
=====================
این ماژول یه ربات تلگرام سبک هست که می‌تونی توکن جدید رو از طریق تلگرام بفرستی.

روی Railway: این ماژول در یه thread جدا اجرا می‌شه (از طریق main.py)
روی Termux: می‌تونی مستقیم اجرا کنی
"""

import os
import json
import logging
import requests
import time
import threading
from pathlib import Path

# ============================================================
# مسیرها
# ============================================================
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
TOKEN_PATH = SCRIPT_DIR / "token.txt"
LOG_PATH = SCRIPT_DIR / "token_bot.log"

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


def is_valid_jwt(token):
    if not token or '.' not in token:
        return False
    parts = token.split('.')
    if len(parts) != 3:
        return False
    try:
        import base64
        payload_b64 = parts[1] + '=' * (4 - len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return 'user_id' in payload or 'expire_time' in payload
    except Exception:
        return False


def save_token(token):
    token = token.strip()
    if token.lower().startswith('authorization:'):
        token = token.split(':', 1)[1].strip()
    if token.lower().startswith('bearer '):
        token = token[7:].strip()

    with open(TOKEN_PATH, 'w', encoding='utf-8') as f:
        f.write(token)
    try:
        os.chmod(TOKEN_PATH, 0o600)
    except Exception:
        pass
    return token


def send_message(bot_token, chat_id, text, parse_mode='HTML'):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': parse_mode,
        'disable_web_page_preview': True
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        logger.error(f"خطا در ارسال پیام: {e}")
        return False


def get_updates(bot_token, offset=0):
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    params = {'offset': offset, 'timeout': 30}
    try:
        r = requests.get(url, params=params, timeout=35)
        if r.status_code == 200:
            return r.json().get('result', [])
        return []
    except Exception as e:
        logger.error(f"خطا در getUpdates: {e}")
        return []


def run_bot(bot_token, allowed_chat_id, stop_event=None):
    """
    اجرای ربات تلگرام.

    Args:
        bot_token: توکن ربات تلگرام
        allowed_chat_id: chat id کاربر مجاز (string)
        stop_event: threading.Event برای توقف آرام
    """
    if not bot_token or not allowed_chat_id:
        logger.error("توکن یا chat_id تنظیم نشده.")
        return

    logger.info(f"🤖 ربات تلگرام شروع شد. chat_id={allowed_chat_id}")

    # پیام خوش‌آمد اولیه
    send_message(
        bot_token, allowed_chat_id,
        "🤖 <b>ربات مانیتور شیفت فعال شد!</b>\n\n"
        "هر زمان توکن منقضی شد، می‌تونی توکن جدید رو بفرستی.\n\n"
        "📖 /help - راهنما\n"
        "📊 /status - وضعیت توکن فعلی\n"
        "🔄 /refresh - چک دستی شیفت‌ها",
        parse_mode='HTML'
    )

    offset = 0
    while stop_event is None or not stop_event.is_set():
        try:
            updates = get_updates(bot_token, offset)
            for update in updates:
                offset = update['update_id'] + 1

                if 'message' not in update:
                    continue

                msg = update['message']
                chat_id = str(msg.get('chat', {}).get('id', ''))
                text = msg.get('text', '').strip()

                if chat_id != str(allowed_chat_id):
                    logger.warning(f"چت غیرمجاز: {chat_id}")
                    continue

                if text == '/start':
                    send_message(bot_token, chat_id,
                        "👋 سلام!\n\n"
                        "من ربات مانیتور شیفت هستم.\n"
                        "وقتی توکنت منقضی شد، فقط بفرستش برام.\n\n"
                        "📖 /help - راهنما\n"
                        "📊 /status - وضعیت توکن\n"
                        "🔄 /refresh - چک دستی"
                    )

                elif text == '/help':
                    send_message(bot_token, chat_id,
                        "📖 <b>راهنما</b>\n\n"
                        "<b>چطور توکن جدید بگیرم؟</b>\n"
                        "1. با مرورگر Kiwi وارد shift-portal.example.com شو\n"
                        "2. لاگین کن و برو به صفحه Jobs\n"
                        "3. منوی Kiwi → Developer Tools\n"
                        "4. تب Network → روشن کن Fetch/XHR\n"
                        "5. صفحه رو رفرش کن\n"
                        "6. روی درخواست <code>jobs?page=1</code> کلیک کن\n"
                        "7. تب Headers → قسمت Request Headers\n"
                        "8. مقدار <code>Authorization</code> رو کپی کن\n"
                        "9. همینجا بفرست برام\n\n"
                        "<b>دستورات:</b>\n"
                        "📊 /status - وضعیت توکن فعلی\n"
                        "🔄 /refresh - چک دستی شیفت‌ها\n"
                        "📖 /help - این راهنما",
                        parse_mode='HTML'
                    )

                elif text == '/status':
                    if TOKEN_PATH.exists():
                        with open(TOKEN_PATH, 'r') as f:
                            token = f.read().strip()
                        if is_valid_jwt(token):
                            try:
                                import base64
                                payload_b64 = token.split('.')[1] + '=' * (4 - len(token.split('.')[1]) % 4)
                                payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                                expire = payload.get('expire_time', 0)
                                user_id = payload.get('user_id', '?')
                                now = int(time.time())
                                days_left = max(0, (expire - now) // 86400)
                                status = "✅ معتبر" if days_left > 0 else "❌ منقضی"
                                send_message(bot_token, chat_id,
                                    f"📊 <b>وضعیت توکن</b>\n\n"
                                    f"وضعیت: {status}\n"
                                    f"User ID: <code>{user_id}</code>\n"
                                    f"روزهای باقی‌مانده: <b>{days_left}</b> روز",
                                    parse_mode='HTML'
                                )
                            except Exception as e:
                                send_message(bot_token, chat_id, f"⚠️ خطا: {e}")
                        else:
                            send_message(bot_token, chat_id, "❌ توکن معتبر نیست.")
                    else:
                        send_message(bot_token, chat_id, "❌ هنوز توکنی ذخیره نشده.")

                elif text == '/refresh':
                    send_message(bot_token, chat_id, "🔄 در حال چک دستی...")
                    # ایمپورت اینجا برای جلوگیری از circular import
                    try:
                        from main import trigger_manual_check
                        trigger_manual_check()
                        send_message(bot_token, chat_id, "✅ چک دستی شروع شد.")
                    except Exception as e:
                        send_message(bot_token, chat_id, f"⚠️ چک دستی فعال نیست: {e}")

                elif text.startswith('/'):
                    send_message(bot_token, chat_id, "دستور ناشناخته. /help رو بزن.")

                else:
                    # احتمالاً توکن
                    if is_valid_jwt(text):
                        saved = save_token(text)
                        logger.info(f"توکن جدید از طرف chat_id={chat_id} ذخیره شد.")
                        send_message(bot_token, chat_id,
                            "✅ <b>توکن با موفقیت ذخیره شد!</b>\n\n"
                            "اسکریپت مانیتورینگ خودکار از توکن جدید استفاده خواهد کرد.",
                            parse_mode='HTML'
                        )
                    else:
                        send_message(bot_token, chat_id,
                            "❌ <b>این یه JWT معتبر نیست.</b>\n\n"
                            "مطمئن شو که:\n"
                            "• کل مقدار Authorization رو کپی کردی\n"
                            "• سه قسمت با نقطه جدا شده (header.payload.signature)\n\n"
                            "برای راهنمایی بیشتر: /help",
                            parse_mode='HTML'
                        )

        except KeyboardInterrupt:
            logger.info("توقف توسط کاربر.")
            break
        except Exception as e:
            logger.exception(f"خطا: {e}")
            time.sleep(5)


def main_standalone():
    """اجرای مستقل (برای Termux)."""
    if not CONFIG_PATH.exists():
        logger.error("config.json پیدا نشد.")
        return

    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)

    bot_token = config.get('telegram_bot_token', '')
    allowed_chat_id = str(config.get('telegram_chat_id', ''))

    if 'PUT_YOUR' in bot_token or 'PUT_YOUR' in allowed_chat_id:
        logger.error("ابتدا config.json را پر کنید.")
        return

    run_bot(bot_token, allowed_chat_id)


if __name__ == '__main__':
    main_standalone()
