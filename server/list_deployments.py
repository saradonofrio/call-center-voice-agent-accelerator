"""
Script to test Azure OpenAI deployments.
This helps identify the correct deployment name to use.
Reads environment variables from the container.
"""

import os
import json
import urllib.request
import urllib.error

def test_deployment(endpoint, key, deployment_name, api_version="2024-08-01-preview"):
    """Test if a deployment works with a simple API call."""
    
    # Remove trailing slash
    endpoint = endpoint.rstrip('/')
    
    # Build URL
    url = f"{endpoint}/openai/deployments/{deployment_name}/chat/completions?api-version={api_version}"
    
    # Prepare request
    headers = {
        "api-key": key,
        "Content-Type": "application/json"
    }
    
    data = json.dumps({
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 5
    }).encode('utf-8')
    
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return True, "Works"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False, "Not found"
        elif e.code == 401:
            return False, "Auth error"
        else:
            return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)[:50]

def main():
    """List available deployments in Azure OpenAI."""
    
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    key = os.environ.get("AZURE_OPENAI_KEY")
    
    if not endpoint or not key:
        print("❌ Azure OpenAI credentials not found")
        print("\nPlease set environment variables:")
        print("  - AZURE_OPENAI_ENDPOINT")
        print("  - AZURE_OPENAI_KEY")
        return
    
    current_model = os.environ.get('VOICE_LIVE_MODEL', '').strip()
    
    print("🔍 Azure OpenAI Deployment Checker")
    print("="*60)
    print(f"\nEndpoint: {endpoint}")
    print(f"Current VOICE_LIVE_MODEL: '{current_model}'")
    
    # Try common deployment names
    common_names = [
        current_model,
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4",
        "gpt-35-turbo",
        "gpt-35-turbo-16k"
    ]
    
    # Remove empty strings and duplicates
    common_names = list(dict.fromkeys([name for name in common_names if name]))
    
    print(f"\n🧪 Testing {len(common_names)} deployment names:\n")
    
    working_deployments = []
    
    for name in common_names:
        print(f"   Testing '{name}'... ", end="", flush=True)
        
        works, message = test_deployment(endpoint, key, name)
        
        if works:
            print("✅ WORKS!")
            working_deployments.append(name)
        else:
            print(f"❌ {message}")
    
    print("\n" + "="*60)
    
    if working_deployments:
        print(f"\n✅ Found {len(working_deployments)} working deployment(s):")
        for name in working_deployments:
            print(f"   - '{name}'")
        
        print(f"\n💡 Recommended: Use deployment '{working_deployments[0]}'")
        
        if current_model != working_deployments[0]:
            print(f"\n🔧 To fix, update your environment variable:")
            print(f"   VOICE_LIVE_MODEL={working_deployments[0]}")
            print(f"\nFor Azure Container Apps, use:")
            print(f"   az containerapp update \\")
            print(f"     --name <your-app-name> \\")
            print(f"     --resource-group <your-rg> \\")
            print(f"     --set-env-vars VOICE_LIVE_MODEL={working_deployments[0]}")
        else:
            print("\n✅ Current VOICE_LIVE_MODEL is correct!")
    else:
        print("\n❌ No working deployments found!")
        print("\n📋 Troubleshooting:")
        print("   1. Check Azure Portal → Azure OpenAI → Deployments")
        print("   2. Verify a chat model (gpt-4o, gpt-4o-mini, etc.) is deployed")
        print("   3. Check the exact deployment name (case-sensitive)")
        print("   4. Verify API key has access to the deployments")
    
    print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    main()
