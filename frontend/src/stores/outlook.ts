import axios from 'axios'
import { defineStore } from 'pinia'
import { handleRequest } from '@/composables/promise'
import type { IMsg } from '@/models/outlook'
import { notifyError, notifySuccess } from '@/services/notify'
import { API_PATHS } from '@/stores/apiPaths'

export const useOutlookStore = defineStore('outlook', {
  state: () => ({ loading: false, msg: {} as IMsg }),
  getters: {
    isLoading: (state) => state.loading,
    getMsg: (state) => state.msg
  },
  actions: {
    /** Parse a validated Outlook message and retain its structured content. */
    async parseMsg(message: FormData): Promise<IMsg> {
      this.loading = true
      return handleRequest<IMsg>(
        axios.post(`${API_PATHS.outlook}/msg/parse/`, message),
        (data) => {
          this.msg = data
          notifySuccess('Mail content successfully read.')
        },
        notifyError,
        () => (this.loading = false)
      )
    }
  }
})
