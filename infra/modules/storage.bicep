param location string
param environmentName string
param uniqueSuffix string
param tags object

@allowed([
  'Standard_LRS'
  'Standard_GRS'
  'Standard_RAGRS'
  'Standard_ZRS'
  'Premium_LRS'
  'Premium_ZRS'
])
param sku string = 'Standard_LRS'

// Storage account names must be between 3 and 24 characters and only lowercase letters and numbers
var storageName = toLower(replace('st${environmentName}${uniqueSuffix}', '-', ''))
var sanitizedStorageName = length(storageName) >= 3 ? take(storageName, 24) : 'stdefault${uniqueSuffix}'

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: sanitizedStorageName
  location: location
  tags: tags
  sku: {
    name: sku
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    networkAcls: {
      defaultAction: 'Allow'
    }
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

// Container for document uploads
resource documentsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'documents'
  properties: {
    publicAccess: 'None'
  }
}

// Container for indexed documents
resource indexedContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'indexed-documents'
  properties: {
    publicAccess: 'None'
  }
}

@secure()
output storageConnectionString string = 'DefaultEndpointsProtocol=https;AccountName=${storage.name};AccountKey=${storage.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'
output storageId string = storage.id
output storageName string = storage.name
output storageAccountKey string = storage.listKeys().keys[0].value
