"""
nexus_state.py — État partagé et schémas Pydantic
"""
from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime


class BugState(BaseModel):
    """État global partagé entre Nexus et tous ses outils."""

    # Identité de la mission
    mission_id: str
    brief:      str
    timestamp:  str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    # Contexte technique (enrichi au fur et à mesure)
    priority:       str        = "P2"
    langage:        str        = ""
    suspect_files:  list[str]  = []
    error_message:  str        = ""
    stack_trace:    str        = ""

    # Résultats accumulés des outils appelés
    tool_results:   list[dict] = []

    # Mémoire de raisonnement d'Nexus (trace des pensées)
    reasoning_steps: list[str] = []

    # Résultat final consolidé
    final_result: dict | None = None

    # Flags de contrôle
    escalate:    bool = False
    done:        bool = False


class ToolResult(BaseModel):
    """Structure standard de retour pour tous les sous-agents."""
    tool_name:   str
    status:      str            # "success" | "partial" | "error"
    data:        dict
    confidence:  float          = 0.0
    summary:     str            = ""
    needs_more:  bool           = False   # Nexus doit-il creuser ?
    escalate:    bool           = False   # Bug trop complexe ?
