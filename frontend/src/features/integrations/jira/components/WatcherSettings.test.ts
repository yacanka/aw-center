// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { NSelect } from 'naive-ui'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import WatcherSettings from './WatcherSettings.vue'
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
const record = (id: string, components: string[] | null) => ({
  id,
  issue: 'CHN-42',
  title: 'Title',
  project_slugs: ['hys'],
  components
})
const fields = [
  { id: 'priority', label: 'Priority', value: 'High' },
  { id: 'customfield_45000', label: 'ECD number', value: 'ECD-1' }
]
const button = (wrapper: ReturnType<typeof mount>, label: string) =>
  wrapper.findAll('button').find((item) => item.text() === label)!
describe('Watcher component settings', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
    api.preferences.mockResolvedValue({
      outstanding_only: false,
      detail_fields: {},
      component_fields: {}
    })
    api.records.mockResolvedValue({
      results: [record('one', ['Hydraulics'])],
      pagination: { next: null }
    })
    api.status.mockResolvedValue({
      components: ['Hydraulics'],
      project_slugs: ['hys'],
      detail_fields: fields
    })
    api.update.mockResolvedValue({
      outstanding_only: false,
      detail_fields: {},
      component_fields: { 'component:Hydraulics': [] }
    })
  })
  it('shows only tracked components and automatically discovers fields before saving an empty selection', async () => {
    const wrapper = mount(WatcherSettings)
    await flushPromises()
    expect(wrapper.findAllComponents(NSelect)[0].props('options')).toEqual([
      { label: 'Hydraulics', value: 'component:Hydraulics' }
    ])
    expect(wrapper.findAllComponents(NSelect)[1].props('options')).toEqual([
      { label: 'Priority', value: 'priority' },
      { label: 'ECD number', value: 'customfield_45000' }
    ])
    wrapper.findAllComponents(NSelect)[1].vm.$emit('update:value', [])
    await button(wrapper, 'Save detail fields').trigger('click')
    await flushPromises()
    expect(api.update).toHaveBeenCalledWith({
      record_id: 'one',
      component_name: 'Hydraulics',
      detail_field_ids: []
    })
    expect(wrapper.text()).toContain('Detail fields saved')
    wrapper.unmount()
  })
  it('lists components from every page, deduplicates shared names and supports None', async () => {
    api.records
      .mockResolvedValueOnce({
        results: [record('one', ['Hydraulics', 'Safety'])],
        pagination: { next: '?page=2' }
      })
      .mockResolvedValueOnce({
        results: [record('two', ['Safety']), record('three', [])],
        pagination: { next: null }
      })
    api.status.mockImplementation(async (id) => ({
      components: id === 'three' ? [] : ['Hydraulics', 'Safety'],
      project_slugs: ['hys'],
      detail_fields: fields
    }))
    const wrapper = mount(WatcherSettings)
    await flushPromises()
    expect(wrapper.findAllComponents(NSelect)[0].props('options')).toEqual([
      { label: 'Hydraulics', value: 'component:Hydraulics' },
      { label: 'Safety', value: 'component:Safety' },
      { label: 'None', value: 'none' }
    ])
    wrapper.findAllComponents(NSelect)[0].vm.$emit('update:value', 'none')
    await flushPromises()
    await button(wrapper, 'Save detail fields').trigger('click')
    await flushPromises()
    expect(api.update).toHaveBeenLastCalledWith(
      expect.objectContaining({ record_id: 'three', component_name: null })
    )
    wrapper.unmount()
  })
  it('loads unknown legacy components rather than mistaking them for None', async () => {
    api.records.mockResolvedValue({ results: [record('one', null)], pagination: { next: null } })
    const wrapper = mount(WatcherSettings)
    await flushPromises()
    expect(wrapper.findAllComponents(NSelect)[0].props('options')).toEqual([
      { label: 'Hydraulics', value: 'component:Hydraulics' }
    ])
    wrapper.unmount()
  })
  it('reports an empty tracked list without offering unrelated projects', async () => {
    api.records.mockResolvedValue({ results: [], pagination: { next: null } })
    const wrapper = mount(WatcherSettings)
    await flushPromises()
    expect(wrapper.findAllComponents(NSelect)[0].props('options')).toEqual([])
    expect(wrapper.text()).toContain('No tracked issues')
    expect(button(wrapper, 'Save detail fields').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
  it('keeps saving disabled after a load error and retries without duplicating earlier pages', async () => {
    api.records
      .mockResolvedValueOnce({
        results: [record('one', ['Hydraulics'])],
        pagination: { next: '?page=2' }
      })
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({
        results: [record('one', ['Hydraulics'])],
        pagination: { next: '?page=2' }
      })
      .mockResolvedValueOnce({ results: [record('two', ['Safety'])], pagination: { next: null } })
    const wrapper = mount(WatcherSettings)
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(button(wrapper, 'Save detail fields').attributes('disabled')).toBeDefined()
    await button(wrapper, 'Retry loading components').trigger('click')
    await flushPromises()
    expect(wrapper.findAllComponents(NSelect)[0].props('options')).toHaveLength(2)
    wrapper.unmount()
  })
  it('ignores stale field discovery when a different component is selected', async () => {
    api.records.mockResolvedValue({
      results: [record('one', ['Hydraulics']), record('two', ['Safety'])],
      pagination: { next: null }
    })
    let resolveOld!: (value: unknown) => void
    api.status.mockImplementation((id) =>
      id === 'one'
        ? new Promise((resolve) => {
            resolveOld = resolve
          })
        : Promise.resolve({
            components: ['Safety'],
            detail_fields: [fields[0]],
            project_slugs: ['hys']
          })
    )
    const wrapper = mount(WatcherSettings)
    await flushPromises()
    wrapper.findAllComponents(NSelect)[0].vm.$emit('update:value', 'component:Safety')
    await flushPromises()
    resolveOld({ components: ['Hydraulics'], detail_fields: [fields[1]], project_slugs: ['hys'] })
    await flushPromises()
    expect(wrapper.findAllComponents(NSelect)[1].props('options')).toEqual([
      { label: 'Priority', value: 'priority' }
    ])
    wrapper.unmount()
  })
})

it('publishes the newly synchronized record version while discovering legacy components', async () => {
  api.preferences.mockResolvedValue({ outstanding_only: false, detail_fields: {} })
  api.records.mockResolvedValue({ results: [record('one', null)], pagination: { next: null } })
  api.status.mockResolvedValue({
    components: ['Hydraulics'],
    project_slugs: ['hys'],
    detail_fields: fields,
    title: 'Updated title',
    record_version: 3
  })
  const synced = vi.fn()
  const wrapper = mount(WatcherSettings, { props: { onRecordSynced: synced } })
  await flushPromises()
  expect(synced).toHaveBeenCalledWith(
    'one',
    expect.objectContaining({ title: 'Updated title', record_version: 3 })
  )
  wrapper.unmount()
})

it('uses a healthy tracked issue when the first matching issue is unavailable', async () => {
  api.preferences.mockResolvedValue({ outstanding_only: false, detail_fields: {} })
  api.records.mockResolvedValue({
    results: [record('one', ['Hydraulics']), record('two', ['Hydraulics'])],
    pagination: { next: null }
  })
  api.status.mockImplementation(async (id) => {
    if (id === 'one') throw new Error('offline')
    return { components: ['Hydraulics'], project_slugs: ['hys'], detail_fields: fields }
  })
  const wrapper = mount(WatcherSettings)
  await flushPromises()
  expect(wrapper.findAllComponents(NSelect)[1].props('options')).toHaveLength(2)
  await button(wrapper, 'Save detail fields').trigger('click')
  await flushPromises()
  expect(api.update).toHaveBeenCalledWith(expect.objectContaining({ record_id: 'two' }))
  wrapper.unmount()
})

it('keeps known components usable when one legacy record cannot load', async () => {
  api.preferences.mockResolvedValue({ outstanding_only: false, detail_fields: {} })
  api.records.mockResolvedValue({
    results: [record('one', null), record('two', ['Hydraulics'])],
    pagination: { next: null }
  })
  api.status.mockImplementation(async (id) => {
    if (id === 'one') throw new Error('offline')
    return { components: ['Hydraulics'], project_slugs: ['hys'], detail_fields: fields }
  })
  const wrapper = mount(WatcherSettings)
  await flushPromises()
  expect(wrapper.findAllComponents(NSelect)[0].props('options')).toEqual([
    { label: 'Hydraulics', value: 'component:Hydraulics' }
  ])
  expect(wrapper.findAllComponents(NSelect)[1].props('options')).toHaveLength(2)
  expect(wrapper.text()).toContain('could not be loaded')
  wrapper.unmount()
})

it('still refreshes parent record metadata after settings close during discovery', async () => {
  api.preferences.mockResolvedValue({ outstanding_only: false, detail_fields: {} })
  api.records.mockResolvedValue({
    results: [record('one', ['Hydraulics'])],
    pagination: { next: null }
  })
  let resolveStatus!: (value: unknown) => void
  api.status.mockImplementation(
    () =>
      new Promise((resolve) => {
        resolveStatus = resolve
      })
  )
  let parentVersion = 1
  const wrapper = mount(WatcherSettings, {
    props: {
      onRecordSynced: (_id, status) => {
        parentVersion = status.record_version
      }
    }
  })
  await flushPromises()
  wrapper.unmount()
  resolveStatus({
    components: ['Hydraulics'],
    project_slugs: ['hys'],
    detail_fields: fields,
    record_version: 4
  })
  await flushPromises()
  expect(parentVersion).toBe(4)
})

it('updates parent preferences when saving finishes after the modal closes', async () => {
  api.preferences.mockResolvedValue({ outstanding_only: false, detail_fields: {} })
  api.records.mockResolvedValue({
    results: [record('one', ['Hydraulics'])],
    pagination: { next: null }
  })
  api.status.mockResolvedValue({
    components: ['Hydraulics'],
    project_slugs: ['hys'],
    detail_fields: fields
  })
  let resolveSave!: (value: unknown) => void
  api.update.mockImplementation(
    () =>
      new Promise((resolve) => {
        resolveSave = resolve
      })
  )
  let parentFields: Record<string, string[]> = {}
  const wrapper = mount(WatcherSettings, {
    props: {
      onPreferencesSaved: (value: { component_fields?: Record<string, string[]> }) => {
        parentFields = value.component_fields ?? {}
      }
    }
  })
  await flushPromises()
  await button(wrapper, 'Save detail fields').trigger('click')
  wrapper.unmount()
  resolveSave({
    outstanding_only: false,
    detail_fields: {},
    component_fields: { 'component:Hydraulics': ['priority'] }
  })
  await flushPromises()
  expect(parentFields).toEqual({ 'component:Hydraulics': ['priority'] })
})
