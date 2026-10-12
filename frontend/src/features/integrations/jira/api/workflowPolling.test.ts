// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { create, NButton, NCard } from 'naive-ui'
import { NAIVE_UI_COMPONENTS } from '@/app/plugins/naiveUi'
import { NAIVE_UI_FEATURE_COMPONENTS } from '@/app/plugins/naiveUiFeatures'
import { useProjectCatalogStore } from '@/features/projects/stores/projectCatalog'
import { useJiraStore } from '@/features/integrations/jira/stores/jira'
import { apiClient } from '@/shared/api/http'
import type { Job } from '@/features/jobs/api/jobs'
import type { EcrWorkflow } from '../api/ecrWorkflows'
import DCCCreator from '@/features/integrations/jira/pages/DCCCreator.vue'
import EcrTask from '@/features/integrations/jira/components/EcrTask.vue'

const priorAdapter = apiClient.defaults.adapter
const wrappers: VueWrapper[] = []
const naiveUi = create({ components: [...NAIVE_UI_COMPONENTS, ...NAIVE_UI_FEATURE_COMPONENTS] })

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}

function job(id: string, status: Job['status'] = 'running'): Job {
  return {
    id,
    kind: 'dcc_create_document',
    title: id,
    status,
    progress: 0,
    message: '',
    error_code: '',
    input_name: '',
    output_name: '',
    result_summary: {},
    attempt: 1,
    max_attempts: 1,
    source_job: null,
    workflow_run: null,
    workflow_step: null,
    request_id: '',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    started_at: null,
    completed_at: null,
    confirmation_expires_at: null,
    can_cancel: false,
    download_url: null,
    recovery_hint: '',
    jira_draft: null
  }
}

function workflow(id: string, status: EcrWorkflow['status'] = 'publishing'): EcrWorkflow {
  return {
    id,
    status,
    version: 1,
    project_slugs: ['hys'],
    snapshot: {
      ecr_number: id,
      title: id,
      project: '',
      change_class: '',
      change_type: '',
      effectivity: '',
      track_type: '',
      record_of_change: '',
      requestor: '',
      originator: '',
      ata: '',
      subata: '',
      initiator: '',
      justification: '',
      proposed_solution: '',
      nonimplementation_consequence: '',
      impacted_groups: ''
    },
    approval: {
      project_key: '',
      extra_fields: {},
      subtasks: [],
      approved_at: null,
      rejected_at: null
    },
    publication: {
      job_id: null,
      job_status: null,
      jira_issue_key: '',
      attachment_confirmed: false,
      subtasks_confirmed: 0,
      subtasks_total: 0,
      published_at: null,
      last_error: null
    },
    allowed_actions: {
      approve: false,
      reject: false,
      publish: false,
      resume: false,
      cancel: false
    },
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    events: []
  }
}

async function screen(
  kind: 'dcc' | 'ecr',
  query: Record<string, string> = {},
  projectsReady?: Promise<[]>
) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const catalog = useProjectCatalogStore()
  catalog.status = 'ready'
  vi.spyOn(catalog, 'load').mockReturnValue(projectsReady || Promise.resolve([]))
  const jira = useJiraStore()
  jira.jiraConnection = { state: 'connected', expires_at: null }
  vi.spyOn(jira, 'fetchJiraConnection').mockResolvedValue(jira.jiraConnection)
  const component = kind === 'dcc' ? DCCCreator : EcrTask
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component }]
  })
  await router.push({ path: '/', query })
  const wrapper = mount(component, { global: { plugins: [pinia, router, naiveUi] } })
  wrappers.push(wrapper)
  await flushPromises()
  return { wrapper, router }
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  window.matchMedia = vi
    .fn()
    .mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })
  window.$notification = { success: vi.fn(), error: vi.fn() } as never
  window.$message = { success: vi.fn(), error: vi.fn() } as never
})

afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  apiClient.defaults.adapter = priorAdapter
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('JIRA workflow request lifetimes', () => {
  it('keeps a manual ECR selection when linked-workflow initialization finishes later', async () => {
    const projects = deferred<[]>()
    let oldReads = 0
    let newReads = 0
    apiClient.defaults.adapter = async (config) => {
      let data: unknown
      if (config.url === 'workflows/ecr/')
        data = { count: 1, next: null, previous: null, results: [workflow('new', 'review')] }
      else if (config.url?.includes('/old/')) data = (oldReads++, workflow('old', 'review'))
      else data = (newReads++, workflow('new', 'review'))
      return { config, data, status: 200, statusText: 'OK', headers: {} }
    }
    const { wrapper, router } = await screen('ecr', { ecr_workflow: 'old' }, projects.promise)
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Review')!
      .trigger('click')
    await flushPromises()
    projects.resolve([])
    await flushPromises()
    expect(oldReads).toBe(0)
    expect(newReads).toBe(1)
    expect(wrapper.findAllComponents(NCard).map((card) => card.props('title'))).toContain('new')
    expect(router.currentRoute.value.query.ecr_workflow).toBe('new')
  })
  it('does not load a linked ECR workflow after initialization outlives unmount', async () => {
    const projects = deferred<[]>()
    let detailRequests = 0
    apiClient.defaults.adapter = async (config) => {
      const data =
        config.url === 'workflows/ecr/'
          ? { count: 0, next: null, previous: null, results: [] }
          : (++detailRequests, workflow('old'))
      return { config, data, status: 200, statusText: 'OK', headers: {} }
    }
    const { wrapper } = await screen('ecr', { ecr_workflow: 'old' }, projects.promise)
    wrapper.unmount()
    projects.resolve([])
    await flushPromises()
    expect(detailRequests).toBe(0)
  })
  it.each(['dcc', 'ecr'] as const)(
    'does not restart %s polling after a pending response outlives unmount',
    async (kind) => {
      const pending = deferred<Job | EcrWorkflow>()
      let detailRequests = 0
      apiClient.defaults.adapter = async (config) => {
        const data =
          config.url === 'workflows/ecr/'
            ? { count: 0, next: null, previous: null, results: [] }
            : (++detailRequests, await pending.promise)
        return { config, data, status: 200, statusText: 'OK', headers: {} }
      }
      const { wrapper } = await screen(
        kind,
        kind === 'dcc' ? { dcc_job: 'old' } : { ecr_workflow: 'old' }
      )
      expect(detailRequests).toBe(1)
      wrapper.unmount()
      pending.resolve(kind === 'dcc' ? job('old') : workflow('old'))
      await flushPromises()
      vi.advanceTimersByTime(6000)
      await flushPromises()
      expect(detailRequests).toBe(1)
    }
  )

  it('keeps the newest ECR selection when an older request completes later', async () => {
    const old = deferred<EcrWorkflow>()
    const newest = deferred<EcrWorkflow>()
    apiClient.defaults.adapter = async (config) => {
      let data: unknown
      if (config.url === 'workflows/ecr/')
        data = {
          count: 2,
          next: null,
          previous: null,
          results: [workflow('old', 'review'), workflow('new', 'review')]
        }
      else data = await (config.url?.includes('/old/') ? old.promise : newest.promise)
      return { config, data, status: 200, statusText: 'OK', headers: {} }
    }
    const { wrapper, router } = await screen('ecr')
    const review = wrapper.findAll('button').filter((button) => button.text() === 'Review')
    await review[0].trigger('click')
    await review[1].trigger('click')
    newest.resolve(workflow('new', 'review'))
    await flushPromises()
    old.resolve(workflow('old', 'review'))
    await flushPromises()
    expect(wrapper.findAllComponents(NCard).map((card) => card.props('title'))).toContain('new')
    expect(wrapper.findAllComponents(NCard).map((card) => card.props('title'))).not.toContain('old')
    expect(router.currentRoute.value.query.ecr_workflow).toBe('new')
  })

  it('keeps a new DCC preview when polling the previous job completes later', async () => {
    const poll = deferred<Job>()
    let reads = 0
    apiClient.defaults.adapter = async (config) => {
      const data =
        config.method === 'post'
          ? job('new', 'queued')
          : ++reads === 1
            ? job('old')
            : await poll.promise
      return { config, data, status: 200, statusText: 'OK', headers: {} }
    }
    const { wrapper, router } = await screen('dcc', { dcc_job: 'old', url: 'DCC-123' })
    vi.advanceTimersByTime(2000)
    await flushPromises()
    expect(reads).toBe(2)
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    poll.resolve(job('old'))
    await flushPromises()
    expect(wrapper.findAllComponents(NCard).map((card) => card.props('title'))).toContain('new')
    expect(wrapper.findAllComponents(NCard).map((card) => card.props('title'))).not.toContain('old')
    expect(router.currentRoute.value.query.dcc_job).toBe('new')
  })

  it.each(['cancel', 'confirm'] as const)(
    'keeps the new DCC %s action usable after superseding a pending action',
    async (action) => {
      const pending = deferred<Job>()
      const initialStatus = action === 'cancel' ? 'running' : 'awaiting_confirmation'
      const initialJob = { ...job('old', initialStatus), can_cancel: true }
      const newJob = { ...job('new', initialStatus), can_cancel: true }
      const actionLabel = action === 'cancel' ? 'Cancel' : 'Confirm and queue exact snapshot'
      let newActions = 0
      apiClient.defaults.adapter = async (config) => {
        let data: Job
        if (config.method === 'get') data = initialJob
        else if (config.url?.includes('/preview/')) data = newJob
        else if (config.url?.includes('/old/')) data = await pending.promise
        else {
          newActions++
          data = job('new', action === 'cancel' ? 'cancelled' : 'queued')
        }
        return { config, data, status: 200, statusText: 'OK', headers: {} }
      }
      const { wrapper } = await screen('dcc', { dcc_job: 'old', url: 'DCC-123' })
      const actionButton = () =>
        wrapper.findAllComponents(NButton).find((button) => button.text() === actionLabel)!
      await actionButton().trigger('click')
      await flushPromises()
      expect(actionButton().props('loading')).toBe(true)
      await wrapper.find('form').trigger('submit')
      await flushPromises()
      expect(actionButton().props('loading')).toBe(false)
      pending.resolve(initialJob)
      await flushPromises()
      await actionButton().trigger('click')
      await flushPromises()
      expect(newActions).toBe(1)
      expect(wrapper.text()).toContain(action === 'cancel' ? 'cancelled' : 'queued')
    }
  )

  it.each(['response', 'error'] as const)(
    'ignores an older ECR poll %s after selecting another workflow',
    async (outcome) => {
      const poll = deferred<EcrWorkflow>()
      let reads = 0
      apiClient.defaults.adapter = async (config) => {
        let data: unknown
        if (config.url === 'workflows/ecr/')
          data = {
            count: 2,
            next: null,
            previous: null,
            results: [workflow('old'), workflow('new', 'review')]
          }
        else if (config.url?.includes('/old/'))
          data = ++reads === 1 ? workflow('old') : await poll.promise
        else data = workflow('new', 'review')
        return { config, data, status: 200, statusText: 'OK', headers: {} }
      }
      const { wrapper } = await screen('ecr', { ecr_workflow: 'old' })
      vi.advanceTimersByTime(2000)
      await flushPromises()
      expect(reads).toBe(2)
      const review = wrapper.findAll('button').filter((button) => button.text() === 'Review')
      await review[1].trigger('click')
      await flushPromises()
      if (outcome === 'response') poll.resolve(workflow('old'))
      else
        poll.reject({
          response: {
            status: 500,
            data: { detail: 'Old workflow unavailable.', code: 'OLD_WORKFLOW_ERROR' }
          }
        })
      await flushPromises()
      expect(wrapper.findAllComponents(NCard).map((card) => card.props('title'))).toContain('new')
      expect(wrapper.findAllComponents(NCard).map((card) => card.props('title'))).not.toContain(
        'old'
      )
      expect(wrapper.text()).not.toContain('Old workflow unavailable.')
      vi.advanceTimersByTime(6000)
      await flushPromises()
      expect(reads).toBe(2)
    }
  )
})
