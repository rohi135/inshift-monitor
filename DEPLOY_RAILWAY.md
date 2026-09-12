# 🚀 راهنمای Deploy روی Railway

این راهنما قدم‌به‌قدم نحوه deploy کردن این‌شیفت مانیتور روی Railway رو توضیح می‌ده.

## 📋 پیش‌نیازها

- یه اکانت GitHub
- یه اکانت Railway (رایگان - با $5 credit شروع می‌کنه)
- یه ربات تلگرام (از @BotFather بگیر)
- توکن JWT این‌شیفت (با Kiwi Browser می‌گیری)

---

## 🎯 قدم ۱: ساخت ربات تلگرام

1. در تلگرام به **@BotFather** پیام بده
2. دستور `/newbot` رو بفرست
3. یه اسم انتخاب کن (مثل "Inshift Monitor")
4. یه username انتخاب کن (مثل `my_inshift_bot`)
5. **توکن** رو کپی کن (مثل: `1234567890:ABCdefGHIjklmNOP...`)

## 🎯 قدم ۲: گرفتن Chat ID خودت

1. به رباتی که ساختی یه پیام `/start` بده
2. در مرورگر این URL رو باز کن (به‌جای `<TOKEN>` توکن رباتت):
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
3. در پاسخ JSON، عدد `chat.id` رو پیدا کن (مثل `123456789`)

## 🎯 قدم ۳: آپلود کد به GitHub

### روش الف: مستقیم از کامپیوتر

```bash
# کلون کردن یا کپی کردن پوشه inshift-monitor
cd inshift-monitor

# init git
git init
git add .
git commit -m "Initial commit - Inshift Monitor"

# به GitHub push کن
git remote add origin https://github.com/YOUR_USERNAME/inshift-monitor.git
git branch -M main
git push -u origin main
```

### روش ب: از طریق GitHub Web

1. وارد GitHub.com بشو
2. New repository → اسم بزن → Create
3. فایل‌ها رو یکی یکی upload کن

## 🎯 قدم ۴: ساخت اپ روی Railway

1. وارد [railway.app](https://railway.app) بشو
2. **Login with GitHub**
3. **New Project** → **Deploy from GitHub repo**
4. ریپوی `inshift-monitor` رو انتخاب کن
5. Railway خودش `Dockerfile` رو تشخیص می‌ده و build می‌کنه
6. صبر کن تا build تموم بشه (حدود ۲-۳ دقیقه)

## 🎯 قدم ۵: تنظیم Environment Variables

در صفحه Railway اپت، تب **Variables** رو باز کن و این‌ها رو اضافه کن:

| Variable Name | Value | توضیح |
|---------------|-------|-------|
| `TELEGRAM_BOT_TOKEN` | `1234567890:ABCdef...` | توکن ربات تلگرام |
| `TELEGRAM_CHAT_ID` | `123456789` | chat id خودت |
| `WEB_PASSWORD` | `mySecretPass123` | پسورد صفحه وب (دلخواه) |
| `CHECK_INTERVAL_MINUTES` | `30` | فاصله چک (دقیقه) |
| `PROXY_REFRESH_MINUTES` | `10` | فاصله refresh پروکسی‌ها |
| `FILTER_JOB_TITLES` | `Stow,Pick` | عناوین شغلی (با کاما جدا) |
| `FILTER_LOCATION` | `دانش` | نام شعبه |
| `FILTER_START_HOUR` | `7` | ساعت شروع |
| `FILTER_START_MINUTE` | `0` | دقیقه شروع |
| `FILTER_END_HOUR` | `17` | ساعت پایان |
| `FILTER_END_MINUTE` | `0` | دقیقه پایان |
| `EXCLUDE_FULL_CAPACITY` | `true` | حذف شیفت‌های پر شده |

> 💡 اگه variableای رو set نکنی، از مقدار پیش‌فرض استفاده می‌شه.

## 🎯 قدم ۶: تنظیم Domain

1. در صفحه Railway اپت، تب **Settings** رو باز کن
2. بخش **Networking** → **Generate Domain**
3. یه URL می‌گیری مثل: `inshift-monitor-production.up.railway.app`
4. این URL رو ذخیره کن - این آدرس صفحه وبته

## 🎯 قدم ۷: تست

1. اپ رو در Railway باز کن - باید لاگ‌ها رو ببینی:
   ```
   🚀 راه‌اندازی اپ...
   🤖 ربات تلگرام شروع شد
   ⏰ Scheduler شروع شد
   ```
2. در تلگرام، رباتت پیام «این‌شیفت مانیتور فعال شد!» رو می‌فرسته
3. صفحه وب رو باز کن: `https://your-app.up.railway.app/`
4. پسورد `WEB_PASSWORD` رو وارد کن
5. به داشبورد می‌ری
6. روی «آپدیت توکن» کلیک کن
7. توکن JWT رو paste کن (طبق راهنمای تو همون صفحه)
8. ذخیره کن

## 🎯 قدم ۸: گرفتن توکن JWT

1. **Kiwi Browser** رو روی گوشی نصب کن (از Play Store)
2. وارد `inshift.digikala.com` شو و لاگین کن
3. به صفحه Jobs برو
4. منوی Kiwi → **Developer tools**
5. تب **Network** → فیلتر **Fetch/XHR**
6. صفحه رو رفرش کن
7. روی `jobs?page=1` کلیک کن
8. تب **Headers** → **Request Headers**
9. مقدار `Authorization` رو کپی کن
10. در صفحه وب Railway paste کن

## 🎯 قدم ۹: تماشای کار سیستم

- هر ۳۰ دقیقه (یا هرچی تنظیم کردی) چک می‌شه
- اگه شیفت match بشه، تلگرام بهت پیام می‌ده
- اگه توکن منقضی بشه، تلگرام بهت می‌گه
- داشبورد رو رفرش کن تا آخرین وضعیت رو ببینی

---

## 🔧 عیب‌یابی

### مشکل: اپ روی Railway اجرا نمی‌شه
1. تب **Logs** رو در Railway چک کن
2. معمولاً خطا مربوط به missing environment variable هست
3. مطمئن شو `TELEGRAM_BOT_TOKEN` و `TELEGRAM_CHAT_ID` تنظیم شدن

### مشکل: صفحه وب باز نمی‌شه
1. صبر کن تا build کامل بشه (ممکنه ۲-۳ دقیقه طول بکشه)
2. تب **Settings** → **Networking** → مطمئن شو domain generated شده
3. URL رو مستقیم باز کن: `https://your-app.up.railway.app/`

### مشکل: پسورد قبول نمی‌شه
1. در Railway → Variables → `WEB_PASSWORD` رو چک کن
2. اپ رو restart کن: **Settings** → **Restart**

### مشکل: تلگرام پیام نمی‌ده
1. توکن ربات رو در `TELEGRAM_BOT_TOKEN` چک کن
2. chat_id رو در `TELEGRAM_CHAT_ID` چک کن (بدون کوتیشن)
3. در مرورگر تست کن:
   ```
   https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<CHAT_ID>&text=test
   ```

### مشکل: پروکسی‌ها کار نمی‌کنن
1. در داشبورد، وضعیت Proxy Pool رو ببین
2. اگه ۰ سالم هست، صبر کن ۱۰ دقیقه تا refresh بشه
3. می‌تونی دستی هم refresh کنی: `POST /api/refresh-proxies`

### مشکل: توکن منقضی می‌شه
- توکن JWT هر ~۵ روز منقضی می‌شه (طبیعیه)
- وقتی منقضی بشه، تلگرام بهت اخطار می‌ده
- وارد صفحه وب بشو، توکن جدید رو paste کن

---

## 💰 هزینه Railway

- **Trial**: $5 credit رایگان (حدود ۲-۳ هفته برای اپ ۲۴/۷)
- **پس از trial**: Hobby plan - $5/ماه برای 500 ساعت executor
- **راه‌حل رایگان**: یه اکانت جدید با ایمیل دیگه بساز و $5 credit جدید بگیر

---

## 🔄 آپدیت کد

اگه کد رو در GitHub آپدیت کنی، Railway خودش دوباره build و deploy می‌کنه.

```bash
git add .
git commit -m "Update"
git push
```

---

## 🆘 پشتیبانی

اگه به مشکل خوردی:
1. لاگ‌های Railway رو چک کن
2. داشبورد رو ببین
3. ربات تلگرام رو با `/status` چک کن

موفق باشی! 🚀
