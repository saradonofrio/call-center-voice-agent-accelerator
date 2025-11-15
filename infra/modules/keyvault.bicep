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

var keyVaultDnsSuffix = environment().suffixes.keyvaultDns

output acsConnectionStringUri string = 'https://${keyVault.name}${keyVaultDnsSuffix}/secrets/${acsConnectionStringSecret.name}'
output azureSearchApiKeyUri string = !empty(azureSearchServiceName) ? 'https://${keyVault.name}${keyVaultDnsSuffix}/secrets/${azureSearchApiKeySecret.name}' : ''
output azureStorageConnectionStringUri string = !empty(storageAccountName) ? 'https://${keyVault.name}${keyVaultDnsSuffix}/secrets/${azureStorageConnectionStringSecret.name}' : ''
output azureOpenAIKeyUri string = !empty(openAIAccountName) ? 'https://${keyVault.name}${keyVaultDnsSuffix}/secrets/${azureOpenAIKeySecret.name}' : ''
output keyVaultId string = keyVault.id
output keyVaultName string = keyVault.name
