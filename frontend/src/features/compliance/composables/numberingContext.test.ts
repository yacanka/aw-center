// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
const fetchFormat = vi.hoisted(() => vi.fn())
vi.mock('../api/compdocNumbering', () => ({ fetchNumberingFormat: fetchFormat }))
import { useNumberingContext } from './numberingContext'
import NumberingContextFields from '../components/NumberingContextFields.vue'
const fields = [
  { key: 'department', required: false, default: 'GEN', max_length: 10 },
  { key: 'branch', required: true, default: null, max_length: 3 }
]
const wrappers: ReturnType<typeof mount>[] = []
beforeEach(() => {
  vi.resetAllMocks()
  fetchFormat.mockResolvedValue({ code: 'CP', fields })
})
afterEach(() => wrappers.splice(0).forEach((wrapper) => wrapper.unmount()))
async function setup() {
  const format = ref<string | null>('CP')
  let state!: ReturnType<typeof useNumberingContext>
  wrappers.push(
    mount(
      defineComponent({
        setup() {
          state = useNumberingContext(ref('ozgur'), format, ref(true))
          return () => h('div')
        }
      })
    )
  )
  await flushPromises()
  return { state, format }
}
describe('format context fields', () => {
  it('requires mandatory values and preserves optional defaults without silently substituting user input', async () => {
    const { state } = await setup()
    expect(state.valid.value).toBe(false)
    expect(state.fields.value[0].default).toBe('GEN')
    state.values.value.branch = 'IST'
    expect(state.valid.value).toBe(true)
    expect(state.payload.value).toEqual({ branch: 'IST' })
    state.values.value.department = 'ENG'
    expect(state.payload.value).toEqual({ department: 'ENG', branch: 'IST' })
    state.values.value.branch = 'TOO LONG'
    expect(state.valid.value).toBe(false)
  })
  it('clears old values and ignores late responses when the format changes', async () => {
    const { state, format } = await setup()
    let finish!: (value: unknown) => void
    fetchFormat.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve
        })
    )
    format.value = 'SLOW'
    await flushPromises()
    fetchFormat.mockResolvedValue({ code: 'NEXT', fields: [] })
    format.value = 'NEXT'
    await flushPromises()
    finish({ code: 'SLOW', fields })
    await flushPromises()
    expect(state.fields.value).toEqual([])
    expect(state.values.value).toEqual({})
    expect(state.valid.value).toBe(true)
  })
  it('renders default hints, required inputs and entered values', async () => {
    const wrapper = mount(NumberingContextFields, {
      props: {
        fields,
        values: { department: '', branch: '' },
        loading: false,
        error: '',
        disabled: false,
        idPrefix: 'test-context'
      }
    })
    wrappers.push(wrapper)
    expect(wrapper.text()).toContain('Default: GEN')
    expect(wrapper.find('#test-context-0').attributes('placeholder')).toBe('GEN')
    expect(wrapper.find('#test-context-1').attributes('required')).toBeDefined()
    await wrapper.find('#test-context-0').setValue('ENG')
    expect(wrapper.emitted('update:values')?.[0]).toEqual([{ department: 'ENG', branch: '' }])
  })
})
