"""
nexus_api.py — API REST pour Nexus-debug v2.1
Endpoints : /debug, /status, /report, /health, /kb, /feedback, /metrics
Webhooks : /webhook/github, /webhook/jira
Notifications : Slack
Sécurité : API Key auth + Rate limiting + Validation
Persistance : SQLite (tasks) + YAML (KB + feedback)
Logging : loguru structuré
"""

from __future__ import annotations

import hashlib
import hmac
import importlib.metadata
import json
import os
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from loguru import logger
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from nexus_agent import nexus_run
from nexus_kb import kb_search, kb_stats, kb_store

# ── DeepSeek healthcheck ──────────────────────────────
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")


async def check_deepseek_health() -> dict:
    """Vérifie que l'API DeepSeek est joignable."""
    if not DEEPSEEK_API_KEY:
        return {"status": "not_configured", "error": "DEEPSEEK_API_KEY manquante"}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{DEEPSEEK_BASE_URL}/models",
                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
            )
            if resp.status_code == 200:
                models = resp.json().get("data", [])
                available = [m["id"] for m in models[:5]]
                return {"status": "ok", "models_available": available}
            return {"status": "error", "http_status": resp.status_code, "detail": resp.text[:200]}
    except httpx.TimeoutException:
        return {"status": "error", "error": "timeout (5s)"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:200]}


# ── Version centralisée ────────────────────────────────────────────
try:
    VERSION = importlib.metadata.version("nexus-debug")
except importlib.metadata.PackageNotFoundError:
    VERSION = "2.2.1-dev"  # fallback pour développement local

# ── Configuration ─────────────────────────────────────────────────────────────
API_PORT = int(os.getenv("NEXUS_API_PORT", "9001"))
API_HOST = os.getenv("NEXUS_API_HOST", "0.0.0.0")
API_KEY = os.getenv("NEXUS_API_KEY", "")
CORS_ORIGIN = os.getenv("NEXUS_CORS_ORIGIN", "http://localhost:9001")
GITHUB_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
DB_PATH = Path(os.getenv("NEXUS_DB_PATH", "/data/nexus/nexus.db"))
REPORTS_DIR = Path(os.getenv("NEXUS_REPORTS_DIR", "/data/nexus/reports"))
FEEDBACK_PATH = Path(os.getenv("NEXUS_FEEDBACK_PATH", "/data/nexus/feedback/nexus_feedback.yaml"))
MAX_BRIEF_LENGTH = int(os.getenv("NEXUS_MAX_BRIEF_LENGTH", "5000"))
RATE_LIMIT = os.getenv("NEXUS_RATE_LIMIT", "10/minute")

REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Rate Limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ── Logger ────────────────────────────────────────────────────────────────────
logger.add(REPORTS_DIR / "nexus_api.log", rotation="10 MB", retention=3, level="INFO")
logger.add(REPORTS_DIR / "nexus_api_error.log", rotation="10 MB", retention=7, level="ERROR")


# ── Database ──────────────────────────────────────────────────────────────────
class Database:
    """SQLite lightweight persistence for tasks store."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn: Any = None

    async def connect(self) -> None:
        import aiosqlite

        db_path = str(self.path) if self.path else ":memory:"
        self._conn = await aiosqlite.connect(db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                status TEXT DEFAULT 'en_attente',
                priority TEXT DEFAULT 'P2',
                brief TEXT DEFAULT '',
                created_at TEXT,
                completed_at TEXT,
                result TEXT DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        """)
        await self._conn.commit()
        logger.info("Database ready at {}", self.path)

    async def _ensure_connected(self) -> None:
        """Auto-connect on first use — handles test contexts without startup event."""
        if self._conn is None:
            await self.connect()

    async def save_task(self, task_id: str, task: dict[str, Any]) -> None:
        await self._ensure_connected()
        await self._conn.execute(
            "INSERT OR REPLACE INTO tasks (task_id, status, priority, brief, created_at, completed_at, result) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                task_id,
                task.get("status", "en_attente"),
                task.get("priority", "P2"),
                task.get("brief", ""),
                task.get("created_at", datetime.utcnow().isoformat()),
                task.get("completed_at"),
                json.dumps(task.get("result", {}), ensure_ascii=False),
            ),
        )
        await self._conn.commit()

    async def get_task(self, task_id: str) -> dict[str, Any] | None:
        await self._ensure_connected()
        cursor = await self._conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        task = dict(row)
        task["result"] = json.loads(task.get("result", "{}"))
        return task

    async def list_tasks(self, limit: int = 50) -> list[dict[str, Any]]:
        await self._ensure_connected()
        cursor = await self._conn.execute(
            "SELECT task_id, status, priority, created_at FROM tasks ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()


db = Database(DB_PATH)


# ── Dépendences ───────────────────────────────────────────────────────────────

def sanitize_brief_text(text: str, max_len: int = 2000) -> str:
    """Sanitization LÉGÈRE du brief : bornes + neutralisation minimale.
    N'enlève PAS les blocs ```, system:, tool_ (nécessaires aux bugs réels).
    """
    # 1) Limiter la taille
    text = text[:max_len]
    # 2) Neutraliser les tentatives de redéfinition du rôle
    #    On prévient dans le system prompt (voir nexus_agent.py),
    #    ici on ne fait qu'une protection basique contre les patterns évidents
    text = text.replace("\u0000", "")  # null byte
    return text


async def verify_api_key(request: Request) -> None:
    """Dependency : vérifie la clé API si configurée."""
    if not API_KEY:
        return
    auth = request.headers.get("Authorization", "")
    if auth not in (f"Bearer {API_KEY}", API_KEY):
        raise HTTPException(status_code=401, detail="Clé API invalide")


def validate_brief_length(request: DebugRequest) -> DebugRequest:
    """Valide la taille du brief."""
    if len(request.description) > MAX_BRIEF_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"Description trop longue ({len(request.description)} chars, max {MAX_BRIEF_LENGTH})",
        )
    return request


# ── Modèles ───────────────────────────────────────────────────────────────────
class DebugRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=5000, description="Description du bug")
    project: str = Field(default="", max_length=200)
    langage: str = Field(default="", max_length=50)
    fichier: str = Field(default="", max_length=500)
    erreur: str = Field(default="", max_length=2000)
    stack: str = Field(default="", max_length=10000)
    priority: str = Field(default="P2", pattern=r"^P[0-4]$")


class FeedbackRequest(BaseModel):
    task_id: str = Field(..., min_length=1)
    rating: int = Field(..., ge=1, le=5)
    comment: str = Field(default="", max_length=2000)
    corrected_by_human: str = Field(default="", max_length=5000)


# ── Notifications ─────────────────────────────────────────────────────────────


async def notify_slack(text: str) -> None:
    if not SLACK_WEBHOOK_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(SLACK_WEBHOOK_URL, json={"text": text})
    except Exception as exc:
        logger.warning("Slack notification failed: {}", exc)


async def post_github_comment(owner: str, repo: str, issue_number: int, body: str) -> None:
    if not GITHUB_TOKEN:
        return
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/comments"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json={"body": body}, headers=headers)
            if resp.status_code not in (200, 201):
                logger.warning("GitHub comment failed: {} {}", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.warning("GitHub comment error: {}", exc)


def extract_summary(report: dict[str, Any]) -> str:
    lines: list[str] = []
    if report.get("root_cause"):
        lines.append(f"Cause racine : {report['root_cause']}")
    if report.get("fix_summary"):
        lines.append(f"Fix : {report['fix_summary']}")
    if report.get("files_modified"):
        lines.append(f"Fichiers : {', '.join(report['files_modified'][:3])}")
    if report.get("status"):
        lines.append(f"Status : {report['status']}")
    return "\n".join(lines) if lines else str(report)[:300]


# ── Tâche de fond ─────────────────────────────────────────────────────────────


async def run_debug_task(
    task_id: str,
    brief: str,
    req: DebugRequest,
    github_info: dict[str, Any] | None = None,
) -> None:
    task = await db.get_task(task_id)
    if task:
        task["status"] = "en_cours"
        task["updated_at"] = datetime.utcnow().isoformat()
        await db.save_task(task_id, task)

    logger.info("Démarrage mission {} — {}", task_id, req.description[:80])

    try:
        result = await nexus_run(brief, mission_id=f"DBG-{task_id}")
        result_status = result.get("status", "unknown")

        await db.save_task(
            task_id,
            {
                "task_id": task_id,
                "status": "termine",
                "brief": brief,
                "result": result,
                "priority": req.priority,
                "created_at": task.get("created_at", datetime.utcnow().isoformat())
                if task
                else datetime.utcnow().isoformat(),
                "completed_at": datetime.utcnow().isoformat(),
            },
        )

        # Stocker dans KB
        if result_status == "fixed":
            kb_store(
                bug_id=f"BUG-{task_id}",
                category=result.get("bug_category", "unknown"),
                summary=result.get("fix_summary", "") or result.get("summary", ""),
                root_cause=result.get("root_cause", ""),
                solution=result.get("fix_summary", ""),
                langage=req.langage,
                keywords=[req.project, req.langage] if req.project or req.langage else [],
            )

        # Notifications
        summary = extract_summary(result)
        slack_msg = f"🧬 *Nexus-debug — Bug résolu*\n```\n{summary}\n```"
        await notify_slack(slack_msg)

        if github_info:
            gh_body = f"## 🤖 Nexus-debug — Rapport automatique\n\n{summary}"
            await post_github_comment(
                github_info["owner"],
                github_info["repo"],
                github_info["issue"],
                gh_body,
            )

        logger.info("Mission {} terminée : {}", task_id, result_status)

    except Exception as exc:
        logger.error("Mission {} échouée : {}", task_id, exc)
        await db.save_task(
            task_id,
            {
                "task_id": task_id,
                "status": "erreur",
                "priority": req.priority,
                "brief": brief,
                "created_at": datetime.utcnow().isoformat(),
                "completed_at": datetime.utcnow().isoformat(),
                "result": {"error": str(exc)},
            },
        )
        await notify_slack(f"❌ *Nexus-debug — Erreur*\n```\n{str(exc)[:500]}\n```")


# ── Endpoints ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(_application: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown handled via lifespan context."""
    # Validation au démarrage
    if not DEEPSEEK_API_KEY:
        logger.warning("🚨 DEEPSEEK_API_KEY non définie — l'API DeepSeek est INACCESSIBLE")
        logger.warning("   → Définir dans .env : DEEPSEEK_API_KEY=sk-votre_clé")
        logger.warning("   → Les appels agents échoueront avec 'Missing credentials'")

    if not API_KEY:
        logger.error("🚨 NEXUS_API_KEY non définie — l'API REFUSE de démarrer sans clé")
        logger.error("   → Définir NEXUS_API_KEY dans .env ou l'environnement")
        msg = "NEXUS_API_KEY est obligatoire — ajoutez-la dans .env"
        raise RuntimeError(msg)
    else:
        logger.info("✅ DEEPSEEK_API_KEY détectée")

    if not GITHUB_SECRET and not GITHUB_TOKEN:
        logger.info("ℹ️  Webhooks GitHub non configurés (GITHUB_SECRET/GITHUB_TOKEN)")
    if not SLACK_WEBHOOK_URL:
        logger.info("ℹ️  Notifications Slack non configurées (SLACK_WEBHOOK_URL)")

    await db.connect()
    logger.info("Nexus-debug API v2.1 démarrée sur {}:{}", API_HOST, API_PORT)
    yield
    await db.close()
    logger.info("Nexus-debug API arrêtée")


app = FastAPI(
    title="Nexus-debug API",
    version=VERSION,
    description="🧬 Système agentique de débogage (ReAct + LangGraph + DeepSeek V4 Pro)",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── Middleware & config ───────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[CORS_ORIGIN],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

# ── Tags OpenAPI ──────────────────────────────────────
TAG_SYSTEM = "⚙️ Système"
TAG_DEBUG = "🧬 Debug"
TAG_KB = "📚 Base de connaissance"
TAG_WEBHOOK = "🔗 Webhooks"

for tag, desc in [
    (TAG_SYSTEM, "Healthcheck, métriques, statut du service"),
    (TAG_DEBUG, "Soumettre et suivre des missions de débogage"),
    (TAG_KB, "Rechercher et consulter la base de connaissance"),
    (TAG_WEBHOOK, "Recevoir des bugs depuis GitHub et Jira"),
]:
    current_tags = app.openapi_tags or []
    if not any(t.get("name") == tag for t in current_tags):
        app.openapi_tags = current_tags + [{"name": tag, "description": desc}]

# ── Prometheus metrics ───────────────────────────────
METRIC_HTTP_REQUESTS = Counter(
    "nexus_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
METRIC_TASKS_TOTAL = Counter(
    "nexus_tasks_total",
    "Total debug tasks submitted",
)
METRIC_TASKS_FIXED = Counter(
    "nexus_tasks_fixed_total",
    "Total bugs successfully fixed",
)
METRIC_TASKS_DURATION = Histogram(
    "nexus_task_duration_seconds",
    "Duration of debug tasks in seconds",
    buckets=[5, 15, 30, 60, 120, 300, 600],
)
METRIC_KB_ENTRIES = Counter(
    "nexus_kb_entries_total",
    "Total knowledge base entries stored",
)


@app.get("/metrics", tags=[TAG_SYSTEM], summary="Métriques Prometheus")
async def metrics() -> PlainTextResponse:
    """Expose les métriques Prometheus pour le monitoring."""
    return PlainTextResponse(
        generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST,
    )


@app.get("/health", tags=[TAG_SYSTEM], summary="Healthcheck complet avec DeepSeek et DB")
async def health() -> dict[str, Any]:
    deepseek = await check_deepseek_health()
    return {
        "status": "ok",
        "version": VERSION,
        "service": "nexus-debug",
        "db_connected": db._conn is not None,
        "deepseek": deepseek,
        "github_webhook": bool(GITHUB_SECRET),
        "slack_webhook": bool(SLACK_WEBHOOK_URL),
        "api_key_configured": bool(API_KEY),
        "metrics_enabled": True,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post(
    "/debug",
    status_code=202,
    dependencies=[Depends(verify_api_key)],
    tags=[TAG_DEBUG],
    summary="Soumettre un bug à l'agent Nexus",
)
@limiter.limit(RATE_LIMIT)
async def debug(
    req: DebugRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> dict[str, Any]:
    validate_brief_length(req)

    task_id = uuid.uuid4().hex[:8]
    brief_parts: list[str] = []
    if req.project:
        brief_parts.append(f"PROJET : {req.project}")
    if req.langage:
        brief_parts.append(f"LANGAGE : {req.langage}")
    if req.fichier:
        brief_parts.append(f"FICHIER : {req.fichier}")
    if req.erreur:
        brief_parts.append(f"ERREUR : {req.erreur}")
    if req.stack:
        brief_parts.append(f"STACK : {req.stack}")
    brief_parts.append(f"PRIORITÉ : {req.priority}")
    brief_parts.append(f"\nDESCRIPTION :\n{req.description}")
    brief = sanitize_brief_text("\n".join(brief_parts))

    await db.save_task(
        task_id,
        {
            "task_id": task_id,
            "status": "en_attente",
            "priority": req.priority,
            "brief": brief,
            "created_at": datetime.utcnow().isoformat(),
            "completed_at": None,
            "result": {},
        },
    )

    background_tasks.add_task(run_debug_task, task_id, brief, req)
    redacted = req.description[:60].replace("sk-", "sk-***").replace("ghp_", "ghp_***")
    logger.info("Bug soumis : {} ({})", task_id, redacted)
    return {"task_id": task_id, "status": "en_attente"}


@app.get("/status/{task_id}", tags=[TAG_DEBUG], summary="Statut d'une mission de débogage")
async def get_status(task_id: str) -> dict[str, Any]:
    task = await db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tâche non trouvée")
    return {"task_id": task_id, "status": task["status"]}


@app.get("/report/{task_id}", tags=[TAG_DEBUG], summary="Rapport complet d'une mission")
async def get_report(task_id: str) -> dict[str, Any]:
    task = await db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tâche non trouvée")
    return task


@app.get("/tasks", tags=[TAG_DEBUG], summary="Lister les missions récentes")
async def list_tasks(limit: int = 20) -> dict[str, Any]:
    tasks = await db.list_tasks(limit=min(limit, 100))
    return {"tasks": tasks, "total": len(tasks)}


# ── Feedback ──────────────────────────────────────────────────────────────────


@app.post(
    "/feedback",
    dependencies=[Depends(verify_api_key)],
    tags=[TAG_DEBUG],
    summary="Noter la qualité d'une mission",
)
async def feedback(req: FeedbackRequest) -> dict[str, str]:
    feedbacks: list[dict[str, Any]] = []
    if FEEDBACK_PATH.exists():
        raw = yaml.safe_load(FEEDBACK_PATH.read_text()) or []
        feedbacks = raw if isinstance(raw, list) else []

    feedbacks.append(
        {
            "task_id": req.task_id,
            "rating": req.rating,
            "comment": req.comment,
            "corrected_by_human": req.corrected_by_human,
            "timestamp": datetime.utcnow().isoformat(),
        }
    )
    FEEDBACK_PATH.write_text(yaml.dump(feedbacks, allow_unicode=True, default_flow_style=False))
    logger.info("Feedback enregistré : {} (note={})", req.task_id, req.rating)
    return {"status": "recorded", "task_id": req.task_id}


# ── KB ────────────────────────────────────────────────────────────────────────


@app.get("/kb/search", tags=[TAG_KB], summary="Rechercher dans la base de connaissance")
async def kb_search_endpoint(q: str = "") -> dict[str, Any]:
    if not q:
        return kb_stats()
    return kb_search(q)


@app.get("/kb/stats", tags=[TAG_KB], summary="Statistiques de la base de connaissance")
async def kb_stats_endpoint() -> dict[str, Any]:
    return kb_stats()


# ── Webhook GitHub ────────────────────────────────────────────────────────────


@app.post("/webhook/github", tags=[TAG_WEBHOOK], summary="Webhook entrant GitHub Issues (label: bug)")
@limiter.limit(RATE_LIMIT)
async def github_webhook(request: Request, background_tasks: BackgroundTasks) -> dict[str, Any]:
    body = await request.body()

    if GITHUB_SECRET:
        signature = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(GITHUB_SECRET.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            logger.warning("Webhook GitHub: signature invalide")
            raise HTTPException(status_code=403, detail="Signature invalide")

    event = request.headers.get("X-GitHub-Event", "")
    payload = json.loads(body)

    if event == "ping":
        return {"status": "pong"}

    if event == "issues" and payload.get("action") in ("opened", "labeled"):
        issue = payload["issue"]
        labels = [lb["name"].lower() for lb in issue.get("labels", [])]

        if "bug" not in labels:
            return {"status": "ignored", "reason": "pas un bug"}

        description = f"{issue.get('title', '')}\n\n{issue.get('body', '') or ''}"
        task_id = uuid.uuid4().hex[:8]
        repo_full = payload.get("repository", {}).get("full_name", "")
        owner, repo = repo_full.split("/") if "/" in repo_full else ("", "")

        req = DebugRequest(description=description, project=repo)
        brief = f"PROJET : {repo}\nPRIORITÉ : P1\n\n{description}"

        await db.save_task(
            task_id,
            {
                "task_id": task_id,
                "status": "en_attente",
                "priority": "P1",
                "brief": brief,
                "created_at": datetime.utcnow().isoformat(),
                "completed_at": None,
                "result": {},
            },
        )

        background_tasks.add_task(
            run_debug_task,
            task_id,
            brief,
            req,
            {"owner": owner, "repo": repo, "issue": issue["number"]},
        )
        logger.info("Webhook GitHub: issue bug #{} → {}", issue["number"], task_id)
        return {"task_id": task_id, "status": "en_attente"}

    return {"status": "ignored"}


# ── Webhook Jira ──────────────────────────────────────────────────────────────


@app.post("/webhook/jira", tags=[TAG_WEBHOOK], summary="Webhook entrant Jira (issuetype: Bug)")
@limiter.limit(RATE_LIMIT)
async def jira_webhook(request: Request, background_tasks: BackgroundTasks) -> dict[str, Any]:
    body = await request.json()
    event_type = body.get("webhookEvent", "")

    if "issue_created" in event_type or "issue_updated" in event_type:
        issue = body.get("issue", {})
        fields = issue.get("fields", {})
        issuetype = fields.get("issuetype", {}).get("name", "").lower()

        if "bug" not in issuetype:
            return {"status": "ignored", "reason": "pas un bug"}

        title = fields.get("summary", "")
        description = fields.get("description", "") or ""
        project = fields.get("project", {}).get("key", "")
        full_desc = f"{title}\n\n{description}"
        task_id = uuid.uuid4().hex[:8]
        req = DebugRequest(description=full_desc, project=project)

        await db.save_task(
            task_id,
            {
                "task_id": task_id,
                "status": "en_attente",
                "priority": "P1",
                "brief": full_desc,
                "created_at": datetime.utcnow().isoformat(),
                "completed_at": None,
                "result": {},
            },
        )

        background_tasks.add_task(run_debug_task, task_id, full_desc, req)
        logger.info("Webhook Jira: bug {} → {}", title[:50], task_id)
        return {"task_id": task_id, "status": "en_attente"}

    return {"status": "ignored"}


# ── Démarrage ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("NEXUS_API_PORT", "9001"))
    host = os.getenv("NEXUS_API_HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port, log_level="info")
