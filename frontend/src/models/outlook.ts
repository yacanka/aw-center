export interface IAttachment {
  id?: string
  name: string
  size: number
  mime: string
  download_url?: string
  [key: string]: unknown
}

export interface IMsg {
  id?: string
  mail: {
    subject: string
    sender: string
    to: string
    cc: string
    date: string
    body_plain: string
  }
  attachments: IAttachment[]
}

export interface IPopup<Input = string> {
  closable?: boolean
  visible: boolean
  title?: string
  input: Input
  onClick: (() => void) | null
}

export type TaskStatus = 'error' | 'success' | 'warning' | 'info' | 'default'

export type TaskEvent = (message?: string | null) => void | Promise<void>

export interface TaskItem {
  id?: string
  title: string
  description?: string
  descriptions: { onSuccess: string; onError: string }
  status?: TaskStatus
  events: {
    ProgressEvent: TaskEvent
    SuccessEvent: TaskEvent
    ErrorEvent: TaskEvent
  }
}
