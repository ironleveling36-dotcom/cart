"""
Swiggy & Myntra registration checkers using camoufox-cli.

Returns True  → number is UNREGISTERED  (safe to use)
Returns False → number is REGISTERED    (must cancel & retry)

Fixes applied:
- _find_ref regex now correctly matches [ref=e1] (no @ in snapshot output)
- @ prefix added when refs are passed to fill/click commands
- --session flag used on ALL commands to target correct browser session
- --persistent and --locale only on `open` command
- Re-snapshot after fill before clicking button (get fresh refs)
- camoufox-cli wait used instead of asyncio.sleep for browser sync
- close() called in finally block to prevent session leaks
- Separate sessions for Swiggy vs Myntra to avoid concurrency collisions
"""

import asyncio
import re

SESSION_SWIGGY = "swiggy-checker"
SESSION_MYNTRA = "myntra-checker"


# ── Core helper ────────────────────────────────────────────────────────────────

async def _camoufox(session: str, *args) -> str:
    """Run: camoufox-cli --session <session> <args...>"""
    cmd = ["camoufox-cli", "--session", session] + list(args)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    return stdout.decode(errors="ignore")


async def _open(session: str, url: str, profile: str) -> str:
    """Open URL with persistent profile + locale (only on open command)."""
    cmd = [
        "camoufox-cli",
        "--session", session,
        "--persistent", profile,
        "--locale", "en-US",
        "open", url,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    return stdout.decode(errors="ignore")


# ── Swiggy checker ─────────────────────────────────────────────────────────────

async def is_swiggy_unregistered(phone: str) -> bool:
    """
    Opens https://checker.otpcart.xyz/swiggy, enters the number, reads result.
    Returns True if UNREGISTERED.
    """
    s = SESSION_SWIGGY
    try:
        await _open(s, "https://checker.otpcart.xyz/swiggy", ".camoufox-swiggy")
        await _camoufox(s, "wait", "3000")

        # Snapshot to find input
        snap = await _camoufox(s, "snapshot", "-i")
        input_ref = _find_ref(snap, ["phone", "mobile", "number", "textbox", "input"])
        if not input_ref:
            return False  # can't find field → treat as registered (safe default)

        # Fill number (ref already has @ prefix from _find_ref)
        await _camoufox(s, "fill", input_ref, phone)
        await _camoufox(s, "wait", "500")

        # Re-snapshot after fill to get fresh refs (DOM may have changed)
        snap2 = await _camoufox(s, "snapshot", "-i")
        btn_ref = _find_ref(snap2, ["check", "submit", "verify", "search", "button"])
        if btn_ref:
            await _camoufox(s, "click", btn_ref)

        # Wait for result to load
        await _camoufox(s, "wait", "5000")

        result = await _camoufox(s, "text", "body")
        result_lower = result.lower()

        if "unregistered" in result_lower:
            return True
        if "registered" in result_lower:
            return False
        return False  # unknown → treat as registered
    except Exception:
        return False
    finally:
        try:
            await _camoufox(s, "close")
        except Exception:
            pass


# ── Myntra checker ─────────────────────────────────────────────────────────────

async def is_myntra_unregistered(phone: str) -> bool:
    """
    Opens https://www.myntra.com/forgot, enters number, clicks Send Link.
    Returns True ONLY if 'Account does not exist'.
    """
    s = SESSION_MYNTRA
    try:
        await _open(s, "https://www.myntra.com/forgot", ".camoufox-myntra")
        await _camoufox(s, "wait", "4000")

        snap = await _camoufox(s, "snapshot", "-i")
        input_ref = _find_ref(snap, ["mobile", "phone", "email", "textbox", "input"])
        if not input_ref:
            return False

        await _camoufox(s, "fill", input_ref, phone)
        await _camoufox(s, "wait", "500")

        # Re-snapshot after fill for fresh refs
        snap2 = await _camoufox(s, "snapshot", "-i")
        btn_ref = _find_ref(snap2, ["send", "link", "submit", "reset", "button"])
        if btn_ref:
            await _camoufox(s, "click", btn_ref)

        await _camoufox(s, "wait", "5000")

        result = await _camoufox(s, "text", "body")
        result_lower = result.lower()

        # Only "account does not exist" → safe to use
        if "account does not exist" in result_lower or "does not exist" in result_lower:
            return True
        return False  # anything else → registered or error
    except Exception:
        return False
    finally:
        try:
            await _camoufox(s, "close")
        except Exception:
            pass


# ── Utility ────────────────────────────────────────────────────────────────────

def _find_ref(snapshot_text: str, keywords: list[str]) -> str | None:
    """
    Parse camoufox-cli snapshot -i output to find a ref matching any keyword.

    Snapshot format:  - textbox "Email" [ref=e1]
    The ref in snapshot is bare (e.g. e1), but must be prefixed with @ when
    passed to fill/click commands (e.g. camoufox-cli fill @e1 "text").

    Bug fixed: original regex r"\\[ref=(@\\w+)\\]" looked for @ inside the
    brackets which never exists → always returned None.
    """
    lines = snapshot_text.splitlines()
    for line in lines:
        lower = line.lower()
        if any(kw in lower for kw in keywords):
            # Correct pattern: [ref=e1] — no @ inside brackets
            match = re.search(r"\[ref=(e\w+)\]", line)
            if match:
                return f"@{match.group(1)}"  # prepend @ for CLI usage
    return None
