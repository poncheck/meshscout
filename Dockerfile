# Multi-purpose Dockerfile dla Mesh Scout
# Obsługuje zarówno MQTT decoder jak i web server

FROM python:3.11-slim

# Metadata
LABEL maintainer="mesh-scout"
LABEL description="Mesh Scout - Meshtastic MQTT Decoder with Web Interface"

# Ustaw zmienne środowiskowe
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Katalog roboczy
WORKDIR /app

# Zainstaluj zależności systemowe
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Kopiuj requirements i zainstaluj zależności
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Kopiuj całą aplikację
COPY . .

# Nadaj uprawnienia wykonywania
RUN chmod +x meshtastic_mqtt_decoder.py web_server.py || true

# Utwórz katalog na bazę danych z odpowiednimi uprawnieniami
RUN mkdir -p /data && \
    chmod 777 /data

# Expose port dla web servera
EXPOSE 5000

# Domyślna komenda - można nadpisać w docker-compose
CMD ["python", "web_server.py"]
