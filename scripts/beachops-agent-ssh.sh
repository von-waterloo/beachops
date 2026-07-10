#!/bin/bash
# Forced-command gate: read-only docker diagnostics for BeachOps Cursor agent.
set -euo pipefail

CMD="${SSH_ORIGINAL_COMMAND:-}"
if [[ -z "${CMD}" ]]; then
  echo "beachops-agent: interactive login denied; pass a read-only docker command" >&2
  exit 1
fi

CMD="$(printf '%s' "$CMD" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/[[:space:]]\+/ /g')"

ALLOWED_CD="/home/const/tg-cursor-bot"
CD_RE='^cd[[:space:]]+([^[:space:]]+)[[:space:]]+&&[[:space:]]+(.+)$'

if [[ "$CMD" =~ $CD_RE ]]; then
  dir="${BASH_REMATCH[1]}"
  dir="${dir#\"}"; dir="${dir%\"}"
  dir="${dir#\'}"; dir="${dir%\'}"
  if [[ "$dir" != "$ALLOWED_CD" ]]; then
    echo "beachops-agent: cd only allowed to ${ALLOWED_CD}" >&2
    exit 1
  fi
  CMD="${BASH_REMATCH[2]}"
  cd "$ALLOWED_CD"
fi

# Deny shell metacharacters; allow {} for docker --format Go templates.
if printf '%s' "$CMD" | grep -Eq '[;|&`$<>()]|\$\('; then
  echo "beachops-agent: shell metacharacters denied" >&2
  exit 1
fi

allow=0
COMPOSE_RE='^docker[[:space:]]+compose[[:space:]]+'
DOCKER_RE='^docker[[:space:]]+'
PROJ_RE='^(-p|--project-name)[[:space:]]+[^[:space:]]+[[:space:]]+(.*)$'

if [[ "$CMD" =~ $COMPOSE_RE ]]; then
  rest="${CMD#docker compose }"
  if [[ "$rest" =~ $PROJ_RE ]]; then
    rest="${BASH_REMATCH[2]}"
  fi
  sub="${rest%% *}"
  case "$sub" in
    ps|logs) allow=1 ;;
  esac
elif [[ "$CMD" =~ $DOCKER_RE ]]; then
  rest="${CMD#docker }"
  sub="${rest%% *}"
  case "$sub" in
    ps|logs|inspect) allow=1 ;;
    stats)
      if [[ "$CMD" == *"--no-stream"* ]]; then
        allow=1
      fi
      ;;
  esac
fi

if [[ "$allow" -ne 1 ]]; then
  echo "beachops-agent: denied. Allowed: docker ps|logs|inspect|stats --no-stream|compose ps|compose logs" >&2
  exit 1
fi

exec /bin/bash -c "$CMD"