// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent, h, type PropType } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Job } from '@/features/jobs/api/jobs'
import type { JiraIssueDraft, JiraIssueDraftPreflight } from '../api/jiraIssueDrafts'

vi.mock('../api/jiraIssueDrafts', () => ({
  fetchJiraIssueDraft: vi.fn(),
  createJiraIssueDraft: vi.fn(),
  updateJiraIssueDraft: vi.fn(),
  approveJiraIssueDraft: vi.fn(),
  preflightJiraIssueDraft: vi.fn(),
  publishJiraIssueDraft: vi.fn()
}))
vi.mock('../api/jiraSession', () => ({
  fetchJiraConnection: vi.fn().mockResolvedValue({
    state: 'connected',
    user: { username: 'reviewer', display_name: 'Reviewer' },
    expires_at: null
  })
}))
vi.mock('@/features/projects/api/projectRegistry', () => ({
  fetchProjectRegistry: vi.fn().mockResolvedValue([
    {
      slug: 'ozgur',
      name: 'Özgür',
      capabilities: ['jira'],
      roles: { jira: 'operator', organization: null, compliance: null }
    }
  ])
}))

import * as api from '../api/jiraIssueDrafts'
import { useJiraIssueDraft } from './useJiraIssueDraft'
import { useJiraStore } from '../stores/jira'
import { create } from 'naive-ui'
import { NAIVE_UI_COMPONENTS } from '@/app/plugins/naiveUi'
import { NAIVE_UI_FEATURE_COMPONENTS } from '@/app/plugins/naiveUiFeatures'
import JiraIssueDraftPanel from '@/features/jobs/components/JiraIssueDraftPanel.vue'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((accept, fail) => {
    resolve = accept
    reject = fail
  })
  return { promise, resolve, reject }
}

function job(id: string, hasDraft = true): Job {
  return {
    id,
    kind: 'word.analyze',
    title: id,
    status: 'succeeded',
    progress: 100,
    message: '',
    error_code: '',
    input_name: '',
    output_name: '',
    result_summary: {},
    attempt: 1,
    max_attempts: 3,
    source_job: null,
    workflow_run: null,
    workflow_step: null,
    request_id: '',
    created_at: '2026-10-23T00:00:00Z',
    started_at: null,
    completed_at: null,
    confirmation_expires_at: null,
    updated_at: '2026-10-23T00:00:00Z',
    can_cancel: false,
    download_url: null,
    recovery_hint: '',
    jira_draft: hasDraft
      ? { id: `draft-${id}`, status: 'draft', version: 1, jira_issue_key: '' }
      : null
  }
}

function draft(id: string, status: JiraIssueDraft['status'] = 'draft'): JiraIssueDraft {
  return {
    id: `draft-${id}`,
    source_job: id,
    owner: 1,
    assigned_users: [],
    project_slugs: ['ozgur'],
    publication_job: null,
    project_key: 'TEST',
    summary: `Summary ${id}`,
    description: '',
    extra_fields: {},
    status,
    version: 1,
    jira_issue_key: '',
    jira_issue_url: null,
    approved_at: null,
    published_at: null,
    last_error_code: '',
    last_error_message: '',
    created_at: '2026-10-23T00:00:00Z',
    updated_at: '2026-10-23T00:00:00Z',
    events: [],
    allowed_actions: { edit: true, approve: true, preflight: true, publish: true }
  }
}

const readyPreflight: JiraIssueDraftPreflight = {
  ready: true,
  project_key: 'TEST',
  issue_type: 'Task',
  fields: [],
  missing_fields: [],
  invalid_fields: [],
  unsupported_fields: [],
  warnings: []
}
const wrappers: ReturnType<typeof mount>[] = []
function panel(selectedJob = job('A')) {
  let state!: ReturnType<typeof useJiraIssueDraft>
  const wrapper = mount(
    defineComponent({
      props: { job: { type: Object as PropType<Job>, required: true } },
      setup(props) {
        state = useJiraIssueDraft(() => props.job)
        return () => h('output', state.draft.value?.summary || 'No draft')
      }
    }),
    { props: { job: selectedJob }, global: { plugins: [createPinia()] } }
  )
  wrappers.push(wrapper)
  return { state, wrapper }
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.fetchJiraIssueDraft).mockImplementation(async (id) =>
    draft(id.replace('draft-', ''))
  )
  vi.mocked(api.preflightJiraIssueDraft).mockResolvedValue(readyPreflight)
  window.$message = { success: vi.fn(), error: vi.fn() } as unknown as typeof window.$message
})
afterEach(() => wrappers.splice(0).forEach((wrapper) => wrapper.unmount()))

describe('JIRA draft selection ownership', () => {
  it.each(['success', 'failure'] as const)(
    'ignores an old load %s while the new selection is loading',
    async (outcome) => {
      const old = deferred<JiraIssueDraft>()
      const current = deferred<JiraIssueDraft>()
      vi.mocked(api.fetchJiraIssueDraft)
        .mockReturnValueOnce(old.promise)
        .mockReturnValueOnce(current.promise)
      const { state, wrapper } = panel()
      await wrapper.setProps({ job: job('B') })

      if (outcome === 'success') old.resolve(draft('A'))
      else old.reject(new Error('Old request failed'))
      await flushPromises()

      expect(state.draft.value).toBeNull()
      expect(state.busy.value).toBe(true)
      expect(window.$message.error).not.toHaveBeenCalled()
      current.resolve(draft('B'))
      await flushPromises()
      expect(wrapper.text()).toBe('Summary B')
      expect(state.busy.value).toBe(false)
    }
  )

  it.each(['prepare', 'save', 'approve', 'preflight', 'publish'] as const)(
    'does not apply an old %s result to another job',
    async (action) => {
      const { state, wrapper } = panel(job('A', action !== 'prepare'))
      await flushPromises()
      const result = deferred<any>()
      const pendingAction = {
        prepare: () => {
          vi.mocked(api.createJiraIssueDraft).mockReturnValueOnce(result.promise)
          return state.prepareDraft()
        },
        save: () => {
          state.form.summary = 'Edited A'
          vi.mocked(api.updateJiraIssueDraft).mockReturnValueOnce(result.promise)
          return state.saveDraft()
        },
        approve: () => {
          vi.mocked(api.approveJiraIssueDraft).mockReturnValueOnce(result.promise)
          return state.approveDraft()
        },
        preflight: () => {
          vi.mocked(api.preflightJiraIssueDraft).mockReturnValueOnce(result.promise)
          return state.checkPreflight()
        },
        publish: () => {
          state.draft.value!.status = 'approved'
          state.preflight.value = readyPreflight
          vi.mocked(api.publishJiraIssueDraft).mockReturnValueOnce(result.promise)
          return state.publishDraft()
        }
      }[action]()
      expect(state.busy.value).toBe(true)
      await wrapper.setProps({ job: job('B') })
      await flushPromises()
      state.form.summary = 'Unsaved B'

      result.resolve(
        action === 'preflight'
          ? readyPreflight
          : action === 'publish'
            ? job('publication-A', false)
            : draft('A')
      )
      await pendingAction
      await flushPromises()

      expect(state.draft.value?.id).toBe('draft-B')
      expect(state.form.summary).toBe('Unsaved B')
      expect(state.preflight.value).toBeNull()
      expect(state.publicationJob.value).toBeNull()
      expect(window.$message.success).not.toHaveBeenCalled()
    }
  )

  it('does not recover an old failed mutation into the newer editable form', async () => {
    const { state, wrapper } = panel()
    await flushPromises()
    const saving = deferred<JiraIssueDraft>()
    vi.mocked(api.updateJiraIssueDraft).mockReturnValueOnce(saving.promise)
    state.form.summary = 'Edited A'
    const action = state.saveDraft()
    await wrapper.setProps({ job: job('B') })
    await flushPromises()
    state.form.summary = 'Unsaved B'
    saving.reject(new Error('Old save failed'))
    await action

    expect(state.form.summary).toBe('Unsaved B')
    expect(window.$message.error).not.toHaveBeenCalled()
    expect(api.fetchJiraIssueDraft).toHaveBeenCalledTimes(2)
  })

  it('does not approve, check or publish an unsaved selection', async () => {
    const { state } = panel()
    await flushPromises()
    state.form.summary = 'Unsaved changes'
    state.draft.value!.status = 'approved'
    state.preflight.value = readyPreflight
    await state.approveDraft()
    await state.checkPreflight()
    await state.publishDraft()
    expect(api.approveJiraIssueDraft).not.toHaveBeenCalled()
    expect(api.preflightJiraIssueDraft).not.toHaveBeenCalled()
    expect(api.publishJiraIssueDraft).not.toHaveBeenCalled()
  })

  it.each(['success', 'failure'] as const)(
    'ignores an old recovery %s after changing selection',
    async (outcome) => {
      const { state, wrapper } = panel()
      await flushPromises()
      const recovering = deferred<JiraIssueDraft>()
      vi.mocked(api.updateJiraIssueDraft).mockRejectedValueOnce(new Error('Conflict'))
      vi.mocked(api.fetchJiraIssueDraft).mockReturnValueOnce(recovering.promise)
      state.form.summary = 'Edited A'
      const action = state.saveDraft()
      await flushPromises()
      await wrapper.setProps({ job: job('B') })
      await flushPromises()
      state.form.summary = 'Unsaved B'
      if (outcome === 'success') recovering.resolve(draft('A'))
      else recovering.reject(new Error('Old recovery failed'))
      await action

      expect(state.draft.value?.id).toBe('draft-B')
      expect(state.form.summary).toBe('Unsaved B')
      expect(window.$message.error).not.toHaveBeenCalled()
    }
  )

  it('keeps the current permitted draft creation, edit, approval and publication flow working', async () => {
    const { state, wrapper } = panel(job('A', false))
    await flushPromises()
    vi.mocked(api.createJiraIssueDraft).mockResolvedValueOnce(draft('A'))
    await state.prepareDraft()
    expect(api.createJiraIssueDraft).toHaveBeenCalledWith('A', ['ozgur'])
    expect(wrapper.text()).toBe('Summary A')

    state.form.summary = 'Edited A'
    const saved = { ...draft('A'), summary: 'Edited A', version: 2 }
    vi.mocked(api.updateJiraIssueDraft).mockResolvedValueOnce(saved)
    await state.saveDraft()
    expect(state.dirty.value).toBe(false)
    expect(state.draft.value?.version).toBe(2)
    await state.checkPreflight()
    expect(state.preflight.value?.ready).toBe(true)

    const approved = { ...saved, status: 'approved' as const, version: 3 }
    vi.mocked(api.approveJiraIssueDraft).mockResolvedValueOnce(approved)
    await state.approveDraft()
    expect(state.draft.value?.status).toBe('approved')
    vi.mocked(api.publishJiraIssueDraft).mockResolvedValueOnce(job('publication-A', false))
    vi.mocked(api.fetchJiraIssueDraft).mockResolvedValueOnce({
      ...approved,
      status: 'publishing',
      version: 4,
      publication_job: 'publication-A'
    })
    await state.publishDraft()
    expect(api.publishJiraIssueDraft).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'draft-A', version: 3 }),
      expect.any(String)
    )
    expect(state.publicationJob.value?.id).toBe('publication-A')
    expect(state.draft.value?.status).toBe('publishing')
    expect(state.busy.value).toBe(false)
  })

  it.each([null, { ...readyPreflight, ready: false }])(
    'reconciles an uncertain draft without create readiness (%s)',
    async (preflight) => {
      const uncertain = {
        ...draft('A', 'reconciliation_required'),
        allowed_actions: { edit: false, approve: false, preflight: true, publish: true }
      }
      vi.mocked(api.fetchJiraIssueDraft).mockResolvedValue(uncertain)
      const { state } = panel()
      await flushPromises()
      state.preflight.value = preflight
      vi.mocked(api.publishJiraIssueDraft).mockResolvedValue(job('publication-A', false))
      await state.publishDraft()
      expect(api.publishJiraIssueDraft).toHaveBeenCalledWith(uncertain, expect.any(String))
      expect(api.preflightJiraIssueDraft).not.toHaveBeenCalled()
    }
  )

  it('offers a read-only reconciliation button when create fields are not ready', async () => {
    vi.mocked(api.fetchJiraIssueDraft).mockResolvedValue({
      ...draft('A', 'reconciliation_required'),
      allowed_actions: { edit: false, approve: false, preflight: true, publish: true }
    })
    vi.mocked(api.publishJiraIssueDraft).mockResolvedValue(job('publication-A', false))
    const wrapper = mount(JiraIssueDraftPanel, {
      props: { job: job('A') },
      global: {
        plugins: [
          createPinia(),
          create({ components: [...NAIVE_UI_COMPONENTS, ...NAIVE_UI_FEATURE_COMPONENTS] })
        ]
      }
    })
    wrappers.push(wrapper)
    await flushPromises()
    const reconcile = wrapper
      .findAll('button')
      .find((button) => button.text() === 'Reconcile publication')
    expect(reconcile).toBeDefined()
    expect(reconcile!.attributes('disabled')).toBeUndefined()
    await reconcile!.trigger('click')
    await flushPromises()
    expect(api.publishJiraIssueDraft).toHaveBeenCalledOnce()
    expect(api.preflightJiraIssueDraft).not.toHaveBeenCalled()
  })

  it.each(['not-ready', 'disconnected', 'no-permission'] as const)(
    'keeps publication gates for %s',
    async (reason) => {
      const selected = draft('A', reason === 'not-ready' ? 'approved' : 'reconciliation_required')
      vi.mocked(api.fetchJiraIssueDraft).mockResolvedValue(selected)
      const { state } = panel()
      await flushPromises()
      state.preflight.value = { ...readyPreflight, ready: false }
      if (reason === 'disconnected') useJiraStore().jiraConnection.state = 'disconnected'
      if (reason === 'no-permission') state.draft.value!.allowed_actions.publish = false
      await state.publishDraft()
      expect(api.publishJiraIssueDraft).not.toHaveBeenCalled()
    }
  )

  it('rejects stale handlers once the current selection has lost action permissions', async () => {
    const { state } = panel()
    await flushPromises()
    state.draft.value!.allowed_actions = {
      edit: false,
      approve: false,
      preflight: false,
      publish: false
    }
    state.form.summary = 'Edited A'
    await state.saveDraft()
    state.form.summary = 'Summary A'
    await state.approveDraft()
    await state.checkPreflight()
    state.draft.value!.status = 'approved'
    state.preflight.value = readyPreflight
    await state.publishDraft()
    expect(api.updateJiraIssueDraft).not.toHaveBeenCalled()
    expect(api.approveJiraIssueDraft).not.toHaveBeenCalled()
    expect(api.preflightJiraIssueDraft).not.toHaveBeenCalled()
    expect(api.publishJiraIssueDraft).not.toHaveBeenCalled()
  })

  it('does not repopulate an unmounted panel after a pending load', async () => {
    const loading = deferred<JiraIssueDraft>()
    vi.mocked(api.fetchJiraIssueDraft).mockReturnValueOnce(loading.promise)
    const { state, wrapper } = panel()
    wrapper.unmount()
    loading.resolve(draft('A'))
    await flushPromises()
    expect(state.draft.value).toBeNull()
  })
})
