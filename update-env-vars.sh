#!/bin/bash
# Quick script to update Container App environment variables without full provision

echo "Updating Container App environment variables..."

# Get values from azd environment
TENANT_ID=$(azd env get-values | grep AZURE_AD_TENANT_ID | cut -d'=' -f2 | tr -d '"')
CLIENT_ID=$(azd env get-values | grep AZURE_AD_CLIENT_ID | cut -d'=' -f2 | tr -d '"')

echo "Azure AD Tenant ID: $TENANT_ID"
echo "Azure AD Client ID: $CLIENT_ID"

# Update using azd's built-in Azure authentication
az containerapp update \
  --name ca-farmacia-agent-6fqtj \
  --resource-group rg-farmacia-agent-6fqtj \
  --set-env-vars \
    AZURE_AD_TENANT_ID="$TENANT_ID" \
    AZURE_AD_CLIENT_ID="$CLIENT_ID" \
  --output table

echo "✅ Environment variables updated!"
echo "Check Azure Portal → Container App → Containers → Environment variables"
