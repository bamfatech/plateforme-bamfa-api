# Plateforme BAMFA — API

API REST de la plateforme **BAMFA** (Benin Association of the Mastercard Foundation Alumni), construite avec **Django + Django REST Framework**.

## Stack

- Python 3.12 · Django 5.2 · Django REST Framework
- PostgreSQL 16 · Redis 7
- Auth : JWT en **cookies httpOnly** (`djangorestframework-simplejwt`) + protection CSRF
- Doc API : OpenAPI via `drf-spectacular`
- Tests : `pytest` · Lint : `ruff`

## Prérequis

- Python **3.12**
- **PostgreSQL 16** et **Redis 7** accessibles (paramètres dans `.env`). Exemple rapide avec Docker :

```bash
docker run -d --name bamfa-db -e POSTGRES_DB=bamfa -e POSTGRES_USER=bamfa \
  -e POSTGRES_PASSWORD=bamfa -p 5432:5432 postgres:16
docker run -d --name bamfa-redis -p 6379:6379 redis:7
```

## Installation (dev local)

```bash
# 1. Environnement virtuel + dépendances
python -m venv .venv
# Windows (PowerShell) : .\.venv\Scripts\Activate.ps1
# macOS / Linux       : source .venv/bin/activate
pip install -r requirements/dev.txt

# 2. Variables d'environnement
cp .env.example .env        # puis ajuster si besoin

# 3. Base de données
python manage.py migrate    # applique les migrations + seed les rôles

# 4. Compte administrateur
python manage.py createsuperuser   # identifiant = e-mail

# 5. Lancer le serveur
python manage.py runserver
```

L'API est alors disponible sur `http://localhost:8000/`.

## Documentation de l'API

Une fois le serveur lancé, la liste complète des endpoints est disponible dans la doc interactive :

- **Swagger** : `http://localhost:8000/api/v1/docs/`
- **Schéma OpenAPI** : `http://localhost:8000/api/v1/schema/`

## Tests & qualité

```bash
pytest              # suite de tests
ruff check .        # lint
```

## Authentification (à savoir)

- Les tokens JWT sont stockés dans des **cookies httpOnly** (jamais accessibles au JS) : `bamfa_access`, `bamfa_refresh`.
- Les requêtes **authentifiées non sûres** (POST/PUT/DELETE) exigent l'en-tête `X-CSRFToken` (token obtenu via `/api/v1/auth/csrf/` ou le cookie `csrftoken`).
- Pour tester le flux complet, utiliser **Postman** (gestion des cookies + en-têtes).
- **Rôles** = groupes Django (`Alumni`, `Rédacteur de contenu`, `Secrétaire`, `Trésorier`, `Administrateur`) ; super-admin = `is_superuser`. Commande de (re)seed : `python manage.py seed_roles`.

## Structure

```
backend/
├── config/              # settings (base/dev), urls, wsgi/asgi
│   └── settings/
├── apps/
│   ├── accounts/        # User, auth JWT, rôles, Mandate
│   └── common/          # utilitaires transverses (health, PublishableMixin)
├── requirements/        # base.txt, dev.txt
└── tests/               # pytest
```

## Conventions

- Voir **`CLAUDE.md`** à la racine du dépôt.
- Messages de commit en **français**, **sans mention d'IA/assistant**.
- **TDD** : test qui échoue → implémentation minimale → test qui passe → commit.
- Une branche par fonctionnalité (`feat/<module>`), PR + revue avant merge sur `main`.
