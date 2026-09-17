import { API_PATHS } from '@/shared/api/apiPaths'
import { apiClient } from '@/shared/api/http'
import type { Job } from '@/features/jobs/api/jobs'

export interface QualityAttribute {
  name: string | null
  method: 'exact' | 'heuristic' | 'unresolved'
  candidates: string[]
}

export interface QualityFinding {
  code: string
  message: string
  suggestion: string
  chapter: string
  panels: string[]
  evidence_count: number
  evidence: {
    absolute_number: number
    identifier: string
    ata_value: string
    panel_value: string
  }[]
}

export interface DoorsQualityResult {
  type: 'doors_module_quality'
  schema_version: 1
  module_path: string
  outcome: 'passed' | 'review_required' | 'incomplete'
  complete: boolean
  attributes: { ata: QualityAttribute; panel: QualityAttribute }
  warnings: string[]
  summary: {
    scanned_objects: number
    checked_objects: number
    unassigned_objects: number
    unresolved_objects: number
    conflicting_chapters: number
    chapters: number
    finding_count: number
    omitted_findings: number
  }
  findings: QualityFinding[]
}

/** Queue the fixed read-only agent task with owner-scoped request idempotency. */
export async function enqueueDoorsQualityCheck(path: string, key: string): Promise<Job> {
  return (
    await apiClient.post<Job>(
      `${API_PATHS.doors}/module-quality-jobs/`,
      { module_path: path },
      { headers: { 'Idempotency-Key': key } }
    )
  ).data
}

/** Read a completed, SHA-256-verified private report and reject incompatible data. */
export async function fetchDoorsQualityResult(job: Job): Promise<DoorsQualityResult> {
  if (
    job.kind !== 'doors.check_module_quality' ||
    job.status !== 'succeeded' ||
    !job.download_url
  ) {
    throw new Error('The DOORS quality report is unavailable.')
  }
  const { data } = await apiClient.get<unknown>(job.download_url, { responseType: 'json' })
  if (!validResult(data)) throw new Error('The DOORS quality report is invalid or unsupported.')
  return data
}

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string')
}

function count(value: unknown): boolean {
  return Number.isSafeInteger(value) && Number(value) >= 0
}

function validAttribute(value: unknown): boolean {
  return (
    record(value) &&
    (value.name === null || typeof value.name === 'string') &&
    ['exact', 'heuristic', 'unresolved'].includes(String(value.method)) &&
    strings(value.candidates)
  )
}

function validFinding(value: unknown): boolean {
  return (
    record(value) &&
    ['code', 'message', 'suggestion', 'chapter'].every((key) => typeof value[key] === 'string') &&
    strings(value.panels) &&
    count(value.evidence_count) &&
    Array.isArray(value.evidence) &&
    value.evidence.every(
      (item) =>
        record(item) &&
        count(item.absolute_number) &&
        ['identifier', 'ata_value', 'panel_value'].every((key) => typeof item[key] === 'string')
    )
  )
}

function validResult(value: unknown): value is DoorsQualityResult {
  if (!record(value) || !record(value.attributes) || !record(value.summary)) return false
  const summary = value.summary
  return (
    value.type === 'doors_module_quality' &&
    value.schema_version === 1 &&
    typeof value.module_path === 'string' &&
    ['passed', 'review_required', 'incomplete'].includes(String(value.outcome)) &&
    typeof value.complete === 'boolean' &&
    validAttribute(value.attributes.ata) &&
    validAttribute(value.attributes.panel) &&
    strings(value.warnings) &&
    [
      'scanned_objects',
      'checked_objects',
      'unassigned_objects',
      'unresolved_objects',
      'conflicting_chapters',
      'chapters',
      'finding_count',
      'omitted_findings'
    ].every((key) => count(summary[key])) &&
    Array.isArray(value.findings) &&
    value.findings.every(validFinding) &&
    (value.outcome !== 'passed' || (value.complete && summary.finding_count === 0))
  )
}
