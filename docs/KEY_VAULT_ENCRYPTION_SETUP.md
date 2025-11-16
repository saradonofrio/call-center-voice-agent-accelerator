# Azure Key Vault Configuration for Feedback System

## Overview

The feedback system uses Azure Key Vault to securely store the anonymization encryption key required for GDPR compliance. This key is used to encrypt PII anonymization maps, ensuring that sensitive data remains protected even in backup storage.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Azure Infrastructure                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────┐         ┌─────────────────────────┐  │
│  │  Azure Key Vault │◄────────┤  Container App          │  │
│  │                  │         │  - User Assigned        │  │
│  │  Secrets:        │         │    Identity (RBAC)      │  │
│  │  ✓ ACS-CONNECTION│         │  - Env: ANONYMIZATION_  │  │
│  │  ✓ AZURE-SEARCH- │         │    ENCRYPTION_KEY       │  │
│  │  ✓ AZURE-STORAGE-│         │    (secretRef)          │  │
│  │  ✓ AZURE-OPENAI- │         └─────────────────────────┘  │
│  │  ✓ ANONYMIZATION-│                                       │
│  │    ENCRYPTION-KEY│                                       │
│  └──────────────────┘                                       │
│         ▲                                                    │
│         │ RBAC: Key Vault Secrets User                      │
│         │                                                    │
│  ┌──────┴───────────┐                                       │
│  │  User Assigned   │                                       │
│  │  Managed Identity│                                       │
│  └──────────────────┘                                       │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Automatic Provisioning

### Infrastructure Deployment (Bicep)

The anonymization encryption key is automatically created and stored during infrastructure provisioning:

**1. Key Vault Module** (`infra/modules/keyvault.bicep`):
```bicep
resource anonymizationEncryptionKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'ANONYMIZATION-ENCRYPTION-KEY'
  properties: {
    value: base64(guid(keyVault.id, 'anonymization-encryption-key-v1'))
    contentType: 'application/x-fernet-key'
  }
}
```

**2. Container App Configuration** (`infra/modules/containerapp.bicep`):
```bicep
secrets: [
  {
    name: 'anonymization-encryption-key'
    keyVaultUrl: anonymizationEncryptionKeySecretUri
    identity: identityId
  }
]

env: [
  {
    name: 'ANONYMIZATION_ENCRYPTION_KEY'
    secretRef: 'anonymization-encryption-key'
  }
]
```

### Post-Provision Hook

The `infra/hooks/postprovision.sh` script validates and updates the encryption key:

1. **Check if key exists** in Key Vault
2. **Validate Fernet format** (44 characters, base64-encoded)
3. **Generate new key** if invalid or missing (using Python cryptography library)
4. **Update Key Vault** with proper Fernet key

## Environment-Specific Configuration

### Test Environment

When deploying test environment:
```bash
azd env new test-env
azd provision
# postprovision.sh automatically creates/validates encryption key
azd deploy
```

The test environment gets its own encryption key stored in:
- Key Vault: `kv-test-env-xxxxx`
- Secret: `ANONYMIZATION-ENCRYPTION-KEY`

### Production Environment

When deploying production environment:
```bash
azd env new production
azd provision
# postprovision.sh automatically creates/validates encryption key
azd deploy
```

The production environment gets a separate encryption key stored in:
- Key Vault: `kv-production-xxxxx`
- Secret: `ANONYMIZATION-ENCRYPTION-KEY`

## Manual Key Management

### Generate New Encryption Key

If you need to manually generate an encryption key:

**Using Python:**
```bash
cd /workspaces/call-center-voice-agent-accelerator/infra/hooks
python3 generate_encryption_key.py
```

**Using Azure CLI:**
```bash
# Generate key
NEW_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

# Store in Key Vault
az keyvault secret set \
  --vault-name <your-keyvault-name> \
  --name ANONYMIZATION-ENCRYPTION-KEY \
  --value "$NEW_KEY" \
  --content-type application/x-fernet-key
```

### Retrieve Existing Key

```bash
az keyvault secret show \
  --vault-name <your-keyvault-name> \
  --name ANONYMIZATION-ENCRYPTION-KEY \
  --query value -o tsv
```

### Update Key in Specific Environment

```bash
# Switch to environment
azd env select <environment-name>

# Get Key Vault name
KEY_VAULT_NAME=$(azd env get-values | grep AZURE_KEY_VAULT_NAME | cut -d'=' -f2 | tr -d '"')

# Generate and update key
NEW_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
az keyvault secret set --vault-name "$KEY_VAULT_NAME" --name ANONYMIZATION-ENCRYPTION-KEY --value "$NEW_KEY"

# Restart container app to pick up new key
CONTAINER_APP=$(az containerapp list --resource-group $(azd env get-values | grep AZURE_RESOURCE_GROUP | cut -d'=' -f2 | tr -d '"') --query "[0].name" -o tsv)
az containerapp revision restart --name "$CONTAINER_APP" --resource-group $(azd env get-values | grep AZURE_RESOURCE_GROUP | cut -d'=' -f2 | tr -d '"')
```

## Security Considerations

### RBAC Permissions

The Container App's User Assigned Managed Identity has the following permissions:

```bicep
// Key Vault Secrets User role
roleDefinition: '4633458b-17de-408a-b874-0445c86b69e6'
```

This allows the app to:
- ✅ Read secrets (including encryption key)
- ❌ Cannot list all secrets
- ❌ Cannot modify or delete secrets
- ❌ Cannot manage Key Vault policies

### Key Rotation

⚠️ **IMPORTANT**: Rotating the encryption key requires careful planning:

1. **Backup existing key** before rotation
2. **Decrypt all anonymization maps** with old key
3. **Re-encrypt with new key**
4. **Update Key Vault secret**
5. **Restart Container App**

**Key Rotation Script** (use with caution):
```bash
# TODO: Implement key rotation script
# This requires:
# 1. Download all anonymization maps from Azure Storage
# 2. Decrypt with old key
# 3. Re-encrypt with new key
# 4. Upload back to Azure Storage
# 5. Update Key Vault
```

### Backup and Recovery

**Backup Key Vault:**
```bash
# Export secret (store securely!)
az keyvault secret show \
  --vault-name <your-keyvault-name> \
  --name ANONYMIZATION-ENCRYPTION-KEY \
  --query value -o tsv > encryption-key-backup.txt

# Secure the backup file
chmod 600 encryption-key-backup.txt
```

**Restore from Backup:**
```bash
# Read from backup
BACKUP_KEY=$(cat encryption-key-backup.txt)

# Restore to Key Vault
az keyvault secret set \
  --vault-name <your-keyvault-name> \
  --name ANONYMIZATION-ENCRYPTION-KEY \
  --value "$BACKUP_KEY"
```

## Application Usage

### Encryption Utils Integration

The `EncryptionUtils` class automatically reads from Key Vault:

```python
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

# In production (Container App with Managed Identity)
credential = DefaultAzureCredential()
key_vault_client = SecretClient(
    vault_url=f"https://{os.environ['AZURE_KEY_VAULT_NAME']}.vault.azure.net/",
    credential=credential
)

# Initialize encryption utils
encryption_utils = EncryptionUtils(
    key_vault_client=key_vault_client,
    secret_name="ANONYMIZATION-ENCRYPTION-KEY"
)
```

### Fallback for Local Development

For local development without Key Vault access:

```bash
# Option 1: Use environment variable
export ANONYMIZATION_ENCRYPTION_KEY="your-fernet-key-here"

# Option 2: Let it generate temporary key (NOT for production)
# WARNING: Data encrypted with temporary key cannot be decrypted after restart
```

## Verification

### Check Key Vault Configuration

```bash
# List all environments
azd env list

# Select environment
azd env select <environment-name>

# Get Key Vault name
azd env get-values | grep AZURE_KEY_VAULT_NAME

# Check secret exists
KEY_VAULT_NAME=$(azd env get-values | grep AZURE_KEY_VAULT_NAME | cut -d'=' -f2 | tr -d '"')
az keyvault secret show --vault-name "$KEY_VAULT_NAME" --name ANONYMIZATION-ENCRYPTION-KEY
```

### Verify Container App Configuration

```bash
# Get Container App details
RESOURCE_GROUP=$(azd env get-values | grep AZURE_RESOURCE_GROUP | cut -d'=' -f2 | tr -d '"')
CONTAINER_APP=$(az containerapp list --resource-group "$RESOURCE_GROUP" --query "[0].name" -o tsv)

# Check environment variables
az containerapp show \
  --name "$CONTAINER_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --query "properties.template.containers[0].env[?name=='ANONYMIZATION_ENCRYPTION_KEY']"

# Check secrets
az containerapp show \
  --name "$CONTAINER_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --query "properties.configuration.secrets[?name=='anonymization-encryption-key']"
```

### Test Encryption/Decryption

```bash
# Test in running container
az containerapp exec \
  --name "$CONTAINER_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --command "python -c \"
from app.encryption_utils import get_encryption_utils
utils = get_encryption_utils()
test_map = {'key1': 'value1', 'key2': 'value2'}
encrypted = utils.encrypt_map(test_map)
decrypted = utils.decrypt_map(encrypted)
assert test_map == decrypted
print('✓ Encryption/decryption test passed')
\""
```

## Troubleshooting

### Error: "Cannot initialize encryption without valid key from Key Vault"

**Cause**: Container App cannot access Key Vault secret

**Solution**:
1. Check Managed Identity has Key Vault Secrets User role
2. Verify secret exists in Key Vault
3. Check Container App secret configuration

```bash
# Verify RBAC assignment
az role assignment list \
  --assignee $(azd env get-values | grep AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID | cut -d'=' -f2 | tr -d '"') \
  --scope "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.KeyVault/vaults/$KEY_VAULT_NAME"
```

### Error: "Invalid Fernet key"

**Cause**: Encryption key is not properly formatted

**Solution**: Regenerate key using postprovision script or manually:
```bash
./infra/hooks/postprovision.sh
```

### Different Keys in Test vs. Production

This is **expected behavior**. Each environment should have its own encryption key for isolation:
- Test environment can be reset without affecting production
- Production data cannot be decrypted with test key (security boundary)
- Each environment is independent

## Migration Guide

### Migrating from Environment Variable to Key Vault

If you previously used `ANONYMIZATION_ENCRYPTION_KEY` environment variable:

1. **Export existing key**:
```bash
EXISTING_KEY=$(azd env get-values | grep ANONYMIZATION_ENCRYPTION_KEY | cut -d'=' -f2 | tr -d '"')
echo "$EXISTING_KEY" > backup-encryption-key.txt
```

2. **Store in Key Vault**:
```bash
KEY_VAULT_NAME=$(azd env get-values | grep AZURE_KEY_VAULT_NAME | cut -d'=' -f2 | tr -d '"')
az keyvault secret set \
  --vault-name "$KEY_VAULT_NAME" \
  --name ANONYMIZATION-ENCRYPTION-KEY \
  --value "$EXISTING_KEY"
```

3. **Redeploy** with updated Bicep configuration:
```bash
azd deploy
```

4. **Verify** existing data can still be decrypted

## Best Practices

1. ✅ **Never commit encryption keys to Git**
2. ✅ **Use Key Vault for all environments** (test and production)
3. ✅ **Backup encryption keys** securely (offline storage, password manager)
4. ✅ **Use separate keys per environment** for isolation
5. ✅ **Monitor Key Vault access logs** for security auditing
6. ✅ **Enable Key Vault soft delete and purge protection**
7. ✅ **Document key rotation procedures** before they're needed
8. ❌ **Don't share encryption keys between environments**
9. ❌ **Don't rotate keys without proper backup/recovery plan**
10. ❌ **Don't use temporary keys in production**

## References

- [Azure Key Vault Overview](https://docs.microsoft.com/azure/key-vault/general/overview)
- [Managed Identities for Azure Resources](https://docs.microsoft.com/azure/active-directory/managed-identities-azure-resources/overview)
- [Fernet (symmetric encryption)](https://cryptography.io/en/latest/fernet/)
- [Azure Container Apps Secrets](https://docs.microsoft.com/azure/container-apps/manage-secrets)
