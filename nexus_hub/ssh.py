"""
Nexus Hub — SSH Diagnostic Engine (Option B)
=============================================

Connecte Nexus-Debug au serveur du client via SSH pour :
  - Lire les logs (nginx, apache, application)
  - Exécuter des diagnostics (top, df, journalctl)
  - Inspecter la configuration
  - Vérifier l'état des services

┌─────────────────────────────────────────────────────────────────────────┐
│ OPTION C — ALTERNATIVE FUTURE (watch-agent)                            │
│                                                                        │
│ Quand les clients sont derrière NAT/firewall, un agent côté client     │
│ est préférable. Voir notes à la fin de ce fichier.                     │
└─────────────────────────────────────────────────────────────────────────┘
"""

import io
import logging
import os
import re
import tempfile
from typing import Optional

import paramiko

from . import db

logger = logging.getLogger("nexus.hub.ssh")


# ─── Constants ────────────────────────────────────────────────────────────

DEFAULT_TIMEOUT = 15  # seconds
DEFAULT_COMMANDS = [
    "hostname",
    "uptime",
    "free -h",
    "df -h /",
    "top -bn1 | head -20",
    "journalctl -u nginx --no-pager -n 30 2>/dev/null || journalctl -u apache2 --no-pager -n 30 2>/dev/null || echo 'No web service logs'",
    "tail -100 /var/log/nginx/error.log 2>/dev/null || tail -100 /var/log/apache2/error.log 2>/dev/null || echo 'No error logs found'",
    "docker ps --format 'table {{.Names}}\t{{.Status}}' 2>/dev/null || echo 'Docker not available'",
]


# ─── SSH Connection ───────────────────────────────────────────────────────

def connect(client_id: str) -> Optional[paramiko.SSHClient]:
    """Open an SSH connection to a client's server."""
    access = db.get_server_access(client_id)
    if not access or not access.get("host") or not access.get("ssh_key"):
        logger.warning("[SSH] %s: pas d'accès configuré", client_id)
        return None

    host = access["host"]
    port = access.get("port", 22)
    user = access.get("user", "root")
    key_pem = access.get("ssh_key", "")

    try:
        key = paramiko.RSAKey.from_private_key(io.StringIO(key_pem))
    except paramiko.SSHException:
        try:
            key = paramiko.Ed25519Key.from_private_key(io.StringIO(key_pem))
        except paramiko.SSHException:
            logger.error("[SSH] %s: clé invalide (ni RSA ni Ed25519)", client_id)
            return None

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            hostname=host,
            port=port,
            username=user,
            pkey=key,
            timeout=DEFAULT_TIMEOUT,
            banner_timeout=10,
        )
        logger.info("[SSH] %s: connecté à %s@%s:%d", client_id, user, host, port)
        return client
    except Exception as e:
        logger.warning("[SSH] %s: échec connexion %s: %s", client_id, host, e)
        return None


def run_commands(client: paramiko.SSHClient, commands: list[str]) -> str:
    """Run multiple commands over SSH and return combined output."""
    results = []
    for cmd in commands:
        try:
            _, stdout, stderr = client.exec_command(cmd, timeout=DEFAULT_TIMEOUT)
            out = stdout.read().decode("utf-8", errors="replace").strip()
            err = stderr.read().decode("utf-8", errors="replace").strip()
            if out:
                results.append(f"$ {cmd}\n{out}")
            if err:
                results.append(f"$ {cmd} (stderr)\n{err}")
        except Exception as e:
            results.append(f"$ {cmd}\n[ERREUR] {e}")
    return "\n\n".join(results)


# ─── Diagnostic ──────────────────────────────────────────────────────────

def diagnose(client_id: str, custom_commands: Optional[list[str]] = None) -> dict:
    """Run full diagnostic on a client's server via SSH.

    Returns structured results ready for Nexus-Debug processing.
    """
    client = connect(client_id)
    if not client:
        return {"success": False, "error": "Connexion SSH impossible. Vérifiez les accès configurés."}

    try:
        commands = custom_commands or DEFAULT_COMMANDS
        output = run_commands(client, commands)

        # Extract summary for quick view
        summary = _extract_summary(output)

        return {
            "success": True,
            "host": db.get_server_access(client_id).get("host", "?"),
            "summary": summary,
            "output": output,
            "commands_executed": commands,
        }
    except Exception as e:
        logger.error("[SSH] %s: erreur diagnostic: %s", client_id, e)
        return {"success": False, "error": str(e)}
    finally:
        client.close()


def _extract_summary(output: str) -> dict:
    """Extract key metrics from raw SSH output."""
    summary = {}

    # Hostname
    m = re.search(r"^([a-zA-Z0-9_-]+)$", output, re.MULTILINE)
    if m:
        summary["hostname"] = m.group(1)

    # Uptime
    m = re.search(r"up\s+(.+?\d+\s+(?:user|users))", output)
    if m:
        summary["uptime"] = m.group(1).strip()

    # Memory
    m = re.search(r"Mem:\s+([\d.]+[GMTK]?).*?([\d.]+[GMTK]?).*?([\d.]+[GMTK]?)", output)
    if m:
        summary["memory"] = {"total": m.group(1), "used": m.group(2), "free": m.group(3)}

    # Disk
    m = re.search(r"/\s+([\d.]+[GMTKP]?).*?([\d.]+[GMTKP]?).*?([\d.]+[GMTKP]?).*?(\d+)%", output)
    if m:
        summary["disk"] = {"size": m.group(1), "used": m.group(2), "avail": m.group(3), "pct": m.group(4)}

    # Docker
    docker_lines = [l for l in output.split("\n") if "Up " in l or "Exited " in l]
    if docker_lines:
        summary["containers"] = docker_lines[:10]

    # Error count in logs
    error_count = len(re.findall(r"error|Error|ERROR|Traceback|FATAL", output))
    if error_count > 0:
        summary["error_mentions"] = error_count

    return summary


# ─── Custom command ──────────────────────────────────────────────────────

def run_custom_command(client_id: str, command: str) -> dict:
    """Run a single custom command on the client's server."""
    client = connect(client_id)
    if not client:
        return {"success": False, "error": "Connexion SSH impossible"}

    try:
        _, stdout, stderr = client.exec_command(command, timeout=DEFAULT_TIMEOUT)
        out = stdout.read().decode("utf-8", errors="replace").strip()
        err = stderr.read().decode("utf-8", errors="replace").strip()
        return {
            "success": True if out else False,
            "command": command,
            "stdout": out,
            "stderr": err,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        client.close()


"""
══════════════════════════════════════════════════════════════════════════
OPTION C — WATCH-AGENT (alternative future)
══════════════════════════════════════════════════════════════════════════

Quand le client n'a pas de SSH (Firewall/NAT, Cloudflare Tunnel, etc.) :

1. watch-agent.py — tourne sur le serveur client (systemd ou Docker)
   → se connecte AU Hub (pas l'inverse, traverse les firewalls)
   → reçoit les tâches de diagnostic sur une WebSocket ou polling
   → exécute les commandes localement
   → renvoie les résultats

2. Architecture :
   ┌──────────────────────┐          ┌──────────────────────┐
   │  Serveur Client      │          │  Nexus Hub            │
   │                      │─────────►│                       │
   │  watch-agent         │ SSE/WS   │  /agent/register      │
   │  pip install watcher │◄─────────│  /agent/task/:id      │
   │                      │  tasks   │  /agent/result/:id    │
   └──────────────────────┘          └──────────────────────┘

3. watch-agent remplace l'appel SSH ici.
   Au lieu de paramiko.SSHClient().connect(...) :
     → Le hub envoie la tâche via Redis ou WebSocket
     → L'agent exécute et répond
     → Même format de retour que run_commands()

4. watch-agent enregistre son fingerprint au démarrage
   → le hub vérifie que c'est bien le bon serveur

5. watch-agent tourne en boucle :
   while True:
       task = hub.poll_task(agent_id)
       if task:
           result = execute(task.commands)
           hub.submit_result(task.id, result)
       time.sleep(10)

══════════════════════════════════════════════════════════════════════════
"""
