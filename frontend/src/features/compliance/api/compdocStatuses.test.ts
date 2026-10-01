import { beforeEach, expect, it, vi } from 'vitest'
import { fetchCompdocStatuses, createCompdocStatus, deleteCompdocStatus } from './compdocStatuses'
import { createStatusChartRows } from './compdocChartData'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }))
vi.mock('@/shared/api/http', () => ({ apiClient: http }))
beforeEach(() => vi.clearAllMocks())
it('uses project scoped endpoints for shared status settings', async () => {
  const option = { id: 'id', value: 'custom', label: 'Custom', usage_count: 0, can_delete: true }
  http.get.mockResolvedValue({ data: [option] })
  http.post.mockResolvedValue({ data: option })
  expect(await fetchCompdocStatuses('ozgur')).toEqual([option])
  expect(await createCompdocStatus('ozgur', 'Custom')).toEqual(option)
  await deleteCompdocStatus('ozgur', 'id')
  expect(http.get).toHaveBeenCalledWith('projects/ozgur/compliance-documents/statuses/')
  expect(http.post).toHaveBeenCalledWith('projects/ozgur/compliance-documents/statuses/', {
    label: 'Custom'
  })
  expect(http.delete).toHaveBeenCalledWith('projects/ozgur/compliance-documents/statuses/id/')
})
it('includes custom chart statuses and uses project labels without unrelated fixed categories', () => {
  const rows = createStatusChartRows(
    { custom: 2, unknown: 1 },
    [
      { value: 'custom', label: 'Custom approval' },
      { value: 'unknown', label: 'Unknown' }
    ],
    '#aaa'
  )
  expect(rows.map((row) => row.value)).toEqual(['custom', 'unknown'])
  expect(rows[0]).toMatchObject({
    label: 'Custom approval',
    count: 2,
    percentage: 67,
    color: '#aaa'
  })
})
