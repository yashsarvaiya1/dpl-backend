FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Use a dummy key just for collectstatic at build time
RUN SECRET_KEY=dummy-build-key python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate && python manage.py create_superuser_env && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --timeout 120 --workers 2"]
