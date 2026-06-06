"""
Inline keyboard builders for the bot.

Fixes applied:
- callback_data for service buttons is now capped at 64 bytes (Telegram limit).
  service_name is truncated to 40 chars to stay safe.
- Long service lists are paginated (max 48 buttons per keyboard — Telegram
  hard-limits inline keyboards to 100 buttons, but 48 keeps UX clean).
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

_MAX_SERVICES_PER_PAGE = 48  # safe cap well under Telegram's 100-button limit
_CB_DATA_LIMIT = 64          # Telegram callback_data byte limit


def _safe_cb(data: str) -> str:
    """Truncate callback_data to Telegram's 64-byte limit."""
    return data.encode()[:_CB_DATA_LIMIT].decode(errors="ignore")


def countries_keyboard(countries: dict) -> InlineKeyboardMarkup:
    """countries: {code: name, ...}"""
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for code, name in countries.items():
        row.append(InlineKeyboardButton(
            f"🌍 {name}",
            callback_data=_safe_cb(f"country:{code}"),
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


def services_keyboard(services: dict, page: int = 0) -> InlineKeyboardMarkup:
    """
    services: {service_id: {service_name, service_price, server_name}, ...}
    Paginated if more than _MAX_SERVICES_PER_PAGE services.
    """
    items = list(services.items())
    total_pages = max(1, (len(items) + _MAX_SERVICES_PER_PAGE - 1) // _MAX_SERVICES_PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    start = page * _MAX_SERVICES_PER_PAGE
    page_items = items[start: start + _MAX_SERVICES_PER_PAGE]

    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []

    for sid, info in page_items:
        name = info["service_name"][:40]   # truncate to keep cb_data ≤ 64 bytes
        label = f"{info['service_name']} ₹{info['service_price']}"
        cb = _safe_cb(f"service:{sid}:{name}")
        row.append(InlineKeyboardButton(label, callback_data=cb))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Pagination row
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"svcpage:{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"svcpage:{page+1}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back:countries")])
    return InlineKeyboardMarkup(buttons)


def cancel_keyboard(activation_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel Number", callback_data=_safe_cb(f"cancel:{activation_id}"))]
    ])


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Get OTP Number", callback_data="menu:get_otp")],
        [InlineKeyboardButton("💰 Check Balance",  callback_data="menu:balance")],
    ])
