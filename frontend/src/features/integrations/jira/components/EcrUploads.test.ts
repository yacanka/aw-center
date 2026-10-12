// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { create, NSelect } from 'naive-ui'
import { NAIVE_UI_COMPONENTS } from '@/app/plugins/naiveUi'
import { NAIVE_UI_FEATURE_COMPONENTS } from '@/app/plugins/naiveUiFeatures'
import { useProjectCatalogStore } from '@/features/projects/stores/projectCatalog'
import { useJiraStore } from '@/features/integrations/jira/stores/jira'
import EcrTask from './EcrTask.vue'
import WatcherAssessmentDialog from './WatcherAssessmentDialog.vue'

vi.mock('../api/ecrWorkflows', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  fetchEcrWorkflows: vi.fn().mockResolvedValue({ count: 0, results: [] })
}))

const wrappers: VueWrapper[] = []
const naiveUi = create({ components: [...NAIVE_UI_COMPONENTS, ...NAIVE_UI_FEATURE_COMPONENTS] })

async function screen(kind: 'assessment' | 'workflow') {
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn()
  })
  const pinia = createPinia()
  setActivePinia(pinia)
  const catalog = useProjectCatalogStore()
  catalog.projects = [
    {
      slug: 'hys',
      name: 'HYS',
      capabilities: ['jira'],
      roles: { compliance: null, organization: null, jira: 'operator' }
    }
  ]
  catalog.status = 'ready'
  vi.spyOn(catalog, 'load').mockResolvedValue(catalog.projects)
  vi.spyOn(useJiraStore(), 'fetchJiraConnection').mockResolvedValue({
    state: 'disconnected',
    expires_at: null
  })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: EcrTask }]
  })
  await router.push('/')
  const wrapper = mount(kind === 'assessment' ? WatcherAssessmentDialog : EcrTask, {
    attachTo: document.body,
    global: { plugins: [pinia, router, naiveUi] }
  })
  wrappers.push(wrapper)
  if (kind === 'assessment') {
    ;(wrapper.vm as InstanceType<typeof WatcherAssessmentDialog>).open()
  }
  await flushPromises()
  return wrapper
}

function button(label: string): HTMLButtonElement {
  const match = Array.from(document.querySelectorAll<HTMLButtonElement>('button')).find(
    (element) => element.textContent?.trim() === label
  )
  if (!match) throw new Error(`Missing button: ${label}`)
  return match
}

afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})

describe.each(['assessment', 'workflow'] as const)('%s ECR upload', (kind) => {
  it('provides a button for choosing a PDF and a drop target', async () => {
    await screen(kind)
    const input = document.querySelector<HTMLInputElement>('input[type="file"]')!
    const openFilePicker = vi.spyOn(input, 'click')

    button('Choose PDF').click()

    expect(openFilePicker).toHaveBeenCalledOnce()
    expect(document.querySelector('.n-upload-dragger')).not.toBeNull()
    expect(input.accept).toContain('.pdf')
  })

  it.each(['chooser', 'drop'] as const)('tracks a PDF from the %s and removal', async (source) => {
    const wrapper = await screen(kind)
    const submit = button(kind === 'assessment' ? 'Assess document' : 'Review PDF snapshot')
    if (kind === 'workflow') {
      wrapper.findComponent(NSelect).vm.$emit('update:value', ['hys'])
      await flushPromises()
    }
    expect(submit.disabled).toBe(true)
    const file = new File(['%PDF-1.4'], 'change.pdf', { type: 'application/pdf' })
    if (source === 'chooser') {
      const input = document.querySelector<HTMLInputElement>('input[type="file"]')!
      Object.defineProperty(input, 'files', {
        value: Object.assign([file], { item: (index: number) => (index === 0 ? file : null) }),
        configurable: true
      })
      input.dispatchEvent(new Event('change', { bubbles: true }))
    } else {
      const target = document.querySelector('.n-upload-dragger')!
      const event = new Event('drop', { bubbles: true, cancelable: true })
      Object.defineProperty(event, 'dataTransfer', {
        value: {
          items: [
            {
              webkitGetAsEntry: () => ({
                isFile: true,
                fullPath: '/change.pdf',
                file: (receive: (value: File) => void) => receive(file)
              })
            }
          ]
        }
      })
      target.dispatchEvent(event)
    }
    await flushPromises()

    expect(document.body.textContent).toContain('change.pdf')
    expect(submit.disabled).toBe(false)
    const remove = document.querySelector<HTMLButtonElement>('.n-upload-file button')!
    expect(remove).not.toBeNull()
    remove.click()
    await flushPromises()
    expect(document.body.textContent).not.toContain('change.pdf')
    expect(submit.disabled).toBe(true)
  })
})
