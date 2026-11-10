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
  useThemeVars: () => ({ value: { textColor3: '#888', cardColor: '#fff' } })
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
import CompDocStatusDashboard from './CompDocStatusDashboard.vue'

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
    name: 'NTag',
    props: ['color', 'type'],
    emits: ['close'],
    template: '<span><slot /><button @click="$emit(\'close\')">Clear scope</button></span>'
  },
  NButton: { template: '<button><slot /></button>' },
  NSelect: {
    name: 'NSelect',
    props: ['value', 'options'],
    emits: ['update:value'],
    template: '<select />'
  },
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

  it('uses the same positive rows for explicit legends and publication chart arcs', async () => {
    const rows = [
      { value: 'custom', label: 'Project review', color: '#888', count: 2, percentage: 100 },
      { value: 'unused', label: 'Unused', color: '#888', count: 0, percentage: 0 }
    ]
    const wrapper = mount(CompDocStatusDashboard, {
      props: { counts: {}, rows },
      global: { stubs }
    })
    wrappers.push(wrapper)
    expect(wrapper.findAll('.status-row').map((row) => row.text())).toEqual(['Project review2100%'])
    await wrapper.setProps({
      groups: [
        { label: 'Issued', total: 2, rows },
        { label: 'Not issued', total: 0, rows: rows.slice(1) }
      ]
    })
    expect(wrapper.findAll('.status-row')).toHaveLength(1)
    expect(wrapper.findComponent({ name: 'DoughnutChart' }).props('data').labels).toEqual([
      'Issued: Project review'
    ])
    expect(wrapper.findAll('.publication-group')[1].text()).toContain('No documents')
    await wrapper.setProps({ groups: [{ label: 'Issued', total: 0, rows: rows.slice(1) }] })
    expect(wrapper.findAll('.status-row')).toHaveLength(0)
    expect(wrapper.findComponent({ name: 'DoughnutChart' }).exists()).toBe(false)
  })

  it('hides pending days while keeping burndown, flow metrics and the API data', async () => {
    const wrapper = await dashboard()
    const timeline = wrapper.findComponent(CompDocTimelineDashboard)
    expect(timeline.text()).toContain('Schedule and delivery burndown')
    expect(timeline.find('.metric-card').exists()).toBe(true)
    expect(timeline.text()).not.toContain('Accumulated pending days')
    expect(timeline.findComponent({ name: 'BarChart' }).exists()).toBe(false)
    expect(timeline.props('pendingDays')).toEqual({ authority: 0, ubm: 20, aw: 0 })
  })

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
    expect(
      Object.values(wrapper.findComponent(CompDocTimelineDashboard).props('pendingDays'))
    ).toEqual([0, 20, 0])
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
    expect(groups[1].text()).toContain('In Design')
    expect(groups[1].text()).toContain('In Design (date missing)')
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

  it('double-click updates doughnut, burndown, retained pending data, performance and risk together', async () => {
    const wrapper = await dashboard()
    await wrapper.findAll('tr')[0].trigger('dblclick')
    expect(wrapper.findComponent({ name: 'DoughnutChart' }).props('data').datasets[0].data).toEqual(
      [1]
    )
    expect(wrapper.findComponent({ name: 'LineChart' }).props('data').datasets[1].data[0].y).toBe(1)
    expect(
      Object.values(wrapper.findComponent(CompDocTimelineDashboard).props('pendingDays'))
    ).toEqual([0, 3, 0])
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
    expect(
      Object.values(wrapper.findComponent(CompDocTimelineDashboard).props('pendingDays'))
    ).toEqual([0, 20, 0])
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

  it('shows four risk levels, filters very-high priorities and counts zero-score documents as low', async () => {
    const summary = dashboardSummary()
    summary.risk.counts = { very_high: 1, high: 1, medium: 1, low: 2 }
    summary.risk.at_risk_count = 4
    const source = summary.risk.priorities[0]
    summary.risk.priorities = (['very_high', 'high', 'medium', 'low'] as const).map(
      (level, index) => ({
        ...source,
        document_id: `priority-${index}`,
        name: `Priority ${index}`,
        level,
        score: [90, 70, 30, 20][index]
      })
    )
    const risk = mount(CompDocRiskDashboard, {
      props: { project: 'ozgur', risk: summary.risk },
      global: { stubs }
    })
    wrappers.push(risk)
    expect(
      risk
        .findAll('.summary-item')
        .slice(0, 4)
        .map((item) => item.text())
    ).toEqual(['Very high1', 'High1', 'Medium1', 'Low2'])
    expect(risk.text()).not.toContain('No signals')
    expect(risk.text()).toContain('only positive scores enter the priority list')
    const headers = risk.findAll('.priority-header')
    expect(headers).toHaveLength(4)
    const colors = headers.map((header) => header.findComponent({ name: 'NTag' }).props('color'))
    expect(new Set(colors.map((color) => color.color)).size).toBe(4)
    const select = risk.findComponent(stubs.NSelect)
    expect(select.props('options').map((option: { value: string }) => option.value)).toEqual([
      'all',
      'very_high',
      'high',
      'medium',
      'low'
    ])
    select.vm.$emit('update:value', 'very_high')
    await flushPromises()
    expect(risk.findAll('.priority-header')).toHaveLength(1)
    expect(risk.find('.priority-header').text()).toContain('Priority 0')
    summary.risk = {
      ...summary.risk,
      at_risk_count: 0,
      priorities: [],
      counts: { very_high: 0, high: 0, medium: 0, low: 5 }
    }
    await risk.setProps({ risk: summary.risk })
    expect(risk.findAll('.summary-item')[3].text()).toBe('Low5')
    expect(risk.findAll('.priority-header')).toHaveLength(0)
    expect(risk.findComponent({ name: 'NEmpty' }).attributes('description')).toBe(
      'No active risk signals.'
    )
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
    const tabs = wrapper.findComponent(stubs.NSelect)
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
