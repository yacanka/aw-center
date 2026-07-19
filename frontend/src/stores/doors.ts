import axios from 'axios'
import { defineStore } from 'pinia'
import { handleRequest } from '@/composables/promise'
import { notifyError, notifySuccess } from '@/services/notify'
import { API_PATHS } from '@/stores/apiPaths'

export const useDoorsStore = defineStore('doors', {
  state: () => ({ loading: false }),
  getters: { isLoading: (state) => state.loading },
  actions: {
    /** Create a bounded DXL script from the submitted workbook. */
    async createScript(workbook: FormData): Promise<string> {
      this.loading = true
      return handleRequest<string>(
        axios.post(`${API_PATHS.doors}/script/`, workbook),
        () => notifySuccess('Script created successfully.'),
        notifyError,
        () => (this.loading = false)
      )
    },
    /** Run the selected DXL operation through the protected DOORS adapter. */
    async run_dxl(moduleRequest: object): Promise<unknown> {
      this.loading = true
      return handleRequest<unknown>(
        axios.post(`${API_PATHS.doors}/run_dxl/`, moduleRequest),
        () => notifySuccess('DOORS triggered successfully.'),
        notifyError,
        () => (this.loading = false)
      )
    }
  }
})
