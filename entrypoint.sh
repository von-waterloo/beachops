#!/bin/sh
set -e

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
    alembic upgrade head
fi

if [ "$#" -eq 0 ]; then
    set -- python -m beachops
fi

exec "$@"
