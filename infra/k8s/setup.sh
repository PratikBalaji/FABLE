#!/bin/bash
# F.A.B.L.E. — Local K8s cluster setup via kind.
# Prerequisites: docker, kind, kubectl
#
# Usage: ./infra/k8s/setup.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CLUSTER_NAME="fable"

echo "=== F.A.B.L.E. K8s Local Setup ==="

# 1. Create kind cluster
echo "[1/6] Creating kind cluster..."
if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    echo "  Cluster '${CLUSTER_NAME}' already exists, reusing."
else
    kind create cluster --config "${SCRIPT_DIR}/kind-config.yaml" --name "${CLUSTER_NAME}"
fi

# 2. Build Docker images
echo "[2/6] Building Docker images..."
docker build -f "${PROJECT_ROOT}/infra/docker/Dockerfile.coordinator" -t fable-coordinator:local "${PROJECT_ROOT}"
docker build -f "${PROJECT_ROOT}/infra/docker/Dockerfile.agent-group" -t fable-agent-group:local "${PROJECT_ROOT}"

# 3. Load images into kind
echo "[3/6] Loading images into kind cluster..."
kind load docker-image fable-coordinator:local --name "${CLUSTER_NAME}"
kind load docker-image fable-agent-group:local --name "${CLUSTER_NAME}"

# 4. Apply Kustomize manifests
echo "[4/6] Applying K8s manifests..."
kubectl apply -k "${SCRIPT_DIR}/overlays/local/"

# 5. Create per-pod secrets (F-030: least privilege — each pod gets only what it needs).
# The coordinator gets all secrets. Agent pods get only their LLM provider key +
# internal token. SUPABASE_SERVICE_ROLE_KEY and APP_ENCRYPTION_KEY are NEVER mounted
# onto agent pods.
echo "[5/6] Setting up secrets..."
if [ -f "${PROJECT_ROOT}/.env" ]; then
    # Source env to read individual values
    set -a; source "${PROJECT_ROOT}/.env"; set +a

    # Coordinator: all secrets
    kubectl delete secret coordinator-secrets -n fable --ignore-not-found
    kubectl create secret generic coordinator-secrets \
        --from-literal=OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-}" \
        --from-literal=OPENAI_API_KEY="${OPENAI_API_KEY:-}" \
        --from-literal=SUPABASE_URL="${SUPABASE_URL:-}" \
        --from-literal=SUPABASE_ANON_KEY="${SUPABASE_ANON_KEY:-}" \
        --from-literal=SUPABASE_SERVICE_ROLE_KEY="${SUPABASE_SERVICE_ROLE_KEY:-}" \
        --from-literal=APP_ENCRYPTION_KEY="${APP_ENCRYPTION_KEY:-}" \
        --from-literal=IDENTITY_COOKIE_SECRET="${IDENTITY_COOKIE_SECRET:-}" \
        --from-literal=AGENT_INTERNAL_TOKEN="${AGENT_INTERNAL_TOKEN:-}" \
        -n fable
    echo "  Coordinator secrets created."

    # Agent pods: only the LLM provider key + internal auth token
    kubectl delete secret agent-secrets -n fable --ignore-not-found
    kubectl create secret generic agent-secrets \
        --from-literal=OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-}" \
        --from-literal=OPENAI_API_KEY="${OPENAI_API_KEY:-}" \
        --from-literal=AGENT_INTERNAL_TOKEN="${AGENT_INTERNAL_TOKEN:-}" \
        -n fable
    echo "  Agent pod secrets created (no DB/encryption keys)."
else
    echo "  WARNING: No .env file found. Create secrets manually."
    echo "  Coordinator: kubectl create secret generic coordinator-secrets --from-literal=... -n fable"
    echo "  Agent pods:  kubectl create secret generic agent-secrets --from-literal=OPENROUTER_API_KEY=sk-... -n fable"
fi

# 6. Wait for rollout
echo "[6/6] Waiting for deployments..."
kubectl rollout status deployment/coordinator -n fable --timeout=120s
kubectl rollout status deployment/planning-pod -n fable --timeout=120s
kubectl rollout status deployment/execution-pod -n fable --timeout=120s
kubectl rollout status deployment/review-pod -n fable --timeout=120s

echo ""
echo "=== F.A.B.L.E. is running ==="
echo "  Coordinator: http://localhost:8000"
echo "  Health:      http://localhost:8000/health"
echo ""
echo "Pod status:"
kubectl get pods -n fable
