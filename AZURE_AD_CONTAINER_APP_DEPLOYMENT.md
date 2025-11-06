# Azure AD Authentication - Container App Deployment Guide

This guide explains how to deploy your application with Azure AD authentication using Container App environment variables (instead of .env files).

## ✅ What Was Updated

The following files were modified to support Azure AD authentication via Container App environment variables:

1. **`infra/modules/containerapp.bicep`** - Added Azure AD parameters and environment variables
2. **`infra/main.bicep`** - Added Azure AD parameters to main deployment
3. **`infra/main.parameters.json`** - Added parameter mappings for azd

## 📋 Deployment Steps

### Step 1: Set Azure AD Environment Variables Locally

After completing the Azure Portal setup (Steps 1-5 in `AZURE_AD_AUTH_SETUP.md`), set the Azure AD values in your local azd environment:

```bash
# Navigate to your project directory
cd /workspaces/call-center-voice-agent-accelerator

# Set Azure AD Tenant ID
azd env set AZURE_AD_TENANT_ID "<your-tenant-id>"

# Set Azure AD Client ID (from your API app: farmacia-pepe-bot-api)
azd env set AZURE_AD_CLIENT_ID "<your-api-app-client-id>"
```

**To get these values:**

1. **Tenant ID**:
   - Azure Portal → Azure Active Directory → Overview → Tenant ID
   - Example: `12345678-1234-1234-1234-123456789abc`

2. **Client ID** (API app):
   - Azure Portal → App Registrations → `farmacia-pepe-bot-api` → Overview → Application (client) ID
   - Example: `b51dfa5b-0077-43f7-ba16-d8b436e7d619`

### Step 2: Deploy to Azure

Deploy your infrastructure and application:

```bash
# Deploy everything (infrastructure + container app)
azd up

# OR deploy just the infrastructure if you've already provisioned
azd provision

# OR deploy just the container app if infrastructure exists
azd deploy
```

### Step 3: Verify Environment Variables in Azure Portal

After deployment, verify the environment variables are set:

1. Go to **Azure Portal** → **Resource Groups** → `rg-<your-env-name>-<suffix>`
2. Click on your **Container App** (starts with `ca-`)
3. Go to **Containers** → **Environment variables**
4. Verify these variables exist:
   - `AZURE_AD_TENANT_ID` = your tenant ID
   - `AZURE_AD_CLIENT_ID` = your API app client ID

### Step 4: Test Authentication

Your API endpoints are now protected. Test them using one of these methods:

#### Method 1: Using the test_auth.py Script

```bash
cd server
python test_auth.py
```

When prompted:
- **Client ID**: Your client app's ID (`farmacia-pepe-bot-client`)
- **Client Secret**: The secret you created for the client app

#### Method 2: Using curl

```bash
# Replace <container-app-url> with your actual Container App FQDN
# Example: https://ca-myenv-abc123.azurecontainerapps.io

curl -X GET "https://<container-app-url>/api/documents" \
  -H "Authorization: Bearer <your-access-token>"
```

#### Method 3: Using Postman

1. Create a new request: `GET https://<container-app-url>/api/documents`
2. Go to **Authorization** tab
3. Type: **OAuth 2.0**
4. Configure:
   - Grant Type: **Client Credentials**
   - Access Token URL: `https://login.microsoftonline.com/<tenant-id>/oauth2/v2.0/token`
   - Client ID: Your client app's ID
   - Client Secret: Your client app's secret
   - Scope: `api://<api-app-client-id>/.default`
5. Click **Get New Access Token**
6. Use the token to make requests

## 🔧 How to Update Environment Variables After Deployment

If you need to change the Azure AD values after deployment:

### Option A: Using azd (Recommended)

```bash
# Update the value
azd env set AZURE_AD_TENANT_ID "<new-tenant-id>"
azd env set AZURE_AD_CLIENT_ID "<new-client-id>"

# Redeploy
azd deploy
```

### Option B: Using Azure Portal

1. Go to your **Container App** in Azure Portal
2. Click **Containers** in the left menu
3. Click **Edit and deploy** → **Create new revision**
4. Scroll to **Environment variables**
5. Update `AZURE_AD_TENANT_ID` and/or `AZURE_AD_CLIENT_ID`
6. Click **Create** to deploy the new revision

### Option C: Using Azure CLI

```bash
# Get your container app name and resource group
RESOURCE_GROUP="rg-<your-env-name>-<suffix>"
CONTAINER_APP="ca-<your-env-name>-<suffix>"

# Update environment variables
az containerapp update \
  --name $CONTAINER_APP \
  --resource-group $RESOURCE_GROUP \
  --set-env-vars \
    AZURE_AD_TENANT_ID="<your-tenant-id>" \
    AZURE_AD_CLIENT_ID="<your-client-id>"
```

## 🔒 Security Best Practices

### ✅ What's Secured

- Environment variables are injected at runtime (not in code)
- Secrets (like client secrets) should NEVER be in environment variables
- Client apps use their own client secrets (not in Container App)
- Authentication is handled by Azure AD (no credentials stored in app)

### ⚠️ Important Notes

1. **Never commit secrets**: The `AZURE_AD_TENANT_ID` and `AZURE_AD_CLIENT_ID` are not secrets, but don't commit them to git
2. **Client secrets are for clients**: The client secret is used by client apps (Postman, frontend) to get tokens, NOT by your Container App
3. **Use managed identity when possible**: Your Container App already uses managed identity for Azure services (AI Services, Key Vault, etc.)
4. **Graceful degradation**: If `AZURE_AD_TENANT_ID` or `AZURE_AD_CLIENT_ID` are empty, authentication is disabled (for local development)

## 📊 Environment Variables Reference

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `AZURE_AD_TENANT_ID` | Optional* | Your Azure AD tenant ID | `12345678-1234-1234-1234-123456789abc` |
| `AZURE_AD_CLIENT_ID` | Optional* | Your API app's client ID | `b51dfa5b-0077-43f7-ba16-d8b436e7d619` |
| `AZURE_AD_AUDIENCE` | Optional | Token audience (defaults to `api://{CLIENT_ID}`) | `api://b51dfa5b-0077-43f7-ba16-d8b436e7d619` |

\* **Optional** means authentication is disabled if not provided. For production, these should be set.

## 🐛 Troubleshooting

### Issue: Environment variables not showing in Container App

**Solution**: 
- Run `azd env get-values` to verify they're set locally
- Run `azd deploy` again to update the Container App
- Check the Container App logs: Azure Portal → Container App → Log stream

### Issue: Authentication not working (401 Unauthorized)

**Solution**:
- Verify environment variables are set: Azure Portal → Container App → Containers → Environment variables
- Check that `AZURE_AD_TENANT_ID` and `AZURE_AD_CLIENT_ID` match your Azure AD app
- Verify your client app has the correct scope and permissions
- Check Container App logs for authentication errors

### Issue: Deployment fails with Bicep errors

**Solution**:
- Make sure you're using the latest code with Azure AD support
- Run `azd env set` for both variables before deploying
- Check `infra/main.bicep` and `infra/modules/containerapp.bicep` for syntax errors

## 🎯 Next Steps

1. ✅ Complete Azure Portal setup (Steps 1-5 in `AZURE_AD_AUTH_SETUP.md`)
2. ✅ Set environment variables locally (`azd env set`)
3. ✅ Deploy to Azure (`azd up`)
4. ✅ Verify environment variables in Azure Portal
5. ✅ Test authentication using Postman or test script
6. 🔄 Integrate authentication in your frontend app (see `AZURE_AD_AUTH_SETUP.md` Step 6)

## 📚 Related Documentation

- **`AZURE_AD_AUTH_SETUP.md`** - Complete Azure AD setup guide with Azure Portal steps
- **`AZURE_AD_IMPLEMENTATION_SUMMARY.md`** - Quick reference for what was implemented
- **`server/test_auth.py`** - Automated testing script for authentication
- **`server/.env-sample-with-auth.txt`** - Environment variable template (for local development)

---

**Questions?** Check the troubleshooting section in `AZURE_AD_AUTH_SETUP.md` or review the Container App logs in Azure Portal.
