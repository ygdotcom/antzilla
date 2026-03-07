#!/bin/sh
# Factory worker entrypoint.
# Reads the Hatchet API token from the auto-generated config
# and exports it before starting the worker.

set -e

CONFIG_DIR="/hatchet/config"
TOKEN_FILE="$CONFIG_DIR/.hatchet-worker-token"

# Wait for Hatchet config to be generated (setup-config writes it)
echo "Waiting for Hatchet config..."
for i in $(seq 1 60); do
    if [ -f "$CONFIG_DIR/.env" ]; then
        break
    fi
    sleep 2
done

# Extract the API token from the generated .env file
if [ -f "$CONFIG_DIR/.env" ]; then
    echo "Loading Hatchet config..."
    export $(grep -v '^#' "$CONFIG_DIR/.env" | xargs)
fi

# The Hatchet SDK reads HATCHET_CLIENT_TOKEN from the environment
echo "Starting factory worker..."
exec python -m src.main
