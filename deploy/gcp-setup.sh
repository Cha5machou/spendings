#!/usr/bin/env bash
# One-time setup of the Google Cloud resources. Safe to re-run: existing resources are kept.
# Run it yourself, signed in with YOUR Google account:   gcloud auth login
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
source deploy/gcp.env

ACCOUNT="$(gcloud config get-value account 2>/dev/null)"
echo "About to create resources in project '$PROJECT_ID' (region $REGION) as: $ACCOUNT"
read -r -p "Continue? [y/N] " answer
[[ "$answer" == "y" || "$answer" == "Y" ]] || { echo "Aborted."; exit 1; }

BUCKET="${PROJECT_ID}-${SERVICE}-documents"
INSTANCE="${SERVICE}-db"
DB_NAME="${SERVICE}"
DB_USER="${SERVICE}"
RUN_ACCOUNT="${SERVICE}-run@${PROJECT_ID}.iam.gserviceaccount.com"
REPOSITORY="${SERVICE}"

gcloud config set project "$PROJECT_ID" >/dev/null

echo "1/7 Enabling APIs..."
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  sqladmin.googleapis.com secretmanager.googleapis.com storage.googleapis.com identitytoolkit.googleapis.com

echo "2/7 Documents bucket (private, uniform access)..."
gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://$BUCKET" --location="$REGION" --uniform-bucket-level-access --public-access-prevention

echo "3/7 Cloud SQL PostgreSQL (smallest tier, daily backups)..."
gcloud sql instances describe "$INSTANCE" >/dev/null 2>&1 || \
  gcloud sql instances create "$INSTANCE" --database-version=POSTGRES_15 --region="$REGION" --tier=db-f1-micro \
    --storage-type=HDD --storage-size=10GB --availability-type=zonal --backup-start-time=03:00 --deletion-protection
gcloud sql databases describe "$DB_NAME" --instance="$INSTANCE" >/dev/null 2>&1 || gcloud sql databases create "$DB_NAME" --instance="$INSTANCE"

echo "4/7 Secrets..."
if ! gcloud secrets describe "${SERVICE}-db-password" >/dev/null 2>&1; then
  PASSWORD="$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32)"
  printf '%s' "$PASSWORD" | gcloud secrets create "${SERVICE}-db-password" --data-file=-
  gcloud sql users create "$DB_USER" --instance="$INSTANCE" --password="$PASSWORD"
fi
if ! gcloud secrets describe anthropic-api-key >/dev/null 2>&1; then
  read -r -s -p "Anthropic API key (leave empty to skip the assistant): " KEY; echo
  if [[ -n "$KEY" ]]; then printf '%s' "$KEY" | gcloud secrets create anthropic-api-key --data-file=-; fi
fi

echo "5/7 Service account for Cloud Run..."
gcloud iam service-accounts describe "$RUN_ACCOUNT" >/dev/null 2>&1 || gcloud iam service-accounts create "${SERVICE}-run" --display-name="Spendings Cloud Run"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$RUN_ACCOUNT" --role=roles/cloudsql.client --condition=None >/dev/null
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$RUN_ACCOUNT" --role=roles/storage.objectAdmin >/dev/null
for secret in "${SERVICE}-db-password" anthropic-api-key; do
  gcloud secrets describe "$secret" >/dev/null 2>&1 && \
    gcloud secrets add-iam-policy-binding "$secret" --member="serviceAccount:$RUN_ACCOUNT" --role=roles/secretmanager.secretAccessor >/dev/null
done

echo "6/7 Image repository..."
gcloud artifacts repositories describe "$REPOSITORY" --location="$REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "$REPOSITORY" --repository-format=docker --location="$REGION"

echo "7/7 Done."
echo
echo "Next:"
echo "  1. Firebase: open https://console.firebase.google.com, add project '$PROJECT_ID', enable Authentication > Google,"
echo "     create a Web app and copy apiKey into deploy/gcp.env (see docs/DEPLOY_GCP.md)."
echo "  2. Copy your data once:  see 'Move your data' in docs/DEPLOY_GCP.md"
echo "  3. Deploy:               ./deploy/gcp-deploy.sh"
