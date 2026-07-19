export interface IPermission {
  id?: number
  name?: string
  codename?: string
  content_type?: { app_label?: string; model?: string }
  [key: string]: unknown
}

export interface IPreferences {
  theme?: 'light' | 'dark' | 'system'
  has_particles?: boolean
  language?: 'en' | 'tr'
  timezone?: string
  email_notifications?: boolean
  push_notifications?: boolean
  sms_notifications?: boolean
  newsletter_subscribed?: boolean
  profile_visible?: boolean
  show_online_status?: boolean
  show_activity?: boolean
  items_per_page?: number
  compact_view?: boolean
  extra_settings?: Record<string, unknown>
  jira_list?: unknown[]
}

export interface IGroup {
  id?: number
  name?: string
  permissions?: IPermission[]
  [key: string]: unknown
}

export interface IUser {
  id?: number
  username?: string
  email?: string
  first_name?: string
  last_name?: string
  last_login?: string | null
  is_active?: boolean
  is_staff?: boolean
  is_superuser?: boolean
  permissions?: IPermission[]
  groups?: number[]
  group_details?: IGroup[]
  preferences?: IPreferences
  [key: string]: unknown
}
