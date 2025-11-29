#!/bin/bash
# Restore Azure Storage Account data from backup

set -e

ENVIRONMENT=${1:-farmacia-agent}
BACKUP_PATH=${2}

if [ -z "$BACKUP_PATH" ]; then
  echo "❌ Usage: $0 <environment> <backup-path>"
  echo "Example: $0 farmacia-agent ./backups/storage/20251129_153000"
  exit 1
fi

if [ ! -d "$BACKUP_PATH" ]; then
  echo "❌ Backup path not found: $BACKUP_PATH"
  exit 1
fi

echo "🔄 Restoring Storage Account for environment: $ENVIRONMENT"
echo "📁 From backup: $BACKUP_PATH"
echo ""
read -p "⚠️  This will overwrite existing data. Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "❌ Restore cancelled"
  exit 1
fi

# Load environment variables
source <(azd env get-values --environment $ENVIRONMENT)

# Restore each container
for container_dir in "$BACKUP_PATH"/*; do
  if [ -d "$container_dir" ]; then
    container=$(basename "$container_dir")
    echo "📤 Uploading container: $container"
    
    # Create container if it doesn't exist
    az storage container create \
      --name "$container" \
      --account-name "${AZURE_STORAGE_ACCOUNT_NAME}" \
      --auth-mode key 2>/dev/null || true
    
    # Upload all blobs
    az storage blob upload-batch \
      --source "$container_dir" \
      --destination "$container" \
      --account-name "${AZURE_STORAGE_ACCOUNT_NAME}" \
      --auth-mode key \
      --overwrite \
      --no-progress
    
    count=$(find "$container_dir" -type f | wc -l)
    echo "  ✅ Restored $count files to $container"
  fi
done

echo ""
echo "✅ Restore completed successfully!"
