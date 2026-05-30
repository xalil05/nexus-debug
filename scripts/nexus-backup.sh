#!/usr/bin/env bash
# =============================================================================
# nexus-backup.sh — Backup volumes Docker Nexus-Debug
# =============================================================================
set -euo pipefail

BACKUP_DIR="${1:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="${BACKUP_DIR}/nexus-backup-${TIMESTAMP}"

echo "📦 Nexus-Debug — Backup ${TIMESTAMP}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Création du répertoire
mkdir -p "${BACKUP_PATH}"

# Backup volumes Docker
echo "💾 Sauvegarde des volumes..."
for volume in nexus_kb nexus_reports nexus_feedback nexus_db nexus_prometheus nexus_grafana; do
    echo "   → ${volume}..."
    docker run --rm \
        -v "${volume}":/source \
        -v "$(realpath "${BACKUP_PATH}")":/backup \
        alpine tar czf "/backup/${volume}.tar.gz" -C /source . 2>/dev/null || \
        echo "   ⚠️  Volume ${volume} vide ou inexistant, ignoré"
done

# Backup docker-compose et configs
echo "📋 Sauvegarde des configs..."
cp -r docker-compose.yml docker/ "${BACKUP_PATH}/" 2>/dev/null || true

# Résumé
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Backup terminé : ${BACKUP_PATH}"
ls -lh "${BACKUP_PATH}"/
echo ""
echo "# Restauration :"
echo "bash nexus-restore.sh ${BACKUP_PATH}"
