import axios from 'axios'

export type IntegrationStatus = 'ready' | 'attention'
export type IntegrationHealthStatus =
  'available' | 'degraded' | 'unavailable' | 'not_configured' | 'unsupported' | 'checking'

export type IntegrationHealth = {
  status: IntegrationHealthStatus
  detail: string
  checked_at: string | null
  latency_ms: number | null
  source: 'live' | 'cache' | 'circuit' | 'busy'
}

export type IntegrationItem = {
  id: string
  name: string
  category: 'external' | 'local'
  status: IntegrationStatus
  configured: boolean
  description: string
  capabilities: string[]
  route: string | null
  platform: 'windows' | 'cross-platform'
  health?: IntegrationHealth
}

/** Returns the non-secret integration capability and readiness catalog. */
export async function fetchIntegrationCatalog(probe = false, refresh = false) {
  const response = await axios.get<{ integrations: IntegrationItem[] }>('integrations/', {
    params: { probe: probe || undefined, refresh: refresh || undefined }
  })
  return response.data.integrations
}
