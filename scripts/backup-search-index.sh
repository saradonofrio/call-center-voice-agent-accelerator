#!/bin/bash
# Backup Azure AI Search index definitions and data

set -e

ENVIRONMENT=${1:-farmacia-agent}
BACKUP_DIR="./backups/$(date +%Y%m%d_%H%M%S)"

echo "🔄 Backing up Azure AI Search for environment: $ENVIRONMENT"

# Load environment variables
source <(azd env get-values --environment $ENVIRONMENT)

mkdir -p "$BACKUP_DIR"

# Backup index definition
echo "📦 Exporting index definition..."
curl -X GET \
  "https://${AZURE_SEARCH_SERVICE}.search.windows.net/indexes/feedback-index?api-version=2023-11-01" \
  -H "api-key: ${AZURE_SEARCH_ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  > "$BACKUP_DIR/feedback-index-definition.json"

echo "✅ Index definition saved to: $BACKUP_DIR/feedback-index-definition.json"

# Backup data source configuration
echo "📦 Exporting data source..."
curl -X GET \
  "https://${AZURE_SEARCH_SERVICE}.search.windows.net/datasources?api-version=2023-11-01" \
  -H "api-key: ${AZURE_SEARCH_ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  > "$BACKUP_DIR/datasources.json"

# Backup indexer configuration
echo "📦 Exporting indexer..."
curl -X GET \
  "https://${AZURE_SEARCH_SERVICE}.search.windows.net/indexers?api-version=2023-11-01" \
  -H "api-key: ${AZURE_SEARCH_ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  > "$BACKUP_DIR/indexers.json"

echo ""
echo "✅ Backup completed successfully!"
echo "📁 Backup location: $BACKUP_DIR"
echo ""
echo "To restore, use: ./scripts/restore-search-index.sh $BACKUP_DIR"
