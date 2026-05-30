#!/usr/bin/env bash
# =============================================================================
# nexus-restore.sh — Restore volumes Docker Nexus-Debug depuis un backup
# =============================================================================
set -euo pipefail

BACKUP_PATH="${1:-}"
if [ -z "${BACKUP_PATH}" ]; then
    echo "❌ Usage: bash nexus-restore.sh <chemin_backup>"
    echo "   Ex: bash nexus-restore.sh ./backups/nexus-backup-20260530_143000"
    exit 1
fi

if [ ! -d "${BACKUP_PATH}" ]; then
    echo "❌ Backup introuvable : ${BACKUP_PATH}"
    exit 1
fi

echo "♻️  Nexus-Debug — Restauration depuis ${BACKUP_PATH}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Vérifier que les containers sont arrêtés
if docker ps --format '{{.Names}}' | grep -q nexus; then
    echo "⚠️  Des containers nexus tournent encore."
    echo "   Arrête-les d'abord : docker compose down"
    exit 1
fi

# Restauration des volumes
for archive in "${BACKUP_PATH}"/*.tar.gz; do
    volume_name=$(basename "${archive}" .tar.gz)
    echo "   → Restauration ${volume_name}..."
    docker run --rm \
        -v "${volume_name}":/target \
        -v "$(realpath "${BACKUP_PATH}")":/backup \
        alpine sh -c "rm -rf /target/* /target/.* 2>/dev/null; tar xzf /backup/$(basename "${archive}") -C /target" || \
        echo "   ⚠️  Volume ${volume_name} non trouvé, création..."
done

echo ""
echo "✅ Restauration terminée. Lance : docker compose up -d"
