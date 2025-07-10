#!/bin/bash
set -e

echo "Waiting for database..."
python manage.py wait_for_db

echo "Running migrations..."
python manage.py migrate

echo "Generating mock data..."
python manage.py generate_mock_data

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting Gunicorn..."
exec gunicorn geopharm.wsgi:application --bind 0.0.0.0:$PORT