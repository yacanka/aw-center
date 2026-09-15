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
async function setup(documents = ref<{ ata: string | null; moc: string | null }[]>([])) {
  const format = ref<string | null>('CP')
  let state!: ReturnType<typeof useNumberingContext>
  wrappers.push(
    mount(
      defineComponent({
        setup() {
          state = useNumberingContext(ref('ozgur'), format, ref(true), undefined, documents)
          return () => h('div')
        }
      })
    )
  )
  await flushPromises()
  return { state, format }
}
describe('format context fields', () => {
  it('fills exact document keywords and follows document edits without changing other fields', async () => {
    fetchFormat.mockResolvedValue({
      fields: ['ata', 'moc', 'ATA', 'ata_chapter'].map((key) => ({
        key,
        required: true,
        default: null,
        max_length: 5
      }))
    })
    const documents = ref([{ ata: '27-00', moc: '0' }])
    const { state } = await setup(documents)
    expect(state.displayValues.value).toEqual({ ata: '2700', moc: '0', ATA: '', ata_chapter: '' })
    expect(state.valid.value).toBe(false)
    state.values.value.ATA = 'other'
    state.values.value.ata_chapter = 'other'
    expect(state.valid.value).toBe(true)
    documents.value[0].ata = '28-00'
    expect(state.payload.value.ata).toBe('2800')
    documents.value[0].ata = '05-10'
    expect(state.payload.value.ata).toBe('0510')
    expect(documents.value[0].ata).toBe('05-10')
    documents.value[0].moc = ''
    expect(state.valid.value).toBe(false)
  })

  it('validates required document values and maximum lengths across all selected documents', async () => {
    fetchFormat.mockResolvedValue({
      fields: [{ key: 'ata', required: true, default: null, max_length: 4 }]
    })
    const documents = ref([
      { ata: '27-00', moc: null },
      { ata: '', moc: null }
    ])
    const { state } = await setup(documents)
    expect(state.valid.value).toBe(false)
    documents.value[1].ata = '28-00'
    expect(state.valid.value).toBe(true)
    documents.value[1].ata = 'too-long'
    expect(state.valid.value).toBe(false)
  })

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
