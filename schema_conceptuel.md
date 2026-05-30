# Schéma Conceptuel — nexus-debug

## Architecture Agentique ReAct

```
Bug signalé
    │
    ▼
┌────────────────────────────────────────────────┐
│                                                │
│           nexus-debug (ReAct Brain)             │
│                                                │
│   ┌─────────────────────────────────────────┐  │
│   │  Boucle de raisonnement :               │  │
│   │                                         │  │
│   │  Thought → Action → Observation → ...   │  │
│   │                                         │  │
│   │  À chaque étape, le cerveau décide :    │  │
│   │  • Quel outil/agent appeler             │  │
│   │  • Dans quel ordre                      │  │
│   │  • S'il faut rappeler un agent          │  │
│   │  • S'il peut s'arrêter                  │  │
│   └──────────────┬──────────────────────────┘  │
└──────────────────┼─────────────────────────────┘
                   │
     ┌─────────────┼─────────────┐
     │             │             │
     ▼             ▼             ▼
┌─────────┐  ┌─────────┐  ┌─────────┐
│ nexus-  │  │ nexus-  │  │ nexus-  │
│ triage  │  │ static  │  │ runtime │
└─────────┘  └─────────┘  └─────────┘
     │             │             │
     ▼             ▼             ▼
┌─────────┐  ┌─────────┐  ┌─────────┐
│ nexus-  │  │ nexus-  │  │ nexus-  │
│ security│  │  perf   │  │  fix    │
└─────────┘  └─────────┘  └─────────┘
     │             │             │
     ▼             ▼             ▼
┌─────────┐  ┌─────────┐
│ nexus-  │  │ nexus-  │
│   qa    │  │postmortem│
└─────────┘  └─────────┘
```

### Exemple : Bug simple (syntaxe Python)

nexus-debug appelle nexus-triage
    → "Erreur de syntaxe Python ligne 42"
nexus-debug appelle nexus-static
    → "SyntaxError: unmatched ')' in user.py:42"
nexus-debug appelle nexus-fix DIRECTEMENT
    → ✅ Résolu en 3 appels

### Exemple : Bug complexe (race condition + fuite mémoire)

nexus-debug appelle nexus-triage
    → "Crash intermittent, semble lié aux threads"
nexus-debug appelle nexus-runtime
    → stack trace partielle
nexus-debug appelle nexus-runtime (2ème fois avec plus de logs)
    → confirmation race condition
nexus-debug appelle nexus-perf
    → fuite mémoire détectée
nexus-debug revient à nexus-static
    → analyse du code concurrent
nexus-debug appelle nexus-fix
    → correction + tests
nexus-debug appelle nexus-qa
    → validation
nexus-debug appelle nexus-postmortem
    → mémorisation
