import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/shared/api/http', () => ({ apiClient: http }))

import {
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
