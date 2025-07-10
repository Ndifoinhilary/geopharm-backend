FROM python:3.11-slim

LABEL maintainer="Ndifoin Hilary"

ENV PYTHONUNBUFFERED=1 \
    PATH="/py/bin:$PATH" \
    DEBIAN_FRONTEND=noninteractive

# Your existing package installation (unchanged)
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

# Copy start.sh BEFORE switching to django-user
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Copy application code and change ownership
COPY --chown=django-user:django-user . /app

# Make sure django-user owns the start.sh script
RUN chown django-user:django-user /app/start.sh

# Switch to non-root user
USER django-user

EXPOSE 8000

CMD ["./start.sh"]