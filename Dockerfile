FROM python:3.9-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y \
    gcc \
    ca-certificates \
    dnsutils \
    iputils-ping \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY templates/ templates/
COPY gcp_key.json .
COPY members.json .
COPY .env .

RUN useradd -m app
RUN chown -R app:app /app
USER app

ENV GCP_KEY_PATH=/app/gcp_key.json

EXPOSE 8082

CMD ["python", "app.py"] 