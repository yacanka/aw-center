// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { NButton, NInput, NPagination } from 'naive-ui'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ICompDoc } from '@/features/compliance/models/compdocs'
import type { CompdocReview } from '@/features/compliance/api/compdocLifecycle'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/shared/api/http', () => ({ apiClient: http }))
import CompDocReviewPanel from './CompDocReviewPanel.vue'

const Slot = { template: '<div><slot /></div>' }
const pending: CompdocReview = {
  id: 'old-pending',
  kind: 'review',
  status: 'pending',
  assignee: 2,
  assignee_username: 'reviewer',
  due_date: null,
  request_note: 'Old pending evidence',
  decision_note: '',
  requested_by_username: 'requester',
  decided_by_username: '',
  source_version: 1,
  created_at: '2026-10-01T09:00:00Z',
  allowed_actions: { approve: true, request_changes: true, cancel: false }
}
const recent = Array.from({ length: 50 }, (_, index) => ({
  ...pending,
  id: `recent-${index}`,
  status: 'approved',
  request_note: `Recent task ${index}`,
  allowed_actions: { approve: false, request_changes: false, cancel: false }
}))

describe('review task pagination', () => {
  const wrappers: ReturnType<typeof mount>[] = []
  beforeEach(() => {
    vi.resetAllMocks()
    window.$message = {
      error: vi.fn(),
      success: vi.fn(),
      warning: vi.fn()
    } as unknown as typeof window.$message
    http.get.mockImplementation(async (_url, config) => ({
      data: {
        count: 51,
        next: config?.params?.page === 2 ? null : '?page=2',
        previous: null,
        results: config?.params?.page === 2 ? [pending] : recent
      }
    }))
    http.post.mockResolvedValue({ data: { ...pending, status: 'approved' } })
  })
  afterEach(() => wrappers.splice(0).forEach((wrapper) => wrapper.unmount()))

  async function panel() {
    const wrapper = mount(CompDocReviewPanel, {
      props: {
        show: true,
        project: 'ozgur',
        document: { id: 'document-one', version: 1 } as ICompDoc,
        canEdit: false
      },
      global: {
        components: { NButton, NInput, NPagination },
        stubs: {
          NCard: Slot,
          NSpin: Slot,
          NFlex: Slot,
          NText: Slot,
          NTag: Slot,
          NSpace: Slot,
          NEmpty: Slot,
          NSelect: Slot,
          NFormItemGi: Slot,
          NDatePicker: Slot,
          NGrid: Slot
        }
      }
    })
    wrappers.push(wrapper)
    await flushPromises()
    return wrapper
  }

  it('loads bounded pages and lets the assignee decide an older pending task', async () => {
    const wrapper = await panel()
    expect(wrapper.text()).not.toContain('Old pending evidence')
    const pagination = wrapper.findComponent(NPagination)
    expect(pagination.exists()).toBe(true)
    expect(pagination.props('itemCount')).toBe(51)
    pagination.vm.$emit('update:page', 2)
    await flushPromises()
    expect(http.get).toHaveBeenLastCalledWith(expect.stringContaining('/document-one/reviews/'), {
      params: { page: 2, page_size: 50 }
    })
    expect(wrapper.text()).toContain('Old pending evidence')
    expect(wrapper.text()).not.toContain('Recent task 0')
    await wrapper.find('input').setValue('Approved the older evidence')
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Approve')!
      .trigger('click')
    await flushPromises()
    expect(http.post).toHaveBeenCalledWith(
      expect.stringContaining('/reviews/old-pending/decision/'),
      {
        status: 'approved',
        decision_note: 'Approved the older evidence'
      }
    )
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('resets pagination and ignores an old page response when the document changes', async () => {
    const wrapper = await panel()
    let resolve!: (value: unknown) => void
    http.get.mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done
        })
    )
    const pagination = wrapper.findComponent(NPagination)
    expect(pagination.exists()).toBe(true)
    pagination.vm.$emit('update:page', 2)
    await flushPromises()
    http.get.mockResolvedValue({
      data: {
        count: 1,
        next: null,
        previous: null,
        results: [{ ...pending, id: 'other', request_note: 'Other document review' }]
      }
    })
    await wrapper.setProps({ document: { id: 'document-two', version: 1 } as ICompDoc })
    await flushPromises()
    resolve({ data: { count: 51, next: null, previous: '?page=1', results: [pending] } })
    await flushPromises()
    expect(wrapper.text()).toContain('Other document review')
    expect(wrapper.text()).not.toContain('Old pending evidence')
    expect(http.get).toHaveBeenLastCalledWith(expect.stringContaining('/document-two/reviews/'), {
      params: { page: 1, page_size: 50 }
    })
  })
})
