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
vi.mock('naive-ui', () => ({
  useMessage: () => ({ warning: mocks.warning }),
  useThemeVars: () => ({ value: { textColor3: '#888' } })
}))
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
import CompDocPanelDashboard from './CompDocPanelDashboard.vue'

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
  NTab: Slot,
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

  async function dashboard(mode = 'ata') {
    const wrapper = mount(ComplianceDashboard, { global: { stubs } })
    wrappers.push(wrapper)
    await flushPromises()
    if (wrapper.findComponent(CompDocPanelDashboard).exists())
      wrapper.findComponent(CompDocPanelDashboard).vm.$emit('update:mode', mode)
    await flushPromises()
    return wrapper
  }

  it('panel focus updates every chart and risk scope, and switching modes clears focus', async () => {
    const summary = dashboardSummary()
    summary.total = 10
    summary.chart_status_counts.delayed = 10
    mocks.fetch.mockResolvedValueOnce(summary)
    const wrapper = await dashboard('panel')
    expect(wrapper.findAll('tr')).toHaveLength(1)
    await wrapper.findAll('tr')[0].trigger('dblclick')
    expect(wrapper.findComponent({ name: 'DoughnutChart' }).props('data').datasets[0].data).toEqual(
      [3]
    )
    expect(wrapper.findComponent({ name: 'LineChart' }).props('data').datasets[1].data[0].y).toBe(3)
    expect(wrapper.findComponent({ name: 'BarChart' }).props('data').datasets[0].data).toEqual([
      0, 20, 0
    ])
    expect(
      wrapper.findComponent(CompDocTimelineDashboard).props('performance').scheduled.filled
    ).toBe(3)
    expect(wrapper.findComponent(CompDocRiskDashboard).props('risk').at_risk_count).toBe(3)
    expect(wrapper.findAll('tr')[0].attributes('aria-selected')).toBe('true')
    expect(mocks.fetch).toHaveBeenCalledTimes(1)
    wrapper.findComponent(CompDocPanelDashboard).vm.$emit('update:mode', 'ata')
    await flushPromises()
    expect(wrapper.findAll('tr')).toHaveLength(2)
    expect(wrapper.findComponent(CompDocTimelineDashboard).props('documentCount')).toBe(10)
    await wrapper.findAll('tr')[0].trigger('dblclick')
    expect(wrapper.findComponent(CompDocTimelineDashboard).props('documentCount')).toBe(1)
  })

  it('groups issued workflow states separately from unissued deadlines and scopes MoC', async () => {
    const summary = dashboardSummary()
    Reflect.set(summary, 'publication', {
      issued: { total: 1, status_counts: { authority_review: 1 } },
      not_issued: { total: 2, status_counts: { expected: 1, missing_target: 1 } }
    })
    Reflect.set(summary, 'unissued_moc_counts', { '1': 1, '': 1 })
    mocks.fetch.mockResolvedValueOnce(summary)
    const wrapper = await dashboard()
    const groups = wrapper.findAll('.publication-group')
    expect(groups).toHaveLength(2)
    expect(groups[0].text()).toContain('Issued')
    expect(groups[0].text()).toContain('Authority Review')
    expect(groups[1].text()).toContain('Expected')
    expect(groups[1].text()).toContain('Target date missing')
    const moc = wrapper.find('.moc-distribution')
    expect(moc.text()).toContain('Not issued by MoC')
    expect(moc.text()).toContain('Unspecified')
    expect(moc.findAll('.moc-row').map((row) => row.text())).toEqual([
      'MoC 1150%',
      'Unspecified150%'
    ])
    await wrapper.findAll('tr')[0].trigger('dblclick')
    expect(moc.findAll('.moc-row').map((row) => row.text())).toEqual(['Unspecified1100%'])
  })

  it('shows CAT counts and percentages below status and keeps risks outside the charts', async () => {
    const summary = dashboardSummary()
    Reflect.set(summary, 'cat_counts', { A: 2, B: 1 })
    Reflect.set(summary.panels[0].analytics, 'cat_counts', { A: 1 })
    mocks.fetch.mockResolvedValueOnce(summary)
    const wrapper = await dashboard()
    const cards = wrapper.find('.dashboard-column').findAll('.dashboard-card')
    expect(cards).toHaveLength(2)
    expect(cards[1].text()).toContain('Document CAT')
    expect(cards[1].findAll('.status-row').map((row) => row.text())).toEqual(['A267%', 'B133%'])
    expect(wrapper.find('.dashboard-grid .risk-card').exists()).toBe(false)
    expect(
      wrapper.find('.dashboard-grid').element.nextElementSibling?.classList.contains('risk-card')
    ).toBe(true)
    await wrapper.findAll('tr')[0].trigger('dblclick')
    expect(
      wrapper.findAllComponents({ name: 'DoughnutChart' })[1].props('data').datasets[0].data
    ).toEqual([1])
    expect(cards[1].text()).toContain('100%')
  })

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

  it('includes missing CAT in percentages and handles an empty distribution', async () => {
    const summary = dashboardSummary()
    summary.cat_counts = { '': 1, B: 2 }
    mocks.fetch.mockResolvedValueOnce(summary)
    const wrapper = await dashboard()
    const catCard = () => wrapper.find('.dashboard-column').findAll('.dashboard-card')[1]
    expect(
      catCard()
        .findAll('.status-row')
        .map((row) => row.text())
    ).toEqual(['B267%', 'Unspecified133%'])
    mocks.fetch.mockResolvedValueOnce({ ...summary, cat_counts: {} })
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Refresh')!
      .trigger('click')
    await flushPromises()
    expect(catCard().findAll('.status-row')).toHaveLength(0)
    expect(catCard().findComponent({ name: 'DoughnutChart' }).exists()).toBe(false)
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

  it('refreshes focused panel groups and clears groups that disappear', async () => {
    const wrapper = await dashboard('panel')
    await wrapper.findAll('tr')[0].trigger('dblclick')
    const updated = dashboardSummary()
    updated.panel_groups[0].ata = '27, 28, 29'
    updated.panel_groups[0].analytics.total = 4
    mocks.fetch.mockResolvedValueOnce(updated)
    const refresh = () =>
      wrapper
        .findAll('button')
        .find((button) => button.text() === 'Refresh')!
        .trigger('click')
    await refresh()
    await flushPromises()
    expect(wrapper.findComponent(CompDocTimelineDashboard).props('documentCount')).toBe(4)
    expect(wrapper.findAll('tr')[0].text()).toContain('27, 28, 29')
    mocks.fetch.mockResolvedValueOnce({ ...updated, panel_groups: [] })
    await refresh()
    await flushPromises()
    expect(wrapper.findComponent(CompDocTimelineDashboard).props('documentCount')).toBe(3)
  })
})
