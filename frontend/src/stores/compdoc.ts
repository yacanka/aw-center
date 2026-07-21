import { defineStore } from 'pinia'
import axios from 'axios'
import {
  ICompDoc,
  ICompDocFieldMetadata,
  ICompDocFieldsResponse,
  IHistory,
  CompDocBulkDeleteRequest
} from '@/models/compdocs'
import { withCompdocDisplayStatus } from '@/services/compdocStatus'
import { handleRequest } from '@/composables/promise'
import { API_BASE_URL } from '@/services/http'
import { notifyError, notifySuccess } from '@/services/notify'
import {
  compactPaginationQuery,
  getPaginationMeta,
  PaginationMeta,
  PaginationQuery
} from '@/services/pagination'

const errorNotification = notifyError
const successNotification = notifySuccess
const COMP_DOCS_PATH = 'compdocs'
const bonusFieldProjects = ['aesa']

export const useCompdocStore = defineStore('compdoc', {
  state: () => ({
    projectName: '',
    compdocs: [] as ICompDoc[],
    loading: true,
    listRequestId: 0,
    fields: [] as ICompDocFieldMetadata[],
    fieldsSchemaVersion: 0,
    fieldsError: null as string | null,
    pagination: { count: 0, next: null, previous: null } as PaginationMeta
  }),
  getters: {
    getCompdocs: (state) => state.compdocs.map(withCompdocDisplayStatus),
    getProjectName: (state) => state.projectName,
    getUploadUrl: (state) => `${API_BASE_URL}/${state.projectName}/compdocs/upload/`,
    isLoading: (state) => state.loading
  },
  actions: {
    setProjectName(name: string) {
      this.projectName = name
    },
    clearList() {
      this.listRequestId += 1
      this.compdocs = []
      this.loading = false
    },
    checkBonusFields() {
      return bonusFieldProjects.includes(this.projectName)
    },
    async fetchCompDocFields() {
      const requestedProject = this.projectName
      this.fieldsError = null
      try {
        return await handleRequest<ICompDocFieldsResponse>(
          axios.get(`${this.projectName}/${COMP_DOCS_PATH}/fields/`),
          (data) => {
            if (this.projectName !== requestedProject) return
            this.fields = data.fields
            this.fieldsSchemaVersion = data.schema_version
          },
          (errorMessage) => {
            if (this.projectName !== requestedProject) return
            this.fields = []
            this.fieldsError = errorMessage
            errorNotification(errorMessage)
          }
        )
      } catch {
        return null
      }
    },
    async fetchCompdocs(query: PaginationQuery = {}) {
      const requestedProject = this.projectName
      const requestId = ++this.listRequestId
      const isCurrent = () =>
        this.projectName === requestedProject && this.listRequestId === requestId
      this.loading = true
      const response = await handleRequest<ICompDoc[]>(
        axios.get(`${this.projectName}/${COMP_DOCS_PATH}/`, {
          params: compactPaginationQuery(query),
          paramsSerializer: { indexes: null }
        }),
        (data) => {
          if (isCurrent()) this.compdocs = data
        },
        (errorMsg) => {
          if (!isCurrent()) return
          errorNotification(errorMsg)
          console.log(errorMsg)
        },
        () => {
          if (isCurrent()) this.loading = false
        }
      )
      if (isCurrent()) this.pagination = getPaginationMeta<ICompDoc>(response) || this.pagination
    },
    async createCompdoc(newCompDocData: ICompDoc) {
      this.loading = true
      await handleRequest<ICompDoc>(
        axios.post(`${this.projectName}/${COMP_DOCS_PATH}/`, newCompDocData), // POST request
        (data) => {
          this.compdocs.unshift(data) // Add created doc to existing list
          successNotification('New document added successfully.')
        },
        (errorMsg) => {
          errorNotification(errorMsg)
          console.log(errorMsg)
        },
        () => (this.loading = false)
      )
    },
    async updateCompdoc(compDocId: string, updatedData: ICompDoc) {
      this.loading = true
      await handleRequest<ICompDoc>(
        axios.put(`${this.projectName}/${COMP_DOCS_PATH}/${compDocId}/`, updatedData), // PUT with ID
        (data) => {
          const existingIndex = this.compdocs.findIndex((doc) => doc.id === compDocId)
          if (existingIndex !== -1) {
            // Doc found
            this.compdocs[existingIndex] = { ...this.compdocs[existingIndex], ...data } // Update with new data
          }
          successNotification('Updated successfully.')
        },
        (errorMsg) => {
          errorNotification(errorMsg)
          console.log(errorMsg)
        },
        () => (this.loading = false)
      )
    },
    async deleteCompdoc(compDocId: string) {
      this.loading = true
      await handleRequest<void> // Void response expected
      (
        axios.delete(`${this.projectName}/${COMP_DOCS_PATH}/${compDocId}/`),
        () => {
          this.compdocs = this.compdocs.filter((doc: ICompDoc) => doc.id !== compDocId)
          successNotification('Deleted successfully.')
        },
        (errorMsg) => {
          errorNotification(errorMsg)
          console.log(errorMsg)
        },
        () => (this.loading = false)
      )
    },
    async deleteCompdocs(payload: CompDocBulkDeleteRequest) {
      this.loading = true
      return await handleRequest<any> // Void response expected
      (
        axios.delete(`${this.projectName}/${COMP_DOCS_PATH}/`, { data: payload }),
        (data) => {
          this.compdocs = []
          this.pagination = { count: 0, next: null, previous: null }
          successNotification(data)
        },
        (errorMsg) => {
          errorNotification(errorMsg)
          console.log(errorMsg)
        },
        () => (this.loading = false)
      )
    },
    async fetchHistory(compDocId: string) {
      this.loading = true
      let history: IHistory[] = []
      await handleRequest<IHistory[]>(
        axios.get(`${this.projectName}/${COMP_DOCS_PATH}/${compDocId}/history/`),
        (data) => {
          history = data
        },
        (errorMsg) => {
          errorNotification(errorMsg)
          console.log(errorMsg)
        },
        () => {
          this.loading = false
        }
      )
      return history
    }
  }
})
