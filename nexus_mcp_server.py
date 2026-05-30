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

CODEBASE_PATH = os.getenv("NEXUS_CODEBASE_PATH", os.path.expanduser("~/"))


# ─── OUTIL 1 : search_code ────────────────────────────────────────────────────
@mcp.tool()
async def search_code(query: str, path: str = "") -> str:
    """Recherche une chaîne ou regex dans le code source via ripgrep."""
    search_path = os.path.join(CODEBASE_PATH, path) if path else CODEBASE_PATH
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
    """Exécute du code court dans un environnement isolé."""
    try:
        if language == "python":
            r = await async_run_mcp_subprocess(
                ["python", "-c", code],
                timeout=timeout,
            )
        elif language == "bash":
            r = await async_run_mcp_subprocess(
                ["bash", "-c", code],
                timeout=timeout,
            )
        elif language in ("javascript", "js"):
            r = await async_run_mcp_subprocess(
                ["node", "-e", code],
                timeout=timeout,
            )
        else:
            return json.dumps({"status": "error", "error": f"Langage non supporté: {language}"})

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
    """Exécute une commande de diagnostic autorisée (pytest, bandit, etc.)."""
    cwd = os.path.join(CODEBASE_PATH, workdir) if workdir else CODEBASE_PATH
    try:
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
    filepath = os.path.join(CODEBASE_PATH, file)
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
    """Analyse un fichier de log : affiche les dernières lignes, filtre par pattern si fourni."""
    log_file = Path(log_path)
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
