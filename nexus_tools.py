"""
nexus_tools.py — Les 8 sous-agents comme outils LangGraph
Switché de Anthropic → DeepSeek V4 Pro (OpenAI-compatible)
Chaque tool = un sous-agent spécialisé qu'Nexus peut appeler librement.
"""
import json
import os
import subprocess
from langchain_core.tools import tool
from openai import OpenAI

# ─── Client DeepSeek ──────────────────────────────────────────────────────────
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
client = OpenAI(
    api_key=DEEPSEEK_API_KEY or None,
    base_url="https://api.deepseek.com/v1",
)


def _call_subagent(skill_name: str, system_prompt: str, context: str) -> dict:
    """
    Appelle un sous-agent via l'API DeepSeek (OpenAI-compatible) avec son prompt dédié.
    Retourne toujours un JSON structuré.
    """
    response = client.chat.completions.create(
        model="deepseek-chat",
        max_tokens=2000,
        temperature=0.1,
        messages=[
            {"role": "system", "content": f"""{system_prompt}

RÈGLE ABSOLUE : Réponds UNIQUEMENT en JSON valide, sans markdown, sans texte avant ou après.
Inclus toujours : status, summary, confidence (0.0-1.0), needs_more (bool), escalate (bool)."""},
            {"role": "user", "content": context}
        ]
    )
    try:
        return json.loads(response.choices[0].message.content)
    except (json.JSONDecodeError, AttributeError, TypeError, IndexError):
        return {
            "status": "error",
            "summary": "Réponse non parseable",
            "raw": str(response.choices[0].message.content)[:500] if response.choices else "",
            "confidence": 0.0,
            "needs_more": False,
            "escalate": False
        }


# ─── OUTIL 1 : Triage ────────────────────────────────────────────────────────
@tool
def tool_triage(brief: str) -> str:
    """
    Classe le bug : type, priorité, langage, fichiers suspects, routing suggéré.
    À appeler EN PREMIER sur tout nouveau bug.
    Retourne : bug_category, priority, langage, suspect_files, routing_hints.
    """
    result = _call_subagent(
        skill_name="nexus-triage",
        system_prompt="""Tu es nexus-triage, expert en classification de bugs.
Analyse le brief et retourne un JSON avec :
{
  "status": "success",
  "bug_category": "null_reference|type_error|runtime_crash|race_condition|memory_leak|perf_degradation|security_vuln|logic_error|...",
  "priority": "P0|P1|P2|P3|P4",
  "priority_reason": "...",
  "langage": "python|javascript|java|go|rust|...",
  "version_runtime": "...",
  "suspect_files": ["fichier1", "fichier2"],
  "suspect_lines": [42, 87],
  "routing_hints": {
    "needs_security": false,
    "needs_perf": false,
    "needs_runtime": true,
    "auto_escalate": false
  },
  "summary": "1 phrase",
  "confidence": 0.9,
  "needs_more": false,
  "escalate": false
}""",
        context=brief
    )
    return json.dumps(result)


# ─── OUTIL 2 : Analyse statique ──────────────────────────────────────────────
@tool
def tool_static_analysis(files: str, langage: str = "python") -> str:
    """
    Analyse statique du code : linters, AST, patterns dangereux.
    Appeler avec les fichiers suspects identifiés par le triage.
    Paramètres : files = liste des chemins séparés par virgule, langage = langage du code.
    Retourne : bugs_found, warnings, root_cause_hypothesis.
    """
    tool_output = ""
    for filepath in files.split(","):
        filepath = filepath.strip()
        if langage == "python":
            r = subprocess.run(
                ["python", "-m", "pylint", filepath, "--errors-only",
                 "--output-format=text"],
                capture_output=True, text=True
            )
            tool_output += f"\nPylint {filepath}:\n{r.stdout}{r.stderr}"

            r2 = subprocess.run(
                ["python", "-m", "py_compile", filepath],
                capture_output=True, text=True
            )
            tool_output += f"\nCompilation {filepath}: {'OK' if not r2.returncode else r2.stderr}"

        elif langage in ["javascript", "typescript"]:
            r = subprocess.run(
                ["node", "--check", filepath],
                capture_output=True, text=True
            )
            tool_output += f"\nNode check {filepath}:\n{r.stderr or 'OK'}"

    result = _call_subagent(
        skill_name="nexus-static",
        system_prompt="""Tu es nexus-static, expert en analyse statique.
Voici les résultats des outils + contexte. Retourne un JSON avec :
{
  "status": "success",
  "bugs_found": [{"type":"...","file":"...","line":0,"severity":"high|medium|low","fix_hint":"..."}],
  "warnings": [],
  "dependency_issues": [],
  "root_cause_hypothesis": "...",
  "summary": "1 phrase",
  "confidence": 0.85,
  "needs_more": false,
  "escalate": false
}""",
        context=f"Fichiers: {files}\nLangage: {langage}\n\nRésultats outils:\n{tool_output}"
    )
    return json.dumps(result)


# ─── OUTIL 3 : Scan sécurité ─────────────────────────────────────────────────
@tool
def tool_security_scan(files: str, langage: str = "python") -> str:
    """
    Scan de sécurité : OWASP, injections, CVE dépendances, secrets hardcodés.
    Appeler si le triage indique needs_security=true ou si mots-clés sécurité présents.
    Retourne : vulns_found, is_critical, escalate_immediately.
    """
    tool_output = ""
    for filepath in files.split(","):
        filepath = filepath.strip()
        if langage == "python":
            r = subprocess.run(
                ["python", "-m", "bandit", "-f", "txt", filepath],
                capture_output=True, text=True
            )
            tool_output += f"\nBandit {filepath}:\n{r.stdout[:1000]}"

    result = _call_subagent(
        skill_name="nexus-security",
        system_prompt="""Tu es nexus-security, expert en sécurité (OWASP Top 10).
Retourne un JSON avec :
{
  "status": "success",
  "is_critical": false,
  "vulns_found": [{"type":"...","file":"...","line":0,"severity":"CRITICAL|HIGH|MEDIUM|LOW","owasp":"A01-A10","fix_hint":"..."}],
  "dependency_vulns": [],
  "secrets_found": false,
  "escalate_immediately": false,
  "summary": "1 phrase",
  "confidence": 0.9,
  "needs_more": false,
  "escalate": false
}
IMPORTANT : si is_critical=true, mettre escalate=true et escalate_immediately=true.""",
        context=f"Fichiers: {files}\n\nRésultats scan:\n{tool_output}"
    )
    return json.dumps(result)


# ─── OUTIL 4 : Débogage dynamique ────────────────────────────────────────────
@tool
def tool_runtime_debug(
    files: str,
    error_message: str,
    stack_trace: str = ""
) -> str:
    """
    Débogage dynamique : reproduit le crash, analyse la stack trace,
    identifie la cause racine exacte avec ligne et valeur fautive.
    Appeler après l'analyse statique pour confirmer la cause racine.
    Retourne : root_cause, confirmed_file, confirmed_line, reproduction_steps.
    """
    file_contents = ""
    for filepath in files.split(",")[:2]:
        filepath = filepath.strip()
        try:
            r = subprocess.run(
                ["head", "-80", filepath],
                capture_output=True, text=True
            )
            file_contents += f"\n--- {filepath} ---\n{r.stdout}"
        except Exception:
            pass

    result = _call_subagent(
        skill_name="nexus-runtime",
        system_prompt="""Tu es nexus-runtime, expert en débogage dynamique.
Analyse la stack trace, le message d'erreur et le code.
Retourne un JSON avec :
{
  "status": "success",
  "bug_reproduced": true,
  "root_cause": "explication précise en 1-2 phrases",
  "confirmed_file": "chemin/fichier.py",
  "confirmed_line": 42,
  "confirmed_value": "valeur fautive ex: user = None",
  "reproduction_steps": ["étape 1", "étape 2"],
  "env_factors": ["facteur environnement si applicable"],
  "summary": "1 phrase",
  "confidence": 0.95,
  "needs_more": false,
  "escalate": false
}""",
        context=f"""Fichiers suspects : {files}
Erreur : {error_message}
Stack trace : {stack_trace}

Contenu des fichiers :
{file_contents}"""
    )
    return json.dumps(result)


# ─── OUTIL 5 : Analyse performance ───────────────────────────────────────────
@tool
def tool_perf_analysis(files: str, symptom: str) -> str:
    """
    Analyse performance et mémoire : bottlenecks CPU, fuites mémoire, N+1 queries.
    Appeler si le triage indique needs_perf=true ou si symptômes de lenteur présents.
    Retourne : bottleneck_found, memory_leak, fix_hints.
    """
    file_contents = ""
    for filepath in files.split(",")[:2]:
        filepath = filepath.strip()
        try:
            r = subprocess.run(
                ["grep", "-n", r"for.*for\|\.query\|\.find\|\.get", filepath],
                capture_output=True, text=True
            )
            file_contents += f"\n--- Patterns suspects {filepath} ---\n{r.stdout[:500]}"
        except Exception:
            pass

    result = _call_subagent(
        skill_name="nexus-perf",
        system_prompt="""Tu es nexus-perf, expert en performance et mémoire.
Retourne un JSON avec :
{
  "status": "success",
  "bottleneck_found": true,
  "bottleneck_type": "n_plus_one|o_n2|memory_leak|blocking_io|...",
  "bottleneck_location": {"file":"...","line":0,"function":"...","description":"..."},
  "memory_leak": false,
  "complexity_issues": [],
  "fix_hints": ["suggestion 1", "suggestion 2"],
  "summary": "1 phrase",
  "confidence": 0.85,
  "needs_more": false,
  "escalate": false
}""",
        context=f"Fichiers: {files}\nSymptôme: {symptom}\n\nCode analysé:\n{file_contents}"
    )
    return json.dumps(result)


# ─── OUTIL 6 : Correction du bug ─────────────────────────────────────────────
@tool
def tool_fix_bug(
    file_to_fix: str,
    root_cause: str,
    fix_description: str
) -> str:
    """
    Implémente la correction du bug dans le fichier cible.
    N'appeler QU'APRÈS avoir une cause racine confirmée (runtime ou static).
    Le fix doit être minimal et chirurgical.
    Retourne : fix_applied, code_before, code_after, files_modified.
    """
    file_content = ""
    try:
        with open(file_to_fix.strip()) as f:
            file_content = f.read()
    except FileNotFoundError:
        return json.dumps({
            "status": "error",
            "summary": f"Fichier non trouvé : {file_to_fix}",
            "fix_applied": False,
            "confidence": 0.0,
            "needs_more": False,
            "escalate": True
        })

    result = _call_subagent(
        skill_name="nexus-fix",
        system_prompt="""Tu es nexus-fix, ingénieur de correction.
Tu reçois le contenu du fichier, la cause racine confirmée et la description du fix.
Génère le code corrigé MINIMAL (change le moins de lignes possible).
Retourne un JSON avec :
{
  "status": "success",
  "fix_applied": true,
  "code_before": "code exact avant modification (5-10 lignes)",
  "code_after": "code exact après modification (5-10 lignes)",
  "fix_description": "ce qui a changé et pourquoi",
  "fix_justification": "pourquoi c'est la bonne approche",
  "lines_affected": [42],
  "files_modified": ["chemin/fichier.py"],
  "other_occurrences": ["autres endroits avec le même pattern"],
  "summary": "1 phrase",
  "confidence": 0.97,
  "needs_more": false,
  "escalate": false
}""",
        context=f"""Fichier à corriger : {file_to_fix}
Cause racine confirmée : {root_cause}
Description du fix : {fix_description}

Contenu actuel du fichier :
{file_content[:3000]}"""
    )
    return json.dumps(result)


# ─── OUTIL 7 : Tests de non-régression ───────────────────────────────────────
@tool
def tool_generate_tests(
    bug_summary: str,
    fix_description: str,
    module_path: str,
    langage: str = "python"
) -> str:
    """
    Génère les tests de non-régression pour le bug corrigé.
    Appeler APRÈS tool_fix_bug pour valider la correction.
    Retourne : test_code, test_file_path, tests_description.
    """
    result = _call_subagent(
        skill_name="nexus-qa",
        system_prompt="""Tu es nexus-qa, expert en tests automatisés.
Génère des tests de non-régression pour le bug décrit.
Le test doit ÉCHOUER sur le code original et PASSER après le fix.
Retourne un JSON avec :
{
  "status": "success",
  "test_code": "code complet du test (pytest/jest/go)",
  "test_file_path": "tests/test_bugfix_XXX.py",
  "tests_written": ["nom::du::test_1", "nom::du::test_2"],
  "test_description": "ce que chaque test vérifie",
  "coverage_target": "fonction ou classe testée",
  "summary": "1 phrase",
  "confidence": 0.92,
  "needs_more": false,
  "escalate": false
}""",
        context=f"""Bug corrigé : {bug_summary}
Fix appliqué : {fix_description}
Module concerné : {module_path}
Langage : {langage}"""
    )
    return json.dumps(result)


# ─── OUTIL 8 : Post-mortem ────────────────────────────────────────────────────
@tool
def tool_write_postmortem(
    mission_id: str,
    bug_summary: str,
    root_cause: str,
    fix_description: str,
    priority: str,
    duration_min: int = 0
) -> str:
    """
    Rédige le post-mortem et met à jour la base de connaissance.
    Appeler en dernier, après que le fix et les tests sont validés.
    Retourne : postmortem_text, prevention_rule, kb_updated.
    """
    result = _call_subagent(
        skill_name="nexus-postmortem",
        system_prompt="""Tu es nexus-postmortem, expert en documentation technique.
Rédige un post-mortem concis et actionnable.
Retourne un JSON avec :
{
  "status": "success",
  "postmortem_text": "texte markdown du post-mortem (max 300 mots)",
  "prevention_rule": "règle concrète pour éviter ce bug à l'avenir",
  "prevention_tool": "outil recommandé (ex: mypy, bandit, semgrep)",
  "lessons_learned": ["leçon 1", "leçon 2"],
  "kb_pattern": "pattern à mémoriser pour les futures missions",
  "summary": "1 phrase",
  "confidence": 0.95,
  "needs_more": false,
  "escalate": false
}""",
        context=f"""Mission : {mission_id}
Priorité : {priority}
Bug : {bug_summary}
Cause racine : {root_cause}
Fix : {fix_description}
Durée totale : {duration_min} minutes"""
    )
    return json.dumps(result)


# ─── Liste de tous les outils pour LangGraph ─────────────────────────────────
NEXUS_TOOLS = [
    tool_triage,
    tool_static_analysis,
    tool_security_scan,
    tool_runtime_debug,
    tool_perf_analysis,
    tool_fix_bug,
    tool_generate_tests,
    tool_write_postmortem,
]
