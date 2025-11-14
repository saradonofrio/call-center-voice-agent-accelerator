targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the the environment which is used to generate a short unique hash used in all resources.')
param environmentName string

@minLength(1)
@description('Primary location for all resources (filtered on available regions for Azure Open AI Service).')
@allowed([
  'eastus2'
  'swedencentral'
])
param location string

var abbrs = loadJsonContent('./abbreviations.json')
param useApplicationInsights bool = true
param useContainerRegistry bool = true
param appExists bool
@description('The OpenAI model name')
param modelName string = ' gpt-4o-mini'
@description('Id of the user or app to assign application roles. If ommited will be generated from the user assigned identity.')
param principalId string = ''
@description('Azure AD Tenant ID for authentication (optional)')
param azureAdTenantId string = ''
@description('Azure AD Client ID (API app) for authentication (optional)')
param azureAdClientId string = ''

// Azure Search parameters
@description('Azure Search endpoint URL')
param azureSearchEndpoint string = ''
@description('Azure Search index name')
param azureSearchIndex string = ''
@secure()
@description('Azure Search API key (secret)')
param azureSearchApiKey string = ''
@description('Azure Search semantic configuration name')
param azureSearchSemanticConfig string = ''
@description('Azure Search top N results')
param azureSearchTopN string = '5'
@description('Azure Search strictness level')
param azureSearchStrictness string = '3'

// Azure Storage parameters
@secure()
@description('Azure Storage connection string (secret)')
param azureStorageConnectionString string = ''

// Azure OpenAI parameters
@description('Azure OpenAI endpoint URL')
param azureOpenAIEndpoint string = ''
@secure()
@description('Azure OpenAI API key (secret)')
param azureOpenAIKey string = ''
@description('Azure OpenAI embedding deployment name')
param azureOpenAIEmbeddingDeployment string = ''

// Security parameters
@description('Allowed CORS origins (comma-separated or * for all)')
param allowedOrigins string = '*'
@description('Rate limit: max document uploads allowed')
param rateLimitUploadsCount int = 10
@description('Rate limit: uploads time window in seconds (3600 = 1 hour)')
param rateLimitUploadsWindow int = 3600
@description('Rate limit: max API calls allowed')
param rateLimitApiCount int = 100
@description('Rate limit: API time window in seconds (3600 = 1 hour)')
param rateLimitApiWindow int = 3600
@description('Rate limit: max admin operations allowed')
param rateLimitAdminCount int = 50
@description('Rate limit: admin time window in seconds (3600 = 1 hour)')
param rateLimitAdminWindow int = 3600

var uniqueSuffix = substring(uniqueString(subscription().id, environmentName), 0, 5)
var tags = {'azd-env-name': environmentName }
var rgName = 'rg-${environmentName}-${uniqueSuffix}'

resource rg 'Microsoft.Resources/resourceGroups@2024-11-01' = {
  name: rgName
  location: location
  tags: tags
}

// [ User Assigned Identity for App to avoid circular dependency ]
module appIdentity './modules/identity.bicep' = {
  name: 'uami'
  scope: rg
  params: {
    location: location
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
  }
}

var sanitizedEnvName = toLower(replace(replace(replace(replace(environmentName, ' ', '-'), '--', '-'), '[^a-zA-Z0-9-]', ''), '_', '-'))
var logAnalyticsName = take('log-${sanitizedEnvName}-${uniqueSuffix}', 63)
var appInsightsName = take('insights-${sanitizedEnvName}-${uniqueSuffix}', 63)
module monitoring 'modules/monitoring/monitor.bicep' = {
  name: 'monitor'
  scope: rg
  params: {
    logAnalyticsName: logAnalyticsName
    appInsightsName: appInsightsName
    tags: tags
  }
}

module registry 'modules/containerregistry.bicep' = {
  name: 'registry'
  scope: rg
  params: {
    location: location
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
    identityName: appIdentity.outputs.name
    tags: tags
  }
  dependsOn: [ appIdentity ]
}


module aiServices 'modules/aiservices.bicep' = {
  name: 'ai-foundry-deployment'
  scope: rg
  params: {
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
    identityId: appIdentity.outputs.identityId
    tags: tags
  }
  dependsOn: [ appIdentity ]
}

module acs 'modules/acs.bicep' = {
  name: 'acs-deployment'
  scope: rg
  params: {
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
    tags: tags
  }
}

// Conditionally create Azure OpenAI if endpoint not provided
module openai 'modules/openai.bicep' = if (empty(azureOpenAIEndpoint)) {
  name: 'openai-deployment'
  scope: rg
  params: {
    location: location
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
    identityId: appIdentity.outputs.identityId
    tags: tags
  }
  dependsOn: [ appIdentity ]
}

// Conditionally create Storage Account if connection string not provided
module storage 'modules/storage.bicep' = if (empty(azureStorageConnectionString)) {
  name: 'storage-deployment'
  scope: rg
  params: {
    location: location
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
    tags: tags
  }
}

// Conditionally create Azure Cognitive Search if endpoint not provided
module search 'modules/search.bicep' = if (empty(azureSearchEndpoint)) {
  name: 'search-deployment'
  scope: rg
  params: {
    location: location
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
    tags: tags
  }
}

var keyVaultName = toLower(replace('kv-${environmentName}-${uniqueSuffix}', '_', '-'))
var sanitizedKeyVaultName = take(toLower(replace(replace(replace(replace(keyVaultName, '--', '-'), '_', '-'), '[^a-zA-Z0-9-]', ''), '-$', '')), 24)
module keyvault 'modules/keyvault.bicep' = {
  name: 'keyvault-deployment'
  scope: rg
  params: {
    location: location
    keyVaultName: sanitizedKeyVaultName
    tags: tags
    acsConnectionString: acs.outputs.acsConnectionString
    azureSearchApiKey: !empty(azureSearchApiKey) ? azureSearchApiKey : (empty(azureSearchEndpoint) ? search.outputs.searchApiKey : '')
    azureStorageConnectionString: !empty(azureStorageConnectionString) ? azureStorageConnectionString : (empty(azureStorageConnectionString) ? storage.outputs.storageConnectionString : '')
    azureOpenAIKey: azureOpenAIKey
  }
  dependsOn: [ appIdentity, acs, openai, storage, search ]
}

// Add role assignments 
module RoleAssignments 'modules/roleassignments.bicep' = {
  scope: rg
  name: 'role-assignments'
  params: {
    identityPrincipalId: appIdentity.outputs.principalId
    aiServicesId: aiServices.outputs.aiServicesId
    keyVaultName: sanitizedKeyVaultName
    storageId: empty(azureStorageConnectionString) ? storage.outputs.storageId : ''
    searchId: empty(azureSearchEndpoint) ? search.outputs.searchId : ''
    openAIId: empty(azureOpenAIEndpoint) ? openai.outputs.openAIId : ''
  }
  dependsOn: [ keyvault, appIdentity, storage, search, openai ] 
}

module containerapp 'modules/containerapp.bicep' = {
  name: 'containerapp-deployment'
  scope: rg
  params: {
    location: location
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
    tags: tags
    exists: appExists
    identityId: appIdentity.outputs.identityId
    identityClientId: appIdentity.outputs.clientId
    containerRegistryName: registry.outputs.name
    aiServicesEndpoint: aiServices.outputs.aiServicesEndpoint
    modelDeploymentName: modelName
    acsConnectionStringSecretUri: keyvault.outputs.acsConnectionStringUri
    logAnalyticsWorkspaceName: logAnalyticsName
    imageName: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
    azureAdTenantId: azureAdTenantId
    azureAdClientId: azureAdClientId
    // Azure Search parameters
    azureSearchEndpoint: !empty(azureSearchEndpoint) ? azureSearchEndpoint : (empty(azureSearchEndpoint) ? search.outputs.searchEndpoint : '')
    azureSearchIndex: azureSearchIndex
    azureSearchApiKeySecretUri: keyvault.outputs.azureSearchApiKeyUri
    azureSearchSemanticConfig: azureSearchSemanticConfig
    azureSearchTopN: azureSearchTopN
    azureSearchStrictness: azureSearchStrictness
    // Azure Storage parameters
    azureStorageConnectionStringSecretUri: keyvault.outputs.azureStorageConnectionStringUri
    // Azure OpenAI parameters
    azureOpenAIEndpoint: !empty(azureOpenAIEndpoint) ? azureOpenAIEndpoint : (empty(azureOpenAIEndpoint) ? openai.outputs.openAIEndpoint : '')
    azureOpenAIKeySecretUri: keyvault.outputs.azureOpenAIKeyUri
    azureOpenAIEmbeddingDeployment: !empty(azureOpenAIEmbeddingDeployment) ? azureOpenAIEmbeddingDeployment : (empty(azureOpenAIEndpoint) ? openai.outputs.embeddingDeploymentName : '')
    // Security parameters
    allowedOrigins: allowedOrigins
    rateLimitUploadsCount: rateLimitUploadsCount
    rateLimitUploadsWindow: rateLimitUploadsWindow
    rateLimitApiCount: rateLimitApiCount
    rateLimitApiWindow: rateLimitApiWindow
    rateLimitAdminCount: rateLimitAdminCount
    rateLimitAdminWindow: rateLimitAdminWindow
  }
  dependsOn: [keyvault, RoleAssignments]
}

// Event Grid System Topic for ACS IncomingCall events
module eventgrid 'modules/eventgrid.bicep' = {
  name: 'eventgrid-deployment'
  scope: rg
  params: {
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
    acsResourceId: acs.outputs.acsResourceId
    containerAppFqdn: containerapp.outputs.containerAppFqdn
    tags: tags
  }
  dependsOn: [ acs, containerapp ]
}

// OUTPUTS will be saved in azd env for later use
output AZURE_LOCATION string = location
output AZURE_TENANT_ID string = tenant().tenantId
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_USER_ASSIGNED_IDENTITY_ID string = appIdentity.outputs.identityId
output AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID string = appIdentity.outputs.clientId

output AZURE_CONTAINER_REGISTRY_ENDPOINT string = registry.outputs.loginServer
output SERVICE_API_ENDPOINTS array = ['${containerapp.outputs.containerAppFqdn}/acs/incomingcall']
output AZURE_VOICE_LIVE_ENDPOINT string = aiServices.outputs.aiServicesEndpoint
output AZURE_VOICE_LIVE_MODEL string = modelName

// Outputs for newly created resources
output AZURE_OPENAI_ENDPOINT string = !empty(azureOpenAIEndpoint) ? azureOpenAIEndpoint : (empty(azureOpenAIEndpoint) ? openai.outputs.openAIEndpoint : '')
output AZURE_OPENAI_EMBEDDING_DEPLOYMENT string = !empty(azureOpenAIEmbeddingDeployment) ? azureOpenAIEmbeddingDeployment : (empty(azureOpenAIEndpoint) ? openai.outputs.embeddingDeploymentName : '')
output AZURE_SEARCH_ENDPOINT string = !empty(azureSearchEndpoint) ? azureSearchEndpoint : (empty(azureSearchEndpoint) ? search.outputs.searchEndpoint : '')
output AZURE_STORAGE_ACCOUNT_NAME string = empty(azureStorageConnectionString) ? storage.outputs.storageName : ''
output AZURE_EVENT_GRID_SYSTEM_TOPIC string = eventgrid.outputs.systemTopicName
