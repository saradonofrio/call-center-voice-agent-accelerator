# Rate Limiting Implementation Guide

## Overview

Rate limiting has been implemented to protect the application from:
- **DoS attacks** via document upload flooding
- **WebSocket connection exhaustion** from excessive concurrent connections
- **API abuse** and resource depletion from rapid repeated calls
- **Storage exhaustion** from unlimited document uploads
- **Indexer abuse** from excessive admin operations

## Implementation Details

### Libraries Used
- **quart-rate-limiter** (>=0.10.0): Provides rate limiting decorators for Quart routes

### Rate Limit Tiers

The application uses four different rate limit tiers based on endpoint sensitivity:

| Tier | Default Limit | Applied To | Purpose |
|------|--------------|------------|---------|
| **UPLOADS** | 10 per hour | POST `/api/documents` | Prevent storage exhaustion from document uploads |
| **API** | 100 per hour | GET `/api/documents`<br>DELETE `/api/documents/<id>`<br>GET `/api/indexer/status` | Allow normal API usage while preventing abuse |
| **WEBSOCKET** | 20 per hour | WebSocket `/acs/ws`<br>WebSocket `/web/ws` | Prevent connection pool exhaustion |
| **ADMIN** | 50 per hour | POST `/api/indexer/create`<br>POST `/api/indexer/run` | Prevent indexer abuse |

### Protected Endpoints

#### Document Management (Strictest)
```python
@app.route("/api/documents", methods=["POST"])
@rate_limit(RATE_LIMIT_UPLOADS)  # 10 per hour
async def upload_documents():
```

#### WebSocket Connections (Moderate)
```python
@app.websocket("/acs/ws")
@rate_limit(RATE_LIMIT_WEBSOCKET)  # 20 per hour
async def acs_ws():

@app.websocket("/web/ws")
@rate_limit(RATE_LIMIT_WEBSOCKET)  # 20 per hour
async def web_ws():
```

#### Admin Operations (Moderate)
```python
@app.route("/api/indexer/create", methods=["POST"])
@rate_limit(RATE_LIMIT_ADMIN)  # 50 per hour
async def create_indexer():

@app.route("/api/indexer/run", methods=["POST"])
@rate_limit(RATE_LIMIT_ADMIN)  # 50 per hour
async def run_indexer():
```

#### General API Operations (Lenient)
```python
@app.route("/api/documents", methods=["GET"])
@rate_limit(RATE_LIMIT_API)  # 100 per hour
async def list_documents():

@app.route("/api/documents/<path:document_id>", methods=["DELETE"])
@rate_limit(RATE_LIMIT_API)  # 100 per hour
async def delete_document(document_id):

@app.route("/api/indexer/status", methods=["GET"])
@rate_limit(RATE_LIMIT_API)  # 100 per hour
async def get_indexer_status():
```

## Configuration

### Environment Variables

All rate limits are configurable via environment variables:

```bash
# Document uploads (strictest - prevents storage exhaustion)
RATE_LIMIT_UPLOADS=10 per hour

# General API calls (moderate - allows normal usage)
RATE_LIMIT_API=100 per hour

# WebSocket connections (moderate - prevents connection pool exhaustion)
RATE_LIMIT_WEBSOCKET=20 per hour

# Admin operations (moderate - prevents indexer abuse)
RATE_LIMIT_ADMIN=50 per hour
```

### Supported Formats

The rate limiting library supports various time periods:
- `"10 per hour"` - 10 requests per hour
- `"100 per day"` - 100 requests per day
- `"5 per minute"` - 5 requests per minute
- `"1000 per month"` - 1000 requests per month

### Azure Deployment

Rate limits are configured in Bicep for Azure Container Apps:

**infra/main.parameters.json:**
```json
{
  "rateLimitUploads": {
    "value": "${RATE_LIMIT_UPLOADS=10 per hour}"
  },
  "rateLimitApi": {
    "value": "${RATE_LIMIT_API=100 per hour}"
  },
  "rateLimitWebSocket": {
    "value": "${RATE_LIMIT_WEBSOCKET=20 per hour}"
  },
  "rateLimitAdmin": {
    "value": "${RATE_LIMIT_ADMIN=50 per hour}"
  }
}
```

## How It Works

1. **Initialization** (server.py):
   ```python
   from quart_rate_limiter import RateLimiter, rate_limit
   
   rate_limiter = RateLimiter(app)
   RATE_LIMIT_UPLOADS = os.environ.get("RATE_LIMIT_UPLOADS", "10 per hour")
   RATE_LIMIT_API = os.environ.get("RATE_LIMIT_API", "100 per hour")
   RATE_LIMIT_WEBSOCKET = os.environ.get("RATE_LIMIT_WEBSOCKET", "20 per hour")
   RATE_LIMIT_ADMIN = os.environ.get("RATE_LIMIT_ADMIN", "50 per hour")
   ```

2. **Decorator Application**:
   - Each endpoint is decorated with `@rate_limit(RATE_LIMIT_TIER)`
   - The decorator tracks requests per IP address
   - When limit is exceeded, returns HTTP 429 (Too Many Requests)

3. **Rate Limit Response**:
   ```json
   {
     "error": "Too Many Requests",
     "message": "Rate limit exceeded. Please try again later.",
     "retry_after": 3600
   }
   ```

## Testing Rate Limits

### Local Testing

1. **Install dependencies**:
   ```bash
   cd server
   pip install quart-rate-limiter
   ```

2. **Run the application**:
   ```bash
   python server.py
   ```

3. **Test document upload rate limit** (10 per hour):
   ```bash
   # Make 11 rapid requests - the 11th should fail with 429
   for i in {1..11}; do
     curl -X POST http://localhost:8000/api/documents \
       -F "file=@test.pdf" \
       -H "Authorization: Bearer $TOKEN"
   done
   ```

4. **Test API rate limit** (100 per hour):
   ```bash
   # Make 101 rapid requests - the 101st should fail with 429
   for i in {1..101}; do
     curl http://localhost:8000/api/documents
   done
   ```

### Azure Testing

After deployment with `azd deploy`, test the same way using your Azure Container App URL:

```bash
AZURE_URL="https://your-container-app.azurewebsites.net"

# Test upload rate limit
for i in {1..11}; do
  curl -X POST $AZURE_URL/api/documents \
    -F "file=@test.pdf"
done
```

## Customization Recommendations

### Development Environment
- **RATE_LIMIT_UPLOADS**: `100 per hour` (higher for testing)
- **RATE_LIMIT_API**: `1000 per hour` (very lenient)
- **RATE_LIMIT_WEBSOCKET**: `100 per hour` (higher for testing)
- **RATE_LIMIT_ADMIN**: `500 per hour` (very lenient)

### Production Environment
- **RATE_LIMIT_UPLOADS**: `10 per hour` (strict - prevents abuse)
- **RATE_LIMIT_API**: `100 per hour` (moderate - allows normal usage)
- **RATE_LIMIT_WEBSOCKET**: `20 per hour` (moderate - prevents exhaustion)
- **RATE_LIMIT_ADMIN**: `50 per hour` (moderate - prevents indexer abuse)

### High-Traffic Production
- **RATE_LIMIT_UPLOADS**: `50 per hour` (moderate - accommodates legitimate users)
- **RATE_LIMIT_API**: `500 per hour` (lenient - supports high traffic)
- **RATE_LIMIT_WEBSOCKET**: `100 per hour` (lenient - supports many users)
- **RATE_LIMIT_ADMIN**: `200 per hour` (lenient - supports admin operations)

## Monitoring

### Logs

Rate limit violations are logged by quart-rate-limiter. Check application logs for:

```
[INFO] Rate limiting enabled - Uploads: 10 per hour, API: 100 per hour, WebSocket: 20 per hour, Admin: 50 per hour
[WARNING] Rate limit exceeded for <endpoint> from <ip_address>
```

### Azure Application Insights

In Azure Portal → Application Insights → Logs, query for rate limit events:

```kusto
requests
| where resultCode == 429
| summarize count() by url, bin(timestamp, 1h)
| order by timestamp desc
```

## Security Benefits

1. **DoS Protection**: Prevents attackers from overwhelming the server with requests
2. **Resource Conservation**: Limits resource consumption per user/IP
3. **Fair Usage**: Ensures all users get reasonable access to the service
4. **Cost Control**: Prevents unexpected Azure costs from abuse
5. **Storage Protection**: Prevents storage exhaustion from unlimited uploads
6. **Connection Pool Protection**: Prevents WebSocket connection exhaustion

## Related Security Features

This rate limiting implementation works alongside:
- **CORS Configuration**: Controls cross-origin access (see ENVIRONMENT_VARIABLES_SETUP.md)
- **Azure AD Authentication**: Controls who can access endpoints (see AZURE_AD_AUTH_SETUP.md)
- **Input Validation**: Validates file types, sizes, and content (see server.py)

## Troubleshooting

### Issue: Rate limit too restrictive for legitimate users

**Solution**: Increase the rate limit via environment variable:
```bash
# Local
export RATE_LIMIT_API="500 per hour"

# Azure
azd env set RATE_LIMIT_API "500 per hour"
azd deploy
```

### Issue: Rate limit not working

**Checklist**:
1. Verify `quart-rate-limiter` is installed: `pip list | grep quart-rate-limiter`
2. Check logs for initialization: `"Rate limiting enabled - ..."`
3. Verify decorator is applied: `@rate_limit(RATE_LIMIT_TIER)`
4. Test with rapid requests exceeding the limit

### Issue: All requests blocked even under limit

**Solution**: Check if rate limiter is using IP address correctly. If behind a proxy, ensure X-Forwarded-For headers are configured.

## Next Steps

1. **Deploy and test**: Deploy to Azure and verify rate limiting works
2. **Monitor usage**: Check Application Insights for 429 responses
3. **Adjust limits**: Fine-tune rate limits based on actual usage patterns
4. **Add authentication**: Combine with Azure AD for user-specific rate limits
5. **Per-user limits**: Implement different rate limits based on user roles (requires authentication)

## References

- [quart-rate-limiter Documentation](https://github.com/Quart-Addons/quart-rate-limiter)
- [OWASP Rate Limiting Guide](https://owasp.org/www-community/controls/Blocking_Brute_Force_Attacks)
- [Azure Best Practices for API Security](https://learn.microsoft.com/en-us/azure/architecture/best-practices/api-design)
