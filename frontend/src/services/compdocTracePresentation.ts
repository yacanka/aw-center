import type { CompdocDccTrace, TraceJobStatus } from '@/services/compdocTraceability'

export type TraceVisualType = 'success' | 'warning' | 'error' | 'info'

/** Convert a trace job status into a readable label. */
export function readableTraceStatus(status: TraceJobStatus): string {
  return status.replaceAll('_', ' ')
}

/** Select the timeline severity for a trace. */
export function traceTimelineType(trace: CompdocDccTrace): TraceVisualType {
  if (!trace.is_current_version && trace.source_change.comparison_status !== 'unchanged') {
    return 'warning'
  }
  if (trace.job_status === 'failed') return 'error'
  return trace.job_status === 'succeeded' ? 'success' : 'info'
}

/** Select the alert severity for a source comparison. */
export function sourceChangeAlertType(trace: CompdocDccTrace): 'warning' | 'info' {
  return trace.source_change.comparison_status === 'unchanged' ? 'info' : 'warning'
}

/** Select the source-version tag severity. */
export function sourceVersionTagType(trace: CompdocDccTrace): 'success' | 'warning' | 'info' {
  if (trace.is_current_version) return 'success'
  return trace.source_change.comparison_status === 'unchanged' ? 'info' : 'warning'
}

/** Describe whether the captured source is current for DCC rendering. */
export function sourceVersionLabel(trace: CompdocDccTrace): string {
  if (trace.is_current_version) return 'Current source version'
  return trace.source_change.comparison_status === 'unchanged'
    ? 'Newer non-DCC metadata'
    : 'Older DCC source'
}

/** Explain the source change without exposing field values. */
export function sourceChangeMessage(trace: CompdocDccTrace): string {
  const status = trace.source_change.comparison_status
  if (status === 'changed') return 'Fields rendered into this DCC changed and require review.'
  if (status === 'unchanged')
    return 'Source history advanced, but DCC-visible fields are unchanged.'
  return 'The captured history is unavailable; compare this DCC manually.'
}

/** Select the visual treatment for a DCC job state. */
export function traceStatusType(
  status: TraceJobStatus
): 'success' | 'warning' | 'error' | 'info' | 'default' {
  if (status === 'succeeded') return 'success'
  if (status === 'failed') return 'error'
  if (status === 'archived' || status.includes('cancel')) return 'warning'
  return status === 'running' ? 'info' : 'default'
}
