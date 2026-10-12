import { beforeEach, describe, expect, it, vi } from 'vitest'
const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }))
vi.mock('@/shared/api/http', () => ({ apiClient: http }))
import {
  importWatcherIssue,
  fetchWatcherStatus,
  fetchWatcherPreferences,
  updateWatcherPreferences,
  deleteWatcherRecord,
  assessWatcherPdf
} from './watcher'
import type { IJiraTrackedIssue } from '../models/records'
import { fetchJiraTrackedIssues } from './jiraRecords'

describe('Watcher API', () => {
  it('retains server pagination counts with filters', async () => {
    http.get.mockResolvedValue({
      data: { count: 25, next: '?page=2', previous: null, results: [] }
    })
    expect((await fetchJiraTrackedIssues({ title: 'Change' })).pagination.count).toBe(25)
  })
  beforeEach(() => vi.clearAllMocks())
  it('uses canonical routes without browser Jira credentials', async () => {
    http.post.mockResolvedValue({ data: {} })
    await importWatcherIssue('CHN-42')
    await fetchWatcherStatus('record-1')
    expect(http.post.mock.calls).toEqual([
      ['integrations/jira/records/import/', { issue: 'CHN-42' }],
      ['integrations/jira/records/record-1/status/', {}]
    ])
  })
  it('keeps optimistic versions on removal', async () => {
    const record = { id: 'record-1', version: 7 } as IJiraTrackedIssue
    http.delete.mockResolvedValue({})
    await deleteWatcherRecord(record)
    expect(http.delete).toHaveBeenCalledWith('integrations/jira/records/record-1/', {
      data: { version: 7 }
    })
  })
  it('reads and saves user-bound Watcher preferences without replacing unrelated settings', async () => {
    const preferences = { outstanding_only: true, detail_fields: { hys: ['priority'] } }
    http.get.mockResolvedValue({ data: preferences })
    http.patch.mockResolvedValue({ data: preferences })
    expect(await fetchWatcherPreferences()).toEqual(preferences)
    expect(
      await updateWatcherPreferences({ project_slug: 'hys', detail_field_ids: ['priority'] })
    ).toEqual(preferences)
    expect(http.get).toHaveBeenCalledWith('integrations/jira/watcher/preferences/')
    expect(http.patch).toHaveBeenCalledWith('integrations/jira/watcher/preferences/', {
      project_slug: 'hys',
      detail_field_ids: ['priority']
    })
  })
  it('uploads a PDF with selected project scope', async () => {
    http.post.mockResolvedValue({ data: { assessment: 'Review' } })
    const file = new File(['%PDF'], 'ecr.pdf', { type: 'application/pdf' })
    await assessWatcherPdf(file, ['hys'])
    const [url, payload, config] = http.post.mock.calls[0]
    expect(config).toEqual({ timeout: 390_000 })
    expect(url).toBe('integrations/jira/assessments/')
    expect(payload.get('file')).toBe(file)
    expect(payload.getAll('project_slugs')).toEqual(['hys'])
  })
})
