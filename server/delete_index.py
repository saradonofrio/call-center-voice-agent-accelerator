#!/usr/bin/env python3
"""
Script to delete the Azure Search index so it can be recreated with the correct schema.
"""
import os
from azure.search.documents.indexes import SearchIndexClient
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv

load_dotenv()

# Get configuration from environment
search_endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
search_index = os.environ.get("AZURE_SEARCH_INDEX")
search_api_key = os.environ.get("AZURE_SEARCH_API_KEY")

if not all([search_endpoint, search_index, search_api_key]):
    print("❌ Missing required environment variables:")
    print(f"   AZURE_SEARCH_ENDPOINT: {'✓' if search_endpoint else '✗'}")
    print(f"   AZURE_SEARCH_INDEX: {'✓' if search_index else '✗'}")
    print(f"   AZURE_SEARCH_API_KEY: {'✓' if search_api_key else '✗'}")
    exit(1)

print(f"🔍 Connecting to Azure Search: {search_endpoint}")
print(f"📋 Index to delete: {search_index}")

# Create index client
credential = AzureKeyCredential(search_api_key)
index_client = SearchIndexClient(endpoint=search_endpoint, credential=credential)

try:
    # Check if index exists
    existing_index = index_client.get_index(search_index)
    print(f"✓ Found existing index with {len(existing_index.fields)} fields:")
    for field in existing_index.fields:
        print(f"  - {field.name} ({field.type})")
    
    # Confirm deletion
    print(f"\n⚠️  About to delete index: {search_index}")
    confirm = input("Type 'yes' to confirm deletion: ")
    
    if confirm.lower() == 'yes':
        index_client.delete_index(search_index)
        print(f"✓ Successfully deleted index: {search_index}")
        print("\n💡 The index will be automatically recreated with the correct schema on the next document upload.")
    else:
        print("❌ Deletion cancelled")
        
except Exception as e:
    if "not found" in str(e).lower():
        print(f"ℹ️  Index '{search_index}' does not exist (nothing to delete)")
    else:
        print(f"❌ Error: {e}")
        exit(1)
