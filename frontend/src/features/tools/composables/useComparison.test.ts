// @vitest-environment jsdom
import { defineComponent, nextTick, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Job } from '@/features/jobs/api/jobs'

const mocks = vi.hoisted(() => ({
  enqueue: vi.fn(),
  inspect: vi.fn(),
  presets: vi.fn(),
  download: vi.fn()
}))
vi.mock('@/features/tools/api/unifiedComparison', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  enqueueComparison: mocks.enqueue,
  fetchInspection: mocks.inspect,
  fetchComparisonPresets: mocks.presets
}))
const job = ref<Job | null>(null)
vi.mock('@/features/jobs/composables/usePageJob', () => ({
  usePageJob: () => ({
    job,
    active: ref(false),
    cancelling: ref(false),
    downloading: ref(false),
    errorMessage: ref(''),
    reset: () => {
      job.value = null
    },
    download: mocks.download,
    cancel: vi.fn(),
    openJobCenter: vi.fn(),
    setJob: (value: Job) => {
      job.value = value
    }
  })
}))
import { useComparison } from './useComparison'

function setup() {
  let state!: ReturnType<typeof useComparison>
  const wrapper = mount(
    defineComponent({
      setup() {
        state = useComparison()
        return () => null
      }
    })
  )
  return { state, wrapper }
}

const presets = {
  presets: [
    {
      id: 'balanced',
      label: 'Balanced',
      description: 'Everyday',
      equal_ratio: 0.92,
      weak_equal_ratio: 0.7
    }
  ],
  default: 'balanced'
}
function result(id: string, kind = 'comparison.compare', status = 'queued') {
  return { id, kind, status } as Job
}

describe('comparison flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    job.value = null
    mocks.presets.mockResolvedValue(presets)
  })
  it('blocks mixed families and clears selections on file replacement', async () => {
    const { state, wrapper } = setup()
    await flushPromises()
    state.setFile('first', new File(['a'], 'a.docx'))
    state.setFile('second', new File(['b'], 'b.pdf'))
    expect(state.canCompare.value).toBe(false)
    expect(state.fileError.value).toContain('same type')
    state.setFile('second', new File(['b'], 'b.docx'))
    expect(state.canCompare.value).toBe(true)
    wrapper.unmount()
  })
  it('automatically downloads a newly completed comparison exactly once', async () => {
    const { state, wrapper } = setup()
    await flushPromises()
    state.setFile('first', new File(['a'], 'a.docx'))
    state.setFile('second', new File(['b'], 'b.docx'))
    mocks.enqueue.mockResolvedValue(result('new-job'))
    await state.compare()
    job.value = result('new-job', 'comparison.compare', 'succeeded')
    await flushPromises()
    job.value = { ...job.value, progress: 100 }
    await flushPromises()
    expect(mocks.download).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
  it('does not automatically download a restored result', async () => {
    const { wrapper } = setup()
    job.value = result('restored', 'comparison.compare', 'succeeded')
    await flushPromises()
    expect(mocks.download).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('ignores inspection details arriving after a file replacement', async () => {
    const { state, wrapper } = setup()
    let resolve!: (value: unknown) => void
    mocks.inspect.mockReturnValue(
      new Promise((value) => {
        resolve = value
      })
    )
    job.value = result('inspection', 'comparison.inspect', 'succeeded')
    await nextTick()
    state.setFile('first', new File(['a'], 'changed.xlsx'))
    resolve({ selection: {}, matching: { requires_input: false } })
    await flushPromises()
    expect(state.inspection.value).toBeNull()
    wrapper.unmount()
  })
})
