# Use Python 3.12 slim for a small footprint
FROM python:3.12-slim

# Install system dependencies for PostgreSQL and building tools
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv directly from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies into the system site-packages
RUN uv pip install --system --no-cache -e . && uv pip install --system gunicorn

# Copy the rest of the project source
COPY . .

# Create necessary directories
RUN mkdir -p /app/staticfiles /app/media

# Collect static files
# dummy SECRET_KEY provided for the build process
RUN SECRET_KEY=build-dummy-key-123 python manage.py collectstatic --noinput

# --- ENTRYPOINT CONFIGURATION ---

# Copy the entrypoint script
COPY entrypoint.sh /app/entrypoint.sh

# Fix potential Windows line ending issues and make it executable
RUN sed -i 's/\r$//g' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

EXPOSE 8000

# Use ENTRYPOINT to run the script which handles migrations/superuser
# before starting Gunicorn
ENTRYPOINT ["/app/entrypoint.sh"]
