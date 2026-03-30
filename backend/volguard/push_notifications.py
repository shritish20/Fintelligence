"""
Fintelligence — Push Notifications (8:47 AM Daily Brief)
=========================================================
Sends the daily TONE (CLEAR / CAUTIOUS / RISK_OFF) + one-line
macro summary to all subscribed users via Telegram.

Phase 5 (mobile): Replace with FCM/APNs when React Native app ships.
For now, Telegram is the transport — traders already use it.

Scheduler: called from volguard lifespan via APScheduler-style background task.
No external scheduler needed — pure asyncio.
"""

import os
import asyncio
import logging
from datetime import datetime
import pytz
import aiohttp

log = logging.getLogger("fintelligence.push")

IST = pytz.timezone("Asia/Kolkata")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

TONE_EMOJI = {
    "CLEAR":    "🟢",
    "CAUTIOUS": "🟡",
    "RISK_OFF": "🔴",
    "MIXED":    "🟠",
    "UNKNOWN":  "⚪",
}


async def send_telegram(text: str) -> bool:
    """Send a message to the configured Telegram chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.debug("Telegram not configured — skipping push")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={
                "chat_id":    TELEGRAM_CHAT_ID,
                "text":       text,
                "parse_mode": "HTML",
            }, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                ok = resp.status == 200
                if not ok:
                    body = await resp.text()
                    log.warning(f"Telegram API error {resp.status}: {body}")
                return ok
    except Exception as e:
        log.warning(f"Telegram send failed: {e}")
        return False


async def send_morning_brief_notification(volguard_system) -> None:
    """
    Pull today's brief from the intelligence layer and push it.
    Called at 08:47 IST by the background scheduler in volguard lifespan.
    """
    try:
        if not volguard_system:
            return

        # Get brief from in-memory cache
        brief = None
        if hasattr(volguard_system, "json_cache"):
            cached = volguard_system.json_cache.get()
            if cached:
                brief = cached.get("morning_brief") or cached.get("brief")

        # Get global tone
        tone = "UNKNOWN"
        vix  = None
        summary_line = ""

        if hasattr(volguard_system, "fetcher"):
            try:
                snapshot = await asyncio.get_event_loop().run_in_executor(
                    None, volguard_system.fetcher.get_macro_snapshot
                )
                if snapshot:
                    tone = snapshot.get("global_tone", "UNKNOWN")
                    vix  = snapshot.get("india_vix")
            except Exception:
                pass

        if brief and isinstance(brief, dict):
            summary_line = brief.get("one_liner") or brief.get("summary", "")[:120]

        emoji = TONE_EMOJI.get(tone, "⚪")
        now_ist = datetime.now(IST).strftime("%d %b %Y")

        msg_lines = [
            f"<b>🕗 Fintelligence Morning Brief — {now_ist}</b>",
            "",
            f"{emoji} <b>GLOBAL TONE: {tone}</b>",
        ]
        if vix:
            msg_lines.append(f"📊 India VIX: <b>{vix:.1f}</b>")
        if summary_line:
            msg_lines.append(f"\n{summary_line}")
        msg_lines.append("\n<i>Open Fintelligence for the full brief →</i>")

        message = "\n".join(msg_lines)
        sent = await send_telegram(message)
        if sent:
            log.info(f"Morning brief push sent — TONE={tone}")
        else:
            log.debug("Morning brief push skipped (Telegram not configured)")

    except Exception as e:
        log.exception(f"Morning brief push failed: {e}")


async def run_morning_brief_scheduler(get_system_fn) -> None:
    """
    Long-running coroutine — fires send_morning_brief_notification at 08:47 IST daily.
    Launch as an asyncio task from the volguard lifespan startup.

    Usage in lifespan:
        asyncio.create_task(run_morning_brief_scheduler(lambda: volguard_system))
    """
    log.info("Morning brief scheduler started — fires at 08:47 IST daily")
    while True:
        try:
            now_ist   = datetime.now(IST)
            target    = now_ist.replace(hour=8, minute=47, second=0, microsecond=0)
            if now_ist >= target:
                # Already past 08:47 today — schedule for tomorrow
                from datetime import timedelta
                target = target + timedelta(days=1)

            sleep_seconds = (target - now_ist).total_seconds()
            log.debug(f"Next morning brief push in {sleep_seconds/3600:.1f}h")
            await asyncio.sleep(sleep_seconds)

            system = get_system_fn()
            await send_morning_brief_notification(system)

            # Wait 60s buffer before re-calculating next target
            await asyncio.sleep(60)

        except asyncio.CancelledError:
            log.info("Morning brief scheduler cancelled")
            break
        except Exception as e:
            log.exception(f"Scheduler loop error: {e}")
            await asyncio.sleep(300)  # retry in 5 min on error
