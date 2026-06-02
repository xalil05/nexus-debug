"""
Nexus-Capture — FastAPI middleware pour capture automatique des exceptions.

Usage:
    from nexus_capture.fastapi_middleware import NexusCaptureFastAPI
    app = FastAPI()
    NexusCaptureFastAPI(app, nexus_url="http://100.70.168.107:9001", api_key="...")
"""
from __future__ import annotations

import os
import sys
from typing import Awaitable, Callable

from nexus_capture.client import (
    CAPTURE_API_KEY,
    CAPTURE_PROJECT,
    CAPTURE_URL,
    CAPTURE_VERSION,
    capture_manual,
)
from nexus_capture.breadcrumbs import add_breadcrumb, get_breadcrumbs


class NexusCaptureFastAPI:
    """Middleware FastAPI qui capture toutes les exceptions non gérées."""

    def __init__(
        self,
        app=None,
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

    def init_app(self, app) -> None:
        """Attache le middleware à l'application FastAPI."""
        from fastapi import Request
        from fastapi.responses import JSONResponse

        os.environ.setdefault("NEXUS_CAPTURE_URL", self.nexus_url)
        os.environ.setdefault("NEXUS_CAPTURE_API_KEY", self.api_key)
        os.environ.setdefault("NEXUS_CAPTURE_PROJECT", self.project)
        os.environ.setdefault("NEXUS_CAPTURE_VERSION", self.version)

        @app.middleware("http")
        async def nexus_capture_middleware(
            request: Request,
            call_next: Callable[[Request], Awaitable],
        ):
            add_breadcrumb(
                f"Requête {request.method} {request.url.path}",
                category="http",
                data={"method": request.method, "path": request.url.path},
            )
            try:
                response = await call_next(request)
                # Capturer les 4xx si demandé
                if self.capture_4xx and 400 <= response.status_code < 500:
                    _capture_http_error(request, response.status_code)
                return response
            except Exception as exc:
                # Capturer toutes les exceptions 5xx
                _capture_exception(request, exc)
                # Relancer — laisser FastAPI gérer l'erreur
                raise

        @app.exception_handler(Exception)
        async def global_exception_handler(request: Request, exc: Exception):
            # Assurons-nous que l'exception est capturée même si le middleware
            # HTTP ne l'attrape pas (ex: exceptions levées dans les dépendances)
            _capture_exception(request, exc)
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error", "captured": True},
            )

        # Logger
        import logging
        logger = logging.getLogger("nexus-capture")
        logger.info(
            "Nexus-Capture FastAPI: actif (url=%s, project=%s, version=%s)",
            self.nexus_url,
            self.project,
            self.version,
        )


def _capture_exception(request, exc: Exception) -> None:
    """Capture une exception avec le contexte de la requête."""
    ctx = {
        "method": request.method,
        "path": request.url.path,
        "query": dict(request.query_params),
        "client_host": request.client.host if request.client else "",
        "user_agent": request.headers.get("user-agent", "")[:200],
    }

    try:
        body = request.state._body  # tentative de récupérer le body
        if body:
            ctx["body_preview"] = str(body)[:500]
    except Exception:
        pass

    add_breadcrumb(
        f"Erreur 500: {type(exc).__name__}",
        category="error",
        level="error",
    )

    capture_manual(
        description=f"FastAPI 5xx: {request.method} {request.url.path} — {type(exc).__name__}",
        project=os.getenv("NEXUS_CAPTURE_PROJECT", ""),
        version=os.getenv("NEXUS_CAPTURE_VERSION", ""),
        langage="Python/FastAPI",
        fichier=str(request.url.path),
        erreur=f"{type(exc).__name__}: {str(exc)[:2000]}",
        stack=_get_traceback(),
        priority="P1",
        context=ctx,
        breadcrumbs=get_breadcrumbs(),
    )


def _capture_http_error(request, status_code: int) -> None:
    """Capture les erreurs HTTP 4xx si configuré."""
    ctx = {
        "method": request.method,
        "path": request.url.path,
        "query": dict(request.query_params),
    }

    capture_manual(
        description=f"HTTP {status_code}: {request.method} {request.url.path}",
        project=os.getenv("NEXUS_CAPTURE_PROJECT", ""),
        priority="P3" if status_code == 404 else "P2",
        langage="HTTP",
        erreur=f"HTTP {status_code}",
        context=ctx,
    )


def _get_traceback() -> str:
    import traceback
    return "".join(traceback.format_exception(*sys.exc_info()))[-10000:]
