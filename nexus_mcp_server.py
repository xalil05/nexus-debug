"""
nexus_mcp_server.py — Serveur MCP pour Nexus-debug
Expose 7 outils de diagnostic appelables par les agents.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import subprocess
from pathlib import Path

from loguru import logger
from mcp.server import FastMCP

from nexus_kb import kb_search, kb_store

# ─── Async subprocess helper ──────────────────────────────────────────────────


def _run_subprocess(
    cmd: list[str],
    timeout: int = 30,
    cwd: str | None = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=cwd,
    )


async def async_run_mcp_subprocess(
    cmd: list[str],
    timeout: int = 30,
    cwd: str | None = None,
) -> subprocess.CompletedProcess:
    """Exécute un subprocess sans bloquer l'event loop MCP."""
    return await asyncio.to_thread(
        _run_subprocess,
        cmd,
        timeout,
        cwd,
    )


mcp = FastMCP("nexus-debug")

CODEBASE_PATH = os.getenv("NEXUS_CODEBASE_PATH", "/app/workspace")
LOGS_ROOT = os.getenv("NEXUS_LOGS_ROOT", "/app/logs")
ALLOWED_DIAGNOSTICS = {"pytest", "bandit", "mypy", "ruff", "semgrep"}

def _safe_resolve(path: str, root: str = CODEBASE_PATH) -> str:
    """Vérifie qu'un chemin résolu est bien contenu dans le root autorisé."""
    resolved = os.path.realpath(os.path.join(root, path))
    root_real = os.path.realpath(root)
    if not resolved.startswith(root_real):
        raise ValueError(f"Chemin interdit: {path} (hors de {root})")
    return resolved


# ─── OUTIL 1 : search_code ────────────────────────────────────────────────────
@mcp.tool()
async def search_code(query: str, path: str = "") -> str:
    """Recherche une chaîne ou regex dans le code source via ripgrep."""
    search_path = _safe_resolve(path) if path else CODEBASE_PATH
    cmd = ["rg", "-n", "--max-count", "20", query, search_path]
    try:
        r = await async_run_mcp_subprocess(cmd, timeout=30)
        if r.returncode == 0:
            return r.stdout[:5000]
        return "Aucun résultat."
    except subprocess.TimeoutExpired:
        return json.dumps({"status": "error", "error": "Timeout (30s)"})
    except Exception as e:
        logger.warning("search_code error: {}", e)
        return json.dumps({"status": "error", "error": str(e)})


# ─── OUTIL 2 : sandbox_execute ────────────────────────────────────────────────
@mcp.tool()
async def sandbox_execute(code: str, language: str = "python", timeout: int = 10) -> str:
    """Exécute du code Python court dans un environnement isolé (Python uniquement)."""
    if language != "python":
        return json.dumps({"status": "error", "error": "Seul le langage 'python' est autorisé pour la sécurité"})
    # Bloque les imports système dangereux
    dangerous = ["import os", "subprocess", "__import__", "open(", "exec(", "eval("]
    if any(d in code for d in dangerous):
        return json.dumps({"status": "error", "error": "Code contenant des opérations système interdites"})
    try:
        r = await async_run_mcp_subprocess(
            ["python", "-c", code],
            timeout=timeout,
        )

        logger.debug("sandbox_execute ({}) — exit {}", language, r.returncode)
        return json.dumps(
            {
                "status": "success" if r.returncode == 0 else "error",
                "stdout": r.stdout[:2000],
                "stderr": r.stderr[:2000],
                "exit_code": r.returncode,
            }
        )
    except subprocess.TimeoutExpired:
        return json.dumps({"status": "error", "error": "Timeout dépassé"})
    except Exception as e:
        logger.warning("sandbox_execute error: {}", e)
        return json.dumps({"status": "error", "error": str(e)})


# ─── OUTIL 3 : run_diagnostic ─────────────────────────────────────────────────
@mcp.tool()
async def run_diagnostic(command: str, workdir: str = "") -> str:
    """Exécute une commande de diagnostic autorisée (pytest, bandit, mypy, ruff, semgrep)."""
    cmd_parts = shlex.split(command)
    if not cmd_parts or cmd_parts[0] not in ALLOWED_DIAGNOSTICS:
        return json.dumps({"status": "error", "error": f"Commande non autorisée: {cmd_parts[0] if cmd_parts else 'vide'}"})
    try:
        cwd = _safe_resolve(workdir) if workdir else CODEBASE_PATH
        r = await async_run_mcp_subprocess(
            shlex.split(command),
            timeout=120,
            cwd=cwd,
        )
        return json.dumps(
            {
                "status": "success" if r.returncode == 0 else "error",
                "stdout": r.stdout[:5000],
                "stderr": r.stderr[:2000],
                "exit_code": r.returncode,
            }
        )
    except subprocess.TimeoutExpired:
        return json.dumps({"status": "error", "error": "Timeout (120s)"})
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})


# ─── OUTIL 4 : git_blame ──────────────────────────────────────────────────────
@mcp.tool()
async def git_blame(file: str, line: int = 0) -> str:
    """Retourne l'auteur et le commit de la dernière modification d'une ligne."""
    try:
        filepath = _safe_resolve(file)
    except ValueError as e:
        return json.dumps({"status": "error", "error": str(e)})
    if not os.path.exists(filepath):
        return json.dumps({"status": "error", "error": f"Fichier non trouvé: {file}"})

    try:
        cmd = ["git", "-C", os.path.dirname(filepath), "blame", "-L", f"{line},{line}", file]
        r = await async_run_mcp_subprocess(cmd, timeout=15)
        if r.returncode == 0:
            return r.stdout[:500]
        return f"Erreur git blame: {r.stderr[:200]}"
    except Exception as e:
        return f"Erreur: {e}"


# ─── OUTIL 5 : kb_search ──────────────────────────────────────────────────────
@mcp.tool()
def kb_search_tool(query: str) -> str:
    """Recherche dans la base de connaissance des bugs résolus."""
    return json.dumps(kb_search(query))


# ─── OUTIL 6 : kb_store ───────────────────────────────────────────────────────
@mcp.tool()
def kb_store_tool(
    bug_id: str,
    category: str,
    summary: str,
    root_cause: str,
    solution: str,
) -> str:
    """Stocke un bug résolu dans la base de connaissance."""
    return json.dumps(
        kb_store(
            bug_id=bug_id,
            category=category,
            summary=summary,
            root_cause=root_cause,
            solution=solution,
        )
    )


# ─── OUTIL 7 : Analyse de logs ──────────────────────────────────────
@mcp.tool()
def analyze_logs(log_path: str, pattern: str = "", max_lines: int = 50) -> str:
    """Analyse un fichier de log dans /app/logs : affiche les dernières lignes, filtre par pattern si fourni."""
    try:
        log_file = Path(_safe_resolve(log_path, root=LOGS_ROOT))
    except ValueError as e:
        return json.dumps({"status": "error", "error": str(e)})
    if not log_file.exists():
        return json.dumps({"status": "error", "error": f"Fichier non trouvé: {log_path}"})

    try:
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        if pattern:
            matched = [l for l in lines if pattern.lower() in l.lower()]
            result = matched[-max_lines:]
            return json.dumps({
                "status": "success",
                "file": log_path,
                "pattern": pattern,
                "total_lines": len(lines),
                "matched_lines": len(matched),
                "lines": result,
            })
        else:
            result = lines[-max_lines:]
            return json.dumps({
                "status": "success",
                "file": log_path,
                "total_lines": len(lines),
                "lines": result,
            })
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})


if __name__ == "__main__":
    logger.remove()
    logger.add(lambda msg: print(msg, end=""), level="INFO")
    logger.info("Nexus-debug MCP server starting...")
    mcp.run()
