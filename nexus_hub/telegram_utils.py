"""Nexus Hub — Shared Telegram utilities (factorized to avoid duplication).

Used by both routes.py (webhook) and notify.py (polling) to avoid
duplicating _send_msg, _edit_msg, and callback handler logic.
"""

import json
import logging
from urllib.request import Request, urlopen

logger = logging.getLogger("nexus.hub.telegram")

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def telegram_send_msg(bot_token: str, chat_id: int | str, text: str,
                      reply_to: int | None = None, parse_mode: str = "Markdown") -> int:
    """Send a Telegram message. Returns message_id or 0 on failure."""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_to:
        payload["reply_to_message_id"] = reply_to

    data = json.dumps(payload).encode()
    try:
        resp = urlopen(Request(
            TELEGRAM_API.format(token=bot_token, method="sendMessage"),
            data=data,
            headers={"Content-Type": "application/json"},
        ), timeout=10)
        result = json.loads(resp.read())
        if result.get("ok"):
            return result["result"]["message_id"]
        logger.warning("[Telegram] sendMessage échec: %s", result.get("description", "?"))
    except Exception as e:
        logger.warning("[Telegram] sendMessage erreur: %s", e)
    return 0


def telegram_edit_msg(bot_token: str, chat_id: int | str, msg_id: int,
                      text: str, parse_mode: str = "Markdown"):
    """Edit an existing Telegram message. Silent on failure."""
    payload = json.dumps({
        "chat_id": chat_id,
        "message_id": msg_id,
        "text": text,
        "parse_mode": parse_mode,
    }).encode()
    try:
        urlopen(Request(
            TELEGRAM_API.format(token=bot_token, method="editMessageText"),
            data=payload,
            headers={"Content-Type": "application/json"},
        ), timeout=10)
    except Exception as e:
        logger.warning("[Telegram] editMessageText erreur: %s", e)


def telegram_ack_callback(bot_token: str, callback_id: str):
    """Acknowledge a callback query (dismisses the loading spinner)."""
    payload = json.dumps({
        "callback_query_id": callback_id,
        "text": "⏳",
        "show_alert": False,
    }).encode()
    try:
        urlopen(Request(
            TELEGRAM_API.format(token=bot_token, method="answerCallbackQuery"),
            data=payload,
            headers={"Content-Type": "application/json"},
        ), timeout=5)
        logger.info("[Telegram] ACK sent ✅")
    except Exception as e:
        logger.warning("[Telegram] ACK failed: %s", e)


def telegram_send_with_keyboard(bot_token: str, chat_id: int | str, text: str,
                                 keyboard: dict) -> bool:
    """Send a message with an inline keyboard."""
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": keyboard,
    }).encode("utf-8")
    try:
        resp = urlopen(Request(
            TELEGRAM_API.format(token=bot_token, method="sendMessage"),
            data=payload,
            headers={"Content-Type": "application/json"},
        ), timeout=10)
        data = json.loads(resp.read())
        if data.get("ok"):
            logger.info("[Telegram] Message envoyé au chat %s", chat_id)
            return True
        logger.warning("[Telegram] Réponse inattendue: %s", data.get("description", "?"))
    except Exception as e:
        logger.warning("[Telegram] Échec envoi: %s", e)
    return False


def telegram_escape_md(text: str) -> str:
    """Escape Telegram Markdown special characters."""
    import re
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!])', r'\\\1', text)


def handle_callback_action(bot_token: str, msg_chat: int | str, msg_id: int | None,
                            action: str, client_id: str, capture_id: str,
                            db_module, generate_ai_report_fn, generate_ai_fix_fn):
    """Handle a callback action (fix/report/detail) — shared by webhook and polling.

    Args:
        bot_token: Telegram bot token
        msg_chat: Chat ID to send responses to
        msg_id: Original message ID (for reply threading)
        action: 'fix', 'report', or 'detail'
        client_id: Client identifier
        capture_id: Capture ID string
        db_module: Database module with get_client_captures
        generate_ai_report_fn: Function to generate AI report
        generate_ai_fix_fn: Function to generate AI fix
    """
    captures = db_module.get_client_captures(client_id, 50)
    capture = next((c for c in captures if str(c["id"]) == capture_id), None)

    if not capture:
        telegram_send_msg(bot_token, msg_chat,
                          f"❌ Capture #{capture_id} non trouvée", reply_to=msg_id)
        return

    if action == "fix":
        mid = telegram_send_msg(bot_token, msg_chat,
                                "🛠️ **Génération du correctif...**\nDeepSeek analyse l'erreur et prépare un fix...",
                                reply_to=msg_id)
        logger.info("[Telegram] Génération du correctif pour #%s...", capture_id)
        fix = generate_ai_fix_fn(capture)
        if mid:
            telegram_edit_msg(bot_token, msg_chat, mid,
                              f"✅ *Correctif généré*\n\n{fix}")
        else:
            telegram_send_msg(bot_token, msg_chat, fix)
        # Final notification
        telegram_send_msg(bot_token, msg_chat,
            f"✅ *Correctif terminé !*\n"
            f"┌─────────────────────\n"
            f"│ Capture #{capture_id} — {capture.get('error_type', '?')}\n"
            f"│ DeepSeek a généré un correctif\n"
            f"│ ✅ Applique le code suggéré ci-dessus\n"
            f"└─────────────────────",
            reply_to=msg_id)

    elif action == "report":
        mid = telegram_send_msg(bot_token, msg_chat,
                                "🤖 **Analyse en cours...**\nDeepSeek diagnostique l'erreur...",
                                reply_to=msg_id)
        logger.info("[Telegram] Génération du rapport IA pour #%s...", capture_id)
        report = generate_ai_report_fn(capture)
        if mid:
            telegram_edit_msg(bot_token, msg_chat, mid, report)
        else:
            telegram_send_msg(bot_token, msg_chat, report)
        # Final notification
        telegram_send_msg(bot_token, msg_chat,
            f"📋 *Rapport terminé !*\n"
            f"┌─────────────────────\n"
            f"│ Capture #{capture_id} — {capture.get('error_type', '?')}\n"
            f"│ Consulte le diagnostic ci-dessus\n"
            f"└─────────────────────",
            reply_to=msg_id)

    elif action == "detail":
        answer = (
            f"🔍 *Détails #{capture_id}*\n"
            f"• Type : {capture['error_type']}\n"
            f"• Message : {capture['error_message'][:200] or '?'}\n"
            f"• URL : {capture['url'] or '/'}\n"
            f"• Status : {capture.get('nexus_status', 'pending')}\n"
            f"• {capture['created_at']}"
        )
        telegram_send_msg(bot_token, msg_chat, answer, reply_to=msg_id)

    else:
        telegram_send_msg(bot_token, msg_chat, "❌ Action inconnue", reply_to=msg_id)
