import { IUser, IPermission, IPreferences } from "@/models/auth"
import { defineStore } from "pinia"
import axios from "axios"
import { handleRequest } from "@/composables/promise"
import { setAuthToken } from "@/services/http"
import { notifyError } from "@/services/notify"
import { readJson, STORAGE_KEYS, removeKey, writeJson, writeString } from "@/services/storage"


let currentUser: IUser | null = null

export function setUser(user: IUser) {
    currentUser = user
    writeJson(STORAGE_KEYS.user, user)
}

export function getUser() {
    if (currentUser) return currentUser
    currentUser = readJson<IUser | null>(STORAGE_KEYS.user, null)
    return currentUser
}

export function isAuthenticated() {
    return !!getUser()
}

export function logout() {
    currentUser = null
    removeKey(STORAGE_KEYS.token)
    removeKey(STORAGE_KEYS.user)
    removeKey(STORAGE_KEYS.project)
    setAuthToken(null)
}

export function setProjectName(name: string) {
    writeString(STORAGE_KEYS.project, name)
}

export const useUserStore = defineStore(
    "user",
    {
        state: () => ({
            loading: true,
            user: {} as IUser,
            permissions: [] as IPermission[],
            preferences: {} as IPreferences,
        }),
        getters: {
            getUser: (state) => state.user,
            getPermissions: (state) => state.permissions,
            getPreferences: (state) => state.preferences,
        },
        actions: {
            setUser(user: IUser) {
                this.user = user
                this.permissions = user.permissions
                this.preferences = user.preferences
                writeJson(STORAGE_KEYS.user, user)
            },
            checkPermission(permissionName: string) {
                return this.permissions.some(permission => permission.codename == permissionName)
            },
            hasRole(app: string, role: string) {
                return this.permissions.some((permission: IPermission) => permission.content_type.app_label == app && permission.codename == role)
            },
            async updatePreference(preferencesData: IPreferences) {
                this.loading = true;
                await handleRequest<IPreferences>(
                    axios.patch(`auth/preferences/`, preferencesData),  // POST request
                    (data) => {
                        this.preferences = data;  // Add created doc to existing list
                        window.$message.success("Preferences updated successfully.")
                    },
                    (errorMsg) => {
                        notifyError(errorMsg)
                        console.log(errorMsg)
                    },
                    () => this.loading = false
                )
            },
            async fetchCurrentUser() {
                this.loading = true
                await handleRequest<IUser>(
                    axios.get(`auth/me/`),
                    (data) => {
                        this.setUser(data)
                    },
                    (errorMsg) => {
                        console.log(errorMsg)
                    },
                    () => this.loading = false
                )
            },
            async resetPasswordRequest(payload: object) {
                this.loading = true
                await handleRequest<IUser>(
                    axios.post(`auth/password-reset/`, payload),
                    (data) => {
                        console.log(data)
                    },
                    (errorMsg) => {
                        console.log(errorMsg)
                    },
                    () => this.loading = false
                )
            },
            async resetPasswordConfirm(payload: object) {
                this.loading = true
                await handleRequest<IUser>(
                    axios.post(`auth/password-reset/confirm/`, payload),
                    (data) => {
                        console.log(data)
                    },
                    (errorMsg) => {
                        console.log(errorMsg)
                    },
                    () => this.loading = false
                )
            },
        }
    }
)
