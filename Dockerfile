# Use Python 3.9 slim image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    ca-certificates \
    dnsutils \
    iputils-ping \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements_cloud.txt .
RUN pip install --no-cache-dir -r requirements_cloud.txt

# Copy application code
COPY app_cloud.py .
COPY templates/ templates/
COPY gcp_key.json .
COPY members.json .
COPY container_network_test.py .
COPY .env .

# Create a non-root user
RUN useradd -m app
RUN chown -R app:app /app
USER app

# Set environment variables
ENV GCP_KEY_PATH=/app/gcp_key.json

# Expose port
EXPOSE 8082

# Run the application directly with Python (not Gunicorn)
CMD ["python", "app_cloud.py"] 