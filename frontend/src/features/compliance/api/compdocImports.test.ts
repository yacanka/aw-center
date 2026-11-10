import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/shared/api/http', () => ({ apiClient: http }))

import {
  confirmCompdocImport,
  previewCompdocImport,
  confirmDoorsImport,
  fetchDoorsImportSource,
  previewDoorsImport
} from '@/features/compliance/api/compdocImports'

describe('compliance DOORS import API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('keeps source, preview, and confirmation project-scoped', async () => {
    const collection = 'projects/ozgur/compliance-documents/'
    const mapping = { 'Document Title': 'name', 'Cover Code': 'cover_page_no' }
    http.get.mockResolvedValue({ data: { job_id: 'job-1' } })
    http.post.mockResolvedValue({ data: { confirmation_token: 'signed' } })

    await fetchDoorsImportSource(collection, 'job-1')
    await previewDoorsImport(collection, 'job-1', mapping)
    await confirmDoorsImport(collection, 'job-1', mapping, 'signed')

    expect(http.get).toHaveBeenCalledWith(
      'projects/ozgur/compliance-documents/imports/doors/sources/job-1/'
    )
    expect(http.post.mock.calls).toEqual([
      ['projects/ozgur/compliance-documents/imports/doors/preview/', { job_id: 'job-1', mapping }],
      [
        'projects/ozgur/compliance-documents/imports/doors/confirm/',
        { job_id: 'job-1', mapping, confirmation_token: 'signed' }
      ]
    ])
  })
})

describe('Excel manual mapping API', () => {
  it('sends exact column links with preview and confirmation multipart data', async () => {
    http.post.mockClear()
    http.post.mockResolvedValue({ data: {} })
    const file = new File(['workbook'], 'documents.xlsx')
    const mapping = { ' Custom title ': 'name' }
    await previewCompdocImport('collection/', file, mapping)
    await confirmCompdocImport('collection/', file, 'reviewed', mapping)
    const preview = http.post.mock.calls[0][1] as FormData
    const confirm = http.post.mock.calls[1][1] as FormData
    expect(preview.get('mapping')).toBe(JSON.stringify(mapping))
    expect(confirm.get('mapping')).toBe(JSON.stringify(mapping))
    expect(confirm.get('confirmation_token')).toBe('reviewed')
    expect(preview.has('confirmation_token')).toBe(false)
  })
})
