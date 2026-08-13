#!/bin/bash
set -euo pipefail

kubectl -n video-rag get deploy/api deploy/chat deploy/worker
kubectl -n video-rag get hpa worker
kubectl -n video-rag get svc api-service chat-service
kubectl -n video-rag get gateway video-rag-private-gateway
kubectl -n video-rag get httproute video-rag-routes

kubectl -n video-rag rollout status deploy/api
kubectl -n video-rag rollout status deploy/chat
kubectl -n video-rag rollout status deploy/worker
