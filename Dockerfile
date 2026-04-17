FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Collect static files at build time
RUN python manage.py collectstatic --noinput || true

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate && python manage.py create_superuser_env && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --timeout 120 --workers 2"]
