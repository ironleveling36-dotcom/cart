# 🤖 Telegram OTP Bot

Automated OTP receiving bot powered by [OTPDoctor.in](https://otpdoctor.in).

## Features

- 🌍 Multi-country support
- 📱 All services via OTPDoctor API
- 🔄 Auto-wait & auto-cancel (3 min timeout)
- ✅ Swiggy & Myntra: auto-checks for unregistered numbers before sending
- 💰 Balance check command

## Setup

### 1. Clone & install
```bash
git clone <your-repo>
cd otp-bot
pip install -r requirements.txt
```

### 2. Configure env
```bash
cp .env.example .env
# Edit .env and set BOT_TOKEN
```

### 3. Run locally
```bash
python bot.py
```

---

## Deploy to Railway

1. Push this repo to GitHub
2. Go to [Railway](https://railway.app) → **New Project** → **Deploy from GitHub repo**
3. Select your repo
4. Go to **Variables** tab and set:
   - `BOT_TOKEN` = your Telegram bot token (from @BotFather)
   - `OTP_API_KEY` = your OTPDoctor API key
5. Railway will auto-detect `railway.toml` and deploy 🚀

---

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Main menu |
| `/balance` | Check OTPDoctor wallet balance |

## Flow

```
/start
  └─ Get OTP Number
        └─ Select Country
              └─ Select Service
                    ├─ Normal: Purchase → Send number → Wait OTP → Forward OTP (or cancel)
                    └─ Swiggy/Myntra: Purchase → Check registration → If registered cancel & retry
                                       → Send unregistered number → Wait OTP → Forward OTP (or cancel)
```
