FROM python:3.11-slim

LABEL maintainer="Ndifoin Hilary"

ENV PYTHONUNBUFFERED=1 \
    PATH="/py/bin:$PATH" \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        python3-dev \
        libffi-dev \
        libssl-dev \
        libpq-dev \
        postgresql-client \
        gdal-bin \
        libgdal-dev \
        libproj-dev \
        libgeos-dev \
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

# Install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN /py/bin/pip install --upgrade pip && \
    /py/bin/pip install --no-cache-dir -r /tmp/requirements.txt && \
    rm -rf /tmp/*

# Create application user and directories
RUN useradd --create-home --shell /bin/bash django-user && \
    mkdir -p /vol/web/media /vol/web/static && \
    chown -R django-user:django-user /vol && \
    chmod -R 755 /vol

# Set working directory and create logs directory
WORKDIR /app
RUN mkdir -p /app/logs && \
    chown -R django-user:django-user /app/logs

# Copy application code
COPY --chown=django-user:django-user . /app

# Switch to non-root user
USER django-user

EXPOSE 8000

# Set production environment variables
ENV SECRET_KEY="${SECRET_KEY:-temporary-secret-key-for-testing-only}" \
    DEBUG="${DEBUG:-False}" \
    DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-geopharm.settings}" \
    PORT="${PORT:-8000}"

# Production startup with optional mock data
CMD ["/bin/bash", "-c", "\
    echo '🚀 Starting Geopharm API Server...' && \
    python manage.py check --database default && \
    python manage.py migrate --noinput && \
    python manage.py collectstatic --noinput && \
    if [ \"${GENERATE_MOCK_DATA:-false}\" = \"true\" ]; then \
        echo '📊 Generating mock data...' && \
        python manage.py generate_mock_data; \
    fi && \
    echo '✅ Server starting on port ${PORT}' && \
    exec gunicorn geopharm.wsgi:application \
        --bind 0.0.0.0:${PORT} \
        --workers 2 \
        --timeout 30 \
        --log-level info \
        --access-logfile - \
        --error-logfile - \
    "]