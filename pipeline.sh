#!/usr/bin/env bash
# Runs the full content refresh once, then exits. Designed to be invoked by a
# scheduler (cron, Kubernetes CronJob, Azure Container Instances, etc.).
set -euo pipefail

echo "[$(date -u +%FT%TZ)] Export starting"
python hubspot_export.py --clean

echo "[$(date -u +%FT%TZ)] Sync starting"
python kb_sync.py

echo "[$(date -u +%FT%TZ)] Pipeline complete"
