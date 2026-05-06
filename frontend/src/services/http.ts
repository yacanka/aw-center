import axios from "axios"

export const API_BASE_URL = import.meta.env.VITE_API_URL

axios.defaults.baseURL = API_BASE_URL
axios.defaults.withCredentials = true

export function setAuthToken(token: string | null) {
  if (token) {
    axios.defaults.headers.common["Authorization"] = `Token ${token}`
    return
  }

  delete axios.defaults.headers.common["Authorization"]
}

export function bootstrapHttpAuth() {}
