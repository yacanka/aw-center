import axios, { type AxiosResponse } from 'axios'
import { defineStore } from 'pinia'
import { handleRequest } from '@/composables/promise'
import type { IDcc } from '@/models/dcc'
import type { IEcd } from '@/models/ecd'
import type { IJira, IUser as JiraUser } from '@/models/jira'
import { notifyError, notifySuccess } from '@/services/notify'
import {
  compactPaginationQuery,
  getPaginationMeta,
  type PaginationMeta,
  type PaginationQuery
} from '@/services/pagination'
import { API_PATHS } from '@/stores/apiPaths'

type AddDccRequest = { url: string; JSESSIONID: string | null }
type DccMailRequest = {
  issue: string
  ccb_no: number | null
  due_date: string | null
  JSESSIONID: string
}
type DccState = {
  dccList: IDcc[]
  issueInfo: IJira
  loading: boolean
  pagination: PaginationMeta
}

export const useDccStore = defineStore('dcc', {
  state: () => ({
    jSessionId: '',
    dccList: [] as IDcc[],
    pagination: { count: 0, next: null, previous: null } as PaginationMeta,
    issueInfo: {} as IJira,
    loading: false
  }),
  getters: {
    getSessionId: (state) => state.jSessionId,
    getDccList: (state) => state.dccList,
    getIssueInfo: (state) => state.issueInfo,
    isLoading: (state) => state.loading
  },
  actions: {
    /** Set the active JIRA session identifier for DCC requests. */
    setSessionId(id: string): void {
      this.jSessionId = id
    },
    /** Add the active JIRA session identifier to a mutable request payload. */
    importSessionId(payload: object): void {
      Object.assign(payload, { JSESSIONID: this.jSessionId })
    },
    /** Load one server-paginated DCC page. */
    async fetchDcc(query: PaginationQuery = {}): Promise<void> {
      this.loading = true
      const response = await handleRequest<IDcc[]>(
        axios.get(API_PATHS.dcc, { params: compactPaginationQuery(query) }),
        (data) => (this.dccList = data),
        notifyError,
        () => (this.loading = false)
      )
      this.pagination = getPaginationMeta<IDcc>(response) || this.pagination
    },
    /** Create a DCC record. */
    async createDcc(data: IDcc): Promise<void> {
      await mutateDcc(this, axios.post(API_PATHS.dcc, data), (created) => {
        this.dccList.unshift(created)
      })
    },
    /** Update a DCC record and synchronize local state. */
    async updateDcc(id: number, data: IDcc): Promise<void> {
      await mutateDcc(this, axios.put(`${API_PATHS.dcc}/${id}/`, data), (updated) => {
        replaceById(this.dccList, id, updated)
        notifySuccess('Updated successfully.')
      })
    },
    /** Delete a DCC record and synchronize local state. */
    async deleteDcc(id: number): Promise<void> {
      this.loading = true
      await handleRequest<void>(
        axios.delete(`${API_PATHS.dcc}/${id}/`),
        () => {
          this.dccList = this.dccList.filter((item) => item.id !== id)
          notifySuccess('Deleted successfully.')
        },
        notifyError,
        () => (this.loading = false)
      )
    },
    /** Import a DCC from its JIRA URL. */
    async addDcc(data: AddDccRequest): Promise<IDcc> {
      return mutateDcc(this, axios.post('dcc/add/', data), (created) => {
        this.dccList.unshift(created)
        notifySuccess('Added new DCC successfully.')
      })
    },
    /** Load current JIRA issue details for a DCC row. */
    async getIssue(payload: object): Promise<IJira> {
      this.importSessionId(payload)
      return handleRequest<IJira>(
        axios.post('dcc/get_issue/', payload),
        (data) => (this.issueInfo = data),
        notifyError
      )
    },
    /** Create a JIRA issue from an ECD payload. */
    async createIssue(data: IEcd): Promise<IDcc> {
      return handleRequest<IDcc>(
        axios.post('dcc/create_issue/', data),
        (created) => {
          this.dccList.unshift(created)
          notifySuccess('Added new DCC successfully.')
        },
        notifyError
      )
    },
    /** Send the bounded DCC reminder mail request. */
    async sendMail(data: DccMailRequest): Promise<void> {
      await withLoadingBar(
        handleRequest<string>(axios.post('dcc/send_mail/', data), notifySuccess, notifyError)
      )
    },
    /** Parse an uploaded ECD document. */
    async uploadEcd(data: FormData): Promise<IEcd> {
      return withLoadingBar(
        handleRequest<IEcd>(axios.post('dcc/upload/', data), () => undefined, notifyError)
      )
    },
    /** Run ECD assessment against the configured workflow. */
    async ecdAssessment(data: IEcd): Promise<IEcd[]> {
      return withLoadingBar(
        handleRequest<IEcd[]>(axios.post('dcc/ecd_assessment/', data), () => undefined, notifyError)
      )
    },
    /** Validate a JIRA session and return the authenticated profile. */
    async checkSession(sessionId: string): Promise<JiraUser> {
      return handleRequest<JiraUser>(
        axios.get('dcc/check_session/', { params: { sessionId } }),
        () => undefined,
        notifyError
      )
    },
    /** Attach a validated file to the target JIRA issue. */
    async addAttachment(data: FormData): Promise<unknown> {
      return withLoadingBar(
        handleRequest<unknown>(
          axios.post('dcc/add_attachment/', data),
          () => undefined,
          notifyError
        )
      )
    }
  }
})

async function mutateDcc(
  state: DccState,
  request: Promise<AxiosResponse<IDcc>>,
  onSuccess: (data: IDcc) => void
): Promise<IDcc> {
  state.loading = true
  return handleRequest<IDcc>(request, onSuccess, notifyError, () => (state.loading = false))
}

function replaceById(items: IDcc[], id: number, updated: IDcc): void {
  const index = items.findIndex((item) => item.id === id)
  if (index >= 0) items[index] = { ...items[index], ...updated }
}

async function withLoadingBar<T>(request: Promise<T>): Promise<T> {
  window.$loadingBar.start()
  try {
    return await request
  } finally {
    window.$loadingBar.finish()
  }
}
