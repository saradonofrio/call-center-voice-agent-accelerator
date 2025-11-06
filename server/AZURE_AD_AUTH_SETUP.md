# Azure AD Authentication Setup Guide

This guide walks you through setting up Azure AD (Entra ID) authentication for your Call Center Voice Agent API endpoints.

## Table of Contents
1. [Azure Portal Setup](#azure-portal-setup)
2. [Environment Configuration](#environment-configuration)
3. [Testing Authentication](#testing-authentication)
4. [Client Integration](#client-integration)
5. [Troubleshooting](#troubleshooting)

---

## Azure Portal Setup

### Step 1: Register the API Application

1. **Navigate to Azure Portal** → **Microsoft Entra ID** (formerly Azure Active Directory)
2. Click **App registrations** → **New registration**
3. Fill in the registration form:
   ```
   Name: call-center-voice-agent-api
   Supported account types: Accounts in this organizational directory only (Single tenant)
   Redirect URI: (Leave empty - not needed for API)
   ```
4. Click **Register**

5. **Save these values** (you'll need them later):
   - **Application (client) ID**: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
   - **Directory (tenant) ID**: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`

### Step 2: Expose the API

1. In your app registration, go to **Expose an API**
2. Click **Add** next to "Application ID URI"
3. Accept the default (`api://your-client-id`) or customize it
4. Click **Save**

5. **Add a scope**:
   - Click **Add a scope**
   - **Scope name**: `Access.API`
   - **Who can consent**: `Admins and users`
   - **Admin consent display name**: `Access Voice Agent API`
   - **Admin consent description**: `Allows access to the voice agent API endpoints`
   - **User consent display name**: `Access Voice Agent`
   - **User consent description**: `Access your voice agent`
   - **State**: `Enabled`
   - Click **Add scope**

### Step 3: Create App Roles

1. Go to **App roles** → **Create app role**

2. **Create Admin Role**:
   ```
   Display name: Admin
   Allowed member types: Users/Groups
   Value: Admin
   Description: Full access to manage documents and indexer
   ```
   - Check "Do you want to enable this app role?"
   - Click **Apply**

3. **Create User Role**:
   ```
   Display name: User
   Allowed member types: Users/Groups
   Value: User
   Description: Can use voice agent and view documents
   ```
   - Check "Do you want to enable this app role?"
   - Click **Apply**

### Step 4: Assign Users to the Application

1. Go to **Microsoft Entra ID** → **Enterprise applications**
2. Search for and select `call-center-voice-agent-api`
3. Go to **Users and groups** → **Add user/group**
4. Click **None Selected** under Users
5. Select users/groups to assign
6. Click **Select role** and choose either `Admin` or `User`
7. Click **Assign**

### Step 5: Register Client Application (for Testing/Frontend)

1. Go back to **App registrations** → **New registration**
2. Register a client app:
   ```
   Name: call-center-voice-agent-client
   Supported account types: Accounts in this organizational directory only
   Redirect URI: 
     - For Postman: https://oauth.pstmn.io/v1/callback
     - For Web app: https://your-frontend-domain.com/callback
   ```
3. Click **Register**

4. **Create Client Secret**:
   - Go to **Certificates & secrets** → **New client secret**
   - Description: `API Testing Secret`
   - Expires: Choose expiration period
   - Click **Add**
   - **COPY THE SECRET VALUE IMMEDIATELY** (you won't see it again)

5. **Configure API Permissions**:
   - Go to **API permissions** → **Add a permission**
   - Select **My APIs** tab
   - Click on `call-center-voice-agent-api`
   - Check `Access.API` scope
   - Click **Add permissions**
   - Click **Grant admin consent for [Your Org]**

---

## Environment Configuration

### Update your `.env` file

Add these variables to your `.env` file:

```bash
# Azure AD Authentication
AZURE_AD_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx  # From Step 1
AZURE_AD_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx  # API app client ID
AZURE_AD_AUDIENCE=api://your-client-id  # Optional, defaults to api://{client_id}
```

### Install Required Python Package

```bash
cd server
pip install PyJWT[crypto] cryptography
```

Or add to your `pyproject.toml`:
```toml
dependencies = [
    "PyJWT[crypto]>=2.8.0",
    "cryptography>=41.0.0",
]
```

---

## Testing Authentication

### Method 1: Using Postman

#### Get an Access Token

1. **Create a new request** in Postman
2. Go to **Authorization** tab
3. Select **OAuth 2.0** type
4. Configure token settings:
   ```
   Grant Type: Authorization Code
   Callback URL: https://oauth.pstmn.io/v1/callback
   Auth URL: https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/authorize
   Access Token URL: https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token
   Client ID: {CLIENT_APP_ID}  # From client app registration
   Client Secret: {CLIENT_SECRET}  # From client app secret
   Scope: api://{API_APP_ID}/Access.API
   ```
5. Click **Get New Access Token**
6. Sign in with your Azure AD credentials
7. Click **Use Token**

#### Test Protected Endpoints

**Upload Document** (requires Admin or User role):
```http
POST http://localhost:8000/api/documents
Authorization: Bearer {YOUR_TOKEN}
Content-Type: multipart/form-data

(Attach a .pdf, .docx, or .txt file)
```

**List Documents** (requires Admin or User role):
```http
GET http://localhost:8000/api/documents
Authorization: Bearer {YOUR_TOKEN}
```

**Delete Document** (requires Admin role only):
```http
DELETE http://localhost:8000/api/documents/{document_id}
Authorization: Bearer {YOUR_TOKEN}
```

**Create Indexer** (requires Admin role only):
```http
POST http://localhost:8000/api/indexer/create
Authorization: Bearer {YOUR_TOKEN}
```

### Method 2: Using cURL

First, get a token using device code flow:

```bash
# Request device code
curl -X POST "https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/devicecode" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id={CLIENT_APP_ID}" \
  -d "scope=api://{API_APP_ID}/Access.API"

# Follow the instructions to authenticate in browser
# Then get the token
curl -X POST "https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=urn:ietf:params:oauth:grant-type:device_code" \
  -d "client_id={CLIENT_APP_ID}" \
  -d "device_code={DEVICE_CODE}"
```

Use the token:
```bash
# List documents
curl http://localhost:8000/api/documents \
  -H "Authorization: Bearer {ACCESS_TOKEN}"

# Upload document
curl -X POST http://localhost:8000/api/documents \
  -H "Authorization: Bearer {ACCESS_TOKEN}" \
  -F "file=@document.pdf"
```

### Method 3: Using Python

```python
import requests
from msal import ConfidentialClientApplication

# Configuration
tenant_id = "your-tenant-id"
client_id = "your-client-app-id"
client_secret = "your-client-secret"
api_scope = f"api://your-api-app-id/Access.API"

# Get token
app = ConfidentialClientApplication(
    client_id,
    authority=f"https://login.microsoftonline.com/{tenant_id}",
    client_credential=client_secret,
)

result = app.acquire_token_for_client(scopes=[api_scope])

if "access_token" in result:
    token = result["access_token"]
    
    # Call API
    headers = {"Authorization": f"Bearer {token}"}
    
    # List documents
    response = requests.get(
        "http://localhost:8000/api/documents",
        headers=headers
    )
    print(response.json())
    
    # Upload document
    with open("test.pdf", "rb") as f:
        files = {"file": f}
        response = requests.post(
            "http://localhost:8000/api/documents",
            headers=headers,
            files=files
        )
    print(response.json())
else:
    print(f"Error: {result.get('error_description')}")
```

---

## Client Integration

### JavaScript/TypeScript Frontend

```typescript
import { PublicClientApplication } from "@azure/msal-browser";

const msalConfig = {
  auth: {
    clientId: "your-client-app-id",
    authority: "https://login.microsoftonline.com/your-tenant-id",
    redirectUri: "https://your-app.com/callback",
  },
};

const msalInstance = new PublicClientApplication(msalConfig);

// Login
async function login() {
  const loginRequest = {
    scopes: ["api://your-api-app-id/Access.API"],
  };
  
  const response = await msalInstance.loginPopup(loginRequest);
  return response.accessToken;
}

// Call protected API
async function uploadDocument(file: File) {
  const token = await getToken();
  
  const formData = new FormData();
  formData.append("file", file);
  
  const response = await fetch("http://localhost:8000/api/documents", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: formData,
  });
  
  return response.json();
}

async function getToken() {
  const accounts = msalInstance.getAllAccounts();
  const request = {
    scopes: ["api://your-api-app-id/Access.API"],
    account: accounts[0],
  };
  
  const response = await msalInstance.acquireTokenSilent(request);
  return response.accessToken;
}
```

---

## Troubleshooting

### Common Issues

#### 1. "Missing Authorization header" (401)
**Cause**: No token sent in request  
**Fix**: Add `Authorization: Bearer {token}` header

#### 2. "Invalid token" (401)
**Causes**:
- Token expired (tokens typically last 1 hour)
- Wrong audience in token
- Invalid signature

**Fixes**:
- Get a new token
- Check `AZURE_AD_AUDIENCE` matches the scope you're requesting
- Verify tenant ID and client ID are correct

#### 3. "Insufficient permissions" (403)
**Cause**: User doesn't have required role  
**Fix**: 
- Go to Enterprise Applications in Azure Portal
- Find your app
- Assign the user to Admin or User role

#### 4. "Token validation failed"
**Causes**:
- Wrong tenant ID
- Wrong client ID
- Network issues reaching Microsoft's key endpoint

**Fixes**:
```bash
# Verify environment variables
echo $AZURE_AD_TENANT_ID
echo $AZURE_AD_CLIENT_ID

# Check server logs for detailed error
tail -f server/logs/app.log
```

#### 5. "No roles claim in token"
**Cause**: User not assigned to app roles  
**Fix**:
1. Azure Portal → Enterprise Applications → Your App
2. Users and groups → Add user/group
3. Select user and assign role

### Verify Token Contents

Decode your token at [jwt.ms](https://jwt.ms) to verify:
- `aud` (audience) matches your `AZURE_AD_AUDIENCE`
- `iss` (issuer) contains your tenant ID
- `roles` array contains expected roles (Admin/User)
- Token hasn't expired (`exp` claim)

### Enable Debug Logging

In your `.env`:
```bash
DEBUG=true
```

Check server logs for detailed authentication errors:
```bash
python server.py 2>&1 | grep -i "auth\|token"
```

---

## Security Best Practices

1. **Never commit tokens or secrets** to version control
2. **Use short token lifetimes** (1 hour is standard)
3. **Implement token refresh** in your client applications
4. **Use HTTPS** in production (Azure Container Apps provides this)
5. **Rotate client secrets** regularly (every 90 days recommended)
6. **Use Managed Identity** in production instead of client secrets
7. **Monitor failed authentication attempts** in Azure AD sign-in logs
8. **Enable Conditional Access** policies for additional security

---

## Next Steps

- [ ] Test authentication with Postman
- [ ] Integrate authentication into your frontend application
- [ ] Set up Conditional Access policies
- [ ] Configure token lifetime policies
- [ ] Enable audit logging
- [ ] Set up alerts for failed authentications
- [ ] Document API for consumers

---

## Support

For issues:
1. Check Azure Portal → Azure AD → Sign-in logs
2. Review server logs for detailed errors
3. Verify environment variables are set correctly
4. Ensure users are assigned to app roles
