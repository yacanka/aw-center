import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('@/shared/api/http', () => ({ apiClient: http }))

import {
  confirmPanelImport,
  previewPanelImport
} from '@/features/organization/api/organizationPanelImports'

describe('organization panel import API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('keeps preview and confirmation scoped to the selected project', async () => {
    const file = new File(['workbook'], 'panels.xlsx')
    http.post.mockResolvedValue({ data: { confirmation_token: 'signed' } })

    await previewPanelImport('project name', file)
    await confirmPanelImport('project name', file, 'signed')

    expect(http.post.mock.calls.map(([path]) => path)).toEqual([
      'projects/project%20name/organization/panels/imports/preview/',
      'projects/project%20name/organization/panels/imports/confirm/'
    ])
    const confirmation = http.post.mock.calls[1][1] as FormData
    expect(confirmation.get('file')).toBe(file)
    expect(confirmation.get('confirmation_token')).toBe('signed')
  })
})
