import { defineStore } from 'pinia'
import axios from 'axios'
import {
  ICompDoc,
  ICompDocFieldMetadata,
  ICompDocFieldsResponse,
  IHistory,
  IStatusFlow
} from '@/models/compdocs'
import { toTitleCase } from '@/utils/text'
import { getDaysDifference, getTodayEUFormat } from '@/utils/time'
import { createEmptyCompdoc } from '@/services/compdocCatalog'
import { SHOW_DELAYED_COMPDOCS } from '@/services/featureFlags'
import { handleRequest } from '@/composables/promise'
import { API_BASE_URL } from '@/services/http'
import { notifyError, notifySuccess } from '@/services/notify'
import {
  compactPaginationQuery,
  getPaginationMeta,
  PaginationMeta,
  PaginationQuery
} from '@/services/pagination'

const BASE_URL = API_BASE_URL
const errorNotification = notifyError
const successNotification = notifySuccess
const COMP_DOCS_PATH = 'compdocs'
const bonusFieldProjects = ['aesa']

function createLocalFieldMetadata(key: string) {
  return {
    key,
    label: toTitleCase(key.replaceAll('_', ' ')),
    width: 15,
    sorter: true,
    filter: true,
    ellipsis: true
  }
}

function fieldToSelectOption(field: ICompDocFieldMetadata) {
  return { label: field.label, value: field.key }
}

function applyDerivedStatusFields(row: ICompDoc) {
  const statusFlow = Array.isArray(row.status_flow) ? row.status_flow : []
  if (statusFlow.length === 0) {
    row.status = 'Unknown'
    return
  }

  row.ubm_target_date = statusFlow[0]?.date
  row.ubm_delivery_date = statusFlow[1]?.date
  applyDelayedStatus(statusFlow, row)
  row.status = statusFlow[statusFlow.length - 1]?.status || 'Unknown'
}

function applyDelayedStatus(statusFlow: IStatusFlow[], row: ICompDoc) {
  if (!SHOW_DELAYED_COMPDOCS || statusFlow.length !== 1) return
  if (statusFlow[0]?.status !== 'to_be_issued') return
  if ((getDaysDifference(getTodayEUFormat(), String(row.ubm_target_date || '')) || 0) <= 0) return
  statusFlow[0].status = 'delayed'
}

function mergeFieldMetadata(serverFields: ICompDocFieldMetadata[]) {
  const fieldsByKey = new Map(serverFields.map((field) => [field.key, field]))
  Object.keys(createEmptyCompdoc()).forEach((key) =>
    fieldsByKey.set(key, fieldsByKey.get(key) || createLocalFieldMetadata(key))
  )
  return Array.from(fieldsByKey.values())
}

export const useCompdocStore = defineStore('compdoc', {
  state: () => ({
    projectName: '',
    compdocs: [] as ICompDoc[],
    loading: true,
    fields: [] as ICompDocFieldMetadata[],
    pagination: { count: 0, next: null, previous: null } as PaginationMeta
  }),
  getters: {
    getCompdocs: (state) => {
      state.compdocs.forEach(applyDerivedStatusFields)
      return state.compdocs
    },
    getProjectName: (state) => state.projectName,
    getCompdocFields: (state) => state.fields.map(fieldToSelectOption),
    getUploadUrl: (state) => `${BASE_URL}/${state.projectName}/compdocs/upload/`,
    getUpdateUrl: (state) => `${BASE_URL}/${state.projectName}/compdocs/update/`,
    isLoading: (state) => state.loading
  },
  actions: {
    setProjectName(name: string) {
      this.projectName = name
    },
    clearList() {
      this.compdocs = []
    },
    checkBonusFields() {
      return bonusFieldProjects.includes(this.projectName)
    },
    createCompDocFields() {
      this.fields = Object.keys(createEmptyCompdoc()).map(createLocalFieldMetadata)
    },
    async fetchCompDocFields() {
      try {
        return await handleRequest<ICompDocFieldsResponse>(
          axios.get(`${this.projectName}/${COMP_DOCS_PATH}/fields/`),
          (data) => {
            this.fields = mergeFieldMetadata(data.fields)
          },
          () => {
            this.createCompDocFields()
          }
        )
      } catch {
        return null
      }
    },
    async fetchCompdocs(query: PaginationQuery = {}) {
      this.loading = true
      const response = await handleRequest<ICompDoc[]>(
        axios.get(`${this.projectName}/${COMP_DOCS_PATH}/`, {
          params: compactPaginationQuery(query)
        }),
        (data) => {
          this.compdocs = data
        },
        (errorMsg) => {
          errorNotification(errorMsg)
          console.log(errorMsg)
        },
        () => {
          this.loading = false
        }
      )
      this.pagination = getPaginationMeta<ICompDoc>(response) || this.pagination
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
    async updateCompdoc(compDocId: Number, updatedData: ICompDoc) {
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
    async deleteCompdoc(compDocId: Number) {
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
    async deleteCompdocs() {
      this.loading = true
      return await handleRequest<any> // Void response expected
      (
        axios.delete(`${this.projectName}/${COMP_DOCS_PATH}/`),
        (data) => {
          this.compdocs = []
          successNotification(data)
        },
        (errorMsg) => {
          errorNotification(errorMsg)
          console.log(errorMsg)
        },
        () => (this.loading = false)
      )
    },
    async fetchHistory(compDocId: number) {
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
    },
    async createCoverPage(compDocData: ICompDoc) {
      this.loading = true
      let res
      await handleRequest<ICompDoc>(
        axios.post(`${this.projectName}/${COMP_DOCS_PATH}/`, compDocData), // POST request
        (data) => {
          res = data
        },
        (errorMsg) => {
          errorNotification(errorMsg)
          console.log(errorMsg)
        },
        () => (this.loading = false)
      )
      return res
    }
  }
})
