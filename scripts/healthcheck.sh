#!/bin/bash
# =============================================================================
# Healthcheck — Écosystème Xaliloulah
# Usage : ./scripts/healthcheck.sh
# Vérifie que tous les services critiques tournent.
# =============================================================================

echo "🌅 Santé écosystème Xaliloulah — $(date '+%d/%m/%Y %H:%M')"
echo ""

total=0
ok=0
ko=0

check() {
    local name="$1"
    local addr="$2"
    local timeout="${3:-5}"
    total=$((total + 1))

    code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout "$timeout" "$addr" 2>/dev/null)
    code="${code:-000}"
    # Nettoyer : ne garder que les 3 premiers chiffres
    code="${code:0:3}"

    if [ "$code" = "000" ]; then
        echo "❌  $name — INJOIGNABLE ($addr)"
        ko=$((ko + 1))
    elif [ "$code" -ge 200 ] && [ "$code" -lt 400 ]; then
        echo "✅  $name — HTTP $code"
        ok=$((ok + 1))
    else
        echo "⚠️  $name — HTTP $code (anormal)"
        ko=$((ko + 1))
    fi
}

# ── Projets ──────────────────────────────────────────────────────────────────
check "BELLISSIMA"          "http://localhost:3031"
check "Khady-Consulting"    "http://localhost:8000"
check "ProjecSen API"       "http://localhost:5001/health"
check "ProjecSen Front"     "http://localhost:3001"
check "Nexus-debug"         "http://localhost:9001/health"

echo ""
echo "━━━ Bilan ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅  $ok / $total services OK"
if [ "$ko" -gt 0 ]; then echo "❌  $ko / $total services KO"; fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

exit "$ko"
