import type { IntegrationItem } from '@/services/integrationHub'
import type { Job, JobStatus, JobSystemStatus } from '@/services/jobs'

export interface WorkMetric {
  label: string
  value: number
  status: JobStatus
}

/** Return the active owner-scoped job counts shown on the application home. */
export function buildWorkMetrics(systemStatus: JobSystemStatus | null): WorkMetric[] {
  const counts = systemStatus?.counts || {}
  return [
    metric('Waiting for review', 'awaiting_confirmation', counts.awaiting_confirmation),
    metric('Queued', 'queued', counts.queued),
    metric('In progress', 'running', (counts.running || 0) + (counts.cancel_requested || 0))
  ]
}

/** Select the newest successful owner-scoped jobs for recent activity. */
export function recentSuccessfulJobs(jobs: Job[], limit = 4): Job[] {
  return jobs.filter((job) => job.status === 'succeeded').slice(0, Math.max(0, limit))
}

/** Return only configuration or live-health integration exceptions. */
export function integrationExceptions(integrations: IntegrationItem[]): IntegrationItem[] {
  return integrations.filter((item) => {
    const health = item.health?.status
    return item.status === 'attention' || health === 'degraded' || health === 'unavailable'
  })
}

function metric(label: string, status: JobStatus, value = 0): WorkMetric {
  return { label, status, value }
}
