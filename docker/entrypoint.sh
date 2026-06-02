#!/bin/bash
# Nexus-Debug entrypoint — corrige les permissions des volumes au démarrage
set -e

# S'assurer que le user nexus peut écrire dans /data/nexus
# (les volumes Docker sont montés en root par défaut)
if [ -d "/data/nexus" ]; then
    echo "📁 Ajustement des permissions /data/nexus..."
    chown -R nexus:nexus /data/nexus 2>/dev/null || true
fi

# Lancer l'application
echo "🚀 Nexus-Debug v3.0 — démarrage..."
exec su-exec nexus uvicorn nexus_api:app --host 0.0.0.0 --port 9001 --log-level info
