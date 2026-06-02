"""Nexus Hub — API routes for multi-tenant error capture."""

import json
import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from . import db
from . import notify

logger = logging.getLogger("nexus.hub")
router = APIRouter(prefix="/hub", tags=["hub"])


# ─── Schemas ─────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    password: str
    project: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class NotificationUpdate(BaseModel):
    telegram_chat: str = ""
    whatsapp_phone: str = ""
    slack_webhook: str = ""


class CaptureData(BaseModel):
    api_key: str
    project: str = ""
    version: str = ""
    environment: str = ""
    error: dict = {}
    request: dict = {}
    headers: dict = {}


# ─── Routes — Client management ─────────────────────────────────────────────

@router.post("/register")
def register(req: RegisterRequest):
    """Register a new client. Returns client_id + api_key."""
    if len(req.password) < 6:
        raise HTTPException(400, "Mot de passe trop court (min 6 caractères)")
    result = db.register_client(req.email, req.password, req.project)
    if not result["success"]:
        raise HTTPException(409, result.get("error", "Erreur inscription"))
    return result


@router.post("/login")
def login(req: LoginRequest):
    """Authenticate a client. Returns profile data."""
    client = db.authenticate(req.email, req.password)
    if not client:
        raise HTTPException(401, "Email ou mot de passe invalide")
    # Don't include api_key in login response for security
    return {
        "client_id": client["client_id"],
        "email": client["email"],
        "project": client["project"],
        "plan": client["plan"],
        "created_at": client["created_at"],
    }


# ─── Routes — Notifications ─────────────────────────────────────────────────

@router.put("/{client_id}/notifications")
def set_notifications(client_id: str, req: NotificationUpdate):
    """Configure notification channels for a client."""
    return db.update_notifications(client_id, req.telegram_chat, req.whatsapp_phone, req.slack_webhook)


@router.get("/{client_id}/notifications")
def get_notifications(client_id: str):
    """Get notification configuration."""
    return db.get_notifications(client_id)


# ─── Routes — Capture ───────────────────────────────────────────────────────

@router.post("/capture")
def capture(data: CaptureData):
    """Receive an error from watch-py. Public endpoint — no auth header needed, api_key in body."""
    # Find client by api_key
    client = db.get_client_by_api_key(data.api_key)
    if not client:
        raise HTTPException(401, "Clé API invalide")

    # Save the capture
    capture_id = db.save_capture(client["client_id"], data.model_dump())
    logger.info("[%s] Capture #%d: %s — %s", client["client_id"], capture_id, data.error.get("type", "?"), data.error.get("message", "")[:60])

    # Send notification to client's configured channels
    notify.notify_client(
        client["client_id"],
        capture_id,
        data.error.get("type", "Erreur"),
        data.error.get("message", ""),
        data.request.get("url", ""),
    )

    return {
        "capture_id": capture_id,
        "status": "received",
        "message": "Erreur reçue. Diagnostic en cours...",
    }


# ─── Routes — Dashboard ─────────────────────────────────────────────────────

@router.get("/{client_id}/stats")
def client_stats(client_id: str):
    """Get aggregate stats for client dashboard."""
    return db.get_client_stats(client_id)


@router.get("/{client_id}/captures")
def client_captures(client_id: str, limit: int = 50):
    """Get capture history for client dashboard."""
    captures = db.get_client_captures(client_id, limit)
    return {"captures": captures, "count": len(captures)}


@router.get("/{client_id}/profile")
def client_profile(client_id: str):
    """Get full client profile (for dashboard)."""
    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT client_id, email, project, plan, created_at FROM clients WHERE client_id = ?",
            (client_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Client non trouvé")
        return dict(row)
    finally:
        conn.close()


# ─── Routes — Admin config ──────────────────────────────────────────────────

class ConfigUpdate(BaseModel):
    key: str
    value: str


@router.post("/admin/config")
def set_config(req: ConfigUpdate):
    """Set a hub-level config (telegram_bot_token, etc)."""
    notify.set_config(req.key, req.value)
    return {"success": True, "key": req.key}


@router.get("/admin/config")
def get_config():
    """Get all hub config (keys only, values masked)."""
    cfg = notify._get_config()
    # Mask sensitive values
    safe = {}
    for k, v in cfg.items():
        if "token" in k.lower() or "secret" in k.lower() or "key" in k.lower():
            safe[k] = v[:8] + "..." if len(v) > 8 else "***"
        else:
            safe[k] = v
    return safe


@router.post("/admin/telegram/set-webhook")
def set_telegram_webhook():
    """Register the hub's Telegram webhook URL with the bot."""
    base_url = notify._get_config().get("hub_base_url", "")
    if not base_url:
        raise HTTPException(400, "hub_base_url non configurée. Faites POST /hub/admin/config avec key=hub_base_url")
    bot_token = notify._get_config().get("telegram_bot_token", "")
    if not bot_token:
        raise HTTPException(400, "telegram_bot_token non configuré")
    webhook_url = f"{base_url.rstrip('/')}/hub/telegram/webhook"
    success = notify.set_telegram_webhook(bot_token, webhook_url)
    return {"success": success, "webhook_url": webhook_url}


# ─── Routes — Telegram Webhook ──────────────────────────────────────────────

@router.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """Receive Telegram bot callback (button clicks from clients)."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    # Callback query (inline button click)
    callback = body.get("callback_query", {})
    if callback:
        data = callback.get("data", "")
        chat_id = str(callback.get("from", {}).get("id", ""))
        msg_id = callback.get("message", {}).get("message_id")

        parts = data.split(":")
        action = parts[0] if len(parts) > 0 else ""
        client_id = parts[1] if len(parts) > 1 else ""
        capture_id = parts[2] if len(parts) > 2 else ""

        logger.info("[Telegram] Callback: %s — client=%s capture=%s", action, client_id, capture_id)

        if action == "fix":
            # TODO: trigger auto-fix
            answer = "✅ Correction en cours... Le fix sera appliqué sous peu."
        elif action == "report":
            # Fetch the capture details
            captures = db.get_client_captures(client_id, 50)
            capture = next((c for c in captures if str(c["id"]) == capture_id), None)
            if capture:
                answer = f"📄 *Rapport #{capture_id}*\nType: {capture['error_type']}\nMessage: {capture['error_message'][:200]}\nURL: {capture['url']}\nStatut: {capture['nexus_status']}"
            else:
                answer = "❌ Capture non trouvée"
        else:
            answer = "❌ Action inconnue"

        # Answer the callback query (dismiss loading on Telegram)
        bot_token = notify._get_config().get("telegram_bot_token", "")
        if bot_token:
            import json as j
            from urllib.request import Request as Req, urlopen
            payload = j.dumps({"callback_query_id": callback.get("id", ""), "text": answer, "show_alert": False}).encode()
            try:
                urlopen(Req(
                    f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery",
                    data=payload, headers={"Content-Type": "application/json"}
                ), timeout=5)
            except Exception:
                pass

        return {"ok": True}

    # /start command (link client to chat)
    message = body.get("message", {})
    text = message.get("text", "")
    chat_id = str(message.get("from", {}).get("id", ""))

    if text.startswith("/start"):
        parts = text.split()
        if len(parts) > 1:
            client_id = parts[1]
            bot_token = notify._get_config().get("telegram_bot_token", "")
            db.update_notifications(client_id, telegram=chat_id)
            logger.info("[Telegram] Chat %s lié au client %s", chat_id, client_id)
            return {"ok": True, "message": "✅ Compte lié ! Vous recevrez les alertes ici."}

    return {"ok": True}
