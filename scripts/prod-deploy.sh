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

rm -rf src/tg_cursor_bot
tar -xzf "$ARCHIVE"
rm -f "$ARCHIVE"
sed -i 's/\r$//' entrypoint.sh scripts/*.sh

sh scripts/bootstrap-prod-env.sh .env

# Build and validate the candidate before disrupting the running app tier.
docker compose -p "$PROJECT" up -d --wait postgres redis
docker compose -p "$PROJECT" build
docker compose -p "$PROJECT" run --rm --no-deps migrate
docker compose -p "$PROJECT" run --rm --no-deps migrate alembic current --check-heads

# The candidate is safe to start; restart the poller only now to prevent two
# long-polling instances from sharing one Telegram bot token.
docker compose -p "$PROJECT" stop -t 30 bot || true
docker compose -p "$PROJECT" up -d --no-deps --force-recreate --remove-orphans \
    bot worker api webapp

for _ in $(seq 1 60); do
    if curl -fsS http://127.0.0.1:8080/ready >/dev/null; then
        echo "BeachOps is ready"
        break
    fi
    sleep 5
done
curl -fsS http://127.0.0.1:8080/ready >/dev/null
docker compose -p "$PROJECT" ps
docker compose -p "$PROJECT" logs --tail=30 migrate bot worker api
