param location string
param environmentName string
param uniqueSuffix string
param tags object
param disableLocalAuth bool = false

@allowed([
  'free'
  'basic'
  'standard'
  'standard2'
  'standard3'
  'storage_optimized_l1'
  'storage_optimized_l2'
])
param sku string = 'standard'

var searchName = 'search-${environmentName}-${uniqueSuffix}'

resource search 'Microsoft.Search/searchServices@2024-06-01-preview' = {
  name: searchName
  location: location
  tags: tags
  sku: {
    name: sku
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    publicNetworkAccess: 'enabled'
    networkRuleSet: {
      ipRules: []
    }
    disableLocalAuth: disableLocalAuth
    authOptions: disableLocalAuth ? {
      aadOrApiKey: {
        aadAuthFailureMode: 'http401WithBearerChallenge'
      }
    } : null
  }
}

@secure()
output searchEndpoint string = 'https://${search.name}.search.windows.net'
output searchId string = search.id
output searchName string = search.name
output searchApiKey string = search.listAdminKeys().primaryKey
