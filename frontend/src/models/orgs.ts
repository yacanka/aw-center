export interface IProject {
  id?: number
  name?: string
  [key: string]: unknown
}

export interface IPanel {
  id?: number
  name?: string
  project?: number | string
  [key: string]: unknown
}

export interface IResponsible {
  id?: number
  name?: string
  panel?: number | string
  [key: string]: unknown
}

export interface IPerson {
  id?: number
  name?: string
  mail?: string
  [key: string]: unknown
}
