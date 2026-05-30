"""
orchestrateur_integration.py — Comment Orchestrateur appelle Nexus agentique
"""
import asyncio
import json
from nexus_agent import nexus_run


async def orchestrateur_delegate_to_nexus(
    brief: str,
    priority: str = "P2",
    project: str = "",
    langage: str = "",
    fichier: str = "",
    erreur: str = "",
    stack: str = ""
) -> dict:
    """
    Orchestrateur construit le brief et délègue à Nexus.
    Nexus prend la main, raisonne librement, résout le bug.
    """
    # Construction du brief structuré
    mission_brief = f"""
PROJET   : {project or 'Non précisé'}
LANGAGE  : {langage or 'À détecter'}
FICHIER  : {fichier or 'À identifier'}
PRIORITÉ : {priority}

DESCRIPTION :
{brief}

ERREUR EXACTE :
{erreur or 'Voir description'}

STACK TRACE :
{stack or 'Non fournie'}
    """.strip()

    print(f"\n[Orchestrateur] Délégation à Nexus-debug...")
    print(f"[Orchestrateur] Priorité : {priority}")

    # Appel agentique — Nexus fait le reste
    result = await nexus_run(
        brief=mission_brief,
        mission_id=f"DBG-{project[:4].upper() if project else 'AGNT'}-001"
    )

    # Synthèse pour l'utilisateur
    status_emoji = {
        "fixed":   "✅",
        "partial": "⚠️",
        "escalate": "🚨",
        "error":   "❌"
    }.get(result.get("status", "error"), "❓")

    summary = f"""
{status_emoji} Mission Nexus terminée
{'─'*40}
Statut    : {result.get('status', 'inconnu')}
Cause     : {result.get('root_cause', 'N/A')[:100]}
Fix       : {result.get('fix_summary', 'N/A')[:100]}
Confiance : {result.get('confidence', 0)*100:.0f}%
Outils    : {', '.join(result.get('tools_used', []))}
    """.strip()

    print(f"\n[Orchestrateur] Rapport de débogage :\n{summary}")
    return result


# ─── Exemple d'usage ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    asyncio.run(orchestrateur_delegate_to_nexus(
        brief="L'API de profil utilisateur plante quand on n'est pas connecté",
        priority="P1",
        project="fisspro-app",
        langage="Python 3.11",
        fichier="src/auth/user.py",
        erreur="AttributeError: 'NoneType' object has no attribute 'id'",
        stack="File 'src/auth/user.py', line 42, in get_user_profile\n  return user.id"
    ))
