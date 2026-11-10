import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ delete: vi.fn(), get: vi.fn(), patch: vi.fn(), post: vi.fn() }))
vi.mock('@/shared/api/http', () => ({ apiClient: http }))
vi.mock('@/shared/services/notify', () => ({
  notifyError: vi.fn(),
  notifySuccess: vi.fn(),
  notifyWarning: vi.fn()
}))

import { createPresentationController } from '@/features/tools/composables/presentationController'

describe('route-local presentation controller', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('queues upload and reconversion with stable caller-owned idempotency keys', async () => {
    const uploadJob = { id: 'upload-job', status: 'queued' }
    const reconvertJob = { id: 'reconvert-job', status: 'queued' }
    http.post
      .mockResolvedValueOnce({ status: 201, data: uploadJob })
      .mockResolvedValueOnce({ status: 201, data: reconvertJob })
    const controller = createPresentationController()
    const form = new FormData()

    await expect(controller.uploadPresentation(form, 'upload-attempt')).resolves.toBe(uploadJob)
    await expect(controller.reconvertPresentation('42', 'reconvert-attempt')).resolves.toBe(
      reconvertJob
    )

    expect(http.post.mock.calls).toEqual([
      [
        'tools/presentations/presentations/upload/',
        form,
        { headers: { 'Idempotency-Key': 'upload-attempt' } }
      ],
      [
        'tools/presentations/presentations/42/reconvert/',
        {},
        { headers: { 'Idempotency-Key': 'reconvert-attempt' } }
      ]
    ])
  })

  it('consumes the bounded page contract and normalizes resource IDs to strings', async () => {
    http.get.mockResolvedValue({
      status: 200,
      data: {
        count: 1,
        next: null,
        previous: null,
        results: [
          {
            id: 42,
            title: 'Architecture',
            status: 'ready',
            created_at: '2026-08-12T00:00:00Z',
            conversion_job_id: 'conversion-job',
            slides: [
              {
                id: 7,
                index: 1,
                image_url: '/api/tools/presentations/slides/7/image/',
                thumb_url: '/api/tools/presentations/slides/7/thumb/',
                updated_at: '2026-08-12T00:00:00Z'
              }
            ]
          }
        ]
      }
    })
    const controller = createPresentationController()

    const presentations = await controller.fetchPresentations()

    expect(http.get).toHaveBeenCalledWith('tools/presentations/presentations/', {
      params: { page_size: 100 }
    })
    expect(presentations[0].id).toBe('42')
    expect(presentations[0].slides[0].id).toBe('7')
  })
})
