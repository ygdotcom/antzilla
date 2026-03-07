#!/bin/bash
# One-command local setup for the Factory.
# Usage: bash scripts/setup.sh

set -e

echo "=== Factory Local Setup ==="
echo ""

# 1. Create .env if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env

    # Generate secure defaults
    POSTGRES_PW=$(openssl rand -hex 16)
    PLAUSIBLE_SK=$(openssl rand -base64 64 | tr -d '\n')

    # Replace placeholders (macOS-compatible sed)
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/changeme_use_a_real_password/$POSTGRES_PW/g" .env
        sed -i '' "s|changeme_generate_with_openssl_rand_base64_64|$PLAUSIBLE_SK|g" .env
    else
        sed -i "s/changeme_use_a_real_password/$POSTGRES_PW/g" .env
        sed -i "s|changeme_generate_with_openssl_rand_base64_64|$PLAUSIBLE_SK|g" .env
    fi

    echo "  .env created with secure passwords."
else
    echo "  .env already exists, skipping."
fi

# 2. Start infrastructure services first (Postgres, Hatchet)
echo ""
echo "Starting infrastructure..."
docker compose up -d postgres
echo "  Waiting for Postgres..."
sleep 5

echo "Running Hatchet migration + setup..."
docker compose up -d hatchet-migration
docker compose up hatchet-setup 2>&1 | tail -5
echo "  Hatchet configured."

# 3. Start all services
echo ""
echo "Starting all services..."
docker compose up -d

# 4. Wait and show status
echo ""
echo "Waiting for services to start..."
sleep 10

echo ""
echo "=== Service Status ==="
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo "=== Access Points ==="
echo "  Hatchet Dashboard:  http://localhost:8080  (admin@example.com / Admin123!!)"
echo "  CEO Dashboard:      http://localhost:9000  (admin / factory)"
echo "  Plausible:          http://localhost:8000"
echo "  Uptime Kuma:        http://localhost:3001"
echo "  Postgres:           localhost:5432"
echo ""
echo "=== Generate Hatchet API Token ==="
echo "  Run this to get a token for external workers:"
echo "  docker compose run --no-deps hatchet-setup /hatchet/hatchet-admin token create --config /hatchet/config --tenant-id 707d0855-80ab-4e1f-a156-f1c4546cbf52"
echo ""
echo "=== Run Tests ==="
echo "  python -m venv .venv && source .venv/bin/activate"
echo "  pip install -e '.[dev]'"
echo "  python -m pytest tests/ -v"
echo ""
echo "=== Seed Test Data (requires running Postgres) ==="
echo "  python -m scripts.seed_test_data"
echo ""
echo "Setup complete!"
