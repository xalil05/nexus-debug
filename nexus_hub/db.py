"""Nexus Hub — multi-tenant error capture service.

SQLite database for clients, captures, and notification configs.
Shares the Nexus-Debug diagnostic engine.
"""

import sqlite3
import uuid
import secrets
import hashlib
import json
import bcrypt
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


DB_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DB_DIR / "hub.db"


# ─── Schema ─────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS clients (
    client_id     TEXT PRIMARY KEY,
    email         TEXT UNIQUE NOT NULL,
    api_key       TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    project       TEXT NOT NULL DEFAULT '',
    plan          TEXT NOT NULL DEFAULT 'starter',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    client_id     TEXT PRIMARY KEY,
    telegram_chat TEXT DEFAULT '',
    whatsapp_phone TEXT DEFAULT '',
    slack_webhook TEXT DEFAULT '',
    updated_at    TEXT NOT NULL,
    FOREIGN KEY (client_id) REFERENCES clients(client_id)
);

CREATE TABLE IF NOT EXISTS captures (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id     TEXT NOT NULL,
    error_type    TEXT NOT NULL,
    error_message TEXT NOT NULL,
    stack_trace   TEXT DEFAULT '',
    url           TEXT DEFAULT '',
    method        TEXT DEFAULT '',
    status_code   INTEGER DEFAULT 500,
    version       TEXT DEFAULT '',
    environment   TEXT DEFAULT '',
    nexus_task_id TEXT DEFAULT '',
    nexus_status  TEXT DEFAULT 'pending',
    resolved      INTEGER DEFAULT 0,
    created_at    TEXT NOT NULL,
    FOREIGN KEY (client_id) REFERENCES clients(client_id)
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS server_access (
    client_id         TEXT PRIMARY KEY,
    ssh_host          TEXT DEFAULT '',
    ssh_port          INTEGER DEFAULT 22,
    ssh_user          TEXT DEFAULT 'root',
    ssh_key_encrypted TEXT DEFAULT '',
    ssh_fingerprint   TEXT DEFAULT '',
    updated_at        TEXT NOT NULL,
    FOREIGN KEY (client_id) REFERENCES clients(client_id)
);

-- Admin settings
INSERT OR IGNORE INTO settings (key, value) VALUES ('hub_name', 'Nexus Watch');
INSERT OR IGNORE INTO settings (key, value) VALUES ('hub_version', '0.1.0');
"""


# ─── Database helpers ────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_password(password: str) -> str:
    """Hash a password with bcrypt (includes salt)."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _generate_api_key() -> str:
    return "sk-watch-" + secrets.token_hex(24)


# ─── Client operations ──────────────────────────────────────────────────────

def register_client(email: str, password: str, project: str = "") -> dict:
    """Register a new client. Returns client info or error."""
    conn = get_db()
    try:
        client_id = str(uuid.uuid4())[:8]
        api_key = _generate_api_key()
        now = _now()
        conn.execute(
            "INSERT INTO clients (client_id, email, api_key, password_hash, project, plan, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 'starter', ?, ?)",
            (client_id, email, api_key, _hash_password(password), project, now, now),
        )
        # Create empty notification config
        conn.execute(
            "INSERT INTO notifications (client_id, updated_at) VALUES (?, ?)",
            (client_id, now),
        )
        conn.commit()
        return {"success": True, "client_id": client_id, "api_key": api_key}
    except sqlite3.IntegrityError:
        return {"success": False, "error": "Email déjà utilisé"}
    finally:
        conn.close()


def authenticate(email: str, password: str) -> Optional[dict]:
    """Authenticate a client. Returns client data or None."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT client_id, email, api_key, project, plan, created_at, password_hash FROM clients WHERE email = ?",
            (email,),
        ).fetchone()
        if not row:
            return None
        stored_hash = row["password_hash"]
        # Detect hash format: bcrypt starts with $2, SHA-256 is 64 hex chars
        if stored_hash.startswith("$2"):
            if bcrypt.checkpw(password.encode(), stored_hash.encode()):
                return dict(row)
        else:
            # Legacy SHA-256 fallback — re-hash to bcrypt on success
            if hashlib.sha256(password.encode()).hexdigest() == stored_hash:
                new_hash = _hash_password(password)
                conn.execute("UPDATE clients SET password_hash=? WHERE email=?", (new_hash, email))
                conn.commit()
                return dict(row)
        return None
    finally:
        conn.close()


def get_client_by_api_key(api_key: str) -> Optional[dict]:
    """Find client by API key (for capture endpoint)."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT client_id, email, project, plan FROM clients WHERE api_key = ?",
            (api_key,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ─── Notification operations ────────────────────────────────────────────────

def update_notifications(client_id: str, telegram: str = "", whatsapp: str = "", slack: str = "") -> dict:
    """Update notification channels for a client."""
    conn = get_db()
    try:
        now = _now()
        conn.execute(
            "UPDATE notifications SET telegram_chat=?, whatsapp_phone=?, slack_webhook=?, updated_at=? WHERE client_id=?",
            (telegram, whatsapp, slack, now, client_id),
        )
        if conn.total_changes == 0:
            conn.execute(
                "INSERT INTO notifications (client_id, telegram_chat, whatsapp_phone, slack_webhook, updated_at) VALUES (?, ?, ?, ?, ?)",
                (client_id, telegram, whatsapp, slack, now),
            )
        conn.commit()
        return {"success": True}
    finally:
        conn.close()


def get_notifications(client_id: str) -> dict:
    """Get notification config for a client."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT telegram_chat, whatsapp_phone, slack_webhook FROM notifications WHERE client_id = ?",
            (client_id,),
        ).fetchone()
        if row:
            return dict(row)
        return {"telegram_chat": "", "whatsapp_phone": "", "slack_webhook": ""}
    finally:
        conn.close()


# ─── Capture operations ─────────────────────────────────────────────────────

def save_capture(client_id: str, data: dict, nexus_task_id: str = "") -> int:
    """Save an error capture and return its ID."""
    conn = get_db()
    try:
        error = data.get("error", {})
        req = data.get("request", {})
        now = _now()
        cur = conn.execute(
            "INSERT INTO captures (client_id, error_type, error_message, stack_trace, url, method, status_code, version, environment, nexus_task_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                client_id,
                error.get("type", "unknown"),
                error.get("message", "")[:2000],
                error.get("stack", "")[:8000],
                req.get("url", ""),
                req.get("method", ""),
                req.get("status_code", 500),
                data.get("version", ""),
                data.get("environment", ""),
                nexus_task_id,
                now,
            ),
        )
        capture_id = cur.lastrowid or 0
        conn.commit()
        return capture_id
    finally:
        conn.close()


def get_client_captures(client_id: str, limit: int = 50) -> list:
    """Get capture history for a client's dashboard."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, error_type, error_message, url, status_code, nexus_status, resolved, created_at "
            "FROM captures WHERE client_id = ? ORDER BY id DESC LIMIT ?",
            (client_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_client_stats(client_id: str) -> dict:
    """Get aggregate stats for a client."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT COUNT(*) as total, SUM(CASE WHEN resolved=1 THEN 1 ELSE 0 END) as resolved "
            "FROM captures WHERE client_id = ?",
            (client_id,),
        ).fetchone()
        total = row["total"] or 0
        resolved = row["resolved"] or 0
        rate = round((resolved / total * 100)) if total > 0 else 0
        return {"total": total, "resolved": resolved, "rate": rate, "open": total - resolved}
    finally:
        conn.close()


# ─── Server access (SSH) operations ──────────────────────────────────────────

import base64
from cryptography.fernet import Fernet

def _get_encryption_key() -> bytes:
    """Get or derive the master encryption key for SSH keys."""
    conn = get_db()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key='master_cipher_key'").fetchone()
        if row:
            return row["value"].encode()
        # Generate new key
        key = Fernet.generate_key()
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('master_cipher_key', ?)", (key.decode(),))
        conn.commit()
        return key
    finally:
        conn.close()


def _encrypt(plaintext: str) -> str:
    """Encrypt sensitive data (SSH keys)."""
    if not plaintext:
        return ""
    key = _get_encryption_key()
    f = Fernet(key)
    return f.encrypt(plaintext.encode()).decode()


def _decrypt(ciphertext: str) -> str:
    """Decrypt sensitive data."""
    if not ciphertext:
        return ""
    key = _get_encryption_key()
    f = Fernet(key)
    return f.decrypt(ciphertext.encode()).decode()


def save_server_access(client_id: str, host: str = "", port: int = 22, user: str = "root", ssh_key: str = "") -> dict:
    """Save SSH access info for a client."""
    conn = get_db()
    try:
        now = _now()
        encrypted_key = _encrypt(ssh_key) if ssh_key else ""
        conn.execute(
            "INSERT OR REPLACE INTO server_access (client_id, ssh_host, ssh_port, ssh_user, ssh_key_encrypted, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (client_id, host, port, user, encrypted_key, now),
        )
        conn.commit()
        return {"success": True}
    finally:
        conn.close()


def get_server_access(client_id: str) -> dict:
    """Get SSH access info for a client (decrypted key)."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT ssh_host, ssh_port, ssh_user, ssh_key_encrypted FROM server_access WHERE client_id = ?",
            (client_id,),
        ).fetchone()
        if not row:
            return {}
        return {
            "host": row["ssh_host"],
            "port": row["ssh_port"],
            "user": row["ssh_user"],
            "ssh_key": _decrypt(row["ssh_key_encrypted"]),
        }
    finally:
        conn.close()


# ─── Init on import ─────────────────────────────────────────────────────────

init_db()
