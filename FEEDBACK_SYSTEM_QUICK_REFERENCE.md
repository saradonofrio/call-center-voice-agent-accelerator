# Feedback System - Quick Reference

## 🚀 Deployment

### Test Environment
```bash
azd env new test-env
azd provision   # Creates Key Vault, generates encryption key automatically
azd deploy
```

### Production Environment
```bash
azd env new production
azd provision   # Creates separate Key Vault with separate encryption key
azd deploy
```

## 🔑 Encryption Key Management

### Check Current Key
```bash
# Get Key Vault name
KEY_VAULT=$(azd env get-values | grep AZURE_KEY_VAULT_NAME | cut -d'=' -f2 | tr -d '"')

# View encryption key
az keyvault secret show --vault-name "$KEY_VAULT" --name ANONYMIZATION-ENCRYPTION-KEY
```

### Backup Encryption Key
```bash
az keyvault secret show --vault-name "$KEY_VAULT" --name ANONYMIZATION-ENCRYPTION-KEY --query value -o tsv > backup-key.txt
chmod 600 backup-key.txt
```

### Regenerate Key (Advanced)
```bash
# Generate new key
NEW_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

# Update in Key Vault
az keyvault secret set --vault-name "$KEY_VAULT" --name ANONYMIZATION-ENCRYPTION-KEY --value "$NEW_KEY"

# Restart container app
RESOURCE_GROUP=$(azd env get-values | grep AZURE_RESOURCE_GROUP | cut -d'=' -f2 | tr -d '"')
CONTAINER_APP=$(az containerapp list --resource-group "$RESOURCE_GROUP" --query "[0].name" -o tsv)
az containerapp revision restart --name "$CONTAINER_APP" --resource-group "$RESOURCE_GROUP"
```

## 📊 Admin Dashboard

### Access Dashboard
```
https://<your-container-app-url>/static/admin/index.html
```

### Features
- **Conversations Tab**: View all conversations with PII anonymization
- **Analytics Tab**: View metrics (total conversations, ratings, approved responses)
- **Feedback**: Rate 1-5 stars, add tags, provide corrections
- **Approve for Learning**: Index approved responses for RAG retrieval

## 🔍 API Endpoints

### Conversation Management
```bash
# List conversations
curl https://<app-url>/admin/api/conversations?page=1&page_size=20

# Get conversation detail
curl https://<app-url>/admin/api/conversations/<conversation-id>
```

### Feedback Submission
```bash
curl -X POST https://<app-url>/admin/api/feedback/<conversation-id> \
  -H "Content-Type: application/json" \
  -d '{
    "conversation_id": "uuid",
    "turn_number": 1,
    "rating": 5,
    "tags": ["helpful", "accurate"],
    "admin_comment": "Great response",
    "corrected_response": ""
  }'
```

### Approve for Learning
```bash
curl -X POST https://<app-url>/admin/api/approve/<conversation-id>/<turn-number>
```

### GDPR Requests
```bash
# Data access request
curl -X POST https://<app-url>/api/gdpr/data-access \
  -H "Content-Type: application/json" \
  -d '{"identifier": "+39123456789", "identifier_type": "phone"}'

# Data erasure request
curl -X DELETE https://<app-url>/api/gdpr/data-erasure \
  -H "Content-Type: application/json" \
  -d '{"identifier": "+39123456789", "identifier_type": "phone"}'
```

### Analytics
```bash
curl https://<app-url>/admin/api/analytics/dashboard
```

## 🗄️ Azure Storage Containers

### Containers Created Automatically
- `conversations` - Anonymized conversation logs
- `anonymization-maps` - Encrypted PII mappings
- `feedback` - Admin feedback submissions
- `approved-responses` - Approved responses backup
- `audit-logs` - GDPR audit trail

### View Containers
```bash
STORAGE_ACCOUNT=$(azd env get-values | grep AZURE_STORAGE_ACCOUNT_NAME | cut -d'=' -f2 | tr -d '"')
az storage container list --account-name "$STORAGE_ACCOUNT" --output table
```

## 🔐 Key Vault Secrets

### Secrets Stored Automatically
- `ACS-CONNECTION-STRING` - Azure Communication Services
- `AZURE-SEARCH-API-KEY` - Azure AI Search
- `AZURE-STORAGE-CONNECTION-STRING` - Azure Storage
- `AZURE-OPENAI-KEY` - Azure OpenAI
- `ANONYMIZATION-ENCRYPTION-KEY` - PII encryption (auto-generated)

### List Secrets
```bash
az keyvault secret list --vault-name "$KEY_VAULT" --query "[].name" -o table
```

## 🔧 Troubleshooting

### Check Container App Logs
```bash
RESOURCE_GROUP=$(azd env get-values | grep AZURE_RESOURCE_GROUP | cut -d'=' -f2 | tr -d '"')
CONTAINER_APP=$(az containerapp list --resource-group "$RESOURCE_GROUP" --query "[0].name" -o tsv)

az containerapp logs show --name "$CONTAINER_APP" --resource-group "$RESOURCE_GROUP" --follow
```

### Verify Encryption Key Works
```bash
# Test encryption/decryption
az containerapp exec \
  --name "$CONTAINER_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --command "python -c \"
from app.encryption_utils import get_encryption_utils
utils = get_encryption_utils()
test = {'key': 'value'}
encrypted = utils.encrypt_map(test)
decrypted = utils.decrypt_map(encrypted)
print('✓ Works!' if test == decrypted else '✗ Failed')
\""
```

### Check RBAC Permissions
```bash
# Verify Managed Identity has Key Vault access
IDENTITY_ID=$(azd env get-values | grep AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID | cut -d'=' -f2 | tr -d '"')

az role assignment list \
  --assignee "$IDENTITY_ID" \
  --scope "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/$RESOURCE_GROUP" \
  --output table
```

## 📈 Monitoring

### View Analytics in Portal
```bash
# Get Application Insights
APP_INSIGHTS=$(az monitor app-insights component list --resource-group "$RESOURCE_GROUP" --query "[0].name" -o tsv)

echo "Application Insights: $APP_INSIGHTS"
echo "View logs in Azure Portal > Application Insights > Logs"
```

### Key Metrics to Monitor
- Total conversations per day
- Average rating per conversation
- Number of approved responses
- PII detection rate
- GDPR requests count

## 🔄 Data Retention

### Default Retention Policies
- Conversations: 90 days
- Anonymization maps: 365 days
- Feedback: Permanent (until manually deleted)
- Approved responses: Permanent
- Audit logs: 365 days

### Manual Cleanup (if needed)
```bash
# Run GDPR cleanup
# This is automated via scheduled task in production
python server/app/gdpr_compliance.py
```

## 📚 Documentation

### Full Documentation
- `/FEEDBACK_SYSTEM_IMPLEMENTATION_SUMMARY.md` - Complete implementation details
- `/docs/KEY_VAULT_ENCRYPTION_SETUP.md` - Key Vault configuration guide
- `/docs/FEEDBACK_SYSTEM_SETUP.md` - Setup instructions (TODO)

### Code Files
- `/server/app/pii_anonymizer.py` - PII detection and anonymization
- `/server/app/encryption_utils.py` - Encryption utilities
- `/server/app/conversation_logger.py` - Conversation tracking
- `/server/app/feedback_indexer.py` - Azure AI Search integration
- `/server/app/gdpr_compliance.py` - GDPR utilities
- `/server/app/analytics.py` - Analytics and metrics

### Infrastructure
- `/infra/modules/keyvault.bicep` - Key Vault with encryption key
- `/infra/modules/containerapp.bicep` - Container App configuration
- `/infra/hooks/postprovision.sh` - Post-provision validation

## ⚡ Quick Commands

```bash
# Deploy to test
azd env select test-env && azd deploy

# Deploy to production
azd env select production && azd deploy

# View logs
azd monitor --follow

# Check environment
azd env get-values | grep -E "(KEY_VAULT|STORAGE|SEARCH)"

# Restart app
RESOURCE_GROUP=$(azd env get-values | grep AZURE_RESOURCE_GROUP | cut -d'=' -f2 | tr -d '"')
CONTAINER_APP=$(az containerapp list --resource-group "$RESOURCE_GROUP" --query "[0].name" -o tsv)
az containerapp revision restart --name "$CONTAINER_APP" --resource-group "$RESOURCE_GROUP"
```

## 🆘 Support

### Common Issues

**"Cannot initialize encryption without valid key"**
→ Run: `./infra/hooks/postprovision.sh` to regenerate key

**"PII not detected"**
→ Check patterns in `/server/app/pii_patterns.py` for Italian context

**"Conversations not appearing"**
→ Verify Azure Storage connection and containers exist

**"Search index not found"**
→ Index auto-created on first approval, check Azure AI Search endpoint

---
**Version**: 1.0  
**Last Updated**: November 2024
