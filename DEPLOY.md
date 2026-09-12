# 🚀 راهنمای Deploy با GitHub Actions

این راهنما قدم‌به‌قدم نحوه راه‌اندازی این‌شیفت مانیتور با GitHub Actions (کاملاً رایگان) رو توضیح می‌ده.

## ✅ مزایا

- 💚 کاملاً رایگان (برای public repos، دقیقه نامحدود)
- 🚫 بدون نیاز به credit card
- ⏰ ۲۴/۷ روشن
- 🤖 خودکار و بدون نیاز به VPS
- 🇮🇷 از ایران هم کار می‌کنه (فقط GitHub account لازم داره)

---

## 📋 پیش‌نیازها

- یه اکانت GitHub (رایگان)
- یه ربات تلگرام (از @BotFather)
- توکن JWT این‌شیفت (با Kiwi Browser می‌گیری)
- (اختیاری) Personal Access Token برای آپدیت خودکار توکن

---

## 🎯 قدم ۱: فورک یا clone ریپو

اگه ریپو رو فورک کردی، خودکار در اکانت تو هست. اگه نه:

```bash
git clone https://github.com/rohnavaz07-ai/inshift-monitor.git
cd inshift-monitor
```

---

## 🎯 قدم ۲: ساخت ربات تلگرام

1. در تلگرام به **@BotFather** پیام بده
2. دستور `/newbot` رو بفرست
3. یه اسم انتخاب کن (مثل "Inshift Monitor")
4. یه username انتخاب کن (مثل `my_inshift_bot`)
5. **توکن** رو کپی کن (مثل: `1234567890:ABCdefGHIjklmNOP...`)

## 🎯 قدم ۳: گرفتن Chat ID خودت

1. به رباتی که ساختی یه پیام `/start` بده
2. در مرورگر این URL رو باز کن:
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
3. در پاسخ JSON، عدد `chat.id` رو پیدا کن (مثل `123456789`)

---

## 🎯 قدم ۴: تنظیم GitHub Secrets

در ریپو → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:

### ضروری:

| Secret Name | Value |
|-------------|-------|
| `TELEGRAM_BOT_TOKEN` | توکن ربات تلگرام |
| `TELEGRAM_CHAT_ID` | chat id شما |
| `INSHIFT_TOKEN` | توکن JWT (قدم ۶ رو ببین) |

### اختیاری (برای آپدیت خودکار توکن):

| Secret Name | Value |
|-------------|-------|
| `GH_PAT` | Personal Access Token با scope `repo` |

---

## 🎯 قدم ۵: (اختیاری) تنظیم متغیرهای فیلتر

در ریپو → **Settings** → **Secrets and variables** → **Actions** → تب **Variables** → **New variable**:

| Variable | Value |
|----------|-------|
| `FILTER_JOB_TITLES` | `Stow,Pick` (پیش‌فرض) |
| `FILTER_LOCATION` | `دانش` (پیش‌فرض) |
| `FILTER_START_HOUR` | `7` (پیش‌فرض) |
| `FILTER_END_HOUR` | `17` (پیش‌فرض) |

> 💡 اگه چیزی set نکنی، از پیش‌فرض‌ها استفاده می‌شه.

---

## 🎯 قدم ۶: گرفتن توکن JWT این‌شیفت

1. **Kiwi Browser** رو روی گوشی نصب کن (از Play Store)
2. وارد `inshift.digikala.com` شو و لاگین کن
3. به صفحه Jobs برو
4. منوی Kiwi (سه نقطه) → **Developer tools**
5. تب **Network** → فیلتر **Fetch/XHR**
6. صفحه رو رفرش کن
7. روی `jobs?page=1` کلیک کن
8. تب **Headers** → **Request Headers**
9. مقدار `Authorization` رو کپی کن (یه رشته طولانی که با `eyJ` شروع می‌شه)
10. در GitHub Secrets به‌عنوان `INSHIFT_TOKEN` اضافه کن

---

## 🎯 قدم ۷: ساخت PAT برای آپدیت خودکار توکن (اختیاری)

برای اینکه بعداً بتونی از طریق تلگرام توکن رو آپدیت کنی (به‌جای آپدیت دستی در GitHub):

1. برو به https://github.com/settings/tokens
2. **Generate new token (classic)**
3. تنظیمات:
   - Note: `inshift-bot`
   - Expiration: 90 days (یا بیشتر)
   - Scope: `repo` (تیک کامل)
4. **Generate token** رو بزن
5. توکن رو کپی کن (فقط یه بار نشون می‌ده!)
6. در GitHub Secrets به‌عنوان `GH_PAT` اضافه کن

---

## 🎯 قدم ۸: فعال‌سازی Workflows

1. برو به تب **Actions** در ریپو
2. اگه warning دیدی درباره workflows، **I understand my workflows, go ahead and enable them** رو بزن
3. دو تا workflow می‌بینی:
   - **Inshift Monitor** - هر ۳۰ دقیقه
   - **Telegram Bot** - هر ۵ دقیقه

---

## 🎯 قدم ۹: تست اولیه

### تست دستی Monitor:

1. در تب Actions، روی **Inshift Monitor** بزن
2. دکمه **Run workflow** رو بزن
3. صبر کن تا کامل بشه (حدود ۱-۲ دقیقه)
4. روی run کلیک کن و لاگ‌ها رو ببین
5. باید ببینی:
   ```
   🚀 GitHub Actions: Inshift Monitor - 2026-09-13 12:00:00
   🌐 در حال راه‌اندازی Proxy Pool...
   ✓ Proxy Pool: 5 پروکسی سالم از 50
   📡 تلاش 1: استفاده از socks5://1.2.3.4:1080
   ✓ موفق! 50 شیفت دریافت شد.
   📊 کل: 50 | Match: 3 | جدید: 3
   ✓ بررسی کامل شد.
   ```

### تست ربات تلگرام:

1. در تلگرام به رباتت پیام `/start` بده
2. صبر کن تا ۵ دقیقه (تا workflow بعدی اجرا بشه)
3. ربات باید جواب بده
4. اگه `/status` بزنی، وضعیت توکن رو می‌گه
5. اگه توکن جدید بفرستی، خودکار آپدیت می‌کنه

---

## 🎯 قدم ۱۰: تماشای کار سیستم

- ⏰ هر ۳۰ دقیقه (ممکنه ۵-۱۰ دقیقه delay داشته باشه در زمان‌های پیک) workflow اجرا می‌شه
- 📊 در تب Actions می‌تونی history همه اجراها رو ببینی
- 🤖 ربات تلگرام هر ۵ دقیقه پیام‌ها رو چک می‌کنه
- 💾 state.json و bot_state.json به‌صورت خودکار به ریپو commit می‌شن

---

## 📊 مانیتورینگ

### مشاهده لاگ‌ها:
1. تب Actions
2. روی workflow کلیک کن
3. روی run کلیک کن
4. روی job کلیک کن
5. لاگ‌ها رو ببین

### بررسی state.json:
فایل `state.json` در ریپو رو باز کن:
```json
{
  "notified_shifts": ["34881", "34899", ...],
  "last_check": "2026-09-13T12:00:00+03:30"
}
```

### اجرای دستی:
در تب Actions → Run workflow

---

## 🔧 عیب‌یابی

### مشکل: workflow اجرا نمی‌شه
1. تب Actions → مطمئن شو workflows enabled هستن
2. مطمئن شو secrets درست set شدن (غلط‌املایی ندارن)
3. workflow رو دستی Run کن و لاگ رو ببین

### مشکل: لاگ می‌گه "INSHIFT_TOKEN تنظیم نشده"
1. ریپو → Settings → Secrets → بررسی کن `INSHIFT_TOKEN` اضافه شده
2. اگه نبود، اضافه کن
3. workflow رو دوباره Run کن

### مشکل: لاگ می‌گه "TELEGRAM_BOT_TOKEN تنظیم نشده"
همون بالا، ولی برای `TELEGRAM_BOT_TOKEN` و `TELEGRAM_CHAT_ID`

### مشکل: هیچ پروکسی سالمی نیست
1. لاگ‌ها رو ببین - باید ببینی چندتا پروکسی fetch شده و چندتا سالمه
2. اگه ۰ تا سالمه، چند بار workflow رو re-run کن (پروکسی‌های رایگان ناپایدارن)
3. اگه بازم نشد، صبر کن ۱۰-۱۵ دقیقه و دوباره امتحان کن

### مشکل: ربات تلگرام جواب نمی‌ده
1. مطمئن شو `TELEGRAM_BOT_TOKEN` و `TELEGRAM_CHAT_ID` درست set شدن
2. در تب Actions، Telegram Bot workflow رو پیدا کن
3. لاگ‌ها رو ببین
4. اگه `GH_PAT` set نیست، فقط می‌تونی `/status` و `/help` بزنی (آپدیت توکن کار نمی‌کنه)

### مشکل: آپدیت توکن کار نمی‌کنه
1. مطمئن شو `GH_PAT` secret set شده
2. مطمئن شو PAT scope `repo` داره
3. لاگ‌های Telegram Bot workflow رو ببین

### مشکل: توکن منقضی می‌شه
- توکن JWT هر ~۵ روز منقضی می‌شه (طبیعیه)
- وقتی منقضی بشه، monitor تلگرام بهت اخطار می‌ده
- توکن جدید رو از Kiwi Browser بگیر
- یا: به ربات تلگرامت بفرست (اگه GH_PAT set شده)
- یا: دستی در GitHub Secrets آپدیت کن

### مشکل: workflow delay داره
- GitHub Actions گاهی ۵-۱۵ دقیقه delay داره (مخصوصاً در زمان پیک)
- این طبیعیه و کاری نمیشه کرد
- اگه خیلی مهمه، می‌تونی interval رو کمتر کنی (مثلاً هر ۱۵ دقیقه)

---

## ⚙️ تنظیمات پیشرفته

### تغییر فاصله چک:

فایل `.github/workflows/monitor.yml` رو ویرایش کن:

```yaml
on:
  schedule:
    - cron: '*/15 * * * *'  # هر ۱۵ دقیقه
    # یا
    - cron: '0 * * * *'      # هر ساعت
```

> ⚠️ توصیه نمیشه کمتر از ۱۵ دقیقه بذاری (ممکنه GitHub rate limit بزنه)

### تغییر فیلترها بدون ویرایش کد:

در ریپو → Settings → Secrets and variables → Actions → Variables:

| Variable | Value |
|----------|-------|
| `FILTER_JOB_TITLES` | `Stow,Pick,Sort` |
| `FILTER_LOCATION` | `بادامک` |
| `FILTER_START_HOUR` | `17` |
| `FILTER_END_HOUR` | `3` |

---

## 🔄 آپدیت کد

اگه کد جدیدی push کنی، خودکار workflow در اجرای بعدی از کد جدید استفاده می‌کنه.

```bash
git add .
git commit -m "Update"
git push
```

---

## 💰 هزینه

| مورد | هزینه |
|------|-------|
| GitHub Actions (public repo) | **رایگان نامحدود** ✅ |
| GitHub Secrets | رایگان |
| ربات تلگرام | رایگان |
| پروکسی‌ها | رایگان |
| **کل** | **رایگان** ✅ |

---

## 🆘 پشتیبانی

اگه مشکل داشتی:
1. تب Actions در GitHub رو چک کن
2. لاگ‌های workflow رو ببین
3. ربات تلگرام رو با `/status` چک کن
4. این راهنما رو دوباره بخون

موفق باشی! 🚀
