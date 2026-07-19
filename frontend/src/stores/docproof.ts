import axios from 'axios'
import { defineStore } from 'pinia'
import { handleRequest } from '@/composables/promise'
import { notifyError } from '@/services/notify'
import { API_PATHS } from '@/stores/apiPaths'

export const useDocproofStore = defineStore('docproof', {
  state: () => ({ loading: false }),
  getters: { isLoading: (state) => state.loading },
  actions: {
    /** Return the number of DocProof matches for a document identifier. */
    async search(documentNumber: string): Promise<number> {
      this.loading = true
      return handleRequest<number>(
        axios.get(`${API_PATHS.docproof}/search/`, { params: { document_no: documentNumber } }),
        () => undefined,
        notifyError,
        () => (this.loading = false)
      )
    }
  }
})
