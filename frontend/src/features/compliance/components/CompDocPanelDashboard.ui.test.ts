// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'
import { NCard, NConfigProvider, NDataTable, NTab, NTabs, NText } from 'naive-ui'
import { dashboardAnalytics, dashboardSummary } from '../models/compdocDashboard.fixtures'
import CompDocPanelDashboard from './CompDocPanelDashboard.vue'

const wrappers: ReturnType<typeof mount>[] = []
afterEach(() => wrappers.splice(0).forEach((wrapper) => wrapper.unmount()))

const ThemedCard = defineComponent({
  setup:
    (_, { attrs, slots }) =>
    () =>
      h(NConfigProvider, null, { default: () => h(NCard, attrs, slots) })
})

function dashboard(
  panels = [
    { id: 'panel:Systems', panel: 'Systems', ata: '27, 28', analytics: dashboardAnalytics() }
  ]
) {
  const wrapper = mount(CompDocPanelDashboard, {
    props: { loading: false, panels },
    global: { components: { NCard: ThemedCard, NDataTable, NTab, NTabs, NText } }
  })
  wrappers.push(wrapper)
  return wrapper
}

async function panelMode(wrapper: ReturnType<typeof dashboard>) {
  const tab = wrapper.findAll('[role="tab"]').find((item) => item.text() === 'Panel based')
  expect(tab).toBeDefined()
  await tab!.trigger('click')
  await flushPromises()
}

it('defaults to panel rows and places the mode tabs immediately above the table', () => {
  const wrapper = dashboard()
  expect(wrapper.findComponent(NTabs).exists()).toBe(true)
  expect(wrapper.findComponent(NTabs).props('value')).toBe('panel')
  expect(wrapper.findAll('[role="tab"]').map((tab) => tab.text())).toEqual([
    'Panel based',
    'ATA based'
  ])
  expect(wrapper.findComponent(NDataTable).props('data')?.[0].ata).toBe('27, 28')
  expect(wrapper.findComponent(NTabs).element.nextElementSibling).toBe(
    wrapper.findComponent(NDataTable).element
  )
})

it('renders grouped analytics and updates rows on refresh', async () => {
  const wrapper = dashboard()
  await panelMode(wrapper)
  expect(wrapper.find('tbody').text()).toContain('27, 28')
  await wrapper.setProps({
    panels: [
      { id: 'panel:Unassigned', panel: 'Unassigned', ata: '', analytics: dashboardAnalytics(1) }
    ]
  })
  expect(wrapper.findComponent(NDataTable).props('data')?.[0].ata).toBe('')
  await wrapper.setProps({ panels: [] })
  expect(wrapper.findComponent(NDataTable).props('data')).toEqual([])
})

it('supports row focus in both panel and ATA modes', async () => {
  const wrapper = dashboard()
  await wrapper.setProps({ selectedPanel: 'panel:Systems' })
  await panelMode(wrapper)
  await wrapper.find('tbody tr').trigger('dblclick')
  expect(wrapper.emitted('select')?.[0]?.[0]).toMatchObject({ id: 'panel:Systems', ata: '27, 28' })
  await wrapper
    .findAll('[role="tab"]')
    .find((item) => item.text() === 'ATA based')!
    .trigger('click')
  await flushPromises()
  await wrapper.setProps({ panels: dashboardSummary().panels, selectedPanel: 'panel-1' })
  expect(wrapper.find('tbody tr').attributes('aria-selected')).toBe('true')
  await wrapper.find('tbody tr').trigger('keydown', { key: 'Enter' })
  expect(wrapper.emitted('select')?.[1]).toEqual([dashboardSummary().panels[0]])
})
