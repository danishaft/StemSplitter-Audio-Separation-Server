targetScope = 'subscription'

@minLength(2)
@maxLength(24)
param name string = 'stemsplitter'

param location string = 'eastus2'
param imageTag string = 'latest'
param deploymentVersion string = 'local'
param deployApps bool = true
param apiMinReplicas int = 1
param apiMaxReplicas int = 10
param workerMinReplicas int = 1
param workerMaxReplicas int = 5

@secure()
param databaseUrl string

@secure()
param redisUrl string

param redisScaleAddress string

@secure()
param redisScaleUsername string

@secure()
param redisScalePassword string

param redisScaleDatabaseIndex string = '0'

@secure()
param objectStorageAccessKeyId string

@secure()
param objectStorageSecretAccessKey string

@secure()
param gpuWorkerApiKey string

@secure()
param edgeVerifySecret string

@secure()
param metricsBearerToken string

@secure()
param sentryDsn string = ''

param authJwksUrl string
param authIssuer string
param authAudience string
param objectStorageBucket string
param objectStorageEndpointUrl string
param objectStorageRegion string
param gpuWorkerUrl string
param publicWebOrigin string

var token = toLower(uniqueString(subscription().id, name, location))
var resourcePrefix = '${name}-${take(token, 8)}'
var tags = {
  application: name
  managedBy: 'bicep'
}

resource resourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: '${resourcePrefix}-rg'
  location: location
  tags: tags
}

module platform 'platform.bicep' = {
  name: '${resourcePrefix}-platform'
  scope: resourceGroup
  params: {
    name: name
    location: location
    imageTag: imageTag
    deploymentVersion: deploymentVersion
    deployApps: deployApps
    apiMinReplicas: apiMinReplicas
    apiMaxReplicas: apiMaxReplicas
    workerMinReplicas: workerMinReplicas
    workerMaxReplicas: workerMaxReplicas
    databaseUrl: databaseUrl
    redisUrl: redisUrl
    redisScaleAddress: redisScaleAddress
    redisScaleUsername: redisScaleUsername
    redisScalePassword: redisScalePassword
    redisScaleDatabaseIndex: redisScaleDatabaseIndex
    objectStorageAccessKeyId: objectStorageAccessKeyId
    objectStorageSecretAccessKey: objectStorageSecretAccessKey
    gpuWorkerApiKey: gpuWorkerApiKey
    edgeVerifySecret: edgeVerifySecret
    metricsBearerToken: metricsBearerToken
    sentryDsn: sentryDsn
    authJwksUrl: authJwksUrl
    authIssuer: authIssuer
    authAudience: authAudience
    objectStorageBucket: objectStorageBucket
    objectStorageEndpointUrl: objectStorageEndpointUrl
    objectStorageRegion: objectStorageRegion
    gpuWorkerUrl: gpuWorkerUrl
    publicWebOrigin: publicWebOrigin
  }
}

output apiOrigin string = platform.outputs.apiOrigin
output containerRegistry string = platform.outputs.containerRegistry
output migrationJobName string = platform.outputs.migrationJobName
output resourceGroupName string = resourceGroup.name
output applicationInsightsConnectionString string = platform.outputs.applicationInsightsConnectionString
