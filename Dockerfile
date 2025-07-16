# Base image
FROM python:3.11-slim

# Variables d'environnement
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Installer les dépendances système pour Tesseract
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-fra \
    tesseract-ocr-eng \
    tesseract-ocr-spa \
    tesseract-ocr-deu \
    tesseract-ocr-ita \
    tesseract-ocr-por \
    && rm -rf /var/lib/apt/lists/*

# Créer un utilisateur non-root AVANT de copier les fichiers
RUN adduser --disabled-password --gecos '' --home /home/myuser myuser

# Définir le répertoire de travail
WORKDIR /home/myuser/app

# Copier les fichiers requirements et installer les dépendances Python
COPY requirements.txt .

# Créer un environnement virtuel et installer les dépendances
RUN python -m venv /opt/venv && \
    source /opt/venv/bin/activate && \
    pip install --no-cache-dir -r requirements.txt

# Copier le code de l'application
COPY . .

# Créer le dossier static et donner les permissions appropriées
RUN mkdir -p static && \
    chown -R myuser:myuser /home/myuser/app && \
    chmod -R 755 /home/myuser/app && \
    chmod -R 777 static

# Changer vers l'utilisateur non-root
USER myuser

# Exposer le port (utilise la variable d'environnement PORT de Render)
EXPOSE 10000

# Commande pour démarrer l'application
CMD ["sh", "-c", "/opt/venv/bin/gunicorn app:app --bind 0.0.0.0:${PORT:-10000}"]