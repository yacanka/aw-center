// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { AxiosError } from 'axios'
import { apiClient } from '@/shared/api/http'
import { provideOrganizationController } from '@/features/organization/composables/organizationController'
import { popupStore } from '@/app/stores/popupStore'
import PeopleUpload from '@/features/organization/components/PeopleUpload.vue'

afterEach(() => vi.restoreAllMocks())

describe('people workbook import', () => {
  it.each(['success', 'failure'] as const)(
    'shows rejected rows and waits for directory refresh %s despite a warm cache',
    async (refreshOutcome) => {
      const pinia = createPinia()
      setActivePinia(pinia)
      let finishRefresh!: () => void
      const notification = vi.fn()
      const finish = vi.fn()
      const error = vi.fn()
      window.$notification = { success: notification, error: vi.fn() } as never
      window.$loadingBar = { start: vi.fn(), finish, error } as never
      const priorAdapter = apiClient.defaults.adapter
      apiClient.defaults.adapter = async (config) => {
        if (config.method === 'post') {
          return {
            config,
            status: 200,
            statusText: 'OK',
            headers: {},
            data: {
              detail: 'People directory import completed.',
              code: 'PEOPLE_IMPORT_COMPLETED',
              rejected: [{ row: 3, errors: { email: ['Invalid email address.'] } }]
            }
          }
        }
        await new Promise<void>((resolve) => (finishRefresh = resolve))
        if (refreshOutcome === 'failure')
          throw new AxiosError('Directory unavailable', 'ERR_NETWORK', config)
        return {
          config,
          status: 200,
          statusText: 'OK',
          headers: {},
          data: [{ id: 2, person_id: '2', name: 'Imported', email: '' }]
        }
      }
      let controller!: ReturnType<typeof provideOrganizationController>
      const wrapper = mount(
        defineComponent({
          setup() {
            controller = provideOrganizationController()
            controller.project = 'hys'
            controller.peopleFetched = true
            controller.people = [{ id: 1, person_id: '1', name: 'Cached', email: '' }]
            return () => h(PeopleUpload)
          }
        }),
        {
          global: {
            plugins: [pinia],
            stubs: {
              Modal: { template: '<div><slot /></div>' },
              Upload: { name: 'Upload', props: ['customRequest'], template: '<div />' },
              NText: true,
              NP: true,
              NUploadDragger: true
            }
          }
        }
      )
      try {
        const request = wrapper.findComponent({ name: 'Upload' }).props('customRequest')({
          file: { file: new File(['workbook'], 'people.xlsx') }
        })
        await flushPromises()
        expect(finish).not.toHaveBeenCalled()
        expect(finishRefresh).toBeTypeOf('function')
        expect(popupStore().visible).toBe(true)
        expect(popupStore().text_content).toContain('3')
        expect(popupStore().text_content).toContain('Invalid email address.')
        finishRefresh()
        await request
        if (refreshOutcome === 'success') {
          expect(controller.people.map((person) => person.name)).toEqual(['Imported'])
          expect(finish).toHaveBeenCalledOnce()
          expect(error).not.toHaveBeenCalled()
        } else {
          expect(controller.peopleFetched).toBe(false)
          expect(controller.loading).toBe(false)
          expect(error).toHaveBeenCalledOnce()
          expect(finish).not.toHaveBeenCalled()
        }
        expect(notification.mock.calls[0][0].content).toBe('People directory import completed.')
        expect(popupStore().visible).toBe(true)
        expect(popupStore().text_content).toContain('3')
        expect(popupStore().text_content).toContain('Invalid email address.')
      } finally {
        wrapper.unmount()
        apiClient.defaults.adapter = priorAdapter
      }
    }
  )
})
