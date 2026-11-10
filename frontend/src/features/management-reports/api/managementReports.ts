import axios from 'axios'
import { apiClient } from '@/shared/api/http'
import type {
  ReportEnvelope,
  ReportPage,
  ReportProjectOption
} from '@/features/management-reports/models/managementReports'

const base = '/api/management-reports/'

export async function fetchReportOptions(signal?: AbortSignal): Promise<ReportProjectOption[]> {
  return (await apiClient.get<{ projects: ReportProjectOption[] }>(`${base}options/`, { signal }))
    .data.projects
}

export async function fetchReportOverview(projects: string[], signal?: AbortSignal) {
  return (
    await apiClient.get<ReportEnvelope>(`${base}overview/`, {
      params: { projects: projects.join(',') },
      signal
    })
  ).data
}

export async function fetchReportHistory(projects: string[], page: number, signal?: AbortSignal) {
  return (
    await apiClient.get<ReportPage>(`${base}reports/`, {
      params: { projects: projects.join(','), page },
      signal
    })
  ).data
}

export async function captureReport(
  project_slugs: string[],
  title: string,
  management_note: string,
  signal?: AbortSignal
) {
  return (
    await apiClient.post<ReportEnvelope>(
      `${base}reports/`,
      { project_slugs, title, management_note },
      { signal }
    )
  ).data
}

export async function fetchSavedReport(id: string, baseline?: string, signal?: AbortSignal) {
  return (
    await apiClient.get<ReportEnvelope>(`${base}reports/${encodeURIComponent(id)}/`, {
      params: baseline ? { baseline } : {},
      signal
    })
  ).data
}

/** Download only server-rendered bytes of an immutable saved report. */
export async function downloadReportPdf(id: string, baseline?: string, signal?: AbortSignal) {
  try {
    const response = await apiClient.get<Blob>(`${base}reports/${encodeURIComponent(id)}/pdf/`, {
      params: baseline ? { baseline } : {},
      responseType: 'blob',
      signal
    })
    return response.data
  } catch (cause) {
    throw await parsePdfError(cause)
  }
}

/** Blob transport also wraps JSON errors; restore the shared error contract for the UI. */
async function parsePdfError(cause: unknown): Promise<unknown> {
  if (!axios.isAxiosError(cause) || !(cause.response?.data instanceof Blob)) return cause
  try {
    cause.response.data = JSON.parse(await cause.response.data.text())
  } catch {
    // Keep non-JSON gateway responses opaque so raw HTML is never shown to users.
    return cause
  }
  return cause
}
