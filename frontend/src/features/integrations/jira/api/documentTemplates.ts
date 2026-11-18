import { apiClient } from '@/shared/api/http'
import { formatApiError, isApiErrorPayload } from '@/shared/api/apiError'
import { saveBlobAsFile } from '@/shared/services/download'
import type { Job } from '@/features/jobs/api/jobs'

const templatesPath = 'integrations/jira/document-templates/'
const generationPath = 'integrations/jira/document-generation/'

export interface Placeholder {
  name: string
  count: number
}

interface JiraDocumentScope {
  project_id: string
  project_name: string
  issue_type_id: string
  issue_type_name: string
}

export interface DocumentTemplate extends JiraDocumentScope {
  id: string
  name: string
  version: number
  archived: boolean
  placeholders: Placeholder[]
  mapping: Record<string, string>
}

export interface ResolvedDocumentIssue extends JiraDocumentScope {
  issue: string
  fields: Array<{ id: string; name: string; value: string; supported: boolean }>
  templates: DocumentTemplate[]
}

export async function listDocumentTemplates(): Promise<DocumentTemplate[]> {
  return (await apiClient.get<{ templates: DocumentTemplate[] }>(templatesPath)).data.templates
}

export async function getDocumentTemplate(id: string): Promise<DocumentTemplate> {
  return (await apiClient.get<DocumentTemplate>(templatesPath + encodeURIComponent(id) + '/')).data
}

export async function downloadDocumentTemplate(template: DocumentTemplate): Promise<void> {
  const response = await apiClient.get<Blob>(
    templatesPath + encodeURIComponent(template.id) + '/source/',
    {
      responseType: 'blob'
    }
  )
  saveBlobAsFile(response.data, template.name.replace(/\.docx$/i, '') + '.docx')
}

export async function inspectDocumentTemplate(file: File): Promise<Placeholder[]> {
  const form = new FormData()
  form.set('file', file)
  return (await apiClient.post<{ placeholders: Placeholder[] }>(templatesPath + 'inspect/', form))
    .data.placeholders
}

export async function resolveDocumentIssue(
  issue: string,
  signal: AbortSignal
): Promise<ResolvedDocumentIssue> {
  return (
    await apiClient.post<ResolvedDocumentIssue>(generationPath + 'resolve/', { issue }, { signal })
  ).data
}

export interface TemplateChanges {
  name?: string
  file?: File
  issue?: string
  mapping?: Record<string, string>
  archived?: boolean
}

export async function saveDocumentTemplate(
  template: DocumentTemplate | null,
  changes: TemplateChanges
): Promise<DocumentTemplate> {
  const payload = template ? { version: template.version, ...changes } : changes
  let body: typeof payload | FormData = payload
  if (changes.file) {
    body = new FormData()
    for (const [key, value] of Object.entries(payload)) {
      body.set(
        key,
        value instanceof File
          ? value
          : typeof value === 'object'
            ? JSON.stringify(value)
            : String(value)
      )
    }
  }
  if (template) {
    return (
      await apiClient.patch<DocumentTemplate>(
        templatesPath + encodeURIComponent(template.id) + '/',
        body
      )
    ).data
  }
  return (await apiClient.post<DocumentTemplate>(templatesPath, body)).data
}

export interface GenerateDocumentRequest {
  issue: string
  template_id: string
  version: number
  manual_values: Record<string, string>
}

export async function generateJiraDocument(
  payload: GenerateDocumentRequest,
  key: string
): Promise<Job> {
  return (
    await apiClient.post<Job>(generationPath + 'jobs/', payload, {
      headers: { 'Idempotency-Key': key }
    })
  ).data
}

/** Include the server's public validation messages beside its normal error and reference. */
export function documentError(error: unknown): string {
  const detail = formatApiError(error)
  const payload = (error as { response?: { data?: unknown } } | null)?.response?.data
  if (!isApiErrorPayload(payload) || !payload.errors) return detail
  const lines = Object.entries(payload.errors).flatMap(([field, errors]) =>
    (Array.isArray(errors) ? errors : [errors])
      .filter((message): message is string => typeof message === 'string')
      .map((message) => field + ': ' + message)
  )
  return [detail, ...lines].join('\n')
}
