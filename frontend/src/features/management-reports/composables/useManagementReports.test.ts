// @vitest-environment jsdom
import { defineComponent, h } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, expect, test, vi } from 'vitest'
import { useManagementReports } from './useManagementReports'
import * as api from '../api/managementReports'

vi.mock('../api/managementReports', () => ({
  fetchReportOptions: vi.fn(),
  fetchReportOverview: vi.fn(),
  fetchReportHistory: vi.fn(),
  fetchSavedReport: vi.fn(),
  captureReport: vi.fn(),
  downloadReportPdf: vi.fn()
}))

beforeEach(() => vi.resetAllMocks())

function setup() {
  let controller!: ReturnType<typeof useManagementReports>
  const wrapper = mount(
    defineComponent({
      setup() {
        controller = useManagementReports()
        return () => h('div')
      }
    })
  )
  return { wrapper, controller }
}

test('an options response after unmount cannot restore report scope or start more requests', async () => {
  let resolve!: (value: { slug: string; display_name: string }[]) => void
  vi.mocked(api.fetchReportOptions).mockReturnValue(
    new Promise((done) => {
      resolve = done
    })
  )
  const { wrapper, controller } = setup()
  wrapper.unmount()
  resolve([{ slug: 'ozgur', display_name: 'Özgür' }])
  await flushPromises()
  expect(controller.options.value).toEqual([])
  expect(controller.initialized.value).toBe(false)
  expect(api.fetchReportOverview).not.toHaveBeenCalled()
})

test('a late overview and history cannot replace the newly selected project', async () => {
  let resolveOverview!: (value: any) => void
  let resolveHistory!: (value: any) => void
  vi.mocked(api.fetchReportOptions).mockResolvedValue([
    { slug: 'ozgur', display_name: 'Özgür' },
    { slug: 'piku', display_name: 'Piku' }
  ])
  vi.mocked(api.fetchReportOverview)
    .mockReturnValueOnce(
      new Promise((done) => {
        resolveOverview = done
      })
    )
    .mockResolvedValueOnce({ report: { id: null, title: 'Current Piku' } } as any)
  vi.mocked(api.fetchReportHistory)
    .mockReturnValueOnce(
      new Promise((done) => {
        resolveHistory = done
      })
    )
    .mockResolvedValueOnce({ count: 0, next: null, previous: null, results: [] })
  const { wrapper, controller } = setup()
  await flushPromises()
  await controller.changeScope(['piku'])
  resolveOverview({ report: { title: 'Stale portfolio' } })
  resolveHistory({ count: 1, results: [{ id: 'stale' }] })
  await flushPromises()
  expect(controller.report.value?.title).toBe('Current Piku')
  expect(controller.history.value.results).toEqual([])
  expect(controller.selected.value).toEqual(['piku'])
  wrapper.unmount()
})
