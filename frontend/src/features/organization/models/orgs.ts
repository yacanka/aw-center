import type { ProjectRegistryItem } from '@/features/projects/models/projectRegistry'

export type IProject = ProjectRegistryItem

export interface IPanel {
  id?: number
  name: string
  slug?: string
  project?: string
  project_slug?: string
  ata: string
  discipline?: string
}

export interface IResponsible {
  id?: number
  project?: string
  panel: number | null
  panel_ata?: string
  name: string
  email: string
  responsibility_role: string
  panel_name?: string
  person_id: string
}

export interface IPerson {
  id?: number
  person_id: string
  name: string
  email: string
  mail?: string
}

export type OrganizationOption = { label: string; value: string | number }
