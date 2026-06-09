FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md alembic.ini ./
COPY alembic ./alembic
COPY src ./src
COPY entrypoint.sh /entrypoint.sh

RUN pip install --no-cache-dir . \
    && chmod +x /entrypoint.sh

RUN mkdir -p /data/workspace

ENV WORKSPACE_PATH=/data/workspace
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/entrypoint.sh"]
