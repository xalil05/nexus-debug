"""
Nexus-Capture — Breadcrumbs system.

Permet d'enregistrer des actions séquentielles avant un crash.
Les breadcrumbs sont automatiquement attachées aux exceptions capturées.

Usage:
    from nexus_capture.breadcrumbs import Breadcrumbs

    crumbs = Breadcrumbs(max_items=50)
    crumbs.add("Requête POST /api/login", category="http")
    crumbs.add("Validation token OK", category="auth")
    crumbs.add("Erreur BDD détectée", category="database", level="error")

    # En cas d'exception, les breadcrumbs sont incluses:
    from nexus_capture.client import capture_exception
    try:
        risky_operation()
    except Exception as e:
        capture_exception(e, breadcrumbs=crumbs.snapshot())
"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Any


class Breadcrumbs:
    """Thread-safe collecteur de breadcrumbs.

    Enregistre les actions séquentielles qui ont mené à un crash.
    Utile pour reconstituer le contexte après coup.

    Usage:
        crumbs = Breadcrumbs(max_items=30)
        crumbs.add("Action exécutée", category="user_action")
        capture_exception(e, breadcrumbs=crumbs.snapshot())
    """

    def __init__(self, max_items: int = 30):
        self._items: list[dict[str, Any]] = []
        self._max = max_items
        self._lock = threading.Lock()

    def add(
        self,
        message: str,
        *,
        category: str = "general",
        level: str = "info",
        data: dict[str, Any] | None = None,
    ) -> None:
        """Ajoute une étape à l'historique.

        Args:
            message: Description de l'action (ex: "Validation token échouée")
            category: Catégorie (http, auth, database, user_action, system, etc.)
            level: Niveau (info, warning, error)
            data: Données additionnelles optionnelles
        """
        item = {
            "timestamp": datetime.utcnow().isoformat(),
            "message": message[:200],
            "category": category,
            "level": level,
        }
        if data:
            item["data"] = str(data)[:1000]

        with self._lock:
            self._items.append(item)
            if len(self._items) > self._max:
                self._items.pop(0)

    def snapshot(self) -> list[dict[str, Any]]:
        """Retourne une copie des breadcrumbs (thread-safe)."""
        with self._lock:
            return list(self._items)

    def clear(self) -> None:
        """Vide l'historique."""
        with self._lock:
            self._items.clear()

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._items)


# Singleton global — pratique pour les middlewares
_default_crumbs = Breadcrumbs(max_items=50)


def add_breadcrumb(
    message: str,
    *,
    category: str = "general",
    level: str = "info",
    data: dict[str, Any] | None = None,
) -> None:
    """Ajoute une breadcrumb au collecteur global (pratique pour les middlewares)."""
    _default_crumbs.add(message, category=category, level=level, data=data)


def get_breadcrumbs() -> list[dict[str, Any]]:
    """Retourne les breadcrumbs du collecteur global."""
    return _default_crumbs.snapshot()


def clear_breadcrumbs() -> None:
    """Vide le collecteur global."""
    _default_crumbs.clear()
