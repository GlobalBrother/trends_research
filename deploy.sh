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
RESOURCE_GROUP="${RESOURCE_GROUP:-GB_Reporting_RG}"

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

APP_SERVICE_PLAN="${APP_SERVICE_PLAN:-trends-research-plan}"
APP_SERVICE_SKU="${APP_SERVICE_SKU:-B1}"

# Ensure the resource group exists
if ! az group show --name "${RESOURCE_GROUP}" &>/dev/null; then
  echo ">>> Creating resource group ${RESOURCE_GROUP}..."
  az group create --name "${RESOURCE_GROUP}" --location "${LOCATION:-westeurope}" --output none
fi

# Ensure the App Service Plan exists
if ! az appservice plan show --name "${APP_SERVICE_PLAN}" --resource-group "${RESOURCE_GROUP}" &>/dev/null; then
  echo ">>> Creating App Service Plan ${APP_SERVICE_PLAN}..."
  az appservice plan create \
    --name "${APP_SERVICE_PLAN}" \
    --resource-group "${RESOURCE_GROUP}" \
    --sku "${APP_SERVICE_SKU}" \
    --is-linux \
    --output none
fi

# Ensure the Web App exists; create or just restart
if az webapp show --name "${APP_NAME}" --resource-group "${RESOURCE_GROUP}" &>/dev/null; then
  echo ">>> Updating container image and restarting App Service..."
  az webapp config container set \
    --name "${APP_NAME}" \
    --resource-group "${RESOURCE_GROUP}" \
    --container-image-name "${FULL_IMAGE}" \
    --container-registry-url "https://${ACR_LOGIN_SERVER}" \
    --output none
  az webapp restart --name "${APP_NAME}" --resource-group "${RESOURCE_GROUP}"
else
  echo ">>> Creating Web App ${APP_NAME}..."
  az webapp create \
    --name "${APP_NAME}" \
    --resource-group "${RESOURCE_GROUP}" \
    --plan "${APP_SERVICE_PLAN}" \
    --container-image-name "${FULL_IMAGE}" \
    --container-registry-url "https://${ACR_LOGIN_SERVER}" \
    --output none

  echo ">>> Configuring app settings..."
  az webapp config appsettings set \
    --name "${APP_NAME}" \
    --resource-group "${RESOURCE_GROUP}" \
    --settings WEBSITES_PORT=8000 WEBSITES_ENABLE_APP_SERVICE_STORAGE=false \
    --output none
fi

echo ""
echo "============================================="
echo "  Done! https://${APP_NAME}.azurewebsites.net"
echo "============================================="
