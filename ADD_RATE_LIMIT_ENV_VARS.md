# How to Add Rate Limiting Environment Variables to Your Container App

## Problem
After running `azd deploy`, the new rate limiting environment variables are not present in the Container App because `azd deploy` only updates the container image, not the infrastructure configuration.

## Solution Options

### Option 1: Manual Add via Azure Portal (FASTEST)

1. **Go to Azure Portal** → Navigate to your Container App
2. **Click "Containers"** in the left menu
3. **Click "Environment variables"** tab
4. **Click "+ Add"** and add each of these 4 variables:

   | Name | Value |
   |------|-------|
   | `RATE_LIMIT_UPLOADS` | `10 per hour` |
   | `RATE_LIMIT_API` | `100 per hour` |
   | `RATE_LIMIT_WEBSOCKET` | `20 per hour` |
   | `RATE_LIMIT_ADMIN` | `50 per hour` |

5. **Click "Save"** at the top
6. **Wait for the revision to deploy** (Container App will restart automatically)

### Option 2: Re-provision Infrastructure (RECOMMENDED for production)

This ensures your Bicep files are the source of truth:

```bash
# From the root of the project
azd provision
```

This will:
- Re-run the Bicep deployment
- Add the new environment variables from `containerapp.bicep`
- Keep all existing resources intact
- NOT rebuild the container image (faster than `azd up`)

### Option 3: Full Re-deployment

```bash
# From the root of the project
azd up
```

This will:
- Re-provision infrastructure (Bicep)
- Rebuild and redeploy the container image
- Takes longer but ensures everything is in sync

## Verification

After adding the variables (via any method), verify they exist:

1. **Azure Portal** → Container App → Containers → Environment variables
2. **OR via Azure CLI**:
   ```bash
   az containerapp show \
     --name <your-container-app-name> \
     --resource-group <your-resource-group> \
     --query "properties.template.containers[0].env" \
     --output table
   ```

You should see all 4 `RATE_LIMIT_*` variables listed.

## Why This Happened

- **`azd deploy`**: Only updates the container image (rebuilds and pushes)
- **`azd provision`**: Only updates infrastructure (Bicep templates)
- **`azd up`**: Does both (provision + deploy)

Since we added new environment variables to the Bicep files, we need to run `azd provision` or `azd up` to apply those infrastructure changes.

## Recommended Approach

For now: **Use Option 1 (Manual)** - fastest way to test rate limiting

For future: **Always use `azd up`** after Bicep changes to ensure infrastructure and code are in sync

## Next Steps After Adding Variables

1. **Verify the container restarted** (check Azure Portal logs)
2. **Test rate limiting**:
   ```bash
   # Make 11 rapid upload requests (should get 429 on the 11th)
   AZURE_URL="https://your-app.azurewebsites.net"
   for i in {1..11}; do
     echo "Request $i"
     curl -X POST $AZURE_URL/api/documents -F "file=@test.pdf"
   done
   ```
3. **Monitor Application Insights** for HTTP 429 responses
