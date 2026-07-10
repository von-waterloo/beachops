#!/bin/sh
# Run inside the postgres container. It does not print the configured password.
set -eu

test -n "${POSTGRES_PASSWORD:-}"
escaped_password="$(printf '%s' "$POSTGRES_PASSWORD" | sed "s/'/''/g")"
printf "ALTER ROLE bot PASSWORD '%s';\n" "$escaped_password" \
    | psql -v ON_ERROR_STOP=1 -U bot -d tg_cursor_bot
