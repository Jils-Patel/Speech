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
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements_cloud.txt .
RUN pip install --no-cache-dir -r requirements_cloud.txt

# Copy application code
COPY app_cloud.py .
COPY templates/ templates/

# Copy environment file and GCP key
COPY .env* ./
COPY gcp_key.json ./

# Create a non-root user
RUN useradd --create-home --shell /bin/bash app
RUN chown -R app:app /app
USER app

# Expose port
EXPOSE 8080

# Run the application
CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "--bind", "0.0.0.0:8080", "--timeout", "120", "app_cloud:app"] 