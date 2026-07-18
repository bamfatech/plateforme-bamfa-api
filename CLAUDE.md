# CLAUDE.md — Dépôt backend BAMFA

Dépôt **backend** de la plateforme BAMFA (Django + DRF). Fait partie d'un ensemble de trois dépôts : `workspace` (orchestration + docs), `backend`, `frontend`.

## Git / Commits

- **Ne jamais mentionner Claude, l'IA ou un assistant dans les messages de commit.** Pas de `Co-Authored-By: Claude`, pas de « Generated with… ».
- Messages de commit en **français** (`feat:`, `fix:`, `chore:`, `refactor:`, `test:`).
- Une branche par slice / module (`feat/<module>`), PR + revue avant merge sur `main`.

## Stack & conventions

- **Django 5.2 + DRF**, PostgreSQL, settings séparés (`config/settings/base.py` + `dev.py`).
- API versionnée sous `/api/v1/`. Schéma OpenAPI via drf-spectacular.
- Une app Django par module métier (`apps/<module>`), responsabilité unique.
- **TDD** : test qui échoue → implémentation minimale → test qui passe → commit.
- Langue : **français** (UI, contenus, `LANGUAGE_CODE = "fr-fr"`).
- Doc de référence d'architecture : voir le dépôt `workspace`, `docs/superpowers/specs/`.

## Lancer en local

- PostgreSQL + Redis via le `docker-compose.yml` du dépôt `workspace`.
- `python manage.py runserver` · tests : `pytest`.
