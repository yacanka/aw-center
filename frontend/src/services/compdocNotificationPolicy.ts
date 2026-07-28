import axios from 'axios'
import type { CompDocNotificationEvent } from '@/services/compdocTracking'

export interface CompDocNotificationRule {
  reminder_interval_hours: number
  failure_retry_hours: number
  primary_titles: string[]
  escalation_titles: string[]
  escalate_after_hours: number
}

export type CompDocNotificationRules = Record<CompDocNotificationEvent, CompDocNotificationRule>

export interface CompDocNotificationPolicyRevision {
  version: number
  change_note: string
  updated_by: string
  created_at: string
  is_active: boolean
}

export interface CompDocNotificationPolicy {
  project: string
  configured: boolean
  version: number
  rules: CompDocNotificationRules
  role_options: Array<{ value: string; label: string }>
  event_options: Array<{ value: CompDocNotificationEvent; label: string }>
  can_manage: boolean
  change_note: string
  updated_by: string
  updated_at: string | null
  history: CompDocNotificationPolicyRevision[]
}

export interface CompDocNotificationPolicyUpdate {
  expected_version: number
  change_note: string
  rules: CompDocNotificationRules
}

/** Load the active project policy and immutable revision summaries. */
export async function fetchCompDocNotificationPolicy(project: string) {
  return (await axios.get<CompDocNotificationPolicy>(policyPath(project))).data
}

/** Publish one optimistic, immutable project policy revision. */
export async function saveCompDocNotificationPolicy(
  project: string,
  payload: CompDocNotificationPolicyUpdate
) {
  return (await axios.put<CompDocNotificationPolicy>(policyPath(project), payload)).data
}

/** Clone policy rules before local editing without mutating the active response. */
export function cloneCompDocNotificationRules(rules: CompDocNotificationRules) {
  return Object.fromEntries(
    Object.entries(rules).map(([event, rule]) => [
      event,
      {
        ...rule,
        primary_titles: [...rule.primary_titles],
        escalation_titles: [...rule.escalation_titles]
      }
    ])
  ) as CompDocNotificationRules
}

function policyPath(project: string) {
  return `/${encodeURIComponent(project)}/compdocs/notification-policy/`
}
