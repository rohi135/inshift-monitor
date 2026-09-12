# 🎯 این‌شیفت مانیتور

ربات پایش شیفت‌های **این‌شیفت دیجی‌کالا** که هر ۳۰ دقیقه شیفت‌های جدید رو چک می‌کنه و اگه شیفت با مشخصه‌های مدنظر شما پیدا شد، از طریق **تلگرام** به شما اطلاع می‌ده.

## ✨ ویژگی‌ها

- ✅ اجرای خودکار هر ۳۰ دقیقه (با GitHub Actions)
- ✅ کاملاً رایگان - بدون credit card لازم
- ✅ نوتیفیکیشن تلگرام با فرمت زیبا
- ✅ **ربات تلگرام** برای آپدیت خودکار توکن (با فرستادن توکن به ربات، خودکار در GitHub Secret ذخیره می‌شه)
- ✅ **Proxy Pool هوشمند** - خودکار پروکسی ایرانی رایگان پیدا می‌کنه
- ✅ تشخیص خودکار انقضای توکن و درخواست لاگین مجدد
- ✅ جلوگیری از اسپم (هر شیفت فقط یک بار نوتیف می‌شه)
- ✅ مدیریت خطا (قطعی اینترنت، خطای سرور، IP بلاک، پروکسی مرده)
- ✅ ۲۴/۷ آنلاین

## 🏗️ معماری

```
GitHub Actions (رایگان، ۲۴/۷)
├── 📝 Monitor Workflow (هر ۳۰ دقیقه)
│   ├── نصب پایتون + deps
│   ├── خوندن INSHIFT_TOKEN از GitHub Secrets
│   ├── اجرای Proxy Pool (۴ منبع)
│   ├── درخواست به staffing.digikala.com
│   ├── فیلتر Stow/Pick + دانش + 07-17
│   ├── نوتیف تلگرام اگه match شد
│   └── commit state.json به ریپو
│
└── 🤖 Telegram Bot Workflow (هر ۵ دقیقه)
    ├── چک پیام‌های جدید تلگرام
    ├── اگه JWT فرستادی → آپدیت GitHub Secret
    └── ذخیره offset در bot_state.json
```

## 🚀 شروع سریع (GitHub Actions)

### قدم ۱: ساخت ربات تلگرام
به @BotFather در تلگرام پیام بده، `/newbot` بزن، توکن رو بگیر.

### قدم ۲: گرفتن Chat ID
به رباتت `/start` بده، بعد این URL رو باز کن:
```
https://api.telegram.org/bot<TOKEN>/getUpdates
```
عدد `chat.id` رو کپی کن.

### قدم ۳: ریپو رو فورک یا کلون کن
این ریپو رو fork کن یا کد رو به ریپوی خودت push کن.

### قدم ۴: تنظیم GitHub Secrets

در ریپو → Settings → Secrets and variables → Actions → New repository secret:

| Secret Name | Value |
|-------------|-------|
| `TELEGRAM_BOT_TOKEN` | توکن ربات تلگرام |
| `TELEGRAM_CHAT_ID` | chat id شما |
| `INSHIFT_TOKEN` | توکن JWT این‌شیفت (نحوه گرفتن در قدم ۶) |
| `GH_PAT` | Personal Access Token با scope `repo` (برای آپدیت خودکار توکن) |

### قدم ۵: (اختیاری) تنظیم متغیرهای فیلتر

در ریپو → Settings → Secrets and variables → Actions → Variables tab:

| Variable Name | Default | توضیح |
|---------------|---------|-------|
| `FILTER_JOB_TITLES` | `Stow,Pick` | عناوین شغلی (با کاما) |
| `FILTER_LOCATION` | `دانش` | نام شعبه |
| `FILTER_START_HOUR` | `7` | ساعت شروع |
| `FILTER_END_HOUR` | `17` | ساعت پایان |
| `EXCLUDE_FULL_CAPACITY` | `true` | حذف شیفت‌های پر شده |

### قدم ۶: گرفتن توکن JWT این‌شیفت

1. **Kiwi Browser** رو روی گوشی نصب کن
2. وارد `inshift.digikala.com` شو و لاگین کن
3. به صفحه Jobs برو
4. منوی Kiwi → **Developer tools**
5. تب **Network** → فیلتر **Fetch/XHR**
6. صفحه رو رفرش کن
7. روی `jobs?page=1` کلیک کن
8. تب **Headers** → **Request Headers**
9. مقدار `Authorization` رو کپی کن
10. در GitHub Secrets به‌عنوان `INSHIFT_TOKEN` اضافه کن

### قدم ۷: ساخت PAT برای آپدیت خودکار توکن (اختیاری)

برای اینکه بعداً بتونی از طریق تلگرام توکن رو آپدیت کنی:

1. برو به https://github.com/settings/tokens
2. **Generate new token (classic)**
3. Note: `inshift-bot`
4. Expiration: 90 days (یا بیشتر)
5. Scope: `repo` (کامل)
6. Generate و کپی کن
7. در GitHub Secrets به‌عنوان `GH_PAT` اضافه کن

### قدم ۸: تست

1. برو به تب **Actions** در ریپو
2. Workflow به‌نام **Inshift Monitor** رو پیدا کن
3. روی **Run workflow** بزن
4. لاگ‌ها رو ببین - باید ببینی:
   ```
   🚀 GitHub Actions: Inshift Monitor
   🌐 در حال راه‌اندازی Proxy Pool...
   ✓ Proxy Pool: X پروکسی سالم از Y
   📡 تلاش 1: استفاده از socks5://...
   ✓ موفق! N شیفت دریافت شد.
   📊 کل: N | Match: M | جدید: K
   ✓ بررسی کامل شد.
   ```

5. اگه شیفت match بشه، تلگرام بهت پیام میاد!

📖 **راهنمای کامل**: [DEPLOY.md](DEPLOY.md)

## 📁 ساختار فایل‌ها

```
inshift-monitor/
├── .github/workflows/
│   ├── monitor.yml              # Workflow هر ۳۰ دقیقه
│   └── telegram-bot.yml         # Workflow هر ۵ دقیقه (برای آپدیت توکن)
├── run_monitor.py               # اسکریپت اصلی (single-run)
├── run_bot.py                   # ربات تلگرام (single-run)
├── inshift_monitor.py           # ماژول مشترک (Token, Filter, Notifier)
├── proxy_pool.py                # مدیریت پروکسی‌های ایرانی
├── token_updater_bot.py         # (اختیاری) نسخه always-on برای Termux/VPS
├── main.py                      # (اختیاری) FastAPI app برای Railway
├── requirements.txt             # وابستگی‌های پایتون
├── Dockerfile                   # (اختیاری) برای Railway/Render
├── railway.json                 # (اختیاری) تنظیمات Railway
├── templates/                   # (اختیاری) صفحات وب برای Railway
├── DEPLOY.md                    # راهنمای deploy
└── README.md                    # این فایل
```

## ⚙️ تنظیمات فیلتر

فیلترها از طریق GitHub Variables (نه Secrets) تنظیم می‌شن:

| Variable | پیش‌فرض | توضیح |
|----------|---------|-------|
| `FILTER_JOB_TITLES` | `Stow,Pick` | عناوین شغلی (با کاما) |
| `FILTER_LOCATION` | `دانش` | نام شعبه |
| `FILTER_START_HOUR` | `7` | ساعت شروع |
| `FILTER_START_MINUTE` | `0` | دقیقه شروع |
| `FILTER_END_HOUR` | `17` | ساعت پایان |
| `FILTER_END_MINUTE` | `0` | دقیقه پایان |
| `EXCLUDE_FULL_CAPACITY` | `true` | حذف شیفت‌های پر شده |

## 🌐 Proxy Pool

سیستم خودکار از ۴ منبع پروکسی رایگان ایرانی استفاده می‌کنه:

| منبع | نوع | نحوه دسترسی |
|------|-----|-------------|
| ProxyScrape API | SOCKS5/HTTP | API با فیلتر country=IR |
| Geonode API | HTTP/HTTPS/SOCKS5 | API با JSON |
| monosans/proxy-list | SOCKS5/HTTP | GitHub raw |
| proxifly/free-proxy-list | HTTP | GitHub raw |

### امنیت:
- ✅ همه درخواست‌ها HTTPS هستن
- ✅ TLS verification همیشه روشن (`verify=True`)
- ✅ پروکسی نمی‌تونه توکن JWT رو ببینه (چون داخل HTTPS encrypted هست)
- ✅ از SOCKS5 proxy استفاده می‌شه (امن‌تر از HTTP proxy)

## 🤖 دستورات تلگرام

| دستور | توضیح |
|-------|-------|
| `/start` | شروع |
| `/help` | راهنمای گرفتن توکن |
| `/status` | وضعیت توکن فعلی |
| (هر متن JWT) | خودکار در GitHub Secret ذخیره می‌شه |

## 🔒 امنیت

| مورد | توضیح |
|------|-------|
| توکن JWT | در GitHub Secrets (رمزنگاری شده) |
| توکن تلگرام | در GitHub Secrets |
| PAT | در GitHub Secrets |
| TLS Verification | همیشه روشن - جلوگیری از MITM |
| HTTPS | همه درخواست‌ها به دیجی‌کالا HTTPS هستن |

> ⚠️ توکن JWT = پسورد لاگین شماست. هرگز به کسی نده.

## 💰 هزینه

| مورد | هزینه |
|------|-------|
| GitHub Actions (public repo) | **رایگان نامحدود** ✅ |
| ربات تلگرام | رایگان |
| پروکسی‌ها | رایگان |
| **کل** | **رایگان** ✅ |

## 🔄 تمدید توکن

توکن JWT هر ~۵ روز منقضی می‌شه. وقتی منقضی شد:

### روش ۱: تلگرام (اگه GH_PAT تنظیم شده)
1. توکن جدید رو از Kiwi Browser بگیر
2. به ربات تلگرامت بفرست
3. ربات خودکار در GitHub Secret ذخیره می‌کنه (حدود ۵ دقیقه طول می‌کشه)

### روش ۲: دستی از طریق GitHub UI
1. توکن جدید رو از Kiwi Browser بگیر
2. ریپو → Settings → Secrets → `INSHIFT_TOKEN` → Update
3. Paste کن و Save

## 🐛 عیب‌یابی

### مشکل: نوتیف تلگرام نمیاد
- `TELEGRAM_BOT_TOKEN` و `TELEGRAM_CHAT_ID` رو چک کن
- در مرورگر تست کن: `https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<CHAT_ID>&text=test`

### مشکل: ارور 401 (توکن منقضی)
- توکن جدید رو از Kiwi Browser بگیر
- در GitHub Secrets آپدیت کن

### مشکل: هیچ پروکسی سالمی نیست
- پروکسی‌های رایگان ناپایدارن
- لاگ‌های GitHub Actions رو ببین
- workflow رو دستی re-run کن

### مشکل: workflow اجرا نمی‌شه
- تب Actions رو چک کن
- مطمئن شو workflow enabled هست
- مطمئن شو secrets درست set شدن

📖 **راهنمای کامل**: [DEPLOY.md](DEPLOY.md)

## 🆘 پشتیبانی

اگه مشکل داشتی:
1. تب Actions در GitHub رو چک کن
2. لاگ‌های workflow رو ببین
3. ربات تلگرام رو با `/status` چک کن

---

**موفق باشید! 🎯**
