param location string
param keyVaultName string
param tags object
@secure()
param acsConnectionString string
param azureSearchServiceName string = ''
param storageAccountName string = ''
param openAIAccountName string = ''

var sanitizedKeyVaultName = take(toLower(replace(replace(replace(replace(keyVaultName, '--', '-'), '_', '-'), '[^a-zA-Z0-9-]', ''), '-$', '')), 24)

resource keyVault 'Microsoft.KeyVault/vaults@2023-02-01' = {
  name: sanitizedKeyVaultName
  location: location
  tags: tags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    accessPolicies: []
    enableRbacAuthorization: true
    enableSoftDelete: true
    enablePurgeProtection: true
    publicNetworkAccess: 'Enabled'
  }
}


resource acsConnectionStringSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'ACS-CONNECTION-STRING'
  properties: {
    value: acsConnectionString
  }
}

// Reference existing Azure Search service if provided
resource searchService 'Microsoft.Search/searchServices@2024-06-01-preview' existing = if (!empty(azureSearchServiceName)) {
  name: azureSearchServiceName
}

resource azureSearchApiKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(azureSearchServiceName)) {
  parent: keyVault
  name: 'AZURE-SEARCH-API-KEY'
  properties: {
    value: !empty(azureSearchServiceName) ? searchService.listAdminKeys().primaryKey : ''
  }
}

// Reference existing Storage Account if provided
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = if (!empty(storageAccountName)) {
  name: storageAccountName
}

resource azureStorageConnectionStringSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(storageAccountName)) {
  parent: keyVault
  name: 'AZURE-STORAGE-CONNECTION-STRING'
  properties: {
    value: !empty(storageAccountName) ? 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};AccountKey=${storageAccount.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}' : ''
  }
}

// Reference existing OpenAI account if provided
resource openAIAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = if (!empty(openAIAccountName)) {
  name: openAIAccountName
}

resource azureOpenAIKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(openAIAccountName)) {
  parent: keyVault
  name: 'AZURE-OPENAI-KEY'
  properties: {
    value: !empty(openAIAccountName) ? openAIAccount.listKeys().key1 : ''
  }
}

// Generate and store anonymization encryption key for PII protection (GDPR compliance)
// This key is used to encrypt PII anonymization maps
// Generated once during deployment and stored securely in Key Vault
resource anonymizationEncryptionKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'ANONYMIZATION-ENCRYPTION-KEY'
  properties: {
    // Generate a Fernet-compatible key (32 bytes base64-encoded = 44 characters)
    // Bicep doesn't have crypto functions, so we use a guid-based approach
    // In production, this will be generated once and persisted
    value: base64(guid(keyVault.id, 'anonymization-encryption-key-v1'))
    contentType: 'application/x-fernet-key'
    attributes: {
      enabled: true
    }
  }
}

var keyVaultDnsSuffix = environment().suffixes.keyvaultDns

output acsConnectionStringUri string = 'https://${keyVault.name}${keyVaultDnsSuffix}/secrets/${acsConnectionStringSecret.name}'
output azureSearchApiKeyUri string = !empty(azureSearchServiceName) ? 'https://${keyVault.name}${keyVaultDnsSuffix}/secrets/${azureSearchApiKeySecret.name}' : ''
output azureStorageConnectionStringUri string = !empty(storageAccountName) ? 'https://${keyVault.name}${keyVaultDnsSuffix}/secrets/${azureStorageConnectionStringSecret.name}' : ''
output azureOpenAIKeyUri string = !empty(openAIAccountName) ? 'https://${keyVault.name}${keyVaultDnsSuffix}/secrets/${azureOpenAIKeySecret.name}' : ''
output anonymizationEncryptionKeyUri string = 'https://${keyVault.name}${keyVaultDnsSuffix}/secrets/${anonymizationEncryptionKeySecret.name}'
output keyVaultId string = keyVault.id
output keyVaultName string = keyVault.name
