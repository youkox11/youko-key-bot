# YOUKO AUTO KEY BOT V2

Telegram bot (Python 3.11+) ដែលពិនិត្យតំណ (link) ពី LootLabs, Platoboost និង Linkvertise ហើយបញ្ជូនទៅ **API ដែលមានការអនុញ្ញាត** (authorized API) តែមួយដែលអ្នកកំណត់ប៉ុណ្ណោះ។

> ⚠️ **សំខាន់៖** Bot នេះ **មិន** bypass ការផ្សាយពាណិជ្ជកម្ម CAPTCHA ប្រព័ន្ធ anti-bot ឬប្រព័ន្ធផ្ទៀងផ្ទាត់ key របស់ភាគីទីបីទេ។ វាមិនបង្កើត key ក្លែងក្លាយទេ។ បើមិនមាន API ដែលមានការអនុញ្ញាតទេ bot នឹងប្រាប់ថា "Automatic key retrieval is unavailable"។ តាមការយល់ដឹងរបស់យើង LootLabs, Platoboost និង Linkvertise មិនមាន public API ផ្លូវការសម្រាប់ទាញយក key ពីតំណដោយមិនបំពេញជំហានទេ ដូច្នេះ adapter ក្នុង `providers.py` ត្រូវការ API របស់អ្នកផ្ទាល់ (ឧ. ប្រព័ន្ធ key របស់អ្នក ឬដៃគូដែលអនុញ្ញាត) ដែលធ្វើតាម contract ខាងក្រោម។

---

## ១. អ្វីដែលបានបញ្ចប់ និងអ្វីដែលត្រូវការ API ភាគីទីបី

| មុខងារ | ស្ថានភាព |
|---|---|
| `/start`, `/help`, `/status`, `/supported` | ✅ ដំណើរការភ្លាមៗ |
| ទទួលតំណ HTTPS និងសម្គាល់ LootLabs / Platoboost / Linkvertise | ✅ |
| Validate តំណ (HTTPS, គ្មាន IP, គ្មាន credentials, គ្មាន port ផ្សេង) | ✅ |
| Rate limit ក្នុងមួយអ្នកប្រើ, ការពារសំណើស្ទួន | ✅ |
| ឯកជនភាព (ដំណើរការតែក្នុង private chat) | ✅ |
| Startup validation (ប្រាប់ឈ្មោះ variable ដែលបាត់ ដោយមិនបង្ហាញ secret) | ✅ |
| Long polling (local) និង webhook (Render) | ✅ |
| ទាញយក key ពិតប្រាកដ | ⏳ ត្រូវការ API ដែលមានការអនុញ្ញាត (`AUTHORIZED_API_URL` + `AUTHORIZED_API_TOKEN`) |

---

## ២. រចនាសម្ព័ន្ធ Project

```
youko-key-bot/
├── bot.py
├── config.py
├── providers.py
├── requirements.txt
├── .env.example
├── .gitignore
├── render.yaml
└── README.md
```

---

## ៣. ដំឡើង និង Test លើ Windows 11 (CMD)

ត្រូវការ Python 3.11 ឬថ្មីជាងនេះ។ ពិនិត្យ៖

```
py --version
```

### ជំហាន ៣.១ — ចូលទៅក្នុងថតត្រឹមត្រូវ

កំហុស `No such file or directory: requirements.txt` កើតឡើងពេលអ្នកមិននៅក្នុងថត project។ ពិនិត្យជានិច្ចថាអ្នកឃើញ `requirements.txt` មុនពេលដំឡើង៖

```
cd %USERPROFILE%\Desktop\youko-key-bot
dir
```

ក្នុងលទ្ធផល `dir` ត្រូវតែមាន `bot.py` និង `requirements.txt`។

### ជំហាន ៣.២ — បង្កើត virtual environment និងដំឡើង packages

```
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

(បើអ្នកមានតែ Python កំណែផ្សេង ដូចជា 3.12 ប្រើ `py -m venv .venv` ជំនួស។)

### ជំហាន ៣.៣ — កំណត់ Telegram Token ឱ្យត្រឹមត្រូវ

១. បើក Telegram → ស្វែងរក `@BotFather` → ផ្ញើ `/newbot` → ធ្វើតាមការណែនាំ → ចម្លង token (មើលទៅដូច `123456789:AAH...`)។

២. **វិធីទី ១ (ណែនាំ) — ប្រើឯកសារ `.env`៖**

```
copy .env.example .env
notepad .env
```

កែបន្ទាត់នេះ (**គ្មាន** សញ្ញាសម្រង់ និង **គ្មាន** ដកឃ្លាជុំវិញ `=`)៖

```
TELEGRAM_BOT_TOKEN=123456789:ដាក់_token_របស់អ្នកនៅទីនេះ
```

Save ហើយបិទ។ ⚠️ ឈ្មោះឯកសារត្រូវតែ `.env` មិនមែន `.env.txt` ទេ។ ការប្រើ `copy` ដូចខាងលើជៀសវាងបញ្ហា Notepad បន្ថែម `.txt`។ ពិនិត្យដោយ `dir /a`។

៣. **វិធីទី ២ — កំណត់ក្នុង CMD (មានប្រសិទ្ធភាពតែក្នុងបង្អួច CMD នេះ)៖**

```
set TELEGRAM_BOT_TOKEN=123456789:ដាក់_token_របស់អ្នកនៅទីនេះ
```

កុំដាក់ `"..."` ព្រោះ CMD នឹងរួមបញ្ចូលសញ្ញាសម្រង់ទៅក្នុងតម្លៃ។

### ជំហាន ៣.៤ — ដំណើរការ bot

```
python bot.py
```

បើ variable បាត់ bot នឹងបង្ហាញឈ្មោះ variable ដែលបាត់ (មិនបង្ហាញតម្លៃ) ហើយបិទ ឧទាហរណ៍៖

```
Startup check failed.
Missing environment variables:
  - TELEGRAM_BOT_TOKEN
```

ទុក CMD បើកចោល។ បិទ bot ដោយចុច `Ctrl + C`។

### ជំហាន ៣.៥ — Test នៅលើ Telegram

ស្វែងរក bot របស់អ្នក ហើយសាកល្បង (**ក្នុង private chat**)៖

| ផ្ញើ | លទ្ធផលរំពឹងទុក |
|---|---|
| `/start` | សារស្វាគមន៍ |
| `/help`, `/status`, `/supported` | បញ្ជីពាក្យបញ្ជា / ស្ថានភាព / សេវាកម្ម |
| `https://example.com` | ❌ Unsupported service |
| `http://linkvertise.com/1` | ❌ Only HTTPS links are accepted |
| `https://linkvertise.com/123/test` | ✅ Valid Linkvertise link recognized + ព័ត៌មានថា API មិនទាន់កំណត់ |

---

## ៤. Upload ទៅ GitHub

ដំឡើង Git សិន ប្រសិនបើមិនទាន់មាន។ បង្កើត repository ទទេឈ្មោះ `youko-key-bot` នៅក្នុងគណនី `youkox11` លើ github.com ហើយបន្ទាប់មកក្នុង CMD (នៅក្នុងថត project)៖

```
git init
git add .
git status
```

ពិនិត្យថា `.env` **មិន** ស្ថិតក្នុងបញ្ជី (`.gitignore` ការពារវារួចហើយ)។ បន្ទាប់មក៖

```
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/youkox11/youko-key-bot.git
git push -u origin main
```

> 🔐 បើអ្នកធ្លាប់ push token ទៅ GitHub ដោយចៃដន្យ សូមទៅ `@BotFather` → `/revoke` ដើម្បីបង្កើត token ថ្មីភ្លាមៗ។

---

## ៥. Deploy លើ Render

Architecture៖ **Web Service + webhook**។ Render កំណត់ `RENDER_EXTERNAL_URL` និង `PORT` ដោយស្វ័យប្រវត្តិ ហើយ bot ចុះឈ្មោះ webhook ជាមួយ Telegram ដោយខ្លួនឯង។

១. ចូល render.com → **New +** → **Web Service** → ភ្ជាប់ GitHub → ជ្រើស `youkox11/youko-key-bot`។
(ឬប្រើ **Blueprint** ដើម្បីអាន `render.yaml`)។

២. កំណត់៖
- Runtime: **Python 3**
- Build Command: `pip install -r requirements.txt`
- Start Command: `python bot.py`

៣. **Environment Variables** (ផ្ទាំង Environment)៖

| Key | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | token ពី BotFather |
| `WEBHOOK_SECRET` | ខ្សែអក្សរចៃដន្យ 16–256 តួ ប្រើតែ `A-Z a-z 0-9 _ -` (ឧ. បង្កើតដោយ `python -c "import secrets; print(secrets.token_urlsafe(32))"`) |
| `PYTHON_VERSION` | `3.11.9` |
| `AUTHORIZED_API_URL` / `AUTHORIZED_API_TOKEN` | ដាក់តែពេលអ្នកមាន API ដែលមានការអនុញ្ញាត |

៤. ចុច **Deploy**។ រង់ចាំរហូតដល់ស្ថានភាព **Live** ហើយពិនិត្យ Logs ឃើញ `Starting in webhook mode`។

៥. Test `/start` និងតំណនៅលើ Telegram ដូចជំហាន ៣.៥។

> ℹ️ **កំណត់សម្គាល់ Free plan៖** Render Free web service ចូលដេក (spin down) បន្ទាប់ពីគ្មានចរាចរមួយរយៈ ដូច្នេះសារដំបូងអាចយឺត ហើយ **មិនធានា uptime 24/7 ទេ**។ បើត្រូវការភាពអាចទុកចិត្តបាន សូមប្រើ paid plan។

---

## ៦. បន្ថែម Authorized API នៅពេលក្រោយ

កំណត់ `AUTHORIZED_API_URL` (HTTPS) និង `AUTHORIZED_API_TOKEN` ក្នុង `.env` ឬ Render។ Bot ប្រើ contract នេះ៖

**សំណើ**

```
POST {AUTHORIZED_API_URL}
Authorization: Bearer {AUTHORIZED_API_TOKEN}
Content-Type: application/json

{"service": "Linkvertise", "url": "https://..."}
```

**ចម្លើយ (JSON)**

```json
{"status": "completed", "key": "FREE_XXXXXXXXXXXXXXXX"}
{"status": "pending", "job_id": "abc123"}
{"status": "failed"}
```

បើ `pending` bot នឹងសួរ `GET {AUTHORIZED_API_URL}/{job_id}` រហូតដល់ `completed`/`failed` ឬអស់ពេល (`JOB_TIMEOUT_SECONDS`)។

ការការពារដែលភ្ជាប់មកជាមួយ៖
- សំណើចេញទៅកាន់តែ host នៃ `AUTHORIZED_API_URL` ប៉ុណ្ណោះ, មិនតាម redirect (ការពារ SSRF)
- តំណអ្នកប្រើមិនត្រូវបាន fetch ដោយ bot ទេ គ្រាន់តែបញ្ជូនជា data ទៅ API
- key ត្រូវបាន validate មុនផ្ញើ ហើយផ្ញើតែទៅអ្នកដែលស្នើសុំ
- Log មិនមាន key ឬតំណពេញលេញ (ប្រើ hash ខ្លី)

បើ API របស់អ្នកមានទម្រង់ផ្សេង សូមកែតែ `AuthorizedApiProvider._interpret` និង `fetch_key` ក្នុង `providers.py`។

---

## ៧. កំហុសទូទៅ

| កំហុស | ដំណោះស្រាយ |
|---|---|
| `TELEGRAM_BOT_TOKEN` បាត់ | ពិនិត្យថា `.env` មាននៅក្នុងថតតែមួយជាមួយ `bot.py` (មិនមែន `.env.txt`) ឬប្រើ `set` ក្នុង CMD ដដែល |
| `No such file or directory: requirements.txt` | `cd` ចូលថត project ហើយ `dir` ដើម្បីឃើញ `requirements.txt` |
| `token format looks wrong` | ចម្លង token ម្តងទៀតពី BotFather គ្មានសញ្ញាសម្រង់ ឬដកឃ្លា |
| Bot មិនឆ្លើយតបក្នុង group | ប្រើ private chat (bot ដំណើរការតំណតែក្នុង private chat ដើម្បីឯកជនភាព) |
| Render: bot ឆ្លើយយឺត | Free plan ដេក, រង់ចាំ ឬប្រើ paid plan |
