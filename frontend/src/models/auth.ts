export interface IPermission {
  id?: number
  name?: string
  codename?: string
  content_type?: { app_label?: string; model?: string }
  [key: string]: unknown
}

export interface IPreferences {
  [key: string]: unknown
}

export interface IUser {
  id?: number
  username?: string
  email?: string
  first_name?: string
  last_name?: string
  is_active?: boolean
  permissions?: IPermission[]
  preferences?: IPreferences
  [key: string]: unknown
}
