# Azure AD Authentication Implementation Summary

## What Was Implemented

✅ **Full Azure AD / Entra ID authentication** for API endpoints using JWT tokens

### Files Created/Modified

1. **`server/app/auth.py`** (NEW)
   - `AzureADAuth` class for token validation
   - `require_auth()` decorator for protected endpoints
   - `require_auth_optional()` decorator for optional auth
   - Role-based access control (RBAC) support

2. **`server/server.py`** (MODIFIED)
   - Added Azure AD configuration
   - Protected all document management endpoints
   - Protected indexer management endpoints
   - Added role requirements:
     - **Admin role**: Delete documents, create/run indexer
     - **Admin or User role**: Upload, list documents, view indexer status

3. **`server/pyproject.toml`** (MODIFIED)
   - Added `PyJWT[crypto]>=2.8.0`
   - Added `cryptography>=41.0.0`

4. **`server/AZURE_AD_AUTH_SETUP.md`** (NEW)
   - Complete setup guide
   - Azure Portal configuration steps
   - Testing examples (Postman, cURL, Python)
   - Troubleshooting guide

5. **`server/.env-sample-with-auth.txt`** (NEW)
   - Updated environment template with Azure AD variables

## Protected Endpoints

| Endpoint | Method | Required Role | Description |
|----------|--------|---------------|-------------|
| `/api/documents` | POST | Admin or User | Upload documents |
| `/api/documents` | GET | Admin or User | List documents |
| `/api/documents/<id>` | DELETE | Admin | Delete document |
| `/api/indexer/create` | POST | Admin | Create indexer |
| `/api/indexer/run` | POST | Admin | Run indexer |
| `/api/indexer/status` | GET | Admin or User | Get indexer status |

**Unprotected endpoints** (by design):
- `/` - Web interface
- `/acs/incomingcall` - EventGrid webhook (validated by EventGrid)
- `/acs/callbacks/<id>` - ACS callbacks (trusted source)
- `/acs/ws` - ACS WebSocket (phone calls)
- `/web/ws` - Web WebSocket (consider adding auth in future)

## What You Need to Do on Azure Portal

### Quick Checklist

- [ ] **Step 1**: Register API application in Azure AD
- [ ] **Step 2**: Expose API and create scope (`Access.API`)
- [ ] **Step 3**: Create App Roles (`Admin`, `User`)
- [ ] **Step 4**: Assign users to roles
- [ ] **Step 5**: Register client application (for testing/frontend)
- [ ] **Step 6**: Grant API permissions to client
- [ ] **Step 7**: Create client secret
- [ ] **Step 8**: Get Tenant ID, Client IDs, and configure `.env`

### Detailed Instructions

See **`AZURE_AD_AUTH_SETUP.md`** for complete step-by-step guide.

## Environment Variables to Add

Add these to your `.env` file:

```bash
AZURE_AD_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_AD_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_AD_AUDIENCE=api://your-client-id  # Optional
```

## Installation

```bash
cd server
pip install PyJWT[crypto] cryptography

# Or with uv:
uv sync
```

## Testing

### Quick Test with Postman

1. Set up OAuth 2.0 in Postman (see setup guide)
2. Get access token
3. Test endpoint:
   ```
   GET http://localhost:8000/api/documents
   Authorization: Bearer {YOUR_TOKEN}
   ```

### Expected Responses

**✅ Success (200)**:
```json
{
  "documents": [...]
}
```

**❌ No token (401)**:
```json
{
  "error": "Missing Authorization header"
}
```

**❌ Invalid token (401)**:
```json
{
  "error": "Invalid token"
}
```

**❌ Wrong role (403)**:
```json
{
  "error": "Insufficient permissions",
  "required_roles": ["Admin"]
}
```

## How It Works

```
1. Client requests token from Azure AD
   ↓
2. Azure AD validates user and issues JWT token (contains roles)
   ↓
3. Client sends request with: Authorization: Bearer {token}
   ↓
4. Server validates token signature using Microsoft's public keys
   ↓
5. Server checks token audience, issuer, expiration
   ↓
6. Server checks if user has required role
   ↓
7. Request allowed (user info available in g.user)
```

## Security Features

✅ **JWT signature validation** using Microsoft's public keys  
✅ **Token expiration checking**  
✅ **Audience validation** (ensures token is for this API)  
✅ **Issuer validation** (ensures token from correct tenant)  
✅ **Role-based access control** (Admin vs User permissions)  
✅ **User context tracking** (access user info in endpoints via `g.user`)  

## Optional: Enable Auth for WebSocket

Currently, the `/web/ws` WebSocket endpoint is **not protected** by Azure AD auth (by design, for simplicity).

To add authentication to WebSocket:

```python
@app.websocket("/web/ws")
async def web_ws():
    # Validate token from query parameter or first message
    token = request.args.get('token')
    
    if azure_ad_auth:
        try:
            token_claims = azure_ad_auth.validate_token(token)
            # Connection authenticated
        except Exception:
            await websocket.close(1008, "Unauthorized")
            return
    
    # ... rest of code
```

## Graceful Degradation

If `AZURE_AD_TENANT_ID` and `AZURE_AD_CLIENT_ID` are **not set**:
- Server starts normally
- Endpoints are **UNPROTECTED** (no authentication)
- Warning logged: "Azure AD authentication NOT configured"

This allows:
- ✅ Local development without Azure AD setup
- ✅ Testing without authentication
- ⚠️ **NOT for production** - always enable auth in production!

## Production Deployment

For Azure Container Apps deployment, add these to your Bicep/environment:

```bicep
{
  name: 'AZURE_AD_TENANT_ID'
  value: tenantId  // From Azure
}
{
  name: 'AZURE_AD_CLIENT_ID'
  value: apiAppClientId  // From app registration
}
{
  name: 'AZURE_AD_AUDIENCE'
  value: 'api://${apiAppClientId}'
}
```

## Next Steps

1. **Complete Azure Portal setup** (see `AZURE_AD_AUTH_SETUP.md`)
2. **Update `.env`** with tenant ID and client ID
3. **Install dependencies**: `pip install PyJWT[crypto] cryptography`
4. **Test with Postman** to verify authentication works
5. **Integrate into your frontend** application
6. **Deploy to Azure** with auth variables configured

## Support

For questions or issues:
- Check `AZURE_AD_AUTH_SETUP.md` troubleshooting section
- Review Azure AD sign-in logs in Azure Portal
- Check server logs for detailed error messages
- Verify environment variables are set correctly
