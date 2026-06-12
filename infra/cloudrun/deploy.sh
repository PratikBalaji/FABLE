#!/usr/bin/env bash
# F.A.B.L.E. backend → Google Cloud Run deploy script (P6c).
#
# Free-tier budget: 2M req/mo, 360k vCPU-sec, 180k GB-sec, scales to zero.
# Cold start target: <8s with the trimmed image.
#
# Prereqs (one-time):
#   1. gcloud CLI installed + `gcloud auth login`
#   2. `gcloud config set project <PROJECT_ID>`
#   3. APIs enabled: run.googleapis.com, cloudbuild.googleapis.com,
#      artifactregistry.googleapis.com, secretmanager.googleapis.com (optional)
#   4. Populate the secrets below in Secret Manager (or pass via --set-env-vars
#      for non-secret config). NEVER commit secret values.
#
# Usage:
#   bash infra/cloudrun/deploy.sh
#
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-fable-backend}"
REGION="${REGION:-us-central1}"
MEMORY="${MEMORY:-512Mi}"
CPU="${CPU:-1}"
MAX_INSTANCES="${MAX_INSTANCES:-5}"
MIN_INSTANCES="${MIN_INSTANCES:-0}"
CONCURRENCY="${CONCURRENCY:-80}"

echo "▶ Deploying ${SERVICE_NAME} to Cloud Run (${REGION})..."
echo "  memory=${MEMORY} cpu=${CPU} max-instances=${MAX_INSTANCES} min-instances=${MIN_INSTANCES}"
echo

# --set-env-vars: NON-SECRET runtime config only.
# --set-secrets:  pulled from Secret Manager. Create each with:
#                 echo -n "<value>" | gcloud secrets create <NAME> --data-file=-
# Adjust the secret names if you already have them under different IDs.

gcloud run deploy "${SERVICE_NAME}" \
  --source . \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --memory "${MEMORY}" \
  --cpu "${CPU}" \
  --max-instances "${MAX_INSTANCES}" \
  --min-instances "${MIN_INSTANCES}" \
  --concurrency "${CONCURRENCY}" \
  --timeout 300 \
  --port 8080 \
  --set-env-vars="USE_SUPABASE=true,USE_JWKS=true,COOKIE_SAMESITE=none,COOKIE_SECURE=true,EMBEDDINGS_MODEL=text-embedding-3-small,EMBEDDINGS_DIMENSIONS=384,PII_ENABLED=true,PII_LLM_FALLBACK=true,GUARDRAILS_ENABLED=true,ADVERSARIAL_MAX_ROUNDS=2" \
  --set-secrets="OPENROUTER_API_KEY=fable-openrouter-key:latest,OPENAI_API_KEY=fable-openai-key:latest,SUPABASE_URL=fable-supabase-url:latest,SUPABASE_ANON_KEY=fable-supabase-anon:latest,SUPABASE_SERVICE_ROLE_KEY=fable-supabase-service:latest,APP_ENCRYPTION_KEY=fable-app-encryption:latest,IDENTITY_COOKIE_SECRET=fable-identity-cookie:latest"

echo
echo "✓ Deployed. Service URL:"
gcloud run services describe "${SERVICE_NAME}" \
  --region "${REGION}" --format='value(status.url)'
