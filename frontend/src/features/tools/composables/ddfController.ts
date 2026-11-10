import { inject, provide, reactive, type InjectionKey } from 'vue'
import { apiClient } from '@/shared/api/http'
import { handleRequest } from '@/shared/composables/promise'
import type { IDdf } from '@/features/tools/models/ddf'
import { notifyError, notifySuccess } from '@/shared/services/notify'
import {
  compactPaginationQuery,
  getPaginationMeta,
  type PaginationMeta,
  type PaginationQuery
} from '@/shared/services/pagination'
import { API_PATHS } from '@/shared/api/apiPaths'

type MessageResponse = { message: string }

export interface DdfController {
  ddfList: IDdf[]
  pagination: PaginationMeta
  loading: boolean
  readonly getList: IDdf[]
  readonly isLoading: boolean
  clearList(): void
  uploadDdf(ddf: FormData): Promise<IDdf>
  fetchDdf(query?: PaginationQuery): Promise<void>
  createDdf(newDdf: IDdf): Promise<void>
  updateDdf(ddfId: number, updatedData: IDdf): Promise<void>
  deleteDdf(ddfId: number): Promise<void>
  deleteDdfs(): Promise<void>
  assessment(ddf: IDdf): Promise<unknown>
}

const ddfControllerKey: InjectionKey<DdfController> = Symbol('ddf-controller')

/** Create DDF table/form state owned by one assistant route visit. */
export function createDdfController(): DdfController {
  const state = reactive({
    ddfList: [] as IDdf[],
    pagination: { count: 0, next: null, previous: null } as PaginationMeta,
    loading: false
  })

  async function persistDdf(
    request: ReturnType<typeof apiClient.post<IDdf>>,
    mode: 'created' | 'updated',
    ddfId?: number
  ): Promise<void> {
    state.loading = true
    await handleRequest<IDdf>(
      request,
      (data) => applyMutation(data, mode, ddfId),
      notifyError,
      () => (state.loading = false)
    )
  }

  function applyMutation(data: IDdf, mode: 'created' | 'updated', ddfId?: number): void {
    if (mode === 'created') state.ddfList.unshift(data)
    const index = state.ddfList.findIndex((ddf) => ddf.id === ddfId)
    if (mode === 'updated' && index >= 0) state.ddfList[index] = data
    notifySuccess(mode === 'created' ? 'New document added successfully.' : 'Updated successfully.')
  }

  return reactive({
    get ddfList() {
      return state.ddfList
    },
    get pagination() {
      return state.pagination
    },
    get loading() {
      return state.loading
    },
    get getList() {
      return state.ddfList
    },
    get isLoading() {
      return state.loading
    },
    clearList() {
      state.ddfList = []
    },
    async uploadDdf(ddf: FormData): Promise<IDdf> {
      state.loading = true
      return handleRequest<IDdf>(
        apiClient.post(`${API_PATHS.ddf}/upload/`, ddf),
        (data) => {
          state.ddfList.unshift(data)
          notifySuccess('DDF content successfully read.')
        },
        notifyError,
        () => (state.loading = false)
      )
    },
    async fetchDdf(query: PaginationQuery = {}): Promise<void> {
      state.loading = true
      const response = await handleRequest<IDdf[]>(
        apiClient.get(`${API_PATHS.ddf}/`, { params: compactPaginationQuery(query) }),
        (data) => (state.ddfList = data),
        notifyError,
        () => (state.loading = false)
      )
      state.pagination = getPaginationMeta<IDdf>(response) || state.pagination
    },
    async createDdf(newDdf: IDdf): Promise<void> {
      await persistDdf(apiClient.post(`${API_PATHS.ddf}/`, newDdf), 'created')
    },
    async updateDdf(ddfId: number, updatedData: IDdf): Promise<void> {
      await persistDdf(apiClient.put(`${API_PATHS.ddf}/${ddfId}/`, updatedData), 'updated', ddfId)
    },
    async deleteDdf(ddfId: number): Promise<void> {
      state.loading = true
      await handleRequest<void>(
        apiClient.delete(`${API_PATHS.ddf}/${ddfId}/`),
        () => {
          state.ddfList = state.ddfList.filter((ddf) => ddf.id !== ddfId)
          notifySuccess('Deleted successfully.')
        },
        notifyError,
        () => (state.loading = false)
      )
    },
    async deleteDdfs(): Promise<void> {
      state.loading = true
      await handleRequest<MessageResponse>(
        apiClient.delete(`${API_PATHS.ddf}/`),
        (data) => {
          state.ddfList = []
          notifySuccess(data.message)
        },
        notifyError,
        () => (state.loading = false)
      )
    },
    async assessment(ddf: IDdf): Promise<unknown> {
      return handleRequest<unknown>(
        apiClient.post(`${API_PATHS.ddf}/assessment/`, ddf),
        () => undefined,
        notifyError
      )
    }
  }) as DdfController
}

export function provideDdfController(controller = createDdfController()) {
  provide(ddfControllerKey, controller)
  return controller
}

export function useDdfController(): DdfController {
  const controller = inject(ddfControllerKey)
  if (!controller) throw new Error('DDF controller is outside its route boundary.')
  return controller
}
