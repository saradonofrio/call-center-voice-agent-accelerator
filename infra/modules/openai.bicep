param location string
param environmentName string
param uniqueSuffix string
param identityId string
param tags object
param disableLocalAuth bool = true

@allowed([
  'S0'
])
param sku string = 'S0'

var openAIName = 'aoai-${environmentName}-${uniqueSuffix}'

resource openAI 'Microsoft.CognitiveServices/accounts@2024-04-01-preview' = {
  name: openAIName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identityId}': {} }
  }
  sku: {
    name: sku
  }
  kind: 'OpenAI'
  tags: tags
  properties: {
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
    }
    disableLocalAuth: disableLocalAuth
    customSubDomainName: 'aoai-${environmentName}-${uniqueSuffix}'
  }
}

// Deploy text-embedding-ada-002 model
resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-04-01-preview' = {
  parent: openAI
  name: 'text-embedding-ada-002'
  sku: {
    name: 'Standard'
    capacity: 120
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'text-embedding-ada-002'
      version: '2'
    }
  }
}

@secure()
output openAIEndpoint string = openAI.properties.endpoint
output openAIId string = openAI.id
output openAIName string = openAI.name
output embeddingDeploymentName string = embeddingDeployment.name
