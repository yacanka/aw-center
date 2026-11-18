import { flushPromises } from '@vue/test-utils'
import { expect, it, vi } from 'vitest'

const get = vi.hoisted(() => vi.fn())
vi.mock('@/shared/api/http', () => ({ apiClient: { get } }))

import { createCompdocController } from './compdocController'

it('rechecks dashboard membership after a document is created or its CAT changes', async () => {
  const matching = { id: 'existing', cat: 'A' }
  const page = (results: unknown[]) => ({
    status: 200,
    data: { results, count: results.length, next: null, previous: null }
  })
  get.mockResolvedValueOnce(page([matching])).mockResolvedValue(page([]))
  const store = createCompdocController()
  store.setProjectName('ozgur')
  await store.fetchCompdocs({ dashboard_cat: 'A', page: 1 })

  store.acceptCreatedCompdoc({ id: 'created', cat: 'B' })
  expect(store.getCompdocs.map((row) => row.id)).toEqual(['existing'])
  await flushPromises()
  expect(store.getCompdocs).toEqual([])

  get.mockResolvedValueOnce(page([matching]))
  await store.fetchCompdocs()
  store.acceptUpdatedCompdoc({ ...matching, cat: 'B' })
  expect(store.getCompdocs[0].cat).toBe('A')
  await flushPromises()
  expect(store.getCompdocs).toEqual([])
  expect(get.mock.lastCall?.[1].params).toEqual({ dashboard_cat: 'A', page: 1 })
})
