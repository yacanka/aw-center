// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { NSelect } from 'naive-ui'
import { flushPromises, mount } from '@vue/test-utils'
import WatcherSettings from './WatcherSettings.vue'
import { useProjectCatalogStore } from '@/features/projects/stores/projectCatalog'
import type { ProjectRegistryItem } from '@/features/projects/models/projectRegistry'
const api = vi.hoisted(() => ({
  preferences: vi.fn(),
  update: vi.fn(),
  status: vi.fn(),
  records: vi.fn()
}))
vi.mock('../api/watcher', () => ({
  fetchWatcherPreferences: api.preferences,
  updateWatcherPreferences: api.update,
  fetchWatcherStatus: api.status
}))
vi.mock('../api/jiraRecords', () => ({ fetchJiraTrackedIssues: api.records }))
function render() {
  return mount(WatcherSettings)
}
describe('Watcher settings', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    useProjectCatalogStore().$patch({
      status: 'ready',
      projects: [
        {
          slug: 'hys',
          name: 'HYS',
          capabilities: ['jira'],
          roles: { jira: 'operator' }
        } as ProjectRegistryItem
      ]
    })
    api.preferences.mockResolvedValue({ outstanding_only: false, detail_fields: {} })
    api.records.mockResolvedValue({
      results: [{ id: 'record-1', issue: 'CHN-42', title: 'Title', project_slugs: ['hys'] }],
      pagination: { next: null }
    })
    api.status.mockResolvedValue({
      detail_fields: [
        { id: 'priority', label: 'Priority', value: 'High' },
        { id: 'customfield_45000', label: 'ECD number', value: 'ECD-1' }
      ]
    })
    api.update.mockResolvedValue({ outstanding_only: false, detail_fields: { hys: [] } })
  })
  it('loads available fields from a tracked key and saves an explicit empty selection', async () => {
    const wrapper = render()
    await flushPromises()
    expect(api.records).toHaveBeenCalledWith(expect.objectContaining({ project_slug: 'hys' }))
    const selects = wrapper.findAllComponents(NSelect)
    selects[1].vm.$emit('update:value', 'record-1')
    await flushPromises()
    expect(api.status).toHaveBeenCalledWith('record-1')
    expect(wrapper.findAllComponents(NSelect)[2].props('options')).toEqual([
      { label: 'Priority', value: 'priority' },
      { label: 'ECD number', value: 'customfield_45000' }
    ])
    wrapper.findAllComponents(NSelect)[2].vm.$emit('update:value', [])
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Save detail fields')!
      .trigger('click')
    await flushPromises()
    expect(api.update).toHaveBeenCalledWith({ project_slug: 'hys', detail_field_ids: [] })
    expect(wrapper.text()).toContain('Detail fields saved')
  })
  it('shows load errors and does not permit saving incomplete settings', async () => {
    api.preferences.mockRejectedValue(new Error('offline'))
    const wrapper = render()
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(api.update).not.toHaveBeenCalled()
  })
  it('retries the failed load-more page without duplicating earlier records', async () => {
    const result = (page: number, next: string | null) => ({
      results: [
        { id: `record-${page}`, issue: `CHN-${page}`, title: 'Title', project_slugs: ['hys'] }
      ],
      pagination: { next }
    })
    api.records.mockReset()
    api.records
      .mockResolvedValueOnce(result(1, '?page=2'))
      .mockResolvedValueOnce(result(2, '?page=3'))
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(result(3, null))
    const wrapper = render()
    await flushPromises()
    const button = (label: string) =>
      wrapper.findAll('button').find((item) => item.text() === label)!
    await button('Load more tracked issues').trigger('click')
    await flushPromises()
    await button('Load more tracked issues').trigger('click')
    await flushPromises()
    await button('Retry loading fields').trigger('click')
    await flushPromises()
    expect(api.records).toHaveBeenLastCalledWith(expect.objectContaining({ page: 3 }))
    expect(wrapper.findAllComponents(NSelect)[1].props('options')).toHaveLength(3)
  })
  it('clears old pagination when a new project cannot load its first page', async () => {
    const catalog = useProjectCatalogStore()
    catalog.projects.push({ ...catalog.projects[0], slug: 'gokbey', name: 'Gokbey' })
    api.records
      .mockResolvedValueOnce({
        results: [{ id: 'record-1', issue: 'CHN-1', title: 'Title', project_slugs: ['hys'] }],
        pagination: { next: '?page=2' }
      })
      .mockRejectedValueOnce(new Error('offline'))
    const wrapper = render()
    await flushPromises()
    expect(wrapper.text()).toContain('Load more tracked issues')
    wrapper.findAllComponents(NSelect)[0].vm.$emit('update:value', 'gokbey')
    await flushPromises()
    expect(wrapper.text()).not.toContain('Load more tracked issues')
    expect(api.records).toHaveBeenLastCalledWith(
      expect.objectContaining({ project_slug: 'gokbey', page: 1 })
    )
  })
})
