#!/bin/bash
set -e

python manage.py migrate
python manage.py collectstatic --noinput
python manage.py create_superuser_env

gunicorn config.wsgi
