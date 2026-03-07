#!/bin/bash
# Deploy Factory to GCP — one-command setup.
# Creates VM, firewall rules, copies setup script, runs it.
#
# Usage: bash scripts/deploy-gcp.sh
#
# Idempotent — safe to run multiple times.

set -euo pipefail

PROJECT="factory-489520"
ZONE="northamerica-northeast1-a"
REGION="northamerica-northeast1"
VM_NAME="factory"
MACHINE_TYPE="e2-standard-4"
BOOT_DISK_SIZE="200GB"
IMAGE_FAMILY="ubuntu-2404-lts-amd64"
IMAGE_PROJECT="ubuntu-os-cloud"
TAG="factory"

echo "=== Factory GCP Deployment ==="
echo "Project:  $PROJECT"
echo "Zone:     $ZONE"
echo "Machine:  $MACHINE_TYPE (4 vCPU, 16 GB RAM)"
echo ""

# Ensure gcloud is configured
gcloud config set project "$PROJECT" --quiet
gcloud config set compute/zone "$ZONE" --quiet

# ── 1. Firewall rules ────────────────────────────────────────────────────────

echo "Creating firewall rules..."

for RULE in \
    "factory-allow-ssh:tcp:22" \
    "factory-allow-http:tcp:80" \
    "factory-allow-https:tcp:443" \
    "factory-allow-dashboard:tcp:9000" \
    "factory-allow-hatchet:tcp:8080"; do

    NAME=$(echo "$RULE" | cut -d: -f1)
    PROTO=$(echo "$RULE" | cut -d: -f2)
    PORT=$(echo "$RULE" | cut -d: -f3)

    if gcloud compute firewall-rules describe "$NAME" --project="$PROJECT" &>/dev/null; then
        echo "  $NAME already exists, skipping."
    else
        gcloud compute firewall-rules create "$NAME" \
            --project="$PROJECT" \
            --direction=INGRESS \
            --priority=1000 \
            --network=default \
            --action=ALLOW \
            --rules="$PROTO:$PORT" \
            --source-ranges=0.0.0.0/0 \
            --target-tags="$TAG" \
            --quiet
        echo "  Created $NAME ($PROTO:$PORT)"
    fi
done

# ── 2. Create VM ─────────────────────────────────────────────────────────────

echo ""
echo "Creating VM instance..."

if gcloud compute instances describe "$VM_NAME" --zone="$ZONE" --project="$PROJECT" &>/dev/null; then
    echo "  VM '$VM_NAME' already exists."
    STATUS=$(gcloud compute instances describe "$VM_NAME" --zone="$ZONE" --project="$PROJECT" --format='get(status)')
    if [ "$STATUS" != "RUNNING" ]; then
        echo "  Starting VM..."
        gcloud compute instances start "$VM_NAME" --zone="$ZONE" --project="$PROJECT" --quiet
    fi
else
    gcloud compute instances create "$VM_NAME" \
        --project="$PROJECT" \
        --zone="$ZONE" \
        --machine-type="$MACHINE_TYPE" \
        --image-family="$IMAGE_FAMILY" \
        --image-project="$IMAGE_PROJECT" \
        --boot-disk-size="$BOOT_DISK_SIZE" \
        --boot-disk-type=pd-ssd \
        --tags="$TAG" \
        --metadata=startup-script='#!/bin/bash
echo "VM created at $(date)" > /var/log/factory-init.log' \
        --quiet
    echo "  VM created."
fi

# Wait for SSH to be ready
echo "  Waiting for SSH..."
for i in $(seq 1 30); do
    if gcloud compute ssh "$VM_NAME" --zone="$ZONE" --project="$PROJECT" --command="echo ok" &>/dev/null; then
        break
    fi
    sleep 5
done
echo "  SSH ready."

# ── 3. Copy and run setup script ─────────────────────────────────────────────

echo ""
echo "Copying setup script to VM..."
gcloud compute scp scripts/setup-server.sh "$VM_NAME":~/setup-server.sh \
    --zone="$ZONE" --project="$PROJECT" --quiet

echo "Running setup on VM (this takes 3-5 minutes)..."
gcloud compute ssh "$VM_NAME" --zone="$ZONE" --project="$PROJECT" \
    --command="chmod +x ~/setup-server.sh && sudo ~/setup-server.sh"

# ── 4. Get external IP and print access info ─────────────────────────────────

EXTERNAL_IP=$(gcloud compute instances describe "$VM_NAME" \
    --zone="$ZONE" --project="$PROJECT" \
    --format='get(networkInterfaces[0].accessConfigs[0].natIP)')

echo ""
echo "============================================="
echo "  Factory deployed successfully!"
echo "============================================="
echo ""
echo "  VM:              $VM_NAME ($MACHINE_TYPE)"
echo "  External IP:     $EXTERNAL_IP"
echo "  Zone:            $ZONE"
echo ""
echo "  CEO Dashboard:   http://$EXTERNAL_IP:9000"
echo "  Hatchet:         http://$EXTERNAL_IP:8080"
echo ""
echo "  SSH:             gcloud compute ssh $VM_NAME --zone=$ZONE"
echo "  Update:          bash scripts/update.sh"
echo "  Logs:            gcloud compute ssh $VM_NAME --zone=$ZONE -- 'cd /home/factory/antzilla && docker compose logs -f'"
echo ""
echo "  First step: open the dashboard and complete the Setup Wizard."
echo "============================================="
