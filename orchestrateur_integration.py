"""
orchestrateur_integration.py — Comment Orchestrateur appelle Nexus agentique
"""

from __future__ import annotations

import asyncio

from loguru import logger

from nexus_agent import nexus_run


async def orchestrateur_delegate_to_nexus(
    brief: str,
    priority: str = "P2",
    project: str = "",
    langage: str = "",
    fichier: str = "",
    erreur: str = "",
    stack: str = "",
) -> dict:
    """
    Orchestrateur construit le brief et délègue à Nexus.
    Nexus prend la main, raisonne librement, résout le bug.
    """
    # Construction du brief structuré
    mission_brief = f"""
PROJET   : {project or "Non précisé"}
LANGAGE  : {langage or "À détecter"}
FICHIER  : {fichier or "À identifier"}
PRIORITÉ : {priority}

DESCRIPTION :
{brief}

ERREUR EXACTE :
{erreur or "Voir description"}

STACK TRACE :
{stack or "Non fournie"}
    """.strip()


    logger.info("Délégation à Nexus — priorité {}", priority)

    # Appel agentique — Nexus fait le reste
    result = await nexus_run(
        brief=mission_brief, mission_id=f"DBG-{project[:4].upper() if project else 'AGNT'}-001"
    )

    # Synthèse pour l'utilisateur
    status_emoji = {"fixed": "✅", "partial": "⚠️", "escalate": "🚨", "error": "❌"}.get(
        result.get("status", "error"), "❓"
    )

    f"""
{status_emoji} Mission Nexus terminée
{"─" * 40}
Statut    : {result.get("status", "inconnu")}
Cause     : {result.get("root_cause", "N/A")[:100]}
Fix       : {result.get("fix_summary", "N/A")[:100]}
Confiance : {result.get("confidence", 0) * 100:.0f}%
Outils    : {", ".join(result.get("tools_used", []))}
    """.strip()

    logger.info("Rapport de débogage reçu — statut: {}", result.get("status", "?"))
    return result


# ─── Exemple d'usage ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    asyncio.run(
        orchestrateur_delegate_to_nexus(
            brief="L'API de profil utilisateur plante quand on n'est pas connecté",
            priority="P1",
            project="fisspro-app",
            langage="Python 3.11",
            fichier="src/auth/user.py",
            erreur="AttributeError: 'NoneType' object has no attribute 'id'",
            stack="File 'src/auth/user.py', line 42, in get_user_profile\n  return user.id",
        )
    )
