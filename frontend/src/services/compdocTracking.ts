import axios from 'axios'

export type ResponsibleMode = 'automatic' | 'custom'
export type CompDocNotificationEvent = 'overdue' | 'due_soon' | 'revision_available'

export interface CompDocResponsibleContact {
  id: number
  name: string
  email: string
  title: string
  panel: string
  panel_name: string
}

export interface CompDocNotificationLog {
  id: string
  event_type: CompDocNotificationEvent
  status: 'pending' | 'sent' | 'failed'
  recipient_count: number
  primary_recipient_count: number
  escalation_recipient_count: number
  policy_version: number
  attempt_count: number
  error_code: string
  created_at: string
  sent_at: string | null
}

export interface CompDocNotificationEventState {
  value: CompDocNotificationEvent
  label: string
  applicable: boolean
  detail: string
  recipient_count: number
  primary_recipient_count: number
  escalation_recipient_count: number
  policy_version: number
}

export interface CompDocTracking {
  document: {
    id: string
    name: string
    ata: string | null
    panel: string | null
    tech_doc_no: string
    tech_doc_issue: string
    delivered_tech_doc_issue: string
    status: string
    ubm_target_date: string | null
  }
  responsible_mode: ResponsibleMode
  responsible_person_ids: number[]
  responsibles: CompDocResponsibleContact[]
  candidate_responsibles: CompDocResponsibleContact[]
  configured: boolean
  notification_enabled: boolean
  notification_events: CompDocNotificationEvent[]
  event_options: Array<{ value: CompDocNotificationEvent; label: string }>
  event_states: CompDocNotificationEventState[]
  docproof: {
    status: string
    issue: string
    checked_at: string | null
  }
  recent_notifications: CompDocNotificationLog[]
}

export interface CompDocTrackingUpdate {
  responsible_mode: ResponsibleMode
  responsible_person_ids: number[]
  notification_enabled: boolean
  notification_events: CompDocNotificationEvent[]
}

export interface CompDocNotificationResult {
  status: 'sent' | 'failed' | 'not_applicable' | 'already_processed'
  event_type: CompDocNotificationEvent
  recipient_count?: number
  tracking: CompDocTracking
}

export interface CompDocNotificationDraft {
  blob: Blob
  filename: string
}

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

/** Refresh the persisted DocProof revision status. */
export async function checkCompDocRevision(project: string, documentId: string) {
  const path = `${documentPath(project, documentId)}/docproof/`
  return (await axios.post<CompDocTracking>(path)).data
}

/** Send one currently applicable event through the configured mail transport. */
export async function sendCompDocNotification(
  project: string,
  documentId: string,
  eventType: CompDocNotificationEvent
) {
  const path = `${documentPath(project, documentId)}/notifications/`
  return (await axios.post<CompDocNotificationResult>(path, { event_type: eventType })).data
}

/** Download one editable Outlook draft built from the shared notification template. */
export async function downloadCompDocNotificationDraft(
  project: string,
  documentId: string,
  eventType: CompDocNotificationEvent
): Promise<CompDocNotificationDraft> {
  const path = `${documentPath(project, documentId)}/notifications/draft/`
  try {
    const response = await axios.post<Blob>(
      path,
      { event_type: eventType },
      { responseType: 'blob' }
    )
    return {
      blob: response.data,
      filename: draftFilename(response.headers['content-disposition'], project, eventType)
    }
  } catch (cause) {
    throw await parseBlobError(cause)
  }
}

function trackingPath(project: string, documentId: string) {
  return `${documentPath(project, documentId)}/tracking/`
}

function documentPath(project: string, documentId: string) {
  return `/${encodeURIComponent(project)}/compdocs/${encodeURIComponent(documentId)}`
}

function draftFilename(header: unknown, project: string, eventType: string) {
  const match = typeof header === 'string' ? /filename="([^"]+\.msg)"/i.exec(header) : null
  return match?.[1] || `${project}-${eventType}.msg`
}

async function parseBlobError(cause: unknown): Promise<unknown> {
  if (!axios.isAxiosError(cause) || !(cause.response?.data instanceof Blob)) return cause
  try {
    cause.response.data = JSON.parse(await cause.response.data.text())
  } catch {
    return cause
  }
  return cause
}
