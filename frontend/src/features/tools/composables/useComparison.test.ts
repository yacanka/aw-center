// @vitest-environment jsdom
import { computed, defineComponent, nextTick, ref } from 'vue'
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
    active: computed(() =>
      ['queued', 'running', 'cancel_requested'].includes(job.value?.status || '')
    ),
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
  it.each(['failed', 'cancelled'])(
    'creates a fresh attempt after a %s comparison',
    async (status) => {
      const { state, wrapper } = setup()
      await flushPromises()
      state.setFile('first', new File(['a'], 'a.docx'))
      state.setFile('second', new File(['b'], 'b.docx'))
      mocks.enqueue.mockResolvedValueOnce(result('first')).mockResolvedValueOnce(result('second'))
      await state.compare()
      job.value = result('first', 'comparison.compare', status)
      await state.compare()
      expect(mocks.enqueue).toHaveBeenCalledTimes(2)
      expect(mocks.enqueue.mock.calls[1][3]).not.toBe(mocks.enqueue.mock.calls[0][3])
      expect(state.job.value?.id).toBe('second')
      wrapper.unmount()
    }
  )

  it('retains the attempt key when an enqueue response is lost', async () => {
    const { state, wrapper } = setup()
    await flushPromises()
    state.setFile('first', new File(['a'], 'a.docx'))
    state.setFile('second', new File(['b'], 'b.docx'))
    mocks.enqueue
      .mockRejectedValueOnce(new Error('response lost'))
      .mockResolvedValueOnce(result('accepted'))
    await state.compare()
    await state.compare()
    expect(mocks.enqueue).toHaveBeenCalledTimes(2)
    expect(mocks.enqueue.mock.calls[1][3]).toBe(mocks.enqueue.mock.calls[0][3])
    expect(state.job.value?.id).toBe('accepted')
    wrapper.unmount()
  })

  it('does not reuse an uncertain attempt for different input', async () => {
    const { state, wrapper } = setup()
    await flushPromises()
    state.setFile('first', new File(['a'], 'a.docx'))
    state.setFile('second', new File(['b'], 'b.docx'))
    mocks.enqueue
      .mockRejectedValueOnce(new Error('response lost'))
      .mockResolvedValueOnce(result('new-input'))
    await state.compare()
    state.setFile('second', new File(['c'], 'c.docx'))
    await state.compare()
    expect(mocks.enqueue.mock.calls[1][3]).not.toBe(mocks.enqueue.mock.calls[0][3])
    wrapper.unmount()
  })
})
