"""Test the full callback processing pipeline."""
import json
from nexus_hub.notify import generate_ai_report
from nexus_hub import db

# Simuler le traitement d'un callback "report:98ed52af:2"
captures = db.get_client_captures("98ed52af", 50)
cap = next((c for c in captures if str(c["id"]) == "2"), None)
if cap:
    print(f"✅ Capture #{cap['id']} trouvée: {cap['error_type']}")
    report = generate_ai_report(cap)
    print(f"Rapport généré ({len(report)} chars):")
    print(report)
else:
    print("❌ Capture 2 non trouvée")
    for c in captures:
        print(f"   Disponible: #{c['id']} {c['error_type']}")

print()

# Tester 'detail'
cap = next((c for c in captures if str(c["id"]) == "2"), None)
if cap:
    answer = (
        f"🔍 Détails #2\n"
        f"• Type : {cap['error_type']}\n"
        f"• Message : {cap['error_message'][:200] or '?'}\n"
        f"• URL : {cap['url'] or '/'}\n"
        f"• Status : {cap.get('nexus_status', 'pending')}\n"
        f"• {cap['created_at']}"
    )
    print(f"Détail ({len(answer)} chars):")
    print(answer)
