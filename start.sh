#!/bin/bash
set -e

echo "=== Starting Deployment ==="
echo "PORT: ${PORT}"
echo "Current directory: $(pwd)"

echo "=== Testing Django Setup ==="
python manage.py check || {
    echo "Django check failed!"
    exit 1
}

echo "=== Waiting for database ==="
python manage.py wait_for_db || {
    echo "Database wait failed!"
    echo "Trying to start without database operations..."
    exec gunicorn geopharm.wsgi:application --bind 0.0.0.0:${PORT} --log-level debug
}

echo "=== Running migrations ==="
python manage.py migrate || {
    echo "Migration failed! Starting server anyway..."
    exec gunicorn geopharm.wsgi:application --bind 0.0.0.0:${PORT} --log-level debug
}

echo "=== Generating mock data ==="
python manage.py generate_mock_data || {
    echo "Mock data generation failed, continuing..."
}

echo "=== Collecting static files ==="
python manage.py collectstatic --noinput || {
    echo "Static file collection failed, continuing..."
}

echo "=== Starting Gunicorn ==="
exec gunicorn geopharm.wsgi:application \
    --bind 0.0.0.0:${PORT} \
    --workers 2 \
    --timeout 120 \
    --log-level info \
    --access-logfile - \
    --error-logfile -