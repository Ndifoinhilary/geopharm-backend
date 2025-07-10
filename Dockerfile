FROM python:3.11-slim

LABEL maintainer="Ndifoin Hilary"

ENV PYTHONUNBUFFERED=1 \
    PATH="/py/bin:$PATH" \
    DEBIAN_FRONTEND=noninteractive

# Package installation (unchanged)
RUN apt-get update --fix-missing || apt-get update --fix-missing || apt-get update --fix-missing

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        python3-dev \
        libffi-dev \
        libssl-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq-dev \
        postgresql-client \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y --no-install-recommends \
        gdal-bin \
        libgdal-dev \
        libproj-dev \
        libgeos-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        libjpeg-dev \
        zlib1g-dev \
        pkg-config \
    && python -m venv /py \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set GDAL environment variables
ENV GDAL_LIBRARY_PATH="/usr/lib/x86_64-linux-gnu/libgdal.so"
ENV GEOS_LIBRARY_PATH="/usr/lib/x86_64-linux-gnu/libgeos_c.so"

# Copy requirements and install Python dependencies
COPY requirements.txt /tmp/requirements.txt

ARG DEV=false

RUN /py/bin/pip install --upgrade pip && \
    /py/bin/pip install --no-cache-dir -r /tmp/requirements.txt && \
    rm -rf /tmp/*

# Create application user and directories
RUN useradd --create-home --shell /bin/bash django-user && \
    mkdir -p /vol/web/media /vol/web/static && \
    chown -R django-user:django-user /vol && \
    chmod -R 755 /vol

# Set working directory
WORKDIR /app

# Copy application code and change ownership
COPY --chown=django-user:django-user . /app

# Switch to non-root user
USER django-user

EXPOSE 8000

# Set default environment variables for production
ENV SECRET_KEY="${SECRET_KEY:-temporary-secret-key-for-testing-only}" \
    DEBUG="${DEBUG:-False}" \
    DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-geopharm.settings}" \
    PORT="${PORT:-8000}"

# Direct startup commands with debugging
CMD echo "🚀 CONTAINER STARTUP DEBUG" && \
    echo "==========================" && \
    echo "Date: $(date)" && \
    echo "User: $(whoami)" && \
    echo "Working Dir: $(pwd)" && \
    echo "🔍 ENVIRONMENT CHECK" && \
    echo "PORT: ${PORT}" && \
    echo "DEBUG: ${DEBUG}" && \
    echo "SECRET_KEY: ${SECRET_KEY:0:10}..." && \
    echo "DATABASE_URL: ${DATABASE_URL:0:30}..." && \
    echo "🐍 PYTHON CHECK" && \
    python --version && \
    echo "📦 DJANGO CHECK" && \
    python -c "import django; print(f'✅ Django {django.get_version()}')" && \
    echo "⚙️ DJANGO SETUP TEST" && \
    python -c "import django; django.setup(); from django.conf import settings; print(f'✅ ALLOWED_HOSTS: {settings.ALLOWED_HOSTS}')" && \
    echo "🗄️ DATABASE OPERATIONS" && \
    python manage.py check --database default && \
    python manage.py migrate --noinput && \
    echo "🚀 STARTING SERVER ON PORT ${PORT}" && \
    exec gunicorn geopharm.wsgi:application \
        --bind 0.0.0.0:${PORT} \
        --workers 2 \
        --timeout 30 \
        --log-level info \
        --access-logfile - \
        --error-logfile -