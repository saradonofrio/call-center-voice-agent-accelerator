param location string
param environmentName string
param uniqueSuffix string
param tags object = {}

// Storage account name must be between 3-24 chars, lowercase alphanumeric
var storageAccountName = toLower(replace(take('st${environmentName}${uniqueSuffix}', 24), '-', ''))

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: true
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    isHnsEnabled: false  // Explicitly disable Hierarchical Namespace (DataLake Gen2)
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }
}

// Create blob service with enhanced backup protection
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
  properties: {
    // Soft delete for blobs - recover deleted blobs within 30 days
    deleteRetentionPolicy: {
      enabled: true
      days: 30
    }
    // Soft delete for containers - recover deleted containers within 30 days
    containerDeleteRetentionPolicy: {
      enabled: true
      days: 30
    }
    // Versioning - keep history of blob changes
    isVersioningEnabled: true
    // Point-in-time restore capability
    restorePolicy: {
      enabled: true
      days: 29
    }
  }
}

// Create testlogs container for test results
resource testLogsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'testlogs'
  properties: {
    publicAccess: 'None'
  }
}

output storageAccountName string = storageAccount.name
output storageAccountId string = storageAccount.id
output blobEndpoint string = storageAccount.properties.primaryEndpoints.blob
