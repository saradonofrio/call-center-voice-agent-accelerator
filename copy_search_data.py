#!/usr/bin/env python3
"""
Script to copy Azure Search index and documents from production to test environment.

This script:
1. Exports the index schema from production
2. Creates the same index in test (if it doesn't exist)
3. Copies all documents from production to test
4. Copies blobs from production storage to test storage

Usage:
    python copy_search_data.py
    
Environment variables required:
    # Production
    PROD_SEARCH_ENDPOINT
    PROD_SEARCH_KEY
    PROD_SEARCH_INDEX
    PROD_STORAGE_CONNECTION_STRING
    PROD_STORAGE_CONTAINER
    
    # Test
    TEST_SEARCH_ENDPOINT
    TEST_SEARCH_KEY
    TEST_SEARCH_INDEX
    TEST_STORAGE_CONNECTION_STRING
    TEST_STORAGE_CONTAINER
"""

import os
import sys
import asyncio
from typing import List, Dict, Any
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.core.credentials import AzureKeyCredential
from azure.storage.blob import BlobServiceClient
import json

# Color codes for terminal output
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_info(message: str):
    print(f"{BLUE}ℹ {message}{RESET}")

def print_success(message: str):
    print(f"{GREEN}✓ {message}{RESET}")

def print_warning(message: str):
    print(f"{YELLOW}⚠ {message}{RESET}")

def print_error(message: str):
    print(f"{RED}✗ {message}{RESET}")

def get_env_var(name: str, required: bool = True) -> str:
    """Get environment variable with optional requirement check."""
    value = os.environ.get(name)
    if required and not value:
        print_error(f"Missing required environment variable: {name}")
        sys.exit(1)
    return value

def copy_search_index_schema():
    """Copy index schema from production to test."""
    print_info("Copying search index schema from production to test...")
    
    # Production credentials
    prod_endpoint = get_env_var("PROD_SEARCH_ENDPOINT")
    prod_key = get_env_var("PROD_SEARCH_KEY")
    prod_index = get_env_var("PROD_SEARCH_INDEX")
    
    # Test credentials
    test_endpoint = get_env_var("TEST_SEARCH_ENDPOINT")
    test_key = get_env_var("TEST_SEARCH_KEY")
    test_index = get_env_var("TEST_SEARCH_INDEX")
    
    # Create clients
    prod_client = SearchIndexClient(
        endpoint=prod_endpoint,
        credential=AzureKeyCredential(prod_key)
    )
    test_client = SearchIndexClient(
        endpoint=test_endpoint,
        credential=AzureKeyCredential(test_key)
    )
    
    try:
        # Get production index
        print_info(f"Fetching index schema from production: {prod_index}")
        prod_index_obj = prod_client.get_index(prod_index)
        
        # Update index name for test environment
        prod_index_obj.name = test_index
        
        # Check if test index already exists
        try:
            existing_index = test_client.get_index(test_index)
            print_warning(f"Index already exists in test: {test_index}")
            print_info("Deleting existing test index...")
            test_client.delete_index(test_index)
            print_success("Existing index deleted")
        except Exception:
            print_info(f"Index does not exist in test (will create): {test_index}")
        
        # Create index in test
        print_info(f"Creating index in test: {test_index}")
        test_client.create_index(prod_index_obj)
        print_success(f"Index created successfully: {test_index}")
        
        return True
        
    except Exception as e:
        print_error(f"Failed to copy index schema: {e}")
        return False

def copy_search_documents():
    """Copy all documents from production to test index."""
    print_info("Copying documents from production to test...")
    
    # Production credentials
    prod_endpoint = get_env_var("PROD_SEARCH_ENDPOINT")
    prod_key = get_env_var("PROD_SEARCH_KEY")
    prod_index = get_env_var("PROD_SEARCH_INDEX")
    
    # Test credentials
    test_endpoint = get_env_var("TEST_SEARCH_ENDPOINT")
    test_key = get_env_var("TEST_SEARCH_KEY")
    test_index = get_env_var("TEST_SEARCH_INDEX")
    
    # Create clients
    prod_search_client = SearchClient(
        endpoint=prod_endpoint,
        index_name=prod_index,
        credential=AzureKeyCredential(prod_key)
    )
    test_search_client = SearchClient(
        endpoint=test_endpoint,
        index_name=test_index,
        credential=AzureKeyCredential(test_key)
    )
    
    try:
        # Get all documents from production
        print_info(f"Fetching documents from production index: {prod_index}")
        results = prod_search_client.search(search_text="*", include_total_count=True)
        
        # Collect all documents
        documents = []
        for result in results:
            # Convert to dict and keep all fields
            doc = dict(result)
            documents.append(doc)
        
        total_docs = len(documents)
        print_success(f"Found {total_docs} documents in production")
        
        if total_docs == 0:
            print_warning("No documents to copy")
            return True
        
        # Upload documents to test in batches
        print_info(f"Uploading {total_docs} documents to test index...")
        batch_size = 100
        for i in range(0, total_docs, batch_size):
            batch = documents[i:i + batch_size]
            result = test_search_client.upload_documents(documents=batch)
            print_info(f"Uploaded batch {i//batch_size + 1} ({len(batch)} documents)")
        
        print_success(f"Successfully uploaded {total_docs} documents to test index")
        return True
        
    except Exception as e:
        print_error(f"Failed to copy documents: {e}")
        import traceback
        traceback.print_exc()
        return False

def copy_blob_storage():
    """Copy blobs from production to test storage."""
    print_info("Copying blobs from production to test storage...")
    
    # Production credentials
    prod_conn_str = get_env_var("PROD_STORAGE_CONNECTION_STRING")
    prod_container = get_env_var("PROD_STORAGE_CONTAINER", required=False) or "documents"
    
    # Test credentials
    test_conn_str = get_env_var("TEST_STORAGE_CONNECTION_STRING")
    test_container = get_env_var("TEST_STORAGE_CONTAINER", required=False) or "documents"
    
    try:
        # Create clients
        prod_blob_service = BlobServiceClient.from_connection_string(prod_conn_str)
        test_blob_service = BlobServiceClient.from_connection_string(test_conn_str)
        
        prod_container_client = prod_blob_service.get_container_client(prod_container)
        test_container_client = test_blob_service.get_container_client(test_container)
        
        # Create test container if it doesn't exist
        try:
            test_container_client.create_container()
            print_success(f"Created test container: {test_container}")
        except Exception:
            print_info(f"Test container already exists: {test_container}")
        
        # List all blobs in production
        print_info(f"Listing blobs in production container: {prod_container}")
        blobs = list(prod_container_client.list_blobs())
        total_blobs = len(blobs)
        print_success(f"Found {total_blobs} blobs in production")
        
        if total_blobs == 0:
            print_warning("No blobs to copy")
            return True
        
        # Copy each blob
        print_info(f"Copying {total_blobs} blobs to test storage...")
        for i, blob in enumerate(blobs, 1):
            source_blob = prod_container_client.get_blob_client(blob.name)
            dest_blob = test_container_client.get_blob_client(blob.name)
            
            # Copy blob
            source_url = source_blob.url
            dest_blob.start_copy_from_url(source_url)
            
            print_info(f"Copied blob {i}/{total_blobs}: {blob.name}")
        
        print_success(f"Successfully copied {total_blobs} blobs to test storage")
        return True
        
    except Exception as e:
        print_error(f"Failed to copy blobs: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main function to orchestrate the copy process."""
    print("\n" + "="*60)
    print("Azure Search Data Copy: Production → Test")
    print("="*60 + "\n")
    
    # Step 1: Copy index schema
    if not copy_search_index_schema():
        print_error("Failed to copy index schema. Aborting.")
        sys.exit(1)
    
    print("\n" + "-"*60 + "\n")
    
    # Step 2: Copy documents
    if not copy_search_documents():
        print_error("Failed to copy documents. Continuing with blob storage...")
    
    print("\n" + "-"*60 + "\n")
    
    # Step 3: Copy blob storage
    if not copy_blob_storage():
        print_error("Failed to copy blob storage.")
    
    print("\n" + "="*60)
    print_success("Data copy process completed!")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
