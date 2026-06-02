"""Nexus Hub — API routes for multi-tenant error capture."""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Optional

from . import db

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

    # TODO: trigger Nexus-Debug diagnostic asynchronously
    # For now, return immediately

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
