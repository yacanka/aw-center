// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, type PropType } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { DashboardPanel } from '../models/compdocDashboard'
import { dashboardSummary } from '../models/compdocDashboard.fixtures'

const mocks = vi.hoisted(() => ({ fetch: vi.fn(), load: vi.fn(), push: vi.fn(), warning: vi.fn() }))
vi.mock('@/features/compliance/api/compdocDashboard', () => ({
  fetchCompdocDashboard: mocks.fetch
}))
vi.mock('@/features/projects/stores/projectCatalog', () => ({
  useProjectCatalogStore: () => ({
    load: mocks.load,
    complianceProjects: [
      { name: 'OZGUR', slug: 'ozgur' },
      { name: 'AESA', slug: 'aesa' }
    ]
  })
}))
vi.mock('@/features/session/stores/session', () => ({
  useSessionStore: () => ({ getPreferences: { theme: 'light' } })
}))
vi.mock('naive-ui', () => ({ useMessage: () => ({ warning: mocks.warning }) }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: mocks.push }) }))
vi.mock('vue-chartjs', () => {
  function chart(name: string) {
    return defineComponent({
      name,
      props: ['data', 'options', 'plugins'],
      render: () => h('canvas')
    })
  }
  return { Doughnut: chart('DoughnutChart'), Line: chart('LineChart'), Bar: chart('BarChart') }
})

import ComplianceDashboard from './ComplianceDashboard.vue'
import CompDocTimelineDashboard from './CompDocTimelineDashboard.vue'
import CompDocRiskDashboard from './CompDocRiskDashboard.vue'

const Slot = { template: '<div><slot name="header" /><slot /></div>' }
const Table = defineComponent({
  props: {
    data: { type: Array as PropType<DashboardPanel[]>, required: true },
    rowProps: { type: Function as PropType<(row: DashboardPanel) => object>, required: true }
  },
  setup: (props) => () =>
    h(
      'table',
      props.data.map((row) =>
        h('tr', { ...props.rowProps(row), key: row.id }, [h('td', `${row.panel} ${row.ata}`)])
      )
    )
})
const stubs = {
  NTabs: { props: ['value'], emits: ['update:value'], template: '<div><slot /></div>' },
  NTabPane: true,
  NSpin: Slot,
  NEmpty: true,
  NGrid: Slot,
  NGi: Slot,
  NStatistic: true,
  NAlert: Slot,
  NFlex: Slot,
  NText: Slot,
  NCard: Slot,
  NScrollbar: Slot,
  NDataTable: Table,
  NProgress: true,
  NTag: {
    emits: ['close'],
    template: '<span><slot /><button @click="$emit(\'close\')">Clear scope</button></span>'
  },
  NButton: { template: '<button><slot /></button>' },
  NSelect: true,
  NCollapse: Slot,
  NCollapseItem: Slot
}

describe('compliance dashboard scope', () => {
  const wrappers: ReturnType<typeof mount>[] = []
  beforeEach(() => {
    vi.resetAllMocks()
    localStorage.clear()
    mocks.load.mockResolvedValue(undefined)
    mocks.fetch.mockImplementation(async (project) => dashboardSummary(project))
  })
  afterEach(() => wrappers.splice(0).forEach((wrapper) => wrapper.unmount()))

  async function dashboard() {
    const wrapper = mount(ComplianceDashboard, { global: { stubs } })
    wrappers.push(wrapper)
    await flushPromises()
    return wrapper
  }

  it('double-click updates doughnut, burndown, bars, performance and risk together', async () => {
    const wrapper = await dashboard()
    await wrapper.findAll('tr')[0].trigger('dblclick')
    expect(wrapper.findComponent({ name: 'DoughnutChart' }).props('data').datasets[0].data).toEqual(
      [1]
    )
    expect(wrapper.findComponent({ name: 'LineChart' }).props('data').datasets[1].data[0].y).toBe(1)
    expect(wrapper.findComponent({ name: 'BarChart' }).props('data').datasets[0].data).toEqual([
      0, 3, 0
    ])
    expect(
      wrapper.findComponent(CompDocTimelineDashboard).props('performance').scheduled.filled
    ).toBe(1)
    expect(wrapper.findComponent(CompDocRiskDashboard).props('risk').at_risk_count).toBe(1)
    expect(mocks.fetch).toHaveBeenCalledTimes(1)

    await wrapper.findAll('tr')[0].trigger('dblclick')
    expect(wrapper.findComponent({ name: 'DoughnutChart' }).props('data').datasets[0].data).toEqual(
      [3]
    )
    expect(wrapper.findComponent({ name: 'LineChart' }).props('data').datasets[1].data[0].y).toBe(3)
    expect(wrapper.findComponent({ name: 'BarChart' }).props('data').datasets[0].data).toEqual([
      0, 20, 0
    ])
    expect(wrapper.findComponent(CompDocRiskDashboard).props('risk').at_risk_count).toBe(3)
  })

  it('distinguishes equal panel names and supports keyboard selection and clear', async () => {
    const wrapper = await dashboard()
    await wrapper.findAll('tr')[0].trigger('dblclick')
    await wrapper.findAll('tr')[1].trigger('keydown', { key: 'Enter' })
    expect(wrapper.findAll('tr')[1].attributes('aria-selected')).toBe('true')
    expect(wrapper.findComponent(CompDocTimelineDashboard).props('documentCount')).toBe(2)
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Clear scope')!
      .trigger('click')
    expect(wrapper.findComponent(CompDocTimelineDashboard).props('documentCount')).toBe(3)
  })

  it('opens the exact risk document by identifier', async () => {
    const wrapper = await dashboard()
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Review document')!
      .trigger('click')
    expect(mocks.push).toHaveBeenCalledWith({
      name: 'compdocs',
      params: { project: 'ozgur' },
      query: { document: dashboardSummary().risk.priorities[0].document_id }
    })
  })

  it('clears old project charts and ignores stale responses during quick tab changes', async () => {
    const wrapper = await dashboard()
    await wrapper.findAll('tr')[0].trigger('dblclick')
    let resolveOld!: (value: ReturnType<typeof dashboardSummary>) => void
    mocks.fetch.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOld = resolve
        })
    )
    const tabs = wrapper.findComponent(stubs.NTabs)
    tabs.vm.$emit('update:value', 'aesa')
    await flushPromises()
    expect(wrapper.findComponent(CompDocTimelineDashboard).exists()).toBe(false)
    tabs.vm.$emit('update:value', 'ozgur')
    await flushPromises()
    expect(wrapper.findComponent(CompDocTimelineDashboard).props('documentCount')).toBe(3)
    resolveOld(dashboardSummary('aesa'))
    await flushPromises()
    expect(wrapper.findComponent(CompDocRiskDashboard).props('project')).toBe('ozgur')
  })

  it('shows errors and retries without displaying stale analytics', async () => {
    mocks.fetch.mockRejectedValueOnce(new Error('Unavailable'))
    const wrapper = await dashboard()
    expect(wrapper.findComponent(CompDocTimelineDashboard).exists()).toBe(false)
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Retry')!
      .trigger('click')
    await flushPromises()
    expect(wrapper.findComponent(CompDocTimelineDashboard).props('documentCount')).toBe(3)
  })

  it('preserves selection on refresh and clears it if the panel disappears', async () => {
    const wrapper = await dashboard()
    await wrapper.findAll('tr')[0].trigger('dblclick')
    const refresh = () =>
      wrapper
        .findAll('button')
        .find((button) => button.text() === 'Refresh')!
        .trigger('click')
    await refresh()
    await flushPromises()
    expect(wrapper.findComponent(CompDocTimelineDashboard).props('documentCount')).toBe(1)
    const updated = dashboardSummary()
    updated.panels = []
    mocks.fetch.mockResolvedValueOnce(updated)
    await refresh()
    await flushPromises()
    expect(wrapper.findComponent(CompDocTimelineDashboard).props('documentCount')).toBe(3)
  })
})
