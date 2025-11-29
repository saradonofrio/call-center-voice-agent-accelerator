#!/bin/bash
# Backup Azure Storage Account data to local or another storage account

set -e

ENVIRONMENT=${1:-farmacia-agent}
BACKUP_TYPE=${2:-local}  # local or azure
BACKUP_DIR="./backups/storage/$(date +%Y%m%d_%H%M%S)"

echo "🔄 Backing up Storage Account for environment: $ENVIRONMENT"

# Load environment variables
source <(azd env get-values --environment $ENVIRONMENT)

if [ "$BACKUP_TYPE" == "local" ]; then
  echo "📦 Downloading all blobs to local directory: $BACKUP_DIR"
  mkdir -p "$BACKUP_DIR"
  
  # Backup each container
  for container in conversations evaluations feedback approved-responses documents servizi anonymization-maps testlogs; do
    echo "  📥 Downloading container: $container"
    az storage blob download-batch \
      --source "$container" \
      --destination "$BACKUP_DIR/$container" \
      --account-name "${AZURE_STORAGE_ACCOUNT_NAME}" \
      --auth-mode key \
      --no-progress \
      2>/dev/null || echo "    ⚠️  Container $container is empty or doesn't exist"
  done
  
  echo ""
  echo "✅ Local backup completed!"
  echo "📁 Backup location: $BACKUP_DIR"
  
elif [ "$BACKUP_TYPE" == "azure" ]; then
  # Cross-region backup to another storage account
  BACKUP_STORAGE=${AZURE_STORAGE_ACCOUNT_NAME}-backup
  BACKUP_REGION="northeurope"  # Different region for disaster recovery
  
  echo "📦 Creating backup storage account: $BACKUP_STORAGE in $BACKUP_REGION"
  
  az storage account create \
    --name "$BACKUP_STORAGE" \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --location "$BACKUP_REGION" \
    --sku Standard_GRS \
    --kind StorageV2 \
    --tags backup=true environment="$ENVIRONMENT" || echo "Storage account may already exist"
  
  # Copy each container
  for container in conversations evaluations feedback approved-responses documents servizi anonymization-maps testlogs; do
    echo "  📥 Copying container: $container"
    
    # Create container in backup storage
    az storage container create \
      --name "$container" \
      --account-name "$BACKUP_STORAGE" \
      --auth-mode key 2>/dev/null || true
    
    # Copy blobs using azcopy
    SOURCE_SAS=$(az storage container generate-sas --account-name "${AZURE_STORAGE_ACCOUNT_NAME}" --name "$container" --permissions rl --expiry $(date -u -d "1 hour" '+%Y-%m-%dT%H:%MZ') -o tsv)
    DEST_SAS=$(az storage container generate-sas --account-name "$BACKUP_STORAGE" --name "$container" --permissions rwl --expiry $(date -u -d "1 hour" '+%Y-%m-%dT%H:%MZ') -o tsv)
    
    azcopy copy \
      "https://${AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net/${container}?${SOURCE_SAS}" \
      "https://${BACKUP_STORAGE}.blob.core.windows.net/${container}?${DEST_SAS}" \
      --recursive \
      2>/dev/null || echo "    ⚠️  Container $container copy failed or is empty"
  done
  
  echo ""
  echo "✅ Azure backup completed!"
  echo "📁 Backup storage: $BACKUP_STORAGE"
  echo "🌍 Backup region: $BACKUP_REGION"
else
  echo "❌ Invalid backup type. Use 'local' or 'azure'"
  exit 1
fi

echo ""
echo "To restore, use: ./scripts/restore-storage.sh $ENVIRONMENT [backup-path]"
