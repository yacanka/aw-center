import { defineStore } from "pinia"
import axios from 'axios'
import { ICompDoc } from "@/models/compdocs"
import { IDcc } from "@/models/dcc"
import { IJira } from "@/models/jira"
import { IEcd } from "@/models/ecd"
import { IDdf } from "@/models/ddf"
import { IUser, IPermission } from "@/models/auth"
import { IPerson, IPanel, IProject, IResponsible } from "@/models/orgs"
import { setUser, logout } from "./user"
import { toTitleCase } from '@/utils/text'
import { nullCheck } from '@/utils/general'
import { getDaysDifference, parseDateFlex, getTodayEUFormat } from '@/utils/time'
import { createEmpty } from "./datatable"
import { useUserStore } from "./user"
import { handleRequest } from "@/composables/promise"

const BASE_URL = import.meta.env.VITE_API_URL
const SHOW_DELAYED_COMPDOCS = import.meta.env.SHOW_DELAYED_COMPDOCS

axios.defaults.baseURL = BASE_URL
let accessToken = localStorage.getItem("token");
if (accessToken) {
  axios.defaults.headers.common["Authorization"] = `Token ${accessToken}`
}

const errorNotification = ( message: string = "", title: string = "Error", duration: number = 3000) => {
  window.$notification.error({
    title: title,
    content: message,
    duration: duration,
  })
}

const warningNotification = (message: string = "", title: string = "Warning", duration: number = 3000) => {
  window.$notification.warning({
    title: title,
    content: message,
    duration: duration,
  })
}

const successNotification = (message: string = "", title: string = "Success", duration: number = 3000) => {
  window.$notification.success({
    title: title,
    content: message,
    duration: 3000,
  })
}

const errorMessage = (message: string) => {
  window.$message.error(message)
}

const API_PATHS = {
  compdocs: "compdocs",
  dcc: "dcc/api",
  auth: "auth",
  doors: "doors",
  ddf: "ddf",
  docproof: "docproof",
  excel: "excel",
  orgs: "orgs",
  outlook: "outlook",
  presentations: "pptxgallery",
}

const bonusFieldProjects = ["aesa"]

export const useCompdocStore = defineStore(
  "compdoc",
  {
    state: () => ({
      projectName: "",
      compdocs: [] as ICompDoc[],
      loading: true,
      fields: [] as { label: string, value: string }[],
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
      async fetchCompdocs() {
        this.loading = true
        await handleRequest<ICompDoc[]>(
          axios.get(`${this.projectName}/${API_PATHS.compdocs}/`),
          (data) => {
            this.compdocs = data.reverse()
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => { this.loading = false }
        )
      },
      async createCompdoc(newCompDocData: ICompDoc) {
        this.loading = true;
        await handleRequest<ICompDoc>(
          axios.post(`${this.projectName}/${API_PATHS.compdocs}/`, newCompDocData),  // POST request
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
          axios.put(`${this.projectName}/${API_PATHS.compdocs}/${compDocId}/`, updatedData),  // PUT with ID
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
          axios.delete(`${this.projectName}/${API_PATHS.compdocs}/${compDocId}/`),
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
          axios.delete(`${this.projectName}/${API_PATHS.compdocs}/`),
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
          axios.get(`${this.projectName}/${API_PATHS.compdocs}/${compDocId}/history/`),
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
          axios.post(`${this.projectName}/${API_PATHS.compdocs}/`, compDocData),  // POST request
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


export const useDccStore = defineStore(
  "dcc",
  {
    state: () => ({
      jSessionId: "" as string,
      dccList: [] as IDcc[],
      issueInfo: {} as IJira,
      visionTypes: [] as string[],
      loading: true,
      ipAddress: axios.defaults.baseURL
    }),
    getters: {
      getSessionId: (state) => state.jSessionId,
      getDccList: (state) => state.dccList,
      getIssueInfo: (state) => state.issueInfo,
      isLoading: (state) => state.loading,
    },
    actions: {
      setSessionId(id: string) {
        this.jSessionId = id
      },
      importSessionId(payload: any) {
        Object.assign(payload, { JSESSIONID: this.jSessionId })
      },
      async fetchDcc() {
        this.loading = true
        await handleRequest<IDcc[]>(
          axios.get(API_PATHS.dcc),
          (data) => {
            this.dccList = data.reverse()
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => { this.loading = false }
        )
      },
      async createDcc(newDccData: IDcc) {
        this.loading = true;
        await handleRequest<IDcc>(
          axios.post(API_PATHS.dcc, newDccData),  // POST request
          (data) => {
            this.dccList.unshift(data);  // Add created doc to existing list
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => this.loading = false
        )
      },
      async updateDcc(dccId: Number, updatedData: IDcc) {
        this.loading = true;
        await handleRequest<IDcc>(
          axios.put(`${API_PATHS.dcc}/${dccId}/`, updatedData),  // PUT with ID
          (data) => {
            const existingIndex = this.dccList.findIndex(dcc => dcc.id === dccId);
            if (existingIndex !== -1) { // Doc found
              this.dccList[existingIndex] = { ...this.dccList[existingIndex], ...data }; // Update with new data
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
      async deleteDcc(dccId: Number) {
        this.loading = true;
        await handleRequest<void>(
          axios.delete(`${API_PATHS.dcc}/${dccId}/`),
          () => {
            this.dccList = this.dccList.filter((dcc: IDcc) => dcc.id !== dccId);
            successNotification("Deleted successfully.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => this.loading = false
        );
      },
      async addDcc(newDccData: IDcc) {
        this.loading = true;
        let dccData
        await handleRequest<IDcc>(
          axios.post('dcc/add/', newDccData),
          (data) => {
            dccData = data
            this.dccList.unshift(data);
            successNotification("Added new DCC successfully.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => this.loading = false
        )
        return dccData
      },
      async getIssue(newDccData: any) {
        this.importSessionId(newDccData)
        await handleRequest<IJira>(
          axios.post('dcc/get_issue/', newDccData),
          (data) => {
            this.issueInfo = data
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => { }
        )
        return this.issueInfo
      },
      async createIssue(issueData: IEcd) {
        const newIssue: IDcc = await handleRequest<IDcc>(
          axios.post('dcc/create_issue/', issueData),
          (data) => {
            this.dccList.unshift(data);
            successNotification("Added new DCC successfully.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => { }
        )
        return newIssue
      },
      async sendMail(data: IDcc) {
        window.$loadingBar.start()
        await handleRequest<any>(
          axios.post('dcc/send_mail/', data),  // POST request
          (data) => {
            successNotification(data)
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => window.$loadingBar.finish()
        )
      },
      async uploadEcd(data: any) {
        window.$loadingBar.start()
        const res = await handleRequest<any>(
          axios.post('dcc/upload/', data),  // POST request
          (data) => {

          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => window.$loadingBar.finish()
        )
        return res
      },
      async ecdAssessment(data: IEcd) {
        window.$loadingBar.start()
        let res
        await handleRequest<any>(
          axios.post('dcc/ecd_assessment/', data),  // POST request
          (data) => {
            res = data
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => window.$loadingBar.finish()
        )
        return res
      },
      async checkSession(sessionId: string) {
        const res = await handleRequest<any>(
          axios.get(`dcc/check_session/?sessionId=${sessionId}`),
          (data) => {

          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => { }
        )
        return res
      },
      async addAttachment(attachmentData: any) {
        window.$loadingBar.start()
        return await handleRequest<any>(
          axios.post('dcc/add_attachment/', attachmentData),
          (data) => {
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
            throw errorMsg
          },
          () => window.$loadingBar.finish()
        )
      },
    }
  }
)


export const useAuthStore = defineStore(
  "auth",
  {
    state: () => ({
      me: {} as IUser,
      token: "" as string,
      users: [] as IUser[],
      permissions: [] as IPermission[],
      loading: false,
      ipAddress: axios.defaults.baseURL
    }),
    getters: {
      getMe: (state) => state.me,
      getUsers: (state) => state.users,
      getToken: (state) => state.token,
      getPermissions: (state) => state.permissions,
      isLoading: (state) => state.loading,
    },
    actions: {
      clearList() {
        this.users = []
      },
      async login(credentials: any) {
        this.loading = true
        let token
        await handleRequest<any>(
          axios.post(`${API_PATHS.auth}/token/`, credentials),
          (data) => {
            token = data.token
            axios.defaults.headers.common["Authorization"] = `Token ${token}`
            localStorage.setItem("token", token);
            successNotification("Login successful")
          },
          (errorMsg) => {
            let description = errorMsg.includes(": ") ? errorMsg.split(": ")[1] : errorMsg
            errorNotification(description)
            console.log(errorMsg)
          },
          () => { this.loading = false }
        )
        return token
      },
      async fetchUsers() {
        this.loading = true
        await handleRequest<any>(
          axios.get("auth/users/"),
          (data) => {
            console.log(data)
            this.users = data
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => { this.loading = false }
        )
      },
      async updateUser(userId: Number, updatedData: IUser) {
        this.loading = true
        await handleRequest<any>(
          axios.patch(`auth/users/${userId}/`, updatedData),
          (data) => {
            const existingIndex = this.users.findIndex(user => user.id === userId);
            if (existingIndex !== -1) {
              this.users[existingIndex] = { ...this.users[existingIndex], ...data }; // Update with new data
            }
            successNotification("Updated successfully.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => { this.loading = false }
        )
      },
      async deleteUser(userId: Number) {
        this.loading = true;
        await handleRequest<void>( // Void response expected
          axios.delete(`auth/users/${userId}/`),
          () => {
            this.users = this.users.filter((user: IUser) => user.id !== userId);
            successNotification("Deleted successfully.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => this.loading = false
        );
      },
      async signup(credentials: any) {
        this.loading = true
        await handleRequest<any>(
          axios.post("auth/users/", credentials),
          (data) => {
            console.log(data)
            successNotification("Registration successful")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => { this.loading = false }
        )
      },
      async logout() {
        this.loading = true
        await handleRequest<any>(
          axios.post(`${API_PATHS.auth}/logout/`),
          (data) => {
            console.log(data)
            successNotification("Logout successful")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => { this.loading = false }
        )
        delete axios.defaults.headers.common["Authorization"]
      },
      async fetchPermissions() {
        this.loading = true
        await handleRequest<any>(
          axios.get(`${API_PATHS.auth}/permissions/`),
          (data) => {
            console.log(data)
            this.permissions = data
          },
          (errorMsg) => {
            console.log(errorMsg)
          },
          () => { this.loading = false }
        )
      },
      async changePassword(password: any) {
        this.loading = true
        await handleRequest<any>(
          axios.post(`${API_PATHS.auth}/change_password/`, password),
          (data) => {
            successNotification(data)
          },
          (errorMsg) => {
            errorNotification(errorMsg)
          },
          () => { this.loading = false }
        )
      }
    }
  }
)

export const useDoorsStore = defineStore(
  "doors",
  {
    state: () => ({
      loading: true,
      ipAddress: axios.defaults.baseURL
    }),
    getters: {
      isLoading: (state) => state.loading,
    },
    actions: {
      async createScript(excel: any) {
        this.loading = true
        let script
        await handleRequest<any>(
          axios.post(`${API_PATHS.doors}/script/`, excel),
          (data) => {
            script = data
            successNotification("Script created successfully.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.error(errorMsg)
          },
          () => { this.loading = false }
        )
        return script
      },
      async run_dxl(modulePath: any) {
        this.loading = true
        const report = await handleRequest<any>(
          axios.post(`${API_PATHS.doors}/run_dxl/`, modulePath),
          (data) => {
            successNotification("DOORS triggered successfully.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.error(errorMsg)
          },
          () => { this.loading = false }
        )
        return report
      },
    }
  }
)

export const useDdfStore = defineStore(
  "ddf",
  {
    state: () => ({
      ddfList: [] as IDdf[],
      loading: true,
      ipAddress: axios.defaults.baseURL
    }),
    getters: {
      getList: (state) => state.ddfList,
      isLoading: (state) => state.loading,
      getUploadUrl: (state) => `${BASE_URL}/ddf/upload/`,
    },
    actions: {
      clearList() {
        this.ddfList = []
      },
      async uploadDdf(ddf: any) {
        this.loading = true
        let res
        await handleRequest<IDdf>(
          axios.post(`${API_PATHS.ddf}/upload/`, ddf),
          (data) => {
            res = data
            this.ddfList.unshift(data);
            successNotification("DDF content successfully read.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.error(errorMsg)
          },
          () => { this.loading = false }
        )
        return res
      },
      async fetchDdf() {
        this.loading = true
        await handleRequest<any>(
          axios.get("ddf/"),
          (data) => {
            console.log(data)
            this.ddfList = data.reverse()
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => { this.loading = false }
        )
      },
      async createDdf(newDdf: IDdf) {
        this.loading = true;
        await handleRequest<IDdf>(
          axios.post(`${API_PATHS.ddf}/`, newDdf),
          (data) => {
            this.ddfList.unshift(data);
            successNotification("New document added successfully.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => this.loading = false
        )
      },
      async updateDdf(ddfId: Number, updatedData: IDcc) {
        this.loading = true;
        await handleRequest<IDdf>(
          axios.put(`${API_PATHS.ddf}/${ddfId}/`, updatedData),
          (data) => {
            const existingIndex = this.ddfList.findIndex(ddf => ddf.id === ddfId);
            if (existingIndex !== -1) {
              this.ddfList[existingIndex] = { ...this.ddfList[existingIndex], ...data };
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
      async deleteDdf(ddfId: Number) {
        this.loading = true;
        await handleRequest<void>( // Void response expected
          axios.delete(`${API_PATHS.ddf}/${ddfId}/`),
          () => {
            this.ddfList = this.ddfList.filter((ddf: IDdf) => ddf.id !== ddfId);
            successNotification("Deleted successfully.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => this.loading = false
        );
      },
      async deleteDdfs() {
        this.loading = true;
        await handleRequest<any>( // Void response expected
          axios.delete(`${API_PATHS.ddf}/`),
          (data) => {
            this.ddfList = [];
            successNotification(data.message)
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => this.loading = false
        );
      },
      async assessment(ddf: IDdf) {
        let res
        await handleRequest<any>(
          axios.post(`${API_PATHS.ddf}/assessment/`, ddf),  // POST request
          (data) => {
            res = data
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => { }
        )
        return res
      },
    }
  }
)

export const useDocproofStore = defineStore(
  "docproof",
  {
    state: () => ({
      loading: true,
      ipAddress: axios.defaults.baseURL
    }),
    getters: {
      isLoading: (state) => state.loading,
    },
    actions: {
      async search(document_no: any) {
        this.loading = true
        let res
        await handleRequest<number>(
          axios.get(`${API_PATHS.docproof}/search/?document_no=${document_no}`),
          (data) => {
            res = data
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.error(errorMsg)
            res = "Error"
          },
          () => { this.loading = false }
        )
        return res
      },
    }
  }
)

export const useOrgsStore = defineStore(
  "orgs",
  {
    state: () => ({
      loading: false,
      project: "" as string,
      projects: [] as IProject[],
      panels: [] as IPanel[],
      responsibles: [] as IResponsible[],
      people: [] as IPerson[],
    }),
    getters: {
      isLoading: (state) => state.loading,
      getProjects: (state) => state.projects,
      getPanels: (state) => state.panels.sort((a, b) => a.name.localeCompare(b.name, 'tr', { sensitivity: 'base' })),
      getPanelOptions: (state) => {
        const uniqueNames = new Set(state.panels.map(panel => panel.name));
        return Array.from(uniqueNames)
          .sort((a, b) => a.localeCompare(b, 'tr', { sensitivity: 'base' }))
          .map(name => ({ label: toTitleCase(name), value: name }));
      },
      getAtaOptions: (state) => state.panels.sort((a, b) => a.ata.localeCompare(b.ata, 'tr', { sensitivity: 'base' })).map((panel) => {
        return { label: panel.ata, value: panel.ata }
      }),
      getResponsibles: (state) => state.responsibles.sort((a, b) => a.name.localeCompare(b.name, 'tr', { sensitivity: 'base' })),
      getPeople: (state) => {
        if (nullCheck(state.people)) {
          useOrgsStore().fetchPeople()
        }
        return state.people.sort((a, b) => a.name.localeCompare(b.name, 'tr', { sensitivity: 'base' }))
      },
    },
    actions: {
      setProject(projectName: string) {
        this.project = projectName
      },
      async fetchProjects() {
        this.loading = true
        await handleRequest<any>(
          axios.get(`${API_PATHS.orgs}/projects/`),
          (data) => {
            this.projects = data
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.error(errorMsg)
          },
          () => { this.loading = false }
        )
      },
      async createProject(newProjectData: IProject) {
        this.loading = true;
        await handleRequest<IProject>(
          axios.post(`${API_PATHS.orgs}/projects/`, newProjectData),  // POST request
          (data) => {
            this.projects.unshift(data);  // Add created doc to existing list
            successNotification("New project added successfully.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => this.loading = false
        )
      },
      async updateProject(projectId: Number, updatedData: IProject) {
        this.loading = true;
        await handleRequest<IProject>(
          axios.put(`${API_PATHS.orgs}/projects/${projectId}/`, updatedData),  // PUT with ID
          (data) => {
            const existingIndex = this.projects.findIndex(project => project.id === projectId);
            if (existingIndex !== -1) { // Doc found
              this.projects[existingIndex] = { ...this.projects[existingIndex], ...data }; // Update with new data
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
      async deleteProject(projectId: Number) {
        this.loading = true;
        await handleRequest<void>( // Void response expected
          axios.delete(`${API_PATHS.orgs}/projects/${projectId}/`),
          () => {
            this.projects = this.projects.filter((project: IProject) => project.id !== projectId);
            successNotification("Deleted successfully.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => this.loading = false
        );
      },
      async fetchPanels() {
        this.loading = true
        await handleRequest<any>(
          axios.get(`${this.project}/${API_PATHS.orgs}/panels/`),
          (data) => {
            this.panels = data
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.error(errorMsg)
          },
          () => { this.loading = false }
        )
      },
      async createPanel(newPanelData: IPanel) {
        this.loading = true;
        await handleRequest<IPanel>(
          axios.post(`${this.project}/${API_PATHS.orgs}/panels/`, newPanelData),
          (data) => {
            this.panels.unshift(data);
            successNotification("New panel added successfully.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
            console.log(errorMsg)
          },
          () => this.loading = false
        )
      },
      async updatePanel(panelId: Number, updatedData: IPanel) {
        this.loading = true;
        await handleRequest<IPanel>(
          axios.put(`${this.project}/${API_PATHS.orgs}/panels/${panelId}/`, updatedData),
          (data) => {
            const existingIndex = this.panels.findIndex((panel: IPanel) => panel.id === panelId);
            if (existingIndex !== -1) {
              this.panels[existingIndex] = { ...this.panels[existingIndex], ...data };
            }
            successNotification("Updated successfully.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
          },
          () => this.loading = false
        )
      },
      async deletePanel(panelId: Number) {
        this.loading = true;
        await handleRequest<void>( // Void response expected
          axios.delete(`${this.project}/${API_PATHS.orgs}/panels/${panelId}/`),
          () => {
            this.panels = this.panels.filter((panel: IPanel) => panel.id !== panelId);
            successNotification("Deleted successfully.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
          },
          () => this.loading = false
        );
      },
      async fetchResponsibles(panel: string) {
        this.loading = true
        await handleRequest<any>(
          axios.get(`${this.project}/${API_PATHS.orgs}/responsibles/?panel=${panel}`),
          (data) => {
            this.responsibles = data
          },
          (errorMsg) => {
            errorNotification(errorMsg)
          },
          () => { this.loading = false }
        )
      },
      async createResponsible(newPersonData: IResponsible) {
        this.loading = true;
        await handleRequest<IResponsible>(
          axios.post(`${this.project}/${API_PATHS.orgs}/responsibles/`, newPersonData),
          (data) => {
            this.responsibles.unshift(data);
            successNotification("New person added successfully.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
          },
          () => this.loading = false
        )
      },
      async updateResponsible(responsibleId: Number, updatedData: IResponsible) {
        this.loading = true;
        await handleRequest<IResponsible>(
          axios.put(`${this.project}/${API_PATHS.orgs}/responsibles/${responsibleId}/`, updatedData),
          (data) => {
            const existingIndex = this.responsibles.findIndex((responsible: IResponsible) => responsible.id === responsibleId);
            if (existingIndex !== -1) {
              this.responsibles[existingIndex] = { ...this.responsibles[existingIndex], ...data };
            }
            successNotification("Updated successfully.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
          },
          () => this.loading = false
        )
      },
      async deleteResponsible(responsibleId: Number) {
        this.loading = true;
        await handleRequest<void>( // Void response expected
          axios.delete(`${this.project}/${API_PATHS.orgs}/responsibles/${responsibleId}/`),
          () => {
            this.people = this.responsibles.filter((responsible: IResponsible) => responsible.id !== responsibleId);
            successNotification("Deleted successfully.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
          },
          () => this.loading = false
        );
      },
      async fetchPeople() {
        this.loading = true
        await handleRequest<any>(
          axios.get(`${API_PATHS.orgs}/people/`),
          (data) => {
            this.people = data
          },
          (errorMsg) => {
            errorNotification(errorMsg)
          },
          () => { this.loading = false }
        )
      },
      async createPerson(newPersonData: IPerson) {
        this.loading = true;
        await handleRequest<IPerson>(
          axios.post(`${API_PATHS.orgs}/people/`, newPersonData),
          (data) => {
            this.people.unshift(data);
            successNotification("New person added successfully.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
          },
          () => this.loading = false
        )
      },
      async updatePerson(peopleId: Number, updatedData: IPerson) {
        this.loading = true;
        await handleRequest<IPerson>(
          axios.put(`${API_PATHS.orgs}/people/${peopleId}/`, updatedData),
          (data) => {
            const existingIndex = this.people.findIndex((person: IPerson) => person.id === peopleId);
            if (existingIndex !== -1) {
              this.people[existingIndex] = { ...this.people[existingIndex], ...data };
            }
            successNotification("Updated successfully.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
          },
          () => this.loading = false
        )
      },
      async deletePerson(personId: Number) {
        this.loading = true;
        await handleRequest<void>( // Void response expected
          axios.delete(`${API_PATHS.orgs}/people/${personId}/`),
          () => {
            this.people = this.people.filter((person: IPerson) => person.id !== personId);
            successNotification("Deleted successfully.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
          },
          () => this.loading = false
        );
      },
      async uploadPeople(file: any) {
        this.loading = true;
        const res = await handleRequest<any>(
          axios.post(`${API_PATHS.orgs}/upload_people/`, file),
          (data) => {
            successNotification(data.message)
          },
          (errorMsg) => {
            errorNotification(errorMsg)
          },
          () => this.loading = false
        )
        return res
      },
    }
  }
)

export const useExcelStore = defineStore(
  "excel",
  {
    state: () => ({
      loading: true,
    }),
    getters: {
      isLoading: (state) => state.loading,
    },
    actions: {
      async getExcelColumns(excel: any) {
        this.loading = true
        const columns = await handleRequest<string[]>(
          axios.post(`${API_PATHS.excel}/get_excel_columns/`, excel),
          (data) => {
            successNotification("Excel content successfully read.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
          },
          () => { this.loading = false }
        )
        return columns
      },
      async excelToCoverPages(excel: any) {
        this.loading = true
        const res = await handleRequest<string[]>(
          axios.post(`${API_PATHS.excel}/excel_to_cover_pages/`, excel),
          (data) => {
            console.log(data)
            successNotification("Cover pages successfully created.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
          },
          () => { this.loading = false }
        )
        return res
      },
    }
  }
)

export const usePptxStore = defineStore(
  "pptxgallery",
  {
    state: () => ({
      loading: false,
      presentations: [] as any[]
    }),
    getters: {
      isLoading: (state) => state.loading,
      getPresentations: (state) => state.presentations,
    },
    actions: {
      async uploadPresentation(form: any) {
        this.loading = true
        const res = await handleRequest<any>(
          axios.post(`${API_PATHS.presentations}/presentations/upload/`, form, { headers: { 'Content-Type': 'multipart/form-data' } }),
          (data) => {
            console.log(data)
            successNotification("Presentation content successfully uploaded.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
          },
          () => { this.loading = false }
        )
        return res
      },
      async fetchPresentations() {
        this.loading = true
        const res = await handleRequest<any[]>(
          axios.get(`${API_PATHS.presentations}/presentations/`),
          (data) => {
            console.log(data)
            this.presentations = data
          },
          (errorMsg) => {
            errorNotification(errorMsg)
          },
          () => { this.loading = false }
        )
        return res
      },
      async removePresentation(id: number) {
        this.loading = true
        const res = await handleRequest<any>(
          axios.delete(`${API_PATHS.presentations}/presentations/${id}/`),
          (data) => {
            console.log(data)
          },
          (errorMsg) => {
            errorNotification(errorMsg)
          },
          () => { this.loading = false }
        )
        return res
      },
      async reconvertPresentation(id: number) {
        this.loading = true
        const res = await handleRequest<any>(
          axios.post(`${API_PATHS.presentations}/presentations/${id}/reconvert/`),
          (data) => {
            console.log(data)
          },
          (errorMsg) => {
            errorNotification(errorMsg)
          },
          () => { this.loading = false }
        )
        return res
      },
      async deleteSlide(id: number) {
        this.loading = true
        const res = await handleRequest<any>(
          axios.delete(`${API_PATHS.presentations}/slides/${id}/`),
          (data) => {
            console.log(data)
          },
          (errorMsg) => {
            errorNotification(errorMsg)
          },
          () => { this.loading = false }
        )
        return res
      },
      async loadSlide(id: number) {
        this.loading = true
        const res = await handleRequest<any>(
          axios.get(`${API_PATHS.presentations}/presentations/${id}/`),
          (data) => {
            console.log(data)
          },
          (errorMsg) => {
            errorNotification(errorMsg)
          },
          () => { this.loading = false }
        )
        return res
      },
      async updateSlide(id: number, form: any) {
        this.loading = true
        const res = await handleRequest<any>(
          axios.patch(`/slides/${id}/`, form),
          (data) => {
            console.log(data)
          },
          (errorMsg) => {
            errorNotification(errorMsg)
          },
          () => { this.loading = false }
        )
        return res
      },
    }
  }
)

export const useOutlookStore = defineStore(
  "outlook",
  {
    state: () => ({
      loading: false,
      msg: {} as IMsg
    }),
    getters: {
      isLoading: (state) => state.loading,
      getMsg: (state) => state.msg,
    },
    actions: {
      async parseMsg(msg: any) {
        this.loading = true
        const parsed = await handleRequest<IMsg>(
          axios.post(`${API_PATHS.outlook}/msg/parse/`, msg),
          (data) => {
            this.msg = data
            successNotification("Mail content successfully read.")
          },
          (errorMsg) => {
            errorNotification(errorMsg)
          },
          () => { this.loading = false }
        )
        return parsed
      },
    }
  }
)