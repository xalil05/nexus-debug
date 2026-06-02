"""Nexus Hub — Notification engine (Telegram, WhatsApp, Slack)."""

import json
import logging
import os
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import quote

from . import db

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

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def send_telegram(bot_token: str, chat_id: str, capture_id: int, client_id: str, error_type: str, error_message: str, url: str) -> bool:
    """Send a 3-button alert to a Telegram chat."""
    if not bot_token or not chat_id:
        return False

    # Escape special Markdown characters to prevent parse errors
    import re as _re
    def _escape_md(text: str) -> str:
        """Escape Telegram Markdown special chars."""
        return _re.sub(r'([_*\[\]()~`>#+\-=|{}.!])', r'\\\1', text)

    msg = _escape_md(error_message[:200]) if error_message else "?"
    err_type = _escape_md(error_type)
    path = _escape_md(url or "/")

    text = (
        f"🚨 *Erreur détectée*\n"
        f"┌─────────────────────\n"
        f"│ `{err_type}` sur `{path}`\n"
        f"│ {msg}\n"
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
                "callback_data": f"detail:{client_id}:{capture_id}",
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
    from urllib.request import Request as Req, urlopen as uo
    import json as j

    url = TELEGRAM_API.format(token=bot_token, method="getUpdates")
    payload = j.dumps({"offset": offset, "timeout": 5}).encode()

    try:
        req = Req(url, data=payload, headers={"Content-Type": "application/json"})
        resp = uo(req, timeout=10)
        data = j.loads(resp.read())
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
    """Handle a Telegram inline button click."""
    from urllib.request import Request as Req, urlopen as uo
    import json as j

    data = callback.get("data", "")
    chat_id = str(callback.get("from", {}).get("id", ""))
    msg_chat = callback.get("message", {}).get("chat", {}).get("id", chat_id)
    parts = data.split(":")
    action = parts[0] if len(parts) > 0 else ""
    client_id = parts[1] if len(parts) > 1 else ""
    capture_id = parts[2] if len(parts) > 2 else ""

    logger.info("[Telegram] Callback: %s — client=%s capture=%s chat=%s", action, client_id, capture_id, chat_id)

    # Step 1: ACKNOWLEDGE IMMEDIATELY — dismiss the button loading state
    ack_payload = j.dumps({
        "callback_query_id": callback.get("id", ""),
        "text": "⏳",
        "show_alert": False,
    }).encode()
    try:
        uo(Req(TELEGRAM_API.format(token=bot_token, method="answerCallbackQuery"),
               data=ack_payload, headers={"Content-Type": "application/json"}), timeout=5)
        logger.info("[Telegram] ACK sent ✅")
    except Exception as e:
        logger.warning("[Telegram] ACK failed: %s", e)

    # Step 2: Process action — send progress, then result
    def _send_msg(text: str) -> int:
        """Send a message and return its message_id."""
        payload = j.dumps({
            "chat_id": msg_chat, "text": text, "parse_mode": "Markdown",
            "reply_to_message_id": callback.get("message", {}).get("message_id"),
        }).encode()
        try:
            resp = uo(Req(TELEGRAM_API.format(token=bot_token, method="sendMessage"),
                          data=payload, headers={"Content-Type": "application/json"}), timeout=10)
            result = j.loads(resp.read())
            if result.get("ok"):
                return result["result"]["message_id"]
        except Exception:
            pass
        return 0

    def _edit_msg(msg_id: int, text: str):
        """Edit an existing message."""
        payload = j.dumps({
            "chat_id": msg_chat, "message_id": msg_id,
            "text": text, "parse_mode": "Markdown",
        }).encode()
        try:
            uo(Req(TELEGRAM_API.format(token=bot_token, method="editMessageText"),
                   data=payload, headers={"Content-Type": "application/json"}), timeout=10)
        except Exception:
            pass

    if action == "fix":
        captures = db.get_client_captures(client_id, 50)
        capture = next((c for c in captures if str(c["id"]) == capture_id), None)
        if capture:
            mid = _send_msg("🛠️ **Génération du correctif...**\nDeepSeek analyse l'erreur et prépare un fix...")
            logger.info("[Telegram] Génération du correctif pour #%s...", capture_id)
            fix = generate_ai_fix(capture)
            if mid:
                _edit_msg(mid, f"✅ *Correctif généré*\n\n{fix}")
            else:
                _send_msg(fix)
            # Final notification
            _send_msg(
                f"✅ *Correctif terminé !*\n"
                f"┌─────────────────────\n"
                f"│ Capture #{capture_id} — {capture.get('error_type', '?')}\n"
                f"│ DeepSeek a généré un correctif\n"
                f"│ ✅ Applique le code suggéré ci-dessus\n"
                f"└─────────────────────"
            )
        else:
            _send_msg(f"❌ Capture #{capture_id} non trouvée")
    elif action == "report":
        captures = db.get_client_captures(client_id, 50)
        capture = next((c for c in captures if str(c["id"]) == capture_id), None)
        if capture:
            mid = _send_msg("🤖 **Analyse en cours...**\nDeepSeek diagnostique l'erreur...")
            logger.info("[Telegram] Génération du rapport IA pour #%s...", capture_id)
            report = generate_ai_report(capture)
            if mid:
                _edit_msg(mid, report)
            else:
                _send_msg(report)
            # Final notification
            _send_msg(
                f"📋 *Rapport terminé !*\n"
                f"┌─────────────────────\n"
                f"│ Capture #{capture_id} — {capture.get('error_type', '?')}\n"
                f"│ Consulte le diagnostic ci-dessus\n"
                f"└─────────────────────"
            )
        else:
            _send_msg(f"❌ Capture #{capture_id} non trouvée")
    elif action == "detail":
        captures = db.get_client_captures(client_id, 50)
        capture = next((c for c in captures if str(c["id"]) == capture_id), None)
        if capture:
            answer = (
                f"🔍 *Détails #{capture_id}*\n"
                f"• Type : {capture['error_type']}\n"
                f"• Message : {capture['error_message'][:200] or '?'}\n"
                f"• URL : {capture['url'] or '/'}\n"
                f"• Status : {capture.get('nexus_status', 'pending')}\n"
                f"• {capture['created_at']}"
            )
            _send_msg(answer)
        else:
            _send_msg(f"❌ Capture #{capture_id} non trouvée")
    else:
        _send_msg("❌ Action inconnue")


def _handle_start_command(bot_token: str, message: dict):
    """Handle /start <client_id> command — link Telegram chat to account."""
    from urllib.request import Request as Req, urlopen as uo
    import json as j

    text = message.get("text", "")
    chat_id = str(message.get("from", {}).get("id", ""))
    parts = text.split()

    if len(parts) < 2:
        # No client_id — send instructions
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

    payload = j.dumps({
        "chat_id": chat_id, "text": reply, "parse_mode": "Markdown"
    }).encode()
    try:
        uo(Req(
            TELEGRAM_API.format(token=bot_token, method="sendMessage"),
            data=payload, headers={"Content-Type": "application/json"}
        ), timeout=5)
    except Exception:
        pass


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
