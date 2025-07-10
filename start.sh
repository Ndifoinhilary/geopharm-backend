#!/bin/bash

# DO NOT exit on error initially - we want to see what fails
set +e

echo "🚀 CONTAINER STARTUP DEBUG"
echo "=========================="
echo "Date: $(date)"
echo "User: $(whoami)"
echo "Working Dir: $(pwd)"

echo "🔍 ENVIRONMENT VARIABLES CHECK"
echo "=============================="
echo "PORT: '${PORT:-NOT_SET}'"
echo "DEBUG: '${DEBUG:-NOT_SET}'"
echo "SECRET_KEY: '${SECRET_KEY:0:10}...'"
echo "DATABASE_URL: '${DATABASE_URL:0:30}...'"
echo "DJANGO_SETTINGS_MODULE: '${DJANGO_SETTINGS_MODULE:-NOT_SET}'"

echo "📁 FILE SYSTEM CHECK"
echo "==================="
ls -la /app/ || echo "❌ Cannot list /app"
ls -la /app/manage.py || echo "❌ manage.py not found"

echo "🐍 PYTHON BASIC TEST"
echo "==================="
python --version || echo "❌ Python version failed"
which python || echo "❌ Python not found in PATH"

echo "📦 DJANGO IMPORT TEST"
echo "===================="
python -c "
try:
    import django
    print(f'✅ Django {django.get_version()} imported')
except Exception as e:
    print(f'❌ Django import failed: {e}')
    exit(1)
"

if [ $? -ne 0 ]; then
    echo "❌ Django import failed - stopping"
    exit 1
fi

echo "⚙️ DJANGO SETTINGS TEST"
echo "======================"

# Set minimal required environment variables if missing
export SECRET_KEY="${SECRET_KEY:-temporary-secret-key-for-testing-only}"
export DEBUG="${DEBUG:-False}"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-geopharm.settings}"

python -c "
import os
import django
print('Setting up Django...')
django.setup()
print('✅ Django setup successful')

from django.conf import settings
print(f'✅ SECRET_KEY: {settings.SECRET_KEY[:10]}...')
print(f'✅ DEBUG: {settings.DEBUG}')
print(f'✅ ALLOWED_HOSTS: {settings.ALLOWED_HOSTS}')
" || {
    echo "❌ Django settings failed"
    exit 1
}

echo "🗄️ DATABASE TEST"
echo "==============="
python manage.py check --database default || {
    echo "❌ Database check failed"
    echo "Trying without database operations..."
}

echo "🎯 BASIC DJANGO CHECK"
echo "===================="
python manage.py check || {
    echo "❌ Django check failed - will try to start anyway"
}

echo "🚀 STARTING SERVER"
echo "=================="
PORT=${PORT:-8000}
echo "Starting server on port $PORT..."

# Simple gunicorn start
exec gunicorn geopharm.wsgi:application \
    --bind 0.0.0.0:$PORT \
    --workers 1 \
    --timeout 30 \
    --log-level debug \
    --access-logfile - \
    --error-logfile -