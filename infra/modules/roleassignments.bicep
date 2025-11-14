param identityPrincipalId string
param aiServicesId string
param keyVaultName string
param storageId string = ''
param searchId string = ''
param openAIId string = ''

resource aiServicesResource 'Microsoft.CognitiveServices/accounts@2023-05-01' existing = {
  name: last(split(aiServicesId, '/'))
}

resource aiServicesRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiServicesId, identityPrincipalId, 'Cognitive Services User')
  scope: aiServicesResource
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
    principalId: identityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource aiAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiServicesId, identityPrincipalId, 'ai-reader')
  scope: aiServicesResource
  properties: {
    principalId: identityPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'acdd72a7-3385-48ef-bd42-f606fba81ae7')
    principalType: 'ServicePrincipal'
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-02-01' existing = {
  name: keyVaultName
}

resource keyVaultRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, identityPrincipalId, 'Key Vault Secrets User')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7')
    principalId: identityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Storage Blob Data Contributor role (if storage is created)
resource storageResource 'Microsoft.Storage/storageAccounts@2023-05-01' existing = if (!empty(storageId)) {
  name: last(split(storageId, '/'))
}

resource storageBlobDataContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(storageId)) {
  name: guid(storageId, identityPrincipalId, 'Storage Blob Data Contributor')
  scope: storageResource
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
    principalId: identityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Search Index Data Contributor role (if search is created)
resource searchResource 'Microsoft.Search/searchServices@2024-06-01-preview' existing = if (!empty(searchId)) {
  name: last(split(searchId, '/'))
}

resource searchIndexDataContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(searchId)) {
  name: guid(searchId, identityPrincipalId, 'Search Index Data Contributor')
  scope: searchResource
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '8ebe5a00-799e-43f5-93ac-243d3dce84a7')
    principalId: identityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Cognitive Services OpenAI User role (if OpenAI is created)
resource openAIResource 'Microsoft.CognitiveServices/accounts@2024-04-01-preview' existing = if (!empty(openAIId)) {
  name: last(split(openAIId, '/'))
}

resource openAIUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(openAIId)) {
  name: guid(openAIId, identityPrincipalId, 'Cognitive Services OpenAI User')
  scope: openAIResource
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
    principalId: identityPrincipalId
    principalType: 'ServicePrincipal'
  }
}
