"""\nNexus-Debug — Config Loader.\n\n📌 GARDÉ POUR USAGE FUTUR — pas encore branché.\nCharge la configuration depuis nexus-config.yaml.\nPriorité : YAML > variables d'env > valeurs par défaut.\n\nUsage:\n    from nexus_config import config\n    print(config.llm.provider)   # "deepseek"\n    print(config.api.port)       # 9001\n    print(config.capture.url)    # "http://nexus-debug:9001"\n\nQuand branché, remplacer les os.getenv() éparpillés par config.llm.api_keys.deepseek\netc. Voir nexus_api.py:lifespan() pour les vars à migrer.\n"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

# ── Chemins de config (par ordre de priorité) ────────────────────────────────
CONFIG_PATHS = [
    Path.cwd() / "nexus-config.yaml",
    Path.home() / ".nexus" / "nexus-config.yaml",
    Path("/etc/nexus/nexus-config.yaml"),
    Path(__file__).parent / "nexus-config.yaml",
]


class ConfigDict(dict):
    """Dict-like object with attribute access (config.key.subkey)."""

    def __getattr__(self, key: str) -> Any:
        try:
            val = self[key]
            if isinstance(val, dict):
                return ConfigDict(val)
            return val
        except KeyError:
            raise AttributeError(f"Config has no key '{key}'")

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value

    def merge(self, other: dict) -> None:
        """Merge another dict recursively (deep update)."""
        for key, val in other.items():
            if key in self and isinstance(self[key], dict) and isinstance(val, dict):
                ConfigDict(self[key]).merge(val)
            else:
                self[key] = val


# ── Valeurs par défaut ───────────────────────────────────────────────────────
DEFAULTS: dict[str, Any] = {
    "version": "3.0.0",
    "llm": {
        "provider": "deepseek",
        "model": "deepseek-chat",
        "api_keys": {
            "deepseek": "",
            "openai": "",
            "openrouter": "",
            "anthropic": "",
        },
    },
    "api": {
        "host": "0.0.0.0",
        "port": 9001,
        "key": "",
        "cors_origin": "http://localhost:9001",
        "rate_limit": "10/minute",
    },
    "storage": {
        "db_path": "/data/nexus/nexus.db",
        "kb_path": "/data/nexus/kb/nexus_kb.yaml",
        "reports_dir": "/data/nexus/reports",
        "feedback_path": "/data/nexus/feedback/nexus_feedback.yaml",
    },
    "codebase": {
        "path": "/app/workspace",
        "max_brief_length": 5000,
    },
    "notifications": {
        "github_webhook_secret": "",
        "github_token": "",
        "slack_webhook_url": "",
    },
    "capture": {
        "url": "http://nexus-debug:9001",
        "enabled": True,
        "project": "unknown",
        "version": "0.0.0",
        "capture_4xx": False,
        "max_breadcrumbs": 50,
    },
    "agent": {
        "temperature": 0.1,
        "max_tokens": 4096,
        "max_retries": 3,
        "interactive": False,
    },
    "monitoring": {
        "prometheus_enabled": True,
        "grafana_password": "CHANGE_ME",
    },
}


def _load_yaml(path: Path) -> dict[str, Any] | None:
    """Charge un fichier YAML, retourne None si inexistant."""
    if not path.exists():
        return None
    try:
        with open(path) as fh:
            data = yaml.safe_load(fh) or {}
            return data
    except (yaml.YAMLError, OSError):
        return None


def _env_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    """Applique les overrides depuis les variables d'env."""
    env_map = {
        "NEXUS_LLM_PROVIDER": ("llm", "provider"),
        "NEXUS_MODEL": ("llm", "model"),
        "DEEPSEEK_API_KEY": ("llm", "api_keys", "deepseek"),
        "OPENAI_API_KEY": ("llm", "api_keys", "openai"),
        "OPENROUTER_API_KEY": ("llm", "api_keys", "openrouter"),
        "ANTHROPIC_API_KEY": ("llm", "api_keys", "anthropic"),
        "NEXUS_API_KEY": ("api", "key"),
        "NEXUS_API_HOST": ("api", "host"),
        "NEXUS_API_PORT": ("api", "port"),
        "NEXUS_CORS_ORIGIN": ("api", "cors_origin"),
        "NEXUS_RATE_LIMIT": ("api", "rate_limit"),
        "NEXUS_DB_PATH": ("storage", "db_path"),
        "NEXUS_KB_PATH": ("storage", "kb_path"),
        "NEXUS_REPORTS_DIR": ("storage", "reports_dir"),
        "NEXUS_FEEDBACK_PATH": ("storage", "feedback_path"),
        "NEXUS_CODEBASE_PATH": ("codebase", "path"),
        "NEXUS_MAX_BRIEF_LENGTH": ("codebase", "max_brief_length"),
        "GITHUB_WEBHOOK_SECRET": ("notifications", "github_webhook_secret"),
        "GITHUB_TOKEN": ("notifications", "github_token"),
        "SLACK_WEBHOOK_URL": ("notifications", "slack_webhook_url"),
        "NEXUS_CAPTURE_URL": ("capture", "url"),
        "NEXUS_CAPTURE_ENABLED": ("capture", "enabled"),
        "NEXUS_CAPTURE_PROJECT": ("capture", "project"),
        "NEXUS_CAPTURE_VERSION": ("capture", "version"),
        "GF_SECURITY_ADMIN_PASSWORD": ("monitoring", "grafana_password"),
    }

    for env_var, keys in env_map.items():
        val = os.getenv(env_var)
        if val is not None and val != "":
            # Naviguer jusqu'au bon endroit
            d = raw
            for k in keys[:-1]:
                if k not in d:
                    d[k] = {}
                d = d[k]
            # Typer automatiquement (int, bool, str)
            raw_val: Any = val
            if val.lower() in ("true", "1", "yes"):
                raw_val = True
            elif val.lower() in ("false", "0", "no"):
                raw_val = False
            elif val.isdigit():
                raw_val = int(val)
            d[keys[-1]] = raw_val

    return raw


def load_config() -> ConfigDict:
    """Charge la configuration : YAML > env > defaults."""
    config = ConfigDict(DEFAULTS)

    # Charger le premier YAML trouvé
    for path in CONFIG_PATHS:
        data = _load_yaml(path)
        if data is not None:
            config.merge(data)
            break

    # Appliquer les overrides env (priorité max)
    config = ConfigDict(_env_overrides(dict(config)))

    return config


# Singleton global
config: ConfigDict = load_config()
