#!/bin/sh
set -eu

ENV_FILE="${1:-.env}"
test -f "$ENV_FILE"
sed -i 's/\r$//' "$ENV_FILE"

env_value() {
    awk -F= -v wanted="$1" '
        $1 == wanted {
            sub(/^[^=]*=/, "")
            print
            exit
        }
    ' "$ENV_FILE"
}

if [ -z "$(env_value DATA_ENCRYPTION_KEY)" ]; then
    printf '\nDATA_ENCRYPTION_KEY=%s\n' "$(openssl rand -hex 32)" >> "$ENV_FILE"
fi

if [ -z "$(env_value OWNER_USER_IDS)" ]; then
    owner_ids="$(env_value ADMIN_USER_IDS)"
    test -n "$owner_ids"
    printf 'OWNER_USER_IDS=%s\n' "$owner_ids" >> "$ENV_FILE"
fi

if [ -z "$(env_value POSTGRES_PASSWORD)" ]; then
    printf 'POSTGRES_PASSWORD=botsecret\n' >> "$ENV_FILE"
fi

if [ -z "$(env_value REPOSITORY_POLICY_JSON)" ]; then
    repo="$(env_value DEFAULT_REPO_URL)"
    branch="$(env_value DEFAULT_BRANCH)"
    branch="${branch:-dev}"
    test -n "$repo"
    printf 'REPOSITORY_POLICY_JSON={"repositories":[{"url":"%s","branches":["%s"]}]}\n' \
        "$repo" "$branch" >> "$ENV_FILE"
fi

if [ -z "$(env_value WORKER_BOOTSTRAP_TOKEN)" ]; then
    printf '\nWORKER_BOOTSTRAP_TOKEN=%s\n' "$(openssl rand -hex 32)" >> "$ENV_FILE"
fi

if [ -z "$(env_value DEFAULT_RUNTIME)" ]; then
    printf 'DEFAULT_RUNTIME=cloud\n' >> "$ENV_FILE"
fi

if [ -z "$(env_value GITHUB_REPO)" ]; then
    printf 'GITHUB_REPO=von-waterloo/beachops\n' >> "$ENV_FILE"
fi
