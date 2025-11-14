param environmentName string
param uniqueSuffix string
param identityId string
param tags object
param disableLocalAuth bool = true

// Voice live api only supported on two regions now 
var location string = 'swedencentral'
var aiServicesName string = 'aiServices-${environmentName}-${uniqueSuffix}'

@allowed([
  'S0'
])
param sku string = 'S0'

resource aiServices 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: aiServicesName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identityId}': {} }
  }
  sku: {
    name: sku
  }
  kind: 'AIServices'
  tags: tags
  properties: {
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
    }
    disableLocalAuth: disableLocalAuth
    customSubDomainName: 'domain-${environmentName}-${uniqueSuffix}' 
  }
}

// AI Foundry Project as child resource
var projectName = 'aiproject-${environmentName}-${uniqueSuffix}'

resource aiProject 'Microsoft.MachineLearningServices/workspaces@2024-10-01' = {
  name: projectName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identityId}': {} }
  }
  sku: {
    name: 'Basic'
    tier: 'Basic'
  }
  kind: 'Project'
  tags: tags
  properties: {
    friendlyName: projectName
    description: 'AI Foundry Project for ${environmentName}'
    hubResourceId: aiServices.id
  }
}

@secure()
output aiServicesEndpoint string = aiServices.properties.endpoint
output aiServicesId string = aiServices.id
output aiServicesName string = aiServices.name
output aiProjectId string = aiProject.id
output aiProjectName string = aiProject.name
