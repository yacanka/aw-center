import { IUser, IPermission, IPreferences } from "@/models/auth"
import { defineStore } from "pinia"
import axios from "axios"
import { handleRequest } from "@/composables/promise"


let currentUser: IUser | null

export function setUser(user: IUser) {
    currentUser = user
    localStorage.setItem("user", JSON.stringify(user))
}

export function getUser() {
    if (currentUser) return currentUser
    const stored = localStorage.getItem("user")
    currentUser = stored ? JSON.parse(stored) : null
    return currentUser
}

export function isAuthenticated() {
    return !!getUser()
}

export function logout() {
    currentUser = null
    localStorage.removeItem("token");
    localStorage.removeItem("user")
    localStorage.removeItem("project")
}

export function setProjectName(name: string) {
    localStorage.setItem("project", name)
}

const errorNotification = (message: string = "", title: string = "Error", duration: number = 3000) => {
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
                localStorage.setItem("user", JSON.stringify(user))
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
                        errorNotification(errorMsg)
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