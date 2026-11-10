// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { expect, it, vi } from 'vitest'
import { NFormItemGi, NSelect } from 'naive-ui'
import { NAIVE_UI_COMPONENTS } from '@/app/plugins/naiveUi'
import { NAIVE_UI_FEATURE_COMPONENTS } from '@/app/plugins/naiveUiFeatures'
import { createEmptyCompdoc } from '../api/compdocCatalog'
import CompDocIdentityFields from './CompDocIdentityFields.vue'

vi.mock('@/features/compliance/composables/compdocController', () => ({
  useCompdocController: () => ({
    getPanels: [
      { id: 1, name: 'Systems', ata: '27-00' },
      { id: 2, name: 'Systems', ata: '28-00' },
      { id: 3, name: 'Structures', ata: '53-00' }
    ],
    getPanelOptions: [],
    getSignaturePanelOptions: []
  })
}))

it('edits Panel and ATA separately, limits ATA choices and clears incompatible selections', async () => {
  const compdoc = { ...createEmptyCompdoc(), panel: 1, panel_name: 'Systems', ata: '27-00' }
  const wrapper = mount(CompDocIdentityFields, {
    props: { compdoc, original: { ...compdoc }, readonly: false },
    global: {
      components: {
        NFormItemGi,
        ...Object.fromEntries(
          [...NAIVE_UI_COMPONENTS, ...NAIVE_UI_FEATURE_COMPONENTS].map((component) => [
            `N${component.name}`,
            component
          ])
        )
      }
    }
  })
  try {
    const field = (path: string) =>
      wrapper
        .findAllComponents(NFormItemGi)
        .find((item) => item.props('path') === path)!
        .findComponent(NSelect)
    const panel = field('panel')
    const ata = field('ata')
    expect(ata.exists()).toBe(true)
    expect(panel.props('options')).toEqual([
      { label: 'Structures', value: 'Structures' },
      { label: 'Systems', value: 'Systems' }
    ])
    expect(ata.props('options')).toEqual([
      { label: '27-00', value: '27-00' },
      { label: '28-00', value: '28-00' }
    ])
    ata.vm.$emit('update:value', '28-00')
    await wrapper.vm.$nextTick()
    expect(compdoc.panel).toBe(2)
    expect(compdoc.ata).toBe('28-00')
    panel.vm.$emit('update:value', 'Structures')
    await wrapper.vm.$nextTick()
    expect(compdoc.ata).toBeNull()
    expect(compdoc.panel).toBeNull()
    expect(ata.props('options')).toEqual([{ label: '53-00', value: '53-00' }])
    ata.vm.$emit('update:value', '27-00')
    await wrapper.vm.$nextTick()
    expect(compdoc.panel).toBeNull()
    expect(compdoc.ata).toBeNull()
    ata.vm.$emit('update:value', '53-00')
    await wrapper.vm.$nextTick()
    expect(compdoc.panel).toBe(3)
    await wrapper.setProps({ readonly: true })
    expect(ata.props('disabled')).toBe(true)
    expect(panel.props('disabled')).toBe(true)
  } finally {
    wrapper.unmount()
  }
})
