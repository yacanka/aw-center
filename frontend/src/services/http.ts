import axios from "axios"
import { readString, STORAGE_KEYS } from "@/services/storage"

export const API_BASE_URL = import.meta.env.VITE_API_URL

axios.defaults.baseURL = API_BASE_URL
axios.defaults.withCredentials = true

axios.interceptors.request.use((config) => {
  config.withCredentials = true
  return config
})

/**
 * Sets or clears the shared Axios token header for authenticated API calls.
 */
export function setAuthToken(token: string | null) {
  if (token) {
    axios.defaults.headers.common["Authorization"] = `Token ${token}`
    return
  }

  delete axios.defaults.headers.common["Authorization"]
}

/**
 * Restores the optional development token fallback for cross-origin HTTP setups.
 */
export function bootstrapHttpAuth() {
  setAuthToken(readString(STORAGE_KEYS.token))
}
