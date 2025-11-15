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

// Azure Search parameters (optional - if not provided, will use deployed service)
@description('Azure Search endpoint URL (optional - uses deployed service if empty)')
param azureSearchEndpoint string = ''
@description('Azure Search index name (optional - uses deployed service if empty)')
param azureSearchIndex string = 'pharmacy-knowledge-base'
@description('Azure Search semantic configuration name')
param azureSearchSemanticConfig string = 'default'
@description('Azure Search top N results')
param azureSearchTopN string = '5'
@description('Azure Search strictness level')
param azureSearchStrictness string = '3'

// Azure OpenAI parameters (optional - if not provided, will use deployed service)
@description('Azure OpenAI endpoint URL (optional - uses deployed service if empty)')
param azureOpenAIEndpoint string = ''
@description('Azure OpenAI embedding deployment name (optional - uses deployed service if empty)')
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

// Deploy Azure Search Service
module search 'modules/azuresearch.bicep' = {
  name: 'search-deployment'
  scope: rg
  params: {
    location: location
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
    tags: tags
    identityPrincipalId: appIdentity.outputs.principalId
  }
  dependsOn: [ appIdentity ]
}

// Deploy Storage Account
module storage 'modules/storageaccount.bicep' = {
  name: 'storage-deployment'
  scope: rg
  params: {
    location: location
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
    tags: tags
  }
}

// Deploy Azure OpenAI
module openai 'modules/openai.bicep' = {
  name: 'openai-deployment'
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
    azureSearchServiceName: search.outputs.searchServiceName
    storageAccountName: storage.outputs.storageAccountName
    openAIAccountName: openai.outputs.openAIName
  }
  dependsOn: [ acs, search, storage, openai ]
}

// Add role assignments 
module RoleAssignments 'modules/roleassignments.bicep' = {
  scope: rg
  name: 'role-assignments'
  params: {
    identityPrincipalId: appIdentity.outputs.principalId
    aiServicesId: aiServices.outputs.aiServicesId
    keyVaultName: sanitizedKeyVaultName
  }
  dependsOn: [ keyvault, appIdentity ] 
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
    // Azure Search parameters - use deployed service or external if provided
    azureSearchEndpoint: !empty(azureSearchEndpoint) ? azureSearchEndpoint : search.outputs.searchServiceEndpoint
    azureSearchIndex: !empty(azureSearchIndex) ? azureSearchIndex : search.outputs.indexName
    azureSearchApiKeySecretUri: keyvault.outputs.azureSearchApiKeyUri
    azureSearchSemanticConfig: azureSearchSemanticConfig
    azureSearchTopN: azureSearchTopN
    azureSearchStrictness: azureSearchStrictness
    // Azure Storage parameters - use deployed service
    azureStorageConnectionStringSecretUri: keyvault.outputs.azureStorageConnectionStringUri
    // Azure OpenAI parameters - use deployed service or external if provided
    azureOpenAIEndpoint: !empty(azureOpenAIEndpoint) ? azureOpenAIEndpoint : openai.outputs.openAIEndpoint
    azureOpenAIKeySecretUri: keyvault.outputs.azureOpenAIKeyUri
    azureOpenAIEmbeddingDeployment: !empty(azureOpenAIEmbeddingDeployment) ? azureOpenAIEmbeddingDeployment : openai.outputs.embeddingDeploymentName
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


// OUTPUTS will be saved in azd env for later use
output AZURE_LOCATION string = location
output AZURE_TENANT_ID string = tenant().tenantId
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_USER_ASSIGNED_IDENTITY_ID string = appIdentity.outputs.identityId
output AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID string = appIdentity.outputs.clientId

output AZURE_CONTAINER_REGISTRY_ENDPOINT string = registry.outputs.loginServer
output SERVICE_API_ENDPOINTS array = ['${containerapp.outputs.containerAppFqdn}/acs/incomingcall']
output AZURE_VOICE_LIVE_MODEL string = modelName

// Azure Search outputs
output AZURE_SEARCH_ENDPOINT string = search.outputs.searchServiceEndpoint
output AZURE_SEARCH_INDEX string = search.outputs.indexName

// Azure Storage outputs
output AZURE_STORAGE_ACCOUNT_NAME string = storage.outputs.storageAccountName
output AZURE_STORAGE_BLOB_ENDPOINT string = storage.outputs.blobEndpoint

// Azure OpenAI outputs
output AZURE_OPENAI_ENDPOINT string = openai.outputs.openAIEndpoint
output AZURE_OPENAI_EMBEDDING_DEPLOYMENT string = openai.outputs.embeddingDeploymentName

// Key Vault output
output AZURE_KEY_VAULT_NAME string = keyvault.outputs.keyVaultName
