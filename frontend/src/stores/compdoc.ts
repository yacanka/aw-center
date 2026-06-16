import { defineStore } from "pinia"
import axios from 'axios'
import { ICompDoc } from "@/models/compdocs"
import { toTitleCase } from '@/utils/text'
import { nullCheck } from '@/utils/general'
import { getDaysDifference, getTodayEUFormat } from '@/utils/time'
import { createEmpty } from "./datatable"
import { handleRequest } from "@/composables/promise"
import { API_BASE_URL } from "@/services/http"
import { notifyError, notifySuccess } from "@/services/notify"
import { compactPaginationQuery, getPaginationMeta, PaginationMeta, PaginationQuery } from '@/services/pagination'

const BASE_URL = API_BASE_URL
const SHOW_DELAYED_COMPDOCS = import.meta.env.SHOW_DELAYED_COMPDOCS
const errorNotification = notifyError
const successNotification = notifySuccess
const COMP_DOCS_PATH = "compdocs"
const bonusFieldProjects = ["aesa"]

export const useCompdocStore = defineStore(
  "compdoc",
  {
    state: () => ({
      projectName: "",
      compdocs: [] as ICompDoc[],
      loading: true,
      fields: [] as { label: string, value: string }[],
      pagination: { count: 0, next: null, previous: null } as PaginationMeta,
    }),
    getters: {
      getCompdocs: (state) => {
        state.compdocs.forEach((row) => {
          if (row.status_flow.length > 0) {
            row.ubm_target_date = row.status_flow[0].date
            if (row.status_flow.length > 1) {
              row.ubm_delivery_date = row.status_flow[1].date
            }
            if (SHOW_DELAYED_COMPDOCS) {
              if (row.status_flow.length == 1 && row.status_flow[0].status == "to_be_issued" && (getDaysDifference(getTodayEUFormat(), row?.ubm_target_date) || 0) > 0) {
                row.status_flow[0].status = "delayed"
              }
            }
            row.status = row.status_flow[row.status_flow.length - 1].status

          } else {
            row.status = "Unknown"
          }
        })
        return state.compdocs
      },
      getProjectName: (state) => state.projectName,
      getCompdocFields: (state) => {
        if (nullCheck(state.fields)) {
          useCompdocStore().createCompDocFields()
        }
        return state.fields
      },
      getUploadUrl: (state) => `${BASE_URL}/${state.projectName}/compdocs/upload/`,
      getUpdateUrl: (state) => `${BASE_URL}/${state.projectName}/compdocs/update/`,
      isLoading: (state) => state.loading,
    },
    actions: {
      setProjectName(name: string) {
        this.projectName = name
      },
      clearList() {
        this.compdocs = []
      },
      checkBonusFields() {
        return bonusFieldProjects.includes(this.projectName);
      },
      createCompDocFields() {
        const obj = createEmpty()
        for (const key in obj) {
          if (obj.hasOwnProperty(key)) {
            this.fields.push({ label: toTitleCase(key.replaceAll("_", " ")), value: key })
          }
        }
      },
      async fetchCompdocs(query: PaginationQuery = {}) {
        this.loading = true
        const response = await handleRequest<ICompDoc[]>(
          axios.get(`${this.projectName}/${COMP_DOCS_PATH}/`, { params: compactPaginationQuery(query) }),
          (data) => {
            this.compdocs = data
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => { this.loading = false }
        )
        this.pagination = getPaginationMeta<ICompDoc>(response) || this.pagination
      },
      async createCompdoc(newCompDocData: ICompDoc) {
        this.loading = true;
        await handleRequest<ICompDoc>(
          axios.post(`${this.projectName}/${COMP_DOCS_PATH}/`, newCompDocData),  // POST request
          (data) => {
            this.compdocs.unshift(data);  // Add created doc to existing list
            successNotification("New document added successfully.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => this.loading = false
        )
      },
      async updateCompdoc(compDocId: Number, updatedData: ICompDoc) {
        this.loading = true;
        await handleRequest<ICompDoc>(
          axios.put(`${this.projectName}/${COMP_DOCS_PATH}/${compDocId}/`, updatedData),  // PUT with ID
          (data) => {
            const existingIndex = this.compdocs.findIndex(doc => doc.id === compDocId);
            if (existingIndex !== -1) { // Doc found
              this.compdocs[existingIndex] = { ...this.compdocs[existingIndex], ...data }; // Update with new data
            }
            successNotification("Updated successfully.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => this.loading = false
        )
      },
      async deleteCompdoc(compDocId: Number) {
        this.loading = true;
        await handleRequest<void>( // Void response expected
          axios.delete(`${this.projectName}/${COMP_DOCS_PATH}/${compDocId}/`),
          () => {
            this.compdocs = this.compdocs.filter((doc: ICompDoc) => doc.id !== compDocId);
            successNotification("Deleted successfully.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => this.loading = false
        );
      },
      async deleteCompdocs() {
        this.loading = true;
        return await handleRequest<any>( // Void response expected
          axios.delete(`${this.projectName}/${COMP_DOCS_PATH}/`),
          (data) => {
            this.compdocs = [];
            successNotification(data)
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => this.loading = false
        );
      },
      async fetchHistory(compDocId: Number) {
        this.loading = true
        let res
        await handleRequest<ICompDoc[]>(
          axios.get(`${this.projectName}/${COMP_DOCS_PATH}/${compDocId}/history/`),
          (data) => {
            res = data
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => { this.loading = false }
        )
        return res
      },
      async createCoverPage(compDocData: ICompDoc) {
        this.loading = true;
        let res
        await handleRequest<ICompDoc>(
          axios.post(`${this.projectName}/${COMP_DOCS_PATH}/`, compDocData),  // POST request
          (data) => {
            res = data
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => this.loading = false
        )
        return res
      },
    }
  }
)

