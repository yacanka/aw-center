import axios from "axios"
import { readString, STORAGE_KEYS } from "./storage"

export const API_BASE_URL = import.meta.env.VITE_API_URL

axios.defaults.baseURL = API_BASE_URL

export function setAuthToken(token: string | null) {
  if (token) {
    axios.defaults.headers.common["Authorization"] = `Token ${token}`
    return
  }

  delete axios.defaults.headers.common["Authorization"]
}

export function bootstrapHttpAuth() {
  setAuthToken(readString(STORAGE_KEYS.token))
}
