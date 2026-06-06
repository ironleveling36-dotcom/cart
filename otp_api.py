"""
OTPDoctor API wrapper — async (httpx).

Fixes applied:
- Removed unused `import json` inside get_countries / get_services
- get_countries() and get_services() now use the shared _get_json() helper
  instead of duplicating httpx + api_key logic
- Retry logic added for TRY_AGAIN response in purchase_number()
- Network exceptions during get_otp() polling are caught & retried instead
  of crashing the whole wait loop
"""

import asyncio
import httpx
from config import OTP_API_KEY, OTP_BASE_URL, OTP_POLL_INTERVAL, OTP_TIMEOUT

_MAX_RETRY = 3  # retries on TRY_AGAIN or transient network errors


# ── Shared helpers ─────────────────────────────────────────────────────────────

async def _get(params: dict) -> str:
    """GET → plain-text response."""
    p = dict(params)
    p["api_key"] = OTP_API_KEY
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(OTP_BASE_URL, params=p)
        r.raise_for_status()
        return r.text.strip()


async def _get_json(params: dict) -> dict:
    """GET → JSON response."""
    p = dict(params)
    p["api_key"] = OTP_API_KEY
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(OTP_BASE_URL, params=p)
        r.raise_for_status()
        return r.json()


# ── Balance ────────────────────────────────────────────────────────────────────

async def get_balance() -> str:
    """Returns balance as a string, or raises ValueError."""
    resp = await _get({"action": "getBalance"})
    if resp.startswith("ACCESS_BALANCE:"):
        return resp.split(":")[1]
    raise ValueError(resp)


# ── Countries ──────────────────────────────────────────────────────────────────

async def get_countries() -> dict:
    """Returns {code: name, ...}"""
    return await _get_json({"action": "getCountries"})


# ── Services ───────────────────────────────────────────────────────────────────

async def get_services(country: str) -> dict:
    """Returns {service_id: {service_name, service_price, server_name}, ...}"""
    return await _get_json({"action": "getServices", "country": country})


# ── Purchase Number ────────────────────────────────────────────────────────────

async def purchase_number(service_id: str, max_price: float = None) -> tuple[str, str]:
    """
    Returns (activation_id, phone_number).
    Raises ValueError on unrecoverable API errors.
    Retries up to _MAX_RETRY times on TRY_AGAIN.
    """
    params = {"action": "getNumber", "service": service_id}
    if max_price is not None:
        params["maxPrice"] = str(max_price)

    for attempt in range(_MAX_RETRY):
        resp = await _get(params)
        if resp.startswith("ACCESS_NUMBER:"):
            parts = resp.split(":")
            return parts[1], parts[2]
        if resp == "TRY_AGAIN":
            await asyncio.sleep(3)
            continue
        # Any other error (NO_BALANCE, BAD_SERVICE, etc.) → raise immediately
        raise ValueError(resp)

    raise ValueError("TRY_AGAIN — server temporarily unavailable, please retry later.")


# ── Cancel Number ──────────────────────────────────────────────────────────────

async def cancel_number(activation_id: str) -> bool:
    """Cancel an activation. Returns True if successfully cancelled."""
    try:
        resp = await _get({"action": "setStatus", "id": activation_id, "status": "8"})
        return "STATUS_CANCEL" in resp
    except Exception:
        return False


# ── Get OTP (polling loop) ────────────────────────────────────────────────────

async def get_otp(activation_id: str) -> str | None:
    """
    Poll until OTP arrives or OTP_TIMEOUT is reached.
    Returns the OTP string, or None on timeout / cancellation.
    Network errors during polling are caught and retried (not fatal).
    """
    elapsed = 0
    while elapsed < OTP_TIMEOUT:
        try:
            resp = await _get({"action": "getStatus", "id": activation_id})
        except Exception:
            # Transient network error — wait and retry instead of crashing
            await asyncio.sleep(OTP_POLL_INTERVAL)
            elapsed += OTP_POLL_INTERVAL
            continue

        if resp.startswith("STATUS_OK:"):
            return resp.split("STATUS_OK:", 1)[1].strip()
        if resp == "STATUS_CANCEL":
            return None  # externally cancelled

        await asyncio.sleep(OTP_POLL_INTERVAL)
        elapsed += OTP_POLL_INTERVAL

    return None  # timed out
