param location string
param keyVaultName string
param tags object
@secure()
param acsConnectionString string
@secure()
param azureSearchApiKey string = ''
@secure()
param azureStorageConnectionString string = ''
@secure()
param azureOpenAIKey string = ''

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

resource azureSearchApiKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(azureSearchApiKey)) {
  parent: keyVault
  name: 'AZURE-SEARCH-API-KEY'
  properties: {
    value: azureSearchApiKey
  }
}

resource azureStorageConnectionStringSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(azureStorageConnectionString)) {
  parent: keyVault
  name: 'AZURE-STORAGE-CONNECTION-STRING'
  properties: {
    value: azureStorageConnectionString
  }
}

resource azureOpenAIKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(azureOpenAIKey)) {
  parent: keyVault
  name: 'AZURE-OPENAI-KEY'
  properties: {
    value: azureOpenAIKey
  }
}

var keyVaultDnsSuffix = environment().suffixes.keyvaultDns

output acsConnectionStringUri string = 'https://${keyVault.name}${keyVaultDnsSuffix}/secrets/${acsConnectionStringSecret.name}'
output azureSearchApiKeyUri string = !empty(azureSearchApiKey) ? 'https://${keyVault.name}${keyVaultDnsSuffix}/secrets/${azureSearchApiKeySecret.name}' : ''
output azureStorageConnectionStringUri string = !empty(azureStorageConnectionString) ? 'https://${keyVault.name}${keyVaultDnsSuffix}/secrets/${azureStorageConnectionStringSecret.name}' : ''
output azureOpenAIKeyUri string = !empty(azureOpenAIKey) ? 'https://${keyVault.name}${keyVaultDnsSuffix}/secrets/${azureOpenAIKeySecret.name}' : ''
output keyVaultId string = keyVault.id
output keyVaultName string = keyVault.name
