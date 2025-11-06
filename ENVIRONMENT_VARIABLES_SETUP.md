# Environment Variables Setup Guide

This guide explains how to configure all environment variables for your call center voice agent application using `azd` commands.

## 📋 Complete Environment Variables List

All environment variables are now managed through Azure Bicep and can be set using `azd env set` commands.

### ✅ Already Configured (Automatic)

These are automatically configured during deployment:
- ✅ `AZURE_VOICE_LIVE_ENDPOINT` - From AI Services deployment
- ✅ `AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID` - From Managed Identity
- ✅ `VOICE_LIVE_MODEL` - From modelName parameter
- ✅ `ACS_CONNECTION_STRING` - From ACS deployment (stored in Key Vault)
- ✅ `DEBUG_MODE` - Set to `true` by default

### 🔐 Secrets (Stored in Key Vault)

These secrets are securely stored in Azure Key Vault and referenced by the Container App:

#### 1. Azure Search API Key
```bash
azd env set AZURE_SEARCH_API_KEY "<your-search-api-key>"
```
**How to get it:**
- Azure Portal → Azure AI Search → Keys → Primary admin key

#### 2. Azure Storage Connection String
```bash
azd env set AZURE_STORAGE_CONNECTION_STRING "<your-storage-connection-string>"
```
**How to get it:**
- Azure Portal → Storage Account → Access keys → Connection string

#### 3. Azure OpenAI API Key
```bash
azd env set AZURE_OPENAI_KEY "<your-openai-api-key>"
```
**How to get it:**
- Azure Portal → Azure OpenAI → Keys and Endpoint → KEY 1

### 📝 Configuration Values (Non-Secrets)

These configuration values are environment variables (not secrets):

#### 4. Azure AD Authentication
```bash
azd env set AZURE_AD_TENANT_ID "3c2f8fc7-162c-4bfa-b056-595e813f4f40"
azd env set AZURE_AD_CLIENT_ID "b51dfa5b-0077-43f7-ba16-d8b436e7d619"
```
**How to get them:**
- Tenant ID: Azure Portal → Azure Active Directory → Overview → Tenant ID
- Client ID: Azure Portal → App Registrations → Your API app → Application (client) ID

#### 5. Azure Search Configuration
```bash
azd env set AZURE_SEARCH_ENDPOINT "https://your-search-service.search.windows.net"
azd env set AZURE_SEARCH_INDEX "your-index-name"
azd env set AZURE_SEARCH_SEMANTIC_CONFIG "your-semantic-config"
azd env set AZURE_SEARCH_TOP_N "5"
azd env set AZURE_SEARCH_STRICTNESS "3"
```
**How to get them:**
- Endpoint: Azure Portal → Azure AI Search → Overview → Url
- Index: Azure Portal → Azure AI Search → Indexes → (your index name)
- Semantic Config: The name you gave to your semantic configuration
- Top N: Number of results to return (default: 5)
- Strictness: Search strictness level 1-5 (default: 3)

#### 6. Azure OpenAI Configuration
```bash
azd env set AZURE_OPENAI_ENDPOINT "https://your-openai.openai.azure.com/"
azd env set AZURE_OPENAI_EMBEDDING_DEPLOYMENT "text-embedding-ada-002"
```
**How to get them:**
- Endpoint: Azure Portal → Azure OpenAI → Keys and Endpoint → Endpoint
- Embedding Deployment: Your embedding model deployment name

## 🚀 Quick Setup Script

Run all these commands at once (replace with your actual values):

```bash
# Navigate to project directory
cd /workspaces/call-center-voice-agent-accelerator

# Azure AD Authentication
azd env set AZURE_AD_TENANT_ID "3c2f8fc7-162c-4bfa-b056-595e813f4f40"
azd env set AZURE_AD_CLIENT_ID "b51dfa5b-0077-43f7-ba16-d8b436e7d619"

# Azure Search (replace with your values)
azd env set AZURE_SEARCH_ENDPOINT "https://your-search.search.windows.net"
azd env set AZURE_SEARCH_INDEX "your-index-name"
azd env set AZURE_SEARCH_API_KEY "your-api-key"
azd env set AZURE_SEARCH_SEMANTIC_CONFIG "your-semantic-config"
azd env set AZURE_SEARCH_TOP_N "5"
azd env set AZURE_SEARCH_STRICTNESS "3"

# Azure Storage (replace with your value)
azd env set AZURE_STORAGE_CONNECTION_STRING "DefaultEndpointsProtocol=https;AccountName=..."

# Azure OpenAI (replace with your values)
azd env set AZURE_OPENAI_ENDPOINT "https://your-openai.openai.azure.com/"
azd env set AZURE_OPENAI_KEY "your-openai-key"
azd env set AZURE_OPENAI_EMBEDDING_DEPLOYMENT "text-embedding-ada-002"

# Deploy with all variables
azd deploy
```

## 📊 Verify Environment Variables

### Check Local azd Environment
```bash
azd env get-values
```

### Check Container App (After Deployment)

**Option 1: Azure Portal**
1. Go to Azure Portal → Resource Groups → `rg-farmacia-agent-6fqtj`
2. Click on Container App → Containers → Environment variables
3. Verify all variables are present

**Option 2: Azure CLI**
```bash
az containerapp show \
  --name ca-farmacia-agent-6fqtj \
  --resource-group rg-farmacia-agent-6fqtj \
  --query "properties.template.containers[0].env" \
  -o table
```

## 🔄 Update Variables After Deployment

If you need to change any variable:

```bash
# Update the value
azd env set AZURE_SEARCH_INDEX "new-index-name"

# Redeploy
azd deploy
```

## 🔒 Security Best Practices

### ✅ What's Secure

1. **Secrets in Key Vault**: API keys and connection strings are stored in Azure Key Vault
2. **Environment variables for config**: Non-secret values are environment variables
3. **Managed Identity**: Container App uses managed identity to access Key Vault (no keys needed)
4. **RBAC**: Proper role assignments for accessing resources

### ⚠️ Important Notes

1. **Never commit secrets to Git**: The `.env` file is in `.gitignore`
2. **Use `azd env set` for all values**: Don't manually edit Azure Portal for consistency
3. **Secrets are references**: Container App gets Key Vault URIs, not actual secret values
4. **Local development**: For local dev, copy values to `.env` file (don't commit it!)

## 📝 Environment Variables Summary Table

| Variable | Type | Required | Default | Where to Get It |
|----------|------|----------|---------|-----------------|
| `AZURE_AD_TENANT_ID` | Config | Optional* | - | Azure AD → Overview |
| `AZURE_AD_CLIENT_ID` | Config | Optional* | - | App Registrations → API app |
| `AZURE_SEARCH_ENDPOINT` | Config | Yes | - | Azure AI Search → Overview |
| `AZURE_SEARCH_INDEX` | Config | Yes | - | Azure AI Search → Indexes |
| `AZURE_SEARCH_API_KEY` | **Secret** | Yes | - | Azure AI Search → Keys |
| `AZURE_SEARCH_SEMANTIC_CONFIG` | Config | Optional | - | Your semantic config name |
| `AZURE_SEARCH_TOP_N` | Config | No | `5` | - |
| `AZURE_SEARCH_STRICTNESS` | Config | No | `3` | - |
| `AZURE_STORAGE_CONNECTION_STRING` | **Secret** | Yes | - | Storage Account → Access keys |
| `AZURE_OPENAI_ENDPOINT` | Config | Yes | - | Azure OpenAI → Keys and Endpoint |
| `AZURE_OPENAI_KEY` | **Secret** | Yes | - | Azure OpenAI → Keys and Endpoint |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | Config | Yes | - | Your embedding deployment name |

\* *Optional* means authentication is disabled if not provided. For production, these should be set.

## 🐛 Troubleshooting

### Issue: Variables not showing in Container App

**Solution:**
```bash
# Check they're set locally
azd env get-values

# If missing, set them
azd env set VARIABLE_NAME "value"

# Redeploy
azd deploy
```

### Issue: Container App fails to start

**Solution:**
1. Check Container App logs: Azure Portal → Container App → Log stream
2. Look for "Missing environment variable" errors
3. Verify secrets exist in Key Vault
4. Check managed identity has Key Vault Secrets User role

### Issue: Key Vault secrets not accessible

**Solution:**
```bash
# Verify role assignments exist
az role assignment list \
  --assignee <managed-identity-object-id> \
  --scope <key-vault-id>

# If missing, redeploy infrastructure
azd provision
```

## 📚 Related Documentation

- **`AZURE_AD_CONTAINER_APP_DEPLOYMENT.md`** - Azure AD authentication deployment
- **`AZURE_AD_AUTH_SETUP.md`** - Complete Azure AD setup guide
- **`server/.env-sample-with-auth.txt`** - Local development environment template

---

**Next Steps:**
1. ✅ Set all required environment variables using `azd env set`
2. ✅ Deploy with `azd deploy`
3. ✅ Verify variables in Azure Portal
4. ✅ Test your application
