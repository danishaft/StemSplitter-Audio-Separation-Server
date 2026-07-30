targetScope = 'resourceGroup'

@minLength(2)
@maxLength(24)
param name string = 'stemsplitter'

param location string = 'eastus2'
param imageTag string = 'latest'
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

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${resourcePrefix}-logs'
  location: location
  tags: tags
  properties: {
    retentionInDays: 30
    sku: {
      name: 'PerGB2018'
    }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${resourcePrefix}-insights'
  location: location
  kind: 'web'
  tags: tags
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: replace(resourcePrefix, '-', '')
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${resourcePrefix}-apps'
  location: location
  tags: tags
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: registry
  name: guid(registry.id, identity.id, 'acr-pull')
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d'
    )
  }
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${resourcePrefix}-env'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

var image = '${registry.properties.loginServer}/stemsplitter:${imageTag}'
var workloadIdentity = {
  type: 'UserAssigned'
  userAssignedIdentities: {
    '${identity.id}': {}
  }
}
var registryConfiguration = [
  {
    server: registry.properties.loginServer
    identity: identity.id
  }
]
var requiredSecretValues = [
  {
    name: 'database-url'
    value: databaseUrl
  }
  {
    name: 'redis-url'
    value: redisUrl
  }
  {
    name: 'redis-scale-username'
    value: redisScaleUsername
  }
  {
    name: 'redis-scale-password'
    value: redisScalePassword
  }
  {
    name: 'storage-access-key'
    value: objectStorageAccessKeyId
  }
  {
    name: 'storage-secret-key'
    value: objectStorageSecretAccessKey
  }
  {
    name: 'gpu-worker-api-key'
    value: gpuWorkerApiKey
  }
  {
    name: 'edge-verify-secret'
    value: edgeVerifySecret
  }
  {
    name: 'metrics-token'
    value: metricsBearerToken
  }
]
var secretValues = empty(sentryDsn)
  ? requiredSecretValues
  : concat(requiredSecretValues, [{ name: 'sentry-dsn', value: sentryDsn }])
var requiredEnvironment = [
  { name: 'APP_ENV', value: 'production' }
  { name: 'PUBLIC_API_URL', value: '${publicWebOrigin}/api' }
  { name: 'TRUSTED_HOSTS', value: '*.azurecontainerapps.io' }
  { name: 'CORS_ALLOWED_ORIGINS', value: publicWebOrigin }
  { name: 'EDGE_MODE', value: 'cloudflare' }
  { name: 'EDGE_VERIFY_SECRET', secretRef: 'edge-verify-secret' }
  { name: 'RATE_LIMIT_ENABLED', value: '1' }
  { name: 'METRICS_BEARER_TOKEN', secretRef: 'metrics-token' }
  { name: 'DATABASE_URL', secretRef: 'database-url' }
  { name: 'DATABASE_POOL_MIN_SIZE', value: '1' }
  { name: 'DATABASE_POOL_MAX_SIZE', value: '3' }
  { name: 'DATABASE_POOL_TIMEOUT', value: '10' }
  { name: 'JOB_STORE_BACKEND', value: 'postgres' }
  { name: 'REDIS_URL', secretRef: 'redis-url' }
  { name: 'JOB_DISPATCH_BACKEND', value: 'rq' }
  { name: 'OBJECT_STORAGE_BACKEND', value: 's3' }
  { name: 'OBJECT_STORAGE_BUCKET', value: objectStorageBucket }
  { name: 'OBJECT_STORAGE_PREFIX', value: 'stemsplitter' }
  { name: 'OBJECT_STORAGE_ENDPOINT_URL', value: objectStorageEndpointUrl }
  { name: 'OBJECT_STORAGE_REGION', value: objectStorageRegion }
  { name: 'OBJECT_STORAGE_ACCESS_KEY_ID', secretRef: 'storage-access-key' }
  { name: 'OBJECT_STORAGE_SECRET_ACCESS_KEY', secretRef: 'storage-secret-key' }
  { name: 'AUTH_MODE', value: 'jwt' }
  { name: 'AUTH_JWKS_URL', value: authJwksUrl }
  { name: 'AUTH_ISSUER', value: authIssuer }
  { name: 'AUTH_AUDIENCE', value: authAudience }
  { name: 'AUTH_ALGORITHMS', value: 'ES256' }
  { name: 'GPU_WORKER_URL', value: gpuWorkerUrl }
  { name: 'GPU_WORKER_API_KEY', secretRef: 'gpu-worker-api-key' }
  { name: 'GPU_WORKER_MAX_EXECUTION_SECONDS', value: '300' }
  { name: 'DEFAULT_PROFILE', value: 'quality_gpu_experimental' }
  { name: 'ALLOW_EVALUATION_PROFILES', value: '1' }
  { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
  { name: 'OTEL_SERVICE_NAME', value: 'stemsplitter' }
  { name: 'ALLOW_MULTIPART_UPLOADS', value: '0' }
]
var commonEnvironment = empty(sentryDsn)
  ? requiredEnvironment
  : concat(requiredEnvironment, [{ name: 'SENTRY_DSN', secretRef: 'sentry-dsn' }])

resource api 'Microsoft.App/containerApps@2024-03-01' = if (deployApps) {
  name: '${resourcePrefix}-api'
  location: location
  tags: tags
  identity: workloadIdentity
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 5000
        transport: 'auto'
        allowInsecure: false
      }
      registries: registryConfiguration
      secrets: secretValues
    }
    template: {
      containers: [
        {
          name: 'api'
          image: image
          command: ['python', '-m', 'scripts.run_api']
          env: commonEnvironment
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/health/live', port: 5000 }
              initialDelaySeconds: 20
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: { path: '/health/ready', port: 5000 }
              initialDelaySeconds: 10
              periodSeconds: 15
            }
          ]
        }
      ]
      scale: {
        minReplicas: apiMinReplicas
        maxReplicas: apiMaxReplicas
        rules: [
          {
            name: 'http'
            http: {
              metadata: {
                concurrentRequests: '50'
              }
            }
          }
        ]
      }
    }
  }
  dependsOn: [acrPull]
}

resource queueWorker 'Microsoft.App/containerApps@2024-03-01' = if (deployApps) {
  name: '${resourcePrefix}-queue'
  location: location
  tags: tags
  identity: workloadIdentity
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      activeRevisionsMode: 'Single'
      registries: registryConfiguration
      secrets: secretValues
    }
    template: {
      containers: [
        {
          name: 'queue'
          image: image
          command: ['python', '-m', 'scripts.run_rq_worker']
          env: commonEnvironment
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
        }
      ]
      scale: {
        minReplicas: workerMinReplicas
        maxReplicas: workerMaxReplicas
        rules: [
          {
            name: 'redis-job-queue'
            custom: {
              type: 'redis'
              metadata: {
                address: redisScaleAddress
                listName: 'rq:queue:stemsplitter'
                listLength: '1'
                activationListLength: '0'
                databaseIndex: redisScaleDatabaseIndex
                enableTLS: 'true'
              }
              auth: [
                {
                  secretRef: 'redis-scale-username'
                  triggerParameter: 'username'
                }
                {
                  secretRef: 'redis-scale-password'
                  triggerParameter: 'password'
                }
              ]
            }
          }
        ]
      }
    }
  }
  dependsOn: [acrPull]
}

resource maintenance 'Microsoft.App/containerApps@2024-03-01' = if (deployApps) {
  name: '${resourcePrefix}-maintenance'
  location: location
  tags: tags
  identity: workloadIdentity
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      activeRevisionsMode: 'Single'
      registries: registryConfiguration
      secrets: secretValues
    }
    template: {
      containers: [
        {
          name: 'maintenance'
          image: image
          command: ['python', '-m', 'scripts.run_maintenance_worker']
          env: commonEnvironment
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
  dependsOn: [acrPull]
}

resource migrationJob 'Microsoft.App/jobs@2024-03-01' = if (deployApps) {
  name: '${resourcePrefix}-migrate'
  location: location
  tags: tags
  identity: workloadIdentity
  properties: {
    environmentId: environment.id
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 900
      replicaRetryLimit: 1
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: registryConfiguration
      secrets: secretValues
    }
    template: {
      containers: [
        {
          name: 'migrate'
          image: image
          command: ['python', '-m', 'scripts.apply_migrations']
          env: commonEnvironment
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
    }
  }
  dependsOn: [acrPull]
}

resource backupJob 'Microsoft.App/jobs@2024-03-01' = if (deployApps) {
  name: '${resourcePrefix}-backup'
  location: location
  tags: tags
  identity: workloadIdentity
  properties: {
    environmentId: environment.id
    configuration: {
      triggerType: 'Schedule'
      replicaTimeout: 1800
      replicaRetryLimit: 2
      scheduleTriggerConfig: {
        cronExpression: '0 3 * * *'
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: registryConfiguration
      secrets: secretValues
    }
    template: {
      containers: [
        {
          name: 'backup'
          image: image
          command: ['python', '-m', 'scripts.backup_postgres']
          env: commonEnvironment
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
    }
  }
  dependsOn: [acrPull]
}

output apiOrigin string = deployApps ? 'https://${api!.properties.configuration.ingress.fqdn}' : ''
output containerRegistry string = registry.properties.loginServer
output migrationJobName string = deployApps ? migrationJob.name : ''
output resourceGroupName string = resourceGroup().name
output applicationInsightsConnectionString string = appInsights.properties.ConnectionString
