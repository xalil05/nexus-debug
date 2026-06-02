"""
Nexus-Capture — HTTP client for sending captured errors to Nexus-Debug API.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any

logger = logging.getLogger("nexus-capture")

CAPTURE_URL = os.getenv("NEXUS_CAPTURE_URL", "http://100.70.168.107:9001")
CAPTURE_API_KEY = os.getenv("NEXUS_CAPTURE_API_KEY", "")
CAPTURE_ENABLED = os.getenv("NEXUS_CAPTURE_ENABLED", "1") == "1"
CAPTURE_PROJECT = os.getenv("NEXUS_CAPTURE_PROJECT", "unknown")
CAPTURE_VERSION = os.getenv("NEXUS_CAPTURE_VERSION", "0.0.0")


@dataclass
class CapturePayload:
    """Payload envoyé à Nexus-Debug POST /debug"""
    description: str
    project: str = CAPTURE_PROJECT
    version: str = CAPTURE_VERSION
    langage: str = ""
    fichier: str = ""
    erreur: str = ""
    stack: str = ""
    priority: str = "P2"
    breadcrumbs: list[dict[str, Any]] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""


def capture_exception(
    exc: Exception,
    project: str = "",
    version: str = "",
    langage: str = "",
    fichier: str = "",
    priority: str = "P2",
    breadcrumbs: list[dict[str, Any]] | None = None,
    context: dict[str, Any] | None = None,
    description: str = "",
) -> None:
    """Capture une exception et l'envoie à Nexus-Debug en arrière-plan (thread)."""
    if not CAPTURE_ENABLED:
        logger.debug("Capture disabled, skipping")
        return

    import traceback

    tb = traceback.format_exc()
    error_type = type(exc).__name__
    error_msg = str(exc)[:2000]

    payload = CapturePayload(
        description=description or f"{error_type}: {error_msg[:200]}",
        project=project or CAPTURE_PROJECT,
        version=version or CAPTURE_VERSION,
        langage=langage or "Python",
        fichier=fichier,
        erreur=f"{error_type}: {error_msg}",
        stack=tb[:10000],
        priority=priority,
        breadcrumbs=breadcrumbs or [],
        context=context or {},
        timestamp=datetime.utcnow().isoformat(),
    )

    # Envoi en arrière-plan — ne bloque jamais l'application
    thread = threading.Thread(
        target=_send_payload,
        args=(payload,),
        daemon=True,
    )
    thread.start()


def capture_manual(
    *,
    description: str,
    project: str = "",
    version: str = "",
    langage: str = "Python",
    fichier: str = "",
    erreur: str = "",
    stack: str = "",
    priority: str = "P2",
    breadcrumbs: list[dict[str, Any]] | None = None,
    context: dict[str, Any] | None = None,
) -> str | None:
    """Envoie manuellement un signalement à Nexus-Debug (synchrone).
    Retourne le task_id si succès, None sinon.
    """
    if not CAPTURE_ENABLED:
        return None

    payload = CapturePayload(
        description=description,
        project=project or CAPTURE_PROJECT,
        version=version or CAPTURE_VERSION,
        langage=langage,
        fichier=fichier,
        erreur=erreur,
        stack=stack[-10000:],
        priority=priority,
        breadcrumbs=breadcrumbs or [],
        context=context or {},
        timestamp=datetime.utcnow().isoformat(),
    )
    return _send_payload(payload)


def _send_payload(payload: CapturePayload) -> str | None:
    """Envoie le payload à l'API Nexus-Debug."""
    try:
        import httpx

        url = f"{CAPTURE_URL}/debug"
        headers = {"Content-Type": "application/json"}
        if CAPTURE_API_KEY:
            headers["Authorization"] = f"Bearer {CAPTURE_API_KEY}"

        data = asdict(payload)
        # Enlever les champs vides pour économiser de la bande
        data = {k: v for k, v in data.items() if v}

        resp = httpx.post(url, json=data, headers=headers, timeout=10)
        if resp.status_code == 200:
            result = resp.json()
            task_id = result.get("task_id", "?")
            logger.info("Nexus-Capture: bug envoyé (task=%s)", task_id)
            return task_id
        else:
            logger.warning(
                "Nexus-Capture: échec HTTP %s: %s",
                resp.status_code,
                resp.text[:200],
            )
            return None
    except Exception as exc:
        logger.debug("Nexus-Capture: échec envoi: %s", exc)
        # Échec silencieux — ne jamais casser l'application hôte
        return None
