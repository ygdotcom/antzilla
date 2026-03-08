#!/bin/sh
# Factory worker entrypoint.
# Uses HATCHET_CLIENT_TOKEN from the container environment (set in .env / docker-compose).

set -e

echo "Starting factory worker..."
echo "HATCHET_CLIENT_TOKEN set: $([ -n "$HATCHET_CLIENT_TOKEN" ] && echo 'yes' || echo 'NO — worker will fail')"

exec python -m src.main
