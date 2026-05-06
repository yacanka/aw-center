export interface IAttachment {
  id?: string
  name?: string
  size: number
  mime?: string
  download_url?: string
  content_base64?: string
  [key: string]: unknown
}

export interface IMsg {
  id?: string
  mail?: {
    subject?: string
    [key: string]: unknown
  }
  attachments?: IAttachment[]
  [key: string]: unknown
}

export interface IPopup {
  closable?: boolean
  visible: boolean
  title?: string
  input?: unknown
  onClick?: ((value?: unknown) => void) | null
  [key: string]: unknown
}

export interface TaskItem {
  id?: string
  title?: string
  description?: string
  run?: () => Promise<void> | void
  [key: string]: unknown
}
