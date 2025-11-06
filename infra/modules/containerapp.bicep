param location string
param environmentName string
param uniqueSuffix string
param tags object
param exists bool
param identityId string
param identityClientId string
param containerRegistryName string
param aiServicesEndpoint string
param modelDeploymentName string
param acsConnectionStringSecretUri string
param logAnalyticsWorkspaceName string
@description('The name of the container image')
param imageName string = ''
@description('Azure AD Tenant ID for authentication')
param azureAdTenantId string = ''
@description('Azure AD Client ID (API app) for authentication')
param azureAdClientId string = ''

// Azure Search parameters
@description('Azure Search endpoint URL')
param azureSearchEndpoint string = ''
@description('Azure Search index name')
param azureSearchIndex string = ''
@description('Azure Search API key (Key Vault secret URI)')
param azureSearchApiKeySecretUri string = ''
@description('Azure Search semantic configuration name')
param azureSearchSemanticConfig string = ''
@description('Azure Search top N results')
param azureSearchTopN string = '5'
@description('Azure Search strictness level')
param azureSearchStrictness string = '3'

// Azure Storage parameters
@description('Azure Storage connection string (Key Vault secret URI)')
param azureStorageConnectionStringSecretUri string = ''

// Azure OpenAI parameters
@description('Azure OpenAI endpoint URL')
param azureOpenAIEndpoint string = ''
@description('Azure OpenAI API key (Key Vault secret URI)')
param azureOpenAIKeySecretUri string = ''
@description('Azure OpenAI embedding deployment name')
param azureOpenAIEmbeddingDeployment string = ''

// Security parameters
@description('Allowed CORS origins (comma-separated or *)')
param allowedOrigins string = '*'

// Helper to sanitize environmentName for valid container app name
var sanitizedEnvName = toLower(replace(replace(replace(replace(environmentName, ' ', '-'), '--', '-'), '[^a-zA-Z0-9-]', ''), '_', '-'))
var containerAppName = take('ca-${sanitizedEnvName}-${uniqueSuffix}', 32)
var containerEnvName = take('cae-${sanitizedEnvName}-${uniqueSuffix}', 32)

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' existing = { name: logAnalyticsWorkspaceName }


module fetchLatestImage './fetch-container-image.bicep' = {
  name: '${containerAppName}-fetch-image'
  params: {
    exists: exists
    name: containerAppName
  }
}

resource containerAppEnv 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: containerEnvName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsWorkspace.properties.customerId
        sharedKey: logAnalyticsWorkspace.listKeys().primarySharedKey
      }
    }
  }
}

resource containerApp 'Microsoft.App/containerApps@2024-10-02-preview' = {
  name: containerAppName
  location: location
  tags: union(tags, { 'azd-service-name': 'app' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identityId}': {} }
  }
  properties: {
    managedEnvironmentId: containerAppEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      registries: [
        {
          server: '${containerRegistryName}.azurecr.io'
          identity: identityId
        }
      ]
      secrets: [
        {
          name: 'acs-connection-string'
          keyVaultUrl: acsConnectionStringSecretUri
          identity: identityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'main'
          image: !empty(imageName) ? imageName : 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
          env: [
            {
              name: 'AZURE_VOICE_LIVE_ENDPOINT'
              value: aiServicesEndpoint
            }
            {
              name: 'AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID'
              value: identityClientId
            }
            {
              name: 'VOICE_LIVE_MODEL'
              value: modelDeploymentName
            }
            {
              name: 'ACS_CONNECTION_STRING'
              secretRef: 'acs-connection-string'
            }
            {
              name: 'AZURE_AD_TENANT_ID'
              value: azureAdTenantId
            }
            {
              name: 'AZURE_AD_CLIENT_ID'
              value: azureAdClientId
            }
            {
              name: 'AZURE_SEARCH_ENDPOINT'
              value: azureSearchEndpoint
            }
            {
              name: 'AZURE_SEARCH_INDEX'
              value: azureSearchIndex
            }
            {
              name: 'AZURE_SEARCH_SEMANTIC_CONFIG'
              value: azureSearchSemanticConfig
            }
            {
              name: 'AZURE_SEARCH_TOP_N'
              value: azureSearchTopN
            }
            {
              name: 'AZURE_SEARCH_STRICTNESS'
              value: azureSearchStrictness
            }
            {
              name: 'AZURE_OPENAI_ENDPOINT'
              value: azureOpenAIEndpoint
            }
            {
              name: 'AZURE_OPENAI_EMBEDDING_DEPLOYMENT'
              value: azureOpenAIEmbeddingDeployment
            }
            {
              name: 'ALLOWED_ORIGINS'
              value: allowedOrigins
            }
            {
              name: 'DEBUG_MODE'
              value: 'true'
            }
          ]
          resources: {
            cpu: json('2.0')
            memory: '4.0Gi'
          }
        }
      ]
      // TODO add memory/cpu scaling
      scale: {
        minReplicas: 1
        maxReplicas: 10
        rules: [
          {
            name: 'http-scaler'
            http: {
              metadata: {
                concurrentRequests: '100'
              }
            }
          }
        ]
      }
    }
  }
}

output containerAppFqdn string = containerApp.properties.configuration.ingress.fqdn
output containerAppId string = containerApp.id
