# 🎯 این‌شیفت مانیتور

ربات پایش شیفت‌های **این‌شیفت دیجی‌کالا** که هر ۳۰ دقیقه شیفت‌های جدید رو چک می‌کنه و اگه شیفت با مشخصه‌های مدنظر شما پیدا شد، از طریق **تلگرام** به شما اطلاع می‌ده.

## ✨ ویژگی‌ها

- ✅ اجرای خودکار هر ۳۰ دقیقه (قابل تغییر)
- ✅ نوتیفیکیشن تلگرام با فرمت زیبا
- ✅ صفحه وب برای آپدیت توکن JWT (با پسورد محافظت می‌شه)
- ✅ ربات تلگرام برای آپدیت توکن از طریق تلگرام
- ✅ **Proxy Pool هوشمند** - خودکار پروکسی ایرانی رایگان پیدا می‌کنه
- ✅ تشخیص خودکار انقضای توکن و درخواست لاگین مجدد
- ✅ جلوگیری از اسپم (هر شیفت فقط یک بار نوتیف می‌شه)
- ✅ مدیریت خطا (قطعی اینترنت، خطای سرور، IP بلاک، پروکسی مرده)
- ✅ داشبورد وب برای مشاهده وضعیت
- ✅ اجرا روی Railway (۲۴/۷ آنلاین)
- ✅ کاملاً رایگان (با trial Railway)

## 🏗️ معماری

```
Railway App (FastAPI + Python)
├── 📄 صفحه وب (/)
│   ├── لاگین با پسورد
│   ├── داشبورد وضعیت
│   └── فرم آپدیت توکن JWT
│
├── 🤖 Telegram Bot (همیشه روشن)
│   ├── /start, /help, /status
│   ├── /refresh - چک دستی
│   └── دریافت توکن از پیام
│
├── 🔄 Proxy Pool (هر ۱۰ دقیقه refresh)
│   ├── Fetch از ProxyScrape API
│   ├── Fetch از Geonode API
│   ├── Fetch از monosans/proxy-list (GitHub)
│   ├── Fetch از proxifly (GitHub)
│   ├── Health check موازی (asyncio)
│   └── Rotation خودکار
│
└── ⏰ Job Monitor (هر ۳۰ دقیقه)
    ├── درخواست با پروکسی ایرانی
    ├── فیلتر Stow/Pick + دانش + 07-17
    ├── حذف شیفت‌های full_capacity
    └── نوتیف تلگرام
```

## 🚀 شروع سریع

### قدم ۱: ساخت ربات تلگرام
به @BotFather در تلگرام پیام بده، `/newbot` بزن، توکن رو بگیر.

### قدم ۲: گرفتن Chat ID
به رباتت `/start` بده، بعد این URL رو باز کن:
```
https://api.telegram.org/bot<TOKEN>/getUpdates
```
عدد `chat.id` رو کپی کن.

### قدم ۳: آپلود به GitHub
کل پوشه `inshift-monitor` رو به یه ریپوی GitHub push کن.

### قدم ۴: Deploy روی Railway
1. وارد [railway.app](https://railway.app) بشو
2. New Project → Deploy from GitHub repo
3. ریپو رو انتخاب کن
4. صبر کن تا build بشه

### قدم ۵: تنظیم Environment Variables
در Railway → Variables این‌ها رو set کن:

| Variable | Value |
|----------|-------|
| `TELEGRAM_BOT_TOKEN` | توکن ربات |
| `TELEGRAM_CHAT_ID` | chat id شما |
| `WEB_PASSWORD` | پسورد دلخواه صفحه وب |
| `FILTER_JOB_TITLES` | `Stow,Pick` |
| `FILTER_LOCATION` | `دانش` |
| `FILTER_START_HOUR` | `7` |
| `FILTER_END_HOUR` | `17` |

### قدم ۶: تنظیم Domain
Railway → Settings → Networking → Generate Domain

### قدم ۷: آپدیت توکن
1. صفحه وب رو باز کن: `https://your-app.up.railway.app/`
2. پسورد رو وارد کن
3. روی «آپدیت توکن» کلیک کن
4. توکن JWT رو paste کن (راهنمای کامل تو صفحه هست)

📖 **راهنمای کامل deploy**: [DEPLOY_RAILWAY.md](DEPLOY_RAILWAY.md)

## 📁 ساختار فایل‌ها

```
inshift-monitor/
├── main.py                  # اپ FastAPI + Scheduler
├── inshift_monitor.py       # ماژول اصلی (Token, Filter, Notifier)
├── token_updater_bot.py     # ربات تلگرام
├── proxy_pool.py            # مدیریت پروکسی‌های ایرانی
├── config.json              # تنظیمات (برای Termux)
├── requirements.txt         # وابستگی‌های پایتون
├── Dockerfile               # برای Railway
├── railway.json             # تنظیمات Railway
├── .dockerignore
├── templates/
│   ├── login.html           # صفحه لاگین وب
│   ├── dashboard.html       # داشبورد وضعیت
│   └── update_token.html    # فرم آپدیت توکن
├── DEPLOY_RAILWAY.md        # راهنمای deploy فارسی
└── README.md                # این فایل
```

## ⚙️ تنظیمات فیلتر

فیلترها از طریق Environment Variables تنظیم می‌شن:

| Variable | پیش‌فرض | توضیح |
|----------|---------|-------|
| `FILTER_JOB_TITLES` | `Stow,Pick` | عناوین شغلی (با کاما جدا) |
| `FILTER_LOCATION` | `دانش` | نام شعبه |
| `FILTER_START_HOUR` | `7` | ساعت شروع |
| `FILTER_START_MINUTE` | `0` | دقیقه شروع |
| `FILTER_END_HOUR` | `17` | ساعت پایان |
| `FILTER_END_MINUTE` | `0` | دقیقه پایان |
| `EXCLUDE_FULL_CAPACITY` | `true` | حذف شیفت‌های پر شده |
| `CHECK_INTERVAL_MINUTES` | `30` | فاصله چک |

### مثال‌های فیلتر:

**فقط Stow و Pick در دانش:**
```
FILTER_JOB_TITLES=Stow,Pick
FILTER_LOCATION=دانش
```

**همه شیفت‌های دانش (هر نوعی):**
```
FILTER_JOB_TITLES=
FILTER_LOCATION=دانش
```

**شیفت‌های شبانه Dispatch در بادامک:**
```
FILTER_JOB_TITLES=Dispatch
FILTER_LOCATION=بادامک
FILTER_START_HOUR=17
FILTER_END_HOUR=3
```

## 🌐 Proxy Pool

سیستم خودکار از ۴ منبع پروکسی رایگان ایرانی استفاده می‌کنه:

| منبع | نوع | نحوه دسترسی |
|------|-----|-------------|
| ProxyScrape API | SOCKS5/HTTP | API با فیلتر country=IR |
| Geonode API | HTTP/HTTPS/SOCKS5 | API با JSON |
| monosans/proxy-list | SOCKS5/HTTP | GitHub raw |
| proxifly/free-proxy-list | HTTP | GitHub raw |

### نحوه کار:
1. هر ۱۰ دقیقه از همه منابع fetch می‌کنه
2. health check موازی روی همه (با `asyncio`)
3. نگه‌داری ۸ پروکسی سالم در pool
4. هر درخواست از یه پروکسی استفاده می‌کنه (round-robin)
5. اگه پروکسی fail شد، عوض می‌شه

### امنیت:
- ✅ همه درخواست‌ها HTTPS هستن
- ✅ TLS verification همیشه روشن (`verify=True`)
- ✅ پروکسی نمی‌تونه توکن JWT رو ببینه (چون داخل HTTPS encrypted هست)
- ✅ از SOCKS5 proxy استفاده می‌شه (امن‌تر از HTTP proxy)

## 🔧 دستورات تلگرام

| دستور | توضیح |
|-------|-------|
| `/start` | شروع |
| `/help` | راهنمای گرفتن توکن |
| `/status` | وضعیت توکن فعلی |
| `/refresh` | چک دستی شیفت‌ها |
| (هر متن دیگه) | اگه JWT معتبر باشه، ذخیره می‌شه |

## 🔒 امنیت

| مورد | توضیح |
|------|-------|
| توکن JWT | در فایل با `chmod 600` ذخیره می‌شه |
| صفحه وب | با پسورد (`WEB_PASSWORD`) محافظت می‌شه |
| TLS Verification | همیشه روشن - جلوگیری از MITM |
| HTTPS | همه درخواست‌ها به دیجی‌کالا HTTPS هستن |
| پروکسی | نمی‌تونه ترافیک encrypted رو بخونه |

> ⚠️ توکن JWT = پسورد لاگین شماست. هرگز به کسی نده.

## 📊 داشبورد

در صفحه وب می‌تونی ببینی:
- وضعیت توکن (معتبر/منقضی + روزهای باقی‌مانده)
- آخرین زمان چک
- تعداد شیفت‌های گزارش شده
- وضعیت Proxy Pool (تعداد سالم + لیست)
- فیلترهای فعال
- اجرای دستی چک
- refresh دستی پروکسی‌ها

## 🔄 تمدید توکن

توکن JWT هر ~۵ روز منقضی می‌شه. وقتی منقضی شد:

### روش ۱: از طریق صفحه وب
1. با Kiwi Browser لاگین کن
2. توکن جدید رو از DevTools بگیر
3. وارد صفحه وب Railway بشو
4. روی «آپدیت توکن» کلیک کن
5. Paste کن و ذخیره کن

### روش ۲: از طریق تلگرام
1. توکن جدید رو از DevTools بگیر
2. به ربات تلگرامت بفرست
3. ربات خودکار ذخیره می‌کنه

## 🐛 عیب‌یابی

### مشکل: نوتیف تلگرام نمیاد
- `TELEGRAM_BOT_TOKEN` و `TELEGRAM_CHAT_ID` رو چک کن
- در مرورگر تست کن: `https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<CHAT_ID>&text=test`

### مشکل: ارور 401 (توکن منقضی)
- توکن جدید رو از Kiwi Browser بگیر
- در صفحه وب paste کن

### مشکل: ارور 403/451 (IP بلاک)
- پروکسی‌ها در حال refresh شدن
- صبر کن ۱۰ دقیقه
- یا دستی refresh کن: `POST /api/refresh-proxies`

### مشکل: هیچ پروکسی سالمی نیست
- پروکسی‌های رایگان ناپایدارن
- صبر کن تا refresh بعدی
- اگه طولانی شد، یه VPS ایرانی بگیر

### مشکل: صفحه وب باز نمی‌شه
- صبر کن تا build کامل بشه
- Domain رو در Railway → Settings → Networking چک کن

📖 **راهنمای کامل عیب‌یابی**: [DEPLOY_RAILWAY.md](DEPLOY_RAILWAY.md)

## 💰 هزینه

| مورد | هزینه |
|------|-------|
| Railway Trial | $5 credit رایگان (~۲-۳ هفته) |
| Railway Hobby | $5/ماه (پس از trial) |
| ربات تلگرام | رایگان |
| پروکسی‌ها | رایگان |
| **کل** | **رایگان** (با ساخت اکانت جدید هر ماه) |

## 🆘 پشتیبانی

اگه مشکل داشتی:
1. لاگ‌های Railway رو چک کن (تب Logs)
2. داشبورد رو در صفحه وب ببین
3. ربات تلگرام رو با `/status` چک کن
4. راهنمای deploy رو بخون: [DEPLOY_RAILWAY.md](DEPLOY_RAILWAY.md)

---

**موفق باشید! 🎯**
