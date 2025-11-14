param environmentName string
param uniqueSuffix string
param acsResourceId string
param containerAppFqdn string
param tags object

var systemTopicName = 'acs-system-topic-${environmentName}-${uniqueSuffix}'
var eventSubscriptionName = 'acs-incoming-call-subscription'

resource systemTopic 'Microsoft.EventGrid/systemTopics@2024-06-01-preview' = {
  name: systemTopicName
  location: 'global'
  tags: tags
  properties: {
    source: acsResourceId
    topicType: 'Microsoft.Communication.CommunicationServices'
  }
}

resource eventSubscription 'Microsoft.EventGrid/systemTopics/eventSubscriptions@2024-06-01-preview' = {
  parent: systemTopic
  name: eventSubscriptionName
  properties: {
    destination: {
      endpointType: 'WebHook'
      properties: {
        endpointUrl: 'https://${containerAppFqdn}/acs/incomingcall'
        maxEventsPerBatch: 1
        preferredBatchSizeInKilobytes: 64
      }
    }
    filter: {
      includedEventTypes: [
        'Microsoft.Communication.IncomingCall'
      ]
    }
    eventDeliverySchema: 'EventGridSchema'
    retryPolicy: {
      maxDeliveryAttempts: 30
      eventTimeToLiveInMinutes: 1440
    }
  }
}

output systemTopicId string = systemTopic.id
output systemTopicName string = systemTopic.name
output eventSubscriptionId string = eventSubscription.id
