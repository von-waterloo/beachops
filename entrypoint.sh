#!/bin/sh
set -e
alembic upgrade head
exec python -m tg_cursor_bot
