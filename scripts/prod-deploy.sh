#!/bin/sh
set -eu

REMOTE_DIR="/home/const/tg-cursor-bot"
PROJECT="tg-cursor-bot"
ARCHIVE="beachops-deploy.tgz"

cd "$REMOTE_DIR"
test -f "$ARCHIVE"
test -f .env
sed -i 's/\r$//' .env

backup="$REMOTE_DIR/beachops-predeploy-$(date +%Y%m%d-%H%M%S).sql"
docker compose -p "$PROJECT" exec -T postgres \
    pg_dump -U bot tg_cursor_bot > "$backup"
echo "Database backup: $backup"

# Stop the only Telegram poller before replacing code.
docker compose -p "$PROJECT" stop -t 30 bot || true
rm -rf src/tg_cursor_bot
tar -xzf "$ARCHIVE"
rm -f "$ARCHIVE"
sed -i 's/\r$//' entrypoint.sh scripts/*.sh

sh scripts/bootstrap-prod-env.sh .env

docker compose -p "$PROJECT" stop -t 30 worker api webapp 2>/dev/null || true
docker compose -p "$PROJECT" build
docker compose -p "$PROJECT" up -d --force-recreate --remove-orphans
sleep 8
docker compose -p "$PROJECT" ps
docker compose -p "$PROJECT" logs --tail=30 migrate bot worker api
