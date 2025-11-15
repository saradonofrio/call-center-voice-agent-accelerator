param location string
param environmentName string
param uniqueSuffix string
param tags object = {}

var openAIName = 'aoai-${environmentName}-${uniqueSuffix}'

resource openAI 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: openAIName
  location: location
  tags: tags
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: openAIName
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
    }
  }
}

// Deploy text-embedding-ada-002 model
resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
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

output openAIName string = openAI.name
output openAIEndpoint string = openAI.properties.endpoint
output openAIId string = openAI.id
output embeddingDeploymentName string = embeddingDeployment.name
