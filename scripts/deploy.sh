#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Déploiement one-command Nexus-Debug
# =============================================================================
set -euo pipefail

echo "🚀 Nexus-Debug — Déploiement"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. Vérifier les prérequis
echo "🔍 Vérification des prérequis..."
command -v docker >/dev/null 2>&1 || { echo "❌ Docker manquant"; exit 1; }
command -v docker compose >/dev/null 2>&1 || { echo "❌ docker compose manquant"; exit 1; }

# 2. Vérifier .env
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "⚠️  .env absent. Copie depuis .env.example..."
        cp .env.example .env
        echo "   🔧 Édite .env avec ta clé DEEPSEEK_API_KEY puis relance"
    else
        echo "❌ .env et .env.example manquants"
        exit 1
    fi
fi

# 3. Vérifier DEEPSEEK_API_KEY
if grep -q "DEEPSEEK_API_KEY=\"\"" .env 2>/dev/null || ! grep -q "DEEPSEEK_API_KEY" .env 2>/dev/null; then
    echo "⚠️  DEEPSEEK_API_KEY non configurée dans .env"
    echo "   Ajoute : DEEPSEEK_API_KEY=sk-votre_clé"
    echo "   (Le service démarre quand même mais ne pourra pas faire de debug)"
fi

# 4. Builder et lancer
echo "🐳 Build Docker..."
docker compose build --quiet 2>/dev/null || docker compose build

echo "▶️  Lancement des services..."
docker compose up -d

# 5. Attendre le healthcheck
echo "⏳ Attente du démarrage..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:9001/health >/dev/null 2>&1; then
        echo ""
        echo "✅ Nexus-Debug opérationnel !"
        echo ""
        echo "   🌐 API      : http://localhost:9001"
        echo "   📈 Prometheus : http://localhost:9090"
        echo "   📉 Grafana    : http://localhost:3000  (admin / nexus2026)"
        echo "   🩺 Health     : curl http://localhost:9001/health"
        exit 0
    fi
    sleep 1
done

echo ""
echo "⚠️  Timeout — Vérifie les logs : docker compose logs nexus"
exit 1
