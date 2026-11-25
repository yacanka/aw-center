import { apiClient } from '@/shared/api/http'
import type { ProjectRegistryItem } from '../models/projectRegistry'

export const fieldLabels = {
  jira_component: 'JIRA component',
  aliases: 'Alternatif adlar',
  dcc_label: 'DCC etiketi',
  dcc_template_name: 'DCC Word şablonu',
  mail_template_name: 'Mail şablonu adı'
} as const

export const statusLabels = {
  configured: 'Tanımlı',
  invalid: 'Geçersiz',
  missing: 'Tanımlanmamış',
  unavailable: 'Yapılandırma okunamadı',
  partial: 'Kısmen geçerli',
  ambiguous: 'Çakışan ad'
} as const

interface FieldDetail {
  status: keyof typeof statusLabels
  value?: string | string[]
}

export interface ProjectOverview extends ProjectRegistryItem {
  enabled: boolean
  configuration: Partial<Record<keyof typeof fieldLabels, FieldDetail>>
}

export async function fetchProjectOverview(): Promise<ProjectOverview[]> {
  return (await apiClient.get<ProjectOverview[]>('projects/overview/')).data
}
