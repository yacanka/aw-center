import axios from 'axios'
import { defineStore } from 'pinia'
import { handleRequest } from '@/composables/promise'
import type { IDdf } from '@/models/ddf'
import { API_BASE_URL } from '@/services/http'
import { notifyError, notifySuccess } from '@/services/notify'
import {
  compactPaginationQuery,
  getPaginationMeta,
  type PaginationMeta,
  type PaginationQuery
} from '@/services/pagination'
import { API_PATHS } from '@/stores/apiPaths'

type MessageResponse = { message: string }

export const useDdfStore = defineStore('ddf', {
  state: () => ({
    ddfList: [] as IDdf[],
    pagination: { count: 0, next: null, previous: null } as PaginationMeta,
    loading: false
  }),
  getters: {
    getList: (state) => state.ddfList,
    isLoading: (state) => state.loading,
    getUploadUrl: () => `${API_BASE_URL}/ddf/upload/`
  },
  actions: {
    /** Clear locally displayed DDF records. */
    clearList(): void {
      this.ddfList = []
    },
    /** Parse and add a validated DDF workbook. */
    async uploadDdf(ddf: FormData): Promise<IDdf> {
      this.loading = true
      return handleRequest<IDdf>(
        axios.post(`${API_PATHS.ddf}/upload/`, ddf),
        (data) => {
          this.ddfList.unshift(data)
          notifySuccess('DDF content successfully read.')
        },
        notifyError,
        () => (this.loading = false)
      )
    },
    /** Load one server-paginated DDF page. */
    async fetchDdf(query: PaginationQuery = {}): Promise<void> {
      this.loading = true
      const response = await handleRequest<IDdf[]>(
        axios.get(`${API_PATHS.ddf}/`, { params: compactPaginationQuery(query) }),
        (data) => (this.ddfList = data),
        notifyError,
        () => (this.loading = false)
      )
      this.pagination = getPaginationMeta<IDdf>(response) || this.pagination
    },
    /** Create one DDF record. */
    async createDdf(newDdf: IDdf): Promise<void> {
      await this.persistDdf(axios.post(`${API_PATHS.ddf}/`, newDdf), 'created')
    },
    /** Update one DDF record. */
    async updateDdf(ddfId: number, updatedData: IDdf): Promise<void> {
      await this.persistDdf(axios.put(`${API_PATHS.ddf}/${ddfId}/`, updatedData), 'updated', ddfId)
    },
    /** Delete one DDF record. */
    async deleteDdf(ddfId: number): Promise<void> {
      this.loading = true
      await handleRequest<void>(
        axios.delete(`${API_PATHS.ddf}/${ddfId}/`),
        () => {
          this.ddfList = this.ddfList.filter((ddf) => ddf.id !== ddfId)
          notifySuccess('Deleted successfully.')
        },
        notifyError,
        () => (this.loading = false)
      )
    },
    /** Delete every DDF record authorized for the current workspace. */
    async deleteDdfs(): Promise<void> {
      this.loading = true
      await handleRequest<MessageResponse>(
        axios.delete(`${API_PATHS.ddf}/`),
        (data) => {
          this.ddfList = []
          notifySuccess(data.message)
        },
        notifyError,
        () => (this.loading = false)
      )
    },
    /** Run server-side DDF assessment and return its explainable result. */
    async assessment(ddf: IDdf): Promise<unknown> {
      return handleRequest<unknown>(
        axios.post(`${API_PATHS.ddf}/assessment/`, ddf),
        () => undefined,
        notifyError
      )
    },
    /** Persist a DDF mutation and synchronize the local page. */
    async persistDdf(
      request: ReturnType<typeof axios.post<IDdf>>,
      mode: 'created' | 'updated',
      ddfId?: number
    ): Promise<void> {
      this.loading = true
      await handleRequest<IDdf>(
        request,
        (data) => this.applyMutation(data, mode, ddfId),
        notifyError,
        () => (this.loading = false)
      )
    },
    /** Apply a successful DDF mutation to local state. */
    applyMutation(data: IDdf, mode: 'created' | 'updated', ddfId?: number): void {
      if (mode === 'created') this.ddfList.unshift(data)
      const existingIndex = this.ddfList.findIndex((ddf) => ddf.id === ddfId)
      if (mode === 'updated' && existingIndex >= 0) this.ddfList[existingIndex] = data
      notifySuccess(
        mode === 'created' ? 'New document added successfully.' : 'Updated successfully.'
      )
    }
  }
})
