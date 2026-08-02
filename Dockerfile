# Image backend BAMFA (Django + DRF) — usage dev via docker-compose (workspace).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dépendances Python (psycopg est fourni en wheel binaire → pas d'outils de build requis).
COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/dev.txt

# Code applicatif (monté en volume en dev pour le rechargement à chaud).
COPY . .

EXPOSE 8000

# Par défaut : serveur de développement. Le service `worker` surcharge la commande.
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
