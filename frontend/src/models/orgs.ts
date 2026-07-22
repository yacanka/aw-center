import type { ProjectCapability } from '@/models/projectRegistry'

export interface IProject {
  slug: string
  display_name: string
  route: string
  enabled: boolean
  capabilities: ProjectCapability[]
  tags: string[]
}

export interface IPanel {
  id?: number
  name: string
  slug?: string
  project?: string
  ata: string
  discipline?: string
}

export interface IResponsible {
  id?: number
  project?: string
  panel: string
  name: string
  email: string
  title: string
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

export type OrganizationOption = { label: string; value: string }
