#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "--- Starting Entrypoint Script ---"

# 1. Wait for Database (Optional but recommended)
# This prevents the backend from crashing if the DB isn't ready yet
echo "Waiting for database to be ready..."
# If you have 'curl' or 'nc' installed, you can add a check here, 
# but usually, Docker Compose 'depends_on' handles the startup order.

# 2. Apply Database Migrations
echo "Applying database migrations..."
python manage.py migrate --noinput

# 3. Create Superuser
# We use '|| true' so that if the user already exists, the script doesn't crash
echo "Checking for superuser creation..."
python manage.py create_superuser_env || echo "Superuser command skipped or user already exists."

# 4. Collect Static Files
# Even though it's in the Dockerfile, running it here ensures 
# any volume-mapped static files are updated.
echo "Collecting static files..."
python manage.py collectstatic --noinput

# 5. Start Gunicorn
# 'exec' ensures Gunicorn becomes PID 1, allowing it to receive shutdown signals
echo "Starting Gunicorn on port 8000..."
exec gunicorn --bind 0.0.0.0:8000 config.wsgi:application
