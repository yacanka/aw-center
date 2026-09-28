// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import { NFormItemGi, NInput } from 'naive-ui'
import { NAIVE_UI_COMPONENTS } from '@/app/plugins/naiveUi'
import { NAIVE_UI_FEATURE_COMPONENTS } from '@/app/plugins/naiveUiFeatures'
import { createEmptyCompdoc } from '../api/compdocCatalog'
import CompDocReferenceFields from './CompDocReferenceFields.vue'

it('edits Cat as free text and preserves the read-only and changed states', async () => {
  const compdoc = createEmptyCompdoc()
  const wrapper = mount(CompDocReferenceFields, {
    props: { compdoc, original: { ...compdoc }, readonly: false, hasExtraFields: false },
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
    const field = wrapper
      .findAllComponents(NFormItemGi)
      .find((item) => item.props('path') === 'cat')!
    const input = field.findComponent(NInput)
    expect(input.exists()).toBe(true)
    await input.find('input').setValue('Custom cat')
    expect(compdoc.cat).toBe('Custom cat')
    await wrapper.setProps({ readonly: true })
    expect(input.props('status')).toBe('warning')
    expect(input.find('input').attributes('readonly')).toBeDefined()
    expect(input.find('input').attributes('maxlength')).toBe('12')
  } finally {
    wrapper.unmount()
  }
})
