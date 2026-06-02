"""
Nexus-Capture — Flask middleware pour capture automatique des exceptions.

Usage:
    from nexus_capture.flask_middleware import NexusCaptureFlask
    app = Flask(__name__)
    NexusCaptureFlask(app, nexus_url="http://100.70.168.107:9001", api_key="...")
"""
from __future__ import annotations

import os
import sys
from typing import Any

from nexus_capture.client import (
    CAPTURE_API_KEY,
    CAPTURE_PROJECT,
    CAPTURE_URL,
    CAPTURE_VERSION,
    capture_manual,
)
from nexus_capture.breadcrumbs import add_breadcrumb, get_breadcrumbs


class NexusCaptureFlask:
    """Middleware Flask qui capture toutes les exceptions non gérées."""

    def __init__(
        self,
        app: Any = None,
        *,
        nexus_url: str = "",
        api_key: str = "",
        project: str = "",
        version: str = "",
        capture_4xx: bool = False,
    ):
        self.nexus_url = nexus_url or os.getenv("NEXUS_CAPTURE_URL", CAPTURE_URL)
        self.api_key = api_key or os.getenv("NEXUS_CAPTURE_API_KEY", CAPTURE_API_KEY)
        self.project = project or os.getenv("NEXUS_CAPTURE_PROJECT", CAPTURE_PROJECT)
        self.version = version or os.getenv("NEXUS_CAPTURE_VERSION", CAPTURE_VERSION)
        self.capture_4xx = capture_4xx

        if app:
            self.init_app(app)

    def init_app(self, app: Any) -> None:
        """Attache le middleware à l'application Flask."""

        # Override les variables d'env pour le client
        os.environ.setdefault("NEXUS_CAPTURE_URL", self.nexus_url)
        os.environ.setdefault("NEXUS_CAPTURE_API_KEY", self.api_key)
        os.environ.setdefault("NEXUS_CAPTURE_PROJECT", self.project)
        os.environ.setdefault("NEXUS_CAPTURE_VERSION", self.version)

        # Breadcrumbs automatiques : chaque requête est tracée
        @app.before_request
        def trace_request():
            from flask import request
            add_breadcrumb(
                f"Requête {request.method} {request.path}",
                category="http",
                data={"method": request.method, "path": request.path, "args": dict(list(request.args.items())[:5])},
            )

        # Intercepter les exceptions via le gestionnaire d'erreurs Flask
        @app.errorhandler(Exception)
        def handle_exception(error: Exception) -> Any:
            from flask import jsonify, request

            # Ne capturer que les 5xx par défaut (pas les 400/404)
            status_code = getattr(error, "code", 500)
            if status_code < 500 and not self.capture_4xx:
                raise error  # laisser Flask gérer normalement

            # Assembler le contexte
            ctx = {
                "method": request.method,
                "path": request.path,
                "query": dict(request.args),
                "remote_addr": request.remote_addr,
                "user_agent": request.headers.get("User-Agent", "")[:200],
            }

            add_breadcrumb(
                f"Erreur {status_code}: {type(error).__name__}",
                category="error",
                level="error",
            )

            capture_manual(
                description=f"Flask 5xx: {request.method} {request.path} — {type(error).__name__}",
                project=self.project,
                version=self.version,
                langage="Python/Flask",
                fichier=request.path,
                erreur=f"{type(error).__name__}: {str(error)[:2000]}",
                stack=_get_traceback(),
                priority="P1" if status_code >= 500 else "P2",
                context=ctx,
                breadcrumbs=get_breadcrumbs(),
            )

            # Laisser Flask gérer l'erreur normalement (page d'erreur)
            raise error

        # Logger l'initialisation
        app.logger.info(
            "Nexus-Capture: actif (url=%s, project=%s, version=%s)",
            self.nexus_url,
            self.project,
            self.version,
        )


def _get_traceback() -> str:
    import traceback
    return "".join(traceback.format_exception(*sys.exc_info()))[-10000:]
