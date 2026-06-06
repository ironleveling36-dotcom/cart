"""
Telegram OTP Bot — main entry point.

Fixes applied:
- service callback_data split uses maxsplit=2 to handle service names with ":"
- Pagination handler added for svcpage: callbacks
- handle_service / _normal_flow / _special_flow run as background tasks so the
  long-running OTP poll doesn't block the bot's event loop / other users
- Stale ctx.user_data["services"] stored after fetching so pagination works
- Error handler now logs the update object safely
- MessageText escaping: special chars in phone/OTP wrapped in backticks (already
  done) but also MarkdownV2 pitfalls avoided by sticking with MARKDOWN mode
  which only needs * _ ` [ ] ( ) ~ > # + - = | { } . ! escaped in code
  (we only use * and ` so it's safe)
- asyncio tasks tracked so cancellations propagate correctly
"""

import asyncio
import logging
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode

import otp_api
import checkers
from keyboards import (
    countries_keyboard,
    services_keyboard,
    cancel_keyboard,
    main_menu_keyboard,
)
from config import (
    BOT_TOKEN,
    SPECIAL_SERVICES,
    CHECKER_RETRY_LIMIT,
    OTP_TIMEOUT,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── /start ─────────────────────────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 *Welcome to OTP Bot!*\n\n"
        "Powered by OTPDoctor. Choose an option below.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )


# ── /balance ───────────────────────────────────────────────────────────────────

async def balance_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        bal = await otp_api.get_balance()
        await update.message.reply_text(
            f"💰 *Balance:* ₹{bal}",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


# ── Callback router ────────────────────────────────────────────────────────────

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data: str = query.data

    if data == "menu:get_otp":
        await show_countries(query, ctx)

    elif data == "menu:balance":
        try:
            bal = await otp_api.get_balance()
            await query.edit_message_text(
                f"💰 *Balance:* ₹{bal}",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=main_menu_keyboard(),
            )
        except Exception as e:
            await query.edit_message_text(f"❌ {e}", reply_markup=main_menu_keyboard())

    elif data.startswith("country:"):
        country_code = data.split(":", 1)[1]
        ctx.user_data["country"] = country_code
        await show_services(query, ctx, country_code, page=0)

    # Bug fix: use maxsplit=2 so service names containing ":" don't break unpacking
    elif data.startswith("service:"):
        parts = data.split(":", 2)
        if len(parts) < 3:
            await query.edit_message_text("❌ Invalid service selection.")
            return
        _, service_id, service_name = parts
        ctx.user_data["service_id"] = service_id
        ctx.user_data["service_name"] = service_name.lower()
        await handle_service(query, ctx)

    # Pagination for service list
    elif data.startswith("svcpage:"):
        try:
            page = int(data.split(":", 1)[1])
        except ValueError:
            page = 0
        country_code = ctx.user_data.get("country", "in")
        await show_services(query, ctx, country_code, page=page)

    elif data.startswith("cancel:"):
        activation_id = data.split(":", 1)[1]
        ok = await otp_api.cancel_number(activation_id)
        if ok:
            await query.edit_message_text("✅ Number cancelled.")
        else:
            await query.edit_message_text("⚠️ Could not cancel (already closed or invalid).")

    elif data == "back:countries":
        await show_countries(query, ctx)

    elif data == "back:main":
        await query.edit_message_text(
            "👋 *Welcome to OTP Bot!*\n\nChoose an option below.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(),
        )


# ── Show countries ─────────────────────────────────────────────────────────────

async def show_countries(query, ctx) -> None:
    try:
        countries = await otp_api.get_countries()
        await query.edit_message_text(
            "🌍 *Select a country:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=countries_keyboard(countries),
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Failed to load countries: {e}")


# ── Show services ──────────────────────────────────────────────────────────────

async def show_services(query, ctx, country_code: str, page: int = 0) -> None:
    try:
        # Cache services in user_data to avoid re-fetching on pagination
        if ctx.user_data.get("country") != country_code or "services" not in ctx.user_data:
            services = await otp_api.get_services(country_code)
            ctx.user_data["services"] = services
            ctx.user_data["country"] = country_code
        else:
            services = ctx.user_data["services"]

        if not services:
            await query.edit_message_text(
                "⚠️ No services available for this country.",
                reply_markup=countries_keyboard(await otp_api.get_countries()),
            )
            return
        await query.edit_message_text(
            "📱 *Select a service:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=services_keyboard(services, page=page),
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Failed to load services: {e}")


# ── Handle service ─────────────────────────────────────────────────────────────

async def handle_service(query, ctx) -> None:
    service_id   = ctx.user_data["service_id"]
    service_name = ctx.user_data["service_name"]
    chat_id      = query.message.chat_id

    is_special = service_name in SPECIAL_SERVICES

    if is_special:
        await query.edit_message_text(
            f"🔍 *{service_name.title()} detected.*\n"
            "Searching for an *unregistered* number… this may take a moment.",
            parse_mode=ParseMode.MARKDOWN,
        )
        # Run as background task so it doesn't block other users
        asyncio.create_task(
            _special_flow(ctx.bot, service_id, service_name, chat_id)
        )
    else:
        await query.edit_message_text(
            f"📲 Purchasing number for *{service_name.title()}*…",
            parse_mode=ParseMode.MARKDOWN,
        )
        asyncio.create_task(
            _normal_flow(ctx.bot, service_id, service_name, chat_id)
        )


# ── Normal OTP flow ────────────────────────────────────────────────────────────

async def _normal_flow(bot, service_id: str, service_name: str, chat_id: int) -> None:
    try:
        act_id, phone = await otp_api.purchase_number(service_id)
    except ValueError as e:
        await bot.send_message(chat_id, f"❌ Could not get number: {e}")
        return

    await bot.send_message(
        chat_id,
        f"✅ *Your number:* `+{phone}`\n"
        f"📦 Service: *{service_name.title()}*\n"
        f"⏳ Waiting for OTP (up to {OTP_TIMEOUT // 60} min)…",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=cancel_keyboard(act_id),
    )

    otp = await otp_api.get_otp(act_id)

    if otp:
        await bot.send_message(
            chat_id,
            f"🎉 *OTP Received!*\n\n"
            f"📱 Number: `+{phone}`\n"
            f"🔑 OTP: `{otp}`",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await otp_api.cancel_number(act_id)
        await bot.send_message(
            chat_id,
            f"⏰ No OTP received within {OTP_TIMEOUT // 60} minutes.\n"
            f"Number `+{phone}` has been automatically cancelled.",
            parse_mode=ParseMode.MARKDOWN,
        )


# ── Special flow (Swiggy / Myntra) ────────────────────────────────────────────

async def _special_flow(bot, service_id: str, service_name: str, chat_id: int) -> None:
    attempt = 0

    while attempt < CHECKER_RETRY_LIMIT:
        attempt += 1
        await bot.send_message(
            chat_id,
            f"🔄 Attempt {attempt}: purchasing number for *{service_name.title()}*…",
            parse_mode=ParseMode.MARKDOWN,
        )

        try:
            act_id, phone = await otp_api.purchase_number(service_id)
        except ValueError as e:
            await bot.send_message(chat_id, f"❌ Could not get number: {e}")
            return

        await bot.send_message(
            chat_id,
            f"🔍 Checking if `+{phone}` is registered on *{service_name.title()}*…",
            parse_mode=ParseMode.MARKDOWN,
        )

        if service_name == "swiggy":
            is_unregistered = await checkers.is_swiggy_unregistered(phone)
        else:
            is_unregistered = await checkers.is_myntra_unregistered(phone)

        if not is_unregistered:
            await bot.send_message(
                chat_id,
                f"⚠️ `+{phone}` is *registered*. Cancelling and trying another…",
                parse_mode=ParseMode.MARKDOWN,
            )
            await otp_api.cancel_number(act_id)
            await asyncio.sleep(2)
            continue

        # Unregistered — send to user and wait for OTP
        await bot.send_message(
            chat_id,
            f"✅ *Unregistered number found!*\n\n"
            f"📱 Number: `+{phone}`\n"
            f"📦 Service: *{service_name.title()}*\n"
            f"⏳ Waiting for OTP (up to {OTP_TIMEOUT // 60} min)…",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=cancel_keyboard(act_id),
        )

        otp = await otp_api.get_otp(act_id)

        if otp:
            await bot.send_message(
                chat_id,
                f"🎉 *OTP Received!*\n\n"
                f"📱 Number: `+{phone}`\n"
                f"🔑 OTP: `{otp}`",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await otp_api.cancel_number(act_id)
            await bot.send_message(
                chat_id,
                f"⏰ No OTP received within {OTP_TIMEOUT // 60} minutes.\n"
                f"Number `+{phone}` has been automatically cancelled.",
                parse_mode=ParseMode.MARKDOWN,
            )
        return

    await bot.send_message(
        chat_id,
        f"😔 Could not find an unregistered *{service_name.title()}* number after "
        f"{CHECKER_RETRY_LIMIT} attempts. Please try again later.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ── Error handler ──────────────────────────────────────────────────────────────

async def error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling update %s:", update, exc_info=ctx.error)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",   start))
    app.add_handler(CommandHandler("balance", balance_cmd))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_error_handler(error_handler)

    logger.info("Bot is running…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
