// @vitest-environment jsdom

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { UploadCustomRequestOptions, UploadFileInfo } from 'naive-ui'
import type { Job } from '@/features/jobs/api/jobs'

const api = vi.hoisted(() => ({ getExcelColumns: vi.fn(), createDoorsScript: vi.fn() }))
vi.mock('@/features/tools/api/doorsScript', () => api)
const attributesApi = vi.hoisted(() => ({
  enqueueDoorsModuleAttributes: vi.fn(),
  fetchDoorsModuleAttributesResult: vi.fn()
}))
const jobs = vi.hoisted(() => ({ fetchJob: vi.fn(), cancelJob: vi.fn() }))
const routing = vi.hoisted(() => ({
  query: {} as Record<string, string>,
  replace: vi.fn(),
  push: vi.fn()
}))
vi.mock('@/features/integrations/api/doorsAutomation', () => attributesApi)
vi.mock('@/features/jobs/api/jobs', async (original) => ({
  ...(await original<object>()),
  ...jobs
}))
vi.mock('vue-router', () => ({ useRoute: () => routing, useRouter: () => routing }))

import DoorsScripter from './DoorsScripter.vue'

const slot = { template: '<div><slot /></div>' }
const stubs = {
  NFlex: slot,
  NGrid: slot,
  NGridItem: slot,
  NCard: slot,
  NTooltip: { template: '<div><slot name="trigger" /></div>' },
  NUploadDragger: slot,
  NText: slot,
  NP: slot,
  NH4: slot,
  NFormItem: { props: ['label'], template: '<label>{{ label }}<slot /></label>' },
  NUpload: {
    name: 'NUpload',
    props: ['customRequest'],
    emits: ['change', 'remove'],
    template: '<div><slot /></div>'
  },
  NInput: {
    props: ['value', 'readonly', 'inputProps', 'disabled'],
    emits: ['update:value'],
    template:
      '<input v-bind="inputProps" :value="value" :readonly="readonly" :disabled="disabled" @input="$emit(\'update:value\', $event.target.value)" />'
  },
  NSwitch: {
    props: ['value'],
    emits: ['update:value'],
    template:
      '<input type="checkbox" :checked="value" @change="$emit(\'update:value\', $event.target.checked)" />'
  },
  NSelect: {
    name: 'NSelect',
    props: ['value', 'options', 'inputProps'],
    emits: ['update:value'],
    template:
      '<select v-bind="inputProps" :value="value" @change="$emit(\'update:value\', $event.target.value)"><option value=""></option><option v-for="option in options" :key="option.value" :value="option.value">{{ option.label }}</option></select>'
  },
  NButton: { props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' },
  NModal: {
    props: ['show'],
    template:
      '<section v-if="show"><slot name="header-extra" /><slot /><slot name="action" /></section>'
  },
  NScrollbar: slot,
  NAlert: slot,
  PageJobStatus: {
    props: ['job'],
    emits: ['cancel'],
    template:
      '<aside v-if="job">{{ job.status }}<button @click="$emit(\'cancel\')">Cancel</button></aside>'
  }
}

describe('DOORS script mapping form', () => {
  let wrapper: VueWrapper

  beforeEach(() => {
    vi.resetAllMocks()
    vi.useFakeTimers()
    routing.query = {}
    window.$message = { success: vi.fn(), error: vi.fn(), warning: vi.fn() } as never
    window.$loadingBar = { start: vi.fn(), finish: vi.fn() } as never
    api.getExcelColumns.mockResolvedValue(['Key', 'Group', 'Text'])
    api.createDoorsScript.mockResolvedValue({
      script: 'Generated DXL',
      row_count: 1,
      mapping_count: 3
    })
    wrapper = mount(DoorsScripter, { global: { stubs } })
  })

  afterEach(() => {
    wrapper.unmount()
    vi.useRealTimers()
  })

  async function upload() {
    const file: UploadFileInfo = {
      id: 'workbook',
      name: 'input.xlsx',
      status: 'pending',
      file: new File(['workbook'], 'input.xlsx')
    }
    const control = wrapper.getComponent({ name: 'NUpload' })
    control.vm.$emit('change', { fileList: [file] })
    control.props('customRequest')({
      file,
      onError: vi.fn()
    } as unknown as UploadCustomRequestOptions)
    await flushPromises()
  }

  async function mapAll() {
    const fields = wrapper.findAll('input[aria-label^="DOORS attribute for"]')
    for (const [index, name] of ['Identifier', 'Group', 'Object Text'].entries()) {
      await fields[index].setValue(name)
    }
  }

  async function generate() {
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Generate')!
      .trigger('click')
    await flushPromises()
  }

  it.each(['update', 'create'])('submits independent composite keys in %s mode', async (mode) => {
    await upload()
    await mapAll()
    const keys = wrapper.findAll('input[type="checkbox"]')
    await keys[0].setValue(true)
    await keys[1].setValue(true)
    expect((keys[0].element as HTMLInputElement).checked).toBe(true)
    expect(wrapper.text()).toContain('Unique Attribute')
    expect(wrapper.text()).not.toContain('Search Item')
    await wrapper.get('select').setValue(mode)
    await generate()
    const request = api.createDoorsScript.mock.calls[0][0] as FormData
    expect(request.get('mode')).toBe(mode)
    expect(JSON.parse(request.get('json') as string)).toEqual([
      { excel: 'Key', doors: 'Identifier', search: true },
      { excel: 'Group', doors: 'Group', search: true },
      { excel: 'Text', doors: 'Object Text', search: false }
    ])
    expect(wrapper.text()).toContain('Generated DXL')
    expect(wrapper.text()).toContain('1 rows · 3 mappings')
  })

  it('requires a unique attribute before generation', async () => {
    await upload()
    await mapAll()
    await generate()
    expect(api.createDoorsScript).not.toHaveBeenCalled()
    expect(window.$message.error).toHaveBeenCalledWith('Select at least one Unique Attribute.')
  })

  it('rejects a unique mapping with a blank DOORS attribute', async () => {
    await upload()
    await wrapper.findAll('input[type="checkbox"]')[0].setValue(true)
    await generate()
    expect(api.createDoorsScript).not.toHaveBeenCalled()
    expect(window.$message.error).toHaveBeenCalledWith(
      'Enter a DOORS attribute name for every selected Unique Attribute.'
    )
  })

  it('shows canonical backend errors', async () => {
    await upload()
    await mapAll()
    await wrapper.findAll('input[type="checkbox"]')[0].setValue(true)
    api.createDoorsScript.mockRejectedValue({
      response: {
        data: { detail: 'The workbook has no mapped data rows.', code: 'DOORS_WORKBOOK_EMPTY' }
      }
    })
    await generate()
    expect(wrapper.text()).not.toContain('Generated DXL')
    expect(window.$message.error).toHaveBeenCalledWith('The workbook has no mapped data rows.')
  })

  function attributeResult(attributes = ['Identifier', 'Group', 'Object Heading']) {
    return { type: 'doors_module_attributes', schema_version: 1, module_path: '/P/M', attributes }
  }

  function attributeJob(status: Job['status']): Job {
    return {
      id: 'attribute-job',
      kind: 'doors.run_dxl',
      status,
      can_cancel: true,
      download_url: status === 'succeeded' ? '/api/jobs/attribute-job/download/' : null
    } as Job
  }

  async function loadAttributes() {
    await wrapper.get('input[aria-label="DOORS module path"]').setValue('/P/M')
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Load Attributes')!
      .trigger('click')
    await flushPromises()
  }

  async function finishLoad() {
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
  }

  it('loads selectable attributes, clears unknown names, and preserves choices on unload', async () => {
    await upload()
    await mapAll()
    await wrapper.findAll('input[type="checkbox"]')[0].setValue(true)
    attributesApi.enqueueDoorsModuleAttributes.mockResolvedValue(attributeJob('queued'))
    jobs.fetchJob.mockResolvedValue(attributeJob('succeeded'))
    attributesApi.fetchDoorsModuleAttributesResult.mockResolvedValue(attributeResult())
    await loadAttributes()
    expect(
      wrapper.get('input[aria-label="DOORS module path"]').attributes('disabled')
    ).toBeDefined()
    expect(
      wrapper
        .findAll('button')
        .find((button) => button.text() === 'Generate')!
        .attributes('disabled')
    ).toBeDefined()
    await finishLoad()
    expect(wrapper.text()).toContain('Unload Attributes')
    const selects = wrapper.findAll('select[aria-label^="DOORS attribute for"]')
    expect(selects).toHaveLength(3)
    expect((selects[0].element as HTMLSelectElement).value).toBe('Identifier')
    expect((selects[2].element as HTMLSelectElement).value).toBe('')
    expect(window.$message.warning).toHaveBeenCalledWith(expect.stringContaining('Text'))
    expect((wrapper.findAll('input[type="checkbox"]')[0].element as HTMLInputElement).checked).toBe(
      true
    )
    const textSelect = wrapper
      .findAllComponents({ name: 'NSelect' })
      .find(
        (control) => control.props('inputProps')?.['aria-label'] === 'DOORS attribute for Text'
      )!
    textSelect.vm.$emit('update:value', null)
    await generate()
    const submitted = api.createDoorsScript.mock.calls[0][0] as FormData
    expect(JSON.parse(submitted.get('json') as string)).toHaveLength(2)
    await selects[2].setValue('Object Heading')
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Unload Attributes')!
      .trigger('click')
    expect(wrapper.findAll('select')).toHaveLength(1)
    expect(wrapper.get('input[aria-label="DOORS attribute for Text"]').element).toHaveProperty(
      'value',
      'Object Heading'
    )
    expect(
      wrapper.get('input[aria-label="DOORS module path"]').attributes('disabled')
    ).toBeUndefined()
  })

  it.each(['failed', 'cancelled'])(
    'retains manual mappings when attribute job is %s',
    async (status) => {
      await upload()
      await mapAll()
      attributesApi.enqueueDoorsModuleAttributes.mockResolvedValue(attributeJob('queued'))
      jobs.fetchJob.mockResolvedValue(attributeJob(status as Job['status']))
      await loadAttributes()
      await finishLoad()
      expect(wrapper.text()).toContain('Load Attributes')
      expect(wrapper.get('input[aria-label="DOORS attribute for Text"]').element).toHaveProperty(
        'value',
        'Object Text'
      )
      expect(
        wrapper.get('input[aria-label="DOORS module path"]').attributes('disabled')
      ).toBeUndefined()
    }
  )

  it('keeps manual values on worker-unavailable and empty-list results', async () => {
    await upload()
    await mapAll()
    attributesApi.enqueueDoorsModuleAttributes.mockRejectedValue({
      response: { data: { detail: 'Worker unavailable', code: 'DOORS_WORKER_UNAVAILABLE' } }
    })
    await loadAttributes()
    expect(wrapper.text()).toContain('Worker unavailable')
    attributesApi.enqueueDoorsModuleAttributes.mockResolvedValue(attributeJob('queued'))
    jobs.fetchJob.mockResolvedValue(attributeJob('succeeded'))
    attributesApi.fetchDoorsModuleAttributesResult.mockResolvedValue(attributeResult([]))
    await loadAttributes()
    await finishLoad()
    expect(wrapper.text()).toContain('No object attributes were found')
    expect(wrapper.get('input[aria-label="DOORS attribute for Key"]').element).toHaveProperty(
      'value',
      'Identifier'
    )
  })

  it('restores attribute discovery without an Excel file', async () => {
    wrapper.unmount()
    routing.query = { doors_scripter_attributes_job: 'attribute-job' }
    jobs.fetchJob.mockResolvedValue(attributeJob('succeeded'))
    attributesApi.fetchDoorsModuleAttributesResult.mockResolvedValue(attributeResult())
    wrapper = mount(DoorsScripter, { global: { stubs } })
    await flushPromises()
    expect(wrapper.text()).toContain('Unload Attributes')
    expect(wrapper.get('input[aria-label="DOORS module path"]').element).toHaveProperty(
      'value',
      '/P/M'
    )
    await upload()
    expect(wrapper.findAll('select[aria-label^="DOORS attribute for"]')).toHaveLength(3)
  })

  it('keeps manual generation available if job polling fails', async () => {
    await upload()
    await mapAll()
    attributesApi.enqueueDoorsModuleAttributes.mockResolvedValue(attributeJob('queued'))
    jobs.fetchJob.mockRejectedValue(new Error('Connection interrupted'))
    await loadAttributes()
    await finishLoad()
    expect(wrapper.text()).toContain('Connection interrupted')
    expect(
      wrapper.get('input[aria-label="DOORS module path"]').attributes('disabled')
    ).toBeUndefined()
    expect(
      wrapper
        .findAll('button')
        .find((button) => button.text() === 'Generate')!
        .attributes('disabled')
    ).toBeUndefined()
  })

  it('ignores attribute results after unmount', async () => {
    wrapper.unmount()
    routing.query = { doors_scripter_attributes_job: 'attribute-job' }
    jobs.fetchJob.mockResolvedValue(attributeJob('succeeded'))
    let complete!: (result: ReturnType<typeof attributeResult>) => void
    attributesApi.fetchDoorsModuleAttributesResult.mockReturnValue(
      new Promise((resolve) => {
        complete = resolve
      })
    )
    wrapper = mount(DoorsScripter, { global: { stubs } })
    await flushPromises()
    expect(attributesApi.fetchDoorsModuleAttributesResult).toHaveBeenCalledOnce()
    wrapper.unmount()
    complete(attributeResult())
    await flushPromises()
    expect(window.$message.warning).not.toHaveBeenCalled()
  })
})
