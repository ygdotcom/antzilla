#!/bin/bash
# Update the factory on GCP — pull latest code, rebuild, restart.
#
# Usage: bash scripts/update.sh

set -euo pipefail

PROJECT="factory-489520"
ZONE="northamerica-northeast1-a"
VM_NAME="factory"

echo "=== Factory Update ==="
echo "Pulling latest code and restarting services..."

gcloud compute ssh "$VM_NAME" \
    --zone="$ZONE" \
    --project="$PROJECT" \
    --command="cd /home/factory/antzilla && sudo git pull && sudo docker compose down && sudo docker compose up -d --build"

EXTERNAL_IP=$(gcloud compute instances describe "$VM_NAME" \
    --zone="$ZONE" --project="$PROJECT" \
    --format='get(networkInterfaces[0].accessConfigs[0].natIP)')

echo ""
echo "Update complete."
echo "Dashboard: http://$EXTERNAL_IP:9000"
