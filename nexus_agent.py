"""
nexus_agent.py — Nexus comme agent ReAct avec LangGraph
Switché de Anthropic → DeepSeek V4 Pro (OpenAI-compatible)
Nexus raisonne librement, choisit ses outils, boucle jusqu'à résolution.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Annotated, Any

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from loguru import logger
from pydantic import BaseModel

from nexus_tools import NEXUS_TOOLS


# ─── État de l'agent ─────────────────────────────────────────────────────────
class NexusAgentState(BaseModel):
    """
    État LangGraph d'Nexus.
    messages = historique complet du raisonnement (auto-accumulé par add_messages).
    """

    messages: Annotated[list[AnyMessage], add_messages]
    mission_id: str = ""
    priority: str = "P2"
    escalate: bool = False


# ─── System prompt d'Nexus ───────────────────────────────────────────────────
NEXUS_SYSTEM_PROMPT = """Tu es Nexus-debug, expert en débogage et orchestrateur agentique.

Tu reçois un brief de bug de Orchestrateur. Tu dois le résoudre en utilisant tes outils de façon AUTONOME et INTELLIGENTE.

Tes outils disponibles :
- tool_triage          : toujours appeler en premier — classifie le bug et guide la stratégie
- tool_static_analysis : analyse statique du code (linters, AST)
- tool_security_scan   : scan sécurité (OWASP, CVE) — uniquement si pertinent
- tool_runtime_debug   : débogage dynamique, confirmation cause racine
- tool_perf_analysis   : analyse perf/mémoire — uniquement si symptômes présents
- tool_fix_bug         : applique la correction — UNIQUEMENT après cause racine confirmée
- tool_generate_tests  : génère les tests de non-régression — après le fix
- tool_write_postmortem: rédige le post-mortem — en dernier

PRINCIPES DE RAISONNEMENT AGENTIQUE :
1. Raisonne à voix haute AVANT chaque appel d'outil (Thought: ...)
2. Appelle l'outil le plus pertinent selon ce que tu sais DÉJÀ
3. Observe le résultat et ajuste ta stratégie
4. Si un outil dit needs_more=true → creuse davantage
5. Si escalate=true → arrête et remonte à Orchestrateur
6. Tu peux appeler le MÊME outil deux fois si nécessaire
7. Tu peux SAUTER des étapes si le bug est simple et évident
8. Ne lance PAS tool_fix_bug sans cause racine confirmée à >= 0.80 de confiance
9. Pour les bugs simples (syntaxe, import) → triage + static + fix + tests suffisent
10. Pour les bugs complexes (race condition, perf, sécurité) → sois plus exhaustif

FORMAT DE RÉPONSE FINALE (quand tu as terminé) :
Retourne un JSON structuré avec :
{
  "mission_id": "...",
  "status": "fixed|partial|escalate",
  "root_cause": "...",
  "files_modified": [...],
  "fix_summary": "...",
  "tests_added": [...],
  "confidence": 0.0-1.0,
  "tools_used": [...],
  "reasoning_summary": "résumé de ta démarche",
  "prevention": "...",
  "needs_human": false
}"""


# ─── Configuration DeepSeek ───────────────────────────────────────────────────
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
NEXUS_MODEL = os.getenv("NEXUS_MODEL", "deepseek-chat")

if not DEEPSEEK_API_KEY:
    logger.warning("DEEPSEEK_API_KEY non définie — l'agent échouera au runtime")


def _get_llm() -> ChatOpenAI:
    """Crée le LLM DeepSeek V4 Pro avec les outils liés."""
    return ChatOpenAI(
        model=NEXUS_MODEL,
        api_key=DEEPSEEK_API_KEY or None,
        base_url=DEEPSEEK_BASE_URL,
        max_tokens=4096,
        temperature=0.1,
    ).bind_tools(NEXUS_TOOLS)


# ─── Construction de l'agent ──────────────────────────────────────────────────
def build_nexus_agent(_memory_path: str | None = None) -> StateGraph:
    """
    Construit l'agent agentique Nexus avec LangGraph.
    Utilise le pattern ReAct : Reason -> Act -> Observe -> Repeat.
    """
    llm = _get_llm()

    # Nœud ToolNode — exécute les outils appelés par Nexus
    tool_node = ToolNode(NEXUS_TOOLS)

    # ── Nœud principal : Nexus raisonne ─────────────────────────────────────
    def nexus_node(state: NexusAgentState) -> dict[str, Any]:
        messages = [SystemMessage(content=NEXUS_SYSTEM_PROMPT)] + state.messages
        response = llm.invoke(messages)
        return {"messages": [response]}

    # ── Routage conditionnel ──────────────────────────────────────────────────
    def should_continue(state: NexusAgentState) -> str:
        last_message = state.messages[-1]

        # Si le dernier message contient des tool_calls → continuer
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"

        # Sinon → Nexus a terminé son raisonnement
        return "end"

    # ── Construction du graphe ────────────────────────────────────────────────
    graph = StateGraph(NexusAgentState)

    graph.add_node("nexus", nexus_node)
    graph.add_node("tools", tool_node)

    graph.set_entry_point("nexus")

    graph.add_conditional_edges("nexus", should_continue, {"tools": "tools", "end": END})
    # Après exécution d'un outil → retour à Nexus pour le prochain raisonnement
    graph.add_edge("tools", "nexus")

    # Mémoire persistante
    memory = MemorySaver()

    return graph.compile(checkpointer=memory)


# ─── Fonction d'entrée principale ────────────────────────────────────────────
async def nexus_run(brief: str, mission_id: str = None) -> dict:
    """
    Point d'entrée pour Orchestrateur.
    Lance Nexus sur un bug et retourne le résultat final.
    """
    if not mission_id:
        mission_id = f"DBG-{uuid.uuid4().hex[:8].upper()}"

    agent = build_nexus_agent()

    initial_state = {
        "messages": [
            HumanMessage(
                content=f"""
MISSION ID : {mission_id}

BRIEF DE ORCHESTRATEUR :
{brief}

Lance ton analyse agentique. Raisonne, utilise tes outils, et résous ce bug.
"""
            )
        ],
        "mission_id": mission_id,
        "priority": "P2",
        "escalate": False,
    }

    config = {"configurable": {"thread_id": mission_id}}

    # Exécution avec streaming pour observer le raisonnement en temps réel
    final_state: dict[str, Any] | None = None
    logger.info("Mission {} — lancement agent ReAct", mission_id)

    async for event in agent.astream(initial_state, config):
        for node_name, node_output in event.items():
            if node_name == "nexus":
                msgs = node_output.get("messages", [])
                for msg in msgs:
                    if hasattr(msg, "content") and msg.content:
                        content = str(msg.content)[:200]
                        if content.strip():
                            logger.debug("[Nexus] {}", content)
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        for tc in msg.tool_calls:
                            logger.info("  → {} ({})", tc["name"], tc.get("id", ""))
            elif node_name == "tools":
                msgs = node_output.get("messages", [])
                for msg in msgs:
                    logger.debug("  ← {}...", str(msg.content)[:100])
        final_state = node_output

    # Extraction du résultat final depuis le dernier message
    if final_state:
        last_msgs = final_state.get("messages", [])
        if last_msgs:
            last_content = last_msgs[-1].content
            try:
                if isinstance(last_content, str):
                    start = last_content.find("{")
                    end = last_content.rfind("}") + 1
                    if start >= 0 and end > start:
                        return json.loads(last_content[start:end])
            except json.JSONDecodeError:
                pass
            return {"status": "done", "raw_output": str(last_content)[:500]}

    return {"status": "error", "mission_id": mission_id}


# ─── CLI pour test rapide ─────────────────────────────────────────────────────
if __name__ == "__main__":
    import asyncio
    import sys

    logger.remove()
    logger.add(sys.stderr, level="INFO")

    brief_test = (
        sys.argv[1]
        if len(sys.argv) > 1
        else """
    PROJET   : test-app
    LANGAGE  : Python 3.11
    FICHIER  : src/main.py
    ERREUR   : AttributeError: 'NoneType' object has no attribute 'id'
    STACK    : File "src/main.py", line 42, in get_user_profile
               return user.id
    PRIORITÉ : P1
    """
    )

    result = asyncio.run(nexus_run(brief_test))
