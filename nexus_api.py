"""
nexus_api.py — API REST pour Nexus-debug v2
Endpoints : /debug, /status, /report, /health, /kb, /feedback
Webhooks : /webhook/github, /webhook/jira
Notifications : Slack
"""
import asyncio
import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
import yaml
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from nexus_agent import nexus_run
from nexus_kb import kb_store, kb_search, kb_stats

# ─── Configuration ────────────────────────────────────────────────────────────
API_PORT = int(os.getenv("NEXUS_API_PORT", "9001"))
API_HOST = os.getenv("NEXUS_API_HOST", "0.0.0.0")
GITHUB_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
REPORTS_DIR = Path(os.getenv("NEXUS_REPORTS_DIR", os.path.expanduser("~/nexus-reports")))
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
FEEDBACK_PATH = Path(os.getenv("NEXUS_FEEDBACK_PATH", os.path.expanduser("~/nexus_feedback.yaml")))

app = FastAPI(title="Nexus-debug API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Stockage des tâches ──────────────────────────────────────────────────────
tasks_store: dict[str, dict] = {}


# ─── Modèles ───────────────────────────────────────────────────────────────────
class DebugRequest(BaseModel):
    description: str
    project: str = ""
    langage: str = ""
    fichier: str = ""
    erreur: str = ""
    stack: str = ""
    priority: str = "P2"


class FeedbackRequest(BaseModel):
    task_id: str
    rating: int = Field(..., ge=1, le=5)
    comment: str = ""
    corrected_by_human: str = ""


# ─── Notifications ────────────────────────────────────────────────────────────

async def notify_slack(text: str) -> None:
    if not SLACK_WEBHOOK_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(SLACK_WEBHOOK_URL, json={"text": text})
    except Exception:
        pass


async def post_github_comment(owner: str, repo: str, issue_number: int, body: str) -> None:
    if not GITHUB_TOKEN:
        return
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/comments"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json={"body": body}, headers=headers)
            if resp.status_code not in (200, 201):
                print(f"[GitHub] Erreur {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[GitHub] Erreur : {e}")


def extract_summary(report: dict) -> str:
    lines = []
    if report.get("root_cause"):
        lines.append(f"Cause racine : {report['root_cause']}")
    if report.get("fix_summary"):
        lines.append(f"Fix : {report['fix_summary']}")
    if report.get("files_modified"):
        lines.append(f"Fichiers : {', '.join(report['files_modified'][:3])}")
    if report.get("status"):
        lines.append(f"Status : {report['status']}")
    return "\n".join(lines) if lines else str(report)[:300]


# ─── Tâche de fond ────────────────────────────────────────────────────────────

async def run_debug_task(task_id: str, brief: str, req: DebugRequest, github_info: dict = None):
    tasks_store[task_id]["status"] = "en_cours"
    tasks_store[task_id]["updated_at"] = datetime.utcnow().isoformat()

    try:
        result = await nexus_run(brief, mission_id=f"DBG-{task_id}")
        tasks_store[task_id]["status"] = "termine"
        tasks_store[task_id]["result"] = result
        tasks_store[task_id]["completed_at"] = datetime.utcnow().isoformat()

        # Stocker dans KB si fix réussi
        if result.get("status") == "fixed":
            kb_store(
                bug_id=f"BUG-{task_id}",
                category=result.get("bug_category", "unknown"),
                summary=result.get("fix_summary", "") or result.get("summary", ""),
                root_cause=result.get("root_cause", ""),
                solution=result.get("fix_summary", ""),
                langage=req.langage,
                keywords=[req.project, req.langage] if req.project or req.langage else [],
            )

        # Sauvegarder le rapport
        report_path = REPORTS_DIR / f"report_{task_id}.json"
        with open(report_path, "w") as f:
            json.dump(tasks_store[task_id], f, indent=2, ensure_ascii=False)

        # Notifications
        summary = extract_summary(result)
        slack_msg = f"🧬 *Nexus-debug — Bug résolu*\n```\n{summary}\n```\n📄 Rapport : {report_path}"
        await notify_slack(slack_msg)

        if github_info:
            gh_body = f"## 🤖 Nexus-debug — Rapport automatique\n\n{summary}\n\n[Rapport complet]({report_path})"
            await post_github_comment(github_info["owner"], github_info["repo"], github_info["issue"], gh_body)

    except Exception as e:
        tasks_store[task_id]["status"] = "erreur"
        tasks_store[task_id]["result"] = {"error": str(e)}
        await notify_slack(f"❌ *Nexus-debug — Erreur*\n```\n{str(e)[:500]}\n```")


# ─── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "2.0.0",
        "service": "nexus-debug",
        "github_webhook": bool(GITHUB_SECRET),
        "slack_webhook": bool(SLACK_WEBHOOK_URL),
    }


@app.post("/debug", status_code=202)
async def debug(req: DebugRequest, background_tasks: BackgroundTasks):
    task_id = uuid.uuid4().hex[:8]

    brief_parts = []
    if req.project: brief_parts.append(f"PROJET : {req.project}")
    if req.langage: brief_parts.append(f"LANGAGE : {req.langage}")
    if req.fichier: brief_parts.append(f"FICHIER : {req.fichier}")
    if req.erreur:  brief_parts.append(f"ERREUR : {req.erreur}")
    if req.stack:   brief_parts.append(f"STACK : {req.stack}")
    brief_parts.append(f"PRIORITÉ : {req.priority}")
    brief_parts.append(f"\nDESCRIPTION :\n{req.description}")
    brief = "\n".join(brief_parts)

    tasks_store[task_id] = {
        "task_id": task_id,
        "status": "en_attente",
        "priority": req.priority,
        "brief": brief,
        "created_at": datetime.utcnow().isoformat(),
        "completed_at": None,
        "result": None,
    }

    background_tasks.add_task(run_debug_task, task_id, brief, req)
    return {"task_id": task_id, "status": "en_attente"}


@app.get("/status/{task_id}")
async def get_status(task_id: str):
    task = tasks_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tâche non trouvée")
    return {"task_id": task_id, "status": task["status"]}


@app.get("/report/{task_id}")
async def get_report(task_id: str):
    task = tasks_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tâche non trouvée")
    return task


@app.get("/tasks")
async def list_tasks():
    return {
        "tasks": [
            {"task_id": t["task_id"], "status": t["status"],
             "priority": t["priority"], "created_at": t["created_at"]}
            for t in tasks_store.values()
        ]
    }


# ─── Feedback ──────────────────────────────────────────────────────────────────

@app.post("/feedback")
async def feedback(req: FeedbackRequest):
    feedbacks = []
    if FEEDBACK_PATH.exists():
        raw = yaml.safe_load(FEEDBACK_PATH.read_text()) or []
        feedbacks = raw if isinstance(raw, list) else []

    feedbacks.append({
        "task_id": req.task_id,
        "rating": req.rating,
        "comment": req.comment,
        "corrected_by_human": req.corrected_by_human,
        "timestamp": datetime.utcnow().isoformat(),
    })
    FEEDBACK_PATH.write_text(yaml.dump(feedbacks, allow_unicode=True, default_flow_style=False))
    return {"status": "recorded", "task_id": req.task_id}


# ─── KB ────────────────────────────────────────────────────────────────────────

@app.get("/kb/search")
async def kb_search_endpoint(q: str = ""):
    if not q:
        return kb_stats()
    return kb_search(q)


@app.get("/kb/stats")
async def kb_stats_endpoint():
    return kb_stats()


# ─── Webhook GitHub ───────────────────────────────────────────────────────────

@app.post("/webhook/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()

    # Vérification HMAC
    if GITHUB_SECRET:
        signature = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(GITHUB_SECRET.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=403, detail="Signature invalide")

    event = request.headers.get("X-GitHub-Event", "")
    payload = json.loads(body)

    if event == "ping":
        return {"status": "pong"}

    if event == "issues" and payload.get("action") in ("opened", "labeled"):
        issue = payload["issue"]
        title = issue.get("title", "")
        body_text = issue.get("body", "") or ""
        labels = [l["name"].lower() for l in issue.get("labels", [])]

        if "bug" not in labels:
            return {"status": "ignored", "reason": "pas un bug"}

        description = f"{title}\n\n{body_text}"
        task_id = uuid.uuid4().hex[:8]
        repo_full = payload.get("repository", {}).get("full_name", "")
        owner, repo = repo_full.split("/") if "/" in repo_full else ("", "")

        req = DebugRequest(description=description, project=repo)
        brief = f"PROJET : {repo}\nPRIORITÉ : P1\n\n{description}"

        tasks_store[task_id] = {
            "task_id": task_id, "status": "en_attente",
            "priority": "P1", "brief": brief,
            "created_at": datetime.utcnow().isoformat(),
            "completed_at": None, "result": None,
            "github_info": {"owner": owner, "repo": repo, "issue": issue["number"]},
        }

        background_tasks.add_task(
            run_debug_task, task_id, brief, req,
            {"owner": owner, "repo": repo, "issue": issue["number"]}
        )
        return {"task_id": task_id, "status": "en_attente"}

    return {"status": "ignored"}


# ─── Webhook Jira ─────────────────────────────────────────────────────────────

@app.post("/webhook/jira")
async def jira_webhook(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    event_type = body.get("webhookEvent", "")

    if "issue_created" in event_type or "issue_updated" in event_type:
        issue = body.get("issue", {})
        fields = issue.get("fields", {})
        issuetype = fields.get("issuetype", {}).get("name", "").lower()

        if "bug" not in issuetype.lower():
            return {"status": "ignored", "reason": "pas un bug"}

        title = fields.get("summary", "")
        description = fields.get("description", "") or ""
        project = fields.get("project", {}).get("key", "")

        full_desc = f"{title}\n\n{description}"
        task_id = uuid.uuid4().hex[:8]
        req = DebugRequest(description=full_desc, project=project)

        tasks_store[task_id] = {
            "task_id": task_id, "status": "en_attente",
            "priority": "P1", "brief": full_desc,
            "created_at": datetime.utcnow().isoformat(),
            "completed_at": None, "result": None,
        }

        background_tasks.add_task(run_debug_task, task_id, full_desc, req)
        return {"task_id": task_id, "status": "en_attente"}

    return {"status": "ignored"}


# ─── Démarrage ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("NEXUS_API_PORT", "9001"))
    host = os.getenv("NEXUS_API_HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port, log_level="info")
