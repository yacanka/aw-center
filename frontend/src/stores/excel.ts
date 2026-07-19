import axios from 'axios'
import { defineStore } from 'pinia'
import { handleRequest } from '@/composables/promise'
import { notifyError, notifySuccess } from '@/services/notify'
import { API_PATHS } from '@/stores/apiPaths'

export const useExcelStore = defineStore('excel', {
  state: () => ({ loading: false }),
  getters: { isLoading: (state) => state.loading },
  actions: {
    /** Read workbook columns after backend file validation. */
    async getExcelColumns(workbook: FormData): Promise<string[]> {
      this.loading = true
      return handleRequest<string[]>(
        axios.post(`${API_PATHS.excel}/get_excel_columns/`, workbook),
        () => notifySuccess('Excel content successfully read.'),
        notifyError,
        () => (this.loading = false)
      )
    },
    /** Start the legacy synchronous cover-page request. */
    async excelToCoverPages(workbook: FormData): Promise<string[]> {
      this.loading = true
      return handleRequest<string[]>(
        axios.post(`${API_PATHS.excel}/excel_to_cover_pages/`, workbook),
        () => notifySuccess('Cover pages successfully created.'),
        notifyError,
        () => (this.loading = false)
      )
    }
  }
})
