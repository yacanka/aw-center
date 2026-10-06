import { beforeEach, describe, expect, it, vi } from 'vitest'
const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }))
vi.mock('@/shared/api/http', () => ({ apiClient: http }))
import {
  importWatcherIssue,
  fetchWatcherStatus,
  updateWatcherRecord,
  deleteWatcherRecord,
  assessWatcherPdf
} from './watcher'
import type { IDcc } from '../models/dcc'
import { fetchDccRecords } from './dccRecords'

describe('Watcher API', () => {
  it('retains server pagination counts with filters', async () => {
    http.get.mockResolvedValue({
      data: { count: 25, next: '?page=2', previous: null, results: [] }
    })
    expect((await fetchDccRecords({ active: true })).pagination.count).toBe(25)
  })
  beforeEach(() => vi.clearAllMocks())
  it('uses canonical routes without browser Jira credentials', async () => {
    http.post.mockResolvedValue({ data: {} })
    await importWatcherIssue('CHN-42')
    await fetchWatcherStatus('record-1')
    expect(http.post.mock.calls).toEqual([
      ['dcc/records/import/', { issue: 'CHN-42' }],
      ['dcc/records/record-1/status/', {}]
    ])
  })
  it('keeps optimistic versions on update and removal', async () => {
    const record = { id: 'record-1', version: 7 } as IDcc
    http.patch.mockResolvedValue({ data: record })
    http.delete.mockResolvedValue({})
    await updateWatcherRecord(record, 'Changed', false)
    await deleteWatcherRecord(record)
    expect(http.patch).toHaveBeenCalledWith('dcc/records/record-1/', {
      title: 'Changed',
      active: false,
      version: 7
    })
    expect(http.delete).toHaveBeenCalledWith('dcc/records/record-1/', { data: { version: 7 } })
  })
  it('uploads a PDF with selected project scope', async () => {
    http.post.mockResolvedValue({ data: { assessment: 'Review' } })
    const file = new File(['%PDF'], 'ecr.pdf', { type: 'application/pdf' })
    await assessWatcherPdf(file, ['hys'])
    const [url, payload, config] = http.post.mock.calls[0]
    expect(config).toEqual({ timeout: 390_000 })
    expect(url).toBe('dcc/assessments/')
    expect(payload.get('file')).toBe(file)
    expect(payload.getAll('project_slugs')).toEqual(['hys'])
  })
})
