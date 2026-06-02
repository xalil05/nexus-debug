"""Nexus Hub — Notification engine (Telegram, WhatsApp, Slack)."""

import json
import logging
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import quote

from . import db

logger = logging.getLogger("nexus.hub.notify")

# ─── Telegram ───────────────────────────────────────────────────────────────

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def send_telegram(bot_token: str, chat_id: str, capture_id: int, client_id: str, error_type: str, error_message: str, url: str) -> bool:
    """Send a 3-button alert to a Telegram chat."""
    if not bot_token or not chat_id:
        return False

    # Truncate long messages
    msg = error_message[:200] if error_message else "?"

    text = (
        f"🚨 *Erreur détectée*\n"
        f"┌─────────────────────\n"
        f"│ `{error_type}` sur `{url or '/'}`\n"
        f"│ _{msg}_\n"
        f"└─────────────────────\n"
        f"🆔 Capture `#{capture_id}`"
    )

    # Inline keyboard with 3 buttons
    keyboard = {
        "inline_keyboard": [[
            {
                "text": "✅ Corriger",
                "callback_data": f"fix:{client_id}:{capture_id}",
            },
            {
                "text": "📄 Rapport",
                "callback_data": f"report:{client_id}:{capture_id}",
            },
            {
                "text": "🔍 Détails",
                "url": f"https://nexus-hub.com/dashboard/{client_id}/captures/{capture_id}",
            },
        ]]
    }

    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": keyboard,
    }).encode("utf-8")

    url_api = TELEGRAM_API.format(token=bot_token, method="sendMessage")
    req = Request(url_api, data=payload, headers={"Content-Type": "application/json"})

    try:
        resp = urlopen(req, timeout=10)
        success = 200 <= resp.status < 300
        data = json.loads(resp.read())
        if data.get("ok"):
            logger.info("[Telegram] Alerte envoyée au chat %s — capture #%d", chat_id, capture_id)
        else:
            logger.warning("[Telegram] Réponse inattendue: %s", data.get("description", "?"))
        return success
    except (URLError, HTTPError, TimeoutError) as e:
        logger.warning("[Telegram] Échec envoi: %s", e)
        return False


def set_telegram_webhook(bot_token: str, webhook_url: str) -> bool:
    """Set the webhook for Telegram bot callbacks (button clicks)."""
    url_api = TELEGRAM_API.format(token=bot_token, method="setWebhook")
    payload = json.dumps({"url": webhook_url}).encode("utf-8")
    req = Request(url_api, data=payload, headers={"Content-Type": "application/json"})
    try:
        resp = urlopen(req, timeout=10)
        data = json.loads(resp.read())
        return data.get("ok", False)
    except Exception:
        return False


# ─── WhatsApp (Twilio) ──────────────────────────────────────────────────────

def send_whatsapp(account_sid: str, auth_token: str, from_phone: str, to_phone: str, message: str) -> bool:
    """Send a WhatsApp message via Twilio API."""
    if not account_sid or not auth_token or not to_phone:
        return False

    from urllib.request import Request, urlopen
    import base64

    auth = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    payload = f"From={quote('whatsapp:' + from_phone)}&Body={quote(message[:1600])}&To={quote('whatsapp:' + to_phone)}"
    req = Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
        data=payload.encode(),
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        resp = urlopen(req, timeout=10)
        return 200 <= resp.status < 300
    except Exception as e:
        logger.warning("[WhatsApp] Échec envoi: %s", e)
        return False


# ─── Slack ──────────────────────────────────────────────────────────────────

def send_slack(webhook_url: str, error_type: str, error_message: str, url: str, capture_id: int, client_id: str) -> bool:
    """Send a Slack message with action buttons."""
    if not webhook_url:
        return False

    payload = json.dumps({
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"🚨 {error_type} détecté"}
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*URL:* {url or '/'}\n*Message:* {error_message[:300] or '?'}"}
            },
            {
                "type": "actions",
                "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": "✅ Corriger"}, "value": f"fix:{client_id}:{capture_id}"},
                    {"type": "button", "text": {"type": "plain_text", "text": "📄 Rapport"}, "value": f"report:{client_id}:{capture_id}"},
                    {"type": "button", "text": {"type": "plain_text", "text": "🔍 Détails"}, "url": f"https://nexus-hub.com/dashboard/{client_id}/captures/{capture_id}"},
                ]
            }
        ]
    }).encode("utf-8")

    req = Request(webhook_url, data=payload, headers={"Content-Type": "application/json"})
    try:
        resp = urlopen(req, timeout=10)
        return 200 <= resp.status < 300
    except Exception as e:
        logger.warning("[Slack] Échec envoi: %s", e)
        return False


# ─── Dispatch ────────────────────────────────────────────────────────────────

def notify_client(client_id: str, capture_id: int, error_type: str, error_message: str, url: str = "") -> dict:
    """Send notification to all configured channels for a client."""
    results = {"telegram": False, "whatsapp": False, "slack": False}

    notif = db.get_notifications(client_id)
    config = db._get_config()

    # Telegram
    bot_token = _get_config().get("telegram_bot_token", "")
    if notif.get("telegram_chat") and bot_token:
        results["telegram"] = send_telegram(bot_token, notif["telegram_chat"], capture_id, client_id, error_type, error_message, url)

    # WhatsApp
    cfg = _get_config()
    twilio_sid = cfg.get("twilio_account_sid", "")
    twilio_token = cfg.get("twilio_auth_token", "")
    from_phone = cfg.get("twilio_from_phone", "")
    if notif.get("whatsapp_phone") and twilio_sid and twilio_token:
        text = f"🚨 {error_type} sur {url}\n{error_message[:200]}\n✅ Corriger | 📄 Rapport | 🔍 Détails"
        results["whatsapp"] = send_whatsapp(twilio_sid, twilio_token, from_phone, notif["whatsapp_phone"], text)

    # Slack
    if notif.get("slack_webhook"):
        results["slack"] = send_slack(notif["slack_webhook"], error_type, error_message, url, capture_id, client_id)

    return results


# ─── Config helpers ─────────────────────────────────────────────────────────

def _get_config() -> dict:
    """Get hub settings from DB."""
    conn = db.get_db()
    try:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}
    finally:
        conn.close()


def set_config(key: str, value: str):
    """Set a hub setting."""
    conn = db.get_db()
    try:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
    finally:
        conn.close()
