#!/bin/bash
set -euo pipefail

BUNDLE_DIR="${1:-/opt/yt-rag-app/deploy-bundle}"

cd "${BUNDLE_DIR}"

kubectl apply -f namespace.yml
kubectl apply -f configmap.yml
kubectl apply -f api-service.yml
kubectl apply -f chat-service.yml
kubectl apply -f api-deployment.yml
kubectl apply -f chat-deployment.yml
kubectl apply -f worker-deployment.yml
kubectl apply -f worker-hpa.yml
kubectl apply -f gateway.yml
kubectl apply -f httproute.yml

kubectl -n video-rag rollout status deploy/api
kubectl -n video-rag rollout status deploy/chat
kubectl -n video-rag rollout status deploy/worker
