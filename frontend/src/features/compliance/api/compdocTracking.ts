import { apiClient as axios } from '@/shared/api/http'
import { compdocDocumentPath } from '@/shared/api/apiPaths'

export type ResponsibleMode = 'automatic' | 'custom'
export type CompDocNotificationEvent = 'overdue' | 'due_soon' | 'revision_available'

export interface CompDocTracking {
  responsible_mode: ResponsibleMode
  responsible_person_ids: number[]
  notification_enabled: boolean
  notification_events: CompDocNotificationEvent[]
  docproof_status: string
  docproof_issue: string
  docproof_checked_at: string | null
  notification_checked_at: string | null
  version: number
  updated_at: string | null
}

export interface CompDocTrackingPreferenceValues {
  responsible_mode: ResponsibleMode
  responsible_person_ids: number[]
  notification_enabled: boolean
  notification_events: CompDocNotificationEvent[]
}

export interface CompDocTrackingUpdate extends CompDocTrackingPreferenceValues {
  version: number
}

export const TRACKING_EVENT_OPTIONS: Array<{ value: CompDocNotificationEvent; label: string }> = [
  { value: 'overdue', label: 'Overdue' },
  { value: 'due_soon', label: 'Due soon' },
  { value: 'revision_available', label: 'Revision available' }
]

/** Map a persisted DocProof state to a compact semantic tag. */
export function docproofTagType(status: string): 'success' | 'warning' | 'default' {
  if (status === 'current') return 'success'
  return status === 'revision_available' ? 'warning' : 'default'
}

/** Format persisted UTC timestamps for compact operator-facing display. */
export function formatTrackingTimestamp(value: string | null) {
  if (!value) return 'never'
  return new Intl.DateTimeFormat('tr-TR', {
    dateStyle: 'short',
    timeStyle: 'short'
  }).format(new Date(value))
}

/** Load one document's tracking workspace. */
export async function fetchCompDocTracking(project: string, documentId: string) {
  return (await axios.get<CompDocTracking>(trackingPath(project, documentId))).data
}

/** Persist responsible and notification preferences. */
export async function saveCompDocTracking(
  project: string,
  documentId: string,
  payload: CompDocTrackingUpdate
) {
  return (await axios.put<CompDocTracking>(trackingPath(project, documentId), payload)).data
}

/** Refresh persisted DocProof evidence without sending credentials through the browser. */
export async function refreshCompDocTracking(project: string, documentId: string, version: number) {
  return (
    await axios.post<CompDocTracking>(`${trackingPath(project, documentId)}docproof/`, { version })
  ).data
}

function trackingPath(project: string, documentId: string) {
  return `${documentPath(project, documentId)}/tracking/`
}

function documentPath(project: string, documentId: string) {
  return compdocDocumentPath(project, documentId)
}
