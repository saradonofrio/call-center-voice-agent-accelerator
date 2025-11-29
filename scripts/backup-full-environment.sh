#!/bin/bash
# Complete environment backup - all Azure resources

set -e

ENVIRONMENT=${1:-farmacia-agent}
BACKUP_ROOT="./backups/full-backup/$(date +%Y%m%d_%H%M%S)"

echo "🔄 Complete backup for environment: $ENVIRONMENT"
echo "📁 Backup location: $BACKUP_ROOT"
echo ""

mkdir -p "$BACKUP_ROOT"

# Load environment variables
source <(azd env get-values --environment $ENVIRONMENT) > "$BACKUP_ROOT/environment-vars.txt"

echo "1️⃣  Backing up environment configuration..."
azd env get-values --environment $ENVIRONMENT > "$BACKUP_ROOT/env-values.txt"
cp ".azure/$ENVIRONMENT/.env" "$BACKUP_ROOT/dotenv-backup.txt" 2>/dev/null || true

echo "2️⃣  Backing up infrastructure state..."
az group show --name "$AZURE_RESOURCE_GROUP" > "$BACKUP_ROOT/resource-group.json"
az resource list --resource-group "$AZURE_RESOURCE_GROUP" > "$BACKUP_ROOT/resources-list.json"

echo "3️⃣  Backing up Storage Account data..."
./scripts/backup-storage.sh "$ENVIRONMENT" local > "$BACKUP_ROOT/storage-backup.log" 2>&1 &
STORAGE_PID=$!

echo "4️⃣  Backing up Azure AI Search configuration..."
./scripts/backup-search-index.sh "$ENVIRONMENT" > "$BACKUP_ROOT/search-backup.log" 2>&1 &
SEARCH_PID=$!

echo "5️⃣  Backing up Key Vault secrets (names only, not values)..."
az keyvault secret list --vault-name "$AZURE_KEY_VAULT_NAME" --query "[].{name:name, enabled:attributes.enabled}" > "$BACKUP_ROOT/keyvault-secrets.json" 2>/dev/null || echo "[]" > "$BACKUP_ROOT/keyvault-secrets.json"

echo "6️⃣  Backing up Application Insights configuration..."
az monitor app-insights component show --app "$AZURE_APP_INSIGHTS_NAME" --resource-group "$AZURE_RESOURCE_GROUP" > "$BACKUP_ROOT/app-insights.json" 2>/dev/null || echo "{}" > "$BACKUP_ROOT/app-insights.json"

echo "7️⃣  Backing up Container App configuration..."
az containerapp show --name "$AZURE_CONTAINER_APP_NAME" --resource-group "$AZURE_RESOURCE_GROUP" > "$BACKUP_ROOT/container-app.json" 2>/dev/null || echo "{}" > "$BACKUP_ROOT/container-app.json"

echo "8️⃣  Backing up Azure OpenAI deployment..."
az cognitiveservices account show --name "$AZURE_OPENAI_NAME" --resource-group "$AZURE_RESOURCE_GROUP" > "$BACKUP_ROOT/openai-account.json" 2>/dev/null || echo "{}" > "$BACKUP_ROOT/openai-account.json"

# Wait for parallel backups
echo ""
echo "⏳ Waiting for storage and search backups to complete..."
wait $STORAGE_PID $SEARCH_PID

# Create manifest
cat > "$BACKUP_ROOT/MANIFEST.txt" << EOF
Backup Manifest
===============
Environment: $ENVIRONMENT
Date: $(date)
Resource Group: $AZURE_RESOURCE_GROUP

Contents:
- environment-vars.txt: Environment variables
- env-values.txt: AZD environment values
- resource-group.json: Resource group metadata
- resources-list.json: All Azure resources
- storage-backup.log: Storage backup log
- search-backup.log: Search index backup log
- keyvault-secrets.json: Key Vault secret names
- app-insights.json: Application Insights config
- container-app.json: Container App config
- openai-account.json: Azure OpenAI config
- storage/: All storage account data

Restore Instructions:
1. Restore infrastructure: azd provision --environment $ENVIRONMENT
2. Restore storage: ./scripts/restore-storage.sh $ENVIRONMENT $BACKUP_ROOT/storage
3. Re-index search: Use Azure Portal or re-run indexer
4. Verify: Test application functionality
EOF

echo ""
echo "✅ Complete backup finished!"
echo "📁 Backup location: $BACKUP_ROOT"
echo "📄 See MANIFEST.txt for details"
echo ""
echo "To restore: Follow instructions in $BACKUP_ROOT/MANIFEST.txt"
