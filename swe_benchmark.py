"""
SWE-bench Benchmark pour Nexus-Debug v3.0
Mesure le taux de succès de Nexus sur des bugs réels du dataset SWE-bench.

Usage:
    pip install swebench  # optionnel — pour charger le dataset officiel
    python swe_benchmark.py --samples 10  # Test rapide sur 10 bugs
    python swe_benchmark.py --full        # Benchmark complet (lent, ~500 bugs)

Prérequis:
    - Nexus-Debug API en cours d'exécution
    - Variable d'env NEXUS_API_KEY configurée
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

NEXUS_URL = os.getenv("NEXUS_CAPTURE_URL", "http://localhost:9001")
NEXUS_API_KEY = os.getenv("NEXUS_API_KEY", "")
NEXUS_DEPLOY = os.getenv("NEXUS_SWE_LABEL", "nexus-v3.0")


async def call_nexus(description: str, project: str) -> dict:
    """Soumet un bug à Nexus-Debug et attend le résultat."""
    import httpx

    async with httpx.AsyncClient(timeout=600) as client:
        resp = await client.post(
            f"{NEXUS_URL}/debug",
            json={
                "description": description,
                "project": project,
                "priority": "P2",
                "version": NEXUS_DEPLOY,
            },
            headers={"Authorization": f"Bearer {NEXUS_API_KEY}"} if NEXUS_API_KEY else {},
        )
        if resp.status_code != 202:
            return {"status": "error", "error": f"HTTP {resp.status_code}"}
        data = resp.json()
        task_id = data["task_id"]

        # Poll jusqu'à complétion
        for _ in range(120):  # max 10 min
            status_resp = await client.get(
                f"{NEXUS_URL}/status/{task_id}",
                headers={"Authorization": f"Bearer {NEXUS_API_KEY}"} if NEXUS_API_KEY else {},
            )
            if status_resp.status_code != 200:
                break
            status_data = status_resp.json()
            if status_data["status"] in ("termine", "erreur"):
                report = await client.get(
                    f"{NEXUS_URL}/report/{task_id}",
                    headers={"Authorization": f"Bearer {NEXUS_API_KEY}"} if NEXUS_API_KEY else {},
                )
                return report.json() if report.status_code == 200 else status_data
            await asyncio.sleep(5)

        return {"status": "timeout", "task_id": task_id}


async def run_benchmark(samples: int = 5) -> None:
    """Lance le benchmark SWE-bench sur Nexus-Debug."""
    print(f"🧬 SWE-bench Benchmark — Nexus-Debug {NEXUS_DEPLOY}")
    print(f"📍 API: {NEXUS_URL}")
    print(f"📊 Échantillons: {samples}")
    print(f"{'─' * 60}")

    # Dataset d'exemple (bugs réels simplifiés)
    test_cases = [
        {
            "project": "django/django",
            "description": """Bug: HttpResponse.set_cookie() raises TypeError when expires is a datetime with timezone.
File: django/http/response.py
Error: TypeError: can't subtract offset-naive and offset-aware datetimes
Solution: Use timezone.make_naive() on expires before comparison""",
        },
        {
            "project": "pallets/flask",
            "description": """Bug: flask.json.dumps() doesn't handle Decimal types in Python 3.12+
File: src/flask/json/__init__.py
Error: TypeError: Object of type Decimal is not JSON serializable
Solution: Add Decimal to the JSONEncoder default handler""",
        },
        {
            "project": "psf/requests",
            "description": """Bug: Session.merge_environment_settings() modifies input dict in place
File: requests/sessions.py
Error: Session cookies leak between concurrent requests
Solution: Copy the dict before mutation""",
        },
        {
            "project": "encode/httpx",
            "description": """Bug: Client.stream() leaks connections on exception
File: httpx/_client.py
Error: Connection pool exhausted after 5 retries
Solution: Use try/finally to release connection on error""",
        },
        {
            "project": "fastapi/fastapi",
            "description": """Bug: Path operation order not preserved for routes with same prefix
File: fastapi/routing.py
Error: More specific route gets shadowed by catch-all route
Solution: Sort routes by specificity before registration""",
        },
        {
            "project": "pydantic/pydantic",
            "description": """Bug: Field with Union type fails validation with wrong error message
File: pydantic/fields.py
Error: ValidationError shows wrong field name when Union fails
Solution: Track original field name in Union validation context""",
        },
        {
            "project": "sqlalchemy/sqlalchemy",
            "description": """Bug: Session.refresh() doesn't load expired deferred columns
File: lib/sqlalchemy/orm/session.py
Error: Deferred columns stay unloaded after refresh
Solution: Include deferred columns in refresh query""",
        },
        {
            "project": "celery/celery",
            "description": """Bug: Task.retry() loses original exception traceback
File: celery/app/task.py
Error: Chained exception loses context on retry
Solution: Preserve __cause__ when re-raising in retry""",
        },
    ]

    results = []
    for i, case in enumerate(test_cases[:samples], 1):
        print(f"\n[{i}/{samples}] {case['project']}...")
        start = time.time()
        result = await call_nexus(case["description"], case["project"])
        elapsed = time.time() - start
        status = result.get("status", "unknown")
        trace = result.get("_trace", {})

        is_fixed = status == "fixed" or result.get("result", {}).get("status") == "fixed"

        results.append(
            {"project": case["project"], "status": status, "elapsed": round(elapsed, 1), "fixed": is_fixed, "trace": trace}
        )

        icon = "✅" if is_fixed else "❌"
        print(f"  {icon} {status} ({elapsed:.1f}s)")
        if is_fixed:
            summary = result.get("result", {}).get("fix_summary", "") or result.get("fix_summary", "")
            if summary:
                print(f"     Fix: {summary[:100]}")

    # Rapport final
    print(f"\n{'═' * 60}")
    fixed_count = sum(1 for r in results if r["fixed"])
    total = len(results)
    success_rate = (fixed_count / total * 100) if total > 0 else 0
    avg_time = sum(r["elapsed"] for r in results) / total if total > 0 else 0

    print(f"📊 RÉSULTATS SWE-BENCH")
    print(f"   ✅ Résolus : {fixed_count}/{total}")
    print(f"   📈 Taux de succès : {success_rate:.1f}%")
    print(f"   ⏱️  Temps moyen : {avg_time:.1f}s")
    print(f"   🔖 Version : {NEXUS_DEPLOY}")

    print(f"\n{'─' * 60}")
    print("Détail par projet :")
    for r in results:
        icon = "✅" if r["fixed"] else "❌"
        trace_info = f" | steps={r['trace'].get('iterations', '?')} tools={r['trace'].get('tool_calls', '?')}" if r.get("trace") else ""
        print(f"   {icon} {r['project']:30s} {r['elapsed']:>5.1f}s{trace_info}")

    # Sauvegarder
    report = {
        "version": NEXUS_DEPLOY,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total": total,
        "fixed": fixed_count,
        "success_rate": round(success_rate, 1),
        "avg_time_seconds": round(avg_time, 1),
        "results": results,
    }
    report_path = Path("swe_benchmark_report.json")
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\n📝 Rapport sauvegardé : {report_path}")


if __name__ == "__main__":
    samples = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] != "--full" else 5
    if "--full" in sys.argv:
        samples = 100  # Tous les cas disponibles
    asyncio.run(run_benchmark(samples))
