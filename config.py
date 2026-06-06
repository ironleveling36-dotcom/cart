import os

# ── Telegram ──────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# ── OTPDoctor ─────────────────────────────────────────────
OTP_API_KEY = os.getenv("OTP_API_KEY", "q6v6ef7r50mm4wkbkmq8a1ntxs8qx3wl")
OTP_BASE_URL = "https://www.otpdoctor.in/stubs/handler_api.php"

# ── Behaviour ─────────────────────────────────────────────
OTP_POLL_INTERVAL   = 5      # seconds between status checks
OTP_TIMEOUT         = 180    # seconds to wait for OTP (3 min)
CHECKER_RETRY_LIMIT = 10     # max numbers to try for Swiggy/Myntra

# ── Checker URLs ──────────────────────────────────────────
SWIGGY_CHECKER_URL  = "https://checker.otpcart.xyz/swiggy"
MYNTRA_CHECKER_URL  = "https://www.myntra.com/forgot"

# ── Services that need registration check ─────────────────
SPECIAL_SERVICES = {"swiggy", "myntra"}
