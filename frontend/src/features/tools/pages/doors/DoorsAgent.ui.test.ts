// @vitest-environment jsdom
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Job } from '@/features/jobs/api/jobs'

const api = vi.hoisted(() => ({
  fetchDoorsStatus: vi.fn(),
  enqueueDoorsQualityCheck: vi.fn(),
  fetchDoorsQualityResult: vi.fn()
}))
const jobs = vi.hoisted(() => ({ fetchJob: vi.fn(), cancelJob: vi.fn() }))
const routing = vi.hoisted(() => ({
  query: {} as Record<string, string>,
  replace: vi.fn(),
  push: vi.fn()
}))
vi.mock('@/features/integrations/api/doorsAutomation', () => ({
  fetchDoorsStatus: api.fetchDoorsStatus
}))
vi.mock('@/features/integrations/api/doorsQuality', () => api)
vi.mock('@/features/jobs/api/jobs', async (original) => ({
  ...(await original<object>()),
  ...jobs
}))
vi.mock('vue-router', () => ({ useRoute: () => routing, useRouter: () => routing }))
import DoorsAgent from './DoorsAgent.vue'

const slot = { template: '<div><slot /></div>' }
const stubs = {
  NSpace: slot,
  NForm: slot,
  NFormItem: slot,
  NText: slot,
  NFlex: slot,
  NTag: slot,
  NProgress: true,
  NCard: { props: ['title'], template: '<section><h2>{{ title }}</h2><slot /></section>' },
  NAlert: {
    props: ['title', 'type'],
    template: '<aside :data-type="type">{{ title }}<slot /></aside>'
  },
  NButton: { props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' },
  NInput: {
    props: ['value'],
    emits: ['update:value'],
    template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />'
  }
}
function job(status: Job['status'], progress = 0) {
  return {
    id: 'job-1',
    kind: 'doors.check_module_quality',
    title: 'Quality check',
    status,
    progress,
    message: 'Step 2/5: Discovering ATA chapter and panel attributes.',
    error_code: '',
    recovery_hint: '',
    attempt: 1,
    max_attempts: 1,
    can_cancel: status === 'running',
    download_url: status === 'succeeded' ? '/api/jobs/job-1/download/' : null
  } as Job
}
function report(outcome = 'review_required') {
  return {
    type: 'doors_module_quality',
    schema_version: 1,
    module_path: '/Project/Module',
    outcome,
    complete: true,
    attributes: {
      ata: { name: 'ATA Chapter', method: 'exact', candidates: ['ATA Chapter'] },
      panel: { name: 'Panel', method: 'heuristic', candidates: ['Panel'] }
    },
    warnings: ['Confirm the selected panel attribute.'],
    summary: {
      scanned_objects: 2,
      checked_objects: 2,
      chapters: 1,
      conflicting_chapters: 1,
      finding_count: 1,
      omitted_findings: 0
    },
    findings: [
      {
        code: 'multiple_panels',
        chapter: '27',
        message: 'This ATA chapter belongs to more than one panel.',
        suggestion: 'Confirm the responsible panel.',
        panels: ['A', 'B'],
        evidence_count: 2,
        evidence: [
          { absolute_number: 42, identifier: 'REQ-42', ata_value: '27', panel_value: 'A' },
          { absolute_number: 43, identifier: 'REQ-43', ata_value: '27', panel_value: 'B' }
        ]
      }
    ]
  }
}
function button(page: VueWrapper, text: string) {
  const found = page.findAll('button').find((item) => item.text() === text)
  if (!found) throw new Error(`Missing button: ${text}`)
  return found
}

describe('DOORS Agent quality workflow', () => {
  let wrapper: VueWrapper | undefined
  beforeEach(() => {
    vi.resetAllMocks()
    vi.useFakeTimers()
    routing.query = {}
    window.$message = { success: vi.fn(), error: vi.fn() } as never
    api.fetchDoorsStatus.mockResolvedValue({ configured: true, available: true, active_workers: 1 })
    api.fetchDoorsQualityResult.mockResolvedValue(report())
  })
  afterEach(() => {
    wrapper?.unmount()
    vi.useRealTimers()
  })
  async function open() {
    wrapper = mount(DoorsAgent, { global: { stubs } })
    await flushPromises()
    return wrapper
  }
  it('polls real worker steps and reveals conflicts only when Details is opened', async () => {
    api.enqueueDoorsQualityCheck.mockResolvedValue(job('queued'))
    jobs.fetchJob
      .mockResolvedValueOnce(job('running', 45))
      .mockResolvedValueOnce(job('succeeded', 100))
    const page = await open()
    await page.find('input').setValue('/Project/Module')
    await button(page, 'Kalite kontrolünü başlat').trigger('click')
    await flushPromises()
    expect(api.enqueueDoorsQualityCheck).toHaveBeenCalledWith('/Project/Module', expect.any(String))
    expect(button(page, 'Kalite kontrolünü başlat').attributes('disabled')).toBeDefined()
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(page.text()).toContain('Çalışıyor')
    expect(page.text()).toContain('Step 2/5: Discovering')
    expect(api.fetchDoorsQualityResult).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(page.text()).toContain('İnceleme gerekiyor')
    expect(page.text()).toContain('1 ATA chapter birden fazla panele bağlı')
    expect(page.text()).not.toContain('REQ-42')
    await button(page, 'Detaylar').trigger('click')
    expect(page.text()).toContain('REQ-42')
    expect(page.text()).toContain('REQ-43')
    expect(page.text()).toContain('Confirm the responsible panel.')
    expect(page.text()).toContain('Sezgisel eşleşme')
    expect(routing.replace).toHaveBeenCalledWith({ query: { doors_agent_job: 'job-1' } })
  })
  it('restores a report after reload and retries a failed download without queueing again', async () => {
    routing.query = { doors_agent_job: 'job-1' }
    jobs.fetchJob.mockResolvedValue(job('succeeded', 100))
    api.fetchDoorsQualityResult
      .mockRejectedValueOnce(new Error('unavailable'))
      .mockResolvedValueOnce(report('incomplete'))
    const page = await open()
    await button(page, 'Raporu yeniden yükle').trigger('click')
    await flushPromises()
    expect(page.text()).toContain('Kontrol tamamlanamadı')
    expect(api.enqueueDoorsQualityCheck).not.toHaveBeenCalled()
  })
  it('retains the idempotency key after an uncertain queue response', async () => {
    api.enqueueDoorsQualityCheck
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce(job('queued'))
    const page = await open()
    await page.find('input').setValue('/P/M')
    await button(page, 'Kalite kontrolünü başlat').trigger('click')
    await flushPromises()
    await button(page, 'Kalite kontrolünü başlat').trigger('click')
    await flushPromises()
    expect(api.enqueueDoorsQualityCheck.mock.calls[0]).toEqual(
      api.enqueueDoorsQualityCheck.mock.calls[1]
    )
  })
  it.each(['failed', 'cancelled'] as const)(
    'stops at the actual step on %s without loading a report',
    async (status) => {
      routing.query = { doors_agent_job: 'job-1' }
      jobs.fetchJob.mockResolvedValue(job(status, 45))
      const page = await open()
      expect(page.text()).toContain(status === 'failed' ? 'Hata' : 'İptal edildi')
      expect(page.text()).toContain('Bekliyor')
      expect(api.fetchDoorsQualityResult).not.toHaveBeenCalled()
    }
  )
  it('cancels an active job using the existing job endpoint', async () => {
    routing.query = { doors_agent_job: 'job-1' }
    jobs.fetchJob.mockResolvedValue(job('running', 45))
    jobs.cancelJob.mockResolvedValue(job('cancel_requested', 45))
    const page = await open()
    await button(page, 'Cancel').trigger('click')
    await flushPromises()
    expect(jobs.cancelJob).toHaveBeenCalledWith('job-1')
    expect(page.text()).toContain('İptal bekleniyor')
  })

  it('can resume monitoring after a transient job status failure', async () => {
    routing.query = { doors_agent_job: 'job-1' }
    jobs.fetchJob
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce(job('running', 45))
    const page = await open()
    await button(page, 'İş durumunu yeniden yükle').trigger('click')
    await flushPromises()
    expect(jobs.fetchJob).toHaveBeenCalledTimes(2)
    expect(page.text()).toContain('Çalışıyor')
    expect(page.text()).not.toContain('İş durumunu yeniden yükle')
  })
})
