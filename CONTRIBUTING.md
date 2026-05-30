# Contribuer à Nexus-Debug 🧬

Merci de t'intéresser à Nexus-Debug ! Toute contribution est la bienvenue.

## 🚀 Quick Start

```bash
git clone https://github.com/xalil05/nexus-debug.git
cd nexus-debug
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 🧪 Tester

```bash
# Lancer tous les tests
make test

# Avec couverture
python -m pytest tests/ -v --cov=nexus --cov-report=term
```

## 🧹 Formater et Linter

```bash
# Formater le code
make format          # ruff format

# Linter
make lint            # ruff check

# Type checking
make typecheck       # mypy
```

Tout doit passer avant de soumettre une PR.

## 📝 Soumettre une Pull Request

1. **Fork** le repo et crée une branche : `git checkout -b feature/ma-feature`
2. **Commit** tes changements avec un message clair (anglais ou français)
3. **Teste** que tout passe (`make test && make lint && make typecheck`)
4. **Push** : `git push origin feature/ma-feature`
5. Ouvre la **Pull Request** sur GitHub

### Convention de commits

```
feat: ajout d'une nouvelle fonctionnalité
fix: correction d'un bug
docs: documentation uniquement
style: format, typo
refactor: refacto sans changement fonctionnel
test: ajout ou modification de tests
chore: build, CI, dépendances
```

## 🐛 Signaler un bug

Utilise le [template Bug Report](.github/ISSUE_TEMPLATE/bug_report.yml) sur GitHub.

## 💡 Proposer une idée

Utilise le [template Feature Request](.github/ISSUE_TEMPLATE/feature_request.yml) sur GitHub.

## 🔐 Sécurité

Nexus utilise DeepSeek V4 Pro via API Key. **Ne commit jamais ta clé API.**
Utilise le fichier `.env` (copie de `.env.example`) pour la config locale.

## 📖 Documentation

- [README.md](README.md) — Documentation complète
- [ARTICLE.md](ARTICLE.md) — Article technique (architecture)
- [DEMO.md](DEMO.md) — Démo interactive
- [CHANGELOG.md](CHANGELOG.md) — Historique des versions

---

Merci de contribuer à Nexus-Debug ! 🎯
