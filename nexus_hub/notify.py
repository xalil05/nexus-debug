"""Nexus Hub — Notification engine (Telegram, WhatsApp, Slack)."""

import json
import logging
import os
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import quote

from . import db
from . import telegram_utils as tg

logger = logging.getLogger("nexus.hub.notify")


# ─── AI Report (DeepSeek) ────────────────────────────────────────────────────

def generate_ai_report(capture: dict) -> str:
    """Generate an AI diagnostic report using DeepSeek."""
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        return "❌ DeepSeek non configuré (DEEPSEEK_API_KEY manquante)"

    prompt = (
        "Analyse cette erreur et fournis un diagnostic concis :\n\n"
        f"Type: {capture.get('error_type', '?')}\n"
        f"Message: {capture.get('error_message', '?')[:500]}\n"
        f"URL: {capture.get('url', '/')}\n\n"
        "Réponds en français (max 300 caractères) :\n"
        "1. Cause racine probable (1 phrase)\n"
        "2. Solution recommandée (2-3 étapes courtes)\n"
        "3. Code de correction si applicable"
    )

    payload = json.dumps({
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "Tu es un expert en débogage. Réponds en français, concis et technique, max 300 caractères."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 500,
        "temperature": 0.3,
    }).encode()

    try:
        req = Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        resp = urlopen(req, timeout=30)
        data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"]
        return f"🤖 Diagnostic IA :\n{content[:350]}"
    except Exception as e:
        return f"❌ Erreur IA : {str(e)[:150]}"


def generate_ai_fix(capture: dict) -> str:
    """Generate an AI code fix using DeepSeek."""
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        return "❌ DeepSeek non configuré (DEEPSEEK_API_KEY manquante)"

    prompt = (
        "Génère un correctif pour cette erreur :\n\n"
        f"Type: {capture.get('error_type', '?')}\n"
        f"Message: {capture.get('error_message', '?')[:500]}\n"
        f"URL: {capture.get('url', '/')}\n\n"
        "Réponds en français avec ce format :\n"
        "1. Cause racine (1 phrase)\n"
        "2. Solution (2-3 étapes)\n"
        "3. Code de correction (bloc ```code```)"
    )

    payload = json.dumps({
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "Tu es un expert en débogage. Fournis des correctifs précis et directement applicables. Réponds en français."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 800,
        "temperature": 0.2,
    }).encode()

    try:
        req = Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        resp = urlopen(req, timeout=30)
        data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"]
        return f"🛠️ *Correctif proposé :*\n\n{content[:800]}"
    except Exception as e:
        return f"❌ Erreur IA : {str(e)[:150]}"


# ─── Telegram ───────────────────────────────────────────────────────────────

def send_telegram(bot_token: str, chat_id: str, capture_id: int, client_id: str,
                  error_type: str, error_message: str, url: str) -> bool:
    """Send a 3-button alert to a Telegram chat."""
    if not bot_token or not chat_id:
        return False

    msg = tg.telegram_escape_md(error_message[:200]) if error_message else "?"
    err_type = tg.telegram_escape_md(error_type)
    path = tg.telegram_escape_md(url or "/")

    text = (
        f"🚨 *Erreur détectée*\n"
        f"┌─────────────────────\n"
        f"│ `{err_type}` sur `{path}`\n"
        f"│ {msg}\n"
        f"└─────────────────────\n"
        f"🆔 Capture `#{capture_id}`"
    )

    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Corriger", "callback_data": f"fix:{client_id}:{capture_id}"},
            {"text": "📄 Rapport", "callback_data": f"report:{client_id}:{capture_id}"},
            {"text": "🔍 Détails", "callback_data": f"detail:{client_id}:{capture_id}"},
        ]]
    }

    return tg.telegram_send_with_keyboard(bot_token, chat_id, text, keyboard)


def set_telegram_webhook(bot_token: str, webhook_url: str) -> bool:
    """Set the webhook for Telegram bot callbacks (button clicks)."""
    url_api = tg.TELEGRAM_API.format(token=bot_token, method="setWebhook")
    payload = json.dumps({"url": webhook_url}).encode("utf-8")
    req = Request(url_api, data=payload, headers={"Content-Type": "application/json"})
    try:
        resp = urlopen(req, timeout=10)
        data = json.loads(resp.read())
        logger.info("[Telegram] Webhook set: %s", data)
        return data.get("ok", False)
    except Exception as e:
        logger.warning("[Telegram] Webhook failed (expected on HTTP/Tailscale): %s", e)
        return False


def process_telegram_updates(bot_token: str, offset: int = 0) -> tuple[int, int]:
    """Poll Telegram for incoming updates (button clicks, /start commands).

    Returns (new_offset, count_processed).
    Used when webhook is not available (HTTP-only servers).
    """
    url = tg.TELEGRAM_API.format(token=bot_token, method="getUpdates")
    payload = json.dumps({"offset": offset, "timeout": 5}).encode()

    try:
        req = Request(url, data=payload, headers={"Content-Type": "application/json"})
        resp = urlopen(req, timeout=10)
        data = json.loads(resp.read())
    except Exception as e:
        logger.warning("[Telegram] Poll error: %s", e)
        return offset, 0

    if not data.get("ok"):
        return offset, 0

    updates = data.get("result", [])
    count = 0

    for update in updates:
        update_id = update.get("update_id", 0)
        offset = max(offset, update_id + 1)

        # Callback query (button clicks)
        cb = update.get("callback_query", {})
        if cb:
            _handle_telegram_callback(bot_token, cb)
            count += 1
            continue

        # /start command
        msg = update.get("message", {})
        text = msg.get("text", "")
        if text.startswith("/start"):
            _handle_start_command(bot_token, msg)
            count += 1

    return offset, count


def _handle_telegram_callback(bot_token: str, callback: dict):
    """Handle a Telegram inline button click — delegates to shared handler."""
    data = callback.get("data", "")
    chat_id = str(callback.get("from", {}).get("id", ""))
    msg_chat = callback.get("message", {}).get("chat", {}).get("id", chat_id)
    msg_id = callback.get("message", {}).get("message_id")
    parts = data.split(":")
    action = parts[0] if len(parts) > 0 else ""
    client_id = parts[1] if len(parts) > 1 else ""
    capture_id = parts[2] if len(parts) > 2 else ""

    logger.info("[Telegram] Callback: %s — client=%s capture=%s chat=%s", action, client_id, capture_id, chat_id)

    # Acknowledge
    tg.telegram_ack_callback(bot_token, callback.get("id", ""))

    # Handle action via shared handler
    tg.handle_callback_action(
        bot_token, msg_chat, msg_id,
        action, client_id, capture_id,
        db, generate_ai_report, generate_ai_fix,
    )


def _handle_start_command(bot_token: str, message: dict):
    """Handle /start <client_id> command — link Telegram chat to account."""
    text = message.get("text", "")
    chat_id = str(message.get("from", {}).get("id", ""))
    parts = text.split()

    if len(parts) < 2:
        reply = (
            "👋 Bienvenue sur Nexus Watch !\n\n"
            "Pour lier votre compte :\n"
            "1. Connectez-vous sur votre dashboard\n"
            "2. Copiez votre Client ID\n"
            "3. Tapez /start VOTRE_CLIENT_ID ici\n\n"
            "Exemple : /start abc12345"
        )
    else:
        client_id = parts[1]
        db.update_notifications(client_id, telegram=chat_id)
        reply = f"✅ Compte lié ! Vous recevrez les alertes pour le client **{client_id}** ici."

    tg.telegram_send_msg(bot_token, chat_id, reply)


# ─── WhatsApp (Twilio) ──────────────────────────────────────────────────────

def send_whatsapp(account_sid: str, auth_token: str, from_phone: str, to_phone: str, message: str) -> bool:
    """Send a WhatsApp message via Twilio API."""
    if not account_sid or not auth_token or not to_phone:
        return False

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
                    {"type": "button", "text": {"type": "plain_text", "text": "🔍 Détails"}, "value": f"detail:{client_id}:{capture_id}"},
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
