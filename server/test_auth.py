#!/usr/bin/env python3
"""
Quick test script for Azure AD authentication.
Run this to verify your Azure AD setup is working correctly.
"""

import os
import sys
import requests
from msal import ConfidentialClientApplication

# Colors for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_step(step, message):
    print(f"{BLUE}[Step {step}]{RESET} {message}")

def print_success(message):
    print(f"{GREEN}✓ {message}{RESET}")

def print_error(message):
    print(f"{RED}✗ {message}{RESET}")

def print_warning(message):
    print(f"{YELLOW}⚠ {message}{RESET}")

def main():
    print("\n" + "="*60)
    print("Azure AD Authentication Test Script")
    print("="*60 + "\n")
    
    # Check environment variables
    print_step(1, "Azure AD Configuration...")
    
    tenant_id = os.getenv("AZURE_AD_TENANT_ID")
    api_client_id = os.getenv("AZURE_AD_CLIENT_ID")
    
    if not tenant_id or not api_client_id:
        print_warning("Azure AD environment variables not set locally")
        print("Please enter your Azure AD configuration:")
        tenant_id = input("  Tenant ID: ").strip()
        api_client_id = input("  API Client ID (from farmacia-pepe-bot-api): ").strip()
        
        if not tenant_id or not api_client_id:
            print_error("Tenant ID and API Client ID are required")
            sys.exit(1)
    
    print_success(f"Tenant ID: {tenant_id[:8]}...")
    print_success(f"API Client ID: {api_client_id[:8]}...")
    
    # Get client credentials for testing
    print_step(2, "Enter client application credentials...")
    print("(These are from your CLIENT app registration, not the API)")
    
    client_app_id = input("Client App ID: ").strip()
    client_secret = input("Client Secret: ").strip()
    
    if not client_app_id or not client_secret:
        print_error("Client ID and Secret are required")
        sys.exit(1)
    
    # Get token
    print_step(3, "Acquiring access token from Azure AD...")
    
    # For client credentials flow, scope must be /.default
    api_scope = f"api://{api_client_id}/.default"
    
    app = ConfidentialClientApplication(
        client_app_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        client_credential=client_secret,
    )
    
    result = app.acquire_token_for_client(scopes=[api_scope])
    
    if "access_token" not in result:
        print_error(f"Failed to acquire token: {result.get('error_description')}")
        print("\nTroubleshooting:")
        print("1. Verify client app has API permissions")
        print("2. Check that admin consent was granted")
        print("3. Ensure client secret is valid and not expired")
        sys.exit(1)
    
    token = result["access_token"]
    print_success("Access token acquired successfully")
    
    # Show token info
    print(f"\nToken preview: {token[:50]}...")
    
    # Decode token to show claims (for debugging)
    try:
        import jwt
        decoded = jwt.decode(token, options={"verify_signature": False})
        print(f"\nToken claims:")
        print(f"  - Audience: {decoded.get('aud')}")
        print(f"  - Issuer: {decoded.get('iss')}")
        print(f"  - Roles: {decoded.get('roles', [])}")
        print(f"  - App ID: {decoded.get('appid')}")
    except Exception as e:
        print_warning(f"Could not decode token: {e}")
    
    # Test API endpoint
    print_step(4, "Testing API endpoint...")
    
    print("\nEnter your API URL:")
    print("  - For Azure Container App: https://ca-<your-env>-<suffix>.azurecontainerapps.io")
    print("  - For local development: http://localhost:8000")
    api_url = input("API URL: ").strip()
    if not api_url:
        print_error("API URL is required")
        sys.exit(1)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test 1: List documents
    print(f"\n{BLUE}Test 1:{RESET} GET /api/documents")
    try:
        response = requests.get(f"{api_url}/api/documents", headers=headers)
        
        if response.status_code == 200:
            print_success(f"Status: {response.status_code} OK")
            data = response.json()
            print(f"  Documents: {len(data.get('documents', []))}")
        elif response.status_code == 401:
            print_error(f"Status: {response.status_code} Unauthorized")
            print(f"  Response: {response.json()}")
        elif response.status_code == 403:
            print_error(f"Status: {response.status_code} Forbidden")
            print(f"  Response: {response.json()}")
            print_warning("  User may not have required role assigned")
        else:
            print_error(f"Status: {response.status_code}")
            print(f"  Response: {response.text}")
    except requests.exceptions.ConnectionError:
        print_error("Could not connect to API server")
        print("  Make sure the server is running: python server.py")
    except Exception as e:
        print_error(f"Request failed: {e}")
    
    # Test 2: Create indexer (Admin only)
    print(f"\n{BLUE}Test 2:{RESET} POST /api/indexer/create (Admin only)")
    try:
        response = requests.post(f"{api_url}/api/indexer/create", headers=headers)
        
        if response.status_code == 200:
            print_success(f"Status: {response.status_code} OK (User has Admin role)")
        elif response.status_code == 403:
            print_warning(f"Status: {response.status_code} Forbidden")
            print("  This is expected if user doesn't have Admin role")
        elif response.status_code == 401:
            print_error(f"Status: {response.status_code} Unauthorized")
            print(f"  Response: {response.json()}")
        else:
            print(f"Status: {response.status_code}")
            print(f"  Response: {response.text}")
    except Exception as e:
        print_error(f"Request failed: {e}")
    
    # Summary
    print("\n" + "="*60)
    print("Test Complete")
    print("="*60)
    print("\nIf you see authentication errors:")
    print("1. Check user is assigned to app in Enterprise Applications")
    print("2. Verify user has Admin or User role assigned")
    print("3. Check server logs for detailed error messages")
    print("4. Review AZURE_AD_AUTH_SETUP.md for troubleshooting")
    print()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest cancelled by user")
        sys.exit(0)
