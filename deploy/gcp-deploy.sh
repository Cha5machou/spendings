#!/usr/bin/env bash
# Builds the image with Cloud Build and deploys it to Cloud Run. Run after deploy/gcp-setup.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
source deploy/gcp.env

: "${FIREBASE_API_KEY:?Set FIREBASE_API_KEY in deploy/gcp.env}"
: "${ALLOWED_EMAILS:?Set ALLOWED_EMAILS in deploy/gcp.env}"

ACCOUNT="$(gcloud config get-value account 2>/dev/null)"
echo "Deploying '$SERVICE' to project '$PROJECT_ID' ($REGION) as: $ACCOUNT"
read -r -p "Continue? [y/N] " answer
[[ "$answer" == "y" || "$answer" == "Y" ]] || { echo "Aborted."; exit 1; }

gcloud config set project "$PROJECT_ID" >/dev/null
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${SERVICE}/app:$(date +%Y%m%d-%H%M%S)"
BUCKET="${PROJECT_ID}-${SERVICE}-documents"
CONNECTION="${PROJECT_ID}:${REGION}:${SERVICE}-db"
RUN_ACCOUNT="${SERVICE}-run@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud builds submit --config deploy/cloudbuild.yaml --substitutions "_IMAGE=${IMAGE}" .

SECRETS="DB_PASSWORD=${SERVICE}-db-password:latest"
gcloud secrets describe anthropic-api-key >/dev/null 2>&1 && SECRETS="${SECRETS},ANTHROPIC_API_KEY=anthropic-api-key:latest"

# ^|^ makes '|' the separator so the comma list of e-mails survives.
gcloud run deploy "$SERVICE" \
  --image "$IMAGE" --region "$REGION" --service-account "$RUN_ACCOUNT" \
  --add-cloudsql-instances "$CONNECTION" \
  --set-env-vars "^|^AUTH_ENABLED=true|FIREBASE_PROJECT_ID=${PROJECT_ID}|FIREBASE_API_KEY=${FIREBASE_API_KEY}|FIREBASE_AUTH_DOMAIN=${FIREBASE_AUTH_DOMAIN}|ALLOWED_EMAILS=${ALLOWED_EMAILS}|STORAGE_BACKEND=gcs|GCS_BUCKET=${BUCKET}|DB_USER=${SERVICE}|DB_NAME=${SERVICE}|CLOUD_SQL_CONNECTION_NAME=${CONNECTION}|CORS_ORIGINS=[]" \
  --set-secrets "$SECRETS" \
  --allow-unauthenticated \
  --min-instances 0 --max-instances 2 --memory 512Mi --cpu 1 --concurrency 20 --timeout 300

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
echo
echo "Deployed: $URL"
echo "Add its domain ($(echo "$URL" | sed 's#https://##')) to Firebase > Authentication > Settings > Authorized domains."
