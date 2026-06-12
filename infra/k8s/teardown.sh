#!/bin/bash
# F.A.B.L.E. — Tear down local K8s cluster.
# Usage: ./infra/k8s/teardown.sh
set -euo pipefail

CLUSTER_NAME="fable"

echo "Deleting kind cluster '${CLUSTER_NAME}'..."
kind delete cluster --name "${CLUSTER_NAME}"
echo "Done. Local images (fable-coordinator:local, fable-agent-group:local) still exist in Docker."
echo "Run 'docker rmi fable-coordinator:local fable-agent-group:local' to remove them."
