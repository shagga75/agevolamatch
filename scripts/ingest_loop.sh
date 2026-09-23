#!/bin/sh
# Runs `ingest` (+ `gare ingest` if enabled) then the matching `alerts run`
# on a loop, for the docker-compose `ingest` service. Configurable via env
# vars so the same image works for a dry-run demo and a real deployment
# without a code change.
set -eu

DB_PATH="${AGEVOLAMATCH_DB_PATH:-data/agevolamatch.db}"
SUBSCRIPTIONS="${ALERT_SUBSCRIPTIONS_PATH:-}"
INTERVAL="${INGEST_INTERVAL_SECONDS:-86400}"
DRY_RUN_FLAG="--dry-run"
if [ "${ALERTS_DRY_RUN:-true}" = "false" ]; then
    DRY_RUN_FLAG="--no-dry-run"
fi
# Off by default: ANAC/TED ingest is a separate, heavier download (a ~30MB
# monthly zip plus paginated API calls) that existing deployments didn't
# opt into before Fase 5 - enable explicitly once you want gare too.
ENABLE_GARE="${ENABLE_GARE:-false}"

while true; do
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) running ingest..."
    uv run agevolamatch ingest --db-path "$DB_PATH"

    if [ "$ENABLE_GARE" = "true" ]; then
        echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) running gare ingest..."
        uv run agevolamatch gare ingest --source all --db-path "$DB_PATH"
    fi

    if [ -n "$SUBSCRIPTIONS" ]; then
        echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) running alerts ($DRY_RUN_FLAG)..."
        uv run agevolamatch alerts run --subscriptions "$SUBSCRIPTIONS" --db-path "$DB_PATH" "$DRY_RUN_FLAG"
        if [ "$ENABLE_GARE" = "true" ]; then
            echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) running gare alerts ($DRY_RUN_FLAG)..."
            uv run agevolamatch gare alerts run --subscriptions "$SUBSCRIPTIONS" --db-path "$DB_PATH" "$DRY_RUN_FLAG"
        fi
    else
        echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) ALERT_SUBSCRIPTIONS_PATH not set, skipping alerts"
    fi

    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) sleeping ${INTERVAL}s"
    sleep "$INTERVAL"
done
