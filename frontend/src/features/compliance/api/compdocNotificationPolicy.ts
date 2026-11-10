import { apiClient as axios } from '@/shared/api/http'
import type { CompDocNotificationEvent } from '@/features/compliance/api/compdocTracking'
import { compdocCollectionPath } from '@/shared/api/apiPaths'

export interface CompDocNotificationRule {
  enabled: boolean
}

export type CompDocNotificationRules = Partial<
  Record<CompDocNotificationEvent, CompDocNotificationRule>
>

export interface CompDocNotificationPolicy {
  version: number
  event_rules: CompDocNotificationRules
  change_note: string
  updated_by?: string
  updated_at: string | null
  allowed_actions: { manage: boolean }
}

export interface CompDocNotificationPolicyUpdate {
  version: number
  change_note: string
  event_rules: CompDocNotificationRules
}

/** Load the active project policy and immutable revision summaries. */
export async function fetchCompDocNotificationPolicy(project: string) {
  return (await axios.get<CompDocNotificationPolicy>(policyPath(project))).data
}

/** Publish one project notification-policy revision. */
export async function saveCompDocNotificationPolicy(
  project: string,
  payload: CompDocNotificationPolicyUpdate
) {
  return (await axios.put<CompDocNotificationPolicy>(policyPath(project), payload)).data
}

/** Clone policy rules before local editing without mutating the active response. */
export function cloneCompDocNotificationRules(rules: CompDocNotificationRules) {
  return Object.fromEntries(
    Object.entries(rules).map(([event, rule]) => [event, { ...rule }])
  ) as CompDocNotificationRules
}

function policyPath(project: string) {
  return `${compdocCollectionPath(project)}notification-policy/`
}
