#!/bin/bash
# Post-provision hook script
# Automatically configures the environment after Azure resources are provisioned

set -e  # Exit on error

echo ""
echo "=========================================="
echo "Post-Provision Configuration"
echo "=========================================="
echo ""

# Get environment name
ENV_NAME=$(azd env get-values | grep AZURE_ENV_NAME | cut -d'=' -f2 | tr -d '"')
echo "Environment: $ENV_NAME"

# Get resource group name
RESOURCE_GROUP=$(azd env get-values | grep AZURE_RESOURCE_GROUP | cut -d'=' -f2 | tr -d '"')
echo "Resource Group: $RESOURCE_GROUP"

# Get tenant ID
TENANT_ID=$(az account show --query tenantId -o tsv)
echo "Tenant ID: $TENANT_ID"

echo ""
echo "=========================================="
echo "Step 1: Configure Azure AD App Registration"
echo "=========================================="
echo ""

# Check if Azure AD variables are already set
EXISTING_CLIENT_ID=$(azd env get-values | grep AZURE_AD_CLIENT_ID | cut -d'=' -f2 | tr -d '"' || echo "")

if [ -z "$EXISTING_CLIENT_ID" ]; then
    echo "Creating Azure AD App Registration..."
    
    # Create or get existing App Registration
    APP_NAME="Call Center Voice Agent API - $ENV_NAME"
    
    # Try to find existing app
    EXISTING_APP=$(az ad app list --display-name "$APP_NAME" --query "[0].appId" -o tsv 2>/dev/null || echo "")
    
    if [ -z "$EXISTING_APP" ]; then
        echo "Creating new App Registration: $APP_NAME"
        CLIENT_ID=$(az ad app create \
            --display-name "$APP_NAME" \
            --sign-in-audience AzureADMyOrg \
            --query appId -o tsv)
        echo "✓ Created App Registration: $CLIENT_ID"
    else
        CLIENT_ID="$EXISTING_APP"
        echo "✓ Found existing App Registration: $CLIENT_ID"
    fi
    
    # Set Azure AD environment variables
    echo "Setting Azure AD environment variables..."
    azd env set AZURE_AD_TENANT_ID "$TENANT_ID"
    azd env set AZURE_AD_CLIENT_ID "$CLIENT_ID"
    echo "✓ Azure AD variables configured"
else
    echo "✓ Azure AD already configured (Client ID: $EXISTING_CLIENT_ID)"
fi

echo ""
echo "=========================================="
echo "Step 2: Configure Search Index Name"
echo "=========================================="
echo ""

# Check if search index name is set
EXISTING_INDEX=$(azd env get-values | grep AZURE_SEARCH_INDEX | cut -d'=' -f2 | tr -d '"' || echo "")

if [ -z "$EXISTING_INDEX" ] || [ "$EXISTING_INDEX" = "null" ]; then
    echo "Setting default search index name..."
    azd env set AZURE_SEARCH_INDEX "pharmacy-knowledge-base"
    echo "✓ Search index name set to: pharmacy-knowledge-base"
else
    echo "✓ Search index already configured: $EXISTING_INDEX"
fi

echo ""
echo "=========================================="
echo "Step 3: Verify Key Vault Secrets"
echo "=========================================="
echo ""

# Get Key Vault name
KEY_VAULT_NAME=$(azd env get-values | grep AZURE_KEY_VAULT_NAME | cut -d'=' -f2 | tr -d '"' || echo "")

if [ -z "$KEY_VAULT_NAME" ]; then
    # Try to find Key Vault in resource group
    KEY_VAULT_NAME=$(az keyvault list --resource-group "$RESOURCE_GROUP" --query "[0].name" -o tsv 2>/dev/null || echo "")
fi

if [ -n "$KEY_VAULT_NAME" ]; then
    echo "Verifying Key Vault secrets in: $KEY_VAULT_NAME"
    echo ""
    
    # Get current user object ID
    USER_OBJECT_ID=$(az ad signed-in-user show --query id -o tsv 2>/dev/null || echo "")
    
    if [ -n "$USER_OBJECT_ID" ]; then
        # Grant temporary permissions to verify secrets
        echo "Granting temporary Key Vault permissions..."
        az role assignment create \
            --role "Key Vault Secrets Officer" \
            --assignee "$USER_OBJECT_ID" \
            --scope "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.KeyVault/vaults/$KEY_VAULT_NAME" \
            --output none 2>/dev/null || echo "⚠ Could not grant permissions (may already exist)"
        
        # Wait for permissions to propagate
        sleep 5
        
        # Verify ACS connection string secret
        echo "Checking ACS connection string secret..."
        ACS_SECRET=$(az keyvault secret show --vault-name "$KEY_VAULT_NAME" --name "ACS-CONNECTION-STRING" --query "value" -o tsv 2>/dev/null || echo "")
        
        if [ -z "$ACS_SECRET" ] || [[ ! "$ACS_SECRET" =~ "endpoint=" ]]; then
            echo "⚠ ACS connection string secret is missing or invalid"
            echo "Retrieving ACS connection string..."
            
            # Get ACS resource name
            ACS_NAME=$(az resource list --resource-group "$RESOURCE_GROUP" --resource-type "Microsoft.Communication/CommunicationServices" --query "[0].name" -o tsv 2>/dev/null || echo "")
            
            if [ -n "$ACS_NAME" ]; then
                echo "Found ACS resource: $ACS_NAME"
                ACS_CONN_STRING=$(az communication list-key --name "$ACS_NAME" --resource-group "$RESOURCE_GROUP" --query "primaryConnectionString" -o tsv 2>/dev/null || echo "")
                
                if [ -n "$ACS_CONN_STRING" ]; then
                    echo "Setting ACS connection string in Key Vault..."
                    az keyvault secret set \
                        --vault-name "$KEY_VAULT_NAME" \
                        --name "ACS-CONNECTION-STRING" \
                        --value "$ACS_CONN_STRING" \
                        --output none
                    echo "✓ ACS connection string secret updated"
                else
                    echo "✗ Failed to retrieve ACS connection string"
                fi
            else
                echo "✗ ACS resource not found in resource group"
            fi
        else
            echo "✓ ACS connection string secret exists"
        fi
        
        # Verify other critical secrets
        echo ""
        echo "Checking other secrets..."
        
        # Azure Search API Key
        SEARCH_SECRET=$(az keyvault secret show --vault-name "$KEY_VAULT_NAME" --name "AZURE-SEARCH-API-KEY" --query "value" -o tsv 2>/dev/null || echo "")
        if [ -n "$SEARCH_SECRET" ]; then
            echo "✓ Azure Search API Key exists"
        else
            echo "⚠ Azure Search API Key secret not found (may not be configured yet)"
        fi
        
        # Storage Connection String
        STORAGE_SECRET=$(az keyvault secret show --vault-name "$KEY_VAULT_NAME" --name "AZURE-STORAGE-CONNECTION-STRING" --query "value" -o tsv 2>/dev/null || echo "")
        if [ -n "$STORAGE_SECRET" ]; then
            echo "✓ Azure Storage Connection String exists"
        else
            echo "⚠ Azure Storage Connection String secret not found (may not be configured yet)"
        fi
        
    else
        echo "⚠ Could not verify secrets (unable to get user identity)"
    fi
else
    echo "⚠ Key Vault not found. Secrets verification skipped."
fi

echo ""
echo "=========================================="
echo "Step 4: Configure AI Services Model Deployments"
echo "=========================================="
echo ""

# Find AI Services resource
AI_SERVICES_NAME=$(az resource list --resource-group "$RESOURCE_GROUP" --resource-type "Microsoft.CognitiveServices/accounts" --query "[?kind=='AIServices'].name" -o tsv 2>/dev/null || echo "")

if [ -n "$AI_SERVICES_NAME" ]; then
    echo "Found AI Services resource: $AI_SERVICES_NAME"
    
    # Check if gpt-4o-mini deployment exists
    echo "Checking gpt-4o-mini deployment..."
    EXISTING_DEPLOYMENT=$(az cognitiveservices account deployment list --name "$AI_SERVICES_NAME" --resource-group "$RESOURCE_GROUP" --query "[?name=='gpt-4o-mini'].name" -o tsv 2>/dev/null || echo "")
    
    if [ -z "$EXISTING_DEPLOYMENT" ]; then
        echo "Creating gpt-4o-mini deployment..."
        az cognitiveservices account deployment create \
            --name "$AI_SERVICES_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --deployment-name gpt-4o-mini \
            --model-name gpt-4o-mini \
            --model-version "2024-07-18" \
            --model-format OpenAI \
            --sku-name "GlobalStandard" \
            --sku-capacity 100 \
            --output none 2>/dev/null
        
        if [ $? -eq 0 ]; then
            echo "✓ gpt-4o-mini deployment created"
        else
            echo "⚠ Failed to create gpt-4o-mini deployment (may need manual configuration)"
        fi
    else
        echo "✓ gpt-4o-mini deployment already exists"
    fi
    
    # Grant Managed Identity permissions to AI Services
    echo ""
    echo "Configuring Managed Identity permissions..."
    MANAGED_IDENTITY_ID=$(azd env get-values | grep AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID | cut -d'=' -f2 | tr -d '"' || echo "")
    
    if [ -n "$MANAGED_IDENTITY_ID" ]; then
        AI_SERVICES_ID="/subscriptions/$(az account show --query id -o tsv)/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.CognitiveServices/accounts/$AI_SERVICES_NAME"
        
        # Check and assign Cognitive Services OpenAI User role
        EXISTING_OPENAI_ROLE=$(az role assignment list --assignee "$MANAGED_IDENTITY_ID" --scope "$AI_SERVICES_ID" --query "[?roleDefinitionName=='Cognitive Services OpenAI User'].roleDefinitionName" -o tsv 2>/dev/null || echo "")
        
        if [ -z "$EXISTING_OPENAI_ROLE" ]; then
            echo "Granting Cognitive Services OpenAI User role..."
            az role assignment create \
                --role "Cognitive Services OpenAI User" \
                --assignee "$MANAGED_IDENTITY_ID" \
                --scope "$AI_SERVICES_ID" \
                --output none 2>/dev/null
            
            if [ $? -eq 0 ]; then
                echo "✓ Cognitive Services OpenAI User role assigned"
            else
                echo "⚠ Failed to assign Cognitive Services OpenAI User role"
            fi
        else
            echo "✓ Cognitive Services OpenAI User role already exists"
        fi
        
        # Check and assign Azure AI User role (required for Voice Live API)
        EXISTING_AI_ROLE=$(az role assignment list --assignee "$MANAGED_IDENTITY_ID" --scope "$AI_SERVICES_ID" --query "[?roleDefinitionName=='Azure AI User'].roleDefinitionName" -o tsv 2>/dev/null || echo "")
        
        if [ -z "$EXISTING_AI_ROLE" ]; then
            echo "Granting Azure AI User role..."
            az role assignment create \
                --role "Azure AI User" \
                --assignee "$MANAGED_IDENTITY_ID" \
                --scope "$AI_SERVICES_ID" \
                --output none 2>/dev/null
            
            if [ $? -eq 0 ]; then
                echo "✓ Azure AI User role assigned"
            else
                echo "⚠ Failed to assign Azure AI User role"
            fi
        else
            echo "✓ Azure AI User role already exists"
        fi
    else
        echo "⚠ Managed Identity not found. Skipping role assignment."
    fi
else
    echo "⚠ AI Services resource not found. Skipping model deployment configuration."
fi

echo ""
echo "=========================================="
echo "Step 5: Copy Data from Production (Optional)"
echo "=========================================="
echo ""

# Only copy data if this is not the production environment
if [[ "$ENV_NAME" != *"farmacia"* ]] && [[ "$ENV_NAME" != *"prod"* ]]; then
    # Check if production environment exists
    PROD_RG="rg-farmacia-agent-6fqtj"
    
    if az group show --name "$PROD_RG" &> /dev/null; then
        echo "Production environment detected."
        echo "Do you want to copy search data from production? (y/n)"
        echo "Note: This will copy the search index schema and documents."
        echo ""
        echo "Skipping automatic copy. Run './copy_search_data.sh' manually if needed."
        echo ""
        echo "To copy data later, run:"
        echo "  ./copy_search_data.sh"
    else
        echo "ℹ No production environment found. Skipping data copy."
    fi
else
    echo "ℹ This is the production environment. Skipping data copy."
fi

echo ""
echo "=========================================="
echo "Step 6: Update Anonymization Encryption Key"
echo "=========================================="
echo ""

if [ -n "$KEY_VAULT_NAME" ]; then
    echo "Checking anonymization encryption key in Key Vault..."
    
    # Check if the key exists and is properly formatted
    EXISTING_KEY=$(az keyvault secret show --vault-name "$KEY_VAULT_NAME" --name "ANONYMIZATION-ENCRYPTION-KEY" --query "value" -o tsv 2>/dev/null || echo "")
    
    if [ -z "$EXISTING_KEY" ]; then
        echo "⚠ Anonymization encryption key not found"
    else
        # Check if the key is Fernet-compatible (44 characters, base64 encoded, ends with =)
        KEY_LENGTH=${#EXISTING_KEY}
        if [ "$KEY_LENGTH" -eq 44 ] && [[ "$EXISTING_KEY" == *"=" ]]; then
            echo "✓ Valid Fernet encryption key found in Key Vault"
        else
            echo "⚠ Key exists but may not be Fernet-compatible (length: $KEY_LENGTH)"
            echo "Generating new Fernet encryption key..."
            
            # Check if Python is available
            if command -v python3 &> /dev/null; then
                # Generate a proper Fernet key using Python
                NEW_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
                
                # Update the key in Key Vault
                az keyvault secret set \
                    --vault-name "$KEY_VAULT_NAME" \
                    --name "ANONYMIZATION-ENCRYPTION-KEY" \
                    --value "$NEW_KEY" \
                    --content-type "application/x-fernet-key" \
                    --output none
                
                echo "✓ Generated and stored new Fernet encryption key"
                echo "  Key length: ${#NEW_KEY} characters"
            else
                echo "⚠ Python3 not available. Cannot generate Fernet key."
                echo "  Please manually update the key in Key Vault: $KEY_VAULT_NAME"
                echo "  Run: python3 infra/hooks/generate_encryption_key.py"
            fi
        fi
    fi
else
    echo "⚠ Key Vault not found. Cannot verify encryption key."
fi

echo ""
echo "=========================================="
echo "Step 7: Finalize Configuration"
echo "=========================================="
echo ""

echo "ℹ Configuration completed. The Container App will be updated on next deployment."
echo ""
echo "Note: If you updated any environment variables, run 'azd deploy' to apply changes."

echo ""
echo "=========================================="
echo "✓ Post-Provision Configuration Complete!"
echo "=========================================="
echo ""
echo "Summary of configured values:"
azd env get-values | grep -E "(AZURE_AD_|AZURE_SEARCH_INDEX)"
echo ""
echo "Secrets verification:"
if [ -n "$KEY_VAULT_NAME" ]; then
    echo "  Key Vault: $KEY_VAULT_NAME"
    echo "  ACS Connection String: $([ -n "$ACS_SECRET" ] && echo '✓ Configured' || echo '✗ Missing')"
    echo "  Search API Key: $([ -n "$SEARCH_SECRET" ] && echo '✓ Configured' || echo '⚠ Not configured')"
    echo "  Storage Connection: $([ -n "$STORAGE_SECRET" ] && echo '✓ Configured' || echo '⚠ Not configured')"
    
    # Verify anonymization encryption key
    ANON_KEY_CHECK=$(az keyvault secret show --vault-name "$KEY_VAULT_NAME" --name "ANONYMIZATION-ENCRYPTION-KEY" --query "value" -o tsv 2>/dev/null || echo "")
    if [ -n "$ANON_KEY_CHECK" ]; then
        echo "  Anonymization Encryption Key: ✓ Configured (${#ANON_KEY_CHECK} chars)"
    else
        echo "  Anonymization Encryption Key: ✗ Missing"
    fi
fi
echo ""
echo "Next steps:"
echo "  1. Run 'azd deploy' to deploy the application"
echo "  2. (Optional) Run './copy_search_data.sh' to copy data from production"
echo "  3. Access your application at the Container App URL"
echo ""
