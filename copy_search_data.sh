#!/bin/bash
# Script to copy Azure Search data from production to test environment
# This script sets up environment variables and runs the Python copy script

set -e  # Exit on error

echo "=========================================="
echo "Azure Search Data Copy Script"
echo "=========================================="
echo ""

# Check if Azure CLI is logged in
if ! az account show &> /dev/null; then
    echo "❌ Not logged into Azure CLI. Please run: az login"
    exit 1
fi

# Get subscription ID
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
echo "✓ Using subscription: $SUBSCRIPTION_ID"
echo ""

# Production resource group and resources
PROD_RG="rg-farmacia-agent-6fqtj"
PROD_SEARCH="index-farmaciapepe"
PROD_STORAGE="farmaciastorageaccount"
PROD_SEARCH_INDEX="rag-1762098848175"

# Test resource group and resources
TEST_RG="rg-test-f4c3w"
TEST_SEARCH="search-test-f4c3w"
TEST_STORAGE="sttestf4c3w"
TEST_SEARCH_INDEX="pharmacy-knowledge-base"

echo "Production Environment:"
echo "  Resource Group: $PROD_RG"
echo "  Search Service: $PROD_SEARCH"
echo "  Storage Account: $PROD_STORAGE"
echo "  Search Index: $PROD_SEARCH_INDEX"
echo ""

echo "Test Environment:"
echo "  Resource Group: $TEST_RG"
echo "  Search Service: $TEST_SEARCH"
echo "  Storage Account: $TEST_STORAGE"
echo "  Search Index: $TEST_SEARCH_INDEX"
echo ""

# Get production search credentials
echo "📡 Retrieving production Azure Search credentials..."
PROD_SEARCH_ENDPOINT=$(az search service show \
    --name "$PROD_SEARCH" \
    --resource-group "$PROD_RG" \
    --query "properties.publicNetworkAccess" -o tsv)

PROD_SEARCH_ENDPOINT="https://${PROD_SEARCH}.search.windows.net"

PROD_SEARCH_KEY=$(az search admin-key show \
    --service-name "$PROD_SEARCH" \
    --resource-group "$PROD_RG" \
    --query "primaryKey" -o tsv)

echo "✓ Production search endpoint: $PROD_SEARCH_ENDPOINT"

# Get test search credentials
echo "📡 Retrieving test Azure Search credentials..."
TEST_SEARCH_ENDPOINT="https://${TEST_SEARCH}.search.windows.net"

TEST_SEARCH_KEY=$(az search admin-key show \
    --service-name "$TEST_SEARCH" \
    --resource-group "$TEST_RG" \
    --query "primaryKey" -o tsv)

echo "✓ Test search endpoint: $TEST_SEARCH_ENDPOINT"

# Get production storage connection string
echo "📡 Retrieving production storage connection string..."
PROD_STORAGE_CONNECTION_STRING=$(az storage account show-connection-string \
    --name "$PROD_STORAGE" \
    --resource-group "$PROD_RG" \
    --query "connectionString" -o tsv)

echo "✓ Production storage connection string retrieved"

# Get test storage connection string
echo "📡 Retrieving test storage connection string..."
TEST_STORAGE_CONNECTION_STRING=$(az storage account show-connection-string \
    --name "$TEST_STORAGE" \
    --resource-group "$TEST_RG" \
    --query "connectionString" -o tsv)

echo "✓ Test storage connection string retrieved"
echo ""

# Export environment variables for Python script
export PROD_SEARCH_ENDPOINT="$PROD_SEARCH_ENDPOINT"
export PROD_SEARCH_KEY="$PROD_SEARCH_KEY"
export PROD_SEARCH_INDEX="$PROD_SEARCH_INDEX"
export PROD_STORAGE_CONNECTION_STRING="$PROD_STORAGE_CONNECTION_STRING"
export PROD_STORAGE_CONTAINER="documents"

export TEST_SEARCH_ENDPOINT="$TEST_SEARCH_ENDPOINT"
export TEST_SEARCH_KEY="$TEST_SEARCH_KEY"
export TEST_SEARCH_INDEX="$TEST_SEARCH_INDEX"
export TEST_STORAGE_CONNECTION_STRING="$TEST_STORAGE_CONNECTION_STRING"
export TEST_STORAGE_CONTAINER="documents"

# Run Python copy script
echo "=========================================="
echo "Starting data copy process..."
echo "=========================================="
echo ""

python3 copy_search_data.py

echo ""
echo "=========================================="
echo "✓ Copy process completed successfully!"
echo "=========================================="
