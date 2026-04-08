#!/bin/bash
# =============================================================================
# Manual deployment: Build Docker image, push to ACR, restart App Service
# Usage: ./deploy.sh [tag]
# =============================================================================
set -euo pipefail

ACR_NAME="${ACR_NAME:-trendsresearchacr}"
IMAGE_NAME="${IMAGE_NAME:-trends-research-app}"
TAG="${1:-latest}"
APP_NAME="${APP_NAME:-trends-research-app}"
RESOURCE_GROUP="${RESOURCE_GROUP:-trends-research-rg}"

ACR_LOGIN_SERVER="${ACR_NAME}.azurecr.io"
FULL_IMAGE="${ACR_LOGIN_SERVER}/${IMAGE_NAME}:${TAG}"

echo "============================================="
echo "  Deploying Trends Research App"
echo "  ACR:   ${ACR_LOGIN_SERVER}"
echo "  Image: ${FULL_IMAGE}"
echo "  App:   ${APP_NAME}"
echo "============================================="

# Check whether Docker is available locally
if command -v docker &>/dev/null && docker info &>/dev/null; then
  USE_DOCKER=true
else
  echo ">>> Docker not available locally – will use ACR cloud build"
  USE_DOCKER=false
fi

if [ "$USE_DOCKER" = true ]; then
  echo ">>> Logging in to ACR..."
  az acr login --name "${ACR_NAME}"

  echo ">>> Building Docker image locally..."
  docker build -f Dockerfile.api -t "${FULL_IMAGE}" .
  [ "${TAG}" != "latest" ] && docker tag "${FULL_IMAGE}" "${ACR_LOGIN_SERVER}/${IMAGE_NAME}:latest"

  echo ">>> Pushing to ACR..."
  docker push "${FULL_IMAGE}"
  [ "${TAG}" != "latest" ] && docker push "${ACR_LOGIN_SERVER}/${IMAGE_NAME}:latest"
else
  echo ">>> Building and pushing image via ACR Tasks (cloud build)..."
  az acr build \
    --registry "${ACR_NAME}" \
    --image "${IMAGE_NAME}:${TAG}" \
    --file Dockerfile.api \
    .
  if [ "${TAG}" != "latest" ]; then
    az acr import \
      --name "${ACR_NAME}" \
      --source "${ACR_LOGIN_SERVER}/${IMAGE_NAME}:${TAG}" \
      --image "${IMAGE_NAME}:latest" \
      --force
  fi
fi

echo ">>> Restarting App Service..."
az webapp restart --name "${APP_NAME}" --resource-group "${RESOURCE_GROUP}"

echo ""
echo "============================================="
echo "  Done! https://${APP_NAME}.azurewebsites.net"
echo "============================================="
