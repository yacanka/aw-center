import { defineStore } from "pinia"
import axios from "axios"
import { IUser, IPermission } from "@/models/auth"
import { handleRequest } from "@/composables/promise"
import { setAuthToken } from "@/services/http"
import { notifyError, notifySuccess } from "@/services/notify"
import { removeKey, STORAGE_KEYS, writeString } from "@/services/storage"

const API_PATH = "auth"

export const useAuthStore = defineStore(
  "auth",
  {
    state: () => ({
      me: {} as IUser,
      token: "" as string,
      users: [] as IUser[],
      permissions: [] as IPermission[],
      loading: false,
      ipAddress: axios.defaults.baseURL,
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
        let token = ""
        await handleRequest<any>(
          axios.post(`${API_PATH}/token/`, credentials),
          (data) => {
            token = data.token
            this.token = token
            setAuthToken(token)
            writeString(STORAGE_KEYS.token, token)
            notifySuccess("Login successful")
          },
          (errorMsg) => {
            const description = errorMsg.includes(": ") ? errorMsg.split(": ")[1] : errorMsg
            notifyError(description)
            console.log(errorMsg)
          },
          () => {
            this.loading = false
          }
        )
        return token
      },
      async fetchUsers() {
        this.loading = true
        await handleRequest<any>(
          axios.get(`${API_PATH}/users/`),
          (data) => {
            this.users = data
          },
          (errorMsg) => {
            notifyError(errorMsg)
            console.log(errorMsg)
          },
          () => {
            this.loading = false
          }
        )
      },
      async updateUser(userId: Number, updatedData: IUser) {
        this.loading = true
        await handleRequest<any>(
          axios.patch(`${API_PATH}/users/${userId}/`, updatedData),
          (data) => {
            const existingIndex = this.users.findIndex((user) => user.id === userId)
            if (existingIndex !== -1) {
              this.users[existingIndex] = { ...this.users[existingIndex], ...data }
            }
            notifySuccess("Updated successfully.")
          },
          (errorMsg) => {
            notifyError(errorMsg)
            console.log(errorMsg)
          },
          () => {
            this.loading = false
          }
        )
      },
      async deleteUser(userId: Number) {
        this.loading = true
        await handleRequest<void>(
          axios.delete(`${API_PATH}/users/${userId}/`),
          () => {
            this.users = this.users.filter((user: IUser) => user.id !== userId)
            notifySuccess("Deleted successfully.")
          },
          (errorMsg) => {
            notifyError(errorMsg)
            console.log(errorMsg)
          },
          () => {
            this.loading = false
          }
        )
      },
      async signup(credentials: any) {
        this.loading = true
        await handleRequest<any>(
          axios.post(`${API_PATH}/users/`, credentials),
          () => {
            notifySuccess("Registration successful")
          },
          (errorMsg) => {
            notifyError(errorMsg)
            console.log(errorMsg)
          },
          () => {
            this.loading = false
          }
        )
      },
      async logout() {
        this.loading = true
        await handleRequest<any>(
          axios.post(`${API_PATH}/logout/`),
          () => {
            notifySuccess("Logout successful")
          },
          (errorMsg) => {
            notifyError(errorMsg)
            console.log(errorMsg)
          },
          () => {
            this.loading = false
          }
        )

        this.token = ""
        setAuthToken(null)
        removeKey(STORAGE_KEYS.token)
      },
      async fetchPermissions() {
        this.loading = true
        await handleRequest<any>(
          axios.get(`${API_PATH}/permissions/`),
          (data) => {
            this.permissions = data
          },
          (errorMsg) => {
            console.log(errorMsg)
          },
          () => {
            this.loading = false
          }
        )
      },
      async changePassword(password: any) {
        this.loading = true
        await handleRequest<any>(
          axios.post(`${API_PATH}/change_password/`, password),
          (data) => {
            notifySuccess(data)
          },
          (errorMsg) => {
            notifyError(errorMsg)
          },
          () => {
            this.loading = false
          }
        )
      },
    },
  }
)
