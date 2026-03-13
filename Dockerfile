FROM python:3.12-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        django \
        djangorestframework \
        django-filter \
        drf-spectacular \
        djangorestframework-simplejwt \
        django-guardian \
        django-auditlog \
        "fhir.resources>=7.1" \
        pydantic \
        psycopg2-binary \
        python-decouple \
        django-cors-headers \
        celery \
        redis

COPY . .

EXPOSE 8000
