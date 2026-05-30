"""
conftest.py — Configuration partagée pour tous les tests
"""

import os

# Force DB to temp path so tests don't conflict with running instance
os.environ.setdefault("NEXUS_DB_PATH", "/tmp/nexus_test.db")

# Remove old test DB before tests
import atexit
import subprocess

atexit.register(lambda: subprocess.run(["rm", "-f", "/tmp/nexus_test.db"], capture_output=True))
